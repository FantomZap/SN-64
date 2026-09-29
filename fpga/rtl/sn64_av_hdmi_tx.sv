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
// Timing convention (same as hdl-util): rgb presented in clock t belongs to the
// position that cx/cy held in clock t-1. Symbols appear on tmds[] two clocks later.
module sn64_av_hdmi_tx #(
    parameter int H_ACTIVE = 720,
    parameter int V_ACTIVE = 480,
    parameter int H_TOTAL = 858,
    parameter int V_TOTAL = 524,
    parameter int HSYNC_START = 16,   // front porch, pixels after H_ACTIVE
    parameter int HSYNC_SIZE = 62,
    parameter int VSYNC_START = 9,    // front porch, lines after V_ACTIVE
    parameter int VSYNC_SIZE = 6,
    parameter bit SYNC_INVERT = 1'b1, // 480p: negative sync polarity
    parameter int VIDEO_ID_CODE = 2,  // CEA-861 VIC 2: 720x480p, 4:3
    parameter real VIDEO_RATE = 27.0198e6,
    parameter int AUDIO_RATE = 32000,
    parameter int AUDIO_BIT_WIDTH = 16,
    parameter bit DVI_OUTPUT = 1'b0,
    parameter bit [8*8-1:0] VENDOR_NAME = {"SN64", 32'd0},
    parameter bit [8*16-1:0] PRODUCT_DESCRIPTION = {"SNES adapter", 32'd0}
) (
    input  wire clk_pixel,
    input  wire reset,
    input  wire [10:0] cx,
    input  wire [9:0]  cy,
    input  wire [23:0] rgb,                 // {R8, G8, B8}
    input  wire clk_audio,                  // one-clock strobe per stereo sample (pixel domain)
    input  wire [AUDIO_BIT_WIDTH-1:0] audio_left, audio_right,
    output logic [9:0] tmds [2:0]
);
    localparam int H_HS0 = H_ACTIVE + HSYNC_START;
    localparam int H_HS1 = H_ACTIVE + HSYNC_START + HSYNC_SIZE;
    localparam int V_VS0 = V_ACTIVE + VSYNC_START;
    localparam int V_VS1 = V_ACTIVE + VSYNC_START + VSYNC_SIZE;

    logic hsync, vsync;
    always_comb begin
        hsync = SYNC_INVERT ^ (cx >= H_HS0 && cx < H_HS1);
`ifdef SN64_AV_FAULT_SYNC
        // Fault injection for the negative test: one short hsync pulse on line 100.
        if (cy == 10'd100 && cx == 11'(H_HS1 - 1)) hsync = SYNC_INVERT;
`endif
        // vsync edges coincide with the hsync leading edge (as in hdl-util)
        if (cy == V_VS0 - 1)
            vsync = SYNC_INVERT ^ (cx >= H_HS0);
        else if (cy == V_VS1 - 1)
            vsync = SYNC_INVERT ^ (cx < H_HS0);
        else
            vsync = SYNC_INVERT ^ (cy >= V_VS0 && cy < V_VS1);
    end

    logic video_data_period;
    always_ff @(posedge clk_pixel)
        if (reset) video_data_period <= 1'b0;
        else video_data_period <= cx < H_ACTIVE && cy < V_ACTIVE;

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
                    video_guard <= cx >= H_TOTAL - 2 && cx < H_TOTAL && (cy == V_TOTAL - 1 || cy < V_ACTIVE - 1);
                    video_preamble <= cx >= H_TOTAL - 10 && cx < H_TOTAL - 2 && (cy == V_TOTAL - 1 || cy < V_ACTIVE - 1);
                end
            end

            // Section 5.2.3.1: packets that fit in horizontal blanking.
            localparam int MAX_PACKETS = (H_TOTAL - H_ACTIVE - 2 - 8 - 4 - 2 - 2 - 8 - 4) / 32;
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

            logic [23:0] header;
            logic [55:0] sub [3:0];
            logic video_field_end;
            assign video_field_end = cx == H_ACTIVE - 1 && cy == V_ACTIVE - 1;
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
                .audio_sample_word(audio_sample_word), .header(header), .sub(sub));

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
