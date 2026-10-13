// -----------------------------------------------------------------------------
// Contrôleur SDRAM SDR x16 minimal, un seul client, précharge automatique.
//
// - Adresse en mots de 16 bits : {ligne[ROWW-1:0], banque[1:0], colonne[COLW-1:0]}.
// - Pas de page ouverte : chaque accès = ACT + RD/WR avec auto-précharge.
//   Latence déterministe.
// - Lectures multiples dans la même ligne (nrd) :
//     nrd = 0 : 1 lecture  (colonne c)
//     nrd = 1 : 2 lectures (c, col2)
//     nrd = 2 : 4 lectures (c, c+1, col2, col2+1)  -> deux mots de 32 bits
//     nrd = 3 : 2 lectures dans deux BANCS différents (addr puis addr2),
//               les deux activations se recouvrent (lecture anticipée P1/P2)
//   Chaque donnée sort avec rvalid et son rang ridx (0..3).
//   Hypothèse de timing pour nrd = 3 : T_RCD = 2 et tRRD <= 2 cycles.
// - refresh_hold : le client peut retarder le rafraîchissement pendant les
//   fenêtres critiques ; il redevient prioritaire s'il est trop en retard.
//
// Paramètres par défaut : W9825G6KH-6 / AS4C32M16SB-6 à 100 MHz, CL2.
// -----------------------------------------------------------------------------
module sdram #(
    parameter ROWW      = 13,
    parameter COLW      = 9,       // 9 : 256 Mbit ; 10 : 512 Mbit
    parameter AW        = ROWW + 2 + COLW,
    parameter T_RCD     = 2,       // >= 2
    parameter T_RC      = 7,       // tRC 60 ns
    parameter T_RP      = 2,
    parameter T_MRD     = 2,
    parameter CL        = 2,
    // Horloge SDRAM = horloge système inversée. La donnée lue est capturée
    // sur le front DESCENDANT de clk, au centre de sa fenêtre de validité.
    // RD_LAT = cycles entre READ et prise en compte (dépend de la carte).
    parameter RD_LAT    = CL,
    parameter REFI      = 780,     // 7,8 us à 100 MHz
    parameter INIT_WAIT = 20000    // 200 us à 100 MHz
) (
    input  wire              clk,
    input  wire              rst,

    input  wire              req,       // maintenu jusqu'à ack
    input  wire              we,
    input  wire [AW-1:0]     addr,
    input  wire [1:0]        nrd,
    input  wire [COLW-1:0]   col2,
    input  wire [AW-1:0]     addr2,     // nrd = 3 : autre banque
    input  wire [15:0]       wdata,
    input  wire [1:0]        wmask,     // 1 = octet écrit
    output reg               ack,
    output reg               rvalid,
    output reg  [1:0]        ridx,
    output reg  [15:0]       rdata,
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
    output reg  [1:0]        sd_dqm,
    output reg  [15:0]       sd_dq_o,
    output reg               sd_dq_oe,
    input  wire [15:0]       sd_dq_i
);
    localparam [3:0] C_NOP = 4'b0111, C_ACT = 4'b0011, C_RD = 4'b0101,
                     C_WR = 4'b0100, C_PRE = 4'b0010, C_REF = 4'b0001,
                     C_MRS = 4'b0000;

    localparam S_INIT = 4'd0, S_PREA = 4'd1, S_IREF = 4'd2, S_MRS = 4'd3,
               S_IDLE = 4'd4, S_ACT = 4'd5, S_RW = 4'd6, S_RDN = 4'd7,
               S_WAIT = 4'd8, S_A2N = 4'd9, S_A2 = 4'd10;

    reg [3:0]  state = S_INIT;
    reg [15:0] tmr = INIT_WAIT;
    reg [3:0]  iref = 4'd0;
    reg [15:0] ref_cnt = 16'd0;
    reg [2:0]  ref_due = 3'd0;
    reg        ref_take;

    reg            r_we;
    reg [1:0]      r_nrd;
    reg [AW-1:0]   r_addr;
    reg [COLW-1:0] r_col2;
    reg [AW-1:0]   r_addr2;
    reg [15:0]     r_wdata;
    reg [1:0]      r_wmask;
    reg [1:0]      rd_i;          // rang de la prochaine lecture

    reg [15:0]     dq_in;
    reg [RD_LAT:0] pv = 0;
    reg [1:0]      pi [0:RD_LAT];
    integer        k;

    wire [COLW-1:0] a_col  = r_addr[COLW-1:0];
    wire [1:0]      a_bank = r_addr[COLW+1:COLW];

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

    // colonne de la lecture de rang i
    function [COLW-1:0] col_of(input [1:0] i);
        case (r_nrd)
        2'd1:    col_of = i[0] ? r_col2 : a_col;
        2'd2:    col_of = (i[1] ? r_col2 : a_col) | {{COLW-1{1'b0}}, i[0]};
        2'd3:    col_of = i[0] ? r_addr2[COLW-1:0] : a_col;
        default: col_of = a_col;
        endcase
    endfunction

    function [1:0] bank_of(input [1:0] i);
        bank_of = (r_nrd == 2'd3 && i[0]) ? r_addr2[COLW+1:COLW] : a_bank;
    endfunction

    // dernier rang : 0, 1 ou 3
    wire [1:0] last_i = (r_nrd == 2'd2) ? 2'd3 : (r_nrd != 2'd0) ? 2'd1 : 2'd0;
    // attente après la dernière commande pour respecter tRC et tRP
    wire [15:0] wait_after = (T_RC - T_RCD - 1 - last_i > T_RP + 1)
                           ? (T_RC - T_RCD - 1 - last_i) : (T_RP + 1);

    // décision de rafraîchissement registrée (hors chemin critique) ; une
    // requête du client passe avant un rafraîchissement non urgent
    reg want_ref = 1'b0, ref_urgent = 1'b0;
    always @(posedge clk) begin
        want_ref   <= (ref_due != 3'd0) && (!refresh_hold || ref_due >= 3'd4);
        ref_urgent <= (ref_due >= 3'd4);
    end

    always @(negedge clk) dq_in <= sd_dq_i;

    always @(posedge clk) begin
        pv <= {pv[RD_LAT-1:0], 1'b0};
        for (k = RD_LAT; k > 0; k = k - 1) pi[k] <= pi[k-1];
        rvalid <= 1'b0;
        if (pv[RD_LAT]) begin rdata <= dq_in; ridx <= pi[RD_LAT]; rvalid <= 1'b1; end

        ack      <= 1'b0;
        ref_take = 1'b0;
        cmd(C_NOP);
        sd_dq_oe <= 1'b0;
        sd_dqm   <= 2'b00;

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
                    sd_a  <= 13'h0400;      // toutes les banques
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
                        sd_a  <= {6'b000000, CL[2:0], 4'b0000};   // BL=1, CL
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
                if (want_ref && (!req || ref_urgent)) begin
                    cmd(C_REF);
                    ref_take = 1'b1;
                    tmr   <= T_RC - 1;
                    state <= S_WAIT;
                end else if (req) begin
                    ack     <= 1'b1;
                    r_we    <= we;
                    r_nrd   <= we ? 2'd0 : nrd;
                    r_addr  <= addr;
                    r_col2  <= col2;
                    r_addr2 <= addr2;
                    r_wdata <= wdata;
                    r_wmask <= wmask;
                    rd_i    <= 2'd0;
                    cmd(C_ACT);
                    sd_ba <= addr[COLW+1:COLW];
                    sd_a  <= addr[AW-1:COLW+2];
                    tmr   <= T_RCD - 2;
                    state <= (!we && nrd == 2'd3) ? S_A2N : S_ACT;
                end
            end
            S_ACT: begin
                if (tmr == 0) state <= S_RW;
                else          tmr <= tmr - 16'd1;
            end
            S_A2N: state <= S_A2;                 // tRRD
            S_A2: begin
                cmd(C_ACT);
                sd_ba <= r_addr2[COLW+1:COLW];
                sd_a  <= r_addr2[AW-1:COLW+2];
                state <= S_RW;
            end
            S_RW: begin
                sd_ba <= bank_of(2'd0);
                if (r_we) begin
                    cmd(C_WR);
                    sd_a     <= col_a(a_col, 1'b1);
                    sd_dq_o  <= r_wdata;
                    sd_dq_oe <= 1'b1;
                    sd_dqm   <= ~r_wmask;
                    tmr      <= wait_after;
                    state    <= S_WAIT;
                end else begin
                    cmd(C_RD);
                    sd_a  <= col_a(col_of(2'd0), last_i == 2'd0 || r_nrd == 2'd3);
                    pv[0] <= 1'b1;
                    pi[0] <= 2'd0;
                    rd_i  <= 2'd1;
                    tmr   <= wait_after;
                    state <= (last_i == 2'd0) ? S_WAIT : S_RDN;
                end
            end
            S_RDN: begin
                sd_ba <= bank_of(rd_i);
                cmd(C_RD);
                sd_a  <= col_a(col_of(rd_i), rd_i == last_i);
                pv[0] <= 1'b1;
                pi[0] <= rd_i;
                rd_i  <= rd_i + 2'd1;
                if (rd_i == last_i) state <= S_WAIT;
            end
            S_WAIT: begin
                if (tmr == 0) state <= S_IDLE;
                else          tmr <= tmr - 16'd1;
            end
            default: state <= S_INIT;
            endcase

            if (ref_cnt == REFI - 1 && !ref_take) begin
                if (ref_due != 3'd7) ref_due <= ref_due + 3'd1;
            end else if (ref_take && !(ref_cnt == REFI - 1)) begin
                ref_due <= ref_due - 3'd1;
            end
        end
    end
endmodule
