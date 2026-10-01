`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Integration check between the bootstrap build and the FPGA N64 endpoint:
// loads the converted bootstrap image (z64_to_rom_words.py output) into
// sn64_n64_endpoint through rom_we/rom_waddr/rom_wdata, reads it back over the
// PI bus model, and replays the bootstrap's per-frame mailbox traffic exactly
// as its 32-bit io_read/io_write calls appear on the PI (two 16-bit halves
// per access). The PI host-model tasks are taken from fpga/tests/tb_n64_endpoint.sv.
//
// Plusargs: +image=<readmemh file> (required), +corrupt_load (fault injection:
// one word is altered while loading; the bench must then FAIL).
module tb_bootstrap_rom_window #(
    parameter integer AW = 16                      // ROM_ADDR_BITS the bootstrap needs (override with -GAW=)
);
    localparam integer DEPTH = 1 << AW;
    reg clk=0; always #23.28 clk=~clk;             // 21.477 MHz
    reg reset=1;
    reg n64_reset=0, n64_nmi=1, alel=0, aleh=0, rd=1, wr=1;
    reg host_drive=0; reg [15:0] host_ad=16'h0;
    wire [15:0] ad = host_drive ? host_ad : 16'hzzzz;
    reg rom_we=0; reg [AW-1:0] rom_waddr=0; reg [15:0] rom_wdata=0;
    wire [15:0] j1,j2,seq; wire [7:0] sx,sy; wire run; wire [1:0] cm;
    wire rst_ev, nmi_ev;

    sn64_n64_endpoint #(.ROM_ADDR_BITS(AW)) dut(.clk(clk),.reset(reset),.cic_cpu_clk(clk),
        .n64_reset(n64_reset),.n64_nmi(n64_nmi),.n64_pi_alel(alel),.n64_pi_aleh(aleh),
        .n64_pi_read(rd),.n64_pi_write(wr),.n64_pi_ad(ad),
        .rom_we(rom_we),.rom_waddr(rom_waddr),.rom_wdata(rom_wdata),
        .joy1_buttons(j1),.joy2_buttons(j2),.joy1_stick_x(sx),.joy1_stick_y(sy),
        .run_request(run),.mailbox_seq(seq),.fault_flags(16'h0000),.status_flags(16'h0011),.build_id(16'h0102),
        .cart_check_mode(cm),.cart_check(16'h8152),
        .region_info(16'h7002),.region_source(16'h0016),
        .n64_cic_clk(1'b1),.n64_cic_dq(),.n64_si_clk(1'b0),.cic_region(1'b0),.cic_invalid_region(),.cic_step(),
        .host_reset_event(rst_ev),.host_nmi_event(nmi_ev));

    integer cycles=0, rd_high_clocks=0;
    always @(negedge clk) begin
        cycles=cycles+1;
        if (!reset && host_drive && dut.pi.n64_pi_ad_oe) $fatal(1,"Cartridge drove AD while host was driving (t=%0d)",cycles);
        rd_high_clocks <= rd ? rd_high_clocks + 1 : 0;
        if (!reset && rd && rd_high_clocks > 4 && dut.pi.n64_pi_ad_oe) $fatal(1,"Cartridge still drives AD %0d clocks after /READ rose",rd_high_clocks);
        if (cycles>600000) $fatal(1,"timeout");
    end

    task pi_addr(input [31:0] a);
        begin
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
    task pi_end; begin #100 aleh=1; alel=1; #300 aleh=0; alel=0; #300; end endtask

    // 32-bit CPU accesses as the PI performs them: upper half at A, lower at A+2.
    task io_write32(input [31:0] a, input [31:0] v);
        begin pi_addr(a); pi_write(v[31:16]); pi_write(v[15:0]); pi_end; end
    endtask
    task io_read32(input [31:0] a, output [31:0] v);
        reg [15:0] hi, lo;
        begin pi_addr(a); pi_read(hi); pi_read(lo); pi_end; v = {hi, lo}; end
    endtask

    reg [15:0] img [0:DEPTH-1];
    string path;
    integer i, last, errors=0, words_checked=0;
    reg [15:0] d;
    reg [31:0] v;

    task check_burst(input integer first, input integer n);
        begin
            pi_addr(32'h1000_0000 + 2*first);
            for (integer k=0;k<n;k=k+1) begin
                pi_read(d); words_checked=words_checked+1;
                if (d !== img[first+k]) begin
                    errors=errors+1;
                    $display("  FAIL ROM word %0d (byte 0x%0h): read %h expected %h", first+k, 2*(first+k), d, img[first+k]);
                end
            end
            pi_end;
        end
    endtask

    initial begin
        if (!$value$plusargs("image=%s", path)) $fatal(1,"missing +image=<readmemh file>");
        for (i=0;i<DEPTH;i=i+1) img[i]=16'hDEAD;
        $readmemh(path, img);
        last = 0;
        for (i=0;i<DEPTH;i=i+1) if (img[i] != 16'h0000) last = i;
        if (img[0] !== 16'h8037 || img[1] !== 16'h1240) $fatal(1,"image header is %h %h, not a .z64 word image", img[0], img[1]);

        // Load the image the way the configuration loader will (one word per clock).
        #10;
        for (i=0;i<DEPTH;i=i+1) begin
            @(negedge clk); rom_we=1; rom_waddr=i[AW-1:0];
            rom_wdata = ($test$plusargs("corrupt_load") && i==32'h20) ? (img[i] ^ 16'h0001) : img[i];
        end
        @(negedge clk) rom_we=0;
        repeat(5) @(negedge clk); reset=0;
        repeat(5) @(negedge clk); n64_reset=1;
        repeat(10) @(negedge clk);

        // ROM window: header, start and end of IPL3, and the last program word.
        check_burst(0, 32);                  // 0x000-0x03F header
        check_burst(32'h20, 16);             // 0x040 IPL3 start
        check_burst(32'h7F8, 8);             // 0xFF0 IPL3 end
        check_burst(32'h800, 16);            // 0x1000 first word after IPL3 (program area)
        check_burst(last-3, 4);              // last non-zero word (exercises ROM word-address bit 16)

        // Mailbox, exactly as main.c issues it each frame.
        io_read32(32'h1FFF_0000, v);
        if (v !== 32'h534E_0102) begin errors=errors+1; $display("  FAIL MAGIC/VERSION pair %h", v); end
        io_read32(32'h1FFF_0004, v);
        if (v[31:16] !== 16'h0011 || v[15:0] !== 16'h0000) begin errors=errors+1; $display("  FAIL STATUS/SEQ pair %h", v); end
        // {FAULT, CART_CHECK}: the power fault code and the result of the last cartridge check.
        io_read32(32'h1FFF_0008, v);
        if (v !== 32'h0000_8152) begin errors=errors+1; $display("  FAIL FAULT/CART_CHECK pair %h", v); end
        // Region telemetry pairs, as mailbox_read() issues them: {COMMIT reads 0, REGION_INFO}, {REGION_SOURCE, 0x1E}.
        io_read32(32'h1FFF_0018, v);
        if (v !== 32'h0000_7002) begin errors=errors+1; $display("  FAIL COMMIT/REGION_INFO pair %h", v); end
        io_read32(32'h1FFF_001C, v);
        if (v !== 32'h0016_0000) begin errors=errors+1; $display("  FAIL REGION_SOURCE pair %h", v); end
        // Frame 1: P1 A+Start (SNES B|Start = 0x0009), P2 idle, stick (x=-40,y=40), run_request with
        // the cartridge check enforced, which is the menu's mode (CONTROL = 0x0001).
        io_write32(32'h1FFF_0010, {16'h0009, 16'h0000});
        io_write32(32'h1FFF_0014, {8'd40, 8'hD8, 16'h0001});
        io_write32(32'h1FFF_0018, 32'h0001_0000);
        repeat(4) @(negedge clk);
        if (j1!==16'h0009 || j2!==16'h0000 || sx!==8'hD8 || sy!==8'd40 || run!==1'b1 || cm!==2'd0 || seq!==16'd1) begin
            errors=errors+1; $display("  FAIL frame 1: j1=%h j2=%h sx=%h sy=%h run=%b check=%0d seq=%0d", j1, j2, sx, sy, run, cm, seq);
        end
        // Frame 2: new buttons on both pads; the 0x1A half of COMMIT must not count.
        io_write32(32'h1FFF_0010, {16'h0F00, 16'h0030});
        io_write32(32'h1FFF_0014, {16'h0000, 16'h0001});
        io_write32(32'h1FFF_0018, 32'h0001_0000);
        repeat(4) @(negedge clk);
        if (j1!==16'h0F00 || j2!==16'h0030 || run!==1'b1 || seq!==16'd2) begin
            errors=errors+1; $display("  FAIL frame 2: j1=%h j2=%h run=%b seq=%0d", j1, j2, run, seq);
        end
        io_read32(32'h1FFF_0014, v);
        if (v !== 32'h0000_0001) begin errors=errors+1; $display("  FAIL STICK/CONTROL readback %h", v); end
        // Frame 3: "Power down cartridge" clears run_request.
        io_write32(32'h1FFF_0010, 32'h0);
        io_write32(32'h1FFF_0014, 32'h0000_0000);
        io_write32(32'h1FFF_0018, 32'h0001_0000);
        repeat(4) @(negedge clk);
        if (run!==1'b0 || cm!==2'd0 || seq!==16'd3) begin errors=errors+1; $display("  FAIL power down: run=%b check=%0d seq=%0d", run, cm, seq); end
        // Frame 4: the service screen's "check the cartridge now": a request in check-only mode
        // (CONTROL = 0x0031), neutral pads.
        io_write32(32'h1FFF_0010, 32'h0);
        io_write32(32'h1FFF_0014, 32'h0000_0031);
        io_write32(32'h1FFF_0018, 32'h0001_0000);
        repeat(4) @(negedge clk);
        if (run!==1'b1 || cm!==2'd3 || j1!==16'h0000 || seq!==16'd4) begin
            errors=errors+1; $display("  FAIL check only: run=%b check=%0d j1=%h seq=%0d", run, cm, j1, seq);
        end
        // Frame 5: the check is over; the menu drops the request and goes back to its own mode.
        io_write32(32'h1FFF_0010, 32'h0);
        io_write32(32'h1FFF_0014, 32'h0000_0000);
        io_write32(32'h1FFF_0018, 32'h0001_0000);
        repeat(4) @(negedge clk);
        if (run!==1'b0 || cm!==2'd0 || seq!==16'd5) begin errors=errors+1; $display("  FAIL after check: run=%b check=%0d seq=%0d", run, cm, seq); end

        // Frame 6: the service screen set the check to report only for the session, then a start (CONTROL = 0x0011).
        io_write32(32'h1FFF_0010, 32'h0);
        io_write32(32'h1FFF_0014, 32'h0000_0011);
        io_write32(32'h1FFF_0018, 32'h0001_0000);
        repeat(4) @(negedge clk);
        if (run!==1'b1 || cm!==2'd1 || seq!==16'd6) begin errors=errors+1; $display("  FAIL report-only start: run=%b check=%0d seq=%0d", run, cm, seq); end

        if (errors) begin
            $display("FAIL: bootstrap ROM window, %0d error(s)%s", errors, $test$plusargs("corrupt_load") ? " (corrupt_load injected)" : "");
            $fatal(1, "bootstrap ROM window check failed");
        end
        $display("PASS: bootstrap image (%0d words, last non-zero word %0d) loaded via rom_we, %0d words read back over PI, mailbox frame traffic (32-bit pairs, FAULT/CART_CHECK and REGION_INFO/REGION_SOURCE reads, COMMIT once per frame, run/power-down, cartridge check mode and check-only request) correct (%0d clocks)",
                 DEPTH, last, words_checked, cycles);
        $finish;
    end
endmodule
