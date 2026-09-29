`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Power-control state machine checks: ordered bring-up, permit only in RUN
// with every hardware condition true, request loss and host reset shut down,
// each fault class trips within one clock, latches, and needs an explicit
// clear with the request dropped. Uses shortened timing parameters.
module tb_power_sequencer;
    reg clk=0; always #23.28 clk=~clk;
    reg reset_n=0;
    reg configured=1, host_3v3_ok=1, fpga_rails_ok=1, efuse_fault_n=1, overtemp=0, host_reset_n=1;
    reg rail_5v_dead=0;                     // model a 5 V rail that never comes up
    reg cart_5v_ok=0, iface_rail_ok=0;
    reg run_request=0, fault_clear=0;
    wire cart_5v_enable, iface_rail_enable, cart_reset_pull, bus_permit, fault_latched;
    wire [3:0] state; wire [7:0] fault_code;

    sn64_power_sequencer #(.CLK_HZ(21_477_272), .RESET_HOLD_MS(1), .RAIL_TIMEOUT_MS(2)) dut (
        .clk(clk), .reset_n(reset_n),
        .configured(configured), .host_3v3_ok(host_3v3_ok), .fpga_rails_ok(fpga_rails_ok),
        .cart_5v_ok(cart_5v_ok), .iface_rail_ok(iface_rail_ok), .efuse_fault_n(efuse_fault_n),
        .overtemp(overtemp), .host_reset_n(host_reset_n),
        .run_request(run_request), .fault_clear(fault_clear),
        .cart_5v_enable(cart_5v_enable), .iface_rail_enable(iface_rail_enable), .cart_reset_pull(cart_reset_pull),
        .bus_permit(bus_permit), .fault_latched(fault_latched), .state(state), .fault_code(fault_code));

    // Rail models: valid a few clocks after enable, drop immediately when disabled.
    reg [2:0] ramp5=0, rampi=0;
    always @(posedge clk) begin
        ramp5 <= cart_5v_enable && !rail_5v_dead ? (ramp5==3'd7 ? ramp5 : ramp5+1) : 0;
        rampi <= iface_rail_enable && cart_5v_ok ? (rampi==3'd7 ? rampi : rampi+1) : 0;
        cart_5v_ok    <= (ramp5 >= 3'd4);
        iface_rail_ok <= (rampi >= 3'd4);
    end

    localparam S_OFF=0, S_RUN=4, S_FAULT=6;
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
        $display("PASS: power sequencer bring-up order, request/host-reset shutdown, 4 fault classes trip and latch, clear refused while requested, rail timeout (%0d clocks)", cycles);
        $finish;
    end
endmodule
