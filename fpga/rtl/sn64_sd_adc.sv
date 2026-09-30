// SN64 v2 cartridge-audio ADC: first-order sigma-delta in the FPGA.
// Per channel the board has an LVDS input pair (+ = AC-coupled, mid-rail biased
// audio; - = RC node) and one feedback output through 10 k into 1 nF on the
// - input. The comparator bit is fed back after two flops, so the RC node
// tracks the input and the density of ones is the input level. A boxcar over
// DECIM clocks gives one sample; DECIM is a power of two so the scaling is a
// shift. Output interface matches the retired sn64_i2s_rx so sn64_audio_mix
// is unchanged: left/right two's complement, frame_tog flips per sample.
// Resolution ~10 bits at 30 kHz (docs/design/v2-board.md); the SNES mixed its
// expansion audio in analog after its own DAC, so this is adequate.
// SPDX-License-Identifier: GPL-3.0-or-later
module sn64_sd_adc #(
    parameter int DECIM_LOG2 = 11,      // 2048 clocks per sample: 62.5 MHz -> 30.5 kHz
    parameter int WORD_BITS  = 24
) (
    input  wire clk,
    input  wire rst_n,
    input  wire cmp_l, cmp_r,           // LVDS comparator outputs (1 = input above the RC node)
    output reg  fb_l, fb_r,             // feedback bits to the RC nodes
    output logic signed [WORD_BITS-1:0] left, right,
    output logic frame_tog,
    output logic frame_stb,
    output logic locked,                // a few frames delivered
    output logic [15:0] frame_errors    // always 0 (kept for the mixer/telemetry interface)
);
    localparam int DECIM = 1 << DECIM_LOG2;
    reg [1:0] sl = 2'b00, sr = 2'b00;
    always @(posedge clk) begin
        sl <= {sl[0], cmp_l};
        sr <= {sr[0], cmp_r};
        fb_l <= sl[1];
        fb_r <= sr[1];
    end

    reg [DECIM_LOG2-1:0] cnt = '0;
    reg [DECIM_LOG2:0]   acc_l = '0, acc_r = '0;
    reg [2:0]            frames = '0;

    function automatic logic signed [WORD_BITS-1:0] scale(input logic [DECIM_LOG2:0] ones);
        logic signed [WORD_BITS-1:0] centred;
        centred = $signed({{(WORD_BITS - DECIM_LOG2 - 1){1'b0}}, ones}) - $signed(WORD_BITS'(DECIM / 2));   // -DECIM/2 .. +DECIM/2
        if (centred >= $signed(WORD_BITS'(DECIM / 2)))
            return {1'b0, {(WORD_BITS - 1){1'b1}}};                                       // saturate +full scale
        return centred <<< (WORD_BITS - DECIM_LOG2);                                      // +-DECIM/2 -> +-2^(WORD_BITS-1)
    endfunction

    always @(posedge clk) begin
        if (!rst_n) begin
            cnt <= '0; acc_l <= '0; acc_r <= '0; frames <= '0;
            left <= '0; right <= '0; frame_tog <= 1'b0; frame_stb <= 1'b0; locked <= 1'b0;
        end else begin
            frame_stb <= 1'b0;
            if (cnt == DECIM_LOG2'(DECIM - 1)) begin
                cnt <= '0;
                left  <= scale(acc_l + {{DECIM_LOG2{1'b0}}, fb_l});
                right <= scale(acc_r + {{DECIM_LOG2{1'b0}}, fb_r});
                acc_l <= '0; acc_r <= '0;
                frame_tog <= ~frame_tog;
                frame_stb <= 1'b1;
                if (frames != 3'd7) frames <= frames + 3'd1;
                if (frames >= 3'd3) locked <= 1'b1;
            end else begin
                cnt <= cnt + 1'b1;
                acc_l <= acc_l + {{DECIM_LOG2{1'b0}}, fb_l};
                acc_r <= acc_r + {{DECIM_LOG2{1'b0}}, fb_r};
            end
        end
    end
    assign frame_errors = 16'd0;
endmodule
