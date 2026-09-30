// SPDX-License-Identifier: GPL-3.0-or-later
// Self-checking testbench for fpga/rtl/sn64_av_out.sv.
//
// A SNES-timing model (4-clock dots, X_OUT = {dot, DOT_CLK}, HDE on dots
// 19..274, VDE on lines 1..224 or 1..239) drives a known test pattern and
// ~32 kHz stereo audio into the DUT. The testbench deserialises the DUT's
// serial TMDS outputs using the TMDS clock channel for word alignment, then
// decodes control tokens, video (8b/10b) and data islands (TERC4 + BCH ECC)
// and checks:
//   - every active pixel of every steady-state frame against the pattern,
//     including the black border and the 256/512 half-dot handling
//   - frame sequence (no dropped, repeated or torn SNES frames)
//   - hsync width, line period, vsync width, lines per frame, active area
//   - data-island structure, packet ECC, InfoFrame presence, AVI InfoFrame
//     VIC / picture aspect / checksum, ACR N/CTS, and audio sample continuity
//     (every SNES sample recovered, in order)
//   - frame lock: after the start-up lock and one overscan change, every
//     lock event is within +-LOCK_TOL (8) pixels and needs no re-phase
//
// Regions:
//   default          NTSC: 1364 master clocks x 262 lines, with the V=240 line
//                    1360 clocks in every other frame (hardware short line), pixel =
//                    master x 74932/59561 (one HDMI frame = the mean SNES frame),
//                    858 x 524 raster, VIC 2
//   SN64_TB_PAL      PAL:  1364 master clocks x 312 lines (hardware and the core
//                    with long dots restored), pixel = master x 432/341,
//                    864 x 624 raster, VIC 17, picture aspect 4:3
//   SN64_TB_ASYNC_27M NTSC timing with an independent 27.000 MHz pixel clock
//
// Time base: abstract ticks. NTSC: 390 ticks = 1 SNES master clock and 310
// ticks = 1 pixel clock (39/31). PAL: 216 and 170 ticks (108/85).
`timescale 1ns/1ps
module tb_av_out;
    localparam int N_FRAMES = 9;
    localparam int WARMUP = 1;       // HDMI frame 0 contains the initial lock acquisition
    localparam int H_ACTIVE = 720;
    localparam [14:0] PAT_XOR = 15'h2A55;

`ifdef SN64_TB_PAL
    localparam bit PAL = 1;
    localparam int H_TOTAL = 864, V_TOTAL = 624, V_ACTIVE = 576;
    localparam int HS_W = 64, VS_LINES = 5, V_CENTER = 288;
    localparam int SNES_LINE = 1364, SNES_LINES = 312;
    localparam int EXP_VIC = 17;
    localparam [1:0] EXP_ASPECT = 2'b01;          // 4:3
    // pixel = master x 432/341
    localparam int MH = 2160, PH = 1705, XH = 341, SO = 170;
    // CTS = pixel clocks per 32 samples = (432/341) x 32 x 21477273/32000 = 27208.7
    localparam int CTS_LO = 27207, CTS_HI = 27211;
    localparam bit ASYNC = 0;
    localparam string CLOCKING = "PAL, pixel = master*432/341";
`else
    localparam bit PAL = 0;
    localparam int H_TOTAL = 858, V_TOTAL = 524, V_ACTIVE = 480;
    localparam int HS_W = 62, VS_LINES = 6, V_CENTER = 240;
    localparam int SNES_LINE = 1364, SNES_LINES = 262;
    localparam int EXP_VIC = 2;
    localparam [1:0] EXP_ASPECT = 2'b00;          // NTSC AVI InfoFrame unchanged: no data (VIC 2 implies 4:3)
`ifdef SN64_TB_ASYNC_27M
    // Clock plan fallback: pixel clock 27.000 MHz from its own reference.
    // 27 / 21.4772727 = 44/35, so the raster drifts ~339 pixels per SNES frame
    // and must be re-phased every frame.
    localparam int MH = 220, PH = 175, XH = 35, SO = 17;
    localparam int CTS_LO = 26998, CTS_HI = 27002;
    localparam bit ASYNC = 1;
    localparam string CLOCKING = "async 27.000 MHz";
