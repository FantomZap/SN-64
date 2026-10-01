// SPDX-License-Identifier: GPL-3.0-or-later
// Host unit test for the game display's sound path (src/sn64_resample.c):
//   * a step of exactly 1.0 passes the samples through unchanged (three samples late);
//   * a steady level stays steady at any step;
//   * cutting the input into pieces of any size gives bit-identical output;
//   * the number of samples out is the number in divided by the step;
//   * tones come out at the right place in time and close to the ideal curve;
//   * the integer arithmetic matches a floating-point reference on full-scale noise;
//   * the rate control holds the sound waiting in the console's output near its target
//     for clocks up to 300 ppm apart, never running dry.
// Build with -DSN64_FAULT_RESAMPLE_NO_CARRY (the position's carry is lost); the test must fail.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sn64_resample.h"

#define ONE (1ull << 32)
static const double PI = 3.14159265358979323846;

static int checks, failures;

static void expect(int ok, const char *what)
{
    checks++;
    if (!ok) {
        failures++;
        printf("  FAIL %s\n", what);
    }
}

static unsigned lcg = 2463534242u;
static unsigned rnd(void) { lcg = lcg * 1664525u + 1013904223u; return lcg >> 8; }

static uint64_t q32(double x) { return (uint64_t)llround(x * 4294967296.0); }

// The same curve in floating point.
static double ref_cubic(double p0, double p1, double p2, double p3, double t)
{
    double y = p1 + 0.5 * t * ((p2 - p0) + t * ((2 * p0 - 5 * p1 + 4 * p2 - p3) + t * (-p0 + 3 * p1 - 3 * p2 + p3)));
    return y > 32767 ? 32767 : y < -32768 ? -32768 : y;
}

// Run `n` pairs through in one call. Returns the pairs written.
static int run_all(const int16_t *in, int n, int16_t *out, int max_out, uint64_t step)
{
    sn64_resample_t r;
    int used = 0;
    sn64_resample_reset(&r);
    int o = sn64_resample(&r, in, n, &used, out, max_out, step);
    return used == n ? o : -1;
}

