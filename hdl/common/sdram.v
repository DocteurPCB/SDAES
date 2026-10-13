// -----------------------------------------------------------------------------
// Contrôleur SDRAM SDR minimal, un seul client, précharge automatique.
//
// - Largeur DW = 16 (une puce x16) ou 32 (deux puces x16 en parallèle,
//   commandes/adresses partagées).
// - Adresse en mots : {ligne[ROWW-1:0], banque[1:0], colonne[COLW-1:0]}.
// - Pas de page ouverte : chaque accès = ACT + RD/WR avec auto-précharge.
//   Latence déterministe, pas de gestion de bancs ouverts.
// - Option "dual" : deux lectures dans la même ligne (colonne addr et col2),
//   utilisée pour récupérer les deux moitiés d'une ligne de tuile C en un
//   seul cycle d'activation.
// - refresh_hold : le client peut retarder le rafraîchissement pendant les
//   fenêtres critiques ; il devient prioritaire s'il est trop en retard.
//
// Paramètres par défaut : W9825G6KH-6 à 133 MHz, CL3.
// -----------------------------------------------------------------------------
module sdram #(
    parameter DW        = 16,
    parameter ROWW      = 13,
    parameter COLW      = 9,
    parameter AW        = ROWW + 2 + COLW,
    parameter T_RCD     = 2,
    parameter T_RC      = 9,      // >= tRC (60 ns) et >= tRAS + tRP
    parameter T_RP      = 2,
    parameter T_MRD     = 2,
    parameter CL        = 3,
    // Horloge SDRAM = horloge système inversée (front montant SDRAM au milieu
    // du cycle). La donnée lue (tAC 5,4 ns, tOH 2,7 ns) est capturée sur le
    // front DESCENDANT de clk, au centre de sa fenêtre de validité, puis
    // utilisée au front montant suivant. RD_LAT = cycles entre READ et prise
    // en compte ; à ajuster avec la phase réelle de la carte.
    parameter RD_LAT    = CL,
    parameter REFI      = 1000,   // 7,8 us à 133 MHz
    parameter INIT_WAIT = 27000   // >= 200 us à 133 MHz
) (
    input  wire              clk,
    input  wire              rst,

    input  wire              req,       // maintenu jusqu'à ack
    input  wire              we,
    input  wire [AW-1:0]     addr,
    input  wire              dual,      // lecture double (même ligne)
    input  wire [COLW-1:0]   col2,
    input  wire [DW-1:0]     wdata,
    input  wire [DW/8-1:0]   wmask,     // 1 = octet écrit
    output reg               ack,
    output reg               rvalid,
    output reg  [DW-1:0]     rdata,
    output reg               rvalid2,
    output reg  [DW-1:0]     rdata2,
    input  wire              refresh_hold,
    output reg               init_done,
    output wire              idle,

    output reg               sd_cke,
    output reg               sd_cs_n,
    output reg               sd_ras_n,
    output reg               sd_cas_n,
    output reg               sd_we_n,
    output reg  [1:0]        sd_ba,
    output reg  [12:0]       sd_a,
    output reg  [DW/8-1:0]   sd_dqm,
    output reg  [DW-1:0]     sd_dq_o,
    output reg               sd_dq_oe,
    input  wire [DW-1:0]     sd_dq_i
);
    // commandes {cs, ras, cas, we}
    localparam [3:0] C_NOP = 4'b0111, C_ACT = 4'b0011, C_RD = 4'b0101,
                     C_WR = 4'b0100, C_PRE = 4'b0010, C_REF = 4'b0001,
                     C_MRS = 4'b0000;

    localparam S_INIT = 4'd0, S_PREA = 4'd1, S_IREF = 4'd2, S_MRS = 4'd3,
               S_IDLE = 4'd4, S_ACT = 4'd5, S_RW = 4'd6, S_RD2 = 4'd7,
               S_WAIT = 4'd8;

    reg [3:0]  state = S_INIT;
    reg [15:0] tmr = INIT_WAIT;
    reg [3:0]  iref = 4'd0;
    reg [15:0] ref_cnt = 16'd0;
    reg [2:0]  ref_due = 3'd0;
    reg        ref_take;

    reg            r_we, r_dual;
    reg [AW-1:0]   r_addr;
    reg [COLW-1:0] r_col2;
    reg [DW-1:0]   r_wdata;
    reg [DW/8-1:0] r_wmask;

    reg [DW-1:0]     dq_in;
    reg [RD_LAT:0]   p1 = 0, p2 = 0;

    wire [COLW-1:0] a_col  = r_addr[COLW-1:0];
    wire [1:0]      a_bank = r_addr[COLW+1:COLW];
    wire [ROWW-1:0] a_row  = r_addr[AW-1:COLW+2];

    assign idle = (state == S_IDLE) && !req;

    task cmd(input [3:0] c);
        {sd_cs_n, sd_ras_n, sd_cas_n, sd_we_n} <= c;
    endtask

    // colonne sur A[COLW-1:0], A10 = auto-précharge
    function [12:0] col_a(input [COLW-1:0] c, input ap);
        begin
            col_a = 13'd0;
            col_a[COLW-1:0] = c;
            col_a[10] = ap;
        end
    endfunction

    wire want_ref = (ref_due != 3'd0) && (!refresh_hold || ref_due >= 3'd4);

    always @(negedge clk) dq_in <= sd_dq_i;

    always @(posedge clk) begin
        p1 <= {p1[RD_LAT-1:0], 1'b0};
        p2 <= {p2[RD_LAT-1:0], 1'b0};
        rvalid  <= 1'b0;
        rvalid2 <= 1'b0;
        if (p1[RD_LAT]) begin rdata  <= dq_in; rvalid  <= 1'b1; end
        if (p2[RD_LAT]) begin rdata2 <= dq_in; rvalid2 <= 1'b1; end

        ack      <= 1'b0;
        ref_take = 1'b0;
        cmd(C_NOP);
        sd_dq_oe <= 1'b0;
        sd_dqm   <= {DW/8{1'b0}};

        if (state != S_INIT && state != S_PREA && state != S_IREF && state != S_MRS) begin
            if (ref_cnt >= REFI - 1) ref_cnt <= 16'd0;
            else                     ref_cnt <= ref_cnt + 16'd1;
        end

        if (rst) begin
            state     <= S_INIT;
            tmr       <= INIT_WAIT;
            init_done <= 1'b0;
            sd_cke    <= 1'b0;
            ref_due   <= 3'd0;
            ref_cnt   <= 16'd0;
        end else begin
            case (state)
            S_INIT: begin
                sd_cke <= 1'b1;
                if (tmr == 0) begin
                    cmd(C_PRE);
                    sd_a  <= 13'h0400;      // A10 = toutes les banques
                    tmr   <= T_RP;
                    state <= S_PREA;
                end else tmr <= tmr - 16'd1;
            end
            S_PREA: begin
                if (tmr == 0) begin
                    cmd(C_REF);
                    tmr   <= T_RC;
                    iref  <= 4'd7;
                    state <= S_IREF;
                end else tmr <= tmr - 16'd1;
            end
            S_IREF: begin
                if (tmr == 0) begin
                    if (iref == 0) begin
                        cmd(C_MRS);
                        sd_ba <= 2'b00;
                        // BL=1, séquentiel, CL, écriture en mode burst (=1)
                        sd_a  <= {6'b000000, CL[2:0], 4'b0000};
                        tmr   <= T_MRD;
                        state <= S_MRS;
                    end else begin
                        cmd(C_REF);
                        iref <= iref - 4'd1;
                        tmr  <= T_RC;
                    end
                end else tmr <= tmr - 16'd1;
            end
            S_MRS: begin
                if (tmr == 0) begin
                    init_done <= 1'b1;
                    state     <= S_IDLE;
                end else tmr <= tmr - 16'd1;
            end
            S_IDLE: begin
                if (want_ref) begin
                    cmd(C_REF);
                    ref_take = 1'b1;
                    tmr   <= T_RC - 1;
                    state <= S_WAIT;
                end else if (req) begin
                    ack     <= 1'b1;
                    r_we    <= we;
                    r_dual  <= dual & ~we;
                    r_addr  <= addr;
                    r_col2  <= col2;
                    r_wdata <= wdata;
                    r_wmask <= wmask;
                    cmd(C_ACT);
                    sd_ba <= addr[COLW+1:COLW];
                    sd_a  <= addr[AW-1:COLW+2];
                    tmr   <= T_RCD - 2;     // T_RCD >= 2
                    state <= S_ACT;
                end
            end
            S_ACT: begin
                if (tmr == 0) state <= S_RW;
                else          tmr <= tmr - 16'd1;
            end
            S_RW: begin
                sd_ba <= a_bank;
                if (r_we) begin
                    cmd(C_WR);
                    sd_a     <= col_a(a_col, 1'b1);
                    sd_dq_o  <= r_wdata;
                    sd_dq_oe <= 1'b1;
                    sd_dqm   <= ~r_wmask;
                    tmr      <= T_RC - T_RCD - 1;
                    state    <= S_WAIT;
                end else begin
                    cmd(C_RD);
                    sd_a <= col_a(a_col, ~r_dual);
                    p1[0] <= 1'b1;
                    if (r_dual) begin
                        state <= S_RD2;
                    end else begin
                        tmr   <= T_RC - T_RCD - 1;
                        state <= S_WAIT;
                    end
                end
            end
            S_RD2: begin
                cmd(C_RD);
                sd_a  <= col_a(r_col2, 1'b1);
                p2[0] <= 1'b1;
                tmr   <= T_RC - T_RCD - 1;
                state <= S_WAIT;
            end
            S_WAIT: begin
                if (tmr == 0) state <= S_IDLE;
                else          tmr <= tmr - 16'd1;
            end
            default: state <= S_INIT;
            endcase

            // compteur de rafraîchissements en attente
            if (ref_cnt == REFI - 1 && !ref_take) begin
                if (ref_due != 3'd7) ref_due <= ref_due + 3'd1;
            end else if (ref_take && !(ref_cnt == REFI - 1)) begin
                ref_due <= ref_due - 3'd1;
            end
        end
    end
endmodule
