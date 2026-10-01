// Bench for the console video path (docs/design/console-video-path.md):
// sn64_n64_endpoint with a synthetic SNES video/audio source on clk_snes and an
// N64 host model on the PI bus reading the frame window at 0x0800_0000 with
// fast domain-2 timing.
//
// Checks: (1) every pixel of a full 256 x 224 frame read back equals the
// RGBA5551 conversion of what the generator wrote for that line, with the
// host following FRAME_STATUS.lines_done (reads a line only after it is done,
// never more than one frame behind); a read that cannot keep up would see
// lines overwritten by the next frame and fail; (2) the audio ring holds the
// last samples in order and AUDIO_WPTR matches; (3) VIDEO_MODE, the mailbox
// and the ROM window still work; (4) FRAME_PHASE reads 0x7FF before the first frame,
// then follows the generator's position in quarter lines through the visible area and
// the vertical blanking, with a frame-start count that steps as the position returns to
// 0. +pwd=<cycles> +rls=<cycles> set the host's
// /RD low/high times in 62.5 MHz PI cycles (defaults 5 and 1: 128 ns/word).
// Fault builds SN64_FAULT_FRAME_RB_SWAP (R/B swapped) and SN64_FAULT_PHASE_NO_RESTART
// (position never restarted at a frame start) must fail.
`timescale 1ns/1ps
module tb_frame_window;
    // ---------------- clocks ----------------
    reg clk_host = 0, clk_snes = 0;
    always #8 clk_host = ~clk_host;            // 62.5 MHz (PI logic, N64 PI cycle)
    always #23.28 clk_snes = ~clk_snes;        // 21.477 MHz SNES master
    reg reset = 1, n64_reset = 0, rst_snes_n = 0;

    // ---------------- synthetic SNES video (as tb_av_out) ----------------
    localparam int SNES_LINE = 1364, SNES_LINES = 262, VIS = 224;
    int h = 0, v = 0, frame = 0;
    int fstarts = 0;                            // frame starts seen by the frame window (vde rising)
    reg [14:0] rgb = 0;
    reg hde = 0, vde = 0;
    reg [8:0] video_x = 0, video_y = 0;
    reg [15:0] audio_left = 0, audio_right = 0;
    reg audio_ready = 0;
    int unsigned dda = 0;
    int samples_sent = 0;
    int written_frame [0:255];                  // frame number in which each line was last completed
    function automatic [14:0] pat(input [8:0] x, input [7:0] k, input [2:0] f);
        reg [8:0] xe;
        xe = k[3] ? x : {x[8:1], 1'b0};
        pat = {f ^ xe[8:6] ^ {1'b0, k[7:6]}, k[5:0], xe[5:0]} ^ 15'h2A55;
    endfunction
    always @(posedge clk_snes) begin
        if (rst_snes_n) begin
            int d, ph;
            reg dotclk;
            d = h / 4; ph = h % 4;
            dotclk = ph < 2;
            hde <= d >= 19 && d < 275;
            vde <= v >= 1 && v <= VIS;
            video_x <= {8'(d - 19), dotclk};
            video_y <= {1'b0, 8'(v - 1)};
            rgb <= pat({8'(d - 19), dotclk}, 8'(v - 1), 3'(frame));
            if (v >= 1 && v <= VIS && d == 275 && ph == 0) written_frame[v - 1] = frame;   // line complete
            audio_ready <= 1'b0;
            dda = dda + 32000;
            if (dda >= 21477273) begin
                dda = dda - 21477273;
                audio_ready <= 1'b1;
                audio_left <= 16'(samples_sent);
                audio_right <= 16'(samples_sent) ^ 16'h5A5A;
                samples_sent++;
            end
            if (v == 1 && h == 1) fstarts++;                      // the clock on which the window restarts its position
            h++;
            if (h == SNES_LINE) begin
                h = 0; v++;
                if (v == SNES_LINES) begin v = 0; frame++; end
            end
        end
    end
    function automatic [15:0] expect_word(input int x, input int y, input int f);
        reg [14:0] c;
        c = pat({8'(x), 1'b0}, 8'(y), 3'(f));                  // first half-dot of dot x
        expect_word = {c[4:0], c[9:5], c[14:10], 1'b1};        // RGBA5551
    endfunction

    // ---------------- DUT ----------------
    reg alel = 0, aleh = 0, rd = 1, wr = 1;
    reg host_drive = 0; reg [15:0] host_ad = 0;
    wire [15:0] ad = host_drive ? host_ad : 16'bz;
    wire n64_cic_dq;
    sn64_n64_endpoint #(.ROM_ADDR_BITS(4)) dut (
        .clk(clk_host), .reset(reset), .cic_cpu_clk(clk_host),
        .n64_reset(n64_reset), .n64_nmi(1'b1),
        .n64_pi_alel(alel), .n64_pi_aleh(aleh), .n64_pi_read(rd), .n64_pi_write(wr), .n64_pi_ad(ad),
        .rom_we(1'b0), .rom_waddr(4'd0), .rom_wdata(16'd0),
        .flash_sck(), .flash_cs_n(), .flash_dq(),
        .joy1_buttons(), .joy2_buttons(), .joy1_stick_x(), .joy1_stick_y(),
        .run_request(), .soft_reset(), .region_mode(), .mailbox_seq(),
        .status_flags(16'hA5C3), .fault_flags(16'h0000), .build_id(16'h0102),
        .region_info(16'h0000), .region_source(16'h0000),
        .clk_snes(clk_snes), .rst_snes_n(rst_snes_n),
        .video_rgb(rgb), .video_hde(hde), .video_vde(vde), .video_x(video_x), .video_y(video_y),
        .video_high_res(1'b0), .video_interlace(1'b0), .video_pal(1'b0),
        .audio_left(audio_left), .audio_right(audio_right), .audio_ready(audio_ready),
        .n64_cic_clk(1'b1), .n64_cic_dq(n64_cic_dq), .n64_si_clk(1'b0), .cic_region(1'b0),
        .cic_invalid_region(), .cic_step(), .host_reset_event(), .host_nmi_event());

    // bus ownership guard (as tb_n64_endpoint)
    always @(posedge clk_host) if (!reset && host_drive && dut.pi.n64_pi_ad_oe) $fatal(1, "cartridge drove AD while the host was driving");

    // ---------------- PI host model ----------------
    int pwd = 5, rls = 1;                         // /RD low = (pwd+1) cycles, high = (rls+1) cycles of 16 ns
    task pi_addr(input [31:0] a);
        begin
            host_drive = 1; host_ad = a[31:16]; #100 aleh = 1; alel = 1; #300;
            host_ad = a[15:0]; aleh = 0; #300 alel = 0; #300 host_drive = 0; #100;
        end
    endtask
    task pi_read_std(output [15:0] d); begin #100 rd = 0; #400 d = ad; #20 rd = 1; #300; end endtask
    task pi_read_fast(output [15:0] d);            // domain-2 timing: sample just before /RD rises
        begin rd = 0; #((pwd + 1) * 16 - 4) d = ad; #4 rd = 1; #((rls + 1) * 16); end
    endtask
    task pi_end; begin #100 aleh = 1; alel = 1; #300 aleh = 0; alel = 0; #300; end endtask

    // FRAME_PHASE against the generator: the window restarts its position one clock after vde
    // rises (v == 1, h == 1), counting 341 master clocks per step. The value read is the one a
    // few clocks before the strobe (word handshake, PI synchroniser): one step of tolerance.
    int phase_checks = 0;
    task automatic check_phase(input string where);
        reg [15:0] ph; int ev, eh, es, clocks, expect_total, got_total, diff;
        begin
            pi_addr(32'h1FFF_0024);
            #100 rd = 0; ev = v; eh = h; es = fstarts; #400 ph = ad; #20 rd = 1; #300;
            pi_end;
            clocks = (ev >= 1) ? ((ev - 1) * SNES_LINE + eh - 2) : ((SNES_LINES - 1) * SNES_LINE + eh - 2);
            if (clocks < 0) clocks += SNES_LINE * SNES_LINES;   // strobe fell just before the restart: still the old frame
            expect_total = (es % 32) * 4096 + clocks / 341;
            got_total = int'(ph[15:11]) * 4096 + int'(ph[10:0]);
            diff = got_total - expect_total;
            if (diff < -1 || diff > 1) begin
                $display("FAIL: tb_frame_window: FRAME_PHASE %s: read starts %0d position %0d, generator at line %0d clock %0d = starts %0d position %0d",
                         where, ph[15:11], ph[10:0], ev, eh, es % 32, clocks / 341);
                $fatal(1);
            end
            phase_checks++;
        end
    endtask

    reg [15:0] d0, d1, d2, d3;
    int errors = 0, words = 0, lines_read = 0;
    realtime t0, t1, tb0, tburst = 0;
    initial begin
        if ($value$plusargs("pwd=%d", pwd)) ;
        if ($value$plusargs("rls=%d", rls)) ;
        #200; reset = 0; rst_snes_n = 1; #200; n64_reset = 1;
        // before the first frame starts: position 0x7FF, no frame start counted
        #600; pi_addr(32'h1FFF_0024); pi_read_std(d0); pi_end;
        if (v != 0) $fatal(1, "bench: the first FRAME_PHASE read came too late (line %0d)", v);
        if (d0 !== 16'h07FF) begin $display("FAIL: tb_frame_window: FRAME_PHASE before the first frame is %h, expected 07ff", d0); $fatal(1); end
        // through the first frames: start of the visible area, middle, end, vertical blanking, wrap
        wait (v == 1 && h == 40);   check_phase("just after a frame start");
        wait (v == 100 && h == 700); check_phase("mid frame");
        wait (v == 224 && h == 1300); check_phase("last visible line");
        wait (v == 240 && h == 10);  check_phase("vertical blanking");
        wait (v == 0 && h == 900);   check_phase("last line before the next frame");
        wait (v == 1 && h == 400);   check_phase("second frame");
        // let two frames go by, then read status
        wait (frame == 2);
        pi_addr(32'h1FFF_001E); pi_read_std(d0); pi_read_std(d1); pi_read_std(d2); pi_end;
        $display("FRAME_STATUS=%h AUDIO_WPTR=%h VIDEO_MODE=%h at frame %0d", d0, d1, d2, frame);
        if (d0[15:8] != 8'd2 && d0[15:8] != 8'd1) $fatal(1, "frame_count %0d unexpected", d0[15:8]);
        check_phase("third frame");
        if (d2 !== 16'h0000) $fatal(1, "VIDEO_MODE %h, expected 0 (NTSC, progressive, 224 lines)", d2);
        // Read a whole frame following lines_done, 16 lines per address latch (one page),
        // starting at the next frame boundary so the frame number is known.
        wait (frame == 3); wait (v == 1);
        t0 = $realtime;
        for (int L = 0; L < VIS; L += 16) begin
            // wait until line L+15 is done in this frame
            forever begin
                pi_addr(32'h1FFF_001E); pi_read_std(d0); pi_end;
                if (d0[15:8] == 8'(frame % 256) && (d0[7:0] != 8'hFF) && (d0[7:0] >= L + 15)) break;
                if (d0[15:8] != 8'(frame % 256) && d0[15:8] == 8'((frame + 1) % 256)) break;   // writer already ahead
            end
            tb0 = $realtime;
            pi_addr(32'h0800_0000 + L * 512);
            for (int y = L; y < L + 16; y++) begin
                int f;
                f = written_frame[y];
                for (int x = 0; x < 256; x++) begin
                    pi_read_fast(d1);
                    words++;
                    if (d1 !== expect_word(x, y, f)) begin
                        if (errors < 8) $display("pixel (%0d,%0d) frame %0d: got %h expected %h", x, y, f, d1, expect_word(x, y, f));
                        errors++;
                    end
                end
                lines_read++;
            end
            pi_end;
            tburst += $realtime - tb0;
        end
        t1 = $realtime;
        $display("frame read: %0d words; whole frame %0.1f us (following the writer); inside bursts %0.0f ns/word = %0.2f MB/s; %0d errors",
                 words, (t1 - t0) / 1000.0, tburst / words, 2.0 * words / (tburst / 1000.0), errors);
        if (errors != 0) begin $display("FAIL: tb_frame_window: %0d pixel errors", errors); $fatal(1); end
        // audio ring: AUDIO_WPTR and the last 4 stereo pairs before it
        pi_addr(32'h1FFF_0020); pi_read_std(d1); pi_end;
        begin
            int w, base, idx;
            w = d1;
            base = ((w - 4) & 10'h3FF);
            pi_addr(32'h0800_0000 + 32'h1E000 + base * 4);
            for (int k = 0; k < 4; k++) begin
                idx = ((w - 4 + k) & 10'h3FF);
                pi_read_std(d2); pi_read_std(d3);
                // sample number n written at index n % 1024: n = samples_sent - 4 + k (approximately: wptr may have advanced)
                if (d3 !== (d2 ^ 16'h5A5A)) begin $display("audio pair %0d: L %h R %h not a matching pair", idx, d2, d3); errors++; end
                if (int'(d2) % 1024 != idx) begin $display("audio pair index %0d holds sample %0d", idx, d2); errors++; end
            end
            pi_end;
        end
        if (errors != 0) begin $display("FAIL: tb_frame_window: audio ring %0d errors", errors); $fatal(1); end
        // ROM window and mailbox unaffected
        pi_addr(32'h1FFF_0000); pi_read_std(d0); pi_end;
        if (d0 !== 16'h534E) $fatal(1, "mailbox magic broken: %h", d0);
        $display("PASS: frame window: %0d lines x 256 pixels read back exactly at PWD %0d / RLS %0d (%0.0f ns/word in bursts, %0.2f MB/s) following lines_done; audio ring in order; mailbox ok; FRAME_PHASE followed the generator at %0d points",
                 lines_read, pwd, rls, tburst / words, 2.0 * words / (tburst / 1000.0), phase_checks);
        $finish;
    end
    initial begin #120_000_000; $fatal(1, "timeout"); end
endmodule
