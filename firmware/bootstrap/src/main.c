// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 bootstrap: the menu program the N64/M64 boots from the SN64 cartridge
// ROM window. It forwards the N64 controllers to the SNES core through the
// SN64 mailbox, lets the user request (or drop) SNES cartridge power, and
// shows the SNES picture and sound on the console's own output.
//
// Built with libdragon (Unlicense). Not yet run on hardware or an emulator;
// see docs/design/n64-bootstrap.md for what has been verified.
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <libdragon.h>

#include "sn64_audioout.h"
#include "sn64_cartcheck.h"
#include "sn64_credits.h"
#include "sn64_framelock.h"
#include "sn64_mailbox.h"
#include "sn64_mapping.h"
#include "sn64_resample.h"
#include "sn64_splash.h"

#ifndef SN64_BOOTSTRAP_VERSION
#define SN64_BOOTSTRAP_VERSION "0.1.0"
#endif

// Held on controller 1 for ~1 s while a cartridge runs: return to the menu.
#define MENU_HOTKEY        (N64_BTN_Z | N64_BTN_L | N64_BTN_R)
#define MENU_HOTKEY_FRAMES 60

// The cartridge check (docs/design/reversed-cartridge-detection.md) is not a menu option (owner,
// 2026-10-01): it runs whenever a cartridge is started and a cartridge that fails is not powered.
// Its test tools are on the service screen: Status / diagnostics, then Z. There the mode can be
// changed for the session, which is what to do if the check ever refuses a good cartridge before
// its thresholds have been confirmed on real ones.
#ifndef SN64_CHECK_MODE_DEFAULT
#define SN64_CHECK_MODE_DEFAULT SN64_CHECK_MODE_ENFORCE
#endif
// "Check cartridge" gives up after this many frames (the FPGA's own limit is 4 s).
#define CHECK_WAIT_FRAMES  480

// Compatibility mode (owner, 2026-10-01; docs/design/frame-lock.md): normally the console's
// picture timing is set to a Super NES's while a game is shown. If a console or display does not
// take that, this keeps the console's own timing and slows the game to match it instead. It is a
// menu item with a confirmation screen that states the slowdown; off after every start-up.
#ifndef SN64_COMPAT_DEFAULT
#define SN64_COMPAT_DEFAULT false
#endif

typedef enum { MODE_MENU, MODE_RUN, MODE_CHECK } run_mode_t;
typedef enum { SCREEN_MAIN, SCREEN_MAPPING, SCREEN_STATUS, SCREEN_SERVICE, SCREEN_ALERT, SCREEN_COMPAT, SCREEN_CREDITS } screen_t;
typedef enum { ITEM_START, ITEM_MAPPING, ITEM_COMPAT, ITEM_STATUS, ITEM_POWER_DOWN, ITEM_CREDITS, ITEM_COUNT } item_t;

static const char *const item_names[ITEM_COUNT] = {
    "Start SNES cartridge",
    "Controller mapping",
    "Compatibility mode",
    "Status / diagnostics",
    "Power down cartridge",
    "Credits",
};

// Credits roll (owner, 2026-10-01): CREDITS.md on the screen, the SN64 crew and the cats last.
// It rises half a pixel a picture; holding A makes it eight times as quick.
#define CREDITS_TOP        22
#define CREDITS_BOTTOM     228
#define CREDITS_FAST       8

static const char *const seq_state_names[16] = {
    "OFF", "RESET", "5V RAMP", "IFACE RAIL", "RUNNING", "SHUTDOWN", "FAULT",
    "CART CHECK", "CHECK END", "CHECK HOLD", "?10", "?11", "?12", "?13", "?14", "?15",
};

// Mailbox state as last read from the hardware.
typedef struct {
    bool     present;
    uint16_t magic, version, status, seq;
    uint16_t rb_joy1, rb_joy2, rb_stick, rb_control;
    uint16_t region_info, region_source;
    uint16_t fault, cart_check;
    uint16_t features;
} mailbox_t;

static mailbox_t  mbox;
static sn64_map_t map;
static bool       run_request;            // bootstrap-owned; default off after every reset
static run_mode_t mode = MODE_MENU;
static screen_t   screen = SCREEN_MAIN;
static int        cursor;
static int        hotkey_frames;
static const char *message = "";
static unsigned   check_mode = SN64_CHECK_MODE_DEFAULT;   // enforce; the service screen can change it for the session
static int        wait_frames;                            // frames spent waiting for a check-only result
static sn64_alert_t alert = SN64_ALERT_NONE;              // what the alert screen shows ...
static uint16_t   alert_fault, alert_check;               // ... and the words it was decided from
static bool       compat_mode = SN64_COMPAT_DEFAULT;      // compatibility mode: the console keeps its own timing
static uint32_t   compat_ppm;                             // what the confirmation screen states
static uint16_t   pad1_n64, pad1_snes;                    // controller 1 as read and as mapped (mapping screen)
static int        credits_pos;                            // how far the credits have risen, in half pixels

static uint32_t col_text, col_dim, col_hi, col_warn, col_bg;

static uint16_t n64_word(joypad_buttons_t b)
{
    uint16_t w = 0;
    if (b.a)       w |= N64_BTN_A;
    if (b.b)       w |= N64_BTN_B;
    if (b.z)       w |= N64_BTN_Z;
    if (b.start)   w |= N64_BTN_START;
    if (b.d_up)    w |= N64_BTN_D_UP;
    if (b.d_down)  w |= N64_BTN_D_DOWN;
    if (b.d_left)  w |= N64_BTN_D_LEFT;
    if (b.d_right) w |= N64_BTN_D_RIGHT;
    if (b.l)       w |= N64_BTN_L;
    if (b.r)       w |= N64_BTN_R;
    if (b.c_up)    w |= N64_BTN_C_UP;
    if (b.c_down)  w |= N64_BTN_C_DOWN;
    if (b.c_left)  w |= N64_BTN_C_LEFT;
    if (b.c_right) w |= N64_BTN_C_RIGHT;
    return w;
}

