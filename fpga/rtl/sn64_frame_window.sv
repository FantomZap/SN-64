// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 frame window: the SNES picture and sound for the N64 to display on the
// console's own output (docs/design/console-video-path.md).
//
// SNES side (clk_snes): every visible line is written into a frame buffer as
// 256 pixels of N64-native RGBA5551 ({r,g,b,1}); in 512-wide (hi-res) modes the
// second half-dot of each dot is dropped. Interlaced fields overwrite the same
// lines. The audio mixer's 32 kHz stereo samples go into a ring of
// 2^AUDIO_LOG2 stereo pairs.
//
// N64 side (clk_host): the buffer is read through the vendored PI controller's
// "SRAM" window (N64 address 0x0800_0000, PI domain 2, 128 KiB), which lands
// on mem_bus addresses 0x03FE_0000-0x03FF_FFFF (SummerCart64 SAVE_OFFSET). Byte
// offsets: 0x00000 frame (line*512 + x*2), 0x1E000 audio ring (pair*4: left,
// right). Status words for the mailbox: FRAME_STATUS {frame_count[7:0],
// lines_done[7:0]} (lines_done = last line completely written; the console
// reads a line only after it is done and is never more than one frame
// behind), AUDIO_WPTR (next stereo pair index to be written), VIDEO_MODE
// {12'd0, pal, interlace, high_res, overscan}, FRAME_PHASE {frames_started[4:0],
// position[10:0]}: where the SNES is in its frame, in quarter lines (341 master
// clocks) since the first visible line began, and a count of frame starts that
// steps at the moment the position returns to 0; position 0x7FF until the first
// frame. The console's program reads it to hold one SNES picture per console
// picture (docs/design/frame-lock.md).
module sn64_frame_window #(
    parameter LINES = 240,
    parameter AUDIO_LOG2 = 10
) (
    // ---- SNES domain ----
    input  wire        clk_snes,
    input  wire        rst_snes_n,
    input  wire [14:0] rgb,             // BGR555: [4:0] R, [9:5] G, [14:10] B
    input  wire        hde, vde,
    input  wire [8:0]  video_x,         // {dot, DOT_CLK}: half-dot index 0..511
    input  wire [8:0]  video_y,         // {field, line}
    input  wire        high_res, interlace, pal,
    input  wire [15:0] audio_left, audio_right,
    input  wire        audio_ready,
    // ---- host domain (mem_bus memory side, 16-bit words) ----
    input  wire        clk_host,
    input  wire        reset,
    input  wire        req,
    input  wire        write,
    input  wire [26:0] address,
    input  wire [15:0] wdata,
    output reg         ack = 1'b0,
    output reg  [15:0] rdata = 16'h0000,
    output wire [15:0] frame_status,
    output wire [15:0] audio_wptr,
    output wire [15:0] video_mode,
    output wire [15:0] frame_phase
);
    localparam FB_WORDS = LINES * 256;
    localparam AUDIO_BASE = 17'h1E000;  // byte offset of the audio ring inside the window

    // ------------------------------------------------------------------
    // Frame buffer (dual clock: SNES writes, host reads)
    // ------------------------------------------------------------------
    reg [15:0] fb [0:FB_WORDS-1];
    reg [15:0] aud [0:(2 << AUDIO_LOG2)-1];   // interleaved L, R

    wire [7:0] line = video_y[7:0];
    wire       px_valid = vde && hde && !video_x[0] && (line < LINES);
    wire [15:0] px_word =
