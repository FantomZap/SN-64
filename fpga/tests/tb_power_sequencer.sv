`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Power-control state machine checks: ordered bring-up, permit only in RUN
// with every hardware condition true, request loss and host reset shut down,
// each fault class trips within one clock, latches, and needs an explicit
// clear with the request dropped. Uses shortened timing parameters.
// A second instance has the cartridge check built in (PROBE_ENABLE = 1) and is
// fed rail readings directly: pass needs consecutive readings, a rail that
// stays low faults in enforce mode and never gets 5 V, report-only starts
// anyway, check-only never powers, and the check is skipped in mode "off".
module tb_power_sequencer;
    reg clk=0; always #23.28 clk=~clk;
    reg reset_n=0;
    reg configured=1, host_3v3_ok=1, fpga_rails_ok=1, efuse_fault_n=1, overtemp=0, host_reset_n=1;
    reg rail_5v_dead=0;                     // model a 5 V rail that never comes up
    reg cart_5v_ok=0, iface_rail_ok=0;
    reg run_request=0, fault_clear=0, hold_reset=0;
    reg [1:0] mode0=2'd0;                   // check mode of the instance without the check
    wire probe_req0;
    wire cart_5v_enable, iface_rail_enable, cart_reset_pull, bus_permit, fault_latched;
    wire [3:0] state; wire [7:0] fault_code;
    localparam S_OFF=0, S_RUN=4, S_SHUTDOWN=5, S_FAULT=6, S_PROBE=7, S_PROBE_END=8, S_PROBE_HOLD=9;

    sn64_power_sequencer #(.CLK_HZ(21_477_272), .RESET_HOLD_MS(1), .RAIL_TIMEOUT_MS(2)) dut (
        .clk(clk), .reset_n(reset_n),
        .configured(configured), .host_3v3_ok(host_3v3_ok), .fpga_rails_ok(fpga_rails_ok),
        .cart_5v_ok(cart_5v_ok), .iface_rail_ok(iface_rail_ok), .efuse_fault_n(efuse_fault_n),
        .overtemp(overtemp), .host_reset_n(host_reset_n),
        .run_request(run_request), .fault_clear(fault_clear), .hold_reset(hold_reset), .release_ok(1'b1),
        .probe_mode(mode0), .probe_req(probe_req0), .probe_active(1'b0), .probe_strobe(1'b0), .probe_code(12'd0),
        .probe_done(), .probe_pass(), .probe_mode_q(), .probe_level(),
        .cart_5v_enable(cart_5v_enable), .iface_rail_enable(iface_rail_enable), .cart_reset_pull(cart_reset_pull),
        .bus_permit(bus_permit), .fault_latched(fault_latched), .state(state), .fault_code(fault_code));

    // ---------------- instance with the cartridge check ----------------
    reg run_p=0, clear_p=0, overtemp_p=0, stuck_active=0, forbid_5v=0;
    reg [1:0] mode_p=2'd0;
    reg probe_strobe_p=0; reg [11:0] probe_code_p=0;
    reg cart_5v_ok_p=0, iface_ok_p=0;
    wire probe_req_p, probe_done_p, probe_pass_p; wire [1:0] probe_mode_q_p; wire [7:0] probe_level_p;
    wire cart_5v_enable_p, iface_enable_p, cart_reset_pull_p, bus_permit_p, fault_latched_p;
    wire [3:0] state_p; wire [7:0] fault_code_p;
    // The monitor keeps the sense pin for a while after the request drops.
    reg [5:0] act_cnt=0;
    always @(posedge clk) act_cnt <= probe_req_p ? 6'd40 : ((act_cnt != 0 && !stuck_active) ? act_cnt - 6'd1 : act_cnt);
    wire probe_active_p = probe_req_p || (act_cnt != 0);
    sn64_power_sequencer #(.CLK_HZ(21_477_272), .RESET_HOLD_MS(1), .RAIL_TIMEOUT_MS(2),
                           .PROBE_ENABLE(1), .PROBE_TIMEOUT_MS(3), .PROBE_OK_CODE(12'd269), .PROBE_OK_SAMPLES(2)) dut_p (
        .clk(clk), .reset_n(reset_n),
        .configured(1'b1), .host_3v3_ok(1'b1), .fpga_rails_ok(1'b1),
        .cart_5v_ok(cart_5v_ok_p), .iface_rail_ok(iface_ok_p), .efuse_fault_n(1'b1),
        .overtemp(overtemp_p), .host_reset_n(1'b1),
        .run_request(run_p), .fault_clear(clear_p), .hold_reset(1'b0), .release_ok(1'b1),
        .probe_mode(mode_p), .probe_req(probe_req_p), .probe_active(probe_active_p),
        .probe_strobe(probe_strobe_p), .probe_code(probe_code_p),
        .probe_done(probe_done_p), .probe_pass(probe_pass_p), .probe_mode_q(probe_mode_q_p), .probe_level(probe_level_p),
        .cart_5v_enable(cart_5v_enable_p), .iface_rail_enable(iface_enable_p), .cart_reset_pull(cart_reset_pull_p),
        .bus_permit(bus_permit_p), .fault_latched(fault_latched_p), .state(state_p), .fault_code(fault_code_p));
    reg [2:0] ramp5_p=0, rampi_p=0;
    always @(posedge clk) begin
        ramp5_p <= cart_5v_enable_p ? (ramp5_p==3'd7 ? ramp5_p : ramp5_p+1) : 0;
        rampi_p <= iface_enable_p && cart_5v_ok_p ? (rampi_p==3'd7 ? rampi_p : rampi_p+1) : 0;
        cart_5v_ok_p <= (ramp5_p >= 3'd4);
        iface_ok_p   <= (rampi_p >= 3'd4);
    end
    always @(negedge clk) begin
        if (probe_req0) $fatal(1,"instance without the check asked for the test current");
        if (probe_req_p && cart_5v_enable_p) $fatal(1,"test current and the 5 V switch on together");
        if (probe_req_p && state_p!=S_PROBE) $fatal(1,"test current outside the check (state %0d)",state_p);
        if (forbid_5v && cart_5v_enable_p) $fatal(1,"5 V enabled although the check must prevent it (state %0d)",state_p);
        // (one clock in SHUTDOWN after RUN is the old behaviour; the top level also pulls /RESET whenever the bus is not permitted)
        if (!cart_reset_pull_p && state_p!=S_RUN && state_p!=S_PROBE && state_p!=S_SHUTDOWN) $fatal(1,"/RESET released in state %0d",state_p);
        if (bus_permit_p && state_p!=S_RUN) $fatal(1,"check instance: bus_permit outside RUN");
    end
    // One rail reading from the monitor.
    task sample(input [11:0] code); begin
        repeat(200) @(negedge clk);
        probe_code_p=code; probe_strobe_p=1; @(negedge clk); probe_strobe_p=0;
    end endtask
    task stop_p; begin
        run_p=0; clear_p=1; wait(state_p==S_OFF); repeat(3) @(negedge clk); clear_p=0; forbid_5v=0;
        if (fault_latched_p) $fatal(1,"check instance: still latched after clear");
        if (cart_5v_enable_p||iface_enable_p||bus_permit_p||!cart_reset_pull_p||probe_req_p) $fatal(1,"check instance: outputs not safe in OFF");
        repeat(60) @(negedge clk);          // the monitor has given the pin back
    end endtask
    task check_tests; begin
        // P1) enforce, rail rises: a single good reading is not enough, two in a row are; 5 V only after
        //     the monitor has given the sense pin back; then the normal bring-up.
        mode_p=2'd0; run_p=1; wait(state_p==S_PROBE); repeat(3) @(negedge clk);
        if (!probe_req_p || cart_reset_pull_p || cart_5v_enable_p) $fatal(1,"P1: check state outputs wrong");
        sample(12'd100); sample(12'd300); sample(12'd250); repeat(20) @(negedge clk);
        if (state_p!=S_PROBE) $fatal(1,"P1: passed without two consecutive readings (state %0d)",state_p);
        sample(12'd300); sample(12'd310); wait(state_p==S_PROBE_END); repeat(10) @(negedge clk);
        if (state_p!=S_PROBE_END || cart_5v_enable_p) $fatal(1,"P1: did not wait for the monitor (state %0d)",state_p);
        wait(state_p==S_RUN); repeat(3) @(negedge clk);
        if (!bus_permit_p || !probe_done_p || !probe_pass_p || probe_level_p!==8'd77 || probe_mode_q_p!==2'd0)
            $fatal(1,"P1: result wrong: done=%b pass=%b level=%0d",probe_done_p,probe_pass_p,probe_level_p);
        stop_p;
        // P2) enforce, rail held at a diode drop (code 186 = 0.45 V): fault 0x01, 5 V never enabled
        mode_p=2'd0; forbid_5v=1; run_p=1; wait(state_p==S_PROBE);
        while (state_p==S_PROBE) sample(12'd186);
        repeat(3) @(negedge clk);
        if (state_p!=S_FAULT || !fault_latched_p || fault_code_p!==8'h01) $fatal(1,"P2: no check fault (state %0d code %h)",state_p,fault_code_p);
        if (!probe_done_p || probe_pass_p || probe_level_p!==8'd46) $fatal(1,"P2: result wrong: done=%b pass=%b level=%0d",probe_done_p,probe_pass_p,probe_level_p);
        repeat(200) @(negedge clk);
        clear_p=1; repeat(3) @(negedge clk);
        if (state_p!=S_FAULT) $fatal(1,"P2: cleared while request still high"); clear_p=0;
        stop_p;
        if (!probe_done_p || probe_pass_p) $fatal(1,"P2: result lost when the request dropped");
        // P3) report only, same rail: recorded as failed, started anyway
        mode_p=2'd1; run_p=1; wait(state_p==S_PROBE);
        if (probe_done_p) $fatal(1,"P3: old result not cleared at the new request");
        while (state_p==S_PROBE) sample(12'd186);
        wait(state_p==S_RUN); repeat(3) @(negedge clk);
        if (fault_latched_p || !probe_done_p || probe_pass_p || probe_mode_q_p!==2'd1 || !bus_permit_p) $fatal(1,"P3: report-only result wrong");
        stop_p;
        // P4) check only, rail rises: result recorded, nothing powered, waits for the request to drop
        mode_p=2'd3; forbid_5v=1; run_p=1; wait(state_p==S_PROBE);
        sample(12'd400); sample(12'd400); wait(state_p==S_PROBE_HOLD); repeat(3000) @(negedge clk);
        if (state_p!=S_PROBE_HOLD || fault_latched_p || !probe_done_p || !probe_pass_p) $fatal(1,"P4: check-only pass wrong");
        stop_p;
        // P5) check only, rail held low: failed result, no fault, nothing powered
        mode_p=2'd3; forbid_5v=1; run_p=1; wait(state_p==S_PROBE);
        while (state_p==S_PROBE) sample(12'd10);
        wait(state_p==S_PROBE_HOLD); repeat(3) @(negedge clk);
        if (fault_latched_p || !probe_done_p || probe_pass_p || probe_level_p!==8'd2) $fatal(1,"P5: check-only fail wrong");
        stop_p;
        // P6) off: no check, straight to the bring-up
        mode_p=2'd2; run_p=1; wait(state_p!=S_OFF); @(negedge clk);
        if (state_p==S_PROBE) $fatal(1,"P6: check ran in mode off");
        wait(state_p==S_RUN); repeat(3) @(negedge clk);
        if (probe_done_p || !bus_permit_p) $fatal(1,"P6: mode off result wrong");
        stop_p;
        // P7) request dropped during the check: back to OFF, no fault
        mode_p=2'd0; forbid_5v=1; run_p=1; wait(state_p==S_PROBE); sample(12'd186);
        run_p=0; wait(state_p==S_OFF); repeat(3) @(negedge clk);
        if (fault_latched_p || probe_req_p) $fatal(1,"P7: abort left a fault or the test current on");
        stop_p;
        // P8) hardware fault during the check: trips like anywhere else, test current off
        mode_p=2'd0; forbid_5v=1; run_p=1; wait(state_p==S_PROBE); sample(12'd186);
        overtemp_p=1; repeat(2) @(negedge clk);
        if (state_p!=S_FAULT || fault_code_p!==8'h80 || probe_req_p) $fatal(1,"P8: overtemp during the check (state %0d code %h)",state_p,fault_code_p);
        overtemp_p=0; stop_p;
        // P9) the monitor never gives the pin back: fault, 5 V never enabled
        mode_p=2'd0; forbid_5v=1; stuck_active=1; run_p=1; wait(state_p==S_PROBE);
        sample(12'd400); sample(12'd400); wait(state_p==S_FAULT); repeat(3) @(negedge clk);
        if (fault_code_p!==8'h01) $fatal(1,"P9: stuck monitor code %h",fault_code_p);
        stuck_active=0; stop_p;
        // P10) a build without the check asked for check only: never powers
        mode0=2'd3; run_request=1; wait(state==S_PROBE_HOLD); repeat(3000) @(negedge clk);
        if (state!=S_PROBE_HOLD || cart_5v_enable || fault_latched) $fatal(1,"P10: check-only powered a build without the check");
        run_request=0; wait(state==S_OFF); mode0=2'd0; expect_safe;
    end endtask

    // Rail models: valid a few clocks after enable, drop immediately when disabled.
    reg [2:0] ramp5=0, rampi=0;
    always @(posedge clk) begin
        ramp5 <= cart_5v_enable && !rail_5v_dead ? (ramp5==3'd7 ? ramp5 : ramp5+1) : 0;
        rampi <= iface_rail_enable && cart_5v_ok ? (rampi==3'd7 ? rampi : rampi+1) : 0;
        cart_5v_ok    <= (ramp5 >= 3'd4);
        iface_rail_ok <= (rampi >= 3'd4);
    end

    integer cycles=0;
    always @(negedge clk) begin
        cycles=cycles+1;
        if (bus_permit && !(cart_5v_ok && iface_rail_ok && configured && host_3v3_ok && fpga_rails_ok && efuse_fault_n && !overtemp && run_request && host_reset_n && !fault_latched))
            $fatal(1,"bus_permit high with a hardware condition false (t=%0d)",cycles);
        if (bus_permit && state!=S_RUN) $fatal(1,"bus_permit outside RUN");
        if (iface_rail_enable && !cart_5v_enable) $fatal(1,"interface rail enabled before cartridge 5 V");
        if (cycles>4_000_000) $fatal(1,"timeout in state %0d",state);
    end

    task bring_up; begin
        run_request=1; wait(state==S_RUN); repeat(3) @(negedge clk);
        if (!bus_permit) $fatal(1,"no permit in RUN");
        if (cart_reset_pull) $fatal(1,"reset still pulled in RUN");
    end endtask
    task expect_safe; begin
        repeat(4) @(negedge clk);
        if (cart_5v_enable||iface_rail_enable||bus_permit||!cart_reset_pull) $fatal(1,"outputs not safe (state %0d)",state);
    end endtask
    // Fault must already be latched; hold for a while, check no auto-restart,
    // check clear is refused while requested, then clear properly.
    task clear_fault(input [7:0] code_mask, input [127:0] name); begin
        wait(state==S_FAULT); @(negedge clk);
        if (!fault_latched || (fault_code & code_mask)==0) $fatal(1,"%0s: fault not latched/coded (code %b)",name,fault_code);
        expect_safe;
        fault_clear=1; repeat(3) @(negedge clk);
        if (state!=S_FAULT) $fatal(1,"%0s: cleared while request still high",name);
        fault_clear=0; run_request=0; @(negedge clk);
        fault_clear=1; wait(state==S_OFF); @(negedge clk); fault_clear=0;
        if (fault_latched) $fatal(1,"%0s: still latched after clear",name);
        expect_safe;
    end endtask

    initial begin
        repeat(5) @(negedge clk); reset_n=1;
        expect_safe;
        // 1) Normal bring-up and request drop
        bring_up; run_request=0; wait(state==S_OFF); expect_safe;
        // 1b) Soft reset while running (region clock switch): /RESET held,
        //     cartridge power and interface rail must stay on throughout, and
        //     the machine stays in RUN (a flashcart keeps its loaded game).
        bring_up; hold_reset=1;
        repeat(50) begin @(negedge clk);
            if (!cart_5v_enable || !iface_rail_enable) $fatal(1,"soft reset removed cartridge power");
            if (state!=S_RUN) $fatal(1,"soft reset left RUN (state %0d)",state);
        end
        if (!cart_reset_pull) $fatal(1,"soft reset did not hold cartridge /RESET");
        hold_reset=0; repeat(3) @(negedge clk);
        if (cart_reset_pull || !cart_5v_enable) $fatal(1,"soft reset did not release cleanly");
        run_request=0; wait(state==S_OFF); expect_safe;
        // 2) Host reset during RUN -> immediate permit loss and shutdown
        bring_up; host_reset_n=0; @(negedge clk); if (bus_permit) $fatal(1,"permit survived host reset");
        wait(state==S_OFF); run_request=0; expect_safe; host_reset_n=1;
        // 3) Fault classes: each drops permit on the next clock and latches
        bring_up; efuse_fault_n=0; @(negedge clk); if (bus_permit) $fatal(1,"permit survived eFuse fault");
        efuse_fault_n=1; clear_fault(8'h40, "eFuse");
        bring_up; overtemp=1; @(negedge clk); if (bus_permit) $fatal(1,"permit survived overtemp");
        overtemp=0; clear_fault(8'h80, "overtemp");
        bring_up; configured=0; @(negedge clk); if (bus_permit) $fatal(1,"permit survived configuration loss");
        configured=1; clear_fault(8'h02, "configuration");
        bring_up; rail_5v_dead=1; repeat(2) @(negedge clk); if (bus_permit) $fatal(1,"permit survived 5 V loss");
        rail_5v_dead=0; clear_fault(8'h18, "5V loss");      // 5 V trip and/or interface-rail trip (rail collapses with it)
        // 4) Rail timeout: 5 V never valid during bring-up -> code 0x08
        rail_5v_dead=1; run_request=1; wait(state==S_FAULT); @(negedge clk);
        if (fault_code!==8'h08) $fatal(1,"rail timeout code wrong: %h",fault_code);
        rail_5v_dead=0; clear_fault(8'h08, "rail timeout");
        // 5) Cartridge check
        check_tests;
        $display("PASS: power sequencer bring-up order, soft reset keeps cartridge power, request/host-reset shutdown, 4 fault classes trip and latch, clear refused while requested, rail timeout; cartridge check: two consecutive readings to pass, enforce faults 0x01 without 5 V, report-only starts anyway, check-only never powers, off skips it, abort and hardware fault during the check (%0d clocks)", cycles);
        $finish;
    end
endmodule
