// BRAM double port : port A lecture/écriture (liaison), port B lecture (console).
// Latence de lecture : 1 cycle sur chaque port.
module bram_dp #(
    parameter DW   = 8,
    parameter AW   = 13,
    parameter INIT = ""
) (
    input  wire          clk,
    input  wire          a_we,
    input  wire [AW-1:0] a_addr,
    input  wire [DW-1:0] a_wdata,
    output reg  [DW-1:0] a_rdata,
    input  wire [AW-1:0] b_addr,
    output reg  [DW-1:0] b_rdata
);
    reg [DW-1:0] mem [0:(1<<AW)-1];
    initial begin
        if (INIT != "") $readmemh(INIT, mem);
    end
    always @(posedge clk) begin
        if (a_we) mem[a_addr] <= a_wdata;
        a_rdata <= mem[a_addr];
        b_rdata <= mem[b_addr];
    end
endmodule