`ifdef SN64_FAULT_FRAME_RB_SWAP
        {rgb[14:10], rgb[9:5], rgb[4:0], 1'b1};    // fault injection: B and R swapped
`else
        {rgb[4:0], rgb[9:5], rgb[14:10], 1'b1};    // RGBA5551 = {R, G, B, 1}
`endif
    reg hde_q = 1'b0, vde_q = 1'b0;
    reg [7:0] frame_count = 8'd0, lines_done = 8'hFF;
    reg [AUDIO_LOG2-1:0] wptr = '0;
    reg overscan_q = 1'b0;
    reg [10:0] pos = 11'h7FF;                 // 0x7FF: no frame has started yet
    reg [8:0]  pos_div = 9'd0;
    reg [4:0]  starts = 5'd0;                 // frame starts, modulo 32
    always @(posedge clk_snes) begin
        if (px_valid) fb[{line, video_x[8:1]}] <= px_word;
        hde_q <= hde;
        vde_q <= vde;
        if (vde && hde_q && !hde) lines_done <= line;          // line finished
        if (vde_q && !vde) begin                                 // visible area finished
            frame_count <= frame_count + 8'd1;
            overscan_q  <= (line > 8'd224);
        end
        if (!vde_q && vde) lines_done <= 8'hFF;                 // new frame: nothing done yet
        // Position in the frame: quarter lines since the visible area began. It runs through the
        // vertical blanking too, which lines_done cannot show.
`ifdef SN64_FAULT_PHASE_NO_RESTART
        if (1'b0) begin                                         // fault injection: never restarted at a frame start
`else
        if (!vde_q && vde) begin
`endif
            pos <= 11'd0; pos_div <= 9'd0; starts <= starts + 5'd1;
        end else if (pos_div == 9'd340) begin
            pos_div <= 9'd0;
            if (pos != 11'h7FF) pos <= pos + 11'd1;
        end else begin
            pos_div <= pos_div + 9'd1;
        end
        if (audio_ready) begin
            aud[{wptr, 1'b0}] <= audio_left;
            aud[{wptr, 1'b1}] <= audio_right;
            wptr <= wptr + 1'b1;
        end
    end

    // Status to the host domain (word transfers with handshake; each changes at
    // most once per quarter line (341 master clocks) or sample, far slower than
    // the handshake).
    sn64_cdc_word #(.W(16)) x_frame (.src_clk(clk_snes), .src_data({frame_count, lines_done}),
                                     .dst_clk(clk_host), .dst_data(frame_status));
    sn64_cdc_word #(.W(16)) x_aud   (.src_clk(clk_snes), .src_data({{(16 - AUDIO_LOG2){1'b0}}, wptr}),
                                     .dst_clk(clk_host), .dst_data(audio_wptr));
    sn64_cdc_word #(.W(16)) x_mode  (.src_clk(clk_snes), .src_data({12'd0, pal, interlace, high_res, overscan_q}),
                                     .dst_clk(clk_host), .dst_data(video_mode));
    sn64_cdc_word #(.W(16), .INIT(16'h07FF)) x_phase (.src_clk(clk_snes), .src_data({starts, pos}),
                                                      .dst_clk(clk_host), .dst_data(frame_phase));

    // ------------------------------------------------------------------
    // Host read port. Both memories are read unconditionally every clock
    // (plain synchronous reads, so the tool maps them to block RAM); the
    // request is answered one clock after it is registered, with the value
    // selected then. Writes are ignored.
    // ------------------------------------------------------------------
    wire [16:0] off = address[16:0];
    wire        aud_sel = off >= AUDIO_BASE;
    wire [15:0] fb_idx = off[16:1];
    wire [AUDIO_LOG2:0] aud_idx = off[AUDIO_LOG2+1:1];
    reg  [15:0] fb_q = 16'h0000, aud_q = 16'h0000;
    reg         pend = 1'b0, sel_q = 1'b0, in_range_q = 1'b0;
    always @(posedge clk_host) begin
        fb_q  <= fb[fb_idx];
        aud_q <= aud[aud_idx];
    end
    always @(posedge clk_host) begin
        ack <= 1'b0;
        if (reset) begin
            pend <= 1'b0;
        end else if (req && !pend && !ack) begin
            pend       <= 1'b1;
            sel_q      <= aud_sel;
            in_range_q <= (fb_idx < FB_WORDS);
        end else if (pend) begin
            rdata <= sel_q ? aud_q : (in_range_q ? fb_q : 16'h0000);
            ack   <= 1'b1;
            pend  <= 1'b0;
        end
    end
endmodule
