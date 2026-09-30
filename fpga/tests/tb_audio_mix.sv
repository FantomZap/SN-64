`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Self-checking bench for the cartridge-audio path: sn64_i2s_rx (on a
// 62.5 MHz clock, as clk_host in sn64_top) -> sn64_audio_mix (clk_snes).
//
// ADC model: I2S master on its own time base, Philips format, 24-bit words
// in 32-bit slots, BCK = 64 fs. Its frame rate is 32 kHz x (1 + adc_ppm),
// independent of both FPGA clocks. After every BCK rising edge the model
// changes WS/SD after a random delay d in [1 ns, 0.78 T]: the whole range the
// Philips I2S specification allows a transmitter (hold >= 0, tdtr <= 0.8 T),
// so a receiver that samples too late or too early is caught.
// SNES model: one stereo sample per `snes_rate` Hz from a phase accumulator
// on clk_snes (21.477 MHz), with known values including near-full-scale
// probes for the saturation check.
//
// Checks (all outputs, every run):
//   * integrity: every mixed output equals sat16(snes + adc[23:8]) for ONE
//     ADC frame n with the SAME n on L and R (L/R pairing, sign, truncation),
//     n advancing by exactly 1 per SNES sample except at a slip;
//   * slips: only drops when the ADC is faster, only repeats when slower,
//     never two in a row, spacing consistent with the measured rate offset,
//     at least 2 per run, net count consistent with the frames actually sent;
//     the DUT's own slip counters agree;
//   * saturation: >= 10 outputs where the exact sum is out of range must
//     clamp (never wrap); a second mixer with CART_GAIN = 0.5 must match
//     sat16(snes + adc >>> 9) for the same frames;
//   * cadence: exactly one output per SNES sample; no unknown (X/Z) output
//     bits ($isunknown; meaningful under a four-state simulator such as
//     Icarus, always false under two-state Verilator).
// Plusargs: +adc_ppm=<real> (default 500), +snes_rate=<int Hz> (32000),
//           +duty=<real percent BCK high> (50), +seed=<int>.
// Fault builds that must FAIL: +define+SN64_FAULT_AUDIO_SWAP_LR,
// SN64_FAULT_AUDIO_NO_SIGNEXT, SN64_FAULT_AUDIO_WRAP, SN64_FAULT_I2S_LATE_SAMPLE.
module tb_audio_mix;
    // ---------------------------------------------------------------- clocks
    logic clk_host = 1'b0;  always #8.000  clk_host = ~clk_host;   // 62.5 MHz receiver clock
    logic clk_snes = 1'b0;  always #23.280 clk_snes = ~clk_snes;   // 21.477 MHz SNES master
    logic rst_host_n = 1'b0, rst_snes_n = 1'b0;

    real    adc_ppm;
    integer snes_rate;
    real    duty;
    integer seed;

    // ------------------------------------------------------------- ADC model
    logic bck = 1'b0, lrck = 1'b0, dout = 1'b0;

    function automatic [15:0] l16(input integer n);
        l16 = (n % 64 == 10) ? 16'h7FFF : 16'((n * 7919 + 12345) & 16'hFFFF);
    endfunction
    function automatic [15:0] r16(input integer n);
        r16 = (n % 64 == 10) ? 16'h8000 : 16'((n * 4513 + 40000) & 16'hFFFF);
    endfunction
    function automatic [23:0] adc_word(input integer n, input bit right);
        if (right) adc_word = {r16(n), (n % 64 == 10) ? 8'h00 : 8'((n * 71 + 3) & 8'hFF)};
        else       adc_word = {l16(n), (n % 64 == 10) ? 8'hFF : 8'((n * 29 + 7) & 8'hFF)};
    endfunction
    // Value of WS/SD that the receiver must sample at rising edge j.
    function automatic bit ws_at(input integer j);
        ws_at = ((j / 32) % 2) == 1;
    endfunction
    function automatic bit sd_at(input integer j);
        integer p, s;
        logic [23:0] w;
        p = j % 32; s = j / 32;
        w = adc_word(s / 2, s % 2);
        if (p >= 1 && p <= 24) sd_at = w[24 - p];
        else                   sd_at = 1'b0;
    endfunction

    integer adc_frames_sent = 0;      // frames whose right word has been fully transmitted
    real    t_bck;
    initial begin : adc
        integer j;
        real hi, d;
        j = 0;
        @(posedge rst_host_n);
        #1234.5;                      // arbitrary phase against both FPGA clocks
        t_bck = 1.0e9 / (64.0 * 32000.0 * (1.0 + adc_ppm * 1.0e-6));
        hi = t_bck * duty / 100.0;
        lrck = ws_at(0); dout = sd_at(0);
        forever begin
            // rising edge r_j; afterwards present the values for r_(j+1)
            bck = 1'b1;
            d = 1.0 + (($unsigned($random(seed)) % 1000) / 1000.0) * (0.78 * t_bck - 1.0);
            if (d < hi) begin
                #(d);        lrck = ws_at(j + 1); dout = sd_at(j + 1);
                #(hi - d);   bck = 1'b0;
                #(t_bck - hi);
            end else begin
                #(hi);       bck = 1'b0;
                #(d - hi);   lrck = ws_at(j + 1); dout = sd_at(j + 1);
                #(t_bck - d);
            end
            if (j % 64 == 56) adc_frames_sent = adc_frames_sent + 1;   // right word (bits 33..56) done
            j = j + 1;
        end
    end

    // ------------------------------------------------------------ SNES model
    logic        snes_ready = 1'b0;
    logic [15:0] snes_l = 16'd0, snes_r = 16'd0;
    integer      acc = 0, k_in = 0;
    function automatic [15:0] sl(input integer k);
        if (k % 16 == 5)       sl = 16'sd32000;
        else if (k % 16 == 13) sl = -16'sd31000;
        else                   sl = 16'(((k * 37) % 2001) - 1000);
    endfunction
    function automatic [15:0] sr(input integer k);
        if (k % 16 == 5)       sr = -16'sd32000;
        else if (k % 16 == 13) sr = 16'sd31500;
        else                   sr = 16'(750 - ((k * 53) % 1501));
    endfunction
    always @(posedge clk_snes) begin
        snes_ready <= 1'b0;
        if (rst_snes_n) begin
            if (acc + snes_rate >= 21477272) begin
                acc <= acc + snes_rate - 21477272;
                snes_ready <= 1'b1;
                snes_l <= sl(k_in);
                snes_r <= sr(k_in);
                k_in <= k_in + 1;
            end else acc <= acc + snes_rate;
        end
    end

    // ------------------------------------------------------------------ DUTs
    wire signed [23:0] rx_l, rx_r;
    wire rx_tog, rx_stb, rx_locked; wire [15:0] rx_err;
    sn64_i2s_rx rx (.clk(clk_host), .rst_n(rst_host_n), .bck(bck), .lrck(lrck), .dout(dout),
                    .left(rx_l), .right(rx_r), .frame_tog(rx_tog), .frame_stb(rx_stb),
                    .locked(rx_locked), .frame_errors(rx_err));

    wire [15:0] mix_l, mix_r, ovf, unf; wire mix_ready, active; wire [3:0] fill;
    sn64_audio_mix mix (.clk(clk_snes), .rst_n(rst_snes_n), .cart_enable(1'b1),
                        .adc_left(rx_l), .adc_right(rx_r), .adc_tog(rx_tog), .adc_locked(rx_locked),
                        .snes_left(snes_l), .snes_right(snes_r), .snes_ready(snes_ready),
                        .mix_left(mix_l), .mix_right(mix_r), .mix_ready(mix_ready),
                        .overflow_slips(ovf), .underflow_slips(unf), .cart_active(active), .fill(fill));

    wire [15:0] mix2_l, mix2_r; wire mix2_ready;
    sn64_audio_mix #(.CART_GAIN_Q12(16'd2048)) mix_half (.clk(clk_snes), .rst_n(rst_snes_n), .cart_enable(1'b1),
                        .adc_left(rx_l), .adc_right(rx_r), .adc_tog(rx_tog), .adc_locked(rx_locked),
                        .snes_left(snes_l), .snes_right(snes_r), .snes_ready(snes_ready),
                        .mix_left(mix2_l), .mix_right(mix2_r), .mix_ready(mix2_ready),
                        .overflow_slips(), .underflow_slips(), .cart_active(), .fill());

    // --------------------------------------------------------------- checker
    integer errors = 0, k_out = 0, n_last = -1, seen_k0 = -1;
    integer drops = 0, repeats = 0, sat_count = 0, last_slip_k = -1, min_gap = 1 << 30;
    integer frames_at_start = 0;
    bit     seen_cart = 1'b0, done = 1'b0;
    integer k_target;

    function automatic integer sat16(input integer v);
        sat16 = (v > 32767) ? 32767 : ((v < -32768) ? -32768 : v);
    endfunction
    function automatic integer s16(input [15:0] v);
        s16 = $signed(v);
    endfunction
    function automatic integer c16(input integer n, input bit right, input integer shift);
        logic signed [23:0] w;
        w = $signed(adc_word(n, right));
        c16 = w >>> shift;
    endfunction
    function automatic bit match(input integer n, input integer sl_v, input integer sr_v,
                                 input integer ol, input integer or_v);
        match = (n >= 0) && (sat16(sl_v + c16(n, 0, 8)) == ol) && (sat16(sr_v + c16(n, 1, 8)) == or_v);
    endfunction
    task automatic err(input string msg);
        errors = errors + 1;
        if (errors <= 10) $display("ERROR: %s", msg);
    endtask

    always @(posedge clk_snes) if (mix_ready && !done) begin : check
        integer sl_v, sr_v, ol, orr, c, e2l, e2r;
        bit found;
        sl_v = s16(snes_l); sr_v = s16(snes_r); ol = s16(mix_l); orr = s16(mix_r);
        if ($isunknown({mix_l, mix_r, mix2_l, mix2_r})) err($sformatf("output %0d has unknown bits", k_out));
        if (!mix2_ready) err($sformatf("output %0d: gain-0.5 mixer out of step", k_out));
        found = 1'b0; c = -1;
        if (!seen_cart) begin
            if (ol == sl_v && orr == sr_v) begin
                found = 1'b1;                                  // still priming: SNES audio passes through
            end else if (k_out % 16 != 5 && k_out % 16 != 13) begin
                for (integer n = 0; n < 64 && !found; n++)
                    if (match(n, sl_v, sr_v, ol, orr)) begin found = 1'b1; c = n; end
                if (found) begin
                    seen_cart = 1'b1; seen_k0 = k_out; frames_at_start = adc_frames_sent;
                    $display("%0.1f us: first cartridge frame n=%0d at output %0d (fill %0d after the pop)", $realtime / 1000.0, c, k_out, fill);
                end
            end else found = 1'b1;                             // ambiguous saturation probe while priming
        end else begin
            if      (match(n_last + 1, sl_v, sr_v, ol, orr)) begin found = 1'b1; c = n_last + 1; end
            else if (match(n_last,     sl_v, sr_v, ol, orr)) begin found = 1'b1; c = n_last;     repeats++; end
            else if (match(n_last + 2, sl_v, sr_v, ol, orr)) begin found = 1'b1; c = n_last + 2; drops++;   end
            if (found && c != n_last + 1) begin
                if (last_slip_k >= 0 && k_out - last_slip_k < min_gap) min_gap = k_out - last_slip_k;
                if (last_slip_k >= 0 && k_out - last_slip_k <= 1) err($sformatf("two slips in a row at output %0d", k_out));
                last_slip_k = k_out;
            end
        end
        if (!found)
            err($sformatf("integrity: output %0d L=%h R=%h (snes %h/%h) matches no ADC frame near n=%0d (exp L %h R %h)",
                          k_out, mix_l, mix_r, snes_l, snes_r, n_last + 1,
                          16'(sat16(sl_v + c16(n_last + 1, 0, 8))), 16'(sat16(sr_v + c16(n_last + 1, 1, 8)))));
        if (c >= 0) begin
            if ((sl_v + c16(c, 0, 8)) != sat16(sl_v + c16(c, 0, 8)) || (sr_v + c16(c, 1, 8)) != sat16(sr_v + c16(c, 1, 8)))
                sat_count++;
            e2l = sat16(sl_v + c16(c, 0, 9)); e2r = sat16(sr_v + c16(c, 1, 9));
            if (s16(mix2_l) != e2l || s16(mix2_r) != e2r)
                err($sformatf("gain 0.5: output %0d got %h/%h expected %h/%h", k_out, mix2_l, mix2_r, 16'(e2l), 16'(e2r)));
            n_last = c;
        end
        k_out = k_out + 1;
        if (seen_cart && k_out - seen_k0 >= k_target) done = 1'b1;
    end

    // ------------------------------------------------------------------ main
    initial begin
        real ratio, per, frames_win, net_exp;
        integer net, outs;
        if (!$value$plusargs("adc_ppm=%f", adc_ppm)) adc_ppm = 500.0;
        if (!$value$plusargs("snes_rate=%d", snes_rate)) snes_rate = 32000;
        if (!$value$plusargs("duty=%f", duty)) duty = 50.0;
        if (!$value$plusargs("seed=%d", seed)) seed = 1;
        // Expected ADC/SNES rate ratio from the modelled clocks (clk_snes period 46.56 ns).
        ratio = (32000.0 * (1.0 + adc_ppm * 1.0e-6)) / (snes_rate * (1.0e9 / 46.56) / 21477272.0);
        per = 1.0 / ((ratio > 1.0) ? (ratio - 1.0) : (1.0 - ratio));   // SNES samples per slip
        k_target = $rtoi(per * 7.0) + 256;                              // 4 slips of slack (half buffer) + >= 2 slips
        $display("tb_audio_mix: adc_ppm=%0.1f snes_rate=%0d duty=%0.0f%% ratio=%0.7f -> one slip per %0.0f SNES samples, observing %0d outputs",
                 adc_ppm, snes_rate, duty, ratio, per, k_target);
        repeat (10) @(posedge clk_host); rst_host_n = 1'b1;
        repeat (10) @(posedge clk_snes); rst_snes_n = 1'b1;
        wait (done);
        repeat (4) @(posedge clk_snes);
        outs = k_out - seen_k0;
        frames_win = adc_frames_sent - frames_at_start;
        net = drops - repeats;
        net_exp = outs * (ratio - 1.0);
        $display("outputs %0d (SNES samples %0d), ADC frames in window %0.0f, drops %0d repeats %0d (DUT ovf %0d unf %0d), min gap %0d, saturated %0d, rx frame errors %0d",
                 k_out, k_in, frames_win, drops, repeats, ovf, unf, min_gap, sat_count, rx_err);
        if (!seen_cart) err("cartridge audio never appeared in the mix");
        if (k_out != k_in && k_out + 1 != k_in) err($sformatf("cadence: %0d outputs for %0d SNES samples", k_out, k_in));
        if (ratio > 1.0 && (repeats != 0 || drops < 2)) err($sformatf("ADC faster: expected >= 2 drops and no repeats, got %0d/%0d", drops, repeats));
        if (ratio < 1.0 && (drops != 0 || repeats < 2)) err($sformatf("ADC slower: expected >= 2 repeats and no drops, got %0d/%0d", drops, repeats));
        if (ovf != drops || unf != repeats) err($sformatf("DUT slip counters %0d/%0d disagree with observed %0d/%0d", ovf, unf, drops, repeats));
        if ((net - net_exp) > 6.0 || (net_exp - net) > 6.0)   // half the buffer (4) is absorbed before the first slip, +/-2 jitter
            err($sformatf("net slips %0d vs %0.1f expected from the rate offset", net, net_exp));
        if (min_gap < $rtoi(per * 0.5)) err($sformatf("slips too close: %0d outputs apart, rate implies %0.0f", min_gap, per));
        if (sat_count < 10) err($sformatf("only %0d saturating outputs exercised", sat_count));
        if (rx_err > 2) err($sformatf("%0d I2S slot-length errors after start-up", rx_err));
        if (errors == 0)
            $display("PASS: tb_audio_mix adc_ppm=%0.1f snes_rate=%0d duty=%0.0f%%: %0d outputs bit-exact (L/R paired, sign, truncation, gain 0.5), %0d drops %0d repeats (one per %0d+ samples, expected every %0.0f), %0d saturated, cadence 1:1",
                     adc_ppm, snes_rate, duty, outs, drops, repeats, min_gap, per, sat_count);
        else begin
            $display("FAIL: tb_audio_mix: %0d error(s)", errors);
            $fatal(1, "tb_audio_mix failed");
        end
        $finish;
    end
    initial begin
        #2_000_000_000;
        $display("FAIL: tb_audio_mix: timeout (outputs %0d)", k_out);
        $fatal(1, "timeout");
    end
endmodule
