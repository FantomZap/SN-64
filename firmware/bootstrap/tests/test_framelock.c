// SPDX-License-Identifier: GPL-3.0-or-later
// Host unit test for the frame lock (src/sn64_framelock.c, docs/design/frame-lock.md):
//   * picture lengths from the console's video registers, against the standard values
//     libdragon writes (libdragon src/vi.h, commit e356bf3) and the rates they give;
//   * the plan for each console standard and game region, normal and compatibility mode:
//     the Super NES-shaped timing, the nominal pace, the slowdown, the sound divider;
//   * the texts of the compatibility-mode confirmation screen;
//   * the control loop against a model of two clocks: every start position, clocks off by
//     up to +-150 ppm, a jittery measurement; it must lock, hold, and never drop a picture.
// Build with -DSN64_FAULT_PACE_SIGN to make the loop push the wrong way; the test must fail.
// `--screens <file>` also writes the confirmation screen's lines for tools/mock_screens.py.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sn64_framelock.h"

static int checks, failures;

static void expect(int ok, const char *what)
{
    checks++;
    if (!ok) {
        failures++;
        printf("  FAIL %s\n", what);
    }
}

static void expect_u(const char *what, unsigned long long got, unsigned long long want)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL %-58s %llu, want %llu\n", what, got, want);
    }
}

static void expect_near(const char *what, double got, double want, double tol)
{
    checks++;
    if (fabs(got - want) > tol) {
        failures++;
        printf("  FAIL %-58s %.6f, want %.6f +-%.6f\n", what, got, want, tol);
    }
}

// libdragon's progressive presets (src/vi.h vi_ntsc_p, vi_pal_p, vi_mpal_p: V_SYNC, H_SYNC, H_SYNC_LEAP).
static const sn64_vi_timing_t std_ntsc = { 0x0000020d, 0x00000c15, 0x0c150c15 };
static const sn64_vi_timing_t std_pal  = { 0x00000271, 0x00150c69, 0x0c6f0c6e };
static const sn64_vi_timing_t std_mpal = { 0x0000020d, 0x00040c11, 0x0c190c1a };
static const sn64_vi_timing_t std_ntsc_interlaced = { 0x0000020c, 0x00000c15, 0x0c150c15 };

// The same quantities worked out independently in floating point.
static const double MASTER_NTSC = 27.0e6 * 35.0 / 44.0, MASTER_PAL = 27.0e6 * 67.0 / 85.0;
static double hz(sn64_tv_t tv, uint32_t frame_x5) { return 5.0 * sn64_vi_clock(tv) / frame_x5; }

// ---- model of the two clocks for the control loop ----
static unsigned lcg = 12345u;
static int noise(void) { lcg = lcg * 1103515245u + 12345u; return (int)((lcg >> 16) % 3u) - 1; }   // -1, 0, +1

typedef struct { int lock_frame; double worst_error; double mean_pace; unsigned relocks; long slips; } run_t;

// `ppm_off`: how much faster the console's clock really is than the plan assumes, relative
// to the board's (positive: the console is quicker, the game needs less slowing).
static run_t run_loop(const sn64_lock_plan_t *plan, double ppm_off, int start, int jitter, int frames)
{
    sn64_pace_t p;
    run_t r = { -1, 0.0, 0.0, 0, 0 };
    const int n = plan->qlines;
    const double d0 = (double)plan->console_frame_x5 / plan->snes_frame_x5 - 1.0;       // nominal: game faster by this
    const double delta = (1.0 + d0) / (1.0 + ppm_off * 1e-6) - 1.0;                     // real
    double pos = start;                     // true position at the vertical interrupt, unwrapped
    double pace_sum = 0.0;
    int pace_n = 0;
    sn64_pace_init(&p, plan);
    for (int f = 0; f < frames; f++) {
        double w = fmod(pos, n);
        if (w < 0) w += n;
        int measured = (int)floor(w) + (jitter ? noise() : 0);
        measured = ((measured % n) + n) % n;
        uint16_t pace = sn64_pace_step(&p, measured);
        if (p.locked && r.lock_frame < 0) r.lock_frame = f;
        if (r.lock_frame >= 0) {
            double e = w - plan->target;
            while (e > n / 2.0) e -= n;
            while (e <= -n / 2.0) e += n;
            if (fabs(e) > r.worst_error) r.worst_error = fabs(e);
            if (f >= frames - 600) { pace_sum += pace; pace_n++; }
        }
        // one console picture later: the game has moved (1 + delta) / (1 + pace / 2^21) pictures
        double step = n * ((1.0 + delta) / (1.0 + pace / 2097152.0) - 1.0);
        // counted half a picture away from the target, where a locked game never is
        double before = floor((pos - plan->target + n / 2.0) / n), after;
        pos += step;
        after = floor((pos - plan->target + n / 2.0) / n);
        if (r.lock_frame >= 0 && after != before) r.slips++;       // a whole picture gained or lost while locked
    }
    r.relocks = p.relocks;
    r.mean_pace = pace_n ? pace_sum / pace_n : 0.0;
    return r;
}

