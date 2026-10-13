// -----------------------------------------------------------------------------
// FPGA "SM" de la carte CHA : couche fixe (S) et programme son Z80 (M1).
//
// Remplace la ROM S, la partie "S" du NEO-273 (verrou PCK2B), la ROM M1 et
// les banques Z80 du NEO-ZMC. S et M1 sont dans une SRAM 1 Mo x 8 (10 ns) :
//   S  en 0x00000-0x7FFFF,  M1 en 0x80000-0xFFFFF.
// Le menu (police S et pilote Z80) est en BRAM.
// -----------------------------------------------------------------------------
module cha_sm_core #(
    parameter MENU_S_INIT  = "",
    parameter MENU_M1_INIT = ""
) (
    input  wire        clk,               // 100 MHz
    input  wire        rst,

    input  wire [15:0] pbus,
    input  wire        pck2b,
    input  wire        s2h1,
    output wire [7:0]  fixd,

    input  wire [15:0] sda,
    input  wire        sdmrd_n,
    input  wire        sdrom_n,
    input  wire        sdrd0_n,
    output wire [7:0]  sdd_o,
    output wire        sdd_drive,

    input  wire        lk_sck,
    input  wire        lk_cs_n,
    input  wire [3:0]  lk_io_i,
    output wire [3:0]  lk_io_o,
    output wire        lk_io_oe,
    input  wire        mode_in,

    output wire [19:0] sr_a,
    output wire [7:0]  sr_d_o,
    output wire        sr_d_oe,
    input  wire [7:0]  sr_d_i,
    output wire        sr_ce_n,
    output wire        sr_oe_n,
    output wire        sr_we_n,

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
    reg [18:0] s_mask  = 19'h1FFFF;
    reg [18:0] m1_mask = 19'h1FFFF;
    reg [31:0] dbg_addr = 32'h0, dbg_data = 32'h0;
    reg        dbg_req = 1'b0, dbg_busy = 1'b0;
    reg [31:0] cnt_pck2b = 0, cnt_z80 = 0;

    wire mode_s;
    sync2 u_smode (.clk(clk), .d(mode_in), .q(mode_s));
    reg  game_mode = 1'b0;
    always @(posedge clk) game_mode <= (ctrl_arm & mode_s) | ctrl_force;

    // signaux partagés entre les blocs SRAM / Z80 / diagnostic
    reg         s_req = 1'b0, z_req = 1'b0;
    reg  [19:0] s_sa, z_sa;
    wire        s_ack, z_ack, w_ack;
    wire [7:0]  sram_rdata;
    reg  [1:0]  z_st = 2'd0;
    wire        z_rd_ev;
    reg         dbg_act = 1'b0;
    wire        sw_empty;
    reg         sw_ovf = 1'b0;
    wire dbg_start = dbg_req && !game_mode && !dbg_act && z_st == 2'd0 && !z_rd_ev;
    wire dbg_done  = dbg_act && z_ack;

    always @(posedge clk) begin
        if (rst) begin
            ctrl_arm <= 1'b0; ctrl_force <= 1'b0;
        end else if (reg_wr) begin
            case (reg_addr)
            8'h01: begin ctrl_arm <= reg_wdata[0]; ctrl_force <= reg_wdata[1]; end
            8'h04: s_mask   <= reg_wdata[18:0];
            8'h05: m1_mask  <= reg_wdata[18:0];
            8'h10: dbg_addr <= reg_wdata;
            default: ;
            endcase
        end
        if (reg_wr && reg_addr == 8'h10) begin dbg_req <= 1'b1; dbg_busy <= 1'b1; end
        if (dbg_start) dbg_req <= 1'b0;
        if (dbg_done) begin dbg_data <= {24'd0, sram_rdata}; dbg_busy <= 1'b0; end
        if (rst) begin dbg_req <= 1'b0; dbg_busy <= 1'b0; end
    end

    always @* begin
        case (reg_addr)
        8'h00: reg_rdata = 32'h4E475332;   // "NGS2"
        8'h01: reg_rdata = {30'd0, ctrl_force, ctrl_arm};
        8'h02: reg_rdata = {26'd0, dbg_busy, sw_ovf, mode_s, game_mode, sw_empty, 1'b1};
        8'h04: reg_rdata = {13'd0, s_mask};
        8'h05: reg_rdata = {13'd0, m1_mask};
        8'h10: reg_rdata = dbg_addr;
        8'h11: reg_rdata = dbg_data;
        8'h12: reg_rdata = cnt_pck2b;
        8'h13: reg_rdata = cnt_z80;
        default: reg_rdata = 32'hDEADBEEF;
        endcase
    end

    // =========================================================================
    // CARTOGRAPHIE (à valider sur matériel)
    // =========================================================================
    reg [15:0] s_latch = 16'h0;
    always @(posedge pck2b) s_latch <= pbus;

    // Octet S : {tuile[11:0], P3, 2H1, ligne[2:0]} (17 bits, 128 Ko)
    function [16:0] s_byte_addr(input [15:0] p, input h1);
        s_byte_addr = {p[15:4], p[3], h1, p[2:0]};
    endfunction

    // =========================================================================
    // BRAM du menu
    // =========================================================================
    reg  [12:0] ms_b_addr;
    reg  [10:0] mm_b_addr;
    wire [7:0]  ms_b_rd, mm_b_rd;
    bram_dp #(.DW(8), .AW(13), .INIT(MENU_S_INIT)) u_menu_s (
        .clk(clk), .a_we(mem_wr && mem_space == 8'd2), .a_addr(mem_addr[12:0]), .a_wdata(mem_wdata),
        .b_addr(ms_b_addr), .b_rdata(ms_b_rd));
    bram_dp #(.DW(8), .AW(11), .INIT(MENU_M1_INIT)) u_menu_m1 (
        .clk(clk), .a_we(mem_wr && mem_space == 8'd3), .a_addr(mem_addr[10:0]), .a_wdata(mem_wdata),
        .b_addr(mm_b_addr), .b_rdata(mm_b_rd));

    // =========================================================================
    // SRAM partagée : fixe (prioritaire), Z80 / diagnostic, chargeur
    // =========================================================================
    // étape de registre puis FIFO de 4 octets (débit de la liaison << SRAM)
    reg         sw_in = 1'b0;
    reg  [27:0] sw_in_d;
    reg  [27:0] sw_fifo [0:3];
    reg  [2:0]  sw_wp = 0, sw_rp = 0, sw_cnt = 0;
    assign sw_empty = (sw_wp == sw_rp) && !sw_in;
    always @(posedge clk) begin
        sw_in   <= mem_wr && mem_space == 8'd0 && !game_mode;
        sw_in_d <= {mem_addr[19:0], mem_wdata};
        if (rst) begin sw_wp <= 0; sw_rp <= 0; sw_cnt <= 0; sw_ovf <= 1'b0; sw_in <= 1'b0; end
        else begin
            if (sw_in) begin
                if (sw_cnt == 3'd4) sw_ovf <= 1'b1;
                else begin
                    sw_fifo[sw_wp[1:0]] <= sw_in_d;
                    sw_wp <= sw_wp + 3'd1;
                end
            end
            if (w_ack) sw_rp <= sw_rp + 3'd1;
            sw_cnt <= sw_cnt + (sw_in && sw_cnt != 3'd4) - w_ack;
        end
    end
    wire [27:0] sw_head = sw_fifo[sw_rp[1:0]];

    sram_ctrl u_sram (
        .clk(clk), .rst(rst),
        .r0_req(s_req), .r0_addr(s_sa), .r0_ack(s_ack),
        .r1_req(z_req | dbg_act), .r1_addr(dbg_act ? dbg_addr[19:0] : z_sa), .r1_ack(z_ack),
        .rdata(sram_rdata),
        .w_req(sw_wp != sw_rp && !game_mode), .w_addr(sw_head[27:8]), .w_data(sw_head[7:0]), .w_ack(w_ack),
        .sr_a(sr_a), .sr_d_o(sr_d_o), .sr_d_oe(sr_d_oe), .sr_d_i(sr_d_i),
        .sr_ce_n(sr_ce_n), .sr_oe_n(sr_oe_n), .sr_we_n(sr_we_n)
    );

    // =========================================================================
    // ROM S : 2 octets lus par verrou PCK2B (2H1 = 0 puis 1)
    // =========================================================================
    wire pck_s;
    sync2 #(.INIT(1'b1)) u_spck (.clk(clk), .d(pck2b), .q(pck_s));
    reg  pck_d = 1'b1;
    always @(posedge clk) pck_d <= pck_s;
    wire pck2_ev = pck_s & ~pck_d;

    reg [7:0]  fix0 = 8'h00, fix1 = 8'h00;
    reg [2:0]  s_st = 3'd0;
    reg        s_pend = 1'b0;
    reg [15:0] s_lat_q;
    reg [16:0] s_ba;

    always @(posedge clk) begin
        if (pck2_ev) begin s_pend <= 1'b1; cnt_pck2b <= cnt_pck2b + 1; end
        if (rst) begin s_st <= 3'd0; s_req <= 1'b0; s_pend <= 1'b0; end
        else case (s_st)
        3'd0: if (s_pend || pck2_ev) begin
                  s_pend  <= 1'b0;
                  s_lat_q <= s_latch;
                  s_st    <= game_mode ? 3'd1 : 3'd4;
                  s_ba     = s_byte_addr(s_latch, 1'b0);
                  s_sa    <= {3'b000, s_ba} & {1'b0, s_mask};
                  s_req   <= game_mode;
                  ms_b_addr <= s_ba[12:0];
              end
        3'd1: if (s_ack) begin
                  fix0  <= sram_rdata;
                  s_ba   = s_byte_addr(s_lat_q, 1'b1);
                  s_sa  <= {3'b000, s_ba} & {1'b0, s_mask};
                  s_st  <= 3'd2;
              end
        3'd2: s_st <= 3'd3;
        3'd3: if (s_ack) begin fix1 <= sram_rdata; s_req <= 1'b0; s_st <= 3'd0; end
        3'd4: begin s_ba = s_byte_addr(s_lat_q, 1'b1); ms_b_addr <= s_ba[12:0]; s_st <= 3'd5; end
        3'd5: begin fix0 <= ms_b_rd; s_st <= 3'd6; end
        3'd6: begin fix1 <= ms_b_rd; s_st <= 3'd0; end
        default: s_st <= 3'd0;
        endcase
    end
    assign fixd = s2h1 ? fix1 : fix0;

    // =========================================================================
    // ROM M1 (Z80) + banques NEO-ZMC
    // =========================================================================
    wire [15:0] sda_s;
    wire [2:0]  zc_s;   // {sdrd0_n, sdrom_n, sdmrd_n}
    sync2 #(.W(16)) u_sync_sda (.clk(clk), .d(sda), .q(sda_s));
    sync2 #(.W(3), .INIT(3'b111)) u_sync_zc (.clk(clk), .d({sdrd0_n, sdrom_n, sdmrd_n}), .q(zc_s));
    reg [2:0] zc_d = 3'b111;
    always @(posedge clk) zc_d <= zc_s;
    assign z_rd_ev = (~zc_s[0] & ~zc_s[1]) & ~(~zc_d[0] & ~zc_d[1]);
    wire bank_ev   = ~zc_s[2] & zc_d[2];

    reg [7:0] bank0 = 8'h1E;   // fenêtre F000-F7FF (2 Ko)
    reg [6:0] bank1 = 7'h0E;   // fenêtre E000-EFFF (4 Ko)
    reg [5:0] bank2 = 6'h06;   // fenêtre C000-DFFF (8 Ko)
    reg [4:0] bank3 = 5'h02;   // fenêtre 8000-BFFF (16 Ko)

    function [18:0] m1_addr(input [15:0] a);
        if (!a[15])      m1_addr = {4'b0000, a[14:0]};
        else if (!a[14]) m1_addr = {bank3, a[13:0]};
        else if (!a[13]) m1_addr = {bank2, a[12:0]};
        else if (!a[12]) m1_addr = {bank1, a[11:0]};
        else             m1_addr = {bank0, a[10:0]};
    endfunction

    reg [7:0]  z_dout = 8'hFF;
    reg [18:0] z_ma;
    always @(posedge clk) begin
        if (bank_ev) begin
            case (sda_s[1:0])
            // numéro de banque = registre B du Z80 (A15-A8) lors d'un IN (C)
            2'd0: bank0 <= sda_s[15:8];
            2'd1: bank1 <= sda_s[14:8];
            2'd2: bank2 <= sda_s[13:8];
            2'd3: bank3 <= sda_s[12:8];
            endcase
        end
        if (rst) begin z_st <= 2'd0; z_req <= 1'b0; dbg_act <= 1'b0; end
        else case (z_st)
        2'd0: if (z_rd_ev) begin
                  cnt_z80 <= cnt_z80 + 1;
                  z_ma = m1_addr(sda_s);
                  if (game_mode) begin
                      z_sa  <= {1'b1, z_ma & m1_mask};
                      z_req <= 1'b1;
                      z_st  <= 2'd1;
                  end else begin
                      mm_b_addr <= z_ma[10:0];
                      z_st <= 2'd2;
                  end
              end else if (dbg_start) begin
                  dbg_act <= 1'b1;
                  z_st <= 2'd1;
              end
        2'd1: if (z_ack) begin
                  if (dbg_act) dbg_act <= 1'b0;
                  else z_dout <= sram_rdata;
                  z_req <= 1'b0;
                  z_st <= 2'd0;
              end
        2'd2: z_st <= 2'd3;
        2'd3: begin z_dout <= mm_b_rd; z_st <= 2'd0; end
        endcase
    end
    assign sdd_o     = z_dout;
    assign sdd_drive = ~sdmrd_n & ~sdrom_n;    // combinatoire depuis les broches

    reg led_r = 1'b0;
    always @(posedge clk) led_r <= game_mode ^ ~sw_empty;
    assign led = led_r;
endmodule