// ---- mailbox access (32-bit PI accesses, register pairs; see sn64_mailbox.h)

static void mailbox_read(void)
{
    uint32_t mv = io_read(SN64_MBOX_BASE + SN64_REG_MAGIC_VERSION);
    mbox.magic   = (uint16_t)(mv >> 16);
    mbox.version = (uint16_t)mv;
    mbox.present = (mbox.magic == SN64_MAGIC);
    if (!mbox.present)
        return;
    uint32_t ss = io_read(SN64_MBOX_BASE + SN64_REG_STATUS_SEQ);
    uint32_t fc = io_read(SN64_MBOX_BASE + SN64_REG_FAULT);           // {FAULT, CART_CHECK}
    uint32_t ft = io_read(SN64_MBOX_BASE + SN64_REG_FEATURES);        // {FEATURES, reserved}
    uint32_t jj = io_read(SN64_MBOX_BASE + SN64_REG_JOY1_JOY2);
    uint32_t sc = io_read(SN64_MBOX_BASE + SN64_REG_STICK_CONTROL);
    uint32_t cr = io_read(SN64_MBOX_BASE + SN64_REG_COMMIT_REGION);   // {COMMIT reads 0, REGION_INFO}
    uint32_t rs = io_read(SN64_MBOX_BASE + SN64_REG_REGION_SOURCE);   // {REGION_SOURCE, FRAME_STATUS}
    mbox.status     = (uint16_t)(ss >> 16);
    mbox.seq        = (uint16_t)ss;
    mbox.rb_joy1    = (uint16_t)(jj >> 16);
    mbox.rb_joy2    = (uint16_t)jj;
    mbox.rb_stick   = (uint16_t)(sc >> 16);
    mbox.rb_control = (uint16_t)sc;
    mbox.region_info   = (uint16_t)cr;
    mbox.region_source = (uint16_t)(rs >> 16);
    mbox.fault         = (uint16_t)(fc >> 16);
    mbox.cart_check    = (uint16_t)fc;
    mbox.features      = (uint16_t)(ft >> 16);
}

// One complete controller update per frame, then COMMIT (SEQ increments).
// Never writes unless MAGIC was seen: unknown hardware is left alone.
static void mailbox_write_frame(uint16_t joy1, uint16_t joy2, uint16_t stick, bool run)
{
    if (!mbox.present)
        return;
    io_write(SN64_MBOX_BASE + SN64_REG_JOY1_JOY2, ((uint32_t)joy1 << 16) | joy2);
    // The check mode travels with the request; "check cartridge" asks for check only.
    unsigned cm = (mode == MODE_CHECK) ? SN64_CHECK_MODE_CHECK_ONLY : check_mode;
    io_write(SN64_MBOX_BASE + SN64_REG_STICK_CONTROL,
             ((uint32_t)stick << 16) | (run ? SN64_CONTROL_RUN_REQUEST : 0u) | (cm << SN64_CONTROL_CHECK_SHIFT));
    io_write(SN64_MBOX_BASE + SN64_REG_COMMIT, 0x00010000u);   // COMMIT at 0x18; 0x1A ignored
}

// =====================================================================
// Console video path: the SNES picture and sound through the console's own output
// (docs/design/console-video-path.md), one SNES picture per console picture
// (docs/design/frame-lock.md).
// =====================================================================
#define PI_BSD_DOM2_LAT_REG ((volatile uint32_t *)0xA4600024)
#define PI_BSD_DOM2_PWD_REG ((volatile uint32_t *)0xA4600028)
#define PI_BSD_DOM2_PGS_REG ((volatile uint32_t *)0xA460002C)
#define PI_BSD_DOM2_RLS_REG ((volatile uint32_t *)0xA4600030)
#define FRAME_CHUNK_LINES   56                 // 4 DMAs per frame, each after the SNES has finished those lines
#define FRAME_CHUNKS        (SN64_FRAME_LINES / FRAME_CHUNK_LINES)
#define GAME_TOP_LINE       8                  // the 224 SNES lines sit centred in the 240-line screen
// Video interface: the registers that set the picture rate (N64brew wiki, Video Interface).
#define VI_V_CURRENT_REG    ((volatile uint32_t *)0xA4400010)
#define VI_V_TOTAL_REG      ((volatile uint32_t *)0xA4400018)
#define VI_H_TOTAL_REG      ((volatile uint32_t *)0xA440001C)
#define VI_H_TOTAL_LEAP_REG ((volatile uint32_t *)0xA4400020)
// Audio interface (N64brew wiki, Audio Interface). Driven directly, one block per picture
// (src/sn64_audioout.c), so the sound is about a picture and 12 ms behind; libdragon's audio
// queue works in 40 ms steps.
#define AI_DRAM_ADDR_REG    ((volatile uint32_t *)0xA4500000)
#define AI_LENGTH_REG       ((volatile uint32_t *)0xA4500004)
#define AI_CONTROL_REG      ((volatile uint32_t *)0xA4500008)
#define AI_STATUS_REG       ((volatile uint32_t *)0xA450000C)
#define AI_DACRATE_REG      ((volatile uint32_t *)0xA4500010)
#define AI_BITRATE_REG      ((volatile uint32_t *)0xA4500014)
#define AI_STATUS_FULL      (1u << 31)         // a second block is waiting behind the one that plays
#define AI_STATUS_BUSY      (1u << 30)         // a block is playing

