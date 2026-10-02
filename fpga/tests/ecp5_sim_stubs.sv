`timescale 1ns/1fs
// SPDX-License-Identifier: GPL-3.0-or-later
// Stand-ins for the three ECP5 primitives sn64_board_top uses, so that the board's real top
// level can be simulated (fpga/tests/tb_board_game.sv). Behaviour only: the right frequencies,
// a clock select that never cuts a pulse short, and the flash clock brought out where the
// board model can pick it up. No timing of the real cells.

// PLL: every output is the VCO divided by its own divider. With the feedback taken from CLKOS,
// f(CLKOS) = f(CLKI) / CLKI_DIV x CLKFB_DIV and f(VCO) = f(CLKOS) x CLKOS_DIV (the comment at the
// top of sn64_board_top.sv); with the feedback from CLKOP the same with CLKOP. The input period
// is measured, so the outputs follow whatever the board's oscillator model gives.
// With the feedback from CLKOS, CLKOS itself is not generated (it stays low): sn64_board_top uses
// it for the feedback alone, the stand-in needs no feedback, and its edges would be a third of
// all the events of the simulation. +pll_feedback_clock makes it run.
module EHXPLLL #(
    parameter CLKI_DIV = 1, parameter CLKFB_DIV = 1,
    parameter CLKOP_DIV = 8, parameter CLKOS_DIV = 8, parameter CLKOS2_DIV = 8, parameter CLKOS3_DIV = 8,
    parameter CLKOP_ENABLE = "ENABLED", parameter CLKOS_ENABLE = "DISABLED",
    parameter CLKOS2_ENABLE = "DISABLED", parameter CLKOS3_ENABLE = "DISABLED",
    parameter CLKOP_CPHASE = 0, parameter CLKOS_CPHASE = 0, parameter CLKOS2_CPHASE = 0, parameter CLKOS3_CPHASE = 0,
    parameter CLKOP_FPHASE = 0, parameter CLKOS_FPHASE = 0, parameter CLKOS2_FPHASE = 0, parameter CLKOS3_FPHASE = 0,
    parameter FEEDBK_PATH = "CLKOP", parameter PLLRST_ENA = "DISABLED", parameter INTFB_WAKE = "DISABLED",
    parameter STDBY_ENABLE = "DISABLED", parameter DPHASE_SOURCE = "DISABLED",
    parameter OUTDIVIDER_MUXA = "DIVA", parameter OUTDIVIDER_MUXB = "DIVB",
    parameter OUTDIVIDER_MUXC = "DIVC", parameter OUTDIVIDER_MUXD = "DIVD"
) (
    input  wire CLKI, CLKFB, RST, STDBY,
    input  wire PHASESEL0, PHASESEL1, PHASEDIR, PHASESTEP, PHASELOADREG, PLLWAKESYNC,
    input  wire ENCLKOP, ENCLKOS, ENCLKOS2, ENCLKOS3,
    output reg  CLKOP = 1'b0, CLKOS = 1'b0, CLKOS2 = 1'b0, CLKOS3 = 1'b0,
    output reg  LOCK = 1'b0,
    output wire INTLOCK, REFCLK, CLKINTFB
);
    assign INTLOCK = LOCK;
    assign REFCLK = CLKI;
    assign CLKINTFB = 1'b0;
    localparam int FB_OUT_DIV = (FEEDBK_PATH == "CLKOS") ? CLKOS_DIV : CLKOP_DIV;
    real t_last = -1.0, period = 0.0, vco = 0.0;
    integer edges = 0;
    reg running = 1'b0;
    always @(posedge CLKI) begin
        if (t_last >= 0.0) period = $realtime - t_last;
        t_last = $realtime;
        edges = edges + 1;
        if (edges == 8) begin
            vco = period * CLKI_DIV / (1.0 * CLKFB_DIV * FB_OUT_DIV);      // VCO period
            running = 1'b1;
        end
        if (edges == 1350) LOCK <= 1'b1;                                  // 50 us at 27 MHz
    end
    // verilator lint_off ZERODLY
    always begin if (!running) @(posedge running); #(vco * CLKOP_DIV / 2.0) CLKOP = ~CLKOP; end
    wire run_os = running && (FEEDBK_PATH != "CLKOS" || $test$plusargs("pll_feedback_clock"));
    always begin if (!run_os) @(posedge run_os); #(vco * CLKOS_DIV / 2.0) CLKOS = ~CLKOS; end
    always begin if (!running) @(posedge running); #(vco * CLKOS2_DIV / 2.0) CLKOS2 = ~CLKOS2; end
    always begin if (!running) @(posedge running); #(vco * CLKOS3_DIV / 2.0) CLKOS3 = ~CLKOS3; end
    // verilator lint_on ZERODLY
endmodule

// Clock select, mode NEG: an input is switched in and out while it is low, and the output stays
// low when neither is selected.
module DCSC #(
    parameter DCSMODE = "POS"
) (
    input  wire CLK0, CLK1, SEL0, SEL1, MODESEL,
    output wire DCSOUT
);
    reg en0 = 1'b0, en1 = 1'b0;
    always @(negedge CLK0) en0 <= SEL0 & ~en1;
    always @(negedge CLK1) en1 <= SEL1 & ~en0;
    assign DCSOUT = (CLK0 & en0) | (CLK1 & en1);
    initial if (DCSMODE != "NEG") $fatal(1, "DCSC stand-in: only DCSMODE NEG is modelled");
endmodule

// The configuration clock pin as user logic drives it. The board model reads `pin` by its
// hierarchical name and puts it on the net of the CCLK ball.
module USRMCLK (
    input wire USRMCLKI, USRMCLKTS
);
    wire pin = USRMCLKTS ? 1'b0 : USRMCLKI;
endmodule
