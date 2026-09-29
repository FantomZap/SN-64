`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// CDC word transfer from 62.5 MHz to 21.477 MHz with unrelated phase: the
// destination must only ever show values that the source actually held (never
// a torn mix of old and new bits) and must converge to the final value.
module tb_cdc;
    reg sclk=0, dclk=0;
    always #8     sclk=~sclk;        // 62.5 MHz
    always #23.28 dclk=~dclk;        // 21.477 MHz
    reg [15:0] src=16'h0000;
    wire [15:0] dst;
    sn64_cdc_word #(.W(16)) dut(.src_clk(sclk), .src_data(src), .dst_clk(dclk), .dst_data(dst));

    // Every value ever presented by the source is legal; anything else is a tear.
    bit legal [0:65535];
    initial for (int i=0;i<65536;i++) legal[i]=0;
    always @(posedge sclk) legal[src]=1;
    always @(posedge dclk) if (!legal[dst]) $fatal(1,"torn or invented value %h at %0t", dst, $time);

    integer changes=0;
    initial begin
        legal[0]=1;
        // Fast bursts of changes with all bits flipping (worst case for tearing)
        repeat(2000) begin
            @(negedge sclk); src = (changes % 2) ? 16'hFFFF ^ src : src + 16'h0101 + changes; changes=changes+1;
            repeat($urandom_range(0,12)) @(negedge sclk);
        end
        src = 16'hB0B1;
        repeat(40) @(posedge dclk);
        if (dst !== 16'hB0B1) $fatal(1,"did not converge to final value: %h", dst);
        $display("PASS: CDC word transfer 62.5 -> 21.477 MHz, %0d source changes, no torn values, converged", changes);
        $finish;
    end
endmodule
