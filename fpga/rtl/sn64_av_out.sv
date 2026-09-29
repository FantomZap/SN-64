// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 digital A/V output: SNES core video and audio to HDMI 720x480p.
//
// Simulation/resource candidate. Not validated on a display or on hardware.
//
// Clocking. The SNES master clock (clk_snes, 21.477 MHz) is never adjusted.
// clk_pixel is expected to be clk_snes * 39/31 (27.0198 MHz) and clk_pixel_x5
// exactly 5x clk_pixel, both from the same reference (two cascaded ECP5 PLLs,
// see docs/design/av-output-implementation.md). With that ratio one SNES line
// (1364 master clocks) is exactly two 858-pixel HDMI lines, and one 262-line
// SNES frame is exactly one 524-line HDMI frame.
//
// Video path. The core's 512 half-dot pixels per line (X_OUT = {dot, DOT_CLK},
// so lo-res dots arrive twice and hi-res dots once) are written into a 4-line
// ring buffer in the SNES domain. The HDMI raster reads each SNES line twice
// (line doubling) and centres the 512x(2*lines) picture in 720x480. The raster
// is phase-locked to the SNES frame: at the HDE rise of SNES line SYNC_LINE the
// SNES side toggles an event; the pixel side compares its raster position with
// the expected position and, if the error exceeds LOCK_TOL pixels, re-phases
// the raster at a point inside horizontal active time of a vertical-blanking
// line (never inside a data island). With the exact clock ratio the error is
// zero in steady state, so the output is a uniform 858x524 raster.
module sn64_av_out #(
    parameter int H_ACTIVE = 720,
    parameter int V_ACTIVE = 480,
    parameter int H_TOTAL = 858,
    parameter int V_TOTAL = 524,
    parameter int PIC_X0 = 104,       // (720 - 512) / 2
    parameter int SYNC_LINE = 250,    // SNES line whose HDE rise is the lock event (maps to the vertical back porch)
    parameter int LEAD_LINES = 3,     // HDMI lines from SNES line start to its first copy
    parameter int SYNC_X = 100,       // raster column at the lock event (HDE offset + CDC)
    parameter int LOCK_TOL = 2,       // pixels of phase error tolerated without re-phasing
    parameter int LOCK_WINDOW = 1024, // |error| at the last event below this reports locked
    parameter real VIDEO_RATE = 27.0198e6,
    parameter bit DVI_OUTPUT = 1'b0
) (
    // SNES master-clock domain (outputs of sn64_console_candidate)
    input  wire clk_snes,
    input  wire rst_snes_n,
    input  wire [14:0] rgb,           // BGR555: [4:0] R, [9:5] G, [14:10] B
    input  wire hde, vde,
    input  wire [8:0] video_x,        // {dot, DOT_CLK}: half-dot index 0..511
    input  wire [8:0] video_y,        // {field, line}
    input  wire [15:0] audio_left, audio_right,
    input  wire audio_ready,
    // HDMI pixel domain
    input  wire clk_pixel,
    input  wire clk_pixel_x5,
    input  wire rst_pixel_n,
    output wire [2:0] tmds,           // serial TMDS data (single-ended view)
    output wire tmds_clock,
    // status (pixel domain)
    output reg  locked,
    output reg  signed [19:0] lock_error,
    output reg  [7:0] rephase_count
);
    localparam int POS_TOTAL = H_TOTAL * V_TOTAL;
    localparam int SYNC_Y_BASE = 2 * (SYNC_LINE - 1) - LEAD_LINES;  // plus v_off
    localparam int PIC_W = 512;

    // ------------------------------------------------------------------
    // SNES domain: capture, line counting, lock event, audio hand-off
    // ------------------------------------------------------------------
    (* ram_style = "block" *) reg [14:0] line_mem [0:2047];
    reg wr_en = 1'b0;
    reg [10:0] wr_addr = 11'd0;
    reg [14:0] wr_data = 15'd0;
    reg hde_q = 1'b0, vde_q = 1'b0, ready_q = 1'b0;
    reg counting = 1'b0;
    reg [8:0] line_cnt = 9'd0, vis_cnt = 9'd0;
    reg [8:0] vis_lines = 9'd224;     // last completed frame, stable between VDE falls
    reg ev_tog = 1'b0;
    reg [15:0] a_l = 16'd0, a_r = 16'd0;
    reg a_tog = 1'b0;

    always @(posedge clk_snes) begin
        wr_en <= rst_snes_n && hde && vde;
        wr_addr <= {video_y[1:0], video_x};
        wr_data <= rgb;
        if (wr_en) line_mem[wr_addr] <= wr_data;
    end

    always @(posedge clk_snes) begin
        if (!rst_snes_n) begin
            hde_q <= 1'b0;
            vde_q <= 1'b0;
            ready_q <= 1'b0;
            counting <= 1'b0;
            line_cnt <= 9'd0;
            vis_cnt <= 9'd0;
            vis_lines <= 9'd224;
        end else begin
            hde_q <= hde;
            vde_q <= vde;
            ready_q <= audio_ready;
            if (vde && !vde_q) begin
                counting <= 1'b1;
                line_cnt <= 9'd0;
                vis_cnt <= 9'd0;
            end else begin
                if (hde && !hde_q && counting) begin
                    line_cnt <= line_cnt + 9'd1;
                    if (line_cnt + 9'd1 == 9'(SYNC_LINE)) begin
                        ev_tog <= ~ev_tog;
                        counting <= 1'b0;
                    end
                end
                if (hde && !hde_q && vde) vis_cnt <= vis_cnt + 9'd1;
                if (!vde && vde_q)
                    vis_lines <= (vis_cnt < 9'd200 || vis_cnt > 9'd240) ? 9'd224 : vis_cnt;
            end
            if (audio_ready && !ready_q) begin
                a_l <= audio_left;
                a_r <= audio_right;
                a_tog <= ~a_tog;
            end
        end
    end

    // ------------------------------------------------------------------
    // Pixel domain
    // ------------------------------------------------------------------
    wire rst_pixel = !rst_pixel_n;

    // Event and audio toggles: 2-FF synchronisers plus edge detect. The
    // quasi-static data (vis_lines, a_l, a_r) changed before its toggle and is
    // sampled only after the toggle has crossed.
    reg [2:0] ev_sync = 3'd0, a_sync = 3'd0;
    always @(posedge clk_pixel) begin
        ev_sync <= {ev_sync[1:0], ev_tog};
        a_sync <= {a_sync[1:0], a_tog};
    end
    wire ev_pulse = ev_sync[2] ^ ev_sync[1];
    wire a_new = a_sync[2] ^ a_sync[1];

    reg [15:0] aud_l = 16'd0, aud_r = 16'd0;
    reg aud_pend = 1'b0, clk_audio = 1'b0;
    always @(posedge clk_pixel) begin
        clk_audio <= 1'b0;
        if (rst_pixel) begin
            aud_pend <= 1'b0;
        end else if (a_new) begin
            aud_l <= a_l;
            aud_r <= a_r;
            aud_pend <= 1'b1;
        end else if (aud_pend) begin
            clk_audio <= 1'b1;
            aud_pend <= 1'b0;
        end
    end

    // Raster with frame lock
    reg [10:0] cx = 11'd0, tx = 11'd0;
    reg [9:0]  cy = 10'd0, ty = 10'd0;
    reg [18:0] pos = 19'd0, tpos = 19'd0;
    reg pending = 1'b0;
    reg [5:0] v_off = 6'd16;
    reg [8:0] vis = 9'd224;
    reg [19:0] since_event = 20'd0;

    function automatic logic safe_col(input logic [10:0] x);
        safe_col = x >= 11'd16 && x < 11'(H_ACTIVE - 16);
    endfunction

    wire last_col = cx == 11'(H_TOTAL - 1);
    wire [10:0] nx = last_col ? 11'd0 : cx + 11'd1;
    wire [9:0]  ny = last_col ? (cy == 10'(V_TOTAL - 1) ? 10'd0 : cy + 10'd1) : cy;
    wire [18:0] npos = pos == 19'(POS_TOTAL - 1) ? 19'd0 : pos + 19'd1;
    wire t_last_col = tx == 11'(H_TOTAL - 1);
    wire [10:0] tnx = t_last_col ? 11'd0 : tx + 11'd1;
    wire [9:0]  tny = t_last_col ? (ty == 10'(V_TOTAL - 1) ? 10'd0 : ty + 10'd1) : ty;
    wire [18:0] tnpos = tpos == 19'(POS_TOTAL - 1) ? 19'd0 : tpos + 19'd1;

    wire [8:0] vis_new = vis_lines;
    wire [5:0] v_off_new = 6'(9'd240 - vis_new);
    wire [9:0] sync_y_new = 10'(SYNC_Y_BASE) + {4'd0, v_off_new};
    wire [18:0] sync_pos_new = 19'(sync_y_new) * 19'(H_TOTAL) + 19'(SYNC_X);
    // phase error, wrapped into (-POS_TOTAL/2, POS_TOTAL/2]
    wire signed [20:0] err_raw = $signed({2'b00, npos}) - $signed({2'b00, sync_pos_new});
    wire signed [20:0] err_wrapped = err_raw > 21'sd224796 ? err_raw - 21'(POS_TOTAL)
                                   : err_raw < -21'sd224795 ? err_raw + 21'(POS_TOTAL) : err_raw;
    wire err_small = err_wrapped <= 21'(LOCK_TOL) && err_wrapped >= -21'(LOCK_TOL);
    wire err_tracking = err_wrapped < 21'(LOCK_WINDOW) && err_wrapped > -21'(LOCK_WINDOW);

    always @(posedge clk_pixel) begin
        if (rst_pixel) begin
            cx <= 11'd0;
            cy <= 10'd0;
            pos <= 19'd0;
            pending <= 1'b0;
            v_off <= 6'd16;
            vis <= 9'd224;
            locked <= 1'b0;
            lock_error <= 20'sd0;
            rephase_count <= 8'd0;
            since_event <= 20'd0;
        end else begin
            cx <= nx;
            cy <= ny;
            pos <= npos;
            tx <= tnx;
            ty <= tny;
            tpos <= tnpos;
            if (since_event != 20'hFFFFF) since_event <= since_event + 20'd1;
            if (since_event > 20'(2 * POS_TOTAL)) locked <= 1'b0;
            if (ev_pulse) begin
                since_event <= 20'd0;
                v_off <= v_off_new;
                vis <= vis_new;
                lock_error <= 20'(err_wrapped);
                locked <= err_tracking;
                tx <= 11'(SYNC_X);
                ty <= sync_y_new;
                tpos <= sync_pos_new;
                pending <= !err_small;
            end else if (pending && safe_col(cx) && safe_col(tx)) begin
                cx <= tnx;
                cy <= tny;
                pos <= tnpos;
                pending <= 1'b0;
                rephase_count <= rephase_count + 8'd1;
            end
        end
    end

    // Picture fetch: SNES line k = (cy - v_off) / 2, half-dot = cx - PIC_X0
    wire in_x = cx >= 11'(PIC_X0) && cx < 11'(PIC_X0 + PIC_W);
    wire [9:0] dy = cy - {4'd0, v_off};
    wire in_y = cy >= {4'd0, v_off} && dy < {vis, 1'b0};
    wire [8:0] px = 9'(cx - 11'(PIC_X0));
    wire [10:0] rd_addr = {dy[2:1], px};
    reg [14:0] rd_q = 15'd0;
    reg in_pic_q = 1'b0;
    reg fault_q = 1'b0;
    always @(posedge clk_pixel) begin
        rd_q <= line_mem[rd_addr];
        in_pic_q <= in_x && in_y;
`ifdef SN64_AV_FAULT_PIXEL
        fault_q <= cx == 11'd300 && cy == 10'd200;  // negative test: one corrupted pixel
`else
        fault_q <= 1'b0;
`endif
    end
    wire [14:0] pix = in_pic_q ? (rd_q ^ {14'd0, fault_q}) : 15'd0;
    wire [4:0] r5 = pix[4:0], g5 = pix[9:5], b5 = pix[14:10];
    wire [23:0] rgb24 = {r5, r5[4:2], g5, g5[4:2], b5, b5[4:2]};

    logic [9:0] tmds_word [2:0];
    sn64_av_hdmi_tx #(
        .H_ACTIVE(H_ACTIVE), .V_ACTIVE(V_ACTIVE), .H_TOTAL(H_TOTAL), .V_TOTAL(V_TOTAL),
        .VIDEO_RATE(VIDEO_RATE), .DVI_OUTPUT(DVI_OUTPUT)
    ) tx_core (
        .clk_pixel(clk_pixel), .reset(rst_pixel), .cx(cx), .cy(cy), .rgb(rgb24),
        .clk_audio(clk_audio), .audio_left(aud_l), .audio_right(aud_r), .tmds(tmds_word));

    sn64_av_serializer serializer (
        .clk_pixel(clk_pixel), .clk_x5(clk_pixel_x5),
        .word0(tmds_word[0]), .word1(tmds_word[1]), .word2(tmds_word[2]),
        .tmds(tmds), .tmds_clock(tmds_clock));
endmodule
