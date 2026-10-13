// Modèle comportemental SDRAM SDR x16/x32 (simulation uniquement).
// Mémoire réduite : index = {ligne[RB-1:0], banque, colonne}.
// Vérifie les erreurs de protocole grossières (banque non ouverte, etc.).
`timescale 1ns/1ps
module sdram_model #(
    parameter DW = 16,
    parameter RB = 6,        // bits de ligne conservés
    parameter CL = 3,
    parameter real T_AC = 5.4,   // accès depuis l'horloge (ns)
    parameter real T_OH = 2.7    // maintien de la donnée (ns)
) (
    input  wire            clk,
    input  wire            cke,
    input  wire            cs_n, ras_n, cas_n, we_n,
    input  wire [1:0]      ba,
    input  wire [12:0]     a,
    input  wire [DW/8-1:0] dqm,
    inout  wire [DW-1:0]   dq
);
    localparam NB = DW / 8;
    reg [DW-1:0] mem [0:(1 << (RB + 2 + 9)) - 1];
    reg [12:0]   open_row [0:3];
    reg [3:0]    is_open = 4'b0;
    reg [DW-1:0] pipe_d [0:CL];
    reg [CL:0]   pipe_v = 0;
    reg          mode_set = 0;
    integer      errors = 0;
    integer      refreshes = 0;
    integer      i;

    initial for (i = 0; i < (1 << (RB + 2 + 9)); i = i + 1) mem[i] = {DW{1'b0}};

    // sortie : l'ancienne donnée disparaît après T_OH, la nouvelle apparaît après T_AC
    reg          dq_valid = 1'b0;
    reg [DW-1:0] dq_val;
    always @(posedge clk) begin
        #(T_OH);
        dq_valid = 1'b0;
        #(T_AC - T_OH);
        dq_valid = pipe_v[CL-1];
        dq_val   = pipe_d[CL-1];
    end
    assign dq = dq_valid ? dq_val : {DW{1'bz}};

    function [RB+10:0] idx(input [1:0] b, input [12:0] row, input [8:0] col);
        idx = {row[RB-1:0], b, col};
    endfunction

    wire [3:0] cmd = {cs_n, ras_n, cas_n, we_n};

    always @(posedge clk) begin
        // pipeline de lecture
        for (i = CL; i > 0; i = i - 1) begin
            pipe_d[i] <= pipe_d[i-1];
            pipe_v[i] <= pipe_v[i-1];
        end
        pipe_v[0] <= 1'b0;

        if (cke) case (cmd)
        4'b0011: begin // ACT
            if (is_open[ba]) begin
                $display("%t SDRAM ERREUR: ACT banque %0d déjà ouverte", $time, ba);
                errors = errors + 1;
            end
            is_open[ba]  <= 1'b1;
            open_row[ba] <= a;
        end
        4'b0101: begin // READ
            if (!is_open[ba]) begin
                $display("%t SDRAM ERREUR: READ banque %0d fermée", $time, ba);
                errors = errors + 1;
            end
            pipe_d[0] <= mem[idx(ba, open_row[ba], a[8:0])];
            pipe_v[0] <= 1'b1;
            if (a[10]) is_open[ba] <= 1'b0;
        end
        4'b0100: begin // WRITE
            if (!is_open[ba]) begin
                $display("%t SDRAM ERREUR: WRITE banque %0d fermée", $time, ba);
                errors = errors + 1;
            end
            for (i = 0; i < NB; i = i + 1)
                if (!dqm[i]) mem[idx(ba, open_row[ba], a[8:0])][i*8 +: 8] <= dq[i*8 +: 8];
            if (a[10]) is_open[ba] <= 1'b0;
        end
        4'b0010: begin // PRECHARGE
            if (a[10]) is_open <= 4'b0; else is_open[ba] <= 1'b0;
        end
        4'b0001: begin // REFRESH
            refreshes = refreshes + 1;
            if (is_open != 0) begin
                $display("%t SDRAM ERREUR: REFRESH avec banque ouverte", $time);
                errors = errors + 1;
            end
        end
        4'b0000: mode_set <= 1'b1;
        default: ;
        endcase
    end
endmodule

// SRAM asynchrone 8 bits
module sram_model #(parameter AW = 20) (
    input  wire [AW-1:0] a,
    inout  wire [7:0]    d,
    input  wire          ce_n, oe_n, we_n
);
    reg [7:0] mem [0:(1<<AW)-1];
    integer i;
    initial for (i = 0; i < (1<<AW); i = i + 1) mem[i] = 8'h00;
    assign #8 d = (!ce_n && !oe_n && we_n) ? mem[a] : 8'hzz;
    always @(posedge we_n) if (!ce_n) mem[a] <= d;
endmodule
