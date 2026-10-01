// SPDX-License-Identifier: GPL-3.0-or-later
// Host unit test for the game display's sound output queue (src/sn64_audioout.c) together with
// the resampler and its rate control (src/sn64_resample.c), against a model of the console's
// sound output: one block playing, one waiting behind it, played at the console's own rate.
//   * what is played is the game's sound in order: no pair repeated or out of place, left
//     and right kept together (the test sound is a slow triangle, moving by one each pair
//     with the right channel 1000 above the left, so any slip shows);
//   * the output never runs dry and never gets a block while it already holds two;
//   * the sound waiting to be played settles near its target with the clocks up to 300 ppm
//     apart, the hand-over a millisecond early or late, and one picture in twenty up to
//     10 ms late (the program hands over right after the console's vertical interrupt, so a
//     picture can be late but not early);
//   * no block ever ends on an 8 KiB address boundary, with buffers placed so that it would;
//   * an output that takes nothing does not hang or overrun anything, and sound comes back
//     once it takes blocks again.
// Build with -DSN64_FAULT_AOUT_NO_CARRY (the pairs held back for the next block are lost);
// the test must fail.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sn64_audioout.h"

#define ONE (1ull << 32)

static int checks, failures;

static void expect(int ok, const char *what)
{
    checks++;
    if (!ok) {
        failures++;
        printf("  FAIL %s\n", what);
    }
}

static unsigned lcg = 99991u;
static unsigned rnd(void) { lcg = lcg * 1664525u + 1013904223u; return lcg >> 8; }

// ---- the console's sound output ----
typedef struct {
    const int16_t *cur; int cur_len, cur_pos;      // the block being played
    const int16_t *nxt; int nxt_len;               // the block waiting behind it
    long dry;                                      // pairs of nothing: no block was there to play
    long refused;                                  // blocks handed over while two were already held
    long bad_end;                                  // blocks ending on an 8 KiB boundary
    int16_t *played; long n_played, cap;           // what came out
    int started;                                   // a real block has started (dry before that is the start-up)
} ai_t;

static void ai_queue(ai_t *ai, const int16_t *buf, int pairs)
{
    if ((((uintptr_t)buf + (uintptr_t)pairs * 4u) & 0x1FFFu) == 0 || (pairs & 1)) ai->bad_end++;
    if (!ai->cur) { ai->cur = buf; ai->cur_len = pairs; ai->cur_pos = 0; }
    else if (!ai->nxt) { ai->nxt = buf; ai->nxt_len = pairs; }
    else ai->refused++;
}

static void ai_play(ai_t *ai, int pairs)
{
    for (int i = 0; i < pairs; i++) {
        if (!ai->cur) { ai->dry++; continue; }
        if (ai->n_played < ai->cap) {
            ai->played[2 * ai->n_played] = ai->cur[2 * ai->cur_pos];
            ai->played[2 * ai->n_played + 1] = ai->cur[2 * ai->cur_pos + 1];
            ai->n_played++;
        }
        if (++ai->cur_pos == ai->cur_len) {
            ai->cur = ai->nxt; ai->cur_len = ai->nxt_len; ai->cur_pos = 0;
            ai->nxt = NULL;
        }
    }
}

// The game's sound: a triangle that moves by one each pair, 0 up to 30000 and back; right = left + 1000.
static void game_pairs(long first, int n, int16_t *out)
{
    for (int i = 0; i < n; i++) {
        long v = (first + i) % 60000;
        if (v > 30000) v = 60000 - v;
        out[2 * i] = (int16_t)v;
        out[2 * i + 1] = (int16_t)(v + 1000);
    }
}

typedef struct {
    long dry, refused, bad_end, order_errors, pair_errors, played;
    double wait_lo, wait_hi;                       // what waited just before a block was added, second half of the run
    double wait_end;                               // the same, averaged over the last 50 pictures
    unsigned dropped;
} result_t;

typedef struct {
    double ppm;            // the console plays this much faster than the game makes sound
    int jitter_pairs;      // every hand-over comes up to this early or late, in pairs of playing time
    int late_pairs;        // and one in twenty comes up to this late
    int frames;
    int stall_at, stall_frames;   // from this picture the output takes nothing for so many pictures (0: never)
    int skip_every;        // every so many pictures one hand-over is missed altogether (0: never)
    int skew;              // place the blocks so that their usual lengths would end on an 8 KiB boundary
} scenario_t;

