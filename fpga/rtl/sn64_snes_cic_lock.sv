// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 SNES-side CIC lock (console lockout chip, F411/F413 lock role).
//
// Talks to the key CIC inside a real SNES cartridge (D411/F411 NTSC or
// D413/F413 PAL, or the key built into SA-1/S-DD1 style chips) so that carts
// which check for a working lock keep running, and reports the region implied
// by the key.
//
// Written for SN64 from published descriptions of the algorithm, not copied
// from any implementation:
//   * segher, "The weird and wonderful CIC", hackmii.com, 2010-01
//     (lock/key exchange one bit each per step and compare with a locally
//     computed copy of the other side's stream).
//   * Super Famicom Development Wiki, "CIC" page (wiki.superfamicom.org/cic):
//     D411/D413 seed tables and the C description of the table update
//     ("mangle"), including the stream-select nibble sent lock->key in bit
//     order 3-0-1-2 and the D411/D413 difference (lock-expected table nibble 2
//     is 9 or 6).
//   * Behaviour and instruction-cycle timing were read (not copied) from the
//     GPL-2.0-only SuperCIC lock source in sd2snes (cic/supercic), which is a
//     proven drop-in lock; the timing parameters below are derived from it.
// See docs/design/snes-cic-implementation.md for evidence and limits. The
// timing has NOT been checked against a real key CIC.
//
// Pin roles (socket contacts, hardware/sn64/interfaces/snes-pin-map.csv):
//   CIC_CLK         56  console output, generated here by dividing `clk`
//   CIC_DATA0       55  lock drives it during the seed and in rounds with dir=1
//   CIC_DATA1       24  lock drives it in rounds with dir=0
//   CIC_SLAVE_RESET 25  lock->key reset, pulsed high then low to start the key
// A released data pin (oe=0) must be defined by an external pull-down.
//
// Policy: `enforce`=0 is the SuperCIC-style pass-through (the console is
// released after the first round whether or not the key answered; failure is
// only reported). `enforce`=1 behaves like an original lock: the console runs
// only while every received bit has matched.
`default_nettype none

module sn64_snes_cic_lock #(
    // Master clocks per CIC_CLK period. 21.477272 MHz / 6 = 3.579545 MHz.
    parameter int unsigned CLK_DIV       = 6,
    // CIC clocks per lock instruction cycle (SuperCIC runs a PIC from the
    // same clock pin: 4 clocks per instruction).
    parameter int unsigned CPI           = 4,
    // Timing, in instruction cycles, derived from the SuperCIC lock program.
    parameter int unsigned T_PWRUP       = 49605, // wait before starting the key
    parameter int unsigned T_KRESET      = 3,     // slave reset high time
    parameter int unsigned T_SEED_FIRST  = 630,   // reset release -> first seed bit
    parameter int unsigned T_SEED_PERIOD = 15,    // seed bit period
    parameter int unsigned T_SEED_HIGH   = 3,     // seed bit high time
    parameter int unsigned T_SEED_SWAP   = 686,   // reset release -> lock stops driving DATA0
    parameter int unsigned T_ROUND1      = 806,   // reset release -> first slot start
    parameter int unsigned T_SLOT        = 93,    // one bit exchange
    parameter int unsigned T_OUT_ON      = 10,    // slot start -> own bit driven
    parameter int unsigned T_OUT_OFF     = 16,    // slot start -> own bit cleared
    // SN64 choice (not in the original): the lock's own seed and round pulses
    // are widened by this many instruction cycles on both sides, so a key
    // that samples a little early or late still reads the right level. The
    // original 3/6-cycle windows lie inside the widened ones.
    parameter int unsigned T_WIDEN       = 4,
    parameter int unsigned C_SAMPLE      = 50,    // slot start -> sample (CIC clocks)
    parameter int unsigned T_LAST_BASE   = 145,   // last slot + 3 mangle calls + tail, excl. iterations
    parameter int unsigned T_TAIL_NZ     = 5,     // restart index != 0
    parameter int unsigned T_TAIL_Z      = 7,     // restart index == 0
    parameter int unsigned T_ITER_NOSKIP = 78,    // one mangle iteration, no carry at step 3
    parameter int unsigned T_ITER_SKIP   = 84     // one mangle iteration, carry at step 3
) (
    input  wire        clk,          // 21.477 MHz master clock
    input  wire        reset_n,      // synchronous, active low
    input  wire        enable,       // cartridge powered and permitted; 0 = idle, all lines released
    input  wire        enforce,      // 1 = hold console unless the key passes
    input  wire        default_pal,  // region reported without a valid key
    input  wire [3:0]  seed,         // stream-select nibble, sampled when the key is reset

    output logic       cic_clk,      // to CIC_CLK (56)
    output logic       slave_reset,  // to CIC_SLAVE_RESET (25)
    output logic       data0_o,      // CIC_DATA0 (55)
    output logic       data0_oe,
    input  wire        data0_i,
    output logic       data1_o,      // CIC_DATA1 (24)
    output logic       data1_oe,
    input  wire        data1_i,

    output logic       console_run,  // 1 = console may leave reset
    output logic       key_ok,       // first round passed and no mismatch since
    output logic       key_fail,     // sticky: a received bit did not match
    output logic       region_valid, // region below comes from a passing key
    output logic       region_pal,   // 1 = 50 Hz (F413/D413), 0 = 60 Hz
    output logic [15:0] rounds_done, // completed exchange rounds (diagnostic)
    output logic [2:0]  phase        // sequencer state (diagnostic)
);

    typedef logic [15:0][3:0] cic_tbl_t;   // element 0 unused

    // Stream the lock sends: b14f4b57fd61e98 (elements 1..15).
    localparam cic_tbl_t LOCK_INIT = {4'h8, 4'h9, 4'he, 4'h1, 4'h6, 4'hd, 4'hf, 4'h7,
                                      4'h5, 4'hb, 4'h4, 4'hf, 4'h4, 4'h1, 4'hb, 4'h0};
    // Stream the key sends: <seed> <9|6> a185f11e10dec. Elements 1 and 2 are
    // filled in at run time.
    localparam cic_tbl_t KEY_INIT  = {4'hc, 4'he, 4'hd, 4'h0, 4'h1, 4'he, 4'h1, 4'h1,
                                      4'hf, 4'h5, 4'h8, 4'h1, 4'ha, 4'h0, 4'h0, 4'h0};

    localparam int unsigned C_PWRUP      = T_PWRUP * CPI;
    localparam int unsigned C_KRESET     = T_KRESET * CPI;
    localparam int unsigned C_SEED_FIRST = T_SEED_FIRST * CPI;
    localparam int unsigned C_SEED_PER   = T_SEED_PERIOD * CPI;
    localparam int unsigned C_SEED_HIGH  = T_SEED_HIGH * CPI;
    localparam int unsigned C_SEED_SWAP  = T_SEED_SWAP * CPI;
    localparam int unsigned C_ROUND1     = T_ROUND1 * CPI;
    localparam int unsigned C_SLOT       = T_SLOT * CPI;
    localparam int unsigned C_OUT_ON     = T_OUT_ON * CPI;
    localparam int unsigned C_OUT_OFF    = T_OUT_OFF * CPI;
    localparam int unsigned C_WIDEN      = T_WIDEN * CPI;
    localparam int unsigned C_LAST_BASE  = T_LAST_BASE * CPI;
    localparam int unsigned C_TAIL_NZ    = T_TAIL_NZ * CPI;
    localparam int unsigned C_TAIL_Z     = T_TAIL_Z * CPI;
    localparam int unsigned C_ITER_NS    = T_ITER_NOSKIP * CPI;
    localparam int unsigned C_ITER_S     = T_ITER_SKIP * CPI;

    // One iteration of the published table update. `skip` reports the carry
    // at step 3, which changes both the result and the iteration's duration.
    function automatic cic_tbl_t mangle_iter(input cic_tbl_t d, input logic [3:0] x,
                                             output logic skip);
        cic_tbl_t n;
        logic [5:0] a;
        logic [5:0] s;
        int unsigned o;
        n = d;
        a = {2'b0, x} + {2'b0, n[1]} + 6'd1;          // step 1
        n[1] = a[3:0];
        a = {2'b0, n[1]} + {2'b0, n[2]} + 6'd1;       // step 2 (complemented)
        s = {2'b0, ~a[3:0]};
        a = {2'b0, n[2]};
        n[2] = s[3:0];
        a = a + {2'b0, n[3]} + 6'd1;                  // step 3, store skipped on carry
        skip = (a >= 6'h10);
        if (!skip) begin
            s = a; a = {2'b0, n[3]}; n[3] = s[3:0]; o = 4;
        end else begin
            o = 3;
        end
        a = a + {2'b0, n[o]};                         // step 4
        n[o] = a[3:0];
        a = {2'b0, n[o]};
        s = a + {2'b0, n[o+1]};                       // step 5
        a = {2'b0, n[o+1]};
        n[o+1] = s[3:0];
`ifdef SN64_FAULT_CIC_MANGLE
        a = a + 6'd7;                                 // injected algorithm error
