// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 bootstrap: the menu program the N64/M64 boots from the SN64 cartridge
// ROM window. It forwards the N64 controllers to the SNES core through the
// SN64 mailbox and lets the user request (or drop) SNES cartridge power.
//
// Built with libdragon (Unlicense). Not yet run on hardware or an emulator;
// see docs/design/n64-bootstrap.md for what has been verified.
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include <libdragon.h>

#include "sn64_mailbox.h"
#include "sn64_mapping.h"

#ifndef SN64_BOOTSTRAP_VERSION
#define SN64_BOOTSTRAP_VERSION "0.1.0"
#endif

// Held on controller 1 for ~1 s while a cartridge runs: return to the menu.
#define MENU_HOTKEY        (N64_BTN_Z | N64_BTN_L | N64_BTN_R)
#define MENU_HOTKEY_FRAMES 60

typedef enum { MODE_MENU, MODE_RUN } run_mode_t;
typedef enum { SCREEN_MAIN, SCREEN_MAPPING, SCREEN_STATUS } screen_t;
typedef enum { ITEM_START, ITEM_MAPPING, ITEM_STATUS, ITEM_POWER_DOWN, ITEM_COUNT } item_t;

static const char *const item_names[ITEM_COUNT] = {
    "Start SNES cartridge",
    "Controller mapping",
    "Status / diagnostics",
    "Power down cartridge",
};

static const char *const seq_state_names[16] = {
    "OFF", "RESET", "5V RAMP", "IFACE RAIL", "RUNNING", "SHUTDOWN", "FAULT",
    "?7", "?8", "?9", "?10", "?11", "?12", "?13", "?14", "?15",
};

// Mailbox state as last read from the hardware.
typedef struct {
    bool     present;
    uint16_t magic, version, status, seq;
    uint16_t rb_joy1, rb_joy2, rb_stick, rb_control;
    uint16_t region_info, region_source;
} mailbox_t;

static mailbox_t  mbox;
static sn64_map_t map;
static bool       run_request;            // bootstrap-owned; default off after every reset
static run_mode_t mode = MODE_MENU;
static screen_t   screen = SCREEN_MAIN;
static int        cursor;
static int        hotkey_frames;
static const char *message = "";

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
    uint32_t jj = io_read(SN64_MBOX_BASE + SN64_REG_JOY1_JOY2);
    uint32_t sc = io_read(SN64_MBOX_BASE + SN64_REG_STICK_CONTROL);
    uint32_t cr = io_read(SN64_MBOX_BASE + SN64_REG_COMMIT_REGION);   // {COMMIT reads 0, REGION_INFO}
    uint32_t rs = io_read(SN64_MBOX_BASE + SN64_REG_REGION_SOURCE);   // {REGION_SOURCE, reserved}
    mbox.status     = (uint16_t)(ss >> 16);
    mbox.seq        = (uint16_t)ss;
    mbox.rb_joy1    = (uint16_t)(jj >> 16);
    mbox.rb_joy2    = (uint16_t)jj;
    mbox.rb_stick   = (uint16_t)(sc >> 16);
    mbox.rb_control = (uint16_t)sc;
    mbox.region_info   = (uint16_t)cr;
    mbox.region_source = (uint16_t)(rs >> 16);
}

// One complete controller update per frame, then COMMIT (SEQ increments).
// Never writes unless MAGIC was seen: unknown hardware is left alone.
static void mailbox_write_frame(uint16_t joy1, uint16_t joy2, uint16_t stick, bool run)
{
    if (!mbox.present)
        return;
    io_write(SN64_MBOX_BASE + SN64_REG_JOY1_JOY2, ((uint32_t)joy1 << 16) | joy2);
    io_write(SN64_MBOX_BASE + SN64_REG_STICK_CONTROL,
             ((uint32_t)stick << 16) | (run ? SN64_CONTROL_RUN_REQUEST : 0u));
    io_write(SN64_MBOX_BASE + SN64_REG_COMMIT, 0x00010000u);   // COMMIT at 0x18; 0x1A ignored
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
    case ITEM_STATUS:
        screen = SCREEN_STATUS;
        break;
    case ITEM_POWER_DOWN:
        run_request = false;
        message = "Cartridge power request cleared";
        break;
    default:
        break;
    }
}

