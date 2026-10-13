// -----------------------------------------------------------------------------
// FPGA "V" de la carte PROG : échantillons ADPCM du YM2610.
//
// Remplace les ROM V et le NEO-PCM2 (démultiplexage des adresses).
//   V1 (ADPCM-A) et V2 (ADPCM-B) dans une SDRAM x16 de 32 Mo.
// Le mode (menu/jeu) vient du FPGA P (entrée MODE).
// -----------------------------------------------------------------------------
module prog_v_core #(
    parameter SDRAM_INIT_WAIT = 20000,
    parameter SDRAM_REFI      = 780
) (
    input  wire        clk,
    input  wire        rst,

    input  wire [7:0]  rad_i,
    output wire [7:0]  rad_o,
    output wire        rad_drive,
    input  wire [9:8]  ra_l,
    input  wire [23:20] ra_u,
    input  wire        rmpx,
    input  wire        roe_n,
    input  wire [7:0]  pad_i,
    output wire [7:0]  pad_o,
    output wire        pad_drive,
    input  wire [11:8] pa,
    input  wire        pmpx,
    input  wire        poe_n,

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
    reg [24:0] v1_base = 25'h0, v2_base = 25'h0;   // en octets
    reg [24:0] v1_mask = 25'hFFFFF, v2_mask = 25'hFFFFF;
    reg [31:0] dbg_addr = 32'h0, dbg_data = 32'h0;
    reg        dbg_req = 1'b0, dbg_busy = 1'b0;
    reg [31:0] cnt_a = 0, cnt_b = 0;

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
            8'h04: v1_base <= reg_wdata[24:0];
            8'h05: v1_mask <= reg_wdata[24:0];
            8'h06: v2_base <= reg_wdata[24:0];
            8'h07: v2_mask <= reg_wdata[24:0];
            8'h10: dbg_addr <= reg_wdata;
            default: ;
            endcase
        end
    end

    always @* begin
        case (reg_addr)
        8'h00: reg_rdata = 32'h4E475632;   // "NGV2"
        8'h01: reg_rdata = {30'd0, ctrl_force, ctrl_arm};
        8'h02: reg_rdata = {26'd0, dbg_busy, pk_ovf, mode_s, game_mode, pk_empty & sd_idle, sd_init_done};
        8'h04: reg_rdata = {7'd0, v1_base};
        8'h05: reg_rdata = {7'd0, v1_mask};
        8'h06: reg_rdata = {7'd0, v2_base};
        8'h07: reg_rdata = {7'd0, v2_mask};
        8'h10: reg_rdata = dbg_addr;
        8'h11: reg_rdata = dbg_data;
        8'h12: reg_rdata = cnt_a;
        8'h13: reg_rdata = cnt_b;
        default: reg_rdata = 32'hDEADBEEF;
        endcase
    end

    // ---- démultiplexage (rôle du NEO-PCM2) : front montant = partie basse,
    //      front descendant = partie haute ----
    reg [9:0]  ra_lo = 0, ra_hi = 0;
    reg [11:0] pa_lo = 0, pa_hi = 0;
    always @(posedge rmpx) ra_lo <= {ra_l, rad_i};
    always @(negedge rmpx) ra_hi <= {ra_l, rad_i};
    always @(posedge pmpx) pa_lo <= {pa, pad_i};
    always @(negedge pmpx) pa_hi <= {pa, pad_i};
    wire [23:0] adpcm_a_addr = {ra_u, ra_hi, ra_lo};
    wire [23:0] adpcm_b_addr = {pa_hi, pa_lo};

    // adresses SDRAM précalculées en continu (les adresses sont verrouillées
    // bien avant /SDROE et /SDPOE) : l'addition reste hors du chemin critique
    reg  [24:0] va_r, vb_r, va_m, vb_m;
    always @(posedge clk) begin
        va_m <= {1'b0, adpcm_a_addr} & v1_mask;
        vb_m <= {1'b0, adpcm_b_addr} & v2_mask;
        va_r <= v1_base + va_m;
        vb_r <= v2_base + vb_m;
    end

    wire [1:0] voe_s;
    sync2 #(.W(2), .INIT(2'b11)) u_svoe (.clk(clk), .d({poe_n, roe_n}), .q(voe_s));
    reg  [1:0] voe_d = 2'b11;
    always @(posedge clk) voe_d <= voe_s;
    wire a_ev = ~voe_s[0] & voe_d[0];
    wire b_ev = ~voe_s[1] & voe_d[1];

    reg  [7:0] rad_dout = 8'h00, pad_dout = 8'h00;
    reg        a_pend = 1'b0, b_pend = 1'b0;

    wire        pk_valid;  wire [23:0] pk_addr; wire [15:0] pk_data; wire [1:0] pk_mask;
    reg         pk_take;
    wr_packer #(.AW(24)) u_pack (
        .clk(clk), .rst(rst),
        .in_stb(mem_wr && mem_space == 8'd0 && !game_mode), .in_addr(mem_addr), .in_data(mem_wdata),
        .flush(xfer_end),
        .out_valid(pk_valid), .out_addr(pk_addr), .out_data(pk_data), .out_mask(pk_mask),
        .out_take(pk_take), .empty(pk_empty), .overflow(pk_ovf));

    reg         sq_req = 1'b0, sq_we = 1'b0;
    reg  [23:0] sq_addr;
    reg  [15:0] sq_wdata;
    reg  [1:0]  sq_wmask;
    reg  [2:0]  op = 3'd0;    // 0 libre, 1 lecture A, 2 lecture B, 3 écriture, 4 diag
    reg         lane;
    wire        sq_ack, sq_rvalid;
    wire [1:0]  sq_ridx;
    wire [15:0] sq_rdata;

    always @(posedge clk) begin
        pk_take <= 1'b0;
        if (a_ev) a_pend <= 1'b1;
        if (b_ev) b_pend <= 1'b1;
        if (reg_wr && reg_addr == 8'h10) begin dbg_req <= 1'b1; dbg_busy <= 1'b1; end
        if (rst) begin
            op <= 3'd0; sq_req <= 1'b0; a_pend <= 1'b0; b_pend <= 1'b0; dbg_req <= 1'b0; dbg_busy <= 1'b0;
        end else case (op)
        3'd0: begin
            if (game_mode && (a_pend || a_ev)) begin
                a_pend <= 1'b0;
                cnt_a  <= cnt_a + 1;
                lane <= va_r[0];
                sq_req <= 1'b1; sq_we <= 1'b0; sq_addr <= va_r[24:1]; op <= 3'd1;
            end else if (game_mode && (b_pend || b_ev)) begin
                b_pend <= 1'b0;
                cnt_b  <= cnt_b + 1;
                lane <= vb_r[0];
                sq_req <= 1'b1; sq_we <= 1'b0; sq_addr <= vb_r[24:1]; op <= 3'd2;
            end else if (!game_mode && pk_valid) begin
                sq_req <= 1'b1; sq_we <= 1'b1; sq_addr <= pk_addr;
                sq_wdata <= pk_data; sq_wmask <= pk_mask; pk_take <= 1'b1; op <= 3'd3;
            end else if (!game_mode && dbg_req) begin
                dbg_req <= 1'b0;
                sq_req <= 1'b1; sq_we <= 1'b0; sq_addr <= dbg_addr[23:0]; op <= 3'd4;
            end
            if (!game_mode) begin a_pend <= 1'b0; b_pend <= 1'b0; end
        end
        3'd1, 3'd2, 3'd4: begin
            if (sq_ack) sq_req <= 1'b0;
            if (sq_rvalid) begin
                if (op == 3'd1) rad_dout <= lane ? sq_rdata[15:8] : sq_rdata[7:0];
                if (op == 3'd2) pad_dout <= lane ? sq_rdata[15:8] : sq_rdata[7:0];
                if (op == 3'd4) begin dbg_data <= {16'd0, sq_rdata}; dbg_busy <= 1'b0; end
                op <= 3'd0;
            end
        end
        3'd3: if (sq_ack) begin sq_req <= 1'b0; op <= 3'd0; end
        default: op <= 3'd0;
        endcase
    end

    sdram #(.COLW(9), .INIT_WAIT(SDRAM_INIT_WAIT), .REFI(SDRAM_REFI)) u_sdram (
        .clk(clk), .rst(rst),
        .req(sq_req), .we(sq_we), .addr(sq_addr), .nrd(2'd0), .col2(9'd0), .addr2(24'd0),
        .wdata(sq_wdata), .wmask(sq_wmask), .ack(sq_ack),
        .rvalid(sq_rvalid), .ridx(sq_ridx), .rdata(sq_rdata),
        .refresh_hold(1'b0), .init_done(sd_init_done), .idle(sd_idle),
        .sd_cke(sd_cke), .sd_cs_n(sd_cs_n), .sd_ras_n(sd_ras_n), .sd_cas_n(sd_cas_n), .sd_we_n(sd_we_n),
        .sd_ba(sd_ba), .sd_a(sd_a), .sd_dqm(sd_dqm), .sd_dq_o(sd_dq_o), .sd_dq_oe(sd_dq_oe), .sd_dq_i(sd_dq_i));

    assign rad_o     = rad_dout;
    assign pad_o     = pad_dout;
    assign rad_drive = ~roe_n;
    assign pad_drive = ~poe_n;
    reg led_r = 1'b0;
    always @(posedge clk) led_r <= game_mode ^ ~pk_empty;
    assign led = led_r;
endmodule