static bool     game_display;                  // display is in the 256x240 game mode
static int      game_frames_shown;
static sn64_lock_plan_t lock_plan;             // the timing numbers for the game on screen
static sn64_pace_t      pacer;                 // the loop that holds the game to the console
static uint32_t lock_slips;                    // pictures gained or lost while locked
static int      lock_prev_starts = -1;
static bool     lock_seen;                     // a game has been shown since start-up (the numbers mean something)
static bool     lock_readout;                  // service: a line of lock numbers above the game picture
static volatile uint32_t vbl_ticks, vbl_period, vbl_count;   // the console's vertical interrupt: when, how far apart, how many
static uint16_t aud_rptr;                      // next audio pair to fetch from the ring
static int16_t *aud_in;                        // the ring's new pairs (uncached: filled by DMA)
static int16_t *aud_block[SN64_AOUT_BLOCKS];   // output blocks (uncached: read by the console's sound DMA)
static sn64_aout_t aout;                       // which block is being filled, what waits where
static bool     aud_on;

static void pi_dom2_fast(void)
{
    *PI_BSD_DOM2_LAT_REG = SN64_PI_DOM2_LAT;
    *PI_BSD_DOM2_PWD_REG = SN64_PI_DOM2_PWD;
    *PI_BSD_DOM2_PGS_REG = SN64_PI_DOM2_PGS;
    *PI_BSD_DOM2_RLS_REG = SN64_PI_DOM2_RLS;
}

// The console's vertical interrupt, for the frame lock: the time of the newest one and the
// distance to the one before, in the processor's tick counter.
static void vbl_handler(void)
{
    uint32_t t = TICKS_READ();
    vbl_period = t - vbl_ticks;
    vbl_ticks = t;
    vbl_count++;
}

static void vi_timing_read(sn64_vi_timing_t *t)
{
    t->v_total = *VI_V_TOTAL_REG;
    t->h_total = *VI_H_TOTAL_REG;
    t->h_total_leap = *VI_H_TOTAL_LEAP_REG;
}

// ---- sound

static void audio_queue(int16_t *buf, int pairs)
{
    *AI_DRAM_ADDR_REG = PhysicalAddr(buf);
    MEMORY_BARRIER();
    *AI_LENGTH_REG = (uint32_t)pairs * 4u;
    MEMORY_BARRIER();
    *AI_CONTROL_REG = 1;
    MEMORY_BARRIER();
}

static void audio_start(void)
{
    if (!aud_in) {
        aud_in = malloc_uncached(SN64_AUDIO_PAIRS * 4u);
        for (int i = 0; i < SN64_AOUT_BLOCKS; i++)
            aud_block[i] = malloc_uncached(SN64_AOUT_BLOCK_PAIRS * 4u);
    }
    // Sample period in video clocks, and the DAC's bit clock as libdragon sets it.
    unsigned div = lock_plan.ai_divider ? lock_plan.ai_divider : 1521u;
    unsigned bit = div / 66u;
    if (bit > 16u) bit = 16u;
    if (bit < 1u) bit = 1u;
    *AI_DACRATE_REG = div - 1u;
    MEMORY_BARRIER();
    *AI_BITRATE_REG = bit - 1u;
    MEMORY_BARRIER();
    if (mbox.present)                           // start from what the game makes from now on
        aud_rptr = (uint16_t)((io_read(SN64_MBOX_BASE + SN64_REG_AUDIO_MODE) >> 16) & (SN64_AUDIO_PAIRS - 1u));
    // A stretch of silence first (one picture and the target), so the first real block, a
    // picture from now, is added behind something that plays.
    uint32_t t0 = TICKS_READ();
    while ((*AI_STATUS_REG & AI_STATUS_FULL) && TICKS_SINCE(t0) < (int32_t)TICKS_FROM_MS(100)) { }
    audio_queue(aud_block[0], sn64_aout_start(&aout, aud_block, lock_plan.audio_picture_pairs));
    aud_on = true;
}

// Whatever the SNES has produced since last time goes from the audio ring to the console's
// output, fitted to its rate; nothing is padded and nothing repeated.
static void game_audio(void)
{
    if (!aud_on || !mbox.present)
        return;
    // 1. the new pairs out of the ring (two runs if they wrap). The ring is 1024 pairs (32 ms).
    uint32_t aw = (io_read(SN64_MBOX_BASE + SN64_REG_AUDIO_MODE) >> 16) & (SN64_AUDIO_PAIRS - 1u);
    int avail = (int)((aw - aud_rptr) & (SN64_AUDIO_PAIRS - 1u));
    int got = 0;
    while (got < avail) {
        int run = avail - got;
        if (aud_rptr + run > (int)SN64_AUDIO_PAIRS) run = (int)SN64_AUDIO_PAIRS - aud_rptr;   // ring wrap
        dma_read_raw_async(aud_in + 2 * got, SN64_FRAME_BASE + SN64_AUDIO_OFFSET + aud_rptr * 4u, (unsigned long)run * 4u);
        dma_wait();
        got += run;
        aud_rptr = (uint16_t)((aud_rptr + run) & (SN64_AUDIO_PAIRS - 1u));
    }
    // 2. how much sound is still waiting in the console's output
    uint32_t st = *AI_STATUS_REG;
    bool busy = (st & AI_STATUS_BUSY) != 0, full = (st & AI_STATUS_FULL) != 0;
    int left = busy ? (int)((*AI_LENGTH_REG & 0x3FFFFu) / 4u) : 0;
    int waiting = sn64_aout_waiting(&aout, busy, left, full);
    // 3. the new pairs, fitted to the output's rate, and a block for the console if it can take one
    int pairs = 0;
    int16_t *block = sn64_aout_feed(&aout, aud_in, avail, sn64_audio_step(lock_plan.audio_step_q32, waiting, SN64_AOUT_TARGET_PAIRS),
                                    busy, left, full, &pairs);
    if (block)
        audio_queue(block, pairs);
}

// ---- frame lock

static void vi_wait_vblank(void)
{
    uint32_t t0 = TICKS_READ();
    while ((*VI_V_CURRENT_REG >> 1) != 1 && TICKS_SINCE(t0) < (int32_t)TICKS_FROM_MS(40)) { }
}

