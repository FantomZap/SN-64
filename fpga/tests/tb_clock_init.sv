`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Behavioural Si5351A I2C slave (address 0x60) for sn64_clock_init: records
// every register write, ACKs its address, returns status register 0 with
// SYS_INIT set for the first few reads. Checks the final register image
// against the values derived in docs/design/clock-plan.md, the PLL reset and
// output enables, clocks_ready, and that the region latch only follows the
// detection/override while the SNES clock is stopped. With +wrong_addr the
// slave ignores the address and the master must report i2c_error.
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
    integer status_reads=0, writes=0;
    reg wrong_addr=0;
    reg [7:0] shift; integer bitc; reg addressed, is_read, have_reg; reg [7:0] reg_ptr, tx;
    reg in_frame=0;
    // START / STOP detection
    always @(negedge sda) if (scl) begin in_frame=1; bitc=0; addressed=0; have_reg=0; slave_sda_low=0; end
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
            if (is_read && addressed && !have_reg_pending) begin send_phase=1; tx = (status_reads<4) ? 8'h80 : 8'h00; status_reads=status_reads+1; slave_sda_low = !tx[7]; end
        end else if (send_phase) begin
            if (bitc < 8) slave_sda_low = !tx[7-bitc]; else slave_sda_low = 0;
        end else if (bitc==8) begin
            // byte complete: decide ACK
            if (!addressed) begin
                if (shift[7:1]==7'h60 && !wrong_addr) begin addressed=1; is_read=shift[0]; slave_sda_low=1; ack_phase=1; end
            end else if (!have_reg) begin reg_ptr=shift; have_reg=1; slave_sda_low=1; ack_phase=1; end
            else begin regs[reg_ptr]=shift; writes=writes+1; reg_ptr=reg_ptr+1; slave_sda_low=1; ack_phase=1; end
        end
    end
    wire have_reg_pending = 1'b0;

    // ---------------- Checks ----------------
    task check_reg(input [7:0] r, input [7:0] v); if (regs[r]!==v) $fatal(1,"register %0d = %h, expected %h", r, regs[r], v); endtask
    integer cycles=0; always @(negedge clk) begin cycles=cycles+1; if (cycles>3_000_000) $fatal(1,"timeout: ready=%b err=%b state=%0d", clocks_ready, i2c_error, dut.q); end

    initial begin
        wrong_addr = $test$plusargs("wrong_addr");
        for (integer i=0;i<256;i=i+1) regs[i]=8'hxx;
        repeat(5) @(negedge clk); reset_n=1;
        if (wrong_addr) begin
            wait(i2c_error); if (clocks_ready) $fatal(1,"ready despite NACK");
            $display("FAIL-EXPECTED: master reported i2c_error on NACK"); $fatal(1,"wrong-address run ends in error as intended");
        end
        wait(clocks_ready || i2c_error);
        if (i2c_error) $fatal(1,"unexpected i2c_error");
        // PLLA 859.0909 MHz (P1=3886 P2=6 P3=11)
        check_reg(26,8'h00); check_reg(27,8'h0B); check_reg(28,8'h00); check_reg(29,8'h0F);
        check_reg(30,8'h2E); check_reg(31,8'h00); check_reg(32,8'h00); check_reg(33,8'h06);
        // PLLB 851.2548 MHz (P1=3846 P2=26536 P3=62500)
        check_reg(34,8'hF4); check_reg(35,8'h24); check_reg(36,8'h00); check_reg(37,8'h0F);
        check_reg(38,8'h06); check_reg(39,8'h00); check_reg(40,8'h67); check_reg(41,8'hA8);
        // MS0 / MS1 divide by 40
        check_reg(45,8'h12); check_reg(43,8'h01); check_reg(53,8'h12); check_reg(51,8'h01);
        // control, PLL reset, outputs
        check_reg(183,8'hD2); check_reg(177,8'hA0); check_reg(16,8'h4F); check_reg(17,8'h6F); check_reg(18,8'h80); check_reg(3,8'hFC);
        if (status_reads<5) $fatal(1,"did not wait for PLL lock (reads=%0d)",status_reads);
        // Region latch: follows detection only while the SNES clock is stopped.
        detected_valid=1; detected_pal=1; repeat(3) @(negedge clk);
        if (!region_pal) $fatal(1,"detected PAL not applied while clock stopped");
        snes_clock_stopped=0;                     // SNES clock running from here on
        detected_pal=0; region_mode=2'd1; repeat(10) @(negedge clk);
        if (!region_pal) $fatal(1,"region changed while the SNES clock was running");
        if (!pending) $fatal(1,"pending change not reported");
        snes_clock_stopped=1; repeat(3) @(negedge clk);   // next power-up window
        if (region_pal) $fatal(1,"forced NTSC not applied at next power-up");
        $display("PASS: Si5351 image (PLLA/PLLB/MS0/MS1/control) written and verified, lock polled (%0d status reads), region latched only while SNES clock stopped (%0d writes, %0d clocks)", status_reads, writes, cycles);
        $finish;
    end
endmodule
