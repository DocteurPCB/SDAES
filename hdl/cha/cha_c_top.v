// Top FPGA "C" (carte CHA) - iCE40HX8K-TQ144
module cha_c_top (
    input  wire        CLK25,
    // bus cartouche (côté 3,3 V des translateurs)
    input  wire [23:0] P,
    input  wire        PCK1B, CA4, CLK_12M, EVEN, LOAD, H,
    output wire [3:0]  GAD, GBD,
    output wire        DOTA, DOTB,
    output wire        XLAT_EN_N,     // translateurs du connecteur CHA (avec SM)
    // liaison RP2350 (bus partagé avec le FPGA SM)
    input  wire        LK_SCK, LK_CS_N,
    inout  wire [3:0]  LK_IO,
    input  wire        MODE,
    // SDRAM C (AS4C32M16SB, 512 Mbit)
    output wire        SD_CLK, SD_CKE, SD_CS_N, SD_RAS_N, SD_CAS_N, SD_WE_N,
    output wire [1:0]  SD_BA,
    output wire [12:0] SD_A,
    output wire [1:0]  SD_DQM,
    inout  wire [15:0] SD_DQ,
    output wire        LED
);
    wire clk, locked, rst;
    sys_pll       u_pll (.clkin(CLK25), .clkout(clk), .locked(locked));
    reset_gen     u_rst (.clk(clk), .locked(locked), .rst(rst));
    sdram_clk_out u_sdc (.clk(clk), .pin(SD_CLK));

    wire [15:0] sd_dq_o;
    wire        sd_dq_oe, lk_oe;
    wire [3:0]  lk_o;
    assign SD_DQ = sd_dq_oe ? sd_dq_o : 16'hz;
    assign LK_IO = lk_oe    ? lk_o    : 4'hz;
    assign XLAT_EN_N = rst;

    cha_c_core u_core (
        .clk(clk), .rst(rst),
        .pbus(P), .pck1b(PCK1B), .ca4(CA4), .clk_12m(CLK_12M), .even(EVEN), .load(LOAD), .h(H),
        .gad(GAD), .gbd(GBD), .dota(DOTA), .dotb(DOTB),
        .lk_sck(LK_SCK), .lk_cs_n(LK_CS_N), .lk_io_i(LK_IO), .lk_io_o(lk_o), .lk_io_oe(lk_oe),
        .mode_in(MODE),
        .sd_cke(SD_CKE), .sd_cs_n(SD_CS_N), .sd_ras_n(SD_RAS_N), .sd_cas_n(SD_CAS_N), .sd_we_n(SD_WE_N),
        .sd_ba(SD_BA), .sd_a(SD_A), .sd_dqm(SD_DQM), .sd_dq_o(sd_dq_o), .sd_dq_oe(sd_dq_oe), .sd_dq_i(SD_DQ),
        .led(LED));
endmodule