static void menu_input(joypad_buttons_t pressed)
{
    if (screen != SCREEN_MAIN) {
        if (pressed.b || pressed.start) screen = SCREEN_MAIN;
        return;
    }
    if (pressed.d_up)   cursor = (cursor + ITEM_COUNT - 1) % ITEM_COUNT;
    if (pressed.d_down) cursor = (cursor + 1) % ITEM_COUNT;
    if (pressed.a)      menu_select((item_t)cursor);
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

// ---- drawing (8x8 font, 320x240 => 40 columns)

static uint32_t col_text, col_dim, col_hi, col_warn, col_bg;

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
    for (int i = 0; i < ITEM_COUNT; i++)
        line(d, 6 + i, i == cursor ? col_hi : col_text, "%c %s", i == cursor ? '>' : ' ', item_names[i]);
    line(d, 12, col_warn, "%s", message);
    line(d, 20, col_dim, "Up/Down select  A choose  B back");
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
    line(d, 18, col_dim, "RINFO %04X RSRC %04X", mbox.region_info, mbox.region_source);
    line(d, 19, col_text, "JOY1 %04X JOY2 %04X", mbox.rb_joy1, mbox.rb_joy2);
    line(d, 20, col_text, "STICK %04X CONTROL %04X", mbox.rb_stick, mbox.rb_control);
    line(d, 22, col_dim, "B: back");
}

int main(void)
{
    display_init(RESOLUTION_320x240, DEPTH_16_BPP, 2, GAMMA_NONE, FILTERS_RESAMPLE);
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

    for (;;) {
        joypad_poll();
        joypad_inputs_t  in1 = joypad_get_inputs(JOYPAD_PORT_1);
        joypad_inputs_t  in2 = joypad_get_inputs(JOYPAD_PORT_2);
        joypad_buttons_t pressed = joypad_get_buttons_pressed(JOYPAD_PORT_1);

        uint16_t n1 = n64_word(in1.btn);
        uint16_t n2 = n64_word(in2.btn);
        uint16_t s1 = sn64_map_buttons(&map, n1, in1.stick_x, in1.stick_y);
        uint16_t s2 = sn64_map_buttons(&map, n2, in2.stick_x, in2.stick_y);
        uint16_t stick = sn64_pack_stick(in1.stick_x, in1.stick_y);

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
        } else {
            menu_input(pressed);
        }

        // While the menu owns controller 1, the SNES sees a neutral pad.
        if (mode == MODE_MENU) {
            uint16_t live1 = s1;
            s1 = 0; s2 = 0; stick = 0;
            mailbox_write_frame(s1, s2, stick, run_request);
            mailbox_read();
            surface_t *d = display_get();
            graphics_fill_screen(d, col_bg);
            if (screen == SCREEN_MAPPING)     draw_mapping(d, n1, live1);
            else if (screen == SCREEN_STATUS) draw_status(d);
            else                              draw_main(d);
            display_show(d);
        } else {
            mailbox_write_frame(s1, s2, stick, run_request);
            mailbox_read();
            surface_t *d = display_get();
            graphics_fill_screen(d, col_bg);
            draw_header(d);
            line(d, 3, col_hi, "SNES cartridge running");
            line(d, 4, col_text, "P1 SNES %04X  P2 SNES %04X", s1, s2);
            line(d, 5, col_text, "SEQ %u  STATUS %04X", mbox.seq, mbox.status);
            line(d, 7, col_dim, "Hold Z+L+R for 1 s: menu");
            display_show(d);
        }
    }
}
