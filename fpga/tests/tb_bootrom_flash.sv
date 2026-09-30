`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Bootstrap ROM window served from the SPI configuration flash.
//
// DUT: sn64_n64_endpoint with ROM_FROM_FLASH = 1 at 62.5 MHz (clk_host), i.e.
// vendored SummerCart64 n64_pi -> sn64_bootrom_flash -> vendored memory_flash
// (Quad I/O Fast Read EBh, SCK 31.25 MHz) -> behavioural QSPI flash model.
//
// The flash model holds a pseudo-random 128 KiB image at FLASH_OFFSET. An N64
// PI host model reads bursts at several offsets with three sets of timing:
//   P0 slow boot default   LAT/PWD 0xFF (4096 ns), RLS 3   (IPL2 header read)
//   P1 IPL3 header timing  0x80371240: LAT 0x40 (1040 ns), PWD 0x12 (304 ns),
//                          RLS 3 (64 ns), 512-byte pages (one ALE per page)
//   P2 endpoint-bench      /READ low 420 ns (sample at 400), high 400 ns: the
//                          strobes of tb_n64_endpoint.sv, first strobe at LAT 0x40
//   P3 fast                PWD 0x0C (208 ns), RLS 2 (48 ns): 256 ns per word
// (one PI cycle = 16 ns at 62.5 MHz; the register decoding follows the n64brew
// PI description and must still be measured on a console).
// Every word is compared with {img[a], img[a+1]} (big-endian, like the BRAM path).
//
// Checks: data; the flash sees only EBh reads (a write through the 0x1FFE
// window must not reach it); CS# deselect time; DQ never driven by both sides
// (through the enables); mailbox still readable. Reports first-word latency,
// streaming service time, FIFO lead (flash ack -> host sample) and AD slack
// (valid word on AD -> host sample).
//
// Fault injection (must FAIL):
//   +fault=1  one image byte corrupted in the flash model
//   +fault=2  image placed 2 bytes after FLASH_OFFSET (wrong offset)
//   +fault=3  flash output valid 40 ns after SCK falls (sample-point check)
// Sensitivity: +ale_step=<ns> shortens the address phase (default 300 ns as in
// tb_n64_endpoint; the flash request starts when ALE_H falls), +p2_lat=<ns>
// moves P2's first strobe (tb_n64_endpoint's own is 500 ns after ALE_L),
// +p3_pwd/+p3_rls=<PI cycles> change P3's strobes (throughput limit),
// +t_sck/+t_clqv=<ns> change the flash-path delays (sample window).

module tb_qspi_flash_model #(
    parameter ADDR_BITS = 24
) (
    input  wire       sck,
    input  wire       cs_n,
    inout  wire [3:0] dq
);
    reg [7:0] mem [0:(1<<ADDR_BITS)-1];

    // Timing at the FPGA pins (ns). t_sck: FPGA SCK register -> flash (USRMCLK
    // + trace). t_clqx/t_clqv: data hold/valid after the flash sees SCK fall,
    // including the return trace. Between them the model drives inverted data.
    real t_sck  = 6.0;
    real t_clqx = 1.0;
    real t_clqv = 9.0;
    real t_shsl = 10.0;     // minimum CS# high time between reads

    reg sck_d = 1'b0, cs_d = 1'b1;
    always @(sck)  sck_d <= #(t_sck) sck;
    always @(cs_n) cs_d  <= #(t_sck) cs_n;

    localparam S_CMD = 0, S_ADDR = 1, S_MODE = 2, S_DUMMY = 3, S_DATA = 4, S_IDLE = 5;
    integer state = S_IDLE, bits = 0;
    reg [7:0]  cmd = 8'h00, mode = 8'h00;
    reg [ADDR_BITS-1:0] addr = '0;
    reg        nib_hi = 1'b1;
    reg [3:0]  nib;
    reg [3:0]  dq_o = 4'h0;
    reg        oe = 1'b0;
    realtime   t_cs_rise = -1000.0;
    integer    reads = 0;

    assign dq = oe ? dq_o : 4'bzzzz;

    always @(negedge cs_d) begin
        if ($realtime - t_cs_rise < t_shsl)
            $fatal(1, "FAIL flash: CS# high for %0.1f ns < tSHSL %0.1f ns", $realtime - t_cs_rise, t_shsl);
        state = S_CMD; bits = 0; cmd = 8'h00;
    end
    always @(posedge cs_d) begin
        t_cs_rise = $realtime;
        state = S_IDLE;
        oe <= #(t_clqx) 1'b0;
    end

    always @(posedge sck_d) if (!cs_d) begin
        case (state)
            S_CMD: begin
                cmd = {cmd[6:0], dq[0]}; bits = bits + 1;
                if (bits == 8) begin
                    if (cmd != 8'hEB) $fatal(1, "FAIL flash: command %02h received (only EBh reads are allowed)", cmd);
                    state = S_ADDR; bits = 0; reads = reads + 1;
                end
            end
            S_ADDR: begin
                addr = {addr[ADDR_BITS-5:0], dq}; bits = bits + 1;
                if (bits == 6) begin state = S_MODE; bits = 0; end
            end
            S_MODE: begin
                mode = {mode[3:0], dq}; bits = bits + 1;
                if (bits == 2) begin
                    if (mode[5:4] == 2'b10) $fatal(1, "FAIL flash: continuous-read mode bits %02h not modelled", mode);
                    state = S_DUMMY; bits = 0;
                end
            end
            S_DUMMY: begin
                bits = bits + 1;
                if (bits == 4) begin state = S_DATA; nib_hi = 1'b1; end
            end
            default: ;
        endcase
    end

    // Output on SCK falling (mode 0): high nibble first, address auto-increments.
    always @(negedge sck_d) if (!cs_d && state == S_DATA) begin
        nib = nib_hi ? mem[addr][7:4] : mem[addr][3:0];
        oe   <= #(t_clqx) 1'b1;
        dq_o <= #(t_clqx) ~nib;
        dq_o <= #(t_clqv) nib;
        if (!nib_hi) addr = addr + 1'b1;
        nib_hi = !nib_hi;
    end
endmodule

module tb_bootrom_flash;
    reg clk = 0; always #8 clk = ~clk;          // clk_host 62.5 MHz
    reg reset = 1;
    reg n64_reset = 0, n64_nmi = 1, alel = 0, aleh = 1, rd = 1, wr = 1;
    reg host_drive = 0; reg [15:0] host_ad = 16'h0;
    wire [15:0] ad = host_drive ? host_ad : 16'hzzzz;
    wire f_sck, f_cs_n; wire [3:0] f_dq;

    localparam [23:0] OFFSET = 24'h40_0000;
    localparam integer WBYTES = 1 << 17;         // ROM_ADDR_BITS 16 -> 64 K words

    sn64_n64_endpoint #(.ROM_ADDR_BITS(16), .ROM_FROM_FLASH(1), .FLASH_OFFSET(OFFSET),
                        .FLASH_USE_USRMCLK(0)) dut (
        .clk(clk), .reset(reset), .cic_cpu_clk(clk),
        .n64_reset(n64_reset), .n64_nmi(n64_nmi), .n64_pi_alel(alel), .n64_pi_aleh(aleh),
        .n64_pi_read(rd), .n64_pi_write(wr), .n64_pi_ad(ad),
        .rom_we(1'b0), .rom_waddr(16'h0), .rom_wdata(16'h0),
        .flash_sck(f_sck), .flash_cs_n(f_cs_n), .flash_dq(f_dq),
        .joy1_buttons(), .joy2_buttons(), .joy1_stick_x(), .joy1_stick_y(),
        .run_request(), .soft_reset(), .region_mode(), .mailbox_seq(),
        .status_flags(16'h1234), .fault_flags(16'h0000), .build_id(16'h0102),
        .clk_snes(1'b0), .rst_snes_n(1'b0), .video_rgb(15'd0), .video_hde(1'b0), .video_vde(1'b0), .video_x(9'd0), .video_y(9'd0),
        .video_high_res(1'b0), .video_interlace(1'b0), .video_pal(1'b0), .audio_left(16'd0), .audio_right(16'd0), .audio_ready(1'b0),
        .n64_cic_clk(1'b1), .n64_cic_dq(), .n64_si_clk(1'b0), .cic_region(1'b0),
        .cic_invalid_region(), .cic_step(), .host_reset_event(), .host_nmi_event());

    tb_qspi_flash_model flash (.sck(f_sck), .cs_n(f_cs_n), .dq(f_dq));

    // ------------------------------------------------------------------
    // Image and expectation
    // ------------------------------------------------------------------
    reg [7:0] img [0:WBYTES-1];
    function automatic [31:0] xorshift(input [31:0] x);
        reg [31:0] y;
        begin y = x ^ (x << 13); y = y ^ (y >> 17); y = y ^ (y << 5); xorshift = y; end
    endfunction
    function automatic [15:0] expect_word(input [31:0] pi_addr);
        reg [16:0] a;
        begin a = pi_addr[16:0]; expect_word = {img[a], img[a + 17'd1]}; end
    endfunction

    // ------------------------------------------------------------------
    // Monitors
    // ------------------------------------------------------------------
    integer cycles = 0;
    wire dut_oe_s = dut.g_rom_flash.u_flash.u_mem.flash_qspi_inst.flash_dq_oe_s;
    wire dut_oe_q = dut.g_rom_flash.u_flash.u_mem.flash_qspi_inst.flash_dq_oe_q;
    wire ad_oe    = dut.pi.n64_pi_ad_oe;

    always @(posedge clk) begin
        cycles <= cycles + 1;
        if (cycles > 3_000_000) $fatal(1, "FAIL timeout");
        if (!reset && host_drive && ad_oe) $fatal(1, "FAIL AD driven by cartridge while host drives it (t=%0t)", $time);
    end
    // DQ ownership through the enables (two-state simulator).
    always @(dut_oe_s or dut_oe_q or flash.oe)
        if (flash.oe && (dut_oe_s || dut_oe_q)) $fatal(1, "FAIL DQ contention: FPGA and flash both drive (t=%0t)", $time);

    // First-word latency and streaming service time. n64_pi latches the low
    // address half and starts the memory request when ALE_H falls (alel_op),
    // before ALE_L falls, so latency is reported from both points.
    realtime t_alel = 0, t_alel_op = 0, t_last_ack = 0;
    reg      first_pending = 0, prev_req = 0, b2b = 0;
    realtime first_lat_op_max = 0, first_lat_alel_max = 0, stream_min = 1e9, stream_max = 0, restart_max = 0;
    integer  reads_at_ack = 0;
    // Ack time of each word of the current burst (FIFO is flushed at alel_op).
    realtime ack_t [0:4095];
    integer  ack_n = 0;
    always @(posedge clk) begin
        prev_req <= dut.mem_bus.request;
        if (dut.pi.alel_op) begin t_alel_op = $realtime; ack_n = 0; end
        if (dut.mem_bus.request && !prev_req)
            b2b = !first_pending && ($realtime - t_last_ack <= 40.0);
        if (dut.mem_bus.ack && !dut.mem_bus.write && !dut.pi.alel_op) begin
            if (dut.pi.read_port == 1 && ack_n < 4096) begin ack_t[ack_n] = $realtime; ack_n = ack_n + 1; end
            if (first_pending) begin
                if ($realtime - t_alel_op > first_lat_op_max) first_lat_op_max = $realtime - t_alel_op;
                if ($realtime - t_alel > first_lat_alel_max) first_lat_alel_max = $realtime - t_alel;
                first_pending = 0;
            end else if (b2b && flash.reads != reads_at_ack) begin
                // a new EBh inside a burst (window wrap): restart, not streaming
                if ($realtime - t_last_ack > restart_max) restart_max = $realtime - t_last_ack;
            end else if (b2b) begin
                if ($realtime - t_last_ack < stream_min) stream_min = $realtime - t_last_ack;
                if ($realtime - t_last_ack > stream_max) stream_max = $realtime - t_last_ack;
            end
            t_last_ack = $realtime;
            reads_at_ack = flash.reads;
        end
    end

    // Reads that found the PI read FIFO empty (first word of a burst: allowed,
    // n64_pi waits; later words: prefetch did not keep up).
    integer rd_since_ale = 0, first_waits = 0, stream_waits = 0;
    always @(posedge clk) begin
        if (dut.pi.alel_op) rd_since_ale <= 0;
        else if (dut.pi.read_op) begin
            if (dut.pi.read_port == 1 && dut.pi.read_fifo_empty) begin
                if (rd_since_ale == 0) first_waits = first_waits + 1;
                else begin
                    stream_waits = stream_waits + 1;
                    $display("INFO: read %0d after ALE found the PI FIFO empty (mem_bus address 0x%07h, t=%0t)",
                             rd_since_ale, dut.mem_bus.address, $time);
                end
            end
            rd_since_ale <= rd_since_ale + 1;
        end
    end

    // Margins per word: FIFO lead = host sample time - time the word's flash
    // ack wrote it into the PI read FIFO (how early the flash path delivered).
    // AD slack = host sample time - time the correct word appeared on AD.
    reg        watching = 0;
    reg [15:0] exp_cur = 0;
    realtime   t_valid = -1;
    always @(ad or ad_oe or watching)
        if (watching && t_valid < 0 && ad_oe && ad == exp_cur) t_valid = $realtime;

    realtime lead_first [0:3];
    realtime lead_stream [0:3];
    realtime slack_min [0:3];
    integer  words_p [0:3];
    integer  words_total = 0, bursts = 0;

    // ------------------------------------------------------------------
    // PI host model (address phase as tb_n64_endpoint.sv: ALE 11 -> 01 -> 00,
    // ale_step ns per step, default 300 as there; idle is ALE_H high, ALE_L low)
    // ------------------------------------------------------------------
    real ale_step = 300.0;
    task pi_addr(input [31:0] a);
        begin
            host_drive = 1; host_ad = a[31:16]; #100 aleh = 1; alel = 1; #(ale_step);
            host_ad = a[15:0]; aleh = 0; #(ale_step) alel = 0; t_alel = $realtime;
            #(ale_step) host_drive = 0;
        end
    endtask
    task pi_end; begin #100 aleh = 1; alel = 0; #300; end endtask

    // One burst: n reads from a with latency lat (ALE_L fall -> first /READ
    // fall), /READ low pwd (sample 20 ns before it rises), high rls.
    task burst(input [31:0] a, input integer n, input real lat, input real pwd, input real rls,
               input integer prof, input integer is_rom);
        reg [15:0] d;
        realtime lead, slack, t_s;
        integer i;
        begin
            first_pending = is_rom;
            pi_addr(a);
            if (t_alel + lat > $realtime) #(t_alel + lat - $realtime);
            for (i = 0; i < n; i = i + 1) begin
                exp_cur = is_rom ? expect_word(a + 2*i) : exp_cur; t_valid = -1; watching = is_rom;
                rd = 0; #(pwd - 20.0); d = ad; t_s = $realtime; watching = 0; #20.0 rd = 1;
                if (is_rom) begin
                    if (d !== exp_cur)
                        $fatal(1, "FAIL P%0d read 0x%08h (word %0d of burst at 0x%08h): got %04h expected %04h",
                               prof, a + 2*i, i, a, d, exp_cur);
                    if (i >= ack_n) $fatal(1, "FAIL P%0d word %0d sampled before its flash ack", prof, i);
                    lead  = t_s - ack_t[i];
                    slack = (t_valid < 0) ? 0 : (t_s - t_valid);
                    if (i == 0) begin if (lead < lead_first[prof]) lead_first[prof] = lead; end
                    else        begin if (lead < lead_stream[prof]) lead_stream[prof] = lead; end
                    if (slack < slack_min[prof]) slack_min[prof] = slack;
                    words_p[prof] = words_p[prof] + 1; words_total = words_total + 1;
                end else begin
                    exp_cur = d;
                end
                #(rls);
            end
            pi_end; bursts = bursts + 1;
        end
    endtask

    // PI DMA of len bytes from a in pages of 512 bytes (one ALE per page).
    task dma(input [31:0] a, input integer len, input real lat, input real pwd, input real rls, input integer prof);
        integer p;
        begin
            for (p = 0; p < len; p = p + 512) begin
                burst(a + p, (len - p >= 512) ? 256 : (len - p) / 2, lat, pwd, rls, prof, 1);
                #200;
            end
        end
    endtask

    task pi_write1(input [15:0] d);
        begin #100 host_drive = 1; host_ad = d; #100 wr = 0; #400 wr = 1; #100 host_drive = 0; #200; end
    endtask

    // ------------------------------------------------------------------
    // Test sequence
    // ------------------------------------------------------------------
    integer fault = 0, i, p3_pwd = 13, p3_rls = 3;     // P3 strobes in PI cycles (PWD+1, RLS+1)
    real    p2_lat = 1040.0, t_arg = 0;
    reg [31:0] seed;
    reg [23:0] img_base;
    localparam real CYC = 16.0;                  // one PI (RCP) cycle at 62.5 MHz
    initial begin
        void'($value$plusargs("fault=%d", fault));
        void'($value$plusargs("p2_lat=%f", p2_lat));
        void'($value$plusargs("ale_step=%f", ale_step));
        void'($value$plusargs("p3_pwd=%d", p3_pwd));
        void'($value$plusargs("p3_rls=%d", p3_rls));
        for (i = 0; i < 4; i = i + 1) begin lead_first[i] = 1e9; lead_stream[i] = 1e9; slack_min[i] = 1e9; words_p[i] = 0; end

        // Flash contents: erased (0xFF) everywhere, image at the offset.
        for (i = 0; i < (1 << 24); i = i + 1) flash.mem[i] = 8'hFF;
        seed = 32'h5EED_1234;
        for (i = 0; i < WBYTES; i = i + 1) begin seed = xorshift(seed); img[i] = seed[15:8]; end
        img_base = OFFSET + ((fault == 2) ? 24'd2 : 24'd0);
        for (i = 0; i < WBYTES; i = i + 1) flash.mem[img_base + i] = img[i];
        if (fault == 1) flash.mem[OFFSET + 24'h1000 + 24'd301] = ~img[24'h1000 + 301];
        if ($value$plusargs("t_sck=%f", t_arg))  flash.t_sck  = t_arg;
        if ($value$plusargs("t_clqv=%f", t_arg)) flash.t_clqv = t_arg;
        if (fault == 3) flash.t_clqv = 40.0;
        $display("INFO: image 128 KiB at flash 0x%06h (DUT FLASH_OFFSET 0x%06h), fault=%0d, flash t_sck=%0.1f t_clqv=%0.1f ns",
                 img_base, OFFSET, fault, flash.t_sck, flash.t_clqv);

        repeat (5) @(negedge clk); reset = 0;
        repeat (5) @(negedge clk); n64_reset = 1;
        repeat (10) @(negedge clk);

        // P0: header word at the slow boot-default timing
        burst(32'h1000_0000, 2, 256*CYC, 256*CYC, 4*CYC, 0, 1);
        // P1: IPL3-style DMA from 0x1000_1000 (4 pages), then bursts at other offsets
        dma(32'h1000_1000, 2048, 65*CYC, 19*CYC, 4*CYC, 1);
        burst(32'h1000_0040,  8, 65*CYC, 19*CYC, 4*CYC, 1, 1);
        burst(32'h1000_7FF2, 20, 65*CYC, 19*CYC, 4*CYC, 1, 1);   // unaligned to a page
        burst(32'h1001_FFF8, 16, 65*CYC, 19*CYC, 4*CYC, 1, 1);   // crosses the window end: wraps to word 0
        burst(32'h1003_0010,  8, 65*CYC, 19*CYC, 4*CYC, 1, 1);   // above the window: mirrored
        // Mailbox still answers in the flash build
        burst(32'h1FFF_0000, 1, 65*CYC, 19*CYC, 4*CYC, 1, 0);
        if (exp_cur !== 16'h534E) $fatal(1, "FAIL mailbox MAGIC %04h", exp_cur);
        // Writes through the 0x1FFE window must not reach the flash (the model
        // fails on any command other than EBh); the window still reads the ROM.
        pi_addr(32'h1FFE_0000); #300; pi_write1(16'hDEAD); pi_write1(16'hBEEF); pi_end;
        burst(32'h1FFE_0000, 4, 65*CYC, 19*CYC, 4*CYC, 1, 1);
        // Restart in the middle of an open stream at a new offset
        burst(32'h1000_5000, 3, 65*CYC, 19*CYC, 4*CYC, 1, 1);
        burst(32'h1000_0100, 6, 65*CYC, 19*CYC, 4*CYC, 1, 1);
        // P2: tb_n64_endpoint strobes (420 ns low, sample at 400, 400 ns high)
        burst(32'h1000_2468, 64, p2_lat, 420.0, 400.0, 2, 1);
        // P3: fast PI timing, one full page
        dma(32'h1000_3000, 512, 65*CYC, p3_pwd*CYC, p3_rls*CYC, 3);

        $display("STATS: ALE step %0.0f ns; first-word latency max %0.0f ns from address latch (ALE_H fall), %0.0f ns from ALE_L fall",
                 ale_step, first_lat_op_max, first_lat_alel_max);
        $display("STATS: streaming ack interval %0.0f..%0.0f ns/word; in-burst restart (window wrap) %0.0f ns; P3 strobes %0.0f ns/word",
                 stream_min, stream_max, restart_max, (p3_pwd + p3_rls) * CYC);
        $display("STATS: min FIFO lead first/later words (ns): P0 %0.0f/-  P1 %0.0f/%0.0f  P2 %0.0f/%0.0f  P3 %0.0f/%0.0f",
                 lead_first[0], lead_first[1], lead_stream[1], lead_first[2], lead_stream[2],
                 lead_first[3], lead_stream[3]);
        $display("STATS: min AD slack (valid word on AD -> host sample, ns): P0 %0.0f  P1 %0.0f  P2 %0.0f  P3 %0.0f",
                 slack_min[0], slack_min[1], slack_min[2], slack_min[3]);
        $display("STATS: FIFO-empty reads: first word %0d, later words %0d; flash EBh commands %0d",
                 first_waits, stream_waits, flash.reads);
        $display("PASS: bootrom flash window: %0d words in %0d bursts match the image (P0 %0d, P1 %0d, P2 %0d, P3 %0d), mailbox ok, writes blocked, no DQ contention (%0d clocks)",
                 words_total, bursts, words_p[0], words_p[1], words_p[2], words_p[3], cycles);
        $finish;
    end
endmodule