// The game display has just been set up with the console's own timing. Work out the plan for
// this console and this cartridge; in normal mode give the console the Super NES's picture
// shape for as long as the game is shown.
static void game_start(void)
{
    sn64_vi_timing_t own;
    vi_timing_read(&own);
    bool can_pace = mbox.present && (mbox.features & SN64_FEATURE_PACE) && (mbox.features & SN64_FEATURE_FRAME_PHASE);
    sn64_lock_plan((sn64_tv_t)get_tv_type(), &own, (mbox.status & SN64_STATUS_PAL) != 0, compat_mode, can_pace, &lock_plan);
    if (lock_plan.set_console) {
        disable_interrupts();
        vi_wait_vblank();                       // in the vertical blanking, as libdragon's own mode set
        *VI_V_TOTAL_REG = lock_plan.game.v_total;
        MEMORY_BARRIER();
        *VI_H_TOTAL_REG = lock_plan.game.h_total;
        MEMORY_BARRIER();
        *VI_H_TOTAL_LEAP_REG = lock_plan.game.h_total_leap;
        MEMORY_BARRIER();
        enable_interrupts();
    }
    sn64_pace_init(&pacer, &lock_plan);
    if (mbox.present)
        io_write(SN64_MBOX_BASE + SN64_REG_PHASE_PACE, pacer.pace);
    lock_slips = 0;
    lock_prev_starts = -1;
    lock_seen = true;
    disable_interrupts();
    vbl_count = 0;
    enable_interrupts();
    audio_start();
}

// The menu and the logos always run on the console's own timing: leaving the game display
// puts it back (libdragon writes its standard values) and lets the game run at full speed.
static void display_mode(bool game)
{
    if (game == game_display) return;
    if (!game) {
        aud_on = false;                         // what is queued plays out (under 30 ms)
        if (mbox.present)
            io_write(SN64_MBOX_BASE + SN64_REG_PHASE_PACE, 0);
    }
    display_close();
    if (game) display_init(RESOLUTION_256x240, DEPTH_16_BPP, 2, GAMMA_NONE, FILTERS_RESAMPLE);
    else      display_init(RESOLUTION_320x240, DEPTH_16_BPP, 2, GAMMA_NONE, FILTERS_RESAMPLE);
    game_display = game;
    game_frames_shown = 0;
    if (game) game_start();
}

// Once per console picture, right after its vertical interrupt: where is the SNES in its
// picture, and what pace keeps it there.
static void lock_service(void)
{
    if (!mbox.present)
        return;
    disable_interrupts();
    uint32_t w = io_read(SN64_MBOX_BASE + SN64_REG_PHASE_PACE);   // {FRAME_PHASE, PACE}
    uint32_t now = TICKS_READ();
    uint32_t at = vbl_ticks, period = vbl_period, count = vbl_count;
    enable_interrupts();
    uint16_t phase = (uint16_t)(w >> 16);
    int position = (count >= 2) ? sn64_lock_position(phase, now - at, period, lock_plan.qlines) : -1;
    uint16_t pace = sn64_pace_step(&pacer, position);
    io_write(SN64_MBOX_BASE + SN64_REG_PHASE_PACE, pace);         // 0x24 is read-only; the low half is PACE
    if (SN64_PHASE_POSITION(phase) != SN64_PHASE_NONE) {
        int starts = (int)SN64_PHASE_STARTS(phase);
        if (lock_prev_starts >= 0 && pacer.locked && ((starts - lock_prev_starts) & 31) != 1)
            lock_slips++;
        lock_prev_starts = starts;
    }
}

// One quarter of the SNES frame into the screen buffer, only after the SNES has finished
// writing those lines (FRAME_STATUS.lines_done) or has already moved on to the next frame; the
// reader therefore stays behind the writer and never tears a line. Returns false if the SNES
// made no progress for 40 ms (its clock stopped): the caller gives the picture up.
static bool game_frame_chunk(surface_t *d, unsigned chunk, uint32_t frame0)
{
    uint8_t *dst = (uint8_t *)d->buffer;
    unsigned first = chunk * FRAME_CHUNK_LINES, last = first + FRAME_CHUNK_LINES - 1;
    uint32_t t0 = TICKS_READ();
    for (;;) {
        uint32_t fs = io_read(SN64_MBOX_BASE + SN64_REG_REGION_SOURCE) & 0xFFFFu;
        uint32_t ld = SN64_FRAME_STATUS_LINES(fs);
        if (SN64_FRAME_STATUS_COUNT(fs) != frame0) break;       // writer is already on the next frame
        if (ld != 0xFFu && ld >= last) break;                    // these lines are done
        if (TICKS_SINCE(t0) > (int32_t)TICKS_FROM_MS(40)) return false;
    }
    dma_read_raw_async(dst + (GAME_TOP_LINE + first) * SN64_FRAME_LINE_BYTES,
                       SN64_FRAME_BASE + first * SN64_FRAME_LINE_BYTES,
                       FRAME_CHUNK_LINES * SN64_FRAME_LINE_BYTES);
    dma_wait();
    return true;
}

// ---- menu logic

static void menu_select(item_t item)
{
    switch (item) {
    case ITEM_START:
        if (!mbox.present) {
            message = "SN64 hardware not detected";
        } else if (mbox.status & SN64_STATUS_FAULT_LATCHED) {
            message = "Power fault latched: not starting";
        } else {
            run_request = true;
            mode = MODE_RUN;
            message = "Running. Hold Z+L+R 1 s for menu";
        }
        break;
    case ITEM_MAPPING:
        screen = SCREEN_MAPPING;
        break;
    case ITEM_COMPAT:
        if (compat_mode) {
            compat_mode = false;                // turning it off needs no confirmation
            message = "Compatibility mode off";
        } else if (mbox.present && !(mbox.features & SN64_FEATURE_PACE)) {
            message = "Not in this SN64 build";
        } else {
            // The figure for this console, with a game of the console's own region.
            sn64_vi_timing_t own;
            sn64_lock_plan_t plan;
            sn64_tv_t tv = (sn64_tv_t)get_tv_type();
            vi_timing_read(&own);               // the menu runs on the console's own timing
            sn64_lock_plan(tv, &own, tv == SN64_TV_PAL, true, true, &plan);
            if (plan.lockable) {
                compat_ppm = plan.slow_ppm;
                screen = SCREEN_COMPAT;
            } else {
                message = "Console timing not readable";   // nothing to hold the game to: no figure to state
            }
        }
        break;
    case ITEM_STATUS:
        screen = SCREEN_STATUS;
        break;
    case ITEM_POWER_DOWN:
        run_request = false;
        message = "Cartridge power request cleared";
        break;
    case ITEM_CREDITS:
        credits_pos = 0;
        screen = SCREEN_CREDITS;
        break;
    default:
        break;
    }
}

