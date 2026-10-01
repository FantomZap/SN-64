// SPDX-License-Identifier: GPL-3.0-or-later
// Frame lock: timing numbers and the control loop. See sn64_framelock.h and
// docs/design/frame-lock.md. Pure C; unit-tested on the host.
#include "sn64_framelock.h"

#include <stdio.h>
#include <string.h>

// ---- the Super NES side, as the SN64 builds it ----
// Master clock made by the v2 board's PLLs from its 27 MHz oscillator (fpga/rtl/sn64_board_top.sv):
// NTSC 27 MHz x 35 / 44 = 21,477,272.7 Hz (exact), PAL 27 MHz x 67 / 85 = 21,282,352.9 Hz
// (+46 ppm against 21,281,370). Hz = NUM / DEN.
#define MASTER_NTSC_NUM 945000000ull
#define MASTER_NTSC_DEN 44ull
#define MASTER_PAL_NUM  1809000000ull
#define MASTER_PAL_DEN  85ull
// Master clocks in one progressive picture: NTSC 262 lines of 1364, less 4 on every other
// picture (the short line); PAL 312 lines of 1364 (docs/design/clock-plan.md).
#define FRAME_MASTER_NTSC 357366u
#define FRAME_MASTER_PAL  425568u
#define LINES_NTSC        262u
#define LINES_PAL         312u
// Sound: the core makes one sample every IN / 3200 master clocks (fpga/tools/prepare_core.py:
// a 409600 / IN clock enable, 128 of them per sample), 32,000 Hz at the nominal master.
#define APU_IN_NTSC 2147727u
#define APU_IN_PAL  2128137u

uint32_t sn64_vi_clock(sn64_tv_t tv)
{
    switch (tv) {
    case SN64_TV_NTSC: return 48681818u;
    case SN64_TV_PAL:  return 49656530u;
    case SN64_TV_MPAL: return 48628322u;
    default:           return 0;
    }
}

uint32_t sn64_vi_frame_x5(const sn64_vi_timing_t *t)
{
    uint32_t half_lines = (t->v_total & 0x3FFu) + 1u;
    if (half_lines & 1u)
        return 0;                                   // interlaced: not the game display
    uint32_t h = t->h_total & 0xFFFu;
    uint32_t pattern = (t->h_total >> 16) & 0x1Fu;
    uint32_t leap_a = (t->h_total_leap >> 16) & 0xFFFu, leap_b = t->h_total_leap & 0xFFFu;
    int32_t extra = 0;                              // over five pictures
    for (int i = 0; i < 5; i++)
        extra += (int32_t)(((pattern >> i) & 1u) ? leap_b : leap_a) - (int32_t)h;
    return (uint32_t)((int32_t)(5u * (half_lines / 2u) * (h + 1u)) + extra);
}

// a / b with 32 fraction bits, by long division (b below 2^63).
static uint64_t ratio_q32(uint64_t a, uint64_t b)
{
    uint64_t q = a / b, r = a % b;
    for (int i = 0; i < 32; i++) {
        q <<= 1;
        r <<= 1;
        if (r >= b) {
            r -= b;
            q |= 1u;
        }
    }
    return q;
}

