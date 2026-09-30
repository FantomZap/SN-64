`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Behavioural Si5351A I2C slave (address 0x60) for sn64_clock_init: records
// every register write, ACKs its address, returns status register 0 with
// SYS_INIT set for the first few reads.
//
// Checks:
//  - the start-up register image against docs/design/clock-plan.md, PLL reset,
//    output enables, lock polling and clocks_ready;
//  - the region latch follows detection/override only while the SNES clock is
//    stopped;
//  - per-region HDMI pixel clock: after start-up only MultiSynth 2 (58-65) and
//    CLK2 control (18) are ever written, only while the SNES clock is stopped
//    (no I2C START while it runs), and the resulting MS2 image, decoded with
//    the AN619 equations, gives pixel/master = 74932/59561 from PLLA (NTSC:
//    one 858 x 524 frame = 357,366 master clocks, the mean of the SNES's
//    357,368/357,364 frames) or 432/341 from PLLB (PAL, 2 x 864 pixels per
//    1364-clock SNES line);
//  - pixel_clock_ready is low from the moment a new region is latched until
//    CLK2 is reprogrammed, and stays high while the SNES clock runs;
//  - a sequence interrupted by a (misbehaving) SNES clock start stops at once
//    and is redone at the next stopped window.
// Negative runs: +wrong_addr (the slave never ACKs: must end in i2c_error) and
// the SN64_FAULT_CLK_IGNORE_STOP build (sequence keeps writing after the SNES
// clock starts: must fail with "Si5351 written while the SNES clock runs").
module tb_clock_init;
    reg clk=0; always #20 clk=~clk;               // 25 MHz housekeeping clock
    reg reset_n=0;
    wire scl_oe, sda_oe; reg slave_sda_low=0;
    wire scl = scl_oe ? 1'b0 : 1'b1;               // open-drain bus with pull-ups
    wire sda = (sda_oe || slave_sda_low) ? 1'b0 : 1'b1;
    reg [1:0] region_mode=0; reg detected_valid=0, detected_pal=0, snes_clock_stopped=1;
    wire region_pal, pending, clocks_ready, i2c_error, pixel_clock_ready, pixel_region_pal;

    sn64_clock_init #(.CLK_HZ(25_000_000), .I2C_HZ(400_000)) dut (
        .clk(clk), .reset_n(reset_n), .scl_oe(scl_oe), .sda_oe(sda_oe), .sda_in(sda),
        .region_mode(region_mode), .detected_valid(detected_valid), .detected_pal(detected_pal),
        .snes_clock_stopped(snes_clock_stopped), .region_pal(region_pal), .region_change_pending(pending),
        .clocks_ready(clocks_ready), .i2c_error(i2c_error),
        .pixel_clock_ready(pixel_clock_ready), .pixel_region_pal(pixel_region_pal));

    // ---------------- I2C slave model ----------------
    reg [7:0] regs [0:255];
    integer status_reads=0, writes=0;
    reg wrong_addr=0;
    reg [7:0] shift; integer bitc; reg addressed, is_read, have_reg; reg [7:0] reg_ptr, tx;
    reg in_frame=0;
    // Post-start-up bookkeeping
    reg seen_ready=0;
    integer n_post=0, starts_running=0, starts_post=0, writes_177=0;
    reg [7:0] post_reg [0:255];
    always @(posedge clocks_ready) seen_ready = 1;
    // START / STOP detection
    always @(negedge sda) if (scl) begin
        in_frame=1; bitc=0; addressed=0; have_reg=0; slave_sda_low=0;
        if (seen_ready) begin
            starts_post = starts_post + 1;
            if (!snes_clock_stopped) begin
                starts_running = starts_running + 1;
                if (starts_running <= 3) $display("ERROR: Si5351 written while the SNES clock runs (I2C START at %0d ns)", $time);
            end
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
                regs[reg_ptr]=shift; writes=writes+1;
                if (reg_ptr == 8'd177) writes_177 = writes_177 + 1;
                if (seen_ready) begin post_reg[n_post[7:0]] = reg_ptr; n_post = n_post + 1; end
                reg_ptr=reg_ptr+1; slave_sda_low=1; ack_phase=1;
            end
        end
    end

    // ---------------- Checks ----------------
    integer errors=0;
    task automatic fail(input string msg); begin errors++; $display("ERROR: %s", msg); end endtask
    task check_reg(input [7:0] r, input [7:0] v); if (regs[r]!==v) $fatal(1,"register %0d = %h, expected %h", r, regs[r], v); endtask
    integer cycles=0; always @(negedge clk) begin cycles=cycles+1; if (cycles>6_000_000) $fatal(1,"timeout: ready=%b err=%b state=%0d", clocks_ready, i2c_error, dut.q); end

    // Readiness must stay high while the SNES clock runs (well-behaved phases only).
    reg expect_ready_while_running=0;
    always @(negedge clk) if (expect_ready_while_running && !snes_clock_stopped && !pixel_clock_ready)
        begin fail("pixel_clock_ready dropped while the SNES clock runs"); expect_ready_while_running=0; end

    // AN619: divider = (P1 + 512)/128 + P2/(128*P3) = ((P1 + 512)*P3 + P2) / (128*P3)
    task automatic ms_decode(input [7:0] base, output longint num, output longint den);
        longint p1, p2, p3;
        p3 = {regs[base+5][7:4], regs[base], regs[base+1]};
        p1 = {regs[base+2][1:0], regs[base+3], regs[base+4]};
        p2 = {regs[base+5][3:0], regs[base+6], regs[base+7]};
        num = (p1 + 512) * p3 + p2;
        den = 128 * p3;
    endtask
    // Check that CLK2 is on the same PLL as the region's SNES master and that
    // f_pixel / f_master = rn / rd exactly.
    task automatic check_pixel_clock(input bit pal_region, input longint rn, input longint rd);
        longint mn, md, pn, pd;
        real fpll, fm, fp;
        longint pl1, pl2, pl3;
        reg [7:0] pll_base;
        ms_decode(pal_region ? 8'd50 : 8'd42, mn, md);      // MS1 (PAL master) or MS0 (NTSC master)
        ms_decode(8'd58, pn, pd);                             // MS2 (pixel)
        if (regs[18][5] !== (pal_region ? regs[17][5] : regs[16][5]))
            fail($sformatf("CLK2 source PLL%s differs from the %s master's PLL", regs[18][5] ? "B" : "A", pal_region ? "PAL" : "NTSC"));
        if (regs[18][7] !== 1'b0 || regs[18][3:2] !== 2'b11 || regs[18][6] !== 1'b0)
            fail($sformatf("CLK2 control %h: expected powered-up fractional MultiSynth 2 output", regs[18]));
        // f_p / f_m = D_master / D_pixel = (mn/md) / (pn/pd)
        if (mn * pd * rd != md * pn * rn)
            fail($sformatf("pixel/master ratio %0d*%0d/(%0d*%0d) is not %0d/%0d", mn, pd, md, pn, rn, rd));
        pll_base = regs[18][5] ? 8'd34 : 8'd26;
        pl3 = {regs[pll_base+5][7:4], regs[pll_base], regs[pll_base+1]};
        pl1 = {regs[pll_base+2][1:0], regs[pll_base+3], regs[pll_base+4]};
        pl2 = {regs[pll_base+5][3:0], regs[pll_base+6], regs[pll_base+7]};
        fpll = 25.0e6 * ($itor(pl1 + 512) + $itor(pl2) / $itor(pl3)) / 128.0;
        fm = fpll * $itor(md) / $itor(mn);
        fp = fpll * $itor(pd) / $itor(pn);
        $display("  %s: PLL%s %.4f MHz, master %.6f MHz, MS2 = %0d/%0d, pixel %.7f MHz (= master x %0d/%0d), %0.3f pixels per %0d-clock SNES line",
                 pal_region ? "PAL " : "NTSC", regs[18][5] ? "B" : "A", fpll / 1e6, fm / 1e6, pn, pd, fp / 1e6, rn, rd,
                 fp / fm * 1364.0, 1364);
    endtask
    task automatic check_post_regs(input string when);
        for (integer i = 0; i < n_post; i++)
            if (!(post_reg[i] == 8'd18 || (post_reg[i] >= 8'd58 && post_reg[i] <= 8'd65)))
                fail($sformatf("%s: register %0d written after start-up (only 18 and 58-65 allowed)", when, post_reg[i]));
        if (writes_177 != 1) fail($sformatf("PLL reset written %0d times (start-up only)", writes_177));
    endtask
    task automatic wait_ready(input string what);
        fork
            wait (pixel_clock_ready);
            begin repeat (400_000) @(negedge clk); end
        join_any
        disable fork;
        if (!pixel_clock_ready) $fatal(1, "%s: pixel_clock_ready never rose", what);
    endtask

    integer n_before;
    initial begin
        wrong_addr = $test$plusargs("wrong_addr");
        for (integer i=0;i<256;i=i+1) regs[i]=8'hxx;
        repeat(5) @(negedge clk); reset_n=1;
        if (wrong_addr) begin
            wait(i2c_error); if (clocks_ready) $fatal(1,"ready despite NACK");
            if (pixel_clock_ready) $fatal(1,"pixel clock ready despite NACK");
            $display("FAIL-EXPECTED: master reported i2c_error on NACK"); $fatal(1,"wrong-address run ends in error as intended");
        end
        wait(clocks_ready || i2c_error);
        if (i2c_error) $fatal(1,"unexpected i2c_error");
        // ---- start-up image (unchanged from the NTSC-only version) ----
        // PLLA 859.0909 MHz (P1=3886 P2=6 P3=11)
        check_reg(26,8'h00); check_reg(27,8'h0B); check_reg(28,8'h00); check_reg(29,8'h0F);
        check_reg(30,8'h2E); check_reg(31,8'h00); check_reg(32,8'h00); check_reg(33,8'h06);
        // PLLB 851.2548 MHz (P1=3846 P2=26536 P3=62500)
        check_reg(34,8'hF4); check_reg(35,8'h24); check_reg(36,8'h00); check_reg(37,8'h0F);
        check_reg(38,8'h06); check_reg(39,8'h00); check_reg(40,8'h67); check_reg(41,8'hA8);
        // MS0 / MS1 divide by 40
        check_reg(45,8'h12); check_reg(43,8'h01); check_reg(53,8'h12); check_reg(51,8'h01);
        // MS2 fractional 31+31/39 (HDMI pixel clock locked to the NTSC master)
        check_reg(58,8'h49); check_reg(59,8'h2D); check_reg(60,8'h00); check_reg(61,8'h0D);
        check_reg(62,8'hE5); check_reg(63,8'h00); check_reg(64,8'h34); check_reg(65,8'hBF);
        check_reg(183,8'hD2); check_reg(177,8'hA0); check_reg(16,8'h4F); check_reg(17,8'h6F); check_reg(18,8'h0F); check_reg(3,8'hF8);
        if (status_reads<5) $fatal(1,"did not wait for PLL lock (reads=%0d)",status_reads);
        repeat(3) @(negedge clk);
        if (!pixel_clock_ready || pixel_region_pal) fail("NTSC pixel clock not ready after start-up");
        check_pixel_clock(1'b0, 74932, 59561);

        // ---- PAL detected while the SNES clock is stopped ----
        detected_valid=1; detected_pal=1; #1;
        if (pixel_clock_ready) fail("pixel_clock_ready high while a region change is pending");
        repeat(3) @(negedge clk);
        if (!region_pal) $fatal(1,"detected PAL not applied while clock stopped");
        if (pixel_clock_ready) fail("pixel_clock_ready high before CLK2 was reprogrammed for PAL");
        wait_ready("NTSC->PAL");
        if (!pixel_region_pal) fail("pixel_region_pal not PAL after the PAL sequence");
        // PAL MS2 = 31 + 31/54: P1 = 3529 (0x0DC9), P2 = 26, P3 = 54; CLK2 from PLLB
        check_reg(58,8'h00); check_reg(59,8'h36); check_reg(60,8'h00); check_reg(61,8'h0D);
        check_reg(62,8'hC9); check_reg(63,8'h00); check_reg(64,8'h00); check_reg(65,8'h1A);
        check_reg(18,8'h2F);
        check_pixel_clock(1'b1, 432, 341);
        if (n_post != 9) fail($sformatf("%0d writes for the PAL pixel clock, expected 9", n_post));
        check_post_regs("NTSC->PAL");

        // ---- SNES clock runs (started only once ready): nothing may be written ----
        snes_clock_stopped=0; expect_ready_while_running=1;
        detected_pal=0; region_mode=2'd1; n_before = n_post;
        repeat(200_000) @(negedge clk);                 // 8 ms
        if (!region_pal) $fatal(1,"region changed while the SNES clock was running");
        if (!pending) $fatal(1,"pending change not reported");
        if (n_post != n_before) fail("Si5351 register written while the SNES clock runs");
        expect_ready_while_running=0;

        // ---- next power-up window: forced NTSC is applied, CLK2 back to PLLA ----
        snes_clock_stopped=1; repeat(3) @(negedge clk);
        if (region_pal) $fatal(1,"forced NTSC not applied at next power-up");
        wait_ready("PAL->NTSC");
        check_reg(58,8'h49); check_reg(59,8'h2D); check_reg(60,8'h00); check_reg(61,8'h0D);
        check_reg(62,8'hE5); check_reg(63,8'h00); check_reg(64,8'h34); check_reg(65,8'hBF);
        check_reg(18,8'h0F);
        check_pixel_clock(1'b0, 74932, 59561);
        if (n_post != 18) fail($sformatf("%0d post-start-up writes, expected 18", n_post));

        // ---- misbehaving top: SNES clock starts in the middle of the PAL sequence ----
        region_mode=2'd2;
        wait (n_post == 21);                            // third MS2 byte received
        snes_clock_stopped=0;
        repeat(100_000) @(negedge clk);
        if (pixel_clock_ready) fail("pixel_clock_ready high after an interrupted sequence");
        if (n_post != 21) fail($sformatf("sequence continued after the SNES clock started (%0d writes, expected 21)", n_post));
        snes_clock_stopped=1;                           // next stopped window: redo in full
        wait_ready("interrupted PAL sequence redone");
        check_reg(59,8'h36); check_reg(62,8'hC9); check_reg(65,8'h1A); check_reg(18,8'h2F);
        check_pixel_clock(1'b1, 432, 341);
        if (n_post != 30) fail($sformatf("%0d post-start-up writes, expected 30", n_post));
        check_post_regs("final");
        if (starts_running != 0) fail($sformatf("%0d I2C transactions started while the SNES clock ran", starts_running));

        if (errors == 0)
            $display("PASS: Si5351 image (PLLA/PLLB/MS0/MS1/MS2/control) written and verified, lock polled (%0d status reads), region latched only while SNES clock stopped; CLK2 retargeted NTSC->PAL->NTSC->PAL (MS2+reg18 only, %0d post-start-up writes, 0 while the SNES clock ran, 1 PLL reset), interrupted sequence stopped and redone (%0d writes, %0d clocks)",
                     status_reads, n_post, writes, cycles);
        else begin
            $display("FAIL: clock-init %0d errors", errors);
            $fatal(1, "clock-init checks failed");
        end
        $finish;
    end
endmodule
