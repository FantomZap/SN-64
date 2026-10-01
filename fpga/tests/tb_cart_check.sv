`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Cartridge check, end to end (docs/design/reversed-cartridge-detection.md):
// sn64_rail_monitor and sn64_power_sequencer against
//   * a TLA2528 model: I2C single-register writes, manual-mode conversions, and channel 3
//     as a push-pull output (PIN_CFG, GPIO_CFG, GPO_DRIVE_CFG, GPO_VALUE; TI SBAS961A);
//   * an electrical model of the cartridge rail SNES_5V_CART as built in hardware/sn64-v2:
//     the 20k/10k divider the ADC reads (R30/R31), the 4.7k /RESET pull-up (R207), the
//     TPS2553 switch with its current limit and fault flag (SLVS841F: 1.04 A with 24.9k,
//     fault after 7.5 ms in limit), the board's rail capacitors, and a cartridge that is
//     absent, the right way round, back to front, or shorted.
// Model assumptions (none of this is measured): a cartridge the right way round draws
// nothing below 0.8 V and then behaves as 150 ohm; back to front it is one silicon junction
// (Is 5 pA, n 1.05) behind 2 ohm; a short is 1 ohm; the switch is a current source of its
// limit that stops at 5 V. The capacitances are one fortieth of the board's (54.4 uF board,
// 22 uF cartridge) so the run is forty times shorter; currents, voltages and resistances
// are the real ones, and the sequencer's check timeout is scaled the same way (100 ms here
// for 4 s on the board). +define+SN64_CHECK_REAL_SCALE builds the same test with the real
// capacitances and the real 4 s timeout (several minutes of run time; not in the suite).
//
// Checked: an empty socket and a good cartridge pass and start; a reversed cartridge and a
// short latch fault 0x01 in enforce mode with the switch never closed and at most 0.2 mA
// through the cartridge; check-only never powers anything; report-only records the failure
// and then shows what the check prevents (the switch in current limit until its fault flag
// trips); the pin stops driving after an FPGA reset in mid-check and after the ADC stops
// answering; the monitor never converts channel 3 while it drives, and the test current and
// the switch are never on together.
// Fault injection: +define+SN64_FAULT_CHECK_IGNORED (sequencer does not enforce) and
// +keep_reset (/RESET stays pulled during the check) must both make this test fail.
module tb_cart_check;
    reg clk = 0; always #18.518 clk = ~clk;            // 27 MHz
    reg rst_n = 0;

    // ---------------- I2C bus (open drain, pulled up) ----------------
    wire scl_oe, sda_oe;
    reg  slave_sda_oe = 0;
    wire scl = ~scl_oe;
    wire sda = ~(sda_oe | slave_sda_oe);

    // ---------------- devices under test ----------------
    wire host_3v3_ok, sys_5v_ok, cart_5v_ok, core_1v1_ok, overtemp, mon_error;
    wire [127:0] codes;
    wire probe_req, probe_active, probe_strobe; wire [11:0] probe_code;
    sn64_rail_monitor #(.CLK_HZ(27_000_000)) monitor (
        .clk(clk), .rst_n(rst_n), .scl_oe(scl_oe), .sda_oe(sda_oe), .sda_in(sda),
        .host_3v3_ok(host_3v3_ok), .sys_5v_ok(sys_5v_ok), .cart_5v_ok(cart_5v_ok), .core_1v1_ok(core_1v1_ok),
        .overtemp(overtemp), .error(mon_error), .codes(codes),
        .probe_req(probe_req), .probe_active(probe_active), .probe_strobe(probe_strobe), .probe_code(probe_code));

    reg run_request = 0; reg [1:0] probe_mode = 2'd0;
    reg efuse_fault_n = 1;
    wire cart_5v_enable, seq_reset_pull, bus_permit, fault_latched, probe_done, probe_pass;
    wire [3:0] state; wire [7:0] fault_code, probe_level; wire [1:0] probe_mode_q;
`ifdef SN64_CHECK_REAL_SCALE
    localparam real SCALE = 1.0;  localparam integer CHECK_TIMEOUT_MS = 4000;
