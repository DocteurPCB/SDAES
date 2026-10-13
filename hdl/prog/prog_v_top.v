// Top FPGA "V" (carte PROG) - iCE40HX8K-TQ144
module prog_v_top (
    input  wire        CLK25,
    // bus YM2610 (côté 3,3 V des translateurs)
    inout  wire [7:0]  SDRAD,
    input  wire [9:8]  SDRA_L,
    input  wire [23:20] SDRA_U,
    input  wire        SDRMPX, SDROE_N,
    inout  wire [7:0]  SDPAD,
    input  wire [11:8] SDPA,
    input  wire        SDPMPX, SDPOE_N,
    output wire        RAD_DIR, PAD_DIR,
    // liaison RP2350 (bus partagé avec le FPGA P)
    input  wire        LK_SCK, LK_CS_N,
    inout  wire [3:0]  LK_IO,
    input  wire        MODE,
    // SDRAM V (W9825G6KH)
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

    wire [7:0]  rad_o, pad_o;
    wire        rad_drive, pad_drive, sd_dq_oe, lk_oe;
    wire [15:0] sd_dq_o;
    wire [3:0]  lk_o;
    assign SDRAD = rad_drive ? rad_o : 8'hz;
    assign SDPAD = pad_drive ? pad_o : 8'hz;
    assign RAD_DIR = rad_drive;
    assign PAD_DIR = pad_drive;
    assign SD_DQ = sd_dq_oe ? sd_dq_o : 16'hz;
    assign LK_IO = lk_oe    ? lk_o    : 4'hz;

    prog_v_core u_core (
        .clk(clk), .rst(rst),
        .rad_i(SDRAD), .rad_o(rad_o), .rad_drive(rad_drive), .ra_l(SDRA_L), .ra_u(SDRA_U),
        .rmpx(SDRMPX), .roe_n(SDROE_N),
        .pad_i(SDPAD), .pad_o(pad_o), .pad_drive(pad_drive), .pa(SDPA), .pmpx(SDPMPX), .poe_n(SDPOE_N),
        .lk_sck(LK_SCK), .lk_cs_n(LK_CS_N), .lk_io_i(LK_IO), .lk_io_o(lk_o), .lk_io_oe(lk_oe),
        .mode_in(MODE),
        .sd_cke(SD_CKE), .sd_cs_n(SD_CS_N), .sd_ras_n(SD_RAS_N), .sd_cas_n(SD_CAS_N), .sd_we_n(SD_WE_N),
        .sd_ba(SD_BA), .sd_a(SD_A), .sd_dqm(SD_DQM), .sd_dq_o(sd_dq_o), .sd_dq_oe(sd_dq_oe), .sd_dq_i(SD_DQ),
        .led(LED));
endmodule
