// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 SNES master clock with pace control (docs/design/frame-lock.md).
//
// The console's picture rate and the Super NES's differ by a few hundredths of
// a percent (SNES-shaped console timing) or by 0.45 % (the console's standard
// timing). To show exactly one SNES picture per console picture the SNES is
// slowed by that amount: its master clock is made here by halving a clock of
// twice the frequency, and now and then one low phase is held for one more
// clk2x period. That master period is 3 half-periods long instead of 2.
//
// Nothing is gated and no pulse is ever shortened: clk_snes is the output of a
// flip-flop, its high phase is always one clk2x period and its low phase one
// or two. Every clocked element on clk_snes, and the cartridge's own clock pin,
// simply sees a slightly slower clock.
//
// `rate` of every 2^ACC_BITS master periods are stretched, evenly spread:
//   average period = nominal x (1 + rate / 2^(ACC_BITS+1))
//   ACC_BITS = 20: one count = 0.477 ppm, 0xFFFF = 3.03 % slower, 0 = untouched.
// `rate` comes from the N64 mailbox (clk_host) and crosses with the word
// handshake; clk2x may be stopped (cartridge off), the divider then holds its
// level and the new rate is taken when the clock runs again.
module sn64_clock_pace #(
    parameter ACC_BITS = 20
) (
    input  wire        clk2x,            // 2 x SNES master, from the region select; stops while the cartridge is off
    input  wire        clk_host,         // domain of `rate`
    input  wire [15:0] rate,
    output reg         clk_snes = 1'b0,
    output wire        stretching        // high for the one clk2x period a stretch adds (tests, diagnostics)
);
    wire [15:0] rate_s;
    sn64_cdc_word #(.W(16)) x_rate (.src_clk(clk_host), .src_data(rate), .dst_clk(clk2x), .dst_data(rate_s));

    reg [ACC_BITS-1:0] acc = '0;
    reg                hold = 1'b0;
    wire [ACC_BITS:0]  sum = {1'b0, acc} + {{(ACC_BITS + 1 - 16){1'b0}}, rate_s};
    always @(posedge clk2x) begin
        if (hold) begin
            hold <= 1'b0;                              // the added clk2x period: the low phase goes on
        end else begin
            clk_snes <= !clk_snes;
            if (clk_snes) begin                        // this edge is the falling edge: decide about the low phase
                acc  <= sum[ACC_BITS-1:0];
`ifdef SN64_FAULT_PACE_NO_STRETCH
                hold <= 1'b0;                          // fault injection: the rate is ignored (tb_clock_pace must fail)
`else
                hold <= sum[ACC_BITS];
`endif
            end
        end
    end
    assign stretching = hold;
endmodule