`else
    // Intended clocking: pixel clock = master * 74932/59561 from the master clock.
    localparam int MH = 374660, PH = 297805, XH = 59561, SO = 29780;
    localparam int CTS_LO = 27018, CTS_HI = 27021;
    localparam bit ASYNC = 0;
    localparam string CLOCKING = "pixel = master*74932/59561";
`endif
`endif
    reg clk_snes = 0, clk_pixel = 0, clk_x5 = 0, clk_samp = 0;
    initial forever #MH clk_snes = ~clk_snes;
    initial forever #PH clk_pixel = ~clk_pixel;
    initial forever #XH clk_x5 = ~clk_x5;
    initial begin #SO; forever #XH clk_samp = ~clk_samp; end

    reg rst_snes_n = 0, rst_pixel_n = 0;

    // ---------------- SNES timing and pattern model ----------------
    function automatic int vis_sched(input int f);
        vis_sched = (f < 4) ? 224 : 239;
    endfunction
    function automatic [14:0] pat(input [8:0] x, input [7:0] k, input [2:0] f);
        reg [8:0] xe;
        xe = k[3] ? x : {x[8:1], 1'b0};   // lines with k[3]=1 carry hi-res content
        pat = {f ^ xe[8:6] ^ {1'b0, k[7:6]}, k[5:0], xe[5:0]} ^ PAT_XOR;
    endfunction

    int h = 0, v = 0, frame = 0;
    reg [14:0] rgb = 0;
    reg hde = 0, vde = 0;
    reg [8:0] video_x = 0, video_y = 0;
    reg [15:0] audio_left = 0, audio_right = 0;
    reg audio_ready = 0;
    int unsigned dda = 0;
    int samples_sent = 0;
    bit sim_done = 0;

    always @(posedge clk_snes) begin
        if (rst_snes_n) begin
            int d, ph, vis;
            reg dotclk;
            d = h / 4; ph = h % 4;
            vis = vis_sched(frame);
            dotclk = ph < 2;
            hde <= d >= 19 && d < 275;
            vde <= v >= 1 && v <= vis;
            video_x <= {8'(d - 19), dotclk};
            video_y <= {1'b0, 8'(v - 1)};
            rgb <= pat({8'(d - 19), dotclk}, 8'(v - 1), 3'(frame));
            // audio: DDA at 32000 / 21477273 per master clock (a fixed ratio to the
            // master in both regions, like the core's CEGen)
            audio_ready <= 1'b0;
            dda = dda + 32000;
            if (dda >= 21477273) begin
                dda = dda - 21477273;
                audio_ready <= 1'b1;
                audio_left <= 16'(samples_sent);
                audio_right <= 16'(samples_sent) ^ 16'h5A5A;
                samples_sent++;
            end
            h++;
            // NTSC hardware short line: V=240 is 1360 clocks in every other frame
            if (h == ((!PAL && v == 240 && frame[0]) ? SNES_LINE - 4 : SNES_LINE)) begin
                h = 0;
                v++;
                if (v == SNES_LINES) begin
                    v = 0;
                    frame++;
                    if (frame == N_FRAMES) sim_done = 1;
                end
            end
        end
    end

    // ---------------- DUT ----------------
    wire [2:0] tmds;
    wire tmds_clock;
    wire locked, mode_pal;
    wire signed [19:0] lock_error;
    wire [7:0] rephase_count;
    sn64_av_out dut (
        .clk_snes(clk_snes), .rst_snes_n(rst_snes_n), .rgb(rgb), .hde(hde), .vde(vde),
        .video_x(video_x), .video_y(video_y), .audio_left(audio_left), .audio_right(audio_right),
        .audio_ready(audio_ready), .pal(PAL), .clk_pixel(clk_pixel), .clk_pixel_x5(clk_x5),
        .rst_pixel_n(rst_pixel_n), .tmds(tmds), .tmds_clock(tmds_clock),
        .locked(locked), .lock_error(lock_error), .rephase_count(rephase_count), .mode_pal(mode_pal));

    // ---------------- deserialiser ----------------
    reg [9:0] sr0 = 0, sr1 = 0, sr2 = 0;
    reg prev_clk_bit = 0;
    int nbits = 0;
    always @(posedge clk_samp or negedge clk_samp) begin
        if (tmds_clock && !prev_clk_bit && nbits >= 10) process_symbol(sr0, sr1, sr2);
        prev_clk_bit <= tmds_clock;
        sr0 <= {tmds[0], sr0[9:1]};
        sr1 <= {tmds[1], sr1[9:1]};
        sr2 <= {tmds[2], sr2[9:1]};
        nbits++;
    end

    // ---------------- decoder ----------------
    function automatic bit ctrl_dec(input [9:0] w, output [1:0] d);
        ctrl_dec = 1;
        case (w)
            10'b1101010100: d = 2'b00;
            10'b0010101011: d = 2'b01;
            10'b0101010100: d = 2'b10;
            10'b1010101011: d = 2'b11;
            default: begin d = 2'b00; ctrl_dec = 0; end
        endcase
    endfunction
    function automatic bit terc4_dec(input [9:0] w, output [3:0] d);
        terc4_dec = 1;
        case (w)
            10'b1010011100: d = 4'h0; 10'b1001100011: d = 4'h1;
            10'b1011100100: d = 4'h2; 10'b1011100010: d = 4'h3;
            10'b0101110001: d = 4'h4; 10'b0100011110: d = 4'h5;
            10'b0110001110: d = 4'h6; 10'b0100111100: d = 4'h7;
            10'b1011001100: d = 4'h8; 10'b0100111001: d = 4'h9;
            10'b0110011100: d = 4'hA; 10'b1011000110: d = 4'hB;
            10'b1010001110: d = 4'hC; 10'b1001110001: d = 4'hD;
            10'b0101100011: d = 4'hE; 10'b1011000011: d = 4'hF;
            default: begin d = 4'h0; terc4_dec = 0; end
        endcase
    endfunction
    function automatic [7:0] tmds_dec8(input [9:0] w);
        reg [7:0] q;
        q = w[9] ? ~w[7:0] : w[7:0];
        tmds_dec8[0] = q[0];
        for (int i = 1; i < 8; i++) tmds_dec8[i] = w[8] ? (q[i] ^ q[i-1]) : ~(q[i] ^ q[i-1]);
    endfunction
    function automatic [7:0] next_ecc(input [7:0] ecc, input bit b);
        next_ecc = (ecc >> 1) ^ ((ecc[0] ^ b) ? 8'b10000011 : 8'd0);
    endfunction
    function automatic [7:0] ex5(input [4:0] c);
        ex5 = {c, c[4:2]};
    endfunction

    localparam int S_CTRL = 0, S_VG = 1, S_VID = 2, S_IG = 3, S_ISL = 4;
    int state = S_CTRL;
    longint sym = 0;
    reg hs = 1, vs = 1;             // decoded sync levels (active low)
    reg hs_act_q = 0, vs_act_q = 0;
    longint last_hs_edge = -1, hs_start = 0, vs_start = 0;
    int guard_len = 0, run_len = 0, isl_len = 0;
    reg [23:0] line_px [0:H_ACTIVE-1];

    // per-frame accumulators
    int hframe = -1;                // HDMI frame index (vsync count)
    int lines_in_frame = 0, runs_in_frame = 0, bad_period = 0;
    int pkt_acr = 0, pkt_aud = 0, pkt_avi = 0, pkt_aif = 0, pkt_spd = 0, pkt_null = 0;
    bit identified = 0, transition = 0;
    int v_off_seen = 0, f_seen = 0, f_real = 0, vis_disp = 0;
    int rephase_at_start = 0;

    // global results
    int errors = 0, pixel_errors = 0, pixels_checked = 0, frames_checked = 0;
    int protocol_errors = 0, ecc_errors = 0, audio_errors = 0, audio_rx = 0;
    int last_f = -1, frame_seq_errors = 0;
    int acr_n = -1, acr_cts_min = 1 << 30, acr_cts_max = 0, acr_count = 0;
    int hsync_width_errors = 0, vsync_width_errors = 0, run_errors = 0;
    int frame_count_errors = 0, island_len_errors = 0, infoframe_errors = 0;
    int avi_checked = 0, avi_errors = 0, avi_vic = -1, avi_aspect = -1;
    int warmup_cut_runs = 0;
    int last_audio_l = -1;
    int steady_lock_samples = 0, steady_lock_bad = 0;
    reg [31:0] hdr_bits;
    reg [63:0] sub_bits [0:3];

    task automatic report_error(input string msg);
        errors++;
        if (errors <= 12) $display("ERROR @sym %0d frame %0d: %s", sym, hframe, msg);
    endtask

    task automatic finish_line();
        int y, kk, pic, fi;
        reg [23:0] expv;
        reg [14:0] p15;
        bit any_pic, any_border;
        y = runs_in_frame;
        runs_in_frame++;
        // The start-up lock (first event after reset) re-phases at whatever line the
        // free-running raster is on, so it may cut one active run in the warm-up
        // frame; that is counted and reported, not failed. Every later run must be exact.
        if (run_len != H_ACTIVE) begin
            if (hframe >= WARMUP) begin run_errors++; report_error($sformatf("active run %0d pixels", run_len)); end
            else begin
                warmup_cut_runs++;
                $display("note: warm-up frame %0d: active run of %0d pixels cut by the start-up lock", hframe, run_len);
            end
        end
        if (hframe < WARMUP || transition) return;
        any_pic = 0; any_border = 0;
        for (int x = 0; x < H_ACTIVE; x++) begin
            if (line_px[x] != 0) begin
                if (x >= 104 && x < 616) any_pic = 1; else any_border = 1;
            end
        end
        if (!identified) begin
            if (!any_pic && !any_border) begin pixels_checked += H_ACTIVE; return; end
            // first picture line: k = 0, px = 0 carries the frame number
            p15 = {line_px[104][7:3], line_px[104][15:11], line_px[104][23:19]} ^ PAT_XOR;
            f_seen = p15[14:12];
            // frame number is carried mod 8; extend it forward from the last one seen
            f_real = (last_f < 0) ? f_seen : last_f + ((f_seen - last_f) & 7);
            identified = 1;
            v_off_seen = y;
            vis_disp = (f_real == 0) ? 224 : vis_sched(f_real - 1);
            transition = (f_real != 0) && vis_sched(f_real) != vis_sched(f_real - 1);
            if (transition) return;
            if (v_off_seen != V_CENTER - vis_disp)
                report_error($sformatf("picture starts on line %0d, expected %0d", v_off_seen, V_CENTER - vis_disp));
        end
        for (int x = 0; x < H_ACTIVE; x++) begin
            kk = (y - v_off_seen) / 2;
            pic = (x >= 104 && x < 616 && y >= v_off_seen && (y - v_off_seen) < 2 * vis_disp);
            if (pic) begin
                p15 = pat(9'(x - 104), 8'(kk), 3'(f_seen));
                expv = {ex5(p15[4:0]), ex5(p15[9:5]), ex5(p15[14:10])};
            end else expv = 24'd0;
            pixels_checked++;
            if (line_px[x] !== expv) begin
                pixel_errors++;
                if (pixel_errors <= 4)
                    report_error($sformatf("pixel (%0d,%0d) got %06h expected %06h", x, y, line_px[x], expv));
            end
        end
    endtask

    task automatic finish_frame();
        int rp;
        rp = rephase_count;
        if (hframe >= WARMUP) begin
            if (runs_in_frame != V_ACTIVE) begin frame_count_errors++; report_error($sformatf("%0d active lines", runs_in_frame)); end
            if (rp == rephase_at_start && lines_in_frame != V_TOTAL) begin
                frame_count_errors++; report_error($sformatf("%0d lines in frame", lines_in_frame));
            end
            if (pkt_avi == 0 || pkt_aif == 0) begin infoframe_errors++; report_error("missing AVI or audio InfoFrame"); end
            if (identified && !transition) begin
                frames_checked++;
                if (last_f >= 0 && f_real != last_f + 1) begin
                    frame_seq_errors++; report_error($sformatf("frame %0d after %0d", f_real, last_f));
                end
                $display("frame %0d: SNES frame %0d, picture lines %0d..%0d, %0d lines, packets acr=%0d audio=%0d avi=%0d aif=%0d spd=%0d null=%0d, rephase=%0d",
                         hframe, f_real, v_off_seen, v_off_seen + 2 * vis_disp - 1, lines_in_frame,
                         pkt_acr, pkt_aud, pkt_avi, pkt_aif, pkt_spd, pkt_null, rp - rephase_at_start);
            end else if (identified) begin
                $display("frame %0d: SNES frame %0d is an overscan transition (placement from previous frame), pixel check skipped, %0d lines, rephase=%0d",
                         hframe, f_real, lines_in_frame, rp - rephase_at_start);
            end
            if (identified) last_f = f_real;
        end
        hframe++;
        lines_in_frame = 0; runs_in_frame = 0; bad_period = 0;
        pkt_acr = 0; pkt_aud = 0; pkt_avi = 0; pkt_aif = 0; pkt_spd = 0; pkt_null = 0;
        identified = 0; transition = 0;
        rephase_at_start = rp;
    endtask

    // AVI InfoFrame (type 0x82): PB0 checksum over HB0-HB2 and PB0-PB27,
    // PB2[5:4] picture aspect (M1M0), PB4[6:0] VIC.
    task automatic check_avi();
        reg [7:0] sum, pb2, pb4;
        sum = hdr_bits[7:0] + hdr_bits[15:8] + hdr_bits[23:16];
        for (int k = 0; k < 4; k++)
            for (int j = 0; j < 7; j++) sum = sum + sub_bits[k][8*j +: 8];
        pb2 = sub_bits[0][23:16];
        pb4 = sub_bits[0][39:32];
        avi_vic = pb4[6:0];
        avi_aspect = pb2[5:4];
        avi_checked++;
        if (sum != 8'd0) begin avi_errors++; report_error($sformatf("AVI InfoFrame checksum %02h", sum)); end
        if (hdr_bits[23:8] != 16'h0D02) begin avi_errors++; report_error($sformatf("AVI InfoFrame version/length %04h", hdr_bits[23:8])); end
        if (pb4[6:0] != 7'(EXP_VIC)) begin avi_errors++; report_error($sformatf("AVI VIC %0d, expected %0d", pb4[6:0], EXP_VIC)); end
        if (pb2[5:4] != EXP_ASPECT) begin avi_errors++; report_error($sformatf("AVI picture aspect %0d, expected %0d", pb2[5:4], EXP_ASPECT)); end
    endtask

    task automatic finish_packet();
        reg [7:0] e;
        reg [7:0] ptype;
        int cts, n;
        e = 0;
        for (int i = 0; i < 24; i++) e = next_ecc(e, hdr_bits[i]);
        if (e != hdr_bits[31:24]) begin ecc_errors++; report_error("header ECC"); end
        for (int k = 0; k < 4; k++) begin
            e = 0;
            for (int i = 0; i < 56; i++) e = next_ecc(e, sub_bits[k][i]);
            if (e != sub_bits[k][63:56]) begin ecc_errors++; report_error($sformatf("subpacket %0d ECC", k)); end
        end
        ptype = hdr_bits[7:0];
        case (ptype)
            8'h00: pkt_null++;
            8'h01: begin
                pkt_acr++;
                cts = {sub_bits[0][11:8], sub_bits[0][23:16], sub_bits[0][31:24]};
                n = {sub_bits[0][35:32], sub_bits[0][47:40], sub_bits[0][55:48]};
                acr_n = n;
                if (hframe >= WARMUP && cts != 0) begin
                    acr_count++;
                    if (cts < acr_cts_min) acr_cts_min = cts;
                    if (cts > acr_cts_max) acr_cts_max = cts;
                end
            end
            8'h02: begin
                pkt_aud++;
                for (int k = 0; k < 4; k++) begin
                    if (hdr_bits[8 + k]) begin
                        int l, r;
                        l = sub_bits[k][23:8];
                        r = sub_bits[k][47:32];
                        audio_rx++;
                        if (r != (l ^ 16'h5A5A)) begin audio_errors++; report_error("audio L/R pairing"); end
                        if (last_audio_l >= 0 && l != ((last_audio_l + 1) & 16'hFFFF)) begin
                            audio_errors++; report_error($sformatf("audio sample %0d after %0d", l, last_audio_l));
                        end
                        last_audio_l = l;
                    end
                end
            end
            8'h82: begin pkt_avi++; if (hframe >= WARMUP) check_avi(); end
            8'h83: pkt_spd++;
            8'h84: pkt_aif++;
            default: begin protocol_errors++; report_error($sformatf("packet type %02h", ptype)); end
        endcase
    endtask

    task automatic process_symbol(input [9:0] w0, input [9:0] w1, input [9:0] w2);
        reg [1:0] c0, c1, c2;
        reg [3:0] t0, t1, t2;
        bit k0, k1, k2, g0, g1, g2, vg, ig;
        bit hs_act, vs_act;
        sym++;
        k0 = ctrl_dec(w0, c0); k1 = ctrl_dec(w1, c1); k2 = ctrl_dec(w2, c2);
        g0 = terc4_dec(w0, t0); g1 = terc4_dec(w1, t1); g2 = terc4_dec(w2, t2);
        vg = w0 == 10'b1011001100 && w1 == 10'b0100110011 && w2 == 10'b1011001100;
        ig = g0 && w1 == 10'b0100110011 && w2 == 10'b0100110011;
        if (k0 && k1 && k2) begin
            if (state == S_VID) finish_line();
            if (state == S_ISL || state == S_IG) begin
                if (isl_len % 32 != 0) begin island_len_errors++; report_error($sformatf("island length %0d", isl_len)); end
            end
            if (state == S_VG) begin protocol_errors++; report_error("video guard without video"); end
            state = S_CTRL;
            {vs, hs} = c0;
        end else if (state == S_VID) begin
            if (run_len < H_ACTIVE) line_px[run_len] = {tmds_dec8(w2), tmds_dec8(w1), tmds_dec8(w0)};
            run_len++;
        end else if (vg && (state == S_CTRL || state == S_VG)) begin
            if (state == S_CTRL) guard_len = 0;
            guard_len++;
            state = S_VG;
        end else if (state == S_VG) begin
            if (guard_len != 2) begin protocol_errors++; report_error($sformatf("video guard length %0d", guard_len)); end
            state = S_VID;
            run_len = 1;
            line_px[0] = {tmds_dec8(w2), tmds_dec8(w1), tmds_dec8(w0)};
        end else if (ig && (state == S_CTRL || state == S_IG || state == S_ISL)) begin
            if (state == S_CTRL) begin isl_len = 0; guard_len = 0; end
            if (state == S_ISL) guard_len = 0;
            guard_len++;
            state = S_IG;
            {vs, hs} = t0[1:0];
        end else if ((state == S_IG || state == S_ISL) && g0 && g1 && g2) begin
            int i;
            if (state == S_IG && guard_len != 2) begin protocol_errors++; report_error("island guard length"); end
            state = S_ISL;
            i = isl_len % 32;
            hdr_bits[i] = t0[2];
            for (int k = 0; k < 4; k++) begin
                sub_bits[k][2*i] = t1[k];
                sub_bits[k][2*i+1] = t2[k];
            end
            isl_len++;
            if (i == 31) finish_packet();
            {vs, hs} = t0[1:0];
        end else begin
            if (hframe >= WARMUP) protocol_errors++;
            if (hframe >= WARMUP) report_error($sformatf("unexpected symbols %03h %03h %03h in state %0d", w0, w1, w2, state));
            state = S_CTRL;
        end

        hs_act = !hs;
        vs_act = !vs;
        if (vs_act && !vs_act_q) begin
            if (hframe >= 0) finish_frame(); else hframe = 0;
            vs_start = sym;
        end
        if (!vs_act && vs_act_q && hframe >= WARMUP && rephase_count == rephase_at_start) begin
            if (sym - vs_start != VS_LINES * H_TOTAL) begin
                vsync_width_errors++; report_error($sformatf("vsync width %0d", sym - vs_start));
            end
        end
        if (hs_act && !hs_act_q) begin
            if (last_hs_edge >= 0 && hframe >= WARMUP && sym - last_hs_edge != H_TOTAL && rephase_count == rephase_at_start)
                begin bad_period++; report_error($sformatf("line period %0d", sym - last_hs_edge)); end
            last_hs_edge = sym;
            hs_start = sym;
            lines_in_frame++;
        end
        if (!hs_act && hs_act_q && hframe >= WARMUP) begin
            if (sym - hs_start != HS_W) begin hsync_width_errors++; report_error($sformatf("hsync width %0d", sym - hs_start)); end
        end
        hs_act_q = hs_act;
        vs_act_q = vs_act;
    endtask

    // lock-error monitor: every event after the first two must need no re-phase
    int events = 0;
    always @(posedge clk_pixel) begin
        if (dut.ev_pulse) begin
            events++;
            if (events > 1 && vis_sched(frame) == vis_sched(frame - 1 < 0 ? 0 : frame - 1)) begin
                // lock_error updates on the next clock; sample it then
                @(posedge clk_pixel);
                steady_lock_samples++;
                if (lock_error > 8 || lock_error < -8) steady_lock_bad++;
            end
        end
    end

    initial begin
        repeat (8) @(posedge clk_pixel);
        rst_pixel_n = 1;
        @(posedge clk_snes);
        rst_snes_n = 1;
        repeat (4) @(posedge clk_pixel);
        if (mode_pal !== PAL) report_error($sformatf("raster mode %0d, expected %0d", mode_pal, PAL));
        wait (sim_done);
        repeat (2000) @(posedge clk_pixel);
        $display("summary: HDMI frames %0d, pixel-checked frames %0d, pixels %0d, pixel errors %0d",
                 hframe, frames_checked, pixels_checked, pixel_errors);
        $display("summary: hsync-width errors %0d, vsync-width errors %0d, active-run errors %0d, frame-shape errors %0d, frame-sequence errors %0d",
                 hsync_width_errors, vsync_width_errors, run_errors, frame_count_errors, frame_seq_errors);
        $display("summary: protocol errors %0d, island-length errors %0d, ECC errors %0d, InfoFrame errors %0d, AVI InfoFrames checked %0d (VIC %0d, aspect %0d, errors %0d)",
                 protocol_errors, island_len_errors, ecc_errors, infoframe_errors, avi_checked, avi_vic, avi_aspect, avi_errors);
        $display("summary: audio sent %0d, recovered %0d, audio errors %0d; ACR N=%0d CTS %0d..%0d over %0d packets",
                 samples_sent, audio_rx, audio_errors, acr_n, acr_cts_min, acr_cts_max, acr_count);
        $display("summary: locked=%0d lock_error=%0d rephase_count=%0d steady events=%0d (out of tolerance %0d), warm-up runs cut by the start-up lock %0d",
                 locked, lock_error, rephase_count, steady_lock_samples, steady_lock_bad, warmup_cut_runs);
        if (frames_checked < 4) report_error($sformatf("only %0d frames fully checked", frames_checked));
        if (avi_checked < 4) report_error($sformatf("only %0d AVI InfoFrames checked", avi_checked));
        if (audio_rx < samples_sent - 40) report_error("audio samples lost");
        if (acr_n != 4096 || acr_cts_min < CTS_LO || acr_cts_max > CTS_HI) report_error("ACR N/CTS out of range");
        if (!ASYNC && (!locked || rephase_count != 2 || steady_lock_bad != 0 || steady_lock_samples < 3))
            report_error($sformatf("frame lock not steady (last lock_error %0d, %0d re-phases, %0d of %0d steady events out of tolerance)",
                                   lock_error, rephase_count, steady_lock_bad, steady_lock_samples));
        if (ASYNC && (!locked || rephase_count < N_FRAMES - 1))
            report_error("asynchronous clocks: expected tracking with a re-phase every frame");
        if (errors == 0)
            $display("PASS: av-out (%s) %0d frames, %0d pixels exact, %0dx%0d in %0dx%0d, hsync %0d, vsync %0d lines, VIC %0d aspect %0d, %0d audio samples in order, ACR CTS %0d..%0d, 0 ECC errors, %0d re-phases",
                     CLOCKING, frames_checked, pixels_checked, H_ACTIVE, V_ACTIVE, H_TOTAL, V_TOTAL, HS_W, VS_LINES,
                     avi_vic, avi_aspect, audio_rx, acr_cts_min, acr_cts_max, rephase_count);
        else begin
            $display("FAIL: av-out %0d errors", errors);
            $fatal(1, "av-out checks failed");
        end
        $finish;
    end
endmodule
