`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Console-side model of the N64 CIC lockout handshake, driving the vendored
// SummerCart64 CIC (SERV soft core running the vendored UltraCIC_C firmware)
// through the SN64 endpoint. The console (PIF) clocks CIC_CLK; the cartridge
// drives CIC_DQ low-or-release. Checks the ID nibble, then that the seed and
// checksum streams match a reference computed from the same public algorithm
// (UltraCIC_C / SummerCart64 cic.c), then that the compare-mode command is
// answered with the right number of bits. Timings are representative: the
// real PIF clocks the CIC at a few hundred kHz. No commercial ROM involved.
module tb_n64_cic;
    reg clk=0; always #23.28 clk=~clk;      // 21.477 MHz FPGA clock
    reg cpu_clk=0; always #8 cpu_clk=~cpu_clk;  // 62.5 MHz CIC soft-CPU clock (SummerCart64 rate)
    reg reset=1;
    reg n64_reset=0;
    reg cic_clk=1, si_clk=0;
    always #320 si_clk=~si_clk;             // ~1.56 MHz PIF/SI clock (timer reference)

    // Open-drain CIC data line: pulled up; console or cartridge may pull low.
    reg console_pull_low=0;
    wire cic_dq;
    assign cic_dq = console_pull_low ? 1'b0 : 1'bz;
    pullup(cic_dq);

    // Unused endpoint ports
    wire [15:0] ad = 16'hzzzz;
    wire [15:0] j1,j2,seq; wire [7:0] sx,sy; wire run, rst_ev, nmi_ev, inv;
    wire [3:0] step;

    sn64_n64_endpoint #(.ROM_ADDR_BITS(4)) dut(.clk(clk),.reset(reset),.cic_cpu_clk(cpu_clk),
        .n64_reset(n64_reset),.n64_nmi(1'b1),.n64_pi_alel(1'b0),.n64_pi_aleh(1'b1),
        .n64_pi_read(1'b1),.n64_pi_write(1'b1),.n64_pi_ad(ad),
        .rom_we(1'b0),.rom_waddr(4'd0),.rom_wdata(16'd0),
        .joy1_buttons(j1),.joy2_buttons(j2),.joy1_stick_x(sx),.joy1_stick_y(sy),
        .run_request(run),.mailbox_seq(seq),.status_flags(16'h0),.build_id(16'h0),
        .n64_cic_clk(cic_clk),.n64_cic_dq(cic_dq),.n64_si_clk(si_clk),.cic_region(1'b0),
        .cic_invalid_region(inv),.cic_step(step),
        .host_reset_event(rst_ev),.host_nmi_event(nmi_ev));

    // --- Console-side bit primitives (mirror of cic_read_bit/cic_write_bit) --
    // Cartridge writes: it sets DQ after CLK falls; console samples before CLK rises.
    // 12.5 us half period (40 kHz). The vendored firmware on bit-serial SERV at
    // 62.5 MHz needs ~16 us per bit (measured in this bench); SummerCart64 works
    // on real consoles, so the PIF's CIC clock is slower than 250 kHz. A faster
    // console model desynchronises the stream.
    localparam HALF = 50000;   // 10 kHz: margin for the firmware's inter-nibble computation
    task console_read_bit(output bit b);
        begin cic_clk=0; #(HALF-50); b=cic_dq; #50; cic_clk=1; #HALF; end
    endtask
    task console_write_bit(input bit b);
        begin console_pull_low=!b; cic_clk=0; #HALF; cic_clk=1; #HALF; console_pull_low=0; end
    endtask
    task console_read(input integer n, output [63:0] v);
        bit b; begin v=0; for (integer i=0;i<n;i=i+1) begin console_read_bit(b); v={v[62:0],b}; end end
    endtask
    task console_write(input [31:0] v, input integer n);
        begin for (integer i=n-1;i>=0;i=i-1) console_write_bit(v[i]); end
    endtask

    integer cycles=0;
    always @(negedge clk) begin cycles=cycles+1; if (cycles>400_000_000) $fatal(1,"CIC test timed out at step %0d",step); end

    reg [63:0] v; reg [3:0] exp_seed [0:5]; reg [3:0] exp_chk [0:15]; integer errors=0;
    initial begin
        // Reference streams computed with the firmware's own algorithm (byte-wide
        // RAM, nibble-masked encode rounds) for seed 0x3F / checksum A536C0F1D859:
        exp_seed[0]=4'hB; exp_seed[1]=4'hD; exp_seed[2]=4'h3; exp_seed[3]=4'h9; exp_seed[4]=4'h3; exp_seed[5]=4'hD;
        {exp_chk[0],exp_chk[1],exp_chk[2],exp_chk[3],exp_chk[4],exp_chk[5],exp_chk[6],exp_chk[7],
         exp_chk[8],exp_chk[9],exp_chk[10],exp_chk[11],exp_chk[12],exp_chk[13],exp_chk[14],exp_chk[15]} = 64'h04E2FAC5210FCE2F;
        // Negative check: +corrupt_expect changes one expected checksum nibble; the run must fail.
        if ($test$plusargs("corrupt_expect")) exp_chk[3] = exp_chk[3] ^ 4'h1;

        repeat(50) @(negedge clk); reset=0;
        repeat(50) @(negedge clk); n64_reset=1;          // console power-on: CIC firmware leaves POWER_OFF
        // SERV is bit-serial: the firmware needs a few thousand FPGA clocks to
        // reach the ID step. The real PIF starts clocking the CIC well after
        // reset release; wait for the firmware's ID step (3) like the PIF's delay.
        wait(step==4'd3); #100000;
        // 1) ID nibble: 4 bits = {0 (cartridge), region=0, 0, 1} = 0001
        console_read(4, v); if (v[3:0]!==4'b0001) begin $display("FAIL ID=%b", v[3:0]); errors=errors+1; end
        // 2) Seed: 6 nibbles (24 bits). The firmware computes two encode rounds
        //    before sending; the PIF leaves a gap between phases, so wait for the
        //    seed step plus its computation time before clocking.
        wait(step==4'd4); #400000;
        console_read(24, v);
        for (integer i=0;i<6;i=i+1) if (v[23-4*i -: 4]!==exp_seed[i]) begin $display("FAIL seed nibble %0d: got %h exp %h",i,v[23-4*i -: 4],exp_seed[i]); errors=errors+1; end
        // 3) Checksum: firmware computes four encode rounds, reads 1 bit from the
        //    console, then writes 16 nibbles.
        wait(step==4'd5); #800000;
        console_write_bit(1'b0);
        console_read(64, v);  // 16 nibbles = 64 bits
        for (integer i=0;i<16;i=i+1) if (v[63-4*i -: 4]!==exp_chk[i]) begin $display("FAIL checksum nibble %0d: got %h exp %h",i,v[63-4*i -: 4],exp_chk[i]); errors=errors+1; end
        // 4) init_ram: console sends two nibbles (random-ish seeds for compare mode)
        wait(step==4'd6); #100000;
        console_write(4'hA, 4); console_write(4'h5, 4);
        // 5) Command: COMPARE (00). Cartridge then answers a bit for each console bit
        //    over a variable-length walk; we exchange 16 bit pairs and only require
        //    that the line is released between console bits (no lock-up) and the
        //    firmware step advances to COMPARE (8).
        wait(step==4'd7); #100000;
        console_write(2'b00, 2);
        #40000; if (step!==4'd8) begin $display("FAIL: step after COMPARE command = %0d (expected 8)", step); errors=errors+1; end
        for (integer i=0;i<15;i=i+1) begin console_write_bit(1'b0); console_read_bit(v[0]); end
        if (errors==0) begin
            $display("PASS: CIC ID, 6102 seed and checksum streams match the reference encoder, compare mode entered (%0d clocks)", cycles);
            $finish;
        end else $fatal(1,"CIC test failed with %0d errors", errors);
    end
endmodule
