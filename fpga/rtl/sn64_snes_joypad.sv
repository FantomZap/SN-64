// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 controller path: N64 mailbox button images -> two emulated standard
// SNES pads on the core's serial joypad interface.
//
// The N64 bootstrap reads the N64 controllers through the console's own PIF,
// applies the (configurable) N64->SNES mapping, and writes one 16-bit SNES
// button image per port to the mailbox (JOY1_BUTTONS 0x10, JOY2_BUTTONS 0x12;
// docs/design/n64-endpoint-implementation.md). This block turns each image
// into the serial stream a real SNES pad (two 4021 shift registers) returns.
//
// Mailbox word layout (active-high, 1 = pressed), identical to the order in
// which a standard SNES pad shifts its bits out:
//   bit  0 B      bit  4 Up      bit  8 A      bit 12-15 reserved: write 0.
//   bit  1 Y      bit  5 Down    bit  9 X                 Ignored here; the
//   bit  2 Select bit  6 Left    bit 10 L                 pad always sends the
//   bit  3 Start  bit  7 Right   bit 11 R                 standard ID 0000.
//
// Serial behaviour (core side, see docs/design/controller-path-implementation.md):
//   * joy_strobe high: parallel load; the data line shows B continuously.
//   * each joyN_clock pulse: shift one bit (on the pulse's falling edge, i.e.
//     the end of the core's read, as the upstream adapter does).
//   * order B,Y,Select,Start,Up,Down,Left,Right,A,X,L,R, ID 0,0,0,0, then 1s.
//   * joyN_di[0] is active-low like a real pad (the core inverts it).
//   * joyN_di[1] (the multitap data line) is held idle high, so $4016/$4017
//     bit 1 and $421C-$421F read 0: no multitap (user decision SN64-U-05).
//     Upstream SNESTang ties this line low, which reads as a constant 1.
//   * pad_present[N]=0 models an empty port: both lines idle high, so every
//     bit, including the trailing ones, reads 0 as on a real console.
//
// The shift register itself is SNESTang's controller_adapter (GPL-3.0, pinned
// commit, unmodified: fpga/vendor/snestang-controller/).
//
// Clocking: clk must be the SNES master clock that also clocks the core and
// the mailbox (sn64_n64_endpoint runs on the same 21.477 MHz clock), so the
// 16-bit image and the core's registered strobe/clock need no synchronizer.
module sn64_snes_joypad (
    input  wire        clk,
    input  wire [15:0] joy1_buttons, joy2_buttons,   // mailbox images (layout above)
    input  wire [1:0]  pad_present,                  // [0] port 1, [1] port 2; tie 2'b11 until a mailbox bit exists
    input  wire        joy_strobe,                   // core JOY_STRB (shared by both ports, as on a real SNES)
    input  wire        joy1_clock, joy2_clock,       // core JOY1_CLK / JOY2_CLK (active-high pulses)
    output wire [1:0]  joy1_di, joy2_di              // core JOY1_DI / JOY2_DI (active-low pad data)
);
    // Standard pad image: 12 buttons, ID nibble 0000 in bits 12-15.
    function automatic [15:0] pad_image(input [15:0] buttons);
`ifdef SN64_FAULT_SWAP_BY
        // Fault injection for the testbenches only: swap B and Y. The tests
        // must reject this. Never define in synthesis.
        pad_image = {4'b0000, buttons[11:2], buttons[0], buttons[1]};
`else
        pad_image = {4'b0000, buttons[11:0]};
`endif
    endfunction

    wire port1_data_n, port2_data_n;

    controller_adapter port1 (
        .clk(clk), .snes_buttons(pad_image(joy1_buttons)),
        .snes_joy_strb(joy_strobe), .snes_joy_clk(joy1_clock), .snes_joy_di(port1_data_n)
    );
    controller_adapter port2 (
        .clk(clk), .snes_buttons(pad_image(joy2_buttons)),
        .snes_joy_strb(joy_strobe), .snes_joy_clk(joy2_clock), .snes_joy_di(port2_data_n)
    );

    assign joy1_di = pad_present[0] ? {1'b1, port1_data_n} : 2'b11;
    assign joy2_di = pad_present[1] ? {1'b1, port2_data_n} : 2'b11;
endmodule
