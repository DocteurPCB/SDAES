// BRAM simple double port (iCE40 SB_RAM40_4K) : port A écriture (liaison ou
// 68000), port B lecture. Latence de lecture : 1 cycle.
module bram_dp #(
    parameter DW   = 8,
    parameter AW   = 13,
    parameter INIT = ""
) (
    input  wire          clk,
    input  wire          a_we,
    input  wire [AW-1:0] a_addr,
    input  wire [DW-1:0] a_wdata,
    input  wire [AW-1:0] b_addr,
    output reg  [DW-1:0] b_rdata
);
    reg [DW-1:0] mem [0:(1<<AW)-1];
    initial begin
        if (INIT != "") $readmemh(INIT, mem);
    end
    always @(posedge clk) begin
        if (a_we) mem[a_addr] <= a_wdata;
        b_rdata <= mem[b_addr];
    end
endmodule
