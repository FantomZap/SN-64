// SPDX-License-Identifier: GPL-3.0-or-later
// Direction sequencing for one SNES CIC data pin through an SN74LVC1T45
// (cart-interface schematic rev 0.3.1, U215/U216). The translator's A side is
// the FPGA pad; DIR high drives the cartridge (A->B), DIR low listens (B->A).
//
// Order that keeps the pad and the translator's A-side output from fighting:
//   drive:   DIR rises with oe; the pad starts driving one clock later.
//   release: the pad stops driving with oe; DIR falls one clock later.
// One clk_25 cycle (40 ns) exceeds the 7.3 ns worst-case DIR disable time at
// VCCA 3.3 V / VCCB 5 V (TI SCES515N section 5.8). The data value itself and
// the pad input go straight between the lock and the pad.
module sn64_cic_pad (
    input  wire clk,
    input  wire oe,       // from sn64_snes_cic_lock data*_oe
    output wire dir,      // to the SN74LVC1T45 DIR pin
    output wire pad_oe    // FPGA output enable on the A-side pad
);
    reg oe_q = 1'b0;
    always @(posedge clk) oe_q <= oe;
`ifdef SN64_FAULT_CIC_PAD_ORDER
    // Fault injection for the testbench only: drive and turn together.
    assign dir    = oe;
    assign pad_oe = oe;
`else
    assign dir    = oe | oe_q;
    assign pad_oe = oe & oe_q;
`endif
endmodule