// Service screen (Status / diagnostics, then Z): the cartridge check's test tools and the
// frame lock's numbers.
static const char *service_note = "";

static void service_input(joypad_buttons_t pressed)
{
    if (pressed.b || pressed.start) {
        screen = SCREEN_STATUS;
    } else if (pressed.c_up) {
        lock_readout = !lock_readout;
    } else if (run_request) {
        if (pressed.a || pressed.l || pressed.r)
            service_note = "Power the cartridge down first";
    } else if (pressed.a) {
        if (!mbox.present) {
            service_note = "SN64 hardware not detected";
        } else {
            run_request = true;                 // with check only in CONTROL: nothing gets powered
            mode = MODE_CHECK;
            wait_frames = 0;
            service_note = "";
        }
    } else if (pressed.l || pressed.r) {        // enforce -> report only -> off -> enforce
        check_mode = (check_mode == SN64_CHECK_MODE_ENFORCE) ? SN64_CHECK_MODE_REPORT :
                     (check_mode == SN64_CHECK_MODE_REPORT)  ? SN64_CHECK_MODE_OFF :
                                                               SN64_CHECK_MODE_ENFORCE;
        service_note = (check_mode == SN64_CHECK_MODE_ENFORCE) ? "" : "Until the console is reset";
    }
}

static void menu_input(joypad_buttons_t pressed)
{
    if (screen == SCREEN_SERVICE) {
        service_input(pressed);
        return;
    }
    if (screen == SCREEN_COMPAT) {              // confirmation: A turns it on, B or Start leaves it off
        if (pressed.a) {
            compat_mode = true;
            message = "Compatibility mode on";
            screen = SCREEN_MAIN;
        } else if (pressed.b || pressed.start) {
            screen = SCREEN_MAIN;
        }
        return;
    }
    if (screen != SCREEN_MAIN) {
        if (pressed.b || pressed.start || (screen == SCREEN_ALERT && pressed.a)) screen = SCREEN_MAIN;
        else if (screen == SCREEN_STATUS && pressed.z) screen = SCREEN_SERVICE;
        return;
    }
    if (pressed.d_up)   cursor = (cursor + ITEM_COUNT - 1) % ITEM_COUNT;
    if (pressed.d_down) cursor = (cursor + 1) % ITEM_COUNT;
    if (pressed.a)      menu_select((item_t)cursor);
}

// ---- cartridge supervision: a latched power fault or a finished check ends the request and
// puts the reason on the alert screen. The fault code is only readable while the request is
// still up (dropping the request clears the latch), so it is copied first.

static bool cartridge_running(void)
{
    return mbox.present && SN64_SEQ_STATE(mbox.status) == SN64_SEQ_RUNNING &&
           (mbox.status & SN64_STATUS_SNES_CLOCK);
}

static void cartridge_stop(sn64_alert_t why)
{
    alert = why;
    alert_fault = mbox.fault;
    alert_check = mbox.cart_check;
    run_request = false;
    mode = MODE_MENU;
    screen = SCREEN_ALERT;
    message = "";
}

static void cartridge_supervise(void)
{
    if (!mbox.present || mode == MODE_MENU)
        return;
    if (mbox.status & SN64_STATUS_FAULT_LATCHED) {
        sn64_alert_t why = sn64_alert_for(mbox.fault, mbox.cart_check, mode == MODE_CHECK);
        if (why == SN64_ALERT_NONE || why == SN64_ALERT_CHECK_OK)   // latched, whatever the words say
            why = SN64_ALERT_POWER_FAULT;
        cartridge_stop(why);
    } else if (mode == MODE_CHECK) {
        if (SN64_SEQ_STATE(mbox.status) == SN64_SEQ_CHECK_HOLD)
            cartridge_stop(sn64_alert_for(0, mbox.cart_check, true));
        else if (++wait_frames > CHECK_WAIT_FRAMES)
            cartridge_stop(SN64_ALERT_CHECK_TIMEOUT);
    }
}

// Controllers, menu or hotkey, one mailbox update and read-back, supervision: once per picture.
static void inputs_and_mailbox(void)
{
    joypad_poll();
    joypad_inputs_t  in1 = joypad_get_inputs(JOYPAD_PORT_1);
    joypad_inputs_t  in2 = joypad_get_inputs(JOYPAD_PORT_2);
    joypad_buttons_t pressed = joypad_get_buttons_pressed(JOYPAD_PORT_1);

    uint16_t n1 = n64_word(in1.btn);
    uint16_t n2 = n64_word(in2.btn);
    uint16_t s1 = sn64_map_buttons(&map, n1, in1.stick_x, in1.stick_y);
    uint16_t s2 = sn64_map_buttons(&map, n2, in2.stick_x, in2.stick_y);
    uint16_t stick = sn64_pack_stick(in1.stick_x, in1.stick_y);
    pad1_n64 = n1;
    pad1_snes = s1;

    if (mode == MODE_RUN) {
        if ((n1 & MENU_HOTKEY) == MENU_HOTKEY) {
            if (++hotkey_frames >= MENU_HOTKEY_FRAMES) {
                mode = MODE_MENU;
                screen = SCREEN_MAIN;
                hotkey_frames = 0;
                message = "Menu (cartridge still running)";
            }
        } else {
            hotkey_frames = 0;
        }
        if (!run_request) mode = MODE_MENU;
    } else if (mode == MODE_MENU) {
        menu_input(pressed);
    }

    // Unless a cartridge is being played, the SNES sees a neutral pad.
    if (mode != MODE_RUN) { s1 = 0; s2 = 0; stick = 0; }
    mailbox_write_frame(s1, s2, stick, run_request);
    mailbox_read();
    cartridge_supervise();
}

