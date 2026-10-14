// Top FPGA "P" (carte PROG) - iCE40HX8K-TQ144
module prog_p_top (
    input  wire        CLK25,
    // bus 68000 (côté 3,3 V des translateurs)
    input  wire [19:1] A,
    inout  wire [15:0] D,
    input  wire        ROMOE_N, PORTOEU_N, PORTOEL_N, PORTWEL_N, PORTWEU_N,
    // configuration des cycles d'attente (sorties de la cartouche vers la console)
    output wire        ROMWAIT_N, PWAIT0_N, PWAIT1_N,
    output wire        XLAT_EN_N,     // résistance de tirage à 1 : isolé au démarrage
    output wire        D_DIR,         // 1 : FPGA -> console
    // liaison RP2350 (bus partagé avec le FPGA V, CS séparés)
    input  wire        LK_SCK, LK_CS_N,
    inout  wire [3:0]  LK_IO,
    output wire        LK_IRQ,
    output wire        MODE,          // vers V, C et SM
    // SDRAM P (W9825G6KH)
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

    wire [15:0] d_o, sd_dq_o;
    wire        d_drive, sd_dq_oe, lk_oe;
    wire [3:0]  lk_o;
    assign D     = d_drive  ? d_o     : 16'hz;
    assign SD_DQ = sd_dq_oe ? sd_dq_o : 16'hz;
    assign LK_IO = lk_oe    ? lk_o    : 4'hz;
    assign D_DIR = d_drive;
    assign XLAT_EN_N = rst;
    // Le connecteur AES ne fournit pas /PORTOE combiné : lecture d'un octet
    // ou de l'autre (la cartouche présente toujours le mot entier)
    wire portoe_n = PORTOEU_N & PORTOEL_N;

    prog_p_core #(.MENU_P_HI_INIT("menu_p_hi.hex"), .MENU_P_LO_INIT("menu_p_lo.hex")) u_core (
        .clk(clk), .rst(rst),
        .a(A), .d_i(D), .d_o(d_o), .d_drive(d_drive),
        .romoe_n(ROMOE_N), .portoe_n(portoe_n), .portwel_n(PORTWEL_N), .portweu_n(PORTWEU_N),
        .wait_n({PWAIT1_N, PWAIT0_N, ROMWAIT_N}),
        .lk_sck(LK_SCK), .lk_cs_n(LK_CS_N), .lk_io_i(LK_IO), .lk_io_o(lk_o), .lk_io_oe(lk_oe),
        .lk_irq(LK_IRQ), .mode_out(MODE),
        .sd_cke(SD_CKE), .sd_cs_n(SD_CS_N), .sd_ras_n(SD_RAS_N), .sd_cas_n(SD_CAS_N), .sd_we_n(SD_WE_N),
        .sd_ba(SD_BA), .sd_a(SD_A), .sd_dqm(SD_DQM), .sd_dq_o(sd_dq_o), .sd_dq_oe(sd_dq_oe), .sd_dq_i(SD_DQ),
        .led(LED));
endmodule
