`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Original testbenches for the SN64 controller path; no commercial ROM.
//
// tb_snes_joypad       : serial protocol of sn64_snes_joypad alone, driven the
//                        way the SNESTang CPU drives JOY_STRB / JOYn_CLK.
// tb_snes_joypad_core  : (define SN64_JOYPAD_CORE_TEST) the real console core
//                        runs an original 65816 diagnostic that reads both pads
//                        through auto-joypad ($4218-$421C) and manual
//                        ($4016/$4017) reads and writes what it saw to $70:0000+.
// Both must fail when built with SN64_FAULT_SWAP_BY (B and Y swapped).

module tb_snes_joypad;
    reg clk = 0;
    always #23.28 clk = ~clk;
    reg [15:0] b1 = 0, b2 = 0;
    reg [1:0] present = 2'b11;
    reg strobe = 0, c1 = 0, c2 = 0;
    wire [1:0] d1, d2;
    integer checks = 0, cases = 0;
    integer hi = 8, lo = 8;   // clock pulse high/low widths in master clocks

    sn64_snes_joypad dut(.clk(clk), .joy1_buttons(b1), .joy2_buttons(b2), .pad_present(present),
        .joy_strobe(strobe), .joy1_clock(c1), .joy2_clock(c2), .joy1_di(d1), .joy2_di(d2));

    // Logical bit i (as the CPU sees it after inversion) of a standard pad
    // holding mailbox image w: 12 buttons in SNES order, ID 0000, then 1s.
    function automatic bit expect_bit(input logic [15:0] w, input integer i);
        if (i < 12) return w[i];
        if (i < 16) return 1'b0;
        return 1'b1;
    endfunction

    task automatic latch();
        strobe = 1; repeat (12) @(negedge clk);
        strobe = 0; repeat (6) @(negedge clk);
    endtask

    task automatic pulse(input bit p1, input bit p2);
        c1 = p1; c2 = p2; repeat (hi) @(negedge clk);
        c1 = 0;  c2 = 0;  repeat (lo) @(negedge clk);
    endtask

    // Sample the data lines, then clock the selected ports, like the core does.
    task automatic read_check(input string name, input integer first, input integer n,
                              input bit p1, input bit p2, input logic [15:0] w1, input logic [15:0] w2,
                              input bit present1, input bit present2);
        bit want;
        for (integer i = first; i < first + n; i++) begin
            if (d1[1] !== 1'b1 || d2[1] !== 1'b1)
                $fatal(1, "%0s: multitap data line not idle high at bit %0d", name, i);
            if (p1) begin
                want = present1 ? expect_bit(w1, i) : 1'b0;
                if (!d1[0] !== want)
                    $fatal(1, "%0s: port 1 bit %0d read %0b, expected %0b (bit order/ID/trailing 1s)", name, i, !d1[0], want);
                checks++;
            end
            if (p2) begin
                want = present2 ? expect_bit(w2, i) : 1'b0;
                if (!d2[0] !== want)
                    $fatal(1, "%0s: port 2 bit %0d read %0b, expected %0b (bit order/ID/trailing 1s)", name, i, !d2[0], want);
                checks++;
            end
            pulse(p1, p2);
        end
    endtask

    initial begin
        repeat (4) @(negedge clk);
        // 1. Walking one: each button alone lands in exactly its slot, both ports.
        for (integer k = 0; k < 12; k++) begin
            b1 = 16'h0001 << k; b2 = 16'h0800 >> k;
            latch(); read_check("walking-one", 0, 24, 1, 1, b1, b2, 1, 1); cases++;
        end
        // 2. Reserved mailbox bits 12-15 set: the ID nibble must stay 0000.
        b1 = 16'hF5A3; b2 = 16'hFFFF;
        latch(); read_check("reserved-bits", 0, 24, 1, 1, b1, b2, 1, 1); cases++;
        // 3. Random images.
        for (integer k = 0; k < 64; k++) begin
            b1 = 16'($urandom); b2 = 16'($urandom);
            latch(); read_check("random", 0, 20, 1, 1, b1, b2, 1, 1); cases++;
        end
        // 4. Buttons change after the latch and mid-read: the latched image is
        //    returned; the new image appears only after the next latch.
        b1 = 16'h0A5D; b2 = 16'h0536; latch();
        read_check("before-change", 0, 5, 1, 1, 16'h0A5D, 16'h0536, 1, 1);
        b1 = ~16'h0A5D; b2 = ~16'h0536;
        read_check("changed-mid-read", 5, 19, 1, 1, 16'h0A5D, 16'h0536, 1, 1);
        latch(); read_check("relatched", 0, 20, 1, 1, b1, b2, 1, 1); cases++;
        // 5. Independent clocks (manual $4016 reads): port 1 clocks must not shift port 2.
        b1 = 16'h0C3A; b2 = 16'h0391; latch();
        read_check("port1-only", 0, 20, 1, 0, b1, b2, 1, 1);
        if (!d2[0] !== b2[0]) $fatal(1, "port 2 shifted by port 1 clocks");
        read_check("port2-after", 0, 20, 0, 1, b1, b2, 1, 1); cases++;
        // 6. Strobe held high: clocks do not advance the register and the data
        //    line follows B live (4021 parallel-load mode, multitap-detect reads).
        b1 = 16'h0001; b2 = 16'h0000; strobe = 1; repeat (4) @(negedge clk);
        for (integer k = 0; k < 4; k++) begin
            pulse(1, 1);
            if (!d1[0] !== 1'b1 || !d2[0] !== 1'b0) $fatal(1, "clock advanced the pad while strobe was high");
            checks++;
        end
        b1 = 16'h0000; b2 = 16'h0001; repeat (2) @(negedge clk);
        if (!d1[0] !== 1'b0 || !d2[0] !== 1'b1) $fatal(1, "data line did not follow B while strobe was high");
        b1 = 16'h0ABC; b2 = 16'h0543; repeat (2) @(negedge clk);
        strobe = 0; repeat (6) @(negedge clk);
        read_check("after-held-strobe", 0, 24, 1, 1, b1, b2, 1, 1); cases++;
        // 7. Minimum-width pulses: one master clock high, one low.
        hi = 1; lo = 1; b1 = 16'h0B6D; b2 = 16'h04D2;
        latch(); read_check("narrow-pulses", 0, 24, 1, 1, b1, b2, 1, 1); cases++;
        hi = 8; lo = 8;
        // 8. Empty port 2: both lines idle high, every bit reads 0 (no trailing 1s).
        present = 2'b01; b1 = 16'h0FFF; b2 = 16'h0FFF;
        latch(); read_check("port2-empty", 0, 24, 1, 1, b1, b2, 1, 0); cases++;
        present = 2'b11;
        $display("PASS: SNES pad serial protocol, %0d cases, %0d bit checks (order B..R, ID 0000, trailing 1s, both ports, latch hold, no multitap, empty port)",
                 cases, checks);
        $finish;
    end
endmodule

`ifdef SN64_JOYPAD_CORE_TEST
module tb_snes_joypad_core;
    reg clk = 0;
    always #23.28 clk = ~clk;
    reg reset_n = 0;
    wire [23:0] address;
    wire [7:0] data_out;
    reg  [7:0] data_in;
    wire rd_n, wr_n, strobe, jc1, jc2;
    wire [1:0] d1, d2;
    reg [15:0] b1, b2;
    integer cycles = 0, frame = 0, strobe_pulses = 0, pc = 0, frame_pc = 0;
    reg [10:0] seen = 0;
    reg in_write = 0, strobe_q = 0;
    reg [23:0] w_addr;
    reg [7:0] w_data;
    byte rom[0:511];

    localparam [15:0] F0_B1 = 16'h0A5D, F0_B2 = 16'h0536;   // frame 0 images
    localparam [15:0] F1_B1 = 16'hF802, F1_B2 = 16'h0401;   // frame 1 (reserved bits set on port 1)

    sn64_console_candidate dut(.clk(clk), .reset_n(reset_n), .enable(1'b1), .pal(1'b0),
        .cart_address(address), .cart_data_in(data_in), .cart_data_out(data_out),
        .cart_peripheral_address(), .cart_prd_n(), .cart_pwr_n(),
        .cart_rd_n(rd_n), .cart_wr_n(wr_n), .cart_irq_n(1'b1), .cart_phi2(),
        .cart_romsel_n(), .cart_wramsel_n(), .cart_refresh(), .cart_wram_read_valid(),
        .joy1_di(d1), .joy2_di(d2), .joy_strobe(strobe), .joy1_clock(jc1), .joy2_clock(jc2),
        .rgb(), .hsync(), .vsync(), .hde(), .vde(), .dot_clock(), .high_res(), .field(), .interlace(),
        .video_x(), .video_y(), .audio_left(), .audio_right(), .audio_ready());
    sn64_snes_joypad pads(.clk(clk), .joy1_buttons(b1), .joy2_buttons(b2), .pad_present(2'b11),
        .joy_strobe(strobe), .joy1_clock(jc1), .joy2_clock(jc2), .joy1_di(d1), .joy2_di(d2));

    task emit(input byte b); rom[pc] = b; pc = pc + 1; endtask
    task op_abs(input byte opc, input logic [15:0] a); emit(opc); emit(a[7:0]); emit(a[15:8]); endtask
    task op_long(input byte opc, input logic [23:0] a); emit(opc); emit(a[7:0]); emit(a[15:8]); emit(a[23:16]); endtask
    task branch(input byte opc, input integer target); emit(opc); emit(byte'(target - (pc + 1))); endtask
    // 16 manual reads of a port into $00/$01 (first bit ends in $01 bit 7),
    // stored to dst/dst+1, then a 17th raw read stored to dst+2.
    task manual(input logic [15:0] port, input logic [23:0] dst);
        integer l;
        emit('ha2); emit(8'h10);                                    // LDX #16
        l = pc;
        op_abs('had, port); emit('h4a);                             // LDA port; LSR A
        emit('h26); emit(8'h00); emit('h26); emit(8'h01);          // ROL $00; ROL $01
        emit('hca); branch('hd0, l);                                // DEX; BNE
        emit('ha5); emit(8'h00); op_long('h8f, dst);                // LDA $00; STA dst
        emit('ha5); emit(8'h01); op_long('h8f, dst + 1);            // LDA $01; STA dst+1
        op_abs('had, port); op_long('h8f, dst + 2);                 // 17th read
    endtask

    // What the CPU's JOYn register must hold for mailbox image w:
    // first-shifted bit (B) in bit 15, ID nibble 0000 in bits 3..0.
    function automatic [15:0] joy_reg(input logic [15:0] w);
        for (integer i = 0; i < 16; i++) joy_reg[15 - i] = (i < 12) ? w[i] : 1'b0;
    endfunction

    initial begin
        integer l;
        for (integer i = 0; i < 512; i++) rom[i] = 'hea;
        b1 = F0_B1; b2 = F0_B2;
        emit('h78); emit('h18); emit('hfb);                         // SEI; CLC; XCE (native, 8-bit A/X)
        emit('ha9); emit(8'h01); op_abs('h8d, 16'h4200);            // NMITIMEN = auto-joypad on, NMI off
        frame_pc = pc;
        l = pc; op_abs('had, 16'h4212); branch('h10, l);            // wait for VBlank
        l = pc; op_abs('had, 16'h4212); emit('h4a); branch('h90, l); // wait for auto-read busy
        l = pc; op_abs('had, 16'h4212); emit('h4a); branch('hb0, l); // wait for auto-read done
        for (integer r = 0; r < 5; r++) begin                       // $4218-$421C -> $70:0000-4
            op_abs('had, 16'(16'h4218 + r)); op_long('h8f, 24'(24'h700000 + r));
        end
        emit('ha9); emit(8'h01); op_abs('h8d, 16'h4016);            // manual latch: $4016 = 1
        op_abs('h9c, 16'h4016);                                     // STZ $4016
        manual(16'h4016, 24'h700005);                               // port 1 -> $70:0005-7
        manual(16'h4017, 24'h700008);                               // port 2 -> $70:0008-A
        op_abs('h4c, 16'(16'h8000 + frame_pc));                     // JMP frame
        if (pc > 512) $fatal(1, "diagnostic program too long");
        repeat (20) @(negedge clk);
        reset_n = 1;
    end

    always @* begin
        data_in = 8'hea;
        if (address >= 24'h008000 && address < 24'h008200) data_in = rom[address[8:0]];
        case (address)
            24'h00fffc: data_in = 8'h00;
            24'h00fffd: data_in = 8'h80;
            default: ;
        endcase
    end

    task automatic check_write(input logic [23:0] a, input logic [7:0] d);
        logic [15:0] j1, j2, e;
        integer idx;
        if (a < 24'h700000 || a > 24'h70000a) return;
        idx = a[3:0];
        j1 = joy_reg(frame == 0 ? F0_B1 : F1_B1);
        j2 = joy_reg(frame == 0 ? F0_B2 : F1_B2);
        case (idx)
            0, 5:  e = {8'h00, j1[7:0]};
            1, 6:  e = {8'h00, j1[15:8]};
            2, 8:  e = {8'h00, j2[7:0]};
            3, 9:  e = {8'h00, j2[15:8]};
            4:     e = 16'h0000;                                     // $421C JOY3L: no multitap
            default: e = 16'h0000;
        endcase
        if (idx == 7) begin
            if ((d & 8'h03) !== 8'h01) $fatal(1, "frame %0d: 17th $4016 read %h, want bit0=1 (trailing) bit1=0 (no multitap)", frame, d);
        end else if (idx == 10) begin
            if ((d & 8'h1f) !== 8'h1d) $fatal(1, "frame %0d: 17th $4017 read %h, want bits4..2=111 bit1=0 bit0=1", frame, d);
        end else if (d !== e[7:0])
            $fatal(1, "frame %0d: CPU wrote %h to %h, expected %h (%0s)", frame, d, a, e[7:0],
                   idx < 5 ? "auto-joypad" : "manual read");
        seen[idx] = 1'b1;
        if (idx == 10) begin
            if (!(&seen)) $fatal(1, "frame %0d: missing diagnostic writes %b", frame, seen);
            $display("frame %0d: JOY1=%h JOY2=%h reached the CPU (auto and manual), %0d clocks", frame,
                     j1, j2, cycles);
            if (frame == 1) begin
                if (strobe_pulses < 4) $fatal(1, "expected auto and manual strobes, saw %0d", strobe_pulses);
                $display("PASS: core auto-joypad ($4218-$421C) and manual ($4016/$4017) reads return mailbox images over 2 frames with a button change; %0d strobes, %0d clocks",
                         strobe_pulses, cycles);
                $finish;
            end
            frame = 1; seen = 0; b1 = F1_B1; b2 = F1_B2;          // new mailbox images between frames
        end
    endtask

    always @(negedge clk) begin
        cycles = cycles + 1;
        if (strobe && !strobe_q) strobe_pulses = strobe_pulses + 1;
        strobe_q = strobe;
        if (reset_n && !wr_n) begin in_write = 1; w_addr = address; w_data = data_out; end
        else if (in_write) begin in_write = 0; check_write(w_addr, w_data); end
        if (cycles > 1500000) $fatal(1, "timed out in frame %0d, writes %b, strobes %0d, address %h", frame, seen, strobe_pulses, address);
    end
endmodule
`endif
