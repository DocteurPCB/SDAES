// Primitives spécifiques iCE40 (HX8K) et reset.

// PLL : 25 MHz -> 100 MHz (icepll -i 25 -o 100 : DIVR=0 DIVF=31 DIVQ=3, VCO 800 MHz)
module sys_pll (
    input  wire clkin,
    output wire clkout,
    output wire locked
);
`ifdef SIMULATION
    assign clkout = clkin;
    assign locked = 1'b1;
`else
    SB_PLL40_CORE #(
        .FEEDBACK_PATH("SIMPLE"),
        .DIVR(4'b0000),
        .DIVF(7'b0011111),
        .DIVQ(3'b011),
        .FILTER_RANGE(3'b010)
    ) u_pll (
        .REFERENCECLK(clkin),
        .PLLOUTGLOBAL(clkout),
        .LOCK(locked),
        .RESETB(1'b1),
        .BYPASS(1'b0)
    );
`endif
endmodule

// Horloge SDRAM = horloge système inversée, sortie par un registre DDR
module sdram_clk_out (
    input  wire clk,
    output wire pin
);
`ifdef SIMULATION
    assign pin = ~clk;
`else
    SB_IO #(.PIN_TYPE(6'b010001)) u_io (
        .PACKAGE_PIN(pin),
        .OUTPUT_CLK(clk),
        .D_OUT_0(1'b0),      // après le front montant
        .D_OUT_1(1'b1)       // après le front descendant
    );
`endif
endmodule

// Reset synchrone tenu tant que la PLL n'est pas verrouillée
module reset_gen (
    input  wire clk,
    input  wire locked,
    output reg  rst
);
    reg [7:0] cnt = 8'd0;
    initial rst = 1'b1;
    always @(posedge clk) begin
        if (!locked) begin cnt <= 8'd0; rst <= 1'b1; end
        else if (cnt != 8'hFF) cnt <= cnt + 8'd1;
        else rst <= 1'b0;
    end
endmodule
