// -----------------------------------------------------------------------------
// Regroupe les octets du chargeur en mots de 16 bits avec masque d'octets,
// puis les place dans une petite FIFO.
// Convention : octet d'adresse paire -> bits [7:0] (petit-boutiste, comme les
// fichiers ROM). Les octets d'un transfert sont à adresses croissantes et
// contiguës ; un mot incomplet est poussé à la fin du transfert (flush).
// Une étape de registre en entrée et l'absence de comparateur d'adresse
// gardent ce bloc hors des chemins critiques.
// -----------------------------------------------------------------------------
module wr_packer #(
    parameter AW    = 24,          // adresse en mots de 16 bits
    parameter DEPTH = 4            // puissance de 2
) (
    input  wire            clk,
    input  wire            rst,
    input  wire            in_stb,
    input  wire [31:0]     in_addr,  // adresse octet
    input  wire [7:0]      in_data,
    input  wire            flush,    // fin de transfert

    output reg             out_valid,   // registré : le client ne reprend pas
    output reg  [AW-1:0]   out_addr,    // de mot avant plusieurs cycles
    output reg  [15:0]     out_data,
    output reg  [1:0]      out_mask,
    input  wire            out_take,
    output wire            empty,
    output reg             overflow
);
    localparam FW = AW + 18;
    localparam PW = $clog2(DEPTH);

    // étape d'entrée
    reg          s_stb = 1'b0, s_flush = 1'b0;
    reg [AW:0]   s_addr;
    reg [7:0]    s_data;
    always @(posedge clk) begin
        s_stb   <= in_stb;
        s_flush <= flush;
        s_addr  <= in_addr[AW:0];
        s_data  <= in_data;
    end

    reg [AW-1:0] cur_addr = 0;
    reg [7:0]    cur_lo = 0;
    reg          cur_has_lo = 1'b0;

    reg [FW-1:0] fifo [0:DEPTH-1];
    reg [PW:0]   wp = 0, rp = 0;
    reg [PW:0]   count = 0;
    wire         full = (count == DEPTH);
    assign empty = (wp == rp) && !cur_has_lo && !s_stb && !s_flush && !out_valid;
    always @(posedge clk) begin
        out_valid <= (wp != rp) && !(out_take && out_valid) && !rst;
        {out_addr, out_data, out_mask} <= fifo[rp[PW-1:0]];
    end

    reg          push;
    reg [FW-1:0] push_val;

    always @(posedge clk) begin
        push = 1'b0;
        if (rst) begin
            wp <= 0; rp <= 0; count <= 0; cur_has_lo <= 1'b0; overflow <= 1'b0;
        end else begin
            if (s_stb) begin
                if (!s_addr[0]) begin
                    cur_addr   <= s_addr[AW:1];
                    cur_lo     <= s_data;
                    cur_has_lo <= 1'b1;
                end else begin
                    // octet impair : complète le mot (ou mot avec seul l'octet haut)
                    push = 1'b1;
                    push_val = cur_has_lo ? {cur_addr, s_data, cur_lo, 2'b11}
                                          : {s_addr[AW:1], s_data, 8'h00, 2'b10};
                    cur_has_lo <= 1'b0;
                end
            end else if (s_flush && cur_has_lo) begin
                push = 1'b1;
                push_val = {cur_addr, 8'h00, cur_lo, 2'b01};
                cur_has_lo <= 1'b0;
            end

            if (push) begin
                if (full) overflow <= 1'b1;
                else begin
                    fifo[wp[PW-1:0]] <= push_val;
                    wp <= wp + 1'b1;
                end
            end
            if (out_take && out_valid) rp <= rp + 1'b1;
            count <= count + (push && !full) - (out_take && out_valid);
        end
    end
endmodule