void sn64_lock_plan(sn64_tv_t tv, const sn64_vi_timing_t *console, bool game_pal, bool compat,
                    bool pace_available, sn64_lock_plan_t *plan)
{
    const uint64_t num = game_pal ? MASTER_PAL_NUM : MASTER_NTSC_NUM;
    const uint64_t den = game_pal ? MASTER_PAL_DEN : MASTER_NTSC_DEN;
    const uint64_t frame_master = game_pal ? FRAME_MASTER_PAL : FRAME_MASTER_NTSC;
    const uint64_t lines = game_pal ? LINES_PAL : LINES_NTSC;
    const uint64_t apu_in = game_pal ? APU_IN_PAL : APU_IN_NTSC;
    const uint64_t vi = sn64_vi_clock(tv);

    memset(plan, 0, sizeof(*plan));
    plan->qlines = (uint16_t)(lines * 4u);
    plan->target = (uint16_t)((SN64_LOCK_TARGET_LINE * 4u) % (lines * 4u));
    // The game's picture in fifths of a console video clock: master clocks x (video Hz / master Hz) x 5.
    uint64_t snes_x5 = vi ? (frame_master * vi * den * 5u + num / 2u) / num : 0;
    plan->snes_frame_x5 = (uint32_t)snes_x5;

    // A lock needs the same field rate on both sides: a 50 Hz game on a 60 Hz console (or the
    // other way round) is shown with pictures repeated or dropped, as before.
    bool same_rate = ((tv == SN64_TV_PAL) == game_pal);
    plan->lockable = pace_available && same_rate && vi != 0;

    uint32_t console_x5 = sn64_vi_frame_x5(console);
    if (plan->lockable && !compat) {
        // Super NES-shaped timing: its line count, and the shortest whole line that leaves the
        // console the margin slower than the game.
        uint64_t want = snes_x5 * (1000000u + SN64_LOCK_MARGIN_PPM);
        uint64_t per_line = 5000000u * lines;
        uint32_t line_clocks = (uint32_t)((want + per_line - 1u) / per_line);
        plan->game.v_total = (uint32_t)(2u * lines - 1u);
        plan->game.h_total = line_clocks - 1u;                              // leap pattern 0
        plan->game.h_total_leap = ((line_clocks - 1u) << 16) | (line_clocks - 1u);   // no leap: both the line length
        plan->set_console = true;
        console_x5 = sn64_vi_frame_x5(&plan->game);
    }
    plan->console_frame_x5 = console_x5;

    if (plan->lockable) {
        // PACE stretches rate / 2^20 of the master periods by half a period: the game's picture
        // grows by rate / 2^21 of itself. Wanted: snes x (1 + rate / 2^21) = console.
        uint64_t pace = 0;
        if (console_x5 >= snes_x5 && snes_x5 != 0)
            pace = (((uint64_t)(console_x5 - snes_x5) << 21) + snes_x5 / 2u) / snes_x5;
        if (console_x5 < snes_x5 || pace > SN64_PACE_LIMIT) {
            plan->lockable = false;                 // the console is faster than the game, or too slow to reach
            plan->set_console = false;
            plan->console_frame_x5 = console_x5 = sn64_vi_frame_x5(console);
        } else {
            plan->pace_nominal = (uint16_t)pace;
            plan->slow_ppm = (uint32_t)(((uint64_t)(console_x5 - snes_x5) * 1000000u + console_x5 / 2u) / console_x5);
        }
    }

    // Sound. Locked, the game makes 3200 x frame_master / IN samples per console picture and the
    // console plays console_x5 / (5 x divider): pick the divider that brings them closest, and
    // let the resampler take the rest. Not locked, the same from the two clocks' own rates.
    if (vi == 0) {
        plan->ai_divider = 0;
        plan->audio_step_q32 = 1ull << 32;
    } else if (plan->lockable && console_x5 != 0) {
        uint64_t samples_x5 = 5u * 3200u * frame_master;                   // x apu_in below
        uint64_t d = ((uint64_t)console_x5 * apu_in + samples_x5 / 2u) / samples_x5;
        plan->ai_divider = (uint16_t)d;
        plan->audio_step_q32 = ratio_q32(samples_x5 * d, (uint64_t)console_x5 * apu_in);
    } else {
        // game samples per second = (num / den) x 3200 / IN; console samples per second = vi / divider
        uint64_t d = (vi * den * apu_in + (num * 3200u) / 2u) / (num * 3200u);
        plan->ai_divider = (uint16_t)d;
        plan->audio_step_q32 = ratio_q32(num * 3200u * d, den * apu_in * vi);
    }
    // What the console plays in one of its pictures; if the timing could not be read, the
    // standard's round figure.
    plan->audio_picture_pairs = (tv == SN64_TV_PAL) ? 640u : 533u;
    if (plan->ai_divider != 0 && console_x5 != 0) {
        uint64_t per = 5u * (uint64_t)plan->ai_divider;
        plan->audio_picture_pairs = (uint16_t)(((uint64_t)console_x5 + per / 2u) / per);
    }
}

char *sn64_ppm_percent(uint32_t ppm, char *buf, unsigned n)
{
    uint32_t hundredths = (ppm + 50u) / 100u;       // of a percent
    snprintf(buf, n, "%u.%02u", (unsigned)(hundredths / 100u), (unsigned)(hundredths % 100u));
    return buf;
}

unsigned sn64_ppm_seconds_per_half_hour(uint32_t ppm)
{
    return (unsigned)(((uint64_t)ppm * 1800u + 500000u) / 1000000u);
}

// Compatibility mode confirmation. %P is the percentage, %S the seconds line.
static const char *const compat_text[SN64_COMPAT_LINES] = {
    "COMPATIBILITY MODE",
    "",
    "When a game starts, the SN64 sets the",
    "console's picture timing to that of a",
    "Super NES. If the picture goes blank,",
    "rolls or flickers when a game starts,",
    "turn this on.",
    "",
    "The console then keeps its own timing",
    "and the game is slowed to match it:",
    "",
    "%P",
    "%S",
    "",
    "Sound is lower by the same amount.",
    "Stays on until the console is reset.",
};

void sn64_compat_screen(uint32_t slow_ppm, char lines[SN64_COMPAT_LINES][SN64_COMPAT_COLUMNS + 1])
{
    char pct[12];
    unsigned secs = sn64_ppm_seconds_per_half_hour(slow_ppm);
    if (secs > 99u) secs = 99u;                     // PACE cannot slow the game by more than 3 %: 55 s
    sn64_ppm_percent(slow_ppm, pct, sizeof(pct));
    for (int i = 0; i < SN64_COMPAT_LINES; i++) {
        if (strcmp(compat_text[i], "%P") == 0)
            snprintf(lines[i], SN64_COMPAT_COLUMNS + 1, "  %s %% slower", pct);
        else if (strcmp(compat_text[i], "%S") == 0)
            snprintf(lines[i], SN64_COMPAT_COLUMNS + 1, "  (about %u second%s in 30 minutes)", secs, secs == 1 ? "" : "s");
        else
            snprintf(lines[i], SN64_COMPAT_COLUMNS + 1, "%s", compat_text[i]);
    }
}

