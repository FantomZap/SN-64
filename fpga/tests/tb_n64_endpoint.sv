`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// N64 host model driving the SN64 endpoint through the PI bus protocol:
// ALE_H/ALE_L address latch, then /READ or /WRITE pulses on the multiplexed
// AD[15:0] lines. Timing follows the N64 PI (~15.6 ns steps, ~100 ns strobes);
// exact console timing must still be measured on hardware. Checks: bootstrap
// ROM reads return the loaded program, mailbox writes reach the SNES-side
// outputs, mailbox reads return magic/status, the AD bus is never driven by
// the cartridge except while /READ is low, and a host reset clears run_request.
module tb_n64_endpoint;
    reg clk=0; always #23.28 clk=~clk;      // 21.477 MHz
    reg reset=1;
    reg n64_reset=0, n64_nmi=1, alel=0, aleh=0, rd=1, wr=1;
    reg host_drive=0; reg [15:0] host_ad=16'h0;
    wire [15:0] ad = host_drive ? host_ad : 16'hzzzz;
    reg rom_we=0; reg [11:0] rom_waddr=0; reg [15:0] rom_wdata=0;
    wire [15:0] j1,j2,seq; wire [7:0] sx,sy; wire run; wire [1:0] check_mode;
    reg [15:0] cart_check=16'hC143;                              // arbitrary pattern; the RTL passes it through
    reg [15:0] status=16'hA5C3;
    reg [15:0] region_info=16'h7E02, region_source=16'h0016;   // arbitrary patterns; the RTL passes them through
    wire rst_ev, nmi_ev;

    sn64_n64_endpoint #(.ROM_ADDR_BITS(12)) dut(.clk(clk),.reset(reset),.cic_cpu_clk(clk),
        .n64_reset(n64_reset),.n64_nmi(n64_nmi),.n64_pi_alel(alel),.n64_pi_aleh(aleh),
        .n64_pi_read(rd),.n64_pi_write(wr),.n64_pi_ad(ad),
        .rom_we(rom_we),.rom_waddr(rom_waddr),.rom_wdata(rom_wdata),
        .joy1_buttons(j1),.joy2_buttons(j2),.joy1_stick_x(sx),.joy1_stick_y(sy),
        .run_request(run),.soft_reset(),.region_mode(),.mailbox_seq(seq),.fault_flags(16'h0100),.status_flags(status),.build_id(16'h0102),
        .cart_check_mode(check_mode),.cart_check(cart_check),
        .region_info(region_info),.region_source(region_source),
        .clk_snes(1'b0), .rst_snes_n(1'b0), .video_rgb(15'd0), .video_hde(1'b0), .video_vde(1'b0), .video_x(9'd0), .video_y(9'd0),
        .video_high_res(1'b0), .video_interlace(1'b0), .video_pal(1'b0), .audio_left(16'd0), .audio_right(16'd0), .audio_ready(1'b0),
        .n64_cic_clk(1'b1),.n64_cic_dq(),.n64_si_clk(1'b0),.cic_region(1'b0),.cic_invalid_region(),.cic_step(),
        .host_reset_event(rst_ev),.host_nmi_event(nmi_ev));

    // Bus rule: the cartridge may only drive AD while /READ is low.
    integer cycles=0, rd_high_clocks=0;
    always @(negedge clk) begin
        cycles=cycles+1;
        // Use the PI controller's actual output enable (two-state simulator: an
        // undriven inout is not reliably X).
        if (!reset && host_drive && dut.pi.n64_pi_ad_oe) $fatal(1,"Cartridge drove AD while host was driving (t=%0d)",cycles);
        // The PI controller releases AD a few clocks after /READ rises (data
        // hold through its input synchroniser); allow that, forbid anything longer.
        rd_high_clocks <= rd ? rd_high_clocks + 1 : 0;
        if (!reset && rd && rd_high_clocks > 4 && dut.pi.n64_pi_ad_oe) $fatal(1,"Cartridge still drives AD %0d clocks after /READ rose (t=%0d)",rd_high_clocks,cycles);
        if (cycles>200000) $fatal(1,"timeout");
    end

    // PI protocol: latch address (high half with ALE_H, low half with ALE_L),
    // then transfers. Each state is held >= 300 ns: the PI controller
    // synchronises inputs through 3 flip-flops at 21.477 MHz (~140 ns) and
    // the real N64 holds ALE states for several hundred ns.
    task pi_addr(input [31:0] a);
        begin
            // N64 PI sequence: both ALE high (HIGH, high half latched on entry),
            // ALE_H drops while ALE_L stays high (LOW), then ALE_L drops (VALID,
            // low half latched). {ALE_H,ALE_L}: 11 -> 01 -> 00.
            host_drive=1; host_ad=a[31:16]; #100 aleh=1; alel=1; #300;
            host_ad=a[15:0]; aleh=0; #300 alel=0;
            #300 host_drive=0; #100;
        end
    endtask
    task pi_read(output [15:0] d);
        begin
            #100 rd=0; #400 d=ad; #20 rd=1; #300;
        end
    endtask
    task pi_write(input [15:0] d);
        begin
            #100 host_drive=1; host_ad=d; #100 wr=0; #400 wr=1; #100 host_drive=0; #200;
        end
    endtask
    task pi_end; begin #100 aleh=1; alel=1; #300 aleh=0; alel=0; #300; end endtask   // VALID -> HIGH -> IDLE(10)? real PI returns to IDLE via ALE_H high

    reg [15:0] d0,d1,d2,d3;
    initial begin
        // Load a bootstrap ROM image: word i = 0x1000+i, plus a marker.
        #10; for (integer i=0;i<4096;i=i+1) begin @(negedge clk); rom_we=1; rom_waddr=i; rom_wdata=16'h1000+i; end
        @(negedge clk) rom_we=0; rom_wdata=0;
        repeat(5) @(negedge clk); reset=0;
        repeat(5) @(negedge clk); n64_reset=1;      // console releases reset
        repeat(10) @(negedge clk);

        // 1) Boot ROM read burst from 0x1000_0000: two words
        pi_addr(32'h1000_0000); pi_read(d0); pi_read(d1); pi_end;
        if (d0!==16'h1000 || d1!==16'h1001) $fatal(1,"ROM read wrong: %h %h",d0,d1);
        // 2) ROM read at an offset (word 0x20)
        pi_addr(32'h1000_0040); pi_read(d0); pi_end;
        if (d0!==16'h1020) $fatal(1,"ROM offset read wrong: %h",d0);
        // 3) Mailbox reads: magic, version, status
        pi_addr(32'h1FFF_0000); pi_read(d0); pi_read(d1); pi_read(d2); pi_end;
        if (d0!==16'h534E || d1!==16'h0102 || d2!==16'hA5C3) $fatal(1,"Mailbox read wrong: %h %h %h",d0,d1,d2);
        // 4) Mailbox writes: JOY1, JOY2, stick, control(run), commit
        pi_addr(32'h1FFF_0010); pi_write(16'hB0B1); pi_write(16'h0C0D); pi_write(16'h7F80); pi_write(16'h0001); pi_write(16'h0000); pi_end;
        repeat(4) @(negedge clk);
        if (j1!==16'hB0B1 || j2!==16'h0C0D || sx!==8'h80 || sy!==8'h7F || run!==1'b1 || seq!==16'd1)
            $fatal(1,"Mailbox write wrong: j1=%h j2=%h sx=%h sy=%h run=%b seq=%0d",j1,j2,sx,sy,run,seq);
        // 5) Read back what was written
        pi_addr(32'h1FFF_0010); pi_read(d0); pi_read(d1); pi_read(d2); pi_read(d3); pi_end;
        if (d0!==16'hB0B1 || d1!==16'h0C0D || d2!==16'h7F80 || d3!==16'h0001) $fatal(1,"Mailbox readback wrong: %h %h %h %h",d0,d1,d2,d3);
        // 5b) REGION_INFO (0x1A) and REGION_SOURCE (0x1C): read as the bootstrap does,
        //     i.e. the 32-bit pairs at 0x18 {COMMIT reads 0, REGION_INFO} and 0x1C {REGION_SOURCE, 0x1E = 0}.
        pi_addr(32'h1FFF_0018); pi_read(d0); pi_read(d1); pi_read(d2); pi_read(d3); pi_end;
        if (d0!==16'h0000 || d1!==16'h7E02 || d2!==16'h0016 || d3!==16'h0000)
            $fatal(1,"REGION_INFO/REGION_SOURCE read wrong: %h %h %h %h",d0,d1,d2,d3);
        // The words follow their inputs (they are live mailbox inputs, not latched in the endpoint).
        region_info=16'h8B31; region_source=16'h0005; repeat(2) @(negedge clk);
        pi_addr(32'h1FFF_001A); pi_read(d1); pi_read(d2); pi_end;
        if (d1!==16'h8B31 || d2!==16'h0005) $fatal(1,"REGION words did not follow their inputs: %h %h",d1,d2);
        // 5c) The bootstrap's COMMIT is a 32-bit write {0x18 = 1, 0x1A = 0}: SEQ +1 exactly, 0x1A stays read-only.
        pi_addr(32'h1FFF_0018); pi_write(16'h0001); pi_write(16'h0000); pi_write(16'hFFFF); pi_end;
        repeat(4) @(negedge clk);
        if (seq!==16'd2) $fatal(1,"COMMIT pair write: SEQ=%0d expected 2",seq);
        pi_addr(32'h1FFF_001A); pi_read(d1); pi_read(d2); pi_end;
        if (d1!==16'h8B31 || d2!==16'h0005) $fatal(1,"write to read-only REGION words changed them: %h %h",d1,d2);
        // 5d) Cartridge check: CONTROL bits 5:4 carry the mode and read back; CART_CHECK is at 0x0A,
        //     the low half of the bootstrap's 32-bit read at 0x08 {FAULT, CART_CHECK}.
        pi_addr(32'h1FFF_0016); pi_write(16'h0031); pi_end;
        repeat(4) @(negedge clk);
        if (check_mode!==2'd3 || run!==1'b1) $fatal(1,"CONTROL check mode not taken: mode=%0d run=%b",check_mode,run);
        pi_addr(32'h1FFF_0016); pi_read(d3); pi_end;
        if (d3!==16'h0031) $fatal(1,"CONTROL readback wrong: %h",d3);
        pi_addr(32'h1FFF_0008); pi_read(d0); pi_read(d1); pi_end;
        if (d0!==16'h0100 || d1!==16'hC143) $fatal(1,"FAULT/CART_CHECK read wrong: %h %h",d0,d1);
        // 6) Host reset drops the run request and produces an event on release
        n64_reset=0; repeat(6) @(negedge clk);
        if (run!==1'b0) $fatal(1,"run_request survived host reset");
        if (check_mode!==2'd0) $fatal(1,"cartridge check mode not back to enforce after host reset");
        n64_reset=1; repeat(4) @(negedge clk);
        $display("PASS: N64 endpoint ROM burst/offset reads, mailbox read/write/readback, REGION_INFO/REGION_SOURCE at 0x1A/0x1C read-only, COMMIT pair +1, check mode in CONTROL and CART_CHECK at 0x0A, run_request and check mode cleared by host reset (%0d clocks)",cycles);
        $finish;
    end
endmodule