int main(void)
{
    enum { N = 40000 };
    static int16_t in[2 * N], out[2 * (N + 2000)], out2[2 * (N + 2000)];
    char what[128];

    // ---- 1. step 1.0: unchanged, three samples late ----
    for (int i = 0; i < N; i++) { in[2 * i] = (int16_t)(rnd() & 0xFFFF); in[2 * i + 1] = (int16_t)(rnd() & 0xFFFF); }
    {
        int o = run_all(in, N, out, N + 2000, ONE);
        int bad = 0;
        for (int k = 3; k < o; k++)
            if (out[2 * k] != in[2 * (k - 3)] || out[2 * k + 1] != in[2 * (k - 3) + 1]) bad++;
        expect(o == N + 1, "step 1.0: one sample out for each one in");
        expect(bad == 0, "step 1.0: every sample unchanged, left and right kept apart");
        expect(out[0] == 0 && out[2] == 0 && out[4] == 0, "step 1.0: silence until the first sample arrives");
    }

    // ---- 2. a steady level stays steady ----
    for (int i = 0; i < N; i++) { in[2 * i] = 12345; in[2 * i + 1] = -23456; }
    {
        static const double steps[] = { 1.000040, 0.999842, 1.0045, 0.9955 };
        int bad = 0;
        for (unsigned s = 0; s < 4; s++) {
            int o = run_all(in, N, out, N + 2000, q32(steps[s]));
            for (int k = 8; k < o; k++) if (out[2 * k] != 12345 || out[2 * k + 1] != -23456) bad++;
        }
        expect(bad == 0, "a steady level is reproduced exactly at every step");
    }

    // ---- 3. pieces of any size give the same output; 4. the count is right ----
    for (int i = 0; i < N; i++) { in[2 * i] = (int16_t)(rnd() & 0xFFFF); in[2 * i + 1] = (int16_t)(rnd() & 0xFFFF); }
    {
        static const double steps[] = { 1.000040, 0.999842, 1.0045, 0.9955, 1.0 };
        for (unsigned s = 0; s < 5; s++) {
            uint64_t step = q32(steps[s]);
            int o1 = run_all(in, N, out, N + 2000, step);
            sn64_resample_t r;
            int o2 = 0, pos = 0;
            sn64_resample_reset(&r);
            while (pos < N) {
                int chunk = (int)(rnd() % 700u), used = 0;         // 0 to 699 pairs, as the ring delivers them
                int room = (int)(rnd() % 600u) + 1;                // and an output that fills up now and then
                if (chunk > N - pos) chunk = N - pos;
                o2 += sn64_resample(&r, in + 2 * pos, chunk, &used, out2 + 2 * o2, room, step);
                pos += used;
            }
            {   // drain what the last call could not place
                int used = 0;
                o2 += sn64_resample(&r, in, 0, &used, out2 + 2 * o2, N + 2000 - o2, step);
            }
            snprintf(what, sizeof(what), "step %.6f: cut into random pieces, same output", steps[s]);
            expect(o1 == o2 && memcmp(out, out2, (size_t)o1 * 4) == 0, what);
            snprintf(what, sizeof(what), "step %.6f: %d in gives %d out", steps[s], N, o1);
            expect(abs(o1 - (int)floor(N / steps[s]) - 1) <= 1, what);
        }
    }

    // ---- 5. tones land at the right time and on the ideal curve ----
    {
        static const struct { double hz, limit; } tones[] = { { 1000.0, 16.0 }, { 4000.0, 400.0 }, { 8000.0, 2400.0 } };
        static const double steps[] = { 1.000040, 0.999842, 1.0045 };
        for (unsigned t = 0; t < 3; t++) {
            double worst = 0.0;
            for (unsigned s = 0; s < 3; s++) {
                for (int i = 0; i < N; i++) {
                    in[2 * i] = (int16_t)lround(20000.0 * sin(2 * PI * tones[t].hz * i / 32000.0));
                    in[2 * i + 1] = (int16_t)lround(20000.0 * cos(2 * PI * tones[t].hz * i / 32000.0));
                }
                // the step as the resampler holds it, so the expected position is exact
                uint64_t step = q32(steps[s]);
                double st = (double)step / 4294967296.0;
                int o = run_all(in, N, out, N + 2000, step);
                for (int k = 8; k < o - 8; k++) {
                    double at = k * st - 3.0;                      // input sample index this output stands at
                    double l = 20000.0 * sin(2 * PI * tones[t].hz * at / 32000.0);
                    double r = 20000.0 * cos(2 * PI * tones[t].hz * at / 32000.0);
                    if (fabs(out[2 * k] - l) > worst) worst = fabs(out[2 * k] - l);
                    if (fabs(out[2 * k + 1] - r) > worst) worst = fabs(out[2 * k + 1] - r);
                }
            }
            printf("  tone %5.0f Hz at amplitude 20000: worst error %.1f\n", tones[t].hz, worst);
            snprintf(what, sizeof(what), "%.0f Hz tone within %.0f of the ideal curve", tones[t].hz, tones[t].limit);
            expect(worst <= tones[t].limit, what);
        }
    }

    // ---- 6. integer arithmetic against the floating-point curve, full-scale noise and edges ----
    {
        double worst = 0.0;
        for (int i = 0; i < N; i++) {
            int16_t v = (i % 16 < 8) ? 32767 : -32768;             // full-scale square for the first half
            if (i >= N / 2) v = (int16_t)(rnd() & 0xFFFF);          // full-scale noise for the second
            in[2 * i] = v; in[2 * i + 1] = (int16_t)-v;
        }
        uint64_t step = q32(1.0045);
        int o = run_all(in, N, out, N + 2000, step);
        uint64_t pos = 0;                                           // 32 fraction bits, as the resampler counts
        for (int k = 0; k < o; k++, pos += step) {
            long j = (long)(pos >> 32) - 3;                         // index of p1
            double t = (double)((uint32_t)pos >> 17) / 32768.0;
            double p[4];
            for (int m = 0; m < 4; m++) { long idx = j - 1 + m; p[m] = (idx >= 0 && idx < N) ? in[2 * idx] : 0.0; }
            double want = ref_cubic(p[0], p[1], p[2], p[3], t);
            if (fabs(out[2 * k] - want) > worst) worst = fabs(out[2 * k] - want);
        }
        printf("  integer curve against floating point on full-scale square and noise: worst difference %.2f\n", worst);
        expect(worst <= 2.0, "integer arithmetic within 2 of the floating-point curve at full scale (no overflow, clamped)");
    }

    // ---- 7. rate control: the step ----
    expect(sn64_audio_step(ONE, 384, 384) == ONE, "rate control: on target, the nominal step");
    expect(llabs((long long)(sn64_audio_step(ONE, 768, 384) - q32(1.005))) < 5000, "rate control: twice the target, 0.5 % larger steps");
    expect(llabs((long long)(sn64_audio_step(ONE, 0, 384) - q32(0.995))) < 5000, "rate control: nothing waiting, 0.5 % smaller steps");
    expect(sn64_audio_step(ONE, 5000, 384) == sn64_audio_step(ONE, 768, 384), "rate control: the trim is limited");
    expect(sn64_audio_step(ONE, 500, 384) > ONE && sn64_audio_step(ONE, 200, 384) < ONE, "rate control: direction");
    expect(sn64_audio_step(ONE, 123, 0) == ONE, "rate control: no target, the nominal step");

    // ---- 8. rate control: the loop, with the two clocks up to 300 ppm apart ----
    {
        static const double errs[] = { -300.0, -45.0, 0.0, 160.0, 300.0 };
        const int target = 384;                    // pairs waiting just before a block is added (12 ms)
        for (unsigned e = 0; e < 5; e++) {
            sn64_resample_t r;
            double game = 0.0, played = 0.0;       // pairs made by the game / played by the console in one picture
            double backlog = target;               // the output starts with `target` pairs of silence
            double lo = 1e9, lo_late = 1e9, hi_late = 0.0;
            long taken = 0;
            sn64_resample_reset(&r);
            for (int f = 0; f < 6000; f++) {
                // one console picture: the game makes 532.4588 pairs, the console plays as many, off by the error
                game += 532.4588;
                int avail = (int)floor(game) - (int)taken, used = 0;
                for (int i = 0; i < avail; i++) { in[2 * i] = 1000; in[2 * i + 1] = 1000; }
                if (backlog < lo) lo = backlog;                    // what waits just before the block is added
                if (f > 5400) { if (backlog < lo_late) lo_late = backlog; if (backlog > hi_late) hi_late = backlog; }
                uint64_t step = sn64_audio_step(ONE, (int)backlog, target);
                int o = sn64_resample(&r, in, avail, &used, out, 1024, step);
                taken += used;
                backlog += o;
                played = 532.4588 * (1.0 + errs[e] * 1e-6);
                backlog -= played;
            }
            printf("  sound loop, console %+4.0f ppm: least ever waiting %.0f pairs; settled between %.0f and %.0f (target %d)\n",
                   errs[e], lo, lo_late, hi_late, target);
            snprintf(what, sizeof(what), "console %+.0f ppm: the output never runs dry", errs[e]);
            expect(lo > 150.0, what);
            snprintf(what, sizeof(what), "console %+.0f ppm: the waiting sound settles near its target", errs[e]);
            expect(lo_late > target * 0.85 && hi_late < target * 1.15, what);
        }
    }

    printf("test_resample: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