int main(int argc, char **argv)
{
    char buf[40];
    sn64_lock_plan_t plan;

    // ---- picture lengths from register values ----
    expect_u("NTSC standard picture, fifths of a clock", sn64_vi_frame_x5(&std_ntsc), 5u * 263u * 3094u);
    expect_u("PAL standard picture (leap 5,6,5,6,5)",    sn64_vi_frame_x5(&std_pal),  5u * 313u * 3178u + 27u);
    expect_u("MPAL standard picture (leap 8,8,9,8,8)",   sn64_vi_frame_x5(&std_mpal), 5u * 263u * 3090u + 41u);
    expect_u("interlaced timing is refused",             sn64_vi_frame_x5(&std_ntsc_interlaced), 0u);
    expect_near("NTSC standard rate, Hz", hz(SN64_TV_NTSC, sn64_vi_frame_x5(&std_ntsc)), 59.8261, 0.0001);
    expect_near("PAL standard rate, Hz",  hz(SN64_TV_PAL,  sn64_vi_frame_x5(&std_pal)),  49.9201, 0.0001);
    expect_near("MPAL standard rate, Hz", hz(SN64_TV_MPAL, sn64_vi_frame_x5(&std_mpal)), 59.8372, 0.0001);

    // ---- NTSC console, NTSC game, normal ----
    sn64_lock_plan(SN64_TV_NTSC, &std_ntsc, false, false, true, &plan);
    expect(plan.lockable && plan.set_console, "NTSC normal: lockable, console timing set");
    expect_u("NTSC normal: V_TOTAL (262 lines)", plan.game.v_total, 523u);
    expect_u("NTSC normal: H_TOTAL (3093 clocks a line)", plan.game.h_total, 3092u);
    expect_u("NTSC normal: no leap", plan.game.h_total_leap, (3092u << 16) | 3092u);
    expect_u("NTSC normal: console picture", plan.console_frame_x5, 5u * 262u * 3093u);
    expect_near("NTSC game picture in video clocks", plan.snes_frame_x5 / 5.0, 357366.0 * 48681818.0 / MASTER_NTSC, 0.11);
    expect_near("NTSC game rate at full speed, Hz", hz(SN64_TV_NTSC, plan.snes_frame_x5), MASTER_NTSC / 357366.0, 0.00002);
    expect_near("NTSC normal: console rate, Hz", hz(SN64_TV_NTSC, plan.console_frame_x5), 60.0739, 0.0001);
    expect_u("NTSC normal: nominal PACE", plan.pace_nominal, 871u);
    expect_u("NTSC normal: slower by, ppm", plan.slow_ppm, 415u);
    expect_u("NTSC normal: quarter lines", plan.qlines, 1048u);
    expect_u("NTSC normal: target position", plan.target, 32u);
    expect_u("NTSC normal: sound divider", plan.ai_divider, 1522u);
    expect_u("NTSC normal: pairs played in one picture", plan.audio_picture_pairs, 532u);
    expect_near("NTSC normal: sound step", plan.audio_step_q32 / 4294967296.0,
                (3200.0 * 357366.0 / 2147727.0) / (plan.console_frame_x5 / 5.0 / 1522.0), 1e-8);
    expect(fabs(plan.audio_step_q32 / 4294967296.0 - 1.0) < 100e-6, "NTSC normal: sound step within 100 ppm of 1");

    // ---- NTSC console, NTSC game, compatibility mode ----
    sn64_lock_plan(SN64_TV_NTSC, &std_ntsc, false, true, true, &plan);
    expect(plan.lockable && !plan.set_console, "NTSC compatibility: lockable, console timing untouched");
    expect_u("NTSC compatibility: console picture is the standard one", plan.console_frame_x5, 5u * 263u * 3094u);
    expect_u("NTSC compatibility: nominal PACE", plan.pace_nominal, 9560u);
    expect_u("NTSC compatibility: slower by, ppm", plan.slow_ppm, 4538u);
    expect_u("NTSC compatibility: sound divider", plan.ai_divider, 1528u);
    expect(fabs(plan.audio_step_q32 / 4294967296.0 - 1.0) < 400e-6, "NTSC compatibility: sound step within 400 ppm of 1");
    uint32_t compat_ntsc_ppm = plan.slow_ppm;

    // ---- PAL console, PAL game ----
    sn64_lock_plan(SN64_TV_PAL, &std_pal, true, false, true, &plan);
    expect(plan.lockable && plan.set_console, "PAL normal: lockable, console timing set");
    expect_u("PAL normal: V_TOTAL (312 lines)", plan.game.v_total, 623u);
    expect_u("PAL normal: H_TOTAL (3184 clocks a line)", plan.game.h_total, 3183u);
    expect_u("PAL normal: quarter lines", plan.qlines, 1248u);
    expect_u("PAL normal: target position", plan.target, 1080u);
    expect_near("PAL game rate at full speed, Hz", hz(SN64_TV_PAL, plan.snes_frame_x5), MASTER_PAL / 425568.0, 0.00002);
    expect_near("PAL normal: slower by, ppm", plan.slow_ppm, 1e6 * (1.0 - (425568.0 * 49656530.0 / MASTER_PAL) / (312.0 * 3184.0)), 1.0);
    expect_u("PAL normal: sound divider", plan.ai_divider, 1552u);
    expect_u("PAL normal: pairs played in one picture", plan.audio_picture_pairs, 640u);
    sn64_lock_plan(SN64_TV_PAL, &std_pal, true, true, true, &plan);
    expect(plan.lockable && !plan.set_console, "PAL compatibility: lockable, console timing untouched");
    expect_near("PAL compatibility: slower by, ppm", plan.slow_ppm, 1e6 * (1.0 - (425568.0 * 49656530.0 / MASTER_PAL) / (sn64_vi_frame_x5(&std_pal) / 5.0)), 1.0);
    uint32_t compat_pal_ppm = plan.slow_ppm;

    // ---- every lockable pair: the margin holds, and the pace really equalises the two ----
    {
        static const struct { sn64_tv_t tv; const sn64_vi_timing_t *std; bool pal; const char *name; } pairs[] = {
            { SN64_TV_NTSC, &std_ntsc, false, "NTSC console, NTSC game" },
            { SN64_TV_MPAL, &std_mpal, false, "MPAL console, NTSC game" },
            { SN64_TV_PAL,  &std_pal,  true,  "PAL console, PAL game" },
        };
        for (unsigned i = 0; i < sizeof(pairs) / sizeof(pairs[0]); i++) {
            for (int compat = 0; compat < 2; compat++) {
                char what[96];
                sn64_lock_plan(pairs[i].tv, pairs[i].std, pairs[i].pal, compat, true, &plan);
                snprintf(what, sizeof(what), "%s, %s: lockable", pairs[i].name, compat ? "compatibility" : "normal");
                expect(plan.lockable, what);
                snprintf(what, sizeof(what), "%s, %s: paced game = console within 1 ppm", pairs[i].name, compat ? "compatibility" : "normal");
                expect(fabs(plan.snes_frame_x5 * (1.0 + plan.pace_nominal / 2097152.0) / plan.console_frame_x5 - 1.0) < 1e-6, what);
                if (!compat) {
                    snprintf(what, sizeof(what), "%s: margin %u ppm kept, less than one clock a line more", pairs[i].name, SN64_LOCK_MARGIN_PPM);
                    expect(plan.slow_ppm >= SN64_LOCK_MARGIN_PPM && plan.slow_ppm < SN64_LOCK_MARGIN_PPM + 330u, what);
                    snprintf(what, sizeof(what), "%s: the game's own line count", pairs[i].name);
                    expect(plan.game.v_total == (pairs[i].pal ? 623u : 523u), what);
                }
                printf("  %-26s %-13s console %.4f Hz, game %.4f Hz, %s %% slower, PACE %u, sound /%u step %.6f\n",
                       pairs[i].name, compat ? "compatibility" : "normal", hz(pairs[i].tv, plan.console_frame_x5),
                       hz(pairs[i].tv, plan.snes_frame_x5), sn64_ppm_percent(plan.slow_ppm, buf, sizeof(buf)),
                       plan.pace_nominal, plan.ai_divider, plan.audio_step_q32 / 4294967296.0);
            }
        }
    }

    // ---- no lock: other field rate, or an FPGA build without the pace ----
    sn64_lock_plan(SN64_TV_NTSC, &std_ntsc, true, false, true, &plan);
    expect(!plan.lockable && !plan.set_console && plan.pace_nominal == 0, "PAL game on an NTSC console: no lock, console untouched");
    expect_u("PAL game on an NTSC console: sound divider", plan.ai_divider, 1521u);
    expect_u("PAL game on an NTSC console: pairs played in one picture", plan.audio_picture_pairs, 535u);
    expect_near("PAL game on an NTSC console: sound step", plan.audio_step_q32 / 4294967296.0,
                (MASTER_PAL * 3200.0 / 2128137.0) / (48681818.0 / 1521.0), 1e-8);
    sn64_lock_plan(SN64_TV_PAL, &std_pal, false, false, true, &plan);
    expect(!plan.lockable && !plan.set_console, "NTSC game on a PAL console: no lock");
    sn64_lock_plan(SN64_TV_NTSC, &std_ntsc, false, false, false, &plan);
    expect(!plan.lockable && !plan.set_console && plan.pace_nominal == 0, "no pace in the FPGA build: no lock, console untouched");
    expect_u("no pace: sound divider", plan.ai_divider, 1521u);
    sn64_lock_plan(SN64_TV_NTSC, &std_ntsc_interlaced, false, true, true, &plan);
    expect(!plan.lockable, "compatibility mode on a timing that cannot be measured: no lock");
    expect_u("timing that cannot be measured: the standard's round figure for a picture's sound", plan.audio_picture_pairs, 533u);

    // ---- texts ----
    expect(strcmp(sn64_ppm_percent(4538, buf, sizeof(buf)), "0.45") == 0, "4538 ppm reads 0.45");
    expect(strcmp(sn64_ppm_percent(415, buf, sizeof(buf)), "0.04") == 0, "415 ppm reads 0.04");
    expect(strcmp(sn64_ppm_percent(1783, buf, sizeof(buf)), "0.18") == 0, "1783 ppm reads 0.18");
    expect(strcmp(sn64_ppm_percent(30303, buf, sizeof(buf)), "3.03") == 0, "30303 ppm reads 3.03");
    expect_u("4538 ppm: seconds in 30 minutes", sn64_ppm_seconds_per_half_hour(4538), 8u);
    expect_u("415 ppm: seconds in 30 minutes", sn64_ppm_seconds_per_half_hour(415), 1u);
    {
        char lines[SN64_COMPAT_LINES][SN64_COMPAT_COLUMNS + 1];
        int pct = 0, secs = 0, fit = 1;
        sn64_compat_screen(compat_ntsc_ppm, lines);
        for (int i = 0; i < SN64_COMPAT_LINES; i++) {
            if (strlen(lines[i]) > SN64_COMPAT_COLUMNS) fit = 0;
            if (strcmp(lines[i], "  0.45 % slower") == 0) pct = 1;
            if (strcmp(lines[i], "  (about 8 seconds in 30 minutes)") == 0) secs = 1;
        }
        expect(fit, "confirmation screen: every line fits 38 columns");
        expect(pct, "confirmation screen states 0.45 % slower on an NTSC console");
        expect(secs, "confirmation screen states about 8 seconds in 30 minutes");
        expect(strcmp(lines[0], "COMPATIBILITY MODE") == 0, "confirmation screen title");
        sn64_compat_screen(415, lines);
        expect(strcmp(lines[12], "  (about 1 second in 30 minutes)") == 0, "one second is singular");
        if (argc == 3 && strcmp(argv[1], "--screens") == 0) {
            FILE *f = fopen(argv[2], "w");
            if (!f) { printf("cannot write %s\n", argv[2]); return 2; }
            const uint32_t ppm[2] = { compat_ntsc_ppm, compat_pal_ppm };
            const char *const name[2] = { "ntsc", "pal" };
            for (int k = 0; k < 2; k++) {
                sn64_compat_screen(ppm[k], lines);
                for (int i = 0; i < SN64_COMPAT_LINES; i++) fprintf(f, "%s|%s\n", name[k], lines[i]);
            }
            fclose(f);
        }
    }

    // ---- position at the vertical interrupt ----
    expect_u("position: read at the interrupt", (unsigned)sn64_lock_position(100, 0, 780000, 1048), 100u);
    expect_u("position: read a quarter picture later", (unsigned)sn64_lock_position(362, 195000, 780000, 1048), 100u);
    expect_u("position: wraps back over the picture start", (unsigned)sn64_lock_position(100, 390000, 780000, 1048), 624u);
    expect_u("position: the frame-start count is ignored", (unsigned)sn64_lock_position((uint16_t)((7u << 11) | 100u), 0, 780000, 1048), 100u);
    expect(sn64_lock_position(0x07FF, 0, 780000, 1048) == -1, "position: no picture yet");
    expect(sn64_lock_position(1100, 0, 780000, 1048) == -1, "position: outside an NTSC picture");
    expect(sn64_lock_position(1100, 0, 780000, 1248) == 1100, "position: inside a PAL picture");
    expect(sn64_lock_position(100, 100, 0, 1048) == -1, "position: no interrupt period yet");
    expect(sn64_lock_position(100, 1700000, 780000, 1048) == -1, "position: stale interrupt time");

    // ---- the control loop ----
    {
        static const struct { sn64_tv_t tv; const sn64_vi_timing_t *std; bool pal; bool compat; const char *name; } modes[] = {
            { SN64_TV_NTSC, &std_ntsc, false, false, "NTSC normal" },
            { SN64_TV_NTSC, &std_ntsc, false, true,  "NTSC compatibility" },
            { SN64_TV_PAL,  &std_pal,  true,  false, "PAL normal" },
            { SN64_TV_PAL,  &std_pal,  true,  true,  "PAL compatibility" },
            { SN64_TV_MPAL, &std_mpal, false, false, "MPAL normal" },
        };
        static const double offs[] = { -150.0, 0.0, 150.0 };
        for (unsigned m = 0; m < sizeof(modes) / sizeof(modes[0]); m++) {
            int worst_lock = 0, not_locked = 0, slipped = 0, runs = 0;
            double worst_err = 0.0, worst_pace_err = 0.0;
            unsigned relocks = 0;
            sn64_lock_plan(modes[m].tv, modes[m].std, modes[m].pal, modes[m].compat, true, &plan);
            for (unsigned o = 0; o < 3; o++) {
                const double d0 = (double)plan.console_frame_x5 / plan.snes_frame_x5 - 1.0;
                const double want_pace = ((1.0 + d0) / (1.0 + offs[o] * 1e-6) - 1.0) * 2097152.0;
                for (int jitter = 0; jitter < 2; jitter++) {
                    for (int start = 0; start < plan.qlines; start += 61) {
                        run_t r = run_loop(&plan, offs[o], start, jitter, 3000);
                        runs++;
                        if (r.lock_frame < 0) { not_locked++; continue; }
                        if (r.lock_frame > worst_lock) worst_lock = r.lock_frame;
                        if (r.worst_error > worst_err) worst_err = r.worst_error;
                        if (fabs(r.mean_pace - want_pace) > worst_pace_err) worst_pace_err = fabs(r.mean_pace - want_pace);
                        if (r.slips) slipped++;
                        relocks += r.relocks;
                    }
                }
            }
            char what[96];
            printf("  loop, %-18s %d runs: locked by picture %d at the latest; worst error once locked %.1f quarter lines; PACE within %.1f of the exact value\n",
                   modes[m].name, runs, worst_lock, worst_err, worst_pace_err);
            snprintf(what, sizeof(what), "%s: every run locks", modes[m].name);
            expect(not_locked == 0, what);
            snprintf(what, sizeof(what), "%s: locked within 3 seconds (180 pictures)", modes[m].name);
            expect(worst_lock <= 180, what);
            snprintf(what, sizeof(what), "%s: stays within 2 lines of the target once locked", modes[m].name);
            expect(worst_err <= 8.0, what);
            snprintf(what, sizeof(what), "%s: no picture gained or lost once locked", modes[m].name);
            expect(slipped == 0, what);
            snprintf(what, sizeof(what), "%s: never has to start over", modes[m].name);
            expect(relocks == 0, what);
            snprintf(what, sizeof(what), "%s: settles on the pace the clocks need", modes[m].name);
            expect(worst_pace_err <= 12.0, what);
        }
        // A console quicker than the game by more than the margin: the game cannot be sped up.
        // The loop must sit at full speed and lose a picture only as often as the clocks dictate.
        sn64_lock_plan(SN64_TV_NTSC, &std_ntsc, false, false, true, &plan);
        {
            const double too_fast = 1e6 * ((double)plan.console_frame_x5 / plan.snes_frame_x5 - 1.0) + 50.0;   // 50 ppm past the margin
            sn64_pace_t p;
            const int n = plan.qlines;
            double pos = plan.target;
            long wraps = 0;
            int max_pace_late = 0;
            sn64_pace_init(&p, &plan);
            for (int f = 0; f < 120000; f++) {
                double w = fmod(pos, n);
                if (w < 0) w += n;
                uint16_t pace = sn64_pace_step(&p, (int)floor(w));
                double d0 = (double)plan.console_frame_x5 / plan.snes_frame_x5 - 1.0;
                double delta = (1.0 + d0) / (1.0 + too_fast * 1e-6) - 1.0;
                double before = floor(pos / n);
                pos += n * ((1.0 + delta) / (1.0 + pace / 2097152.0) - 1.0);
                if (floor(pos / n) != before) wraps++;
                if (f > 60000 && pace > max_pace_late) max_pace_late = pace;
            }
            // 50 ppm at 60 pictures a second: one picture every 333 s; 120,000 pictures = 2,000 s = 6 pictures.
            printf("  loop, console 50 ppm too quick for the margin: %ld pictures lost in 2,000 s, %u fresh starts\n", wraps < 0 ? -wraps : wraps, (unsigned)p.relocks);
            expect(labs(wraps) >= 4 && labs(wraps) <= 8, "console too quick: pictures lost at the rate the clocks dictate, no faster");
            expect(p.relocks <= 8, "console too quick: no hunting");
        }
        // No lock possible: the loop stays out of it.
        sn64_lock_plan(SN64_TV_NTSC, &std_ntsc, true, false, true, &plan);
        {
            sn64_pace_t p;
            sn64_pace_init(&p, &plan);
            int nonzero = 0;
            for (int f = 0; f < 200; f++) if (sn64_pace_step(&p, (f * 37) % 1248) != 0) nonzero++;
            expect(nonzero == 0 && !p.locked, "no lock possible: PACE stays 0");
        }
    }

    printf("test_framelock: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