`else
    localparam real SCALE = 40.0; localparam integer CHECK_TIMEOUT_MS = 100;
`endif
    sn64_power_sequencer #(.CLK_HZ(27_000_000), .RESET_HOLD_MS(1), .RAIL_TIMEOUT_MS(50),
                           .PROBE_ENABLE(1), .PROBE_TIMEOUT_MS(CHECK_TIMEOUT_MS), .PROBE_OK_CODE(12'd269)) sequencer (
        .clk(clk), .reset_n(rst_n),
        .configured(1'b1), .host_3v3_ok(host_3v3_ok), .fpga_rails_ok(core_1v1_ok & sys_5v_ok),
        .cart_5v_ok(cart_5v_ok), .iface_rail_ok(1'b1), .efuse_fault_n(efuse_fault_n),
        .overtemp(overtemp), .host_reset_n(1'b1),
        .run_request(run_request), .fault_clear(!run_request), .release_ok(1'b1), .hold_reset(1'b0),
        .probe_mode(probe_mode), .probe_req(probe_req), .probe_active(probe_active),
        .probe_strobe(probe_strobe), .probe_code(probe_code),
        .probe_done(probe_done), .probe_pass(probe_pass), .probe_mode_q(probe_mode_q), .probe_level(probe_level),
        .cart_5v_enable(cart_5v_enable), .iface_rail_enable(), .cart_reset_pull(seq_reset_pull),
        .bus_permit(bus_permit), .fault_latched(fault_latched), .state(state), .fault_code(fault_code));
    localparam S_OFF=0, S_RUN=4, S_FAULT=6, S_PROBE=7, S_PROBE_HOLD=9;
    localparam [1:0] M_ENFORCE=2'd0, M_REPORT=2'd1, M_CHECK=2'd3;
    // The socket's /RESET pull as sn64_top forms it; +keep_reset models the regression
    // "reset not released during the check".
    reg keep_reset = 0;
    wire reset_pulled = keep_reset | seq_reset_pull | (!bus_permit & !probe_req);

    // ---------------- TLA2528 model ----------------
    reg [7:0] r_pin_cfg = 0, r_gpio_cfg = 0, r_gpo_drive = 0, r_gpo_value = 0, r_chan = 0;
    reg       slave_present = 1;               // 0: the ADC does not answer
    wire pin3_hi = r_pin_cfg[3] & r_gpio_cfg[3] & r_gpo_drive[3] & r_gpo_value[3];
    wire pin3_lo = r_pin_cfg[3] & r_gpio_cfg[3] & ~r_gpo_value[3];
    wire pin3_driving = pin3_hi | pin3_lo;
    real v_rail = 0.0;                         // SNES_5V_CART
    localparam real AVDD = 3.3, R30 = 20.0e3, R31 = 10.0e3, R207 = 4.7e3;
    function automatic [11:0] convert(input [2:0] ch);
        real v; integer c;
        begin
            case (ch)
                3'd0: v = 3.3 / 2.0;                               // HOST_3V3 / 2
                3'd2: v = 5.0 / 3.0;                               // 5V_SYS / 3
                3'd3: v = pin3_hi ? AVDD : pin3_lo ? 0.0 : v_rail * R31 / (R30 + R31);
                3'd4: v = 1.1;                                     // FPGA_1V1
                3'd5: v = 1.65;                                    // NTC at 25 C
                default: v = 0.0;                                  // VBUS, CC1, CC2: nothing attached
            endcase
            c = $rtoi(v / AVDD * 4096.0);
            if (c > 4095) c = 4095; if (c < 0) c = 0;
            convert = c[11:0];
        end
    endfunction
    reg        started = 0, addressed = 0, reading = 0, master_nack = 0, conv_while_driving = 0;
    integer    bc = 0, nbyte = 0;
    reg [7:0]  sh = 0, opcode = 0, regaddr = 0;
    reg [15:0] conv = 0;
    always @(negedge sda) if (scl) begin       // START
        started = 1; bc = 0; nbyte = 0; addressed = 0; reading = 0; master_nack = 0; slave_sda_oe <= 1'b0;
    end
    always @(posedge sda) if (scl) begin       // STOP
        started = 0; slave_sda_oe <= 1'b0;
    end
    always @(posedge scl) if (started) begin
        if (bc < 8) begin
            if (!(addressed && reading && nbyte > 0)) sh = {sh[6:0], sda};
            bc = bc + 1;
        end else begin
            if (addressed && reading && nbyte > 0) master_nack = sda;
            bc = 9;
        end
    end
    always @(negedge scl) if (started) begin
        if (bc == 8) begin                     // a byte is complete: acknowledge phase
            if (addressed && reading && nbyte > 0) slave_sda_oe <= 1'b0;      // the master acknowledges our data
            else begin
                if (nbyte == 0) begin
                    addressed = slave_present && (sh[7:1] == 7'h10);
                    reading = sh[0];
                    if (addressed && reading) begin
                        if (r_chan[2:0] == 3'd3 && pin3_driving) conv_while_driving = 1;
                        conv = {convert(r_chan[2:0]), 4'b0000};
                    end
                end else if (addressed) begin
                    case (nbyte)
                        1: opcode = sh;
                        2: regaddr = sh;
                        3: if (opcode == 8'h08) case (regaddr)
                               8'h05: r_pin_cfg = sh;
                               8'h07: r_gpio_cfg = sh;
                               8'h09: r_gpo_drive = sh;
                               8'h0B: r_gpo_value = sh;
                               8'h11: r_chan = sh;
                               default: ;
                           endcase
                        default: ;
                    endcase
                end
                slave_sda_oe <= addressed;
            end
        end else if (bc == 9) begin            // acknowledge clock done
            bc = 0; nbyte = nbyte + 1;
            if (addressed && reading && !master_nack) begin slave_sda_oe <= ~conv[15]; conv = {conv[14:0], 1'b1}; end
            else slave_sda_oe <= 1'b0;
        end else if (addressed && reading && nbyte > 0) begin
            slave_sda_oe <= ~conv[15]; conv = {conv[14:0], 1'b1};
        end
    end

    // ---------------- cartridge rail, 1 us steps ----------------
    localparam real DT = 1.0e-6;
    localparam real C_BOARD = 54.4e-6 / SCALE, C_CART = 22.0e-6 / SCALE;
    localparam real V5 = 5.0, I_LIM = 1.036;                        // switch: its current limit until the rail is at 5 V
    localparam real VON = 0.8, R_GOOD = 150.0;                      // cartridge the right way round
    localparam real IS = 5.0e-12, NVT = 1.05 * 0.02585, RS = 2.0;   // cartridge back to front
    localparam real R_SHORT = 1.0;
    integer cart_kind = 0;                     // 0 none, 1 right way round, 2 back to front, 3 shorted
    reg     discharge = 0;                     // test helper: empty the rail capacitors
    real    i_div, i_rst, i_sw, i_cart = 0.0, i_d = 0.0, g, c_tot;
    real    v_peak = 0.0, i_rev_peak = 0.0;
    integer lim_us = 0, off_us = 0, k;
    always #1000 begin
        i_div = pin3_hi ? (AVDD - v_rail) / R30 : pin3_lo ? -v_rail / R30 : -v_rail / (R30 + R31);
        i_rst = reset_pulled ? -v_rail / R207 : 0.0;
        i_sw = (cart_5v_enable && v_rail < V5) ? I_LIM : 0.0;
        case (cart_kind)
            1: i_cart = (v_rail > VON) ? (v_rail - VON) / R_GOOD : 0.0;
            2: begin                           // v = n Vt ln(i/Is + 1) + i Rs, solved for i
                if (i_d < 1.0e-13) i_d = 1.0e-13;
                for (k = 0; k < 12; k = k + 1) begin
                    g = NVT * $ln(i_d / IS + 1.0) + i_d * RS - v_rail;
                    i_d = i_d - g / (NVT / (i_d + IS) + RS);
                    if (i_d < 0.0) i_d = 0.0;
                end
                i_cart = i_d;
            end
            3: i_cart = v_rail / R_SHORT;
            default: i_cart = 0.0;
        endcase
        c_tot = C_BOARD + ((cart_kind == 1 || cart_kind == 2) ? C_CART : 0.0);
        v_rail = v_rail + (i_div + i_rst + i_sw - i_cart) * DT / c_tot;
        if (v_rail < 0.0 || discharge) v_rail = 0.0;
        if (cart_5v_enable && v_rail > V5) v_rail = V5;
        if (v_rail > v_peak) v_peak = v_rail;
        if (cart_kind == 2 && i_cart > i_rev_peak) i_rev_peak = i_cart;
        // TPS2553 fault flag: asserted after 7.5 ms in current limit, released 7.5 ms after the switch is off
        lim_us = (cart_5v_enable && v_rail < V5 - 0.25) ? lim_us + 1 : 0;      // cannot reach 5 V: in current limit
        off_us = cart_5v_enable ? 0 : off_us + 1;
        if (lim_us >= 7500) efuse_fault_n <= 1'b0;
        else if (off_us >= 7500) efuse_fault_n <= 1'b1;
    end

    // ---------------- invariants ----------------
    reg forbid_5v = 0;
    always @(negedge clk) begin
        if (cart_5v_enable && pin3_driving) $fatal(1, "test current and the 5 V switch on together");
        if (forbid_5v && cart_5v_enable) $fatal(1, "5 V switched on into a cartridge the check must protect (state %0d)", state);
        if (conv_while_driving) $fatal(1, "channel 3 converted while it was driving");
        if (bus_permit && state != S_RUN) $fatal(1, "bus_permit outside RUN");
    end
    initial begin
        #(1.0e9 * (0.5 + 10.0 * CHECK_TIMEOUT_MS / 1000.0));
        $fatal(1, "cartridge check test timed out (state %0d, rail %0.3f V)", state, v_rail);
    end

    // ---------------- test sequence ----------------
    real t0, t_none, t_good, t_again, t_exposed, v_none, v_good, v_rev, v_short, i_rev, i_exposed;
    integer lvl_none, lvl_good, lvl_rev, lvl_short;
    task automatic request(input [1:0] mode); begin
        @(negedge clk); probe_mode = mode; run_request = 1; t0 = $realtime;
    end endtask
    task automatic drop; begin
        @(negedge clk); run_request = 0; wait (state == S_OFF); wait (!probe_active); repeat (4) @(negedge clk); forbid_5v = 0;
        if (fault_latched) $fatal(1, "fault still latched after the request dropped");
        wait (efuse_fault_n);
    end endtask
    task automatic fit(input integer kind); begin       // put a cartridge in (or take it out) with the rail empty
        cart_kind = kind; i_d = 0.0; discharge = 1; #5000; discharge = 0; #5000; v_peak = 0.0; i_rev_peak = 0.0;
    end endtask
    initial begin
        if ($test$plusargs("keep_reset")) keep_reset = 1;
        repeat (20) @(negedge clk); rst_n = 1;
        wait (!mon_error && host_3v3_ok && sys_5v_ok && core_1v1_ok); repeat (4) @(negedge clk);
        if (pin3_driving || r_pin_cfg != 8'h00) $fatal(1, "pin not analog after start-up");

        // A) empty socket: the rail rises, the check passes, 5 V comes up
        fit(0); request(M_ENFORCE); wait (state == S_PROBE); wait (state != S_PROBE);
        if (state == S_FAULT) $fatal(1, "empty socket failed the check (rail reached %0.3f V)", v_peak);
        t_none = ($realtime - t0) / 1.0e6; v_none = v_rail; lvl_none = probe_level;
        wait (state == S_RUN); repeat (4) @(negedge clk);
        if (!bus_permit || !cart_5v_ok || v_rail < 4.6) $fatal(1, "A: did not run (rail %0.3f V)", v_rail);
        if (!probe_done || !probe_pass) $fatal(1, "A: result not recorded");
        drop;
        // A2) asked again at once: the rail still holds charge and passes on the first two readings
        if (v_rail < 1.0) $fatal(1, "A2: the rail emptied faster than the model says (%0.3f V)", v_rail);
        request(M_ENFORCE); wait (state == S_RUN); t_again = ($realtime - t0) / 1.0e6; drop;

        // B) cartridge the right way round
        fit(1); request(M_ENFORCE); wait (state == S_PROBE); wait (state != S_PROBE);
        if (state == S_FAULT) $fatal(1, "good cartridge failed the check (rail reached %0.3f V)", v_peak);
        t_good = ($realtime - t0) / 1.0e6; v_good = v_rail; lvl_good = probe_level;
        wait (state == S_RUN); repeat (4) @(negedge clk);
        if (!bus_permit || !cart_5v_ok || v_rail < 4.6) $fatal(1, "B: did not run (rail %0.3f V)", v_rail);
        drop;

        // C) cartridge back to front, enforce: fault 0x01, the switch never closes
        fit(2); forbid_5v = 1; request(M_ENFORCE); wait (state == S_FAULT); repeat (4) @(negedge clk);
        if (fault_code !== 8'h01 || !probe_done || probe_pass) $fatal(1, "C: no check fault (code %h done %b pass %b)", fault_code, probe_done, probe_pass);
        v_rev = v_peak; i_rev = i_rev_peak; lvl_rev = probe_level;
        if (i_rev_peak > 0.2e-3) $fatal(1, "C: %0.3f mA went backwards through the cartridge", i_rev_peak * 1.0e3);
        if (v_peak > 0.6) $fatal(1, "C: rail reached %0.3f V on a reversed cartridge", v_peak);
        #2_000_000; if (pin3_driving) $fatal(1, "C: test current left on after the fault");
        drop;
        if (!probe_done || probe_pass) $fatal(1, "C: result lost when the request dropped");

        // D) back to front, check only: failed result, no fault, nothing powered
        fit(2); forbid_5v = 1; request(M_CHECK); wait (state == S_PROBE_HOLD); repeat (4) @(negedge clk);
        if (fault_latched || !probe_done || probe_pass) $fatal(1, "D: check-only result wrong");
        if (i_rev_peak > 0.2e-3) $fatal(1, "D: %0.3f mA went backwards through the cartridge", i_rev_peak * 1.0e3);
        drop;
        // E) right way round, check only: passes, nothing powered
        fit(1); forbid_5v = 1; request(M_CHECK); wait (state == S_PROBE_HOLD); #5_000_000;
        if (state != S_PROBE_HOLD || fault_latched || !probe_done || !probe_pass) $fatal(1, "E: check-only result wrong");
        if (v_peak > 3.4) $fatal(1, "E: rail reached %0.3f V in check-only mode", v_peak);
        drop;

        // F) shorted rail: fault 0x01
        fit(3); forbid_5v = 1; request(M_ENFORCE); wait (state == S_FAULT); repeat (4) @(negedge clk);
        if (fault_code !== 8'h01) $fatal(1, "F: short gave code %h", fault_code);
        v_short = v_peak; lvl_short = probe_level;
        drop;

        // G) back to front in report-only mode: the failure is recorded, then 5 V is applied anyway.
        //    This is what the check prevents: the switch sits in current limit until its fault flag trips.
        fit(2); request(M_REPORT); wait (cart_5v_enable); t0 = $realtime;
        if (!probe_done || probe_pass) $fatal(1, "G: report-only did not record the failed check");
        wait (state == S_FAULT); t_exposed = ($realtime - t0) / 1.0e6; i_exposed = i_rev_peak;
        repeat (4) @(negedge clk);
        if (fault_code !== 8'h40) $fatal(1, "G: expected the switch fault flag, got code %h", fault_code);
        if (i_exposed < 0.9) $fatal(1, "G: model did not reach the current limit (%0.3f A)", i_exposed);
        drop;

        // H) FPGA reset in the middle of a check: the ADC keeps its registers, so the first thing the
        //    monitor does afterwards must be to make the pin an analog input again
        fit(1); request(M_ENFORCE); wait (pin3_hi); #3_000_000;
        rst_n = 0; run_request = 0; repeat (20) @(negedge clk);
        if (!pin3_hi) $fatal(1, "H: model lost the pin setting on an FPGA reset");
        rst_n = 1; #2_000_000;
        if (pin3_driving) $fatal(1, "H: pin still driving 2 ms after the reset");
        wait (!mon_error && sys_5v_ok && core_1v1_ok); repeat (4) @(negedge clk);

        // I) the ADC stops answering during a check: the sequencer trips on the missing rail readings,
        //    and the pin is made analog as soon as the ADC answers again; then a normal start works
        fit(1); forbid_5v = 1; request(M_ENFORCE); wait (pin3_hi); #3_000_000;
        slave_present = 0; wait (state == S_FAULT); repeat (4) @(negedge clk);
        if ((fault_code & 8'h0C) == 8'h00) $fatal(1, "I: silent ADC gave code %h", fault_code);
        if (!pin3_hi) $fatal(1, "I: model lost the pin setting");
        slave_present = 1; wait (!mon_error); repeat (4) @(negedge clk);
        if (pin3_driving) $fatal(1, "I: pin still driving after the ADC answered again");
        drop;
        fit(1); request(M_ENFORCE); wait (state == S_RUN); repeat (4) @(negedge clk);
        if (!bus_permit) $fatal(1, "I: no start after recovery");
        drop;

        $display("PASS: cartridge check (model, capacitances /%0d): empty socket passes in %0.1f ms at %0.2f V (level %0d), again at once in %0.1f ms; good cartridge passes in %0.1f ms at %0.2f V (level %0d); reversed cartridge held at %0.2f V (level %0d), fault 0x01, switch never closed, %0.3f mA peak through the cartridge; short held at %0.3f V (level %0d), fault 0x01; check-only never powers; report-only then applies 5 V: %0.2f A for %0.1f ms until the switch fault trips; pin analog again after FPGA reset and after a silent ADC",
                 $rtoi(SCALE), t_none, v_none, lvl_none, t_again, t_good, v_good, lvl_good, v_rev, lvl_rev, i_rev * 1.0e3, v_short, lvl_short, i_exposed, t_exposed);
        $finish;
    end
endmodule
