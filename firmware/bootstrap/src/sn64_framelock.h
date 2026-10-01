// SPDX-License-Identifier: GPL-3.0-or-later
// Frame lock: one Super NES picture for every console picture, with no picture dropped or
// shown twice (docs/design/frame-lock.md).
//
// A Super NES makes 60.10 pictures a second, a Nintendo 64 shows 59.83. Two ways to close
// the gap, both software only:
//   * normal: while a game is shown, the console's picture timing is set to the Super NES's
//     shape (262 lines; the line a touch longer), which leaves the console a few hundredths
//     of a percent slower than the game, and the SN64 slows the game's clock by that much;
//   * compatibility mode (owner, 2026-10-01): the console's timing is left exactly as the
//     console set it and the game is slowed by the whole difference, 0.45 %.
// In both the game follows the console: the program reads where the Super NES is in its
// picture at each of the console's vertical interrupts (FRAME_PHASE) and steers the game's
// clock with PACE so that position stays put. The menu and the logos never change the
// console's timing; it is set when the game display starts and restored when it ends.
//
// Pure C, no libdragon dependency, so the numbers and the control loop are unit-tested on
// the host (firmware/bootstrap/tests/test_framelock.c). Nothing here has run on a console.
#ifndef SN64_FRAMELOCK_H
#define SN64_FRAMELOCK_H

#include <stdbool.h>
#include <stdint.h>

// Console video standard; the values are libdragon's tv_type_t (get_tv_type()).
typedef enum { SN64_TV_PAL = 0, SN64_TV_NTSC = 1, SN64_TV_MPAL = 2 } sn64_tv_t;

// The three video-interface registers that set the picture rate, as written to the console
// (N64brew wiki, Video Interface): V_TOTAL = half lines per picture minus one; H_TOTAL bits
// 11:0 = video clocks per line minus one, bits 20:16 = leap pattern; H_TOTAL_LEAP = LEAP_A
// (bits 27:16) and LEAP_B (bits 11:0), the length of one line in the vertical sync, chosen
// per picture by the pattern (bit set: LEAP_B).
typedef struct {
    uint32_t v_total, h_total, h_total_leap;
} sn64_vi_timing_t;

// The console's video clock in Hz (libdragon src/audio.c, commit e356bf3: the sound output
// divides the same clock). 0 for an unknown standard.
uint32_t sn64_vi_clock(sn64_tv_t tv);

// Length of one progressive picture in fifths of a video clock (the leap pattern repeats
// every five pictures, so fifths keep it whole). 0 if the timing is not progressive.
uint32_t sn64_vi_frame_x5(const sn64_vi_timing_t *t);

// How far the Super NES-shaped console timing is kept below the game's own rate, so the
// game can always be slowed to meet it. ASSUMED until measured on consoles: the SN64's
// oscillator is +-50 ppm and a console's crystal is taken as no worse than +-100 ppm.
#define SN64_LOCK_MARGIN_PPM 200u

// Where the Super NES should be at the console's vertical interrupt: this many lines after
// its picture began. 224 lines are drawn, the last quarter of them takes 29 lines to
// fetch, and the rest is margin before the console swaps pictures. ASSUMED until timed on
// a console.
#define SN64_LOCK_TARGET_LINE 270u

typedef struct {
    bool     lockable;          // the game can be held to the console (same field rate, pace available)
    bool     set_console;       // write `game` to the console when the game display starts
    sn64_vi_timing_t game;      // Super NES-shaped timing (valid when set_console)
    uint32_t console_frame_x5;  // console picture, fifths of a video clock, with the timing in force
    uint32_t snes_frame_x5;     // Super NES picture at full speed, same unit (as the board makes its clock)
    uint16_t pace_nominal;      // PACE that makes them equal; 0 if not lockable
    uint32_t slow_ppm;          // how much slower than a Super NES the game then runs, parts per million
    uint16_t qlines;            // quarter lines in a Super NES picture: 1048 (NTSC) or 1248 (PAL)
    uint16_t target;            // wanted FRAME_PHASE position at the console's vertical interrupt
    uint16_t ai_divider;        // sound output: video clocks per sample (AI_DACRATE + 1)
    uint16_t audio_picture_pairs;   // stereo pairs the console plays in one picture at that rate
    uint64_t audio_step_q32;    // Super NES samples per output sample, 32 fraction bits (close to 1.0)
} sn64_lock_plan_t;

// Works out everything above. `console` is the timing the console is running the game
// display with (read back from the video interface after libdragon set it up); `game_pal`
// is the cartridge's region; `compat` is compatibility mode; `pace_available` is the
// FEATURES bit of this FPGA build.
void sn64_lock_plan(sn64_tv_t tv, const sn64_vi_timing_t *console, bool game_pal, bool compat,
                    bool pace_available, sn64_lock_plan_t *plan);

// "0.45" for 4538: a rate in parts per million as a percentage with two decimals. Returns buf.
char *sn64_ppm_percent(uint32_t ppm, char *buf, unsigned n);

// Seconds lost in 30 minutes of play at that rate, rounded.
unsigned sn64_ppm_seconds_per_half_hour(uint32_t ppm);

// ---- compatibility mode: the confirmation screen ----
#define SN64_COMPAT_COLUMNS 38
#define SN64_COMPAT_LINES   16
// Fills `lines` with the screen text for a game slowed by `slow_ppm`; unused lines are empty.
void sn64_compat_screen(uint32_t slow_ppm, char lines[SN64_COMPAT_LINES][SN64_COMPAT_COLUMNS + 1]);

// ---- where the Super NES is at the console's vertical interrupt ----
// `phase` is FRAME_PHASE read `dt_ticks` after the interrupt, `frame_ticks` the time between
// two interrupts in the same unit. Returns the position in quarter lines, or -1 if there is
// no picture yet or the numbers make no sense.
int sn64_lock_position(uint16_t phase, uint32_t dt_ticks, uint32_t frame_ticks, unsigned qlines);

// ---- the control loop ----
#define SN64_PACE_LIMIT        0xFFFFu   // PACE register maximum: 3.03 % slower
#define SN64_LOCK_WINDOW       8         // quarter lines: inside this for SN64_LOCK_FRAMES pictures = locked
#define SN64_LOCK_FRAMES       30
#define SN64_TRACK_WINDOW      24        // quarter lines: start fine control inside this
#define SN64_UNLOCK_WINDOW     64        // outside this for SN64_UNLOCK_FRAMES pictures: start over
#define SN64_UNLOCK_FRAMES     8

typedef struct {
    uint16_t qlines, target, pace_ff;
    int32_t  kp;                // PACE counts per quarter line of error
    int32_t  integ;             // integral term, 1/256 PACE count
    uint16_t pace;              // last output
    int16_t  error;             // last error in quarter lines (positive: the game is ahead)
    bool     tracking, locked;
    bool     coasting;          // the console is quicker than the game at full speed: nothing to steer with
    uint16_t in_window, out_window;
    uint32_t frames, relocks;
} sn64_pace_t;

void sn64_pace_init(sn64_pace_t *p, const sn64_lock_plan_t *plan);

// One console picture: takes the position from sn64_lock_position (or -1) and returns the
// PACE to write.
//
// The game can only be slowed, never sped up. If a console turns out quicker than the game
// even at full speed (its clock further off than SN64_LOCK_MARGIN_PPM allows for), the loop
// lets the game run at full speed and fall behind at the rate the two clocks dictate
// (`coasting`): a picture is then shown twice now and then, and no more often than that.
uint16_t sn64_pace_step(sn64_pace_t *p, int position);

#endif