// ---- region telemetry text

// "PAL via key CIC", "NTSC via ROM header", ... or "not decided yet".
static void region_text(char *buf, size_t n)
{
    if (!(mbox.region_source & SN64_RSRC_DECIDED)) {
        snprintf(buf, n, "not decided yet");
        return;
    }
    snprintf(buf, n, "%s via %s%s", (mbox.region_source & SN64_RSRC_PAL) ? "PAL" : "NTSC",
             sn64_region_source_names[mbox.region_source & SN64_RSRC_SOURCE_MASK],
             (mbox.region_source & SN64_RSRC_TIMEOUT) ? " (timeout)" : "");
}

// ROM header probe: "valid, ctry 02" or "invalid, rej 0110" (+ " aborted").
static void header_text(char *buf, size_t n)
{
    uint16_t ri = mbox.region_info;
    if (!(ri & SN64_RINFO_DONE)) {
        snprintf(buf, n, "not probed");
        return;
    }
    unsigned rej = (ri & SN64_RINFO_REJECT_MASK) >> SN64_RINFO_REJECT_SHIFT;
    snprintf(buf, n, "%s ctry %02X rej %u%u%u%u%s", (ri & SN64_RINFO_VALID) ? "ok" : "bad",
             ri & SN64_RINFO_COUNTRY_MASK, (rej >> 3) & 1, (rej >> 2) & 1, (rej >> 1) & 1, rej & 1,
             (ri & SN64_RINFO_ABORTED) ? " abort" : "");
}

// Frame lock in a few words, for the service screen and the readout.
static const char *lock_text(void)
{
    if (!lock_seen)          return "no game shown yet";
    if (!lock_plan.lockable) return "off (free running)";
    if (pacer.locked)        return "locked";
    if (pacer.coasting)      return "console too quick";
    return "bringing the game in";
}

// How much slower than a Super NES the game runs at the pace in force, parts per million.
static uint32_t pace_ppm(uint16_t pace)
{
    return (uint32_t)(((uint64_t)pace * 1000000u) / (2097152u + pace));
}

// ---- drawing (8x8 font, 320x240 => 40 columns)

static void line(surface_t *d, int row, uint32_t colour, const char *fmt, ...)
    __attribute__((format(printf, 4, 5)));
static void line(surface_t *d, int row, uint32_t colour, const char *fmt, ...)
{
    char buf[48];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    graphics_set_color(colour, 0);
    graphics_draw_text(d, 16, 12 + row * 10, buf);
}

static void draw_header(surface_t *d)
{
    line(d, 0, col_hi, "SN64 bootstrap v%s", SN64_BOOTSTRAP_VERSION);
    if (mbox.present)
        line(d, 1, col_text, "SN64 build %u.%u (0x%04X)",
             mbox.version >> 8, mbox.version & 0xFF, mbox.version);
    else
        line(d, 1, col_warn, "SN64 not detected (MAGIC %04X)", mbox.magic);
}

static void draw_main(surface_t *d)
{
    draw_header(d);
    if (mbox.present) {
        line(d, 2, col_text, "Status 0x%04X  seq %u  %s", mbox.status, mbox.seq,
             seq_state_names[(mbox.status & SN64_STATUS_SEQ_STATE_MASK) >> SN64_STATUS_SEQ_STATE_SHIFT]);
        if (mbox.status & SN64_STATUS_FAULT_LATCHED)
            line(d, 3, col_warn, "POWER FAULT LATCHED");
    }
    line(d, 4, col_text, "Cartridge: %s%s", run_request ? "run requested" : "off",
         (mbox.status & SN64_STATUS_BUS_PERMIT) ? ", permitted" : "");
    if (mbox.present) {
        char rt[40];
        region_text(rt, sizeof(rt));
        line(d, 5, col_text, "Region: %s", rt);
    }
    for (int i = 0; i < ITEM_COUNT; i++) {
        uint32_t c = i == cursor ? col_hi : col_text;
        if (i == ITEM_COMPAT)
            line(d, 6 + i, c, "%c %s: %s", i == cursor ? '>' : ' ', item_names[i], compat_mode ? "ON" : "off");
        else
            line(d, 6 + i, c, "%c %s", i == cursor ? '>' : ' ', item_names[i]);
    }
    line(d, 13, col_warn, "%s", message);
    if (check_mode != SN64_CHECK_MODE_ENFORCE)          // never silently: the service screen relaxed the check
        line(d, 15, col_warn, "Cartridge check: %s", sn64_check_mode_name(check_mode));
    if (compat_mode)                                    // never silently either
        line(d, 16, col_warn, "Compatibility mode: games run slower");
    line(d, 20, col_dim, "Up/Down select  A choose  B back");
}

// The credits roll: section titles and the credit line in the highlight colour, the projects
// dim, the people in white, the crew at the end in white too.
static void draw_credits(surface_t *d)
{
    int index[32], y[32];
    const int end = 2 * sn64_credits_end(CREDITS_TOP, CREDITS_BOTTOM);
    credits_pos += (pad1_n64 & N64_BTN_A) ? CREDITS_FAST : 1;
    if (credits_pos > end) credits_pos = end;           // it stops with the last line in the middle
    int n = sn64_credits_visible(credits_pos / 2, CREDITS_TOP, CREDITS_BOTTOM, index, y, 32);
    for (int i = 0; i < n; i++) {
        unsigned kind = sn64_credits_kind[index[i]];
        graphics_set_color(kind == SN64_CREDIT_TITLE ? col_hi : kind == SN64_CREDIT_PROJECT ? col_dim : col_text, 0);
        graphics_draw_text(d, 16, y[i], sn64_credits_lines[index[i]]);
    }
    line(d, 22, col_dim, "A: faster   B: back");
}