static result_t run(scenario_t s)
{
    static int16_t arena[4 * 0x4000];              // room to place four blocks at chosen addresses
    static int16_t in[2 * 1024];
    static int16_t played[2 * 2400000];
    int16_t *blocks[SN64_AOUT_BLOCKS];
    sn64_aout_t a;
    ai_t ai;
    result_t r;
    memset(&ai, 0, sizeof(ai));
    memset(&r, 0, sizeof(r));
    ai.played = played; ai.cap = 2400000;
    for (int i = 0; i < SN64_AOUT_BLOCKS; i++) {
        // 16 KiB apart, from an 8 KiB boundary; with `skew` the block starts just below the next
        // boundary, so that a block of 530 + 2 i pairs would end exactly on it
        uintptr_t base = (((uintptr_t)arena + 0x2000u) & ~(uintptr_t)0x1FFFu) + (uintptr_t)i * 0x4000u;
        blocks[i] = (int16_t *)(s.skew ? base + 0x2000u - (uintptr_t)(530 + 2 * i) * 4u : base);
    }
    ai_queue(&ai, blocks[0], sn64_aout_start(&a, blocks, 533));

    // Time runs in pictures. Hand-over f happens at f plus its jitter; up to then the console has
    // played 532.4588 x (1 + ppm) pairs a picture and the game has made 532.4588.
    long played_total = 0, taken = 0, dry_start = 0;
    double last_t = -1.0, end_sum = 0.0;
    int end_n = 0;
    r.wait_lo = 1e9;
    for (int f = 0; f < s.frames; f++) {
        double t = f;
        if (s.jitter_pairs) t += ((double)(rnd() % 2001u) / 1000.0 - 1.0) * s.jitter_pairs / 532.4588;
        if (s.late_pairs && rnd() % 20u == 0) t += ((double)(rnd() % 1001u) / 1000.0) * s.late_pairs / 532.4588;
        if (t < 0.0) t = 0.0;
        if (t <= last_t) t = last_t + 0.01;
        if (s.skip_every && f % s.skip_every == s.skip_every - 1) continue;   // this hand-over never happens
        last_t = t;
        long due = (long)floor(532.4588 * (1.0 + s.ppm * 1e-6) * t);
        ai_play(&ai, (int)(due - played_total));
        played_total = due;
        if (f == 0) dry_start = ai.dry;            // (nothing has played yet)
        long made = (long)floor(532.4588 * t);
        int avail = (int)(made - taken);
        if (avail > 1023) { taken += avail - 1023; avail = 1023; }   // the FPGA's ring holds no more: the oldest are gone
        game_pairs(taken, avail, in);
        taken += avail;
        int stalled = s.stall_at && f >= s.stall_at && f < s.stall_at + s.stall_frames;
        int waiting = sn64_aout_waiting(&a, ai.cur != NULL, ai.cur ? ai.cur_len - ai.cur_pos : 0, ai.nxt != NULL);
        if (f > s.frames / 2 && !s.stall_at) {
            if (waiting < r.wait_lo) r.wait_lo = waiting;
            if (waiting > r.wait_hi) r.wait_hi = waiting;
        }
        if (f >= s.frames - 50) { end_sum += waiting; end_n++; }
        int pairs = 0;
        int16_t *buf = sn64_aout_feed(&a, in, avail, sn64_audio_step(ONE, waiting, SN64_AOUT_TARGET_PAIRS),
                                      ai.cur != NULL, ai.cur ? ai.cur_len - ai.cur_pos : 0, ai.nxt != NULL || stalled, &pairs);
        if (buf) ai_queue(&ai, buf, pairs);         // (never while stalled: feed returns NULL when full)
    }
    // What was played: after the opening silence the triangle, moving by 0, 1 or 2 each pair (the
    // rate control keeps the step a hair off 1.0), right exactly 1000 above left. A pair from the
    // wrong place, or a block played twice or not at all, breaks one or the other.
    long k = 0;
    while (k < ai.n_played && played[2 * k] == 0 && played[2 * k + 1] == 0) k++;
    long first_sound = k;
    for (k = first_sound + 8; k + 1 < ai.n_played; k++) {
        int l0 = played[2 * k], l1 = played[2 * (k + 1)], r0 = played[2 * k + 1];
        int d = l1 - l0;
        if (d < -2 || d > 2) { if (r.order_errors < 3) printf("    pair %ld: left %d then %d\n", k, l0, l1); r.order_errors++; }
        if (r0 - l0 != 1000) { if (r.pair_errors < 3) printf("    pair %ld: left %d right %d\n", k, l0, r0); r.pair_errors++; }
    }
    r.dry = ai.dry - dry_start; r.refused = ai.refused; r.bad_end = ai.bad_end; r.dropped = a.dropped;
    r.played = ai.n_played - first_sound;
    r.wait_end = end_n ? end_sum / end_n : 0.0;
    return r;
}

