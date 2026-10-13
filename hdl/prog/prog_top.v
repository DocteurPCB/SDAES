// Top FPGA de la carte PROG (Lattice ECP5 LFE5U-25F-6BG256C).
module prog_top (
    input  wire        CLK25,

    // Bus 68000 (côté 3,3 V des translateurs)
    input  wire [19:1] A,
    inout  wire [15:0] D,
    input  wire        ROMOE_N, PORTOE_N, PORTWEL_N, PORTWEU_N,
    // Bus YM2610
    inout  wire [7:0]  SDRAD,
    input  wire [9:8]  SDRA_L,
    input  wire [23:20] SDRA_U,
    input  wire        SDRMPX, SDROE_N,
    inout  wire [7:0]  SDPAD,
    input  wire [11:8] SDPA,
    input  wire        SDPMPX, SDPOE_N,
    // Contrôle des translateurs (résistance de tirage à 1 -> isolés au démarrage)
    output wire        XLAT_EN_N,
    output wire        D_DIR,         // 1 : FPGA -> console
    output wire        RAD_DIR,
    output wire        PAD_DIR,

    // Liaison RP2350
    input  wire        LK_SCK, LK_CS_N,
    inout  wire [3:0]  LK_IO,
    output wire        LK_IRQ,
    output wire        MODE_OUT,

    // SDRAM P
    output wire        PS_CLK, PS_CKE, PS_CS_N, PS_RAS_N, PS_CAS_N, PS_WE_N,
    output wire [1:0]  PS_BA,
    output wire [12:0] PS_A,
    output wire [1:0]  PS_DQM,
    inout  wire [15:0] PS_DQ,
    // SDRAM V
    output wire        VS_CLK, VS_CKE, VS_CS_N, VS_RAS_N, VS_CAS_N, VS_WE_N,
    output wire [1:0]  VS_BA,
    output wire [12:0] VS_A,
    output wire [1:0]  VS_DQM,
    inout  wire [15:0] VS_DQ,

    output wire        LED
);
    wire clk, locked, rst;
    ecp5_pll   u_pll (.clkin(CLK25), .clkout(clk), .locked(locked));
    reset_gen  u_rst (.clk(clk), .locked(locked), .rst(rst));
    sdram_clk_out u_psclk (.clk(clk), .pin(PS_CLK));
    sdram_clk_out u_vsclk (.clk(clk), .pin(VS_CLK));

    wire [15:0] d_o;     wire d_drive;
    wire [7:0]  rad_o, pad_o;
    wire        rad_drive, pad_drive;
    wire [3:0]  lk_o;    wire lk_oe;
    wire [15:0] p_dq_o, v_dq_o;
    wire        p_dq_oe, v_dq_oe;

    // Côté FPGA, les bus bidirectionnels ne sont pilotés que dans le sens
    // FPGA -> console ; le translateur suit DIR.
    assign D     = d_drive   ? d_o   : 16'hz;
    assign SDRAD = rad_drive ? rad_o : 8'hz;
    assign SDPAD = pad_drive ? pad_o : 8'hz;
    assign D_DIR   = d_drive;
    assign RAD_DIR = rad_drive;
    assign PAD_DIR = pad_drive;
    assign XLAT_EN_N = rst;

    assign LK_IO = lk_oe   ? lk_o   : 4'hz;
    assign PS_DQ = p_dq_oe ? p_dq_o : 16'hz;
    assign VS_DQ = v_dq_oe ? v_dq_o : 16'hz;

    prog_core #(
        .MENU_P_HI_INIT("menu_p_hi.hex"),
        .MENU_P_LO_INIT("menu_p_lo.hex")
    ) u_core (
        .clk(clk), .rst(rst),
        .a(A), .d_i(D), .d_o(d_o), .d_drive(d_drive),
        .romoe_n(ROMOE_N), .portoe_n(PORTOE_N), .portwel_n(PORTWEL_N), .portweu_n(PORTWEU_N),
        .rad_i(SDRAD), .rad_o(rad_o), .rad_drive(rad_drive), .ra_l(SDRA_L), .ra_u(SDRA_U),
        .rmpx(SDRMPX), .roe_n(SDROE_N),
        .pad_i(SDPAD), .pad_o(pad_o), .pad_drive(pad_drive), .pa(SDPA), .pmpx(SDPMPX), .poe_n(SDPOE_N),
        .lk_sck(LK_SCK), .lk_cs_n(LK_CS_N), .lk_io_i(LK_IO), .lk_io_o(lk_o), .lk_io_oe(lk_oe),
        .lk_irq(LK_IRQ), .mode_out(MODE_OUT),
        .p_cke(PS_CKE), .p_cs_n(PS_CS_N), .p_ras_n(PS_RAS_N), .p_cas_n(PS_CAS_N), .p_we_n(PS_WE_N),
        .p_ba(PS_BA), .p_sa(PS_A), .p_dqm(PS_DQM), .p_dq_o(p_dq_o), .p_dq_oe(p_dq_oe), .p_dq_i(PS_DQ),
        .v_cke(VS_CKE), .v_cs_n(VS_CS_N), .v_ras_n(VS_RAS_N), .v_cas_n(VS_CAS_N), .v_we_n(VS_WE_N),
        .v_ba(VS_BA), .v_sa(VS_A), .v_dqm(VS_DQM), .v_dq_o(v_dq_o), .v_dq_oe(v_dq_oe), .v_dq_i(VS_DQ),
        .led(LED)
    );
endmodule