// Compatibility mode: the confirmation, with the slowdown stated.
static void draw_compat(surface_t *d)
{
    char text[SN64_COMPAT_LINES][SN64_COMPAT_COLUMNS + 1];
    sn64_compat_screen(compat_ppm, text);
    draw_header(d);
    for (int i = 0; i < SN64_COMPAT_LINES; i++)
        line(d, 3 + i, i == 0 ? col_hi : (i == 11 || i == 12) ? col_warn : col_text, "%s", text[i]);
    line(d, 21, col_dim, "A: turn it on        B: cancel");
}

static void draw_service(surface_t *d)
{
    char cs[40], pct[12];
    draw_header(d);
    line(d, 3, col_hi, "Service: cartridge check");
    line(d, 5, col_text, "The check runs whenever a cartridge");
    line(d, 6, col_text, "is started. These are its test tools.");
    line(d, 8, check_mode == SN64_CHECK_MODE_ENFORCE ? col_text : col_warn, "Mode: %s", sn64_check_mode_name(check_mode));
    line(d, 9, col_dim, check_mode == SN64_CHECK_MODE_ENFORCE ? "a failed check stops the start" :
                        check_mode == SN64_CHECK_MODE_REPORT  ? "measures, then starts anyway" :
                                                                "no check: nothing is caught");
    line(d, 11, (mbox.cart_check & SN64_CHECK_DONE) && !(mbox.cart_check & SN64_CHECK_PASS) ? col_warn : col_text,
         "Last check: %s", sn64_check_summary(mbox.cart_check, cs, sizeof(cs)));
    line(d, 12, col_warn, "%s", service_note);
    // The frame lock as it was when a game was last shown.
    line(d, 14, col_hi, "Frame lock: %s", lock_text());
    line(d, 15, col_text, "Slow %s %%  off %+d  lost %lu",
         sn64_ppm_percent(pace_ppm(pacer.pace), pct, sizeof(pct)), pacer.error, (unsigned long)lock_slips);
    line(d, 16, col_dim, "Console timing: %s", !lock_seen ? "-" : lock_plan.set_console ? "Super NES" : "its own");
    line(d, 17, lock_readout ? col_warn : col_dim, "Readout over the game: %s", lock_readout ? "ON" : "off");
    line(d, 19, col_dim, "A: check the cartridge now, no power");
    line(d, 20, col_dim, "L or R: change the check mode");
    line(d, 21, col_dim, "C-up: readout over the game");
    line(d, 22, col_dim, "B: back");
}

// A request is up but the cartridge is not running yet (or will not be: check only).
static void draw_wait(surface_t *d)
{
    unsigned st = SN64_SEQ_STATE(mbox.status);
    draw_header(d);
    if (mode == MODE_CHECK || st == SN64_SEQ_CHECK || st == SN64_SEQ_CHECK_END)
        line(d, 4, col_hi, "Checking the cartridge...");
    else
        line(d, 4, col_hi, "Starting the cartridge...");
    line(d, 6, col_text, "Sequencer: %s", seq_state_names[st]);
    if (mode == MODE_CHECK)
        line(d, 8, col_dim, "Cartridge power stays off.");
    else if (check_mode == SN64_CHECK_MODE_REPORT)
        line(d, 8, col_dim, "Check is set to report only.");
    if (mode == MODE_RUN)
        line(d, 20, col_dim, "Hold Z+L+R 1 s for the menu");
}

static void draw_alert(surface_t *d)
{
    const char *const *text = sn64_alert_lines(alert);
    bool good = (alert == SN64_ALERT_CHECK_OK);
    draw_header(d);
    for (int i = 0; i < SN64_ALERT_MAX_LINES && text[i]; i++)
        line(d, 3 + i, i == 0 ? (good ? col_hi : col_warn) : col_text, "%s", text[i]);
    unsigned mv = sn64_check_millivolts(alert_check);
    if (alert_check & SN64_CHECK_DONE)
        line(d, 13, col_dim, "Rail test %u.%02u V, check %s", mv / 1000u, (mv % 1000u) / 10u,
             sn64_check_mode_name((alert_check & SN64_CHECK_MODE_MASK) >> SN64_CHECK_MODE_SHIFT));
    if (SN64_FAULT_CODE(alert_fault))
        line(d, 14, col_dim, "Fault code 0x%02X", SN64_FAULT_CODE(alert_fault));
    line(d, 20, col_dim, "A or B: back to the menu");
}

static void draw_mapping(surface_t *d, uint16_t n1, uint16_t s1)
{
    char name[40];
    line(d, 0, col_hi, "Controller mapping (default)");
    line(d, 1, col_dim, "N64 button   -> SNES");
    for (int i = 0; i < SN64_MAP_ENTRIES; i++)
        line(d, 2 + i, col_text, "%-12s -> %s", map.entry[i].n64_name,
             sn64_snes_mask_name(map.entry[i].snes, name, sizeof(name)));
    line(d, 16, col_text, "Stick |x|,|y| >= %d -> D-pad", map.stick_threshold);
    line(d, 17, col_dim, "Up+Down / Left+Right cancel");
    line(d, 19, col_hi, "Live P1: N64 %04X -> SNES %04X", n1, s1);
    line(d, 20, col_text, "%s", sn64_snes_mask_name(s1, name, sizeof(name)));
    line(d, 22, col_dim, "B: back");
}

