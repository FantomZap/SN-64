// SPDX-License-Identifier: GPL-3.0-or-later
// Bench for sn64_clock_pace (docs/design/frame-lock.md): the SNES master clock made by
// halving a doubled clock, with an occasional low phase held one clk2x period longer.
//
// Checks:
//  1. No shortened pulse, ever: every high phase is exactly one clk2x period, every low
//     phase exactly one or two. This is what makes the slowed clock safe for everything
//     on it and for the cartridge's clock pin.
//  2. Rate 0 leaves the clock untouched (exactly clk2x / 2).
//  3. For each rate, exactly `rate` of 2^20 consecutive master periods are stretched, and
//     the elapsed time is (2^21 + rate) clk2x periods: slowdown rate / (2^21 + rate).
//  4. The stretches are spread evenly (gap between two never differs by more than one
//     master period from 2^20 / rate).
//  5. A new rate written on the host clock takes effect; rate 0 stops the stretching.
//  6. clk2x stopping and restarting (cartridge off and on) never makes a short pulse.
// Fault build SN64_FAULT_PACE_NO_STRETCH (rate ignored) must fail.
`timescale 1ns/1ps
module tb_clock_pace;
    localparam real HALF = 11.640;                 // clk2x = 42.95 MHz (2 x NTSC master)
    localparam real P = 2.0 * HALF;                // one clk2x period
    localparam real EPS = 0.005;
    reg clk2x = 0, clk_host = 0, run = 1;
    always begin #(HALF); if (run || clk2x) clk2x = ~clk2x; end      // stops low, like the board's clock select
    always #8.1 clk_host = ~clk_host;              // 61.7 MHz, unrelated phase
    reg [15:0] rate = 16'd0;
    wire clk_snes, stretching;
    sn64_clock_pace dut (.clk2x(clk2x), .clk_host(clk_host), .rate(rate), .clk_snes(clk_snes), .stretching(stretching));

    function automatic bit near(input real a, input real b); near = (a > b - EPS) && (a < b + EPS); endfunction

    // ---------------- monitor ----------------
    bit      monitor_widths = 1;                   // off only across a deliberate clk2x stop
    realtime t_rise = 0, t_fall = 0;
    longint  periods = 0, stretched = 0, since_stretch = 0;
    longint  gap_min = 64'h7FFF_FFFF_FFFF_FFFF, gap_max = 0;
    bit      gap_valid = 0;
    int      errors = 0;
    real     shortest = 1.0e9;
    always @(posedge clk_snes) begin
        if (t_fall != 0) begin
            real low;
            low = $realtime - t_fall;
            if (low < shortest) shortest = low;
            if (low < P - EPS) begin
                if (errors < 8) $display("short low phase %0.3f ns at %0.3f ns", low, $realtime);
                errors++;
            end
            if (monitor_widths) begin
                if (near(low, 2.0 * P)) begin
                    stretched++;
                    if (gap_valid) begin
                        if (since_stretch < gap_min) gap_min = since_stretch;
                        if (since_stretch > gap_max) gap_max = since_stretch;
                    end
                    gap_valid = 1; since_stretch = 0;
                end else if (!near(low, P)) begin
                    if (errors < 8) $display("low phase %0.3f ns is neither one nor two clk2x periods at %0.3f ns", low, $realtime);
                    errors++;
                end
            end
        end
        t_rise = $realtime;
        periods++; since_stretch++;
    end
    always @(negedge clk_snes) begin
        if (t_rise != 0) begin
            real high;
            high = $realtime - t_rise;
            if (high < shortest) shortest = high;
            if (high < P - EPS) begin
                if (errors < 8) $display("short high phase %0.3f ns at %0.3f ns", high, $realtime);
                errors++;
            end
            if (monitor_widths && !near(high, P)) begin
                if (errors < 8) $display("high phase %0.3f ns is not one clk2x period at %0.3f ns", high, $realtime);
                errors++;
            end
        end
        t_fall = $realtime;
    end

    // Count stretches over exactly n master periods, starting at a rising edge.
    task automatic measure(input longint n, output longint got, output real elapsed_ns);
        longint p0, s0; realtime t0;
        begin
            @(posedge clk_snes); #0.001;
            p0 = periods; s0 = stretched; t0 = t_rise;
            while (periods - p0 < n) begin @(posedge clk_snes); #0.001; end   // after the monitor has counted the edge
            got = stretched - s0; elapsed_ns = t_rise - t0;
        end
    endtask

    task automatic set_rate(input [15:0] r);
        begin
            @(posedge clk_host); rate = r;
            repeat (40) @(posedge clk2x);            // word handshake into the clk2x domain
            if (dut.rate_s !== r) begin $display("FAIL: tb_clock_pace: rate %0d did not reach the divider (%0d)", r, dut.rate_s); $fatal(1); end
            gap_valid = 0; gap_min = 64'h7FFF_FFFF_FFFF_FFFF; gap_max = 0;
        end
    endtask

    longint got; real el, expect_el;
    int rates [0:4] = '{1, 871, 9560, 30000, 65535};
    initial begin
        // 2. rate 0: untouched
        repeat (8) @(posedge clk_snes);
        measure(4096, got, el);
        if (got != 0 || !near(el, 4096.0 * 2.0 * P)) begin
            $display("FAIL: tb_clock_pace: rate 0 changed the clock (%0d stretches, %0.3f ns for 4096 periods)", got, el); $fatal(1);
        end
        // 3. and 4. exact count, elapsed time, even spread
        for (int i = 0; i < 5; i++) begin
            longint ideal;
            set_rate(16'(rates[i]));
            measure(64'd1048576, got, el);
            expect_el = (2097152.0 + rates[i]) * P;
            $display("rate %5d: %0d of 1048576 master periods stretched; %0.1f ppm slower; gaps %0d..%0d periods",
                     rates[i], got, 1.0e6 * rates[i] / (2097152.0 + rates[i]), gap_min, gap_max);
            if (got != rates[i]) begin
                $display("FAIL: tb_clock_pace: rate %0d stretched %0d of 2^20 master periods", rates[i], got); $fatal(1);
            end
            if (el < expect_el - 1.0 || el > expect_el + 1.0) begin
                $display("FAIL: tb_clock_pace: rate %0d took %0.3f ns, expected %0.3f ns", rates[i], el, expect_el); $fatal(1);
            end
            ideal = 64'd1048576 / rates[i];
            if (rates[i] > 1 && (gap_min < ideal || gap_max > ideal + 1)) begin
                $display("FAIL: tb_clock_pace: rate %0d stretches not evenly spread (gaps %0d..%0d, ideal %0d)", rates[i], gap_min, gap_max, ideal); $fatal(1);
            end
        end
        // 5. back to 0 through the handshake
        set_rate(16'd0);
        measure(8192, got, el);
        if (got != 0) begin $display("FAIL: tb_clock_pace: still stretching after rate 0 (%0d)", got); $fatal(1); end
        // 6. clk2x stops and restarts with the divider at either level, while a rate is set
        set_rate(16'd65535);
        for (int k = 0; k < 6; k++) begin
            repeat (37 + k) @(posedge clk2x);
            monitor_widths = 0;
            run = 0; #(500.0 + 3.3 * k); run = 1;
            repeat (6) @(posedge clk_snes);
            monitor_widths = 1;
        end
        repeat (200) @(posedge clk_snes);
        if (errors != 0) begin $display("FAIL: tb_clock_pace: %0d pulse-width errors", errors); $fatal(1); end
        $display("PASS: clock pace: %0d master periods; shortest phase %0.3f ns (one clk2x period is %0.3f ns); rates 1, 871, 9560, 30000 and 65535 stretch exactly that many of 2^20 periods, evenly spread; rate 0 is clk2x / 2; clk2x stop and restart makes no short pulse",
                 periods, shortest, P);
        $finish;
    end
    initial begin #400_000_000; $display("FAIL: tb_clock_pace: timeout"); $fatal(1); end
endmodule
