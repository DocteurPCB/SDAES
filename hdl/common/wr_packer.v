// -----------------------------------------------------------------------------
// Regroupe les octets du chargeur (adresses croissantes) en mots de DW bits
// avec masque d'octets, puis les place dans une petite FIFO.
// Convention : l'octet d'adresse a va dans la voie (a mod DW/8),
// voie 0 = bits [7:0] (petit-boutiste, comme les fichiers ROM).
// -----------------------------------------------------------------------------
module wr_packer #(
    parameter DW    = 16,
    parameter AW    = 24,          // adresse en mots
    parameter DEPTH = 16           // puissance de 2
) (
    input  wire            clk,
    input  wire            rst,
    input  wire            in_stb,
    input  wire [31:0]     in_addr,  // adresse octet
    input  wire [7:0]      in_data,
    input  wire            flush,    // fin de transfert

    output wire            out_valid,
    output wire [AW-1:0]   out_addr,
    output wire [DW-1:0]   out_data,
    output wire [DW/8-1:0] out_mask,
    input  wire            out_take,
    output wire            empty,
    output reg             overflow
);
    localparam NB = DW / 8;
    localparam LB = (NB == 1) ? 1 : $clog2(NB);
    localparam FW = AW + DW + NB;
    localparam PW = $clog2(DEPTH);

    reg [AW-1:0] cur_addr = 0;
    reg [DW-1:0] cur_data = 0;
    reg [NB-1:0] cur_mask = 0;

    reg [FW-1:0] fifo [0:DEPTH-1];
    reg [PW:0]   wp = 0, rp = 0;
    wire         full = (wp - rp) == DEPTH;
    assign empty     = (wp == rp) && (cur_mask == 0);
    assign out_valid = (wp != rp);
    assign {out_addr, out_data, out_mask} = fifo[rp[PW-1:0]];

    wire [AW-1:0] a_word = in_addr[AW+LB-1:LB];
    wire [LB-1:0] a_lane = (NB == 1) ? {LB{1'b0}} : in_addr[LB-1:0];

    reg          push;
    reg [FW-1:0] push_val;

    always @(posedge clk) begin
        push = 1'b0;
        if (rst) begin
            wp <= 0; rp <= 0; cur_mask <= 0; overflow <= 1'b0;
        end else begin
            if (out_take && out_valid) rp <= rp + 1'b1;

            if (in_stb) begin
                if (cur_mask != 0 && a_word != cur_addr) begin
                    // mot précédent incomplet : on le pousse tel quel
                    push = 1'b1;
                    push_val = {cur_addr, cur_data, cur_mask};
                    cur_mask <= {{NB-1{1'b0}}, 1'b1} << a_lane;
                end else begin
                    cur_mask <= cur_mask | ({{NB-1{1'b0}}, 1'b1} << a_lane);
                end
                cur_addr <= a_word;
                cur_data[a_lane*8 +: 8] <= in_data;
                if (a_lane == NB - 1 && !(cur_mask != 0 && a_word != cur_addr)) begin
                    // mot complet
                    push = 1'b1;
                    push_val = {a_word, cur_data, cur_mask | ({{NB-1{1'b0}}, 1'b1} << a_lane)};
                    push_val[NB + a_lane*8 +: 8] = in_data;
                    cur_mask <= 0;
                end
            end else if (flush && cur_mask != 0) begin
                push = 1'b1;
                push_val = {cur_addr, cur_data, cur_mask};
                cur_mask <= 0;
            end

            if (push) begin
                if (full) overflow <= 1'b1;
                else begin
                    fifo[wp[PW-1:0]] <= push_val;
                    wp <= wp + 1'b1;
                end
            end
        end
    end
endmodule
