// Top FPGA "SM" (carte CHA) - iCE40HX8K-TQ144
module cha_sm_top (
    input  wire        CLK25,
    // bus cartouche (côté 3,3 V des translateurs)
    input  wire [15:0] P,
    input  wire        PCK2B, S2H1,
    output wire [7:0]  FIXD,
    input  wire [15:0] SDA,
    input  wire        SDMRD_N, SDROM_N, SDRD0_N,
    output wire [7:0]  SDD,
    output wire        SDD_OE_N,      // translateur SDD (sortie vers la console)
    // liaison RP2350 (bus partagé avec le FPGA C)
    input  wire        LK_SCK, LK_CS_N,
    inout  wire [3:0]  LK_IO,
    input  wire        MODE,
    // SRAM 1 Mo x 8 (IS61WV10248)
    output wire [19:0] SR_A,
    inout  wire [7:0]  SR_D,
    output wire        SR_OE_N, SR_WE_N     // /CE de la SRAM relié à la masse
);                                          // (pas de LED : broches comptées)
    wire clk, locked, rst;
    sys_pll   u_pll (.clkin(CLK25), .clkout(clk), .locked(locked));
    reset_gen u_rst (.clk(clk), .locked(locked), .rst(rst));

    wire [7:0] sr_d_o;
    wire       sr_d_oe, sdd_drive, lk_oe;
    wire [3:0] lk_o;
    assign SR_D  = sr_d_oe ? sr_d_o : 8'hz;
    assign LK_IO = lk_oe   ? lk_o   : 4'hz;
    assign SDD_OE_N = rst | ~sdd_drive;

    cha_sm_core #(.MENU_S_INIT("menu_s.hex"), .MENU_M1_INIT("menu_m1.hex")) u_core (
        .clk(clk), .rst(rst),
        .pbus(P), .pck2b(PCK2B), .s2h1(S2H1), .fixd(FIXD),
        .sda(SDA), .sdmrd_n(SDMRD_N), .sdrom_n(SDROM_N), .sdrd0_n(SDRD0_N),
        .sdd_o(SDD), .sdd_drive(sdd_drive),
        .lk_sck(LK_SCK), .lk_cs_n(LK_CS_N), .lk_io_i(LK_IO), .lk_io_o(lk_o), .lk_io_oe(lk_oe),
        .mode_in(MODE),
        .sr_a(SR_A), .sr_d_o(sr_d_o), .sr_d_oe(sr_d_oe), .sr_d_i(SR_D),
        .sr_ce_n(), .sr_oe_n(SR_OE_N), .sr_we_n(SR_WE_N),
        .led());
endmodule
