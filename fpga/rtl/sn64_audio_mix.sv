// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 cartridge-audio mixer: elastic buffer + saturating mix into the SNES
// DSP sample stream that feeds the N64 endpoint's audio ring (sn64_frame_window,
// docs/design/console-video-path.md).
//
// Rates. The SNES side produces one stereo sample per `snes_ready` pulse at
// the core's DSP rate (clk_snes domain). The cartridge ADC delivers one
// stereo frame per LRCK period from its own oscillator (nominally 32 kHz).
// The two never share a clock, so their long-term rates differ by the sum
// of both clock errors (and, with the pinned SNESTang DSP constant, by a
// fixed offset; see docs/design/cart-audio-implementation.md).
//
// Elastic buffer. ADC frames arrive through a toggle synchroniser (the
// receiver holds each frame for a whole LRCK period) and are written into a
// 2^FIFO_AW-entry FIFO in the clk_snes domain. Reading starts once the FIFO
// is half full. Each SNES sample pops one ADC frame. Rate mismatch is
// absorbed by slipping exactly one sample:
//   * overflow  (ADC faster, FIFO full, no pop on that clock): the incoming
//     ADC frame is dropped;
//   * underflow (ADC slower, FIFO empty): the previous ADC frame is repeated.
// The SNES stream is never delayed, dropped or repeated: exactly one output
// per `snes_ready`, one clock later, so the sn64_av_out audio contract
// (16-bit words, rising edge of `audio_ready`) is unchanged.
//
// Mix. out = sat16(snes + cart_scaled), cart_scaled = (adc * CART_GAIN_Q12)
// >>> (ADC_BITS - 16 + 12) (arithmetic shift, i.e. floor). With the default
// gain of 1.0 an ADC full-scale word maps to 16-bit full scale (adc[23:8]).
// The SNES DSP output is already clamped to 16 bits by the core, so the sum
// needs one extra bit; there is 0 dB headroom for coincident full-scale
// peaks and the result saturates at +32767 / -32768 (never wraps). CART_GAIN
// is PROVISIONAL until the analog front end (cartridge line level versus
// ADC full scale) and the level of cartridge audio relative to the DSP on a
// real console are measured.
//
// With cart_enable low, or the ADC not locked, the buffer is flushed and the
// SNES samples pass through bit-exact.
`default_nettype none

module sn64_audio_mix #(
    parameter int        ADC_BITS      = 24,
    parameter int        FIFO_AW       = 3,          // FIFO depth 2^FIFO_AW stereo frames
    parameter bit [15:0] CART_GAIN_Q12 = 16'd4096    // unsigned Q4.12, 4096 = 1.0 (PROVISIONAL)
) (
    input  wire                        clk,          // clk_snes
    input  wire                        rst_n,        // synchronous, active low (clk_snes domain)
    input  wire                        cart_enable,  // 0: SNES audio only (buffer flushed)
    // ADC receiver side (another clock domain; words stable while adc_tog is unchanged)
    input  wire signed [ADC_BITS-1:0]  adc_left, adc_right,
    input  wire                        adc_tog,
    input  wire                        adc_locked,
    // SNES DSP stream (clk_snes)
    input  wire [15:0]                 snes_left, snes_right,
    input  wire                        snes_ready,
    // Mixed stream to sn64_av_out (clk_snes)
    output logic [15:0]                mix_left = 16'd0, mix_right = 16'd0,
    output logic                       mix_ready = 1'b0,
    // Status (clk_snes)
    output logic [15:0]                overflow_slips = 16'd0,   // ADC frames dropped
    output logic [15:0]                underflow_slips = 16'd0,  // ADC frames repeated
    output logic                       cart_active = 1'b0,       // buffer primed, cartridge audio mixed
    output logic [FIFO_AW:0]           fill
);
    localparam int DEPTH   = 1 << FIFO_AW;
    localparam int PREFILL = DEPTH / 2;
    localparam int SHIFT   = ADC_BITS - 16 + 12;

    // ------------------------------------------------------------------
    // Crossing from the receiver clock: toggle synchroniser, lock level.
    // ------------------------------------------------------------------
    wire tog_s, lock_s;
    sn64_sync_bit s_tog  (.clk(clk), .d(adc_tog),    .q(tog_s));
    sn64_sync_bit s_lock (.clk(clk), .d(adc_locked), .q(lock_s));
    logic tog_d = 1'b0, ready_q = 1'b0;
    wire  frame_evt = (tog_s != tog_d);
    wire  snes_evt  = snes_ready && !ready_q;
    wire  run       = rst_n && cart_enable && lock_s;

    // ------------------------------------------------------------------
    // FIFO (distributed RAM, asynchronous read of the head)
    // ------------------------------------------------------------------
    logic [2*ADC_BITS-1:0] mem [0:DEPTH-1];
    logic [FIFO_AW:0] wptr = '0, rptr = '0;
    assign fill = wptr - rptr;
    wire empty = (fill == '0);
    wire full  = (fill == (FIFO_AW+1)'(DEPTH));

    wire do_pop    = snes_evt && cart_active && !empty;
    wire underflow = snes_evt && cart_active && empty;
    wire do_push   = frame_evt && run && (!full || do_pop);
    wire overflow  = frame_evt && run && full && !do_pop;

    logic [2*ADC_BITS-1:0] last = '0;
    wire  [2*ADC_BITS-1:0] head = mem[rptr[FIFO_AW-1:0]];
    wire  [2*ADC_BITS-1:0] cart = !cart_active ? '0 : (do_pop ? head : last);

    // ------------------------------------------------------------------
    // Mix arithmetic
    // ------------------------------------------------------------------
    function automatic logic [15:0] mix1(input logic [15:0] s, input logic [ADC_BITS-1:0] a);
        logic signed [ADC_BITS+17:0] prod;
        logic signed [ADC_BITS+17:0] scaled;
        logic signed [ADC_BITS+17:0] sum;
`ifdef SN64_FAULT_AUDIO_NO_SIGNEXT
        prod = $signed({18'd0, a}) * $signed({{(ADC_BITS+2){1'b0}}, CART_GAIN_Q12});   // fault: ADC word zero-extended
