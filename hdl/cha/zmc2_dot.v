// -----------------------------------------------------------------------------
// Équivalent de la partie "dot" du NEO-ZMC2 : sérialise un mot C de 32 bits
// (8 pixels, 4 plans de bits) en deux pixels par cycle 12 MHz (GAD et GBD).
//
// CR[7:0]  = plan 0   (ROM C impaire, octet bas)
// CR[15:8] = plan 1   (ROM C impaire, octet haut)
// CR[23:16]= plan 2   (ROM C paire, octet bas)
// CR[31:24]= plan 3   (ROM C paire, octet haut)
//
// Cadencé directement par la broche 12M, comme la puce d'origine.
// Comportement repris des rétro-ingénieries publiques du NEO-ZMC2 (Furrtek).
// À VALIDER sur matériel (voir docs/08-validation.md).
// -----------------------------------------------------------------------------
module zmc2_dot (
    input  wire        clk_12m,
    input  wire        even,
    input  wire        load,
    input  wire        h,         // retournement horizontal
    input  wire [31:0] cr,
    output reg  [3:0]  gad,
    output reg  [3:0]  gbd,
    output wire        dota,
    output wire        dotb
);
    reg [31:0] sr = 32'h0;

    always @(negedge clk_12m) begin
        if (load)
            sr <= cr;
        else if (h)
            sr <= {sr[29:24], 2'b00, sr[21:16], 2'b00, sr[13:8], 2'b00, sr[5:0], 2'b00};
        else
            sr <= {2'b00, sr[31:26], 2'b00, sr[23:18], 2'b00, sr[15:10], 2'b00, sr[7:2]};
    end

    always @* begin
        case ({even, h})
        2'b11: {gbd, gad} = {sr[31], sr[23], sr[15], sr[7], sr[30], sr[22], sr[14], sr[6]};
        2'b10: {gbd, gad} = {sr[24], sr[16], sr[8],  sr[0], sr[25], sr[17], sr[9],  sr[1]};
        2'b01: {gbd, gad} = {sr[30], sr[22], sr[14], sr[6], sr[31], sr[23], sr[15], sr[7]};
        default: {gbd, gad} = {sr[25], sr[17], sr[9], sr[1], sr[24], sr[16], sr[8],  sr[0]};
        endcase
    end

    assign dota = |gad;
    assign dotb = |gbd;
endmodule
