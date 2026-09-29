// SPDX-License-Identifier: GPL-3.0-or-later
// Self-checking bench for sn64_snes_cic_lock.
//
// Contains a behavioural key-CIC model (D411 / D413 role) clocked by the
// DUT's CIC_CLK. The model keeps its own copy of both streams, updates them
// with its own C-style implementation of the published table update, drives
// its bit on the pin the protocol assigns to the key and checks every bit it
// receives from the lock. A pull-down resolves released lines and a monitor
// fails on any clock where lock and key drive the same pin.
//
// Independent reference: the physical DATA1/DATA0 bit streams of the first
// four rounds are compared with the output of the C program published on
// wiki.superfamicom.org/cic (built and run separately, see
// docs/design/snes-cic-implementation.md), for seed 0/D411 and seed F/D413.
//
// Fault injection (the bench must then report FAIL):
//   +define+SN64_FAULT_CIC_NO_COMPARE  lock never flags a mismatch
//   +define+SN64_FAULT_CIC_MANGLE      one constant in the RTL table update wrong
`timescale 1ns/1ps
`default_nettype none

module tb_snes_cic_lock;

    // ------------------------------------------------------------ constants
    // Same derived timing as the DUT defaults (instruction cycles x 4 clocks).
    localparam int CPI        = 4;
    localparam int SEED_FIRST = 630 * CPI;
    localparam int SEED_PER   = 15 * CPI;
    localparam int SEED_HIGH  = 3 * CPI;
    localparam int ROUND1     = 806 * CPI;
    localparam int SLOT       = 93 * CPI;
    localparam int OUT_ON     = 10 * CPI;
    localparam int OUT_OFF    = 16 * CPI;
    localparam int SAMPLE     = 50;
    localparam int LAST_BASE  = 145;       // instructions
    localparam int PWRUP_INSN = 25;        // shortened power-up wait for simulation

    // ------------------------------------------------------------------ DUT
    logic clk = 1'b0;
    always #23.280 clk = ~clk;             // 21.477 MHz

    logic       reset_n = 1'b0;
    logic       enable = 1'b0;
    logic       enforce = 1'b0;
    logic       default_pal = 1'b0;
    logic [3:0] seed = 4'h0;

    wire        cic_clk, slave_reset;
    wire        d0_o, d0_oe, d1_o, d1_oe;
    wire        console_run, key_ok, key_fail, region_valid, region_pal;
    wire [15:0] rounds_done;
    wire [2:0]  phase;

    logic k0_o = 1'b0, k0_oe = 1'b0, k1_o = 1'b0, k1_oe = 1'b0;
    wire line0 = d0_oe ? d0_o : (k0_oe ? k0_o : 1'b0);   // pull-down when released
    wire line1 = d1_oe ? d1_o : (k1_oe ? k1_o : 1'b0);

    sn64_snes_cic_lock #(.T_PWRUP(PWRUP_INSN)) dut (
        .clk(clk), .reset_n(reset_n), .enable(enable), .enforce(enforce),
        .default_pal(default_pal), .seed(seed),
        .cic_clk(cic_clk), .slave_reset(slave_reset),
        .data0_o(d0_o), .data0_oe(d0_oe), .data0_i(line0),
        .data1_o(d1_o), .data1_oe(d1_oe), .data1_i(line1),
        .console_run(console_run), .key_ok(key_ok), .key_fail(key_fail),
        .region_valid(region_valid), .region_pal(region_pal),
        .rounds_done(rounds_done), .phase(phase)
    );

    // -------------------------------------------------------------- monitors
    int errors = 0;
    int contention = 0;
    always @(posedge clk) begin
        if ((d0_oe && k0_oe) || (d1_oe && k1_oe)) contention++;
    end

    task automatic check(input bit cond, input string what);
        if (!cond) begin
            errors++;
            $display("ERROR: %s", what);
        end
    endtask

    // ------------------------------------------------------------ key model
    // Model configuration for the current scenario.
    bit  km_present;
    bit  km_pal;
    int  km_skew;             // CIC clocks added to every key event
    int  km_corrupt_round;    // -1 = none
    int  km_corrupt_idx;
    int  km_mismatch;         // bits from the lock that did not match
    int  km_rounds;

    // Recorded physical streams per round (sampled at the key's sample point).
    string rec1 [0:7];
    string rec0 [0:7];
    int    rstart [0:7];

    int tbl [0:1][0:15];      // [0] = stream the lock sends, [1] = stream the key sends
    int kt;                   // CIC_CLK rising edges since the key reset released

    // Published table update, written C-style (independent of the RTL
    // function). Returns the duration in instruction cycles (78 or 84 per
    // iteration, carry at step 3 -> 84).
    function automatic int tb_mangle(int w);
        int d [0:15];
        int a, x, temp, off, carry, cost;
        for (int i = 0; i < 16; i++) d[i] = tbl[w][i];
        cost = 0;
        a = d[15];
        do begin
            x = a; off = 1; carry = 1;
            a = a + d[off] + carry; d[off] = a & 15; a = d[off]; off++;
            a = a + d[off] + carry; a = (~a) & 15; temp = a; a = d[off]; d[off] = temp & 15; off++;
            a = a + d[off] + carry;
            if (a < 16) begin
                temp = a; a = d[off]; d[off] = temp & 15; off++;
                cost += 78;
            end else begin
                cost += 84;
            end
            a = a + d[off]; d[off] = a & 15; a = d[off]; off++;
            carry = 0;
            a = a + d[off] + carry; temp = a; a = d[off]; d[off] = temp & 15; off++;
            a = a + 8;
            if (a < 16) a = a + d[off] + carry;
            temp = a; a = d[off]; d[off] = temp & 15; off++;
            while (off < 16) begin
                a = a + 1 + d[off]; d[off] = a & 15; a = d[off]; off++;
            end
            a = x + 15;
            if (a > 15) begin a = a & 15; carry = 1; end else carry = 0;
        end while (carry != 0);
        for (int i = 0; i < 16; i++) tbl[w][i] = d[i];
        return cost;
    endfunction

    task automatic advance_to(input int target);
        while (kt < target) begin
            @(posedge cic_clk);
            kt++;
        end
    endtask

    task automatic key_model();
        int lseed [0:15] = '{0, 'hb, 1, 4, 'hf, 4, 'hb, 5, 7, 'hf, 'hd, 6, 1, 'he, 9, 8};
        int kseed [0:15] = '{0, 0, 0, 'ha, 1, 8, 5, 'hf, 1, 1, 'he, 1, 0, 'hd, 'he, 'hc};
        int s, start, dir, slot_start, cost, r, bitv, b;
        k0_oe = 0; k1_oe = 0; k0_o = 0; k1_o = 0;
        @(posedge slave_reset);
        @(negedge slave_reset);
        kt = 0;
        // During the seed the key listens on DATA0 and drives DATA1 low.
        k1_oe = 1; k1_o = 0;
        s = 0;
        for (int k = 0; k < 4; k++) begin
            advance_to(SEED_FIRST + k * SEED_PER + SEED_HIGH / 2 + km_skew);
            @(negedge cic_clk);
            b = line0;
            case (k)
                0: s |= b << 3;
                1: s |= b << 0;
                2: s |= b << 1;
                default: s |= b << 2;
            endcase
        end
        advance_to(678 * CPI + km_skew);
        k1_oe = 0;
        advance_to(692 * CPI + km_skew);
        k0_oe = 1; k0_o = 0;
        for (int i = 0; i < 16; i++) begin
            tbl[0][i] = lseed[i];
            tbl[1][i] = kseed[i];
        end
        tbl[1][1] = s;
        tbl[1][2] = km_pal ? 6 : 9;
        start = 1; dir = 0; slot_start = ROUND1; r = 0;
        forever begin
            if (r < 8) begin rec1[r] = ""; rec0[r] = ""; rstart[r] = start; end
            advance_to(slot_start + km_skew);
            if (dir == 0) begin k0_oe = 1; k0_o = 0; end
            else          begin k1_oe = 1; k1_o = 0; end
            for (int i = start; i < 16; i++) begin
                bitv = tbl[1][i] & 1;
                if (r == km_corrupt_round && i == km_corrupt_idx) bitv ^= 1;
                advance_to(slot_start + OUT_ON + km_skew);
                if (dir == 0) k0_o = bitv[0]; else k1_o = bitv[0];
                advance_to(slot_start + SAMPLE + km_skew);
                @(negedge cic_clk);
                if (r < 8) begin
                    rec1[r] = {rec1[r], line1 ? "1" : "0"};
                    rec0[r] = {rec0[r], line0 ? "1" : "0"};
                end
                if ((dir == 0 ? line1 : line0) != tbl[0][i][0]) km_mismatch++;
                advance_to(slot_start + OUT_OFF + km_skew);
                k0_o = 0; k1_o = 0;
                if (i == 15) begin
                    k0_oe = 0; k1_oe = 0;
                end else begin
                    slot_start += SLOT;
                end
            end
            cost = 0;
            for (int m = 0; m < 3; m++) cost += tb_mangle(0);
            for (int m = 0; m < 3; m++) cost += tb_mangle(1);
            slot_start += CPI * (LAST_BASE + cost + ((tbl[1][7] == 0) ? 7 : 5));
            start = (tbl[1][7] == 0) ? 1 : tbl[1][7];
            dir = tbl[1][7] & 1;
            r++;
            km_rounds = r;
        end
    endtask

    // ------------------------------------------------------------ scenarios
    task automatic restart_dut(input logic [3:0] sd, input bit enf, input bit dpal);
        enable = 0;
        k0_oe = 0; k1_oe = 0; k0_o = 0; k1_o = 0;
        repeat (20) @(posedge clk);
        seed = sd; enforce = enf; default_pal = dpal;
        km_mismatch = 0; km_rounds = 0;
        contention = 0;
        enable = 1;
    endtask

    task automatic wait_rounds(input int n, input string name);
        int guard;
        guard = 0;
        while (rounds_done < 16'(n) && guard < 700000 * n) begin
            @(posedge clk);
            guard++;
        end
        check(rounds_done >= 16'(n), $sformatf("%s: lock did not complete %0d rounds (hung, got %0d)",
                                               name, n, rounds_done));
    endtask

    task automatic compare_ref(input string name, input int r, input int st,
                               input string s1, input string s0);
        check(rstart[r] == st, $sformatf("%s round %0d: start index %0d, reference %0d",
                                         name, r, rstart[r], st));
        check(rec1[r] == s1, $sformatf("%s round %0d DATA1: %s, reference %s", name, r, rec1[r], s1));
        check(rec0[r] == s0, $sformatf("%s round %0d DATA0: %s, reference %s", name, r, rec0[r], s0));
    endtask

    task automatic good_key(input string name, input logic [3:0] sd, input bit pal,
                            input int skew, input int with_ref);
        int e0;
        e0 = errors;
        km_present = 1; km_pal = pal; km_skew = skew; km_corrupt_round = -1; km_corrupt_idx = 0;
        restart_dut(sd, 1'b1, ~pal);   // enforce on; default region deliberately opposite
        fork
            key_model();
        join_none
        wait_rounds(5, name);
        repeat (10) @(posedge clk);
        check(key_ok, {name, ": key_ok low"});
        check(!key_fail, {name, ": key_fail set"});
        check(region_valid, {name, ": region not valid"});
        check(region_pal == pal, {name, ": wrong region"});
        check(console_run, {name, ": console held in reset"});
        check(km_mismatch == 0, $sformatf("%s: key model saw %0d wrong lock bits", name, km_mismatch));
        check(contention == 0, $sformatf("%s: %0d contention clocks", name, contention));
        if (with_ref == 1) begin   // seed 0, D411: wiki reference program output
            compare_ref(name, 0, 1,  "110101111101010", "010101111010100");
            compare_ref(name, 1, 6,  "1010000100", "1010101101");
            compare_ref(name, 2, 8,  "10011101", "01111101");
            compare_ref(name, 3, 1,  "010100111110011", "111100001001010");
        end else if (with_ref == 2) begin   // seed F, D413
            compare_ref(name, 0, 1,  "110101111101010", "100101111010100");
            compare_ref(name, 1, 11, "10011", "00100");
            compare_ref(name, 2, 12, "1101", "0011");
            compare_ref(name, 3, 15, "1", "1");
        end
        disable fork;
        $display("%s: %s rounds=%0d key_ok=%0b region_pal=%0b console_run=%0b",
                 (errors == e0) ? "ok  " : "BAD ", name, rounds_done, key_ok, region_pal, console_run);
    endtask

    initial begin
        int e0;
        repeat (5) @(posedge clk);
        reset_n = 1;

        // 0. CIC_CLK frequency and duty from the divider.
        begin
            realtime r0, r1, f0;
            restart_dut(4'h0, 1'b0, 1'b0);
            @(posedge cic_clk); r0 = $realtime;
            @(negedge cic_clk); f0 = $realtime;
            @(posedge cic_clk); r1 = $realtime;
            $display("CIC_CLK period %0.2f ns (%0.4f MHz), high %0.2f ns", r1 - r0,
                     1000.0 / (r1 - r0), f0 - r0);
            check((r1 - r0) > 279.0 && (r1 - r0) < 280.0, "CIC_CLK period is not 6 master clocks");
            check((f0 - r0) > 139.0 && (f0 - r0) < 140.0, "CIC_CLK is not 50% duty");
        end

        // 1-2. NTSC and PAL keys against the published reference streams.
        good_key("ntsc-seed0-ref", 4'h0, 1'b0, 0, 1);
        good_key("pal-seedF-ref",  4'hF, 1'b1, 0, 2);
        // 3-4. Other seeds.
        good_key("pal-seed5",  4'h5, 1'b1, 0, 0);
        good_key("ntsc-seedA", 4'hA, 1'b0, 0, 0);
        // 5-6. Key timing offset by +/- 2 instruction cycles still passes.
        good_key("ntsc-skew+8", 4'h3, 1'b0,  8, 0);
        good_key("pal-skew-8",  4'hC, 1'b1, -8, 0);

        // 7. No key, pass-through policy: failure flagged, console runs, no hang.
        e0 = errors;
        km_present = 0;
        restart_dut(4'hF, 1'b0, 1'b0);
        wait_rounds(3, "no-key");
        check(key_fail, "no-key: failure not flagged");
        check(!key_ok, "no-key: key_ok set");
        check(!region_valid, "no-key: region claimed valid");
        check(region_pal == 1'b0, "no-key: region not the default");
        check(console_run, "no-key pass-through: console held in reset");
        $display("%s: no-key pass-through rounds=%0d key_fail=%0b console_run=%0b",
                 (errors == e0) ? "ok  " : "BAD ", rounds_done, key_fail, console_run);

        // 8. No key, enforce policy: console stays in reset, sequencer keeps going.
        e0 = errors;
        restart_dut(4'h0, 1'b1, 1'b1);
        wait_rounds(3, "no-key-enforce");
        check(key_fail, "no-key-enforce: failure not flagged");
        check(!console_run, "no-key-enforce: console released");
        check(region_pal == 1'b1, "no-key-enforce: default region not reported");
        $display("%s: no-key enforce rounds=%0d key_fail=%0b console_run=%0b",
                 (errors == e0) ? "ok  " : "BAD ", rounds_done, key_fail, console_run);

        // 9. One corrupted key bit (round 2, element 15), enforce policy.
        e0 = errors;
        km_present = 1; km_pal = 0; km_skew = 0; km_corrupt_round = 2; km_corrupt_idx = 15;
        restart_dut(4'h0, 1'b1, 1'b0);
        fork
            key_model();
        join_none
        wait_rounds(2, "corrupt");
        repeat (10) @(posedge clk);
        check(key_ok && !key_fail && console_run, "corrupt: rounds before the corrupted bit did not pass");
        wait_rounds(3, "corrupt");
        repeat (10) @(posedge clk);
        check(key_fail, "corrupt: corrupted key bit not detected");
        check(!key_ok, "corrupt: key_ok still set");
        check(!console_run, "corrupt-enforce: console not stopped");
        disable fork;
        $display("%s: corrupted bit (enforce) key_fail=%0b console_run=%0b",
                 (errors == e0) ? "ok  " : "BAD ", key_fail, console_run);

        // 10. Same corruption, pass-through: flagged, console keeps running.
        e0 = errors;
        restart_dut(4'h0, 1'b0, 1'b0);
        fork
            key_model();
        join_none
        wait_rounds(3, "corrupt-pass");
        repeat (10) @(posedge clk);
        check(key_fail, "corrupt-pass: corrupted key bit not detected");
        check(console_run, "corrupt-pass: console stopped in pass-through");
        disable fork;
        $display("%s: corrupted bit (pass-through) key_fail=%0b console_run=%0b",
                 (errors == e0) ? "ok  " : "BAD ", key_fail, console_run);

        // 11. Key 5 instruction cycles late: outside the sample window, must fail.
        e0 = errors;
        km_corrupt_round = -1; km_skew = 20;
        restart_dut(4'h0, 1'b1, 1'b0);
        fork
            key_model();
        join_none
        wait_rounds(2, "late-key");
        check(key_fail, "late-key: desynchronised key not detected");
        disable fork;
        $display("%s: key 20 CIC clocks late key_fail=%0b", (errors == e0) ? "ok  " : "BAD ", key_fail);

        if (errors == 0)
            $display("PASS: SNES CIC lock: D411/D413 handshakes match reference streams, region detected, no-key and corrupted-bit cases flagged, no contention");
        else begin
            $display("FAIL: SNES CIC lock: %0d error(s)", errors);
            $fatal(1, "SNES CIC lock bench failed");   // non-zero exit for evaluate.py
        end
        $finish;
    end

endmodule

`default_nettype wire
