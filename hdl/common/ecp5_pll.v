// PLL ECP5 : 25 MHz -> 133,33 MHz (VCO 533 MHz).
// Paramètres à régénérer avec `ecppll -i 25 -o 133.333` si l'oscillateur change.
module ecp5_pll (
    input  wire clkin,
    output wire clkout,
    output wire locked
);
`ifdef SIMULATION
    assign clkout = clkin;
    assign locked = 1'b1;
`else
    (* FREQUENCY_PIN_CLKI="25" *)
    (* FREQUENCY_PIN_CLKOP="133.333" *)
    (* ICP_CURRENT="12" *) (* LPF_RESISTOR="8" *) (* MFG_ENABLE_FILTEROPAMP="1" *) (* MFG_GMCREF_SEL="2" *)
    EHXPLLL #(
        .PLLRST_ENA("DISABLED"),
        .INTFB_WAKE("DISABLED"),
        .STDBY_ENABLE("DISABLED"),
        .DPHASE_SOURCE("DISABLED"),
        .OUTDIVIDER_MUXA("DIVA"),
        .OUTDIVIDER_MUXB("DIVB"),
        .OUTDIVIDER_MUXC("DIVC"),
        .OUTDIVIDER_MUXD("DIVD"),
        .CLKI_DIV(3),
        .CLKOP_ENABLE("ENABLED"),
        .CLKOP_DIV(4),
        .CLKOP_CPHASE(1),
        .CLKOP_FPHASE(0),
        .FEEDBK_PATH("CLKOP"),
        .CLKFB_DIV(16)
    ) u_pll (
        .RST(1'b0), .STDBY(1'b0), .CLKI(clkin), .CLKOP(clkout), .CLKFB(clkout), .CLKINTFB(),
        .PHASESEL0(1'b0), .PHASESEL1(1'b0), .PHASEDIR(1'b1), .PHASESTEP(1'b1), .PHASELOADREG(1'b1),
        .PLLWAKESYNC(1'b0), .ENCLKOP(1'b0), .LOCK(locked)
    );
`endif
endmodule

// Sortie d'horloge SDRAM = horloge système inversée (registre DDR de sortie)
module sdram_clk_out (
    input  wire clk,
    output wire pin
);
`ifdef SIMULATION
    assign pin = ~clk;
`else
    ODDRX1F u_oddr (.SCLK(clk), .RST(1'b0), .D0(1'b0), .D1(1'b1), .Q(pin));
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
