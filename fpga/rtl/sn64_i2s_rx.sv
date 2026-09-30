// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 I2S receiver for the cartridge-audio ADC (FPGA is the I2S slave).
//
// The board's stereo ADC is the I2S master on its own oscillator: it drives
// BCK (64 fs, 2.048 MHz at fs = 32 kHz), LRCK (= WS, fs) and DOUT (= SD),
// Philips I2S, 24-bit words in 32-bit slots. All three are asynchronous to
// every FPGA clock, so they are NOT used as clocks here: they are sampled by
// a fast free-running clock (clk_host, 62.5 MHz, in sn64_top) through
// identical synchroniser chains, and BCK rising edges are detected in that
// clock domain. Written for SN64 from the Philips I2S bus specification
// (Philips Semiconductors, "I2S bus specification", Feb 1986, revised
// 5 June 1996; copy and SHA-256 in docs/design/cart-audio-implementation.md):
//   * SD is two's complement, MSB first; the MSB is sent one clock period
//     after WS changes (section 3.1);
//   * WS = 0 is channel 1 (left), WS = 1 channel 2 (right) (section 3.2);
//   * the receiver latches SD and WS on the leading (rising) edge of SCK;
//   * transmitter: delay tdtr <= 0.8T after the rising edge, hold thtr >= 0;
//     SCK HIGH and LOW each >= 0.35T in master mode (Table 1 / Figure 2).
//
// Sampling point. By the specification SD and WS are only guaranteed valid
// from 0.8T after one rising edge until the next rising edge (hold >= 0), i.e.
// in the last 0.2T = 97.7 ns before each rising edge at T = 488.3 ns. The
// first synchroniser stage that sees BCK high was clocked at most one fast
// clock after the true edge (two if the stage before it went metastable and
// resolved high). SD and WS are therefore taken from the capture DATA_LAG
// fast clocks BEFORE that one: with DATA_LAG = 2 and a 16 ns clock the sample
// lies between 48 ns and 16 ns before the edge, inside the 97.7 ns window with
// >= 49 ns margin at the early side and >= 16 ns at the late side. BCK HIGH
// and LOW (>= 0.35T = 171 ns) span >= 10 fast clocks, so no edge is missed.
// Requirement on the sampling clock: (DATA_LAG + 1) * Tclk <= 0.2T and
// Tclk < 0.35T / 2; clk_snes (46.6 ns) would NOT meet the first one.
//
// Framing check: every slot must be exactly SLOT_BITS BCK periods (WS toggles
// every 32 rising edges at 64 fs). A frame (left slot then right slot) is
// only delivered if both slots and the slot before them had the right length;
// `locked` needs LOCK_FRAMES good frames in a row and drops on any bad slot.
//
// Output: one stereo frame per LRCK period. `left`/`right` hold the last
// complete frame and `frame_tog` flips when they change, so another clock
// domain can take them with a two-flop toggle synchroniser (the words are
// stable for a whole frame, 31 us, after the toggle flips).
`default_nettype none

module sn64_i2s_rx #(
    parameter int WORD_BITS   = 24,   // ADC word length (MSB-justified in the slot)
    parameter int SLOT_BITS   = 32,   // BCK periods per channel slot (64 fs => 32)
    parameter int DATA_LAG    = 2,    // fast clocks between the SD/WS capture and the BCK-high capture
    parameter int LOCK_FRAMES = 2     // good frames in a row before `locked`
) (
    input  wire                        clk,        // fast sampling clock (62.5 MHz clk_host in sn64_top)
    input  wire                        rst_n,      // synchronous, active low
    input  wire                        bck,        // asynchronous ADC outputs
    input  wire                        lrck,
    input  wire                        dout,
    output logic signed [WORD_BITS-1:0] left,      // last complete frame, two's complement
    output logic signed [WORD_BITS-1:0] right,
    output logic                        frame_tog,  // flips once per delivered frame
    output logic                        frame_stb,  // one-clock pulse per delivered frame (clk domain)
    output logic                        locked,     // LOCK_FRAMES good frames in a row
    output logic [15:0]                 frame_errors // slots with the wrong length (saturating)
);
    // ------------------------------------------------------------------
    // Synchronisers: identical chains; stage 0 is the capture flop.
    // ------------------------------------------------------------------
    localparam int DEPTH = 3 + DATA_LAG;          // enough stages for the lagged taps
    (* async_reg = "true" *) logic [DEPTH-1:0] bck_q  = '0;
    (* async_reg = "true" *) logic [DEPTH-1:0] ws_q   = '0;
    (* async_reg = "true" *) logic [DEPTH-1:0] sd_q   = '0;
    always_ff @(posedge clk) begin
        bck_q <= {bck_q[DEPTH-2:0], bck};
        ws_q  <= {ws_q[DEPTH-2:0],  lrck};
        sd_q  <= {sd_q[DEPTH-2:0],  dout};
    end
    // BCK rising edge seen at stage 2 (two flops of metastability settling).
    wire bck_rise = bck_q[2] && !bck_q[3];
`ifdef SN64_FAULT_I2S_LATE_SAMPLE
    // Fault: take SD/WS from the same capture as the first BCK-high sample,
    // i.e. up to one clock AFTER the rising edge (violates hold = 0 margin).
    wire ws_s = ws_q[2];
    wire sd_s = sd_q[2];
