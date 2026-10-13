// -----------------------------------------------------------------------------
// FPGA "C" de la carte CHA : sprites.
//
// Remplace les ROM C, la partie "C" du NEO-273 (verrou d'adresse PCK1B) et le
// sérialiseur du NEO-ZMC2. ROM C dans une SDRAM x16 de 64 Mo (512 Mbit) :
// chaque verrou PCK1B déclenche 4 lectures dans la même ligne (deux mots de
// 32 bits : moitiés CA4 = 0 et 1).
// -----------------------------------------------------------------------------
module cha_c_core #(
    parameter SDRAM_INIT_WAIT = 20000,
    parameter SDRAM_REFI      = 780
) (
    input  wire        clk,               // 100 MHz
    input  wire        rst,

    input  wire [23:0] pbus,
    input  wire        pck1b,
    input  wire        ca4,
    input  wire        clk_12m,
    input  wire        even,
    input  wire        load,
    input  wire        h,
    output wire [3:0]  gad,
    output wire [3:0]  gbd,
    output wire        dota,
    output wire        dotb,

    input  wire        lk_sck,
    input  wire        lk_cs_n,
    input  wire [3:0]  lk_io_i,
    output wire [3:0]  lk_io_o,
    output wire        lk_io_oe,
    input  wire        mode_in,

    output wire        sd_cke, sd_cs_n, sd_ras_n, sd_cas_n, sd_we_n,
    output wire [1:0]  sd_ba,
    output wire [12:0] sd_a,
    output wire [1:0]  sd_dqm,
    output wire [15:0] sd_dq_o,
    output wire        sd_dq_oe,
    input  wire [15:0] sd_dq_i,

    output wire        led
);
    wire [7:0]  reg_addr;  wire reg_wr;  wire [31:0] reg_wdata;  reg [31:0] reg_rdata;
    wire        reg_rd;
    wire [7:0]  mem_space; wire [31:0] mem_addr; wire mem_wr; wire [7:0] mem_wdata;
    wire        mem_rd;    wire xfer_end;

    qlink u_link (
        .clk(clk), .rst(rst),
        .sck_i(lk_sck), .cs_n_i(lk_cs_n), .io_i(lk_io_i), .io_o(lk_io_o), .io_oe(lk_io_oe),
        .reg_addr(reg_addr), .reg_wr(reg_wr), .reg_wdata(reg_wdata), .reg_rdata(reg_rdata), .reg_rd(reg_rd),
        .mem_space(mem_space), .mem_addr(mem_addr), .mem_wr(mem_wr), .mem_wdata(mem_wdata),
        .mem_rd(mem_rd), .mem_rdata(8'hFF), .xfer_end(xfer_end)
    );

    reg        ctrl_arm = 1'b0, ctrl_force = 1'b0;
    reg [23:0] c_mask = 24'hFFFFFF;       // en mots de 32 bits
    reg [31:0] dbg_addr = 32'h0, dbg_data = 32'h0;
    reg        dbg_req = 1'b0, dbg_busy = 1'b0;
    reg [31:0] cnt_pck1b = 0;

    wire mode_s;
    sync2 u_smode (.clk(clk), .d(mode_in), .q(mode_s));
    reg  game_mode = 1'b0;
    always @(posedge clk) game_mode <= (ctrl_arm & mode_s) | ctrl_force;

    wire sd_init_done, sd_idle, pk_empty, pk_ovf;

    always @(posedge clk) begin
        if (rst) begin
            ctrl_arm <= 1'b0; ctrl_force <= 1'b0;
        end else if (reg_wr) begin
            case (reg_addr)
            8'h01: begin ctrl_arm <= reg_wdata[0]; ctrl_force <= reg_wdata[1]; end
            8'h03: c_mask   <= reg_wdata[23:0];
            8'h10: dbg_addr <= reg_wdata;
            default: ;
            endcase
        end
    end

    localparam CL_IDLE = 2'd0, CL_C = 2'd1, CL_W = 2'd2, CL_DBG = 2'd3;
    reg [1:0] cl_st = CL_IDLE;

    always @* begin
        case (reg_addr)
        8'h00: reg_rdata = 32'h4E474332;   // "NGC2"
        8'h01: reg_rdata = {30'd0, ctrl_force, ctrl_arm};
        8'h02: reg_rdata = {26'd0, dbg_busy, pk_ovf, mode_s, game_mode,
                            pk_empty & sd_idle & (cl_st == CL_IDLE), sd_init_done};
        8'h03: reg_rdata = {8'd0, c_mask};
        8'h10: reg_rdata = dbg_addr;
        8'h11: reg_rdata = dbg_data;
        8'h12: reg_rdata = cnt_pck1b;
        default: reg_rdata = 32'hDEADBEEF;
        endcase
    end

    // =========================================================================
    // CARTOGRAPHIE (à valider sur matériel, cf. docs/03-memoire-et-timings.md)
    // =========================================================================
    // Verrou NEO-273 capturé directement sur la broche PCK1B (front montant).
    reg [23:0] c_latch = 24'h0;
    always @(posedge pck1b) c_latch <= pbus;

    // Mot C (32 bits) : {tuile[19:0], CA4, ligne[3:0]}
    //   tuile[15:0] = P[15:0], ligne = P[19:16], tuile[19:16] = P[23:20]
    function [24:0] c_word_addr(input [23:0] p, input half);
        c_word_addr = {p[23:20], p[15:0], half, p[19:16]};
    endfunction

    // Le .neo entrelace c1/c2 octet par octet : un mot de 32 bits lu en
    // SDRAM = {v3,v2,v1,v0} ; bus CR du ZMC2 = {v3,v1,v2,v0}
    //   CR[7:0] = plan 0, CR[15:8] = plan 1 (c1) ; CR[23:16] = plan 2, CR[31:24] = plan 3 (c2)
    function [31:0] c_remap(input [31:0] w);
        c_remap = {w[31:24], w[15:8], w[23:16], w[7:0]};
    endfunction

    // =========================================================================
    // Lecture des deux moitiés à chaque verrou PCK1B
    // =========================================================================
    wire pck_s;
    sync2 #(.INIT(1'b1)) u_spck (.clk(clk), .d(pck1b), .q(pck_s));
    reg  pck_d = 1'b1;
    always @(posedge clk) pck_d <= pck_s;
    wire pck1_ev = pck_s & ~pck_d;

    reg [31:0] c_half0 = 32'h0, c_half1 = 32'h0;
    reg [15:0] lo_tmp;
    reg        c_pend = 1'b0;
    reg [24:0] c_a0;
    reg [7:0]  since_ev = 8'hFF;

    reg         sq_req = 1'b0, sq_we = 1'b0;
    reg  [24:0] sq_addr;
    reg  [1:0]  sq_nrd;
    reg  [9:0]  sq_col2;
    reg  [15:0] sq_wdata;
    reg  [1:0]  sq_wmask;
    wire        sq_ack, sq_rvalid;
    wire [1:0]  sq_ridx;
    wire [15:0] sq_rdata;

    wire        pk_valid;  wire [24:0] pk_addr; wire [15:0] pk_data; wire [1:0] pk_mask;
    reg         pk_take;
    wr_packer #(.AW(25)) u_pack (
        .clk(clk), .rst(rst),
        .in_stb(mem_wr && mem_space == 8'd0 && !game_mode), .in_addr(mem_addr), .in_data(mem_wdata),
        .flush(xfer_end),
        .out_valid(pk_valid), .out_addr(pk_addr), .out_data(pk_data), .out_mask(pk_mask),
        .out_take(pk_take), .empty(pk_empty), .overflow(pk_ovf));

    always @(posedge clk) begin
        pk_take <= 1'b0;
        if (since_ev != 8'hFF) since_ev <= since_ev + 8'd1;
        if (pck1_ev) begin
            c_pend    <= 1'b1;
            since_ev  <= 8'd0;
            cnt_pck1b <= cnt_pck1b + 1;
        end
        if (reg_wr && reg_addr == 8'h10) begin dbg_req <= 1'b1; dbg_busy <= 1'b1; end

        if (rst) begin
            cl_st <= CL_IDLE; sq_req <= 1'b0; c_pend <= 1'b0; dbg_req <= 1'b0; dbg_busy <= 1'b0;
        end else case (cl_st)
        CL_IDLE: begin
            if (game_mode && (c_pend || pck1_ev)) begin
                c_pend  <= 1'b0;
                c_a0     = c_word_addr(c_latch, 1'b0) & {1'b0, c_mask};
                // mots de 16 bits : 2*a0, 2*a0+1, puis moitié CA4=1 (bit 5)
                sq_req  <= 1'b1;
                sq_we   <= 1'b0;
                sq_addr <= {c_a0[23:0], 1'b0};
                sq_nrd  <= 2'd2;
                sq_col2 <= {c_a0[8:0], 1'b0} | 10'h020;
                cl_st   <= CL_C;
            end else if (!game_mode && pk_valid) begin
                sq_req <= 1'b1; sq_we <= 1'b1; sq_addr <= pk_addr; sq_nrd <= 2'd0;
                sq_wdata <= pk_data; sq_wmask <= pk_mask; pk_take <= 1'b1;
                cl_st <= CL_W;
            end else if (!game_mode && dbg_req) begin
                dbg_req <= 1'b0;
                sq_req <= 1'b1; sq_we <= 1'b0; sq_addr <= dbg_addr[24:0]; sq_nrd <= 2'd0;
                cl_st <= CL_DBG;
            end
            if (!game_mode) c_pend <= 1'b0;
        end
        CL_C: begin
            if (sq_ack) sq_req <= 1'b0;
            if (sq_rvalid) case (sq_ridx)
                2'd0: lo_tmp <= sq_rdata;
                2'd1: c_half0 <= c_remap({sq_rdata, lo_tmp});
                2'd2: lo_tmp <= sq_rdata;
                2'd3: begin c_half1 <= c_remap({sq_rdata, lo_tmp}); cl_st <= CL_IDLE; end
            endcase
        end
        CL_W: if (sq_ack) begin sq_req <= 1'b0; cl_st <= CL_IDLE; end
        CL_DBG: begin
            if (sq_ack) sq_req <= 1'b0;
            if (sq_rvalid) begin dbg_data <= {16'd0, sq_rdata}; dbg_busy <= 1'b0; cl_st <= CL_IDLE; end
        end
        endcase

        if (!game_mode) begin
            c_half0 <= 32'h0;       // menu : sprites transparents
            c_half1 <= 32'h0;
        end
    end

    // rafraîchissement juste après une lecture C, ou bus inactif depuis > 2 us
    wire ref_window = (since_ev < 8'd40) || (since_ev > 8'd200);
    wire ref_hold   = game_mode && (c_pend || pck1_ev || cl_st == CL_C || !ref_window);

    sdram #(.COLW(10), .INIT_WAIT(SDRAM_INIT_WAIT), .REFI(SDRAM_REFI)) u_sdram (
        .clk(clk), .rst(rst),
        .req(sq_req), .we(sq_we), .addr(sq_addr), .nrd(sq_nrd), .col2(sq_col2), .addr2(25'd0),
        .wdata(sq_wdata), .wmask(sq_wmask), .ack(sq_ack),
        .rvalid(sq_rvalid), .ridx(sq_ridx), .rdata(sq_rdata),
        .refresh_hold(ref_hold), .init_done(sd_init_done), .idle(sd_idle),
        .sd_cke(sd_cke), .sd_cs_n(sd_cs_n), .sd_ras_n(sd_ras_n), .sd_cas_n(sd_cas_n), .sd_we_n(sd_we_n),
        .sd_ba(sd_ba), .sd_a(sd_a), .sd_dqm(sd_dqm), .sd_dq_o(sd_dq_o), .sd_dq_oe(sd_dq_oe), .sd_dq_i(sd_dq_i));

    // ZMC2 : bus CR = moitié choisie par CA4 (combinatoire, comme une ROM)
    wire [31:0] cr = ca4 ? c_half1 : c_half0;
    zmc2_dot u_zmc2 (
        .clk_12m(clk_12m), .even(even), .load(load), .h(h), .cr(cr),
        .gad(gad), .gbd(gbd), .dota(dota), .dotb(dotb)
    );

    reg led_r = 1'b0;
    always @(posedge clk) led_r <= game_mode ^ ~pk_empty;
    assign led = led_r;
endmodule