int sn64_lock_position(uint16_t phase, uint32_t dt_ticks, uint32_t frame_ticks, unsigned qlines)
{
    unsigned pos = phase & 0x07FFu;
    if (pos >= qlines || frame_ticks == 0 || qlines == 0 || dt_ticks > 2u * frame_ticks)
        return -1;                                  // no picture yet, or the interrupt time is stale
    // The game moves through `qlines` quarter lines in one console picture (exactly so once
    // locked; within 3 % while it is being brought in, which this short span does not notice).
    uint32_t moved = (uint32_t)(((uint64_t)dt_ticks * qlines + frame_ticks / 2u) / frame_ticks);
    return (int)((pos + 2u * qlines - (moved % (2u * qlines))) % qlines);
}

void sn64_pace_init(sn64_pace_t *p, const sn64_lock_plan_t *plan)
{
    memset(p, 0, sizeof(*p));
    p->qlines = plan->lockable ? plan->qlines : 0;  // 0: no control, PACE stays 0
    p->target = plan->target;
    p->pace_ff = plan->pace_nominal;
    if (p->qlines)
        p->kp = (int32_t)((1u << 21) / ((uint32_t)p->qlines * 32u));   // an error is closed in about 32 pictures
    p->pace = plan->lockable ? plan->pace_nominal : 0;
}

uint16_t sn64_pace_step(sn64_pace_t *p, int position)
{
    if (p->qlines == 0)
        return 0;
    p->frames++;
    const int n = p->qlines;
    if (position < 0 || position >= n)
        return p->pace;                             // no measurement this picture: hold
    int e = position - (int)p->target;              // positive: the game is ahead of where it should be
    while (e > n / 2) e -= n;
    while (e <= -(n / 2)) e += n;
    p->error = (int16_t)e;
    const int ae = e < 0 ? -e : e;

    if (p->coasting) {
        // Full speed and still falling behind: wait for the target to come round by itself.
        if (ae > SN64_TRACK_WINDOW) {
            p->pace = 0;
            return 0;
        }
        p->coasting = false;
        p->integ = 0;
        p->out_window = 0;
    }
    if (!p->tracking) {
        if (ae > SN64_TRACK_WINDOW) {
            // Bringing the game in. It can only be slowed: either let it catch up at full speed,
            // or slow it until the target comes round again, whichever is sooner.
            bool wait = false;
            if (e < 0) {
                uint64_t ff = p->pace_ff ? p->pace_ff : 1u;
                uint64_t wait_frames = ((uint64_t)(-e) << 21) / ((uint64_t)n * ff);
                uint64_t round_frames = ((uint64_t)(n + e) << 21) / ((uint64_t)n * (SN64_PACE_LIMIT - p->pace_ff)) + 12u;
                wait = wait_frames <= round_frames;
            }
            if (wait) {
                p->pace = 0;
            } else {
                // Close a quarter of the distance each picture, as fast as PACE allows.
                uint64_t ahead = (uint64_t)(e >= 0 ? e : e + n);
                uint64_t pace = p->pace_ff + (ahead << 21) / ((uint64_t)n * 4u);
                p->pace = (uint16_t)(pace > SN64_PACE_LIMIT ? SN64_PACE_LIMIT : pace);
            }
            return p->pace;
        }
        p->tracking = true;
        p->integ = 0;
        p->out_window = 0;
    }

    // Fine control: proportional and integral on the position error.
#ifdef SN64_FAULT_PACE_SIGN
    int32_t u = (int32_t)p->pace_ff - p->kp * e + p->integ / 256;   // fault injection: pushes the wrong way
#else
    int32_t u = (int32_t)p->pace_ff + p->kp * e + p->integ / 256;
#endif
    // The integral term learns how far the two clocks really are apart; it stops while the
    // output is at a limit and the error pushes further out.
    if (!((u > (int32_t)SN64_PACE_LIMIT && e > 0) || (u < 0 && e < 0)))
        p->integ += 2 * p->kp * e;
    p->pace = (uint16_t)(u < 0 ? 0 : u > (int32_t)SN64_PACE_LIMIT ? (int32_t)SN64_PACE_LIMIT : u);

    if (ae <= SN64_LOCK_WINDOW) {
        if (p->in_window < 0xFFFFu) p->in_window++;
        if (p->in_window >= SN64_LOCK_FRAMES) p->locked = true;
    } else {
        p->in_window = 0;
    }
    if (ae > SN64_TRACK_WINDOW) {
        if (++p->out_window >= SN64_UNLOCK_FRAMES) {
            p->locked = false;
            if (e < 0 && p->pace == 0) {
                p->coasting = true;                 // behind at full speed: the console is the quicker one
            } else if (e > SN64_UNLOCK_WINDOW) {    // far ahead: bring it in again
                p->tracking = false;
                p->relocks++;
            }
        }
    } else {
        p->out_window = 0;
    }
    return p->pace;
}