`else
    wire ws_s = ws_q[2 + DATA_LAG];
    wire sd_s = sd_q[2 + DATA_LAG];
`endif

    // ------------------------------------------------------------------
    // Slot/bit framing on BCK rising edges.
    // The first rising edge with a new WS carries the last bit of the
    // previous slot (1-bit I2S delay); the next WORD_BITS edges are the new
    // word, MSB first; the remaining edges of the slot are ignored.
    // ------------------------------------------------------------------
    logic                  ws_prev = 1'b0;
    logic [7:0]            cnt = 8'd0;            // index of the next rising edge in this slot
    logic                  prev_slot_ok = 1'b0;   // the slot that ended at the last WS change was full length
    logic [WORD_BITS-1:0]  shreg = '0;
    logic signed [WORD_BITS-1:0] left_hold = '0;
    logic                  left_ok = 1'b0;
    logic [7:0]            good_frames = 8'd0;

    always_ff @(posedge clk) begin
        frame_stb <= 1'b0;
        if (!rst_n) begin
            ws_prev <= 1'b0; cnt <= 8'd0; prev_slot_ok <= 1'b0;
            shreg <= '0; left_hold <= '0; left_ok <= 1'b0; good_frames <= 8'd0;
            left <= '0; right <= '0; frame_tog <= 1'b0; locked <= 1'b0; frame_errors <= 16'd0;
        end else if (bck_rise) begin
            ws_prev <= ws_s;
            if (ws_s != ws_prev) begin
                // Slot boundary: the slot that just ended had `cnt` rising edges.
                prev_slot_ok <= (cnt == 8'(SLOT_BITS));
                if (cnt != 8'(SLOT_BITS)) begin
                    locked <= 1'b0; good_frames <= 8'd0; left_ok <= 1'b0;
                    if (frame_errors != 16'hFFFF) frame_errors <= frame_errors + 16'd1;
                end
                cnt <= 8'd1;
            end else begin
                if (cnt != 8'hFF) cnt <= cnt + 8'd1;
                if (cnt >= 8'd1 && cnt <= 8'(WORD_BITS)) begin
                    shreg <= {shreg[WORD_BITS-2:0], sd_s};
                    if (cnt == 8'(WORD_BITS)) begin
                        // Word complete for channel ws_s. Valid only if this slot
                        // started cleanly (the slot before it had full length).
                        if (!ws_s) begin
                            left_hold <= {shreg[WORD_BITS-2:0], sd_s};
                            left_ok   <= prev_slot_ok;
                        end else if (left_ok && prev_slot_ok) begin
`ifdef SN64_FAULT_AUDIO_SWAP_LR
                            left  <= {shreg[WORD_BITS-2:0], sd_s};   // fault: channels swapped
                            right <= left_hold;
`else
                            left  <= left_hold;
                            right <= {shreg[WORD_BITS-2:0], sd_s};
`endif
                            frame_tog <= ~frame_tog;
                            frame_stb <= 1'b1;
                            left_ok   <= 1'b0;
                            if (good_frames != 8'hFF) good_frames <= good_frames + 8'd1;
                            if (good_frames + 8'd1 >= 8'(LOCK_FRAMES)) locked <= 1'b1;
                        end
                    end
                end
            end
        end
    end
endmodule

`default_nettype wire
