// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 10:1 TMDS serializer for ECP5: three data channels plus the TMDS clock.
//
// clk_x5 must be exactly 5x clk_pixel and edge-aligned with it (same PLL).
// Each 10-bit word is sent LSB first as five DDR bit pairs through ODDRX1F.
// The TMDS clock channel sends 10'b0000011111, so it rises at each word start.
//
// Simulation: Verilator has no ECP5 primitive library, so under `VERILATOR the
// ODDRX1F is replaced by a behavioural model (D0 during SCLK high, D1 during
// SCLK low, registered on the rising edge). The model is not a timing model.
// Outputs are single-ended bit streams; the differential I/O standard and pin
// placement belong to the board top level.
module sn64_av_serializer (
    input  wire clk_pixel,
    input  wire clk_x5,
    input  wire [9:0] word0, word1, word2,
    output wire [2:0] tmds,
    output wire tmds_clock
);
    reg [9:0] w0 = 10'd0, w1 = 10'd0, w2 = 10'd0;
    reg ptog = 1'b0;
    always @(posedge clk_pixel) begin
        w0 <= word0;
        w1 <= word1;
        w2 <= word2;
        ptog <= ~ptog;
    end

    // Related-clock phase detect: load once per pixel, three x5 edges after the
    // pixel edge, while w* is stable.
    reg ptog_a = 1'b0, ptog_b = 1'b0;
    reg [9:0] s0 = 10'd0, s1 = 10'd0, s2 = 10'd0, sc = 10'd0;
    always @(posedge clk_x5) begin
        ptog_a <= ptog;
        ptog_b <= ptog_a;
        if (ptog_a != ptog_b) begin
            s0 <= w0;
            s1 <= w1;
            s2 <= w2;
            sc <= 10'b0000011111;
        end else begin
            s0 <= s0 >> 2;
            s1 <= s1 >> 2;
            s2 <= s2 >> 2;
            sc <= sc >> 2;
        end
    end

    wire [3:0] d0 = {sc[0], s2[0], s1[0], s0[0]};
    wire [3:0] d1 = {sc[1], s2[1], s1[1], s0[1]};
    wire [3:0] q;
    genvar i;
    generate
        for (i = 0; i < 4; i = i + 1) begin : ddr
            sn64_av_oddr oddr (.sclk(clk_x5), .d0(d0[i]), .d1(d1[i]), .q(q[i]));
        end
    endgenerate
    assign tmds = q[2:0];
    assign tmds_clock = q[3];
endmodule

// One DDR output bit. ECP5 primitive when synthesised with SN64_SYNTH defined,
// behavioural model otherwise. (Not keyed on VERILATOR: whole-design synthesis
// must define VERILATOR to select the SNES core's inferred-memory branch.)
module sn64_av_oddr (
    input  wire sclk, d0, d1,
    output wire q
);
`ifndef SN64_SYNTH
    reg r0 = 1'b0, r1 = 1'b0, r1n = 1'b0;
    always @(posedge sclk) begin
        r0 <= d0;
        r1 <= d1;
    end
    always @(negedge sclk) r1n <= r1;
    assign q = sclk ? r0 : r1n;
`else
    ODDRX1F oddr (.D0(d0), .D1(d1), .SCLK(sclk), .RST(1'b0), .Q(q));
`endif
endmodule