`else
        prod = $signed({{18{a[ADC_BITS-1]}}, a}) * $signed({{(ADC_BITS+2){1'b0}}, CART_GAIN_Q12});
`endif
        scaled = prod >>> SHIFT;
        sum = scaled + $signed({{(ADC_BITS+2){s[15]}}, s});
`ifdef SN64_FAULT_AUDIO_WRAP
        return sum[15:0];                                                                 // fault: wraps instead of saturating
`else
        if (sum > $signed((ADC_BITS+18)'(32767)))       return 16'h7FFF;
        else if (sum < -$signed((ADC_BITS+18)'(32768))) return 16'h8000;
        else                                             return sum[15:0];
`endif
    endfunction

    always_ff @(posedge clk) begin
        mix_ready <= 1'b0;
        tog_d     <= tog_s;
        if (!rst_n) begin
            ready_q <= 1'b0;
            mix_left <= 16'd0; mix_right <= 16'd0;
            wptr <= '0; rptr <= '0; last <= '0; cart_active <= 1'b0;
            overflow_slips <= 16'd0; underflow_slips <= 16'd0;
        end else begin
            ready_q <= snes_ready;
            // Buffer control
            if (!run) begin
                wptr <= '0; rptr <= '0; last <= '0; cart_active <= 1'b0;
            end else begin
                if (do_push) begin
                    mem[wptr[FIFO_AW-1:0]] <= {adc_left, adc_right};
                    wptr <= wptr + 1'b1;
                end
                if (do_pop) rptr <= rptr + 1'b1;
                if (!cart_active && fill >= (FIFO_AW+1)'(PREFILL)) cart_active <= 1'b1;
                if (overflow  && overflow_slips  != 16'hFFFF) overflow_slips  <= overflow_slips + 16'd1;
                if (underflow && underflow_slips != 16'hFFFF) underflow_slips <= underflow_slips + 16'd1;
            end
            // One output per SNES sample, one clock later.
            if (snes_evt) begin
                last      <= cart;
                mix_left  <= mix1(snes_left,  cart[2*ADC_BITS-1:ADC_BITS]);
                mix_right <= mix1(snes_right, cart[ADC_BITS-1:0]);
                mix_ready <= 1'b1;
            end
        end
    end
endmodule

`default_nettype wire
