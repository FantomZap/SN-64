// Bench for sn64_sd_adc: an RC integrator model on each feedback pin, a DC level
// on each + input, and the delivered words must land within the boxcar's noise
// of the expected code. Three levels are tried (mid-rail, +0.28 FS, -0.55 FS).
// SPDX-License-Identifier: GPL-3.0-or-later
`timescale 1ns/1ps
module tb_sd_adc;
    reg clk = 0; always #8 clk = ~clk;          // 62.5 MHz
    reg rst_n = 0;
    real vin_l = 0.5, vin_r = 0.5;                // 0..1 of the 3.3 V rail, 0.5 = bias
    real vnode_l = 0.5, vnode_r = 0.5;
    localparam real ALPHA = 16.0e-9 / (10.0e3 * 1.0e-9);   // clock period / RC (10 k, 1 nF)
    wire fb_l, fb_r;
    wire cmp_l = vin_l > vnode_l, cmp_r = vin_r > vnode_r;
    always @(posedge clk) begin
        vnode_l <= vnode_l + ((fb_l ? 1.0 : 0.0) - vnode_l) * ALPHA;
        vnode_r <= vnode_r + ((fb_r ? 1.0 : 0.0) - vnode_r) * ALPHA;
    end
    wire signed [23:0] left, right; wire tog, stb, locked; wire [15:0] errs;
    sn64_sd_adc dut (.clk(clk), .rst_n(rst_n), .cmp_l(cmp_l), .cmp_r(cmp_r), .fb_l(fb_l), .fb_r(fb_r),
                     .left(left), .right(right), .frame_tog(tog), .frame_stb(stb), .locked(locked), .frame_errors(errs));

    task automatic check(input real lvl_l, input real lvl_r, input string what);
        int n, bad, exp_l, exp_r, tol;
        vin_l = lvl_l; vin_r = lvl_r;
        exp_l = $rtoi((lvl_l - 0.5) * 2.0 * 8388608.0); exp_r = $rtoi((lvl_r - 0.5) * 2.0 * 8388608.0);
        tol = 8388608 / 64;                          // 1.6 % of full scale: boxcar over 2048 plus the loop's limit cycle
        repeat (6) @(posedge stb);                   // let the RC node settle and the window refill
        bad = 0;
        for (n = 0; n < 8; n++) begin
            @(posedge stb); #1;
            if ((left - exp_l > tol) || (exp_l - left > tol) || (right - exp_r > tol) || (exp_r - right > tol)) begin
                bad++;
                $display("  %s: sample %0d L=%0d (exp %0d) R=%0d (exp %0d)", what, n, left, exp_l, right, exp_r);
            end
        end
        if (bad != 0) $fatal(1, "sd adc: %0d of 8 samples outside tolerance for %s", bad, what);
        $display("sd adc %s: L=%0d (exp %0d) R=%0d (exp %0d) ok", what, left, exp_l, right, exp_r);
    endtask

    initial begin
        #100 rst_n = 1;
        check(0.5, 0.5, "mid-rail");
        check(0.5 + 0.14, 0.5 - 0.275, "+0.28/-0.55 FS");
        check(0.5 + 0.40, 0.5 + 0.05, "+0.80/+0.10 FS");
        if (!locked || errs != 0) $fatal(1, "sd adc: locked=%0d errors=%0d", locked, errs);
        $display("PASS: sigma-delta ADC: three DC levels within 1.6 %% of full scale on both channels, %0d clocks per sample", 2048);
        $finish;
    end
endmodule