int main(void)
{
    char what[160];
    static const double offs[] = { -300.0, 0.0, 300.0 };
    const double target = SN64_AOUT_TARGET_PAIRS;

    // ---- steady pictures, clocks apart ----
    for (unsigned o = 0; o < 3; o++) {
        result_t r = run((scenario_t){ .ppm = offs[o], .frames = 4000 });
        printf("  console %+4.0f ppm, steady pictures: %ld pairs played, waiting sound %.0f to %.0f (target %d)\n",
               offs[o], r.played, r.wait_lo, r.wait_hi, SN64_AOUT_TARGET_PAIRS);
        snprintf(what, sizeof(what), "console %+.0f ppm: every pair played in order", offs[o]);
        expect(r.order_errors == 0 && r.played > 2000000, what);
        snprintf(what, sizeof(what), "console %+.0f ppm: left and right stay together", offs[o]);
        expect(r.pair_errors == 0, what);
        snprintf(what, sizeof(what), "console %+.0f ppm: the output never runs dry and never gets a third block", offs[o]);
        expect(r.dry == 0 && r.refused == 0, what);
        snprintf(what, sizeof(what), "console %+.0f ppm: nothing dropped", offs[o]);
        expect(r.dropped == 0, what);
        snprintf(what, sizeof(what), "console %+.0f ppm: waiting sound within 15 %% of its target", offs[o]);
        expect(r.wait_lo > target * 0.85 && r.wait_hi < target * 1.15, what);
    }

    // ---- every hand-over up to 1 ms (32 pairs) early or late, and one in twenty up to 10 ms (320 pairs) late ----
    for (unsigned o = 0; o < 3; o++) {
        result_t r = run((scenario_t){ .ppm = offs[o], .jitter_pairs = 32, .late_pairs = 320, .frames = 4000 });
        printf("  console %+4.0f ppm, hand-over +-1 ms and one in twenty up to 10 ms late: waiting sound %.0f to %.0f\n",
               offs[o], r.wait_lo, r.wait_hi);
        snprintf(what, sizeof(what), "console %+.0f ppm, late pictures: in order, together, nothing dropped, no third block", offs[o]);
        expect(r.order_errors == 0 && r.pair_errors == 0 && r.refused == 0 && r.dropped == 0, what);
        snprintf(what, sizeof(what), "console %+.0f ppm, late pictures: never dry", offs[o]);
        expect(r.dry == 0, what);
        snprintf(what, sizeof(what), "console %+.0f ppm, late pictures: no more than 40 ms of sound ever waiting", offs[o]);
        expect(r.wait_hi < 1280.0, what);
    }

    // ---- blocks placed so that their usual lengths would end on an 8 KiB boundary ----
    {
        result_t r = run((scenario_t){ .frames = 4000, .skew = 1 });
        expect(r.bad_end == 0, "no block ends on an 8 KiB boundary, and every length is a whole multiple of two pairs");
        expect(r.order_errors == 0 && r.pair_errors == 0 && r.dry == 0 && r.dropped == 0,
               "8 KiB rule: the pairs held back go out with the next block, in order");
        r = run((scenario_t){ .jitter_pairs = 32, .late_pairs = 320, .frames = 4000, .skew = 1 });
        expect(r.bad_end == 0 && r.order_errors == 0 && r.pair_errors == 0 && r.dropped == 0 && r.dry == 0, "8 KiB rule with late pictures: the same");
    }

    // ---- one hand-over in 400 missed altogether (the program was a whole picture late) ----
    {
        result_t r = run((scenario_t){ .frames = 4000, .skip_every = 400 });
        printf("  one hand-over in 400 missed (10 times): %ld pairs of nothing played, %ld breaks in the sound, %.0f pairs waiting at the end\n",
               r.dry, r.order_errors, r.wait_end);
        expect(r.dry > 0 && r.dry <= 10 * 200, "missed hand-over: a gap of at most 6 ms each time");
        expect(r.order_errors <= 10 * 6 && r.pair_errors <= 10 * 6, "missed hand-over: one break each time (the ring overflowed), nothing else out of place");
        expect(r.refused == 0 && r.dropped == 0, "missed hand-over: nothing handed to a full output, nothing dropped by the queue");
        expect(r.wait_end > target * 0.8 && r.wait_end < target * 1.2, "missed hand-over: the waiting sound comes back to its target");
    }

    // ---- an output that takes nothing for 40 pictures, then works again ----
    {
        result_t r = run((scenario_t){ .frames = 3000, .stall_at = 500, .stall_frames = 40 });
        printf("  stalled output for 40 pictures: %u pairs dropped, %ld pairs of nothing played, %ld breaks\n", r.dropped, r.dry, r.order_errors);
        expect(r.dropped > 15000 && r.dropped < 22000, "stalled output: what could not be played is dropped, about 40 pictures' worth");
        expect(r.refused == 0, "stalled output: nothing is handed over while it is full");
        expect(r.dry > 0 && r.dry < 22000, "stalled output: silence while stalled, then sound again");
        expect(r.order_errors <= 8, "stalled output: one break in the sound, then in order again");
        expect(r.wait_end > target * 0.8 && r.wait_end < target * 1.2, "stalled output: the waiting sound comes back to its target");
    }

    printf("test_audioout: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}