`else
        a = a + 6'd8;                                 // step 6
`endif
        if (a < 6'h10) a = a + {2'b0, n[o+2]};
        s = a; a = {2'b0, n[o+2]}; n[o+2] = s[3:0];
        for (int k = 6; k < 16; k++) begin            // chain to the end
            if (k >= o + 3) begin
                a = a + 6'd1 + {2'b0, n[k]};
                n[k] = a[3:0];
                a = {2'b0, n[k]};
            end
        end
        return n;
    endfunction

    // ---------------------------------------------------------------- CIC_CLK
    localparam int unsigned DIVW = (CLK_DIV > 2) ? $clog2(CLK_DIV) : 1;
    wire run = reset_n && enable;
    logic [DIVW-1:0] div_cnt;
    logic tick;                      // coincides with the CIC_CLK rising edge
    assign tick = run && (div_cnt == DIVW'(CLK_DIV - 1));

    always_ff @(posedge clk) begin
        if (!run) begin
            div_cnt <= DIVW'(CLK_DIV - 1);   // first CIC_CLK cycle is full length
            cic_clk <= 1'b0;
        end else begin
            div_cnt <= tick ? '0 : div_cnt + 1'b1;
            cic_clk <= tick ? 1'b1 : ((div_cnt + 1'b1) < DIVW'(CLK_DIV / 2));
        end
    end

    // Inputs come from the 5 V domain through translators: synchronise.
    logic [1:0] d0_s, d1_s;
    always_ff @(posedge clk) begin
        d0_s <= {d0_s[0], data0_i};
        d1_s <= {d1_s[0], data1_i};
    end

    // -------------------------------------------------------------- sequencer
    typedef enum logic [2:0] {S_IDLE, S_PWRUP, S_KRESET, S_SEED, S_ROUND} state_t;
    state_t st;
    logic [19:0] t;                  // CIC clocks within the current phase/slot
    logic [19:0] slot_len;
    logic [3:0]  idx;
    logic        dir;                // 0: lock drives DATA1, 1: lock drives DATA0
    logic        first_round;
    logic        first_done;
    logic        det_pal;
    logic [3:0]  seed_q;
    cic_tbl_t    lt, kt;

    // Mangle engine (one iteration per master clock).
    logic        mg_start, mg_busy, mg_fin;
    logic [2:0]  mg_n;               // 0-2: lock table, 3-5: key table
    logic [3:0]  mg_x;
    logic [19:0] mg_cost;

    wire rx_bit = dir ? d1_s[1] : d0_s[1];

    logic seed_pulse;
    always_comb begin
        seed_pulse = 1'b0;
        for (int k = 0; k < 4; k++) begin
            if (t >= 20'(C_SEED_FIRST + k * C_SEED_PER - C_WIDEN) &&
                t <  20'(C_SEED_FIRST + k * C_SEED_PER + C_SEED_HIGH + C_WIDEN)) begin
                case (k)
                    0: seed_pulse = seed_q[3];
                    1: seed_pulse = seed_q[0];
                    2: seed_pulse = seed_q[1];
                    default: seed_pulse = seed_q[2];
                endcase
            end
        end
    end

    logic mismatch;
    always_comb begin
        mismatch = 1'b0;
        if (st == S_ROUND && tick && t == 20'(C_SAMPLE) && !(first_round && idx == 4'd2))
            mismatch = (rx_bit != kt[idx][0]);
`ifdef SN64_FAULT_CIC_NO_COMPARE
        mismatch = 1'b0;
`endif
    end

    always_ff @(posedge clk) begin
        if (!run) begin
            st          <= S_IDLE;
            t           <= '0;
            slot_len    <= 20'(C_SLOT);
            idx         <= 4'd1;
            dir         <= 1'b0;
            first_round <= 1'b1;
            first_done  <= 1'b0;
            det_pal     <= 1'b0;
            seed_q      <= 4'd0;
            lt          <= LOCK_INIT;
            kt          <= KEY_INIT;
            key_ok      <= 1'b0;
            key_fail    <= 1'b0;
            rounds_done <= '0;
            mg_start    <= 1'b0;
            mg_busy     <= 1'b0;
            mg_fin      <= 1'b0;
            mg_n        <= '0;
            mg_x        <= '0;
            mg_cost     <= '0;
        end else begin
            mg_start <= 1'b0;
            if (st == S_IDLE) begin
                st <= S_PWRUP;
                t  <= '0;
            end else if (tick) begin
                case (st)
                    S_PWRUP: begin
                        if (t == 20'(C_PWRUP - 1)) begin
                            st <= S_KRESET; t <= '0;
                            seed_q <= seed;
                        end else t <= t + 1'b1;
                    end
                    S_KRESET: begin
                        if (t == 20'(C_KRESET - 1)) begin
                            st <= S_SEED; t <= '0;
                            lt <= LOCK_INIT;
                            kt <= KEY_INIT;
                            kt[1] <= seed_q;
                        end else t <= t + 1'b1;
                    end
                    S_SEED: begin
                        if (t == 20'(C_ROUND1 - 1)) begin
                            st <= S_ROUND; t <= '0;
                            idx <= 4'd1; dir <= 1'b0; first_round <= 1'b1;
                            slot_len <= 20'(C_SLOT);
                        end else t <= t + 1'b1;
                    end
                    S_ROUND: begin
                        if (t == 20'(C_SAMPLE)) begin
                            if (first_round && idx == 4'd2) begin
                                // Region: key nibble 2 is 9 (D/F411) or 6 (D/F413).
                                kt[2]   <= rx_bit ? 4'h9 : 4'h6;
                                det_pal <= !rx_bit;
                            end else if (mismatch) begin
                                key_fail <= 1'b1;
                                key_ok   <= 1'b0;
                            end
                        end
                        if (t == 20'(C_OUT_OFF) && idx == 4'd15)
                            mg_start <= 1'b1;
                        if (t == slot_len - 1'b1) begin
                            t <= '0;
                            if (idx == 4'd15) begin
                                rounds_done <= rounds_done + 1'b1;
                                first_round <= 1'b0;
                                if (first_round) begin
                                    first_done <= 1'b1;
                                    key_ok     <= !key_fail;
                                end
                                idx      <= (kt[7] == 4'd0) ? 4'd1 : kt[7];
                                dir      <= kt[7][0];
                                slot_len <= 20'(C_SLOT);
                            end else begin
                                idx <= idx + 1'b1;
                            end
                        end else t <= t + 1'b1;
                    end
                    default: ;
                endcase
            end

            // Table update between rounds: 3 mangles of each table. The
            // accumulated duration sets the length of the round's last slot.
            if (mg_start) begin
                mg_busy <= 1'b1;
                mg_n    <= 3'd0;
                mg_x    <= lt[15];
                mg_cost <= '0;
            end else if (mg_busy) begin
                logic     sk;
                cic_tbl_t nt;
                if (mg_n < 3'd3) begin
                    nt = mangle_iter(lt, mg_x, sk);
                    lt <= nt;
                end else begin
                    nt = mangle_iter(kt, mg_x, sk);
                    kt <= nt;
                end
                mg_cost <= mg_cost + (sk ? 20'(C_ITER_S) : 20'(C_ITER_NS));
                if (mg_x == 4'd0) begin
                    if (mg_n == 3'd5) begin
                        mg_busy <= 1'b0;
                        mg_fin  <= 1'b1;
                    end else begin
                        mg_n <= mg_n + 1'b1;
                        mg_x <= (mg_n == 3'd2) ? kt[15] : nt[15];
                    end
                end else begin
                    mg_x <= mg_x - 1'b1;
                end
            end
            if (mg_fin) begin
                mg_fin   <= 1'b0;
                slot_len <= 20'(C_LAST_BASE) + mg_cost +
                            ((kt[7] == 4'd0) ? 20'(C_TAIL_Z) : 20'(C_TAIL_NZ));
            end
        end
    end

    // ----------------------------------------------------------------- outputs
    wire in_gap = (idx == 4'd15) && (t >= 20'(C_OUT_OFF + C_WIDEN));
    wire own_bit = (t >= 20'(C_OUT_ON - C_WIDEN)) && (t < 20'(C_OUT_OFF + C_WIDEN)) && lt[idx][0];
    // After a detected mismatch the key is out of step and may drive either
    // pin, so the lock stops driving the data pins (it keeps sequencing and
    // reporting). This prevents a push-pull fight with a desynchronised key.
    wire may_drive = !key_fail;

    always_ff @(posedge clk) begin
        if (!run) begin
            slave_reset  <= 1'b0;
            data0_o      <= 1'b0;
            data0_oe     <= 1'b0;
            data1_o      <= 1'b0;
            data1_oe     <= 1'b0;
            console_run  <= 1'b0;
            region_valid <= 1'b0;
            region_pal   <= default_pal;
        end else begin
            slave_reset <= (st == S_KRESET);
            data0_o  <= 1'b0; data0_oe <= 1'b0;
            data1_o  <= 1'b0; data1_oe <= 1'b0;
            // The lock drives a data pin only while it needs to: DATA0 until
            // shortly after the last seed bit, then its round output pin from
            // the first slot of a round to the end of its last bit. Both pins
            // are released across every direction change.
            if (st == S_SEED && t < 20'(C_SEED_SWAP)) begin
                data0_oe <= 1'b1;
                data0_o  <= seed_pulse;
            end else if (st == S_ROUND && !in_gap && may_drive) begin
                if (dir) begin data0_oe <= 1'b1; data0_o <= own_bit; end
                else     begin data1_oe <= 1'b1; data1_o <= own_bit; end
            end
            console_run  <= first_done && (!enforce || key_ok);
            region_valid <= key_ok;
            region_pal   <= key_ok ? det_pal : default_pal;
        end
    end

    assign phase = st;

endmodule

`default_nettype wire
