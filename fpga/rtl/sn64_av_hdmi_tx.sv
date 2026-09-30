// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 HDMI transmitter core: TMDS symbol generation for an externally
// supplied raster position (cx, cy).
//
// The period scheduling (video preamble/guard, data-island preamble/guards,
// packet slots, sync pulse placement) follows hdl-util/hdmi src/hdmi.sv
// (Sameer Puri, MIT OR Apache-2.0, commit 83b1c9543a91b776671a44e68e130f81cae437b7).
// It is re-implemented here, rather than vendored, because SN64 locks the raster
// to the SNES frame: cx/cy come from sn64_av_out and may be re-phased in vertical
// blanking. The packet, ECC and TMDS encoders are the vendored hdl-util modules
// under fpga/vendor/hdl-util-hdmi/src, used unmodified.
//
// Two raster modes, selected by `pal` (static: sn64_av_out changes it only
// while the pixel domain is in reset):
//   pal = 0: CEA-861 VIC 2 (720x480p) timing with 524 instead of 525 lines
//   pal = 1: CEA-861 VIC 17 (720x576p50, 4:3) timing with 624 instead of 625 lines
// Horizontal active width (720) is the same in both, so the data-island slot
// positions are shared. VIC 17 source timing: hdl-util hdmi.sv lines 152-162
// and Linux drivers/gpu/drm/drm_edid.c (v6.10) lines 837-841: 27.000 MHz,
// H 720/732/796/864, V 576/581/586/625, negative syncs, 4:3.
//
// AVI InfoFrame: packet_picker carries the NTSC AVI InfoFrame (VIC 2, as
// before). In PAL mode the AVI packet (type 0x82) is replaced, byte for byte,
// by a second vendored auxiliary_video_information_info_frame instance with
// VIC 17 and picture aspect 4:3, so the vendored files stay unmodified.
//
// Timing convention (same as hdl-util): rgb presented in clock t belongs to the
// position that cx/cy held in clock t-1. Symbols appear on tmds[] two clocks later.
module sn64_av_hdmi_tx #(
    parameter int H_ACTIVE = 720,
    // NTSC raster (pal = 0)
    parameter int V_ACTIVE = 480,
    parameter int H_TOTAL = 858,
    parameter int V_TOTAL = 524,
    parameter int HSYNC_START = 16,   // front porch, pixels after H_ACTIVE
    parameter int HSYNC_SIZE = 62,
    parameter int VSYNC_START = 9,    // front porch, lines after V_ACTIVE
    parameter int VSYNC_SIZE = 6,
    parameter int VIDEO_ID_CODE = 2,  // CEA-861 VIC 2: 720x480p, 4:3
    // PAL raster (pal = 1)
    parameter int PAL_V_ACTIVE = 576,
    parameter int PAL_H_TOTAL = 864,
    parameter int PAL_V_TOTAL = 624,
    parameter int PAL_HSYNC_START = 12,
    parameter int PAL_HSYNC_SIZE = 64,
    parameter int PAL_VSYNC_START = 5,
    parameter int PAL_VSYNC_SIZE = 5,
    parameter int PAL_VIDEO_ID_CODE = 17,        // CEA-861 VIC 17: 720x576p50, 4:3
    parameter bit [1:0] PAL_PICTURE_ASPECT = 2'b01, // AVI M1M0: 01 = 4:3
    parameter bit SYNC_INVERT = 1'b1, // 480p and 576p: negative sync polarity
    parameter real VIDEO_RATE = 27.0198e6, // only sizes the ACR CTS counter (15 bits for 27.02 and 27.04 MHz)
    parameter int AUDIO_RATE = 32000,
    parameter int AUDIO_BIT_WIDTH = 16,
    parameter bit DVI_OUTPUT = 1'b0,
    parameter bit [8*8-1:0] VENDOR_NAME = {"SN64", 32'd0},
    parameter bit [8*16-1:0] PRODUCT_DESCRIPTION = {"SNES adapter", 32'd0}
) (
    input  wire clk_pixel,
    input  wire reset,
    input  wire pal,                        // raster mode; change only while reset is asserted
    input  wire [10:0] cx,
    input  wire [9:0]  cy,
    input  wire [23:0] rgb,                 // {R8, G8, B8}
    input  wire clk_audio,                  // one-clock strobe per stereo sample (pixel domain)
    input  wire [AUDIO_BIT_WIDTH-1:0] audio_left, audio_right,
    output logic [9:0] tmds [2:0]
);
    // Runtime raster values (two constant sets, one mux each).
    wire [10:0] h_total = pal ? 11'(PAL_H_TOTAL) : 11'(H_TOTAL);
    wire [9:0]  v_active = pal ? 10'(PAL_V_ACTIVE) : 10'(V_ACTIVE);
    wire [9:0]  v_total = pal ? 10'(PAL_V_TOTAL) : 10'(V_TOTAL);
    wire [10:0] h_hs0 = pal ? 11'(H_ACTIVE + PAL_HSYNC_START) : 11'(H_ACTIVE + HSYNC_START);
    wire [10:0] h_hs1 = pal ? 11'(H_ACTIVE + PAL_HSYNC_START + PAL_HSYNC_SIZE)
                            : 11'(H_ACTIVE + HSYNC_START + HSYNC_SIZE);
    wire [9:0]  v_vs0 = pal ? 10'(PAL_V_ACTIVE + PAL_VSYNC_START) : 10'(V_ACTIVE + VSYNC_START);
    wire [9:0]  v_vs1 = pal ? 10'(PAL_V_ACTIVE + PAL_VSYNC_START + PAL_VSYNC_SIZE)
                            : 10'(V_ACTIVE + VSYNC_START + VSYNC_SIZE);

    logic hsync, vsync;
    always_comb begin
        hsync = SYNC_INVERT ^ (cx >= h_hs0 && cx < h_hs1);
`ifdef SN64_AV_FAULT_SYNC
        // Fault injection for the negative test: one short hsync pulse on line 100.
        if (cy == 10'd100 && cx == h_hs1 - 11'd1) hsync = SYNC_INVERT;
`endif
        // vsync edges coincide with the hsync leading edge (as in hdl-util)
        if (cy == v_vs0 - 10'd1)
            vsync = SYNC_INVERT ^ (cx >= h_hs0);
        else if (cy == v_vs1 - 10'd1)
            vsync = SYNC_INVERT ^ (cx < h_hs0);
        else
            vsync = SYNC_INVERT ^ (cy >= v_vs0 && cy < v_vs1);
    end

    logic video_data_period;
    always_ff @(posedge clk_pixel)
        if (reset) video_data_period <= 1'b0;
        else video_data_period <= cx < 11'(H_ACTIVE) && cy < v_active;

    logic [2:0] mode;
    logic [23:0] video_data;
    logic [5:0] control_data;
    logic [11:0] data_island_data;

    generate
        if (!DVI_OUTPUT) begin : hdmi_mode
            logic video_guard, video_preamble;
            always_ff @(posedge clk_pixel) begin
                if (reset) begin
                    video_guard <= 1'b0;
                    video_preamble <= 1'b0;
                end else begin
                    video_guard <= cx >= h_total - 11'd2 && cx < h_total &&
                                   (cy == v_total - 10'd1 || cy < v_active - 10'd1);
                    video_preamble <= cx >= h_total - 11'd10 && cx < h_total - 11'd2 &&
                                      (cy == v_total - 10'd1 || cy < v_active - 10'd1);
                end
            end

            // Section 5.2.3.1: packets that fit in horizontal blanking; the
            // narrower blanking of the two modes sets the count (3 for both).
            localparam int BLANK_MIN = (H_TOTAL < PAL_H_TOTAL ? H_TOTAL : PAL_H_TOTAL) - H_ACTIVE;
            localparam int MAX_PACKETS = (BLANK_MIN - 2 - 8 - 4 - 2 - 2 - 8 - 4) / 32;
            localparam int NUM_PACKETS = MAX_PACKETS > 18 ? 18 : MAX_PACKETS;
            localparam int DI_START = H_ACTIVE + 14;
            localparam int DI_END = H_ACTIVE + 14 + NUM_PACKETS * 32;

            logic di_now, packet_enable;
            assign di_now = NUM_PACKETS > 0 && cx >= DI_START && cx < DI_END;
            assign packet_enable = di_now && 5'(cx + H_ACTIVE + 18) == 5'd0;

            logic di_guard, di_preamble, di_period;
            always_ff @(posedge clk_pixel) begin
                if (reset) begin
                    di_guard <= 1'b0;
                    di_preamble <= 1'b0;
                    di_period <= 1'b0;
                end else begin
                    di_guard <= NUM_PACKETS > 0 && ((cx >= H_ACTIVE + 12 && cx < DI_START) ||
                                                    (cx >= DI_END && cx < DI_END + 2));
                    di_preamble <= NUM_PACKETS > 0 && cx >= H_ACTIVE + 4 && cx < H_ACTIVE + 12;
                    di_period <= di_now;
                end
            end

            logic [23:0] header, picked_header, avi_pal_header;
            logic [55:0] sub [3:0];
            logic [55:0] picked_sub [3:0];
            logic [55:0] avi_pal_sub [3:0];
            logic video_field_end;
            assign video_field_end = cx == 11'(H_ACTIVE - 1) && cy == v_active - 10'd1;
            logic [4:0] packet_pixel_counter;
            logic [AUDIO_BIT_WIDTH-1:0] audio_sample_word [1:0];
            assign audio_sample_word[0] = audio_left;
            assign audio_sample_word[1] = audio_right;

            packet_picker #(
                .VIDEO_ID_CODE(VIDEO_ID_CODE),
                .VIDEO_RATE(VIDEO_RATE),
                .IT_CONTENT(1'b1),
                .AUDIO_RATE(AUDIO_RATE),
                .AUDIO_BIT_WIDTH(AUDIO_BIT_WIDTH),
                .VENDOR_NAME(VENDOR_NAME),
                .PRODUCT_DESCRIPTION(PRODUCT_DESCRIPTION),
                .SOURCE_DEVICE_INFORMATION(8'h08) // CTA-861: game
            ) packet_picker (
                .clk_pixel(clk_pixel), .clk_audio(clk_audio), .reset(reset),
                .video_field_end(video_field_end), .packet_enable(packet_enable),
                .packet_pixel_counter(packet_pixel_counter),
                .audio_sample_word(audio_sample_word), .header(picked_header), .sub(picked_sub));

            // PAL AVI InfoFrame (VIC 17, 4:3), substituted for the picker's AVI packet.
            auxiliary_video_information_info_frame #(
                .VIDEO_ID_CODE(PAL_VIDEO_ID_CODE),
                .IT_CONTENT(1'b1),
                .PICTURE_ASPECT_RATIO(PAL_PICTURE_ASPECT)
            ) avi_pal (.header(avi_pal_header), .sub(avi_pal_sub));

            wire use_pal_avi = pal && picked_header[7:0] == 8'h82;
            assign header = use_pal_avi ? avi_pal_header : picked_header;
            assign sub[0] = use_pal_avi ? avi_pal_sub[0] : picked_sub[0];
            assign sub[1] = use_pal_avi ? avi_pal_sub[1] : picked_sub[1];
            assign sub[2] = use_pal_avi ? avi_pal_sub[2] : picked_sub[2];
            assign sub[3] = use_pal_avi ? avi_pal_sub[3] : picked_sub[3];

            logic [8:0] packet_data;
            packet_assembler packet_assembler (
                .clk_pixel(clk_pixel), .reset(reset), .data_island_period(di_period),
                .header(header), .sub(sub), .packet_data(packet_data), .counter(packet_pixel_counter));

            always_ff @(posedge clk_pixel) begin
                if (reset) begin
                    mode <= 3'd0;
                    video_data <= 24'd0;
                    control_data <= 6'd0;
                    data_island_data <= 12'd0;
                end else begin
                    mode <= di_guard ? 3'd4 : di_period ? 3'd3 : video_guard ? 3'd2 : video_data_period ? 3'd1 : 3'd0;
                    video_data <= rgb;
                    control_data <= {{1'b0, di_preamble}, {1'b0, video_preamble || di_preamble}, {vsync, hsync}};
                    data_island_data[11:4] <= packet_data[8:1];
                    data_island_data[3] <= cx != 0;
                    data_island_data[2] <= packet_data[0];
                    data_island_data[1:0] <= {vsync, hsync};
                end
            end
        end else begin : dvi_mode
            always_ff @(posedge clk_pixel) begin
                if (reset) begin
                    mode <= 3'd0;
                    video_data <= 24'd0;
                    control_data <= 6'd0;
                end else begin
                    mode <= video_data_period ? 3'd1 : 3'd0;
                    video_data <= rgb;
                    control_data <= {4'b0000, {vsync, hsync}};
                end
            end
            assign data_island_data = 12'd0;
        end
    endgenerate

    genvar i;
    generate
        for (i = 0; i < 3; i++) begin : tmds_gen
            tmds_channel #(.CN(i)) tmds_channel (
                .clk_pixel(clk_pixel), .video_data(video_data[i*8+7:i*8]),
                .data_island_data(data_island_data[i*4+3:i*4]),
                .control_data(control_data[i*2+1:i*2]), .mode(mode), .tmds(tmds[i]));
        end
    endgenerate
endmodule
