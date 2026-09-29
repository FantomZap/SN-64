// SPDX-License-Identifier: GPL-3.0-or-later
// Clock-domain crossing helpers for SN64.
//
// Domains: clk_25 (housekeeping: power sequencer, Si5351 start-up),
// clk_host (62.5 MHz, always on: N64 endpoint and CIC), clk_snes (21.477 or
// 21.281 MHz from the Si5351, started once at power-on).

// Two-flop synchroniser for single-bit levels.
module sn64_sync_bit #(parameter INIT = 1'b0) (
    input  wire clk,
    input  wire d,
    output wire q
);
    (* async_reg = "true" *) reg [1:0] ff = {2{INIT}};
    always @(posedge clk) ff <= {ff[0], d};
    assign q = ff[1];
endmodule

// Multi-bit value transfer with a toggle handshake: the source captures a
// new word and flips `req`; the destination sees the synchronised toggle,
// captures the (by then stable) word and flips `ack`. The source does not
// capture again until `ack` matches, so the destination never samples a word
// that is changing. Suited to slowly updated state (controller images,
// status flags); a word written faster than the round trip is replaced by the
// newest one, never torn.
module sn64_cdc_word #(parameter W = 16, parameter [W-1:0] INIT = {W{1'b0}}) (
    input  wire         src_clk,
    input  wire [W-1:0] src_data,
    input  wire         dst_clk,
    output reg  [W-1:0] dst_data = INIT
);
    reg [W-1:0] hold = INIT;
    reg req = 1'b0;
    wire ack_s;
    reg ack = 1'b0;
    // Source side: capture when idle (req == synchronised ack) and data differs.
    always @(posedge src_clk)
        if (req == ack_s && hold != src_data) begin
            hold <= src_data;
            req  <= ~req;
        end
    sn64_sync_bit req_sync (.clk(dst_clk), .d(req), .q(req_s));
    wire req_s;
    // Destination side: capture on a toggle, then acknowledge.
    always @(posedge dst_clk)
        if (req_s != ack) begin
            dst_data <= hold;
            ack <= req_s;
        end
    sn64_sync_bit ack_sync (.clk(src_clk), .d(ack), .q(ack_s));
endmodule
