`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Behavioural Si5351A I2C slave (address 0x60) for sn64_clock_init: records
// every register write, ACKs its address, returns status register 0 with
// SYS_INIT set for the first few reads.
//
// Checks:
//  - the start-up register image against docs/design/clock-plan.md (PLLA,
//    PLLB, MS0, MS1, crystal load), PLL reset, CLK0/CLK1 control, CLK2 left
//    powered down with its output disabled (no pixel clock: the picture goes
//    to the console over the cartridge bus), lock polling and clocks_ready;
//  - the region latch follows detection/override only while the SNES clock is
//    stopped, and a change made while it runs is reported as pending and
//    applied at the next stopped window;
//  - nothing is ever written after start-up (no I2C START after clocks_ready,
//    whether the SNES clock is stopped or running).
// Negative run: +wrong_addr (the slave never ACKs: must end in i2c_error).
module tb_clock_init;
    reg clk=0; always #20 clk=~clk;               // 25 MHz housekeeping clock
    reg reset_n=0;
    wire scl_oe, sda_oe; reg slave_sda_low=0;
    wire scl = scl_oe ? 1'b0 : 1'b1;               // open-drain bus with pull-ups
    wire sda = (sda_oe || slave_sda_low) ? 1'b0 : 1'b1;
    reg [1:0] region_mode=0; reg detected_valid=0, detected_pal=0, snes_clock_stopped=1;
    wire region_pal, pending, clocks_ready, i2c_error;

    sn64_clock_init #(.CLK_HZ(25_000_000), .I2C_HZ(400_000)) dut (
        .clk(clk), .reset_n(reset_n), .scl_oe(scl_oe), .sda_oe(sda_oe), .sda_in(sda),
        .region_mode(region_mode), .detected_valid(detected_valid), .detected_pal(detected_pal),
        .snes_clock_stopped(snes_clock_stopped), .region_pal(region_pal), .region_change_pending(pending),
        .clocks_ready(clocks_ready), .i2c_error(i2c_error));

    // ---------------- I2C slave model ----------------
    reg [7:0] regs [0:255];
    reg written [0:255];                          // two-state simulators cannot use 8'hxx as "never written"
    integer status_reads=0, writes=0;
    reg wrong_addr=0;
    reg [7:0] shift; integer bitc; reg addressed, is_read, have_reg; reg [7:0] reg_ptr, tx;
    reg in_frame=0;
    // Post-start-up bookkeeping
    reg seen_ready=0;
    integer n_post=0, starts_post=0, writes_177=0;
    always @(posedge clocks_ready) seen_ready = 1;
    // START / STOP detection
    always @(negedge sda) if (scl) begin
        in_frame=1; bitc=0; addressed=0; have_reg=0; slave_sda_low=0;
        if (seen_ready) begin
            starts_post = starts_post + 1;
            if (starts_post <= 3) $display("ERROR: Si5351 accessed after start-up (I2C START at %0d ns)", $time);
        end
    end
    always @(posedge sda) if (scl) begin in_frame=0; slave_sda_low=0; end
    // Receive on SCL rising, drive ACK / data after SCL falls
    reg ack_phase=0, send_phase=0;
    always @(posedge scl) if (in_frame) begin
        if (send_phase) begin
            bitc = bitc + 1;
            if (bitc==9) begin send_phase=0; bitc=0; end   // master ACK/NACK bit
        end else if (!ack_phase) begin
            shift = {shift[6:0], sda}; bitc = bitc + 1;
        end
    end
    always @(negedge scl) if (in_frame) begin
        if (ack_phase) begin
            slave_sda_low = 0; ack_phase = 0; bitc = 0;
            if (is_read && addressed) begin send_phase=1; tx = (status_reads<4) ? 8'h80 : 8'h00; status_reads=status_reads+1; slave_sda_low = !tx[7]; end
        end else if (send_phase) begin
            if (bitc < 8) slave_sda_low = !tx[7-bitc]; else slave_sda_low = 0;
        end else if (bitc==8) begin
            // byte complete: decide ACK
            if (!addressed) begin
                if (shift[7:1]==7'h60 && !wrong_addr) begin addressed=1; is_read=shift[0]; slave_sda_low=1; ack_phase=1; end
            end else if (!have_reg) begin reg_ptr=shift; have_reg=1; slave_sda_low=1; ack_phase=1; end
            else begin
                regs[reg_ptr]=shift; written[reg_ptr]=1; writes=writes+1;
                if (reg_ptr == 8'd177) writes_177 = writes_177 + 1;
                if (seen_ready) n_post = n_post + 1;
                reg_ptr=reg_ptr+1; slave_sda_low=1; ack_phase=1;
            end
        end
    end

    // ---------------- Checks ----------------
    integer errors=0;
    task automatic fail(input string msg); begin errors++; $display("ERROR: %s", msg); end endtask
    task check_reg(input [7:0] r, input [7:0] v); if (regs[r]!==v) $fatal(1,"register %0d = %h, expected %h", r, regs[r], v); endtask
    integer cycles=0; always @(negedge clk) begin cycles=cycles+1; if (cycles>6_000_000) $fatal(1,"timeout: ready=%b err=%b state=%0d", clocks_ready, i2c_error, dut.q); end

    // AN619: divider = (P1 + 512)/128 + P2/(128*P3) = ((P1 + 512)*P3 + P2) / (128*P3)
    task automatic ms_decode(input [7:0] base, output longint num, output longint den);
        longint p1, p2, p3;
        p3 = {regs[base+5][7:4], regs[base], regs[base+1]};
        p1 = {regs[base+2][1:0], regs[base+3], regs[base+4]};
        p2 = {regs[base+5][3:0], regs[base+6], regs[base+7]};
        num = (p1 + 512) * p3 + p2;
        den = 128 * p3;
    endtask
    // Decode a master clock from its PLL and MultiSynth registers and report it.
    task automatic report_master(input bit pal_region);
        longint mn, md, pl1, pl2, pl3;
        real fpll, fm;
        reg [7:0] pll_base, ctrl;
        ctrl = pal_region ? regs[17] : regs[16];
        ms_decode(pal_region ? 8'd50 : 8'd42, mn, md);      // MS1 (PAL master) or MS0 (NTSC master)
        pll_base = ctrl[5] ? 8'd34 : 8'd26;
        pl3 = {regs[pll_base+5][7:4], regs[pll_base], regs[pll_base+1]};
        pl1 = {regs[pll_base+2][1:0], regs[pll_base+3], regs[pll_base+4]};
        pl2 = {regs[pll_base+5][3:0], regs[pll_base+6], regs[pll_base+7]};
        fpll = 25.0e6 * ($itor(pl1 + 512) + $itor(pl2) / $itor(pl3)) / 128.0;
        fm = fpll * $itor(md) / $itor(mn);
        $display("  %s: PLL%s %.4f MHz, master %.6f MHz", pal_region ? "PAL " : "NTSC", ctrl[5] ? "B" : "A", fpll / 1e6, fm / 1e6);
    endtask

    integer n_before;
    initial begin
        wrong_addr = $test$plusargs("wrong_addr");
        for (integer i=0;i<256;i=i+1) begin regs[i]=8'hxx; written[i]=0; end
        repeat(5) @(negedge clk); reset_n=1;
        if (wrong_addr) begin
            wait(i2c_error); if (clocks_ready) $fatal(1,"ready despite NACK");
            $display("FAIL-EXPECTED: master reported i2c_error on NACK"); $fatal(1,"wrong-address run ends in error as intended");
        end
        wait(clocks_ready || i2c_error);
        if (i2c_error) $fatal(1,"unexpected i2c_error");
        // ---- start-up image ----
        // PLLA 859.0909 MHz (P1=3886 P2=6 P3=11)
        check_reg(26,8'h00); check_reg(27,8'h0B); check_reg(28,8'h00); check_reg(29,8'h0F);
        check_reg(30,8'h2E); check_reg(31,8'h00); check_reg(32,8'h00); check_reg(33,8'h06);
        // PLLB 851.2548 MHz (P1=3846 P2=26536 P3=62500)
        check_reg(34,8'hF4); check_reg(35,8'h24); check_reg(36,8'h00); check_reg(37,8'h0F);
        check_reg(38,8'h06); check_reg(39,8'h00); check_reg(40,8'h67); check_reg(41,8'hA8);
        // MS0 / MS1 divide by 40
        check_reg(45,8'h12); check_reg(43,8'h01); check_reg(53,8'h12); check_reg(51,8'h01);
        // MS2 never written (no pixel clock)
        for (integer r = 58; r <= 65; r++) if (written[r]) fail($sformatf("MultiSynth 2 register %0d written (%h): no pixel clock exists", r, regs[r]));
        check_reg(183,8'hD2); check_reg(177,8'hA0); check_reg(16,8'h4F); check_reg(17,8'h6F);
        check_reg(18,8'h80);                         // CLK2 powered down
        check_reg(3,8'hFC);                          // outputs 0 and 1 enabled, 2-7 disabled
        if (writes_177 != 1) fail($sformatf("PLL reset written %0d times (start-up only)", writes_177));
        if (status_reads<5) $fatal(1,"did not wait for PLL lock (reads=%0d)",status_reads);
        report_master(1'b0); report_master(1'b1);
        repeat(3) @(negedge clk);
        if (region_pal) fail("region not NTSC after reset");

        // ---- PAL detected while the SNES clock is stopped ----
        detected_valid=1; detected_pal=1;
        repeat(3) @(negedge clk);
        if (!region_pal) $fatal(1,"detected PAL not applied while clock stopped");
        if (pending) fail("pending reported after the region was latched");

        // ---- SNES clock runs (started only once ready): nothing may be written, region frozen ----
        snes_clock_stopped=0;
        detected_pal=0; region_mode=2'd1; n_before = n_post;
        repeat(200_000) @(negedge clk);                 // 8 ms
        if (!region_pal) $fatal(1,"region changed while the SNES clock was running");
        if (!pending) $fatal(1,"pending change not reported");
        if (n_post != n_before) fail("Si5351 register written while the SNES clock runs");

        // ---- next power-up window: forced NTSC is applied ----
        snes_clock_stopped=1; repeat(3) @(negedge clk);
        if (region_pal) $fatal(1,"forced NTSC not applied at next power-up");
        if (pending) fail("pending reported after the forced region was latched");
        region_mode=2'd2; repeat(3) @(negedge clk);
        if (!region_pal) $fatal(1,"forced PAL not applied while clock stopped");
        repeat(50_000) @(negedge clk);                  // 2 ms: still nothing on the bus
        if (n_post != 0) fail($sformatf("%0d registers written after start-up (none allowed)", n_post));
        if (starts_post != 0) fail($sformatf("%0d I2C transactions started after start-up", starts_post));

        if (errors == 0)
            $display("PASS: Si5351 image (PLLA/PLLB/MS0/MS1/control, CLK2 off) written and verified, lock polled (%0d status reads), region latched only while SNES clock stopped (NTSC->PAL->NTSC->PAL), 0 writes after start-up (%0d writes, 1 PLL reset, %0d clocks)",
                     status_reads, writes, cycles);
        else begin
            $display("FAIL: clock-init %0d errors", errors);
            $fatal(1, "clock-init checks failed");
        end
        $finish;
    end
endmodule