static void draw_status(surface_t *d)
{
    draw_header(d);
    if (!mbox.present) {
        line(d, 3, col_warn, "No mailbox at 0x%08lX", (unsigned long)SN64_MBOX_BASE);
        line(d, 22, col_dim, "B: back");
        return;
    }
    line(d, 2, col_text, "STATUS 0x%04X", mbox.status);
    for (unsigned i = 0; i < SN64_STATUS_BIT_COUNT; i++)
        line(d, 3 + (int)i, (mbox.status & sn64_status_bits[i].mask) ? col_hi : col_dim, "[%c] %s",
             (mbox.status & sn64_status_bits[i].mask) ? 'x' : ' ', sn64_status_bits[i].name);
    // Rows 3..14 hold the 12 STATUS bits; the rest starts below them.
    char rt[40], ht[40];
    region_text(rt, sizeof(rt));
    header_text(ht, sizeof(ht));
    line(d, 15, col_text, "Sequencer: %s  SEQ %u",
         seq_state_names[(mbox.status & SN64_STATUS_SEQ_STATE_MASK) >> SN64_STATUS_SEQ_STATE_SHIFT], mbox.seq);
    line(d, 16, col_text, "Region: %s", rt);
    line(d, 17, col_text, "Header: %s", ht);
    line(d, 18, col_dim, "RINFO %04X RSRC %04X FEAT %04X", mbox.region_info, mbox.region_source, mbox.features);
    line(d, 19, col_text, "JOY1 %04X JOY2 %04X", mbox.rb_joy1, mbox.rb_joy2);
    line(d, 20, col_text, "STICK %04X CONTROL %04X", mbox.rb_stick, mbox.rb_control);
    line(d, 21, col_text, "FAULT %04X CHECK %04X", mbox.fault, mbox.cart_check);
    line(d, 22, col_dim, "B: back   Z: service");
}

// ---- splash screens at start-up, on the N64 and the M64 alike (owner, 2026-10-01): the SN64
// logo, then the FantomZap logo, then the menu. A, B or Start skips straight to the menu.

static bool splash_one(const sn64_splash_image_t *img)
{
    for (int frame = 0; ; frame++) {
        int level = sn64_splash_level(frame);
        if (level < 0)
            return true;
        joypad_poll();
        joypad_buttons_t pressed = joypad_get_buttons_pressed(JOYPAD_PORT_1);
        if (pressed.a || pressed.b || pressed.start)
            return false;
        surface_t *d = display_get();
        sn64_splash_draw((uint16_t *)d->buffer, d->width, d->height, d->stride / 2, img, level);
        display_show(d);
    }
}

static void splash(void)
{
    if (splash_one(&sn64_splash_sn64))
        splash_one(&sn64_splash_fantomzap);
}

int main(void)
{
    display_init(RESOLUTION_320x240, DEPTH_16_BPP, 2, GAMMA_NONE, FILTERS_RESAMPLE);
    game_display = false;
    register_VI_handler(vbl_handler);
    pi_dom2_fast();
    joypad_init();
    sn64_map_default(&map);

    col_bg   = graphics_make_color(0x10, 0x18, 0x30, 0xFF);
    col_text = graphics_make_color(0xE0, 0xE0, 0xE0, 0xFF);
    col_dim  = graphics_make_color(0x80, 0x88, 0x98, 0xFF);
    col_hi   = graphics_make_color(0xFF, 0xD8, 0x40, 0xFF);
    col_warn = graphics_make_color(0xFF, 0x60, 0x50, 0xFF);

    // Default-off: explicitly clear any stale request after every boot.
    run_request = false;
    mailbox_read();
    mailbox_write_frame(0, 0, 0, false);

    splash();

    for (;;) {
        // Menu, or a request that is still being checked or started: text screens on the console's
        // own timing. The game display is entered only once the cartridge really runs.
        display_mode(mode == MODE_RUN && cartridge_running());
        surface_t *d = display_get();               // comes back just after the console's vertical interrupt

        if (!game_display) {
            inputs_and_mailbox();
            graphics_fill_screen(d, col_bg);
            if (mode != MODE_MENU)             draw_wait(d);
            else if (screen == SCREEN_MAPPING) draw_mapping(d, pad1_n64, pad1_snes);
            else if (screen == SCREEN_STATUS)  draw_status(d);
            else if (screen == SCREEN_SERVICE) draw_service(d);
            else if (screen == SCREEN_ALERT)   draw_alert(d);
            else if (screen == SCREEN_COMPAT)  draw_compat(d);
            else if (screen == SCREEN_CREDITS) draw_credits(d);
            else                               draw_main(d);
        } else {
            // Game: the SNES picture and sound go to the console's own output. The SNES is a few
            // lines into the picture it is drawing now; that picture is fetched quarter by
            // quarter as it is finished and shown at the next vertical interrupt.
            lock_service();
            if (game_frames_shown < 2) graphics_fill_screen(d, graphics_make_color(0, 0, 0, 0xFF));   // both buffers' borders once
            game_audio();
            uint32_t frame0 = SN64_FRAME_STATUS_COUNT(io_read(SN64_MBOX_BASE + SN64_REG_REGION_SOURCE) & 0xFFFFu);
            bool alive = game_frame_chunk(d, 0, frame0);
            // The controllers after the first quarter: the console has read them since its
            // interrupt, and the SNES reads the result at the end of this same picture.
            inputs_and_mailbox();
            for (unsigned c = 1; alive && c < FRAME_CHUNKS; c++)
                alive = game_frame_chunk(d, c, frame0);
            if (lock_readout) {
                char b[40];
                snprintf(b, sizeof(b), "%c%c e%+d p%u x%lu", pacer.locked ? 'L' : pacer.coasting ? 'Q' : '-',
                         lock_plan.set_console ? 'S' : 'N', pacer.error, pacer.pace, (unsigned long)lock_slips);
                graphics_set_color(col_text, graphics_make_color(0, 0, 0, 0xFF));
                graphics_draw_text(d, 0, 0, b);
            }
            game_frames_shown++;
        }
        display_show(d);
    }
}
