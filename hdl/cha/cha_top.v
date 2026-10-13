// Top FPGA de la carte CHA (Lattice ECP5 LFE5U-25F-6BG256C).
// Noms de broches = noms des signaux de la cartouche (voir
// docs/02-signaux-connecteurs.md et hardware/cha_pins.lpf).
module cha_top (
    input  wire        CLK25,

    // Bus cartouche (côté 3,3 V des translateurs)
    input  wire [23:0] P,
    input  wire        PCK1B, PCK2B, CA4, S2H1, CLK_12M, EVEN, LOAD, H,
    output wire [3:0]  GAD, GBD,
    output wire        DOTA, DOTB,
    output wire [7:0]  FIXD,
    input  wire [15:0] SDA,
    input  wire        SDMRD_N, SDROM_N, SDRD0_N,
    output wire [7:0]  SDD,
    // Contrôle des translateurs (tirés à 1 par résistance tant que le FPGA
    // n'est pas configuré -> cartouche isolée de la console)
    output wire        XLAT_EN_N,     // toutes les entrées + GAD/GBD/DOT/FIXD
    output wire        SDD_OE_N,      // translateur SDD (sortie vers la console)

    // Liaison RP2350
    input  wire        LK_SCK, LK_CS_N,
    inout  wire [3:0]  LK_IO,
    input  wire        MODE_IN,

    // SDRAM (2 x W9825G6KH, commandes partagées)
    output wire        SD_CLK, SD_CKE, SD_CS_N, SD_RAS_N, SD_CAS_N, SD_WE_N,
    output wire [1:0]  SD_BA,
    output wire [12:0] SD_A,
    output wire [3:0]  SD_DQM,
    inout  wire [31:0] SD_DQ,

    // SRAM 1 Mo x 8
    output wire [19:0] SR_A,
    inout  wire [7:0]  SR_D,
    output wire        SR_CE_N, SR_OE_N, SR_WE_N,

    output wire        LED
);
    wire clk, locked, rst;
    ecp5_pll   u_pll (.clkin(CLK25), .clkout(clk), .locked(locked));
    reset_gen  u_rst (.clk(clk), .locked(locked), .rst(rst));
    sdram_clk_out u_sdclk (.clk(clk), .pin(SD_CLK));

    wire [3:0]  lk_o;  wire lk_oe;
    wire [31:0] sd_dq_o; wire sd_dq_oe;
    wire [7:0]  sr_d_o;  wire sr_d_oe;
    wire        sdd_drive;

    assign LK_IO = lk_oe    ? lk_o    : 4'hz;
    assign SD_DQ = sd_dq_oe ? sd_dq_o : 32'hz;
    assign SR_D  = sr_d_oe  ? sr_d_o  : 8'hz;

    assign XLAT_EN_N = rst;
    assign SDD_OE_N  = rst | ~sdd_drive;

    cha_core #(
        .MENU_S_INIT("menu_s.hex"),
        .MENU_M1_INIT("menu_m1.hex")
    ) u_core (
        .clk(clk), .rst(rst),
        .pbus(P), .pck1b(PCK1B), .pck2b(PCK2B), .ca4(CA4), .s2h1(S2H1),
        .clk_12m(CLK_12M), .even(EVEN), .load(LOAD), .h(H),
        .gad(GAD), .gbd(GBD), .dota(DOTA), .dotb(DOTB), .fixd(FIXD),
        .sda(SDA), .sdmrd_n(SDMRD_N), .sdrom_n(SDROM_N), .sdrd0_n(SDRD0_N),
        .sdd_o(SDD), .sdd_drive(sdd_drive),
        .lk_sck(LK_SCK), .lk_cs_n(LK_CS_N), .lk_io_i(LK_IO), .lk_io_o(lk_o), .lk_io_oe(lk_oe),
        .mode_in(MODE_IN),
        .sd_cke(SD_CKE), .sd_cs_n(SD_CS_N), .sd_ras_n(SD_RAS_N), .sd_cas_n(SD_CAS_N), .sd_we_n(SD_WE_N),
        .sd_ba(SD_BA), .sd_a(SD_A), .sd_dqm(SD_DQM), .sd_dq_o(sd_dq_o), .sd_dq_oe(sd_dq_oe), .sd_dq_i(SD_DQ),
        .sr_a(SR_A), .sr_d_o(sr_d_o), .sr_d_oe(sr_d_oe), .sr_d_i(SR_D),
        .sr_ce_n(SR_CE_N), .sr_oe_n(SR_OE_N), .sr_we_n(SR_WE_N),
        .led(LED)
    );
endmodule
