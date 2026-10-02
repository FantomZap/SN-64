// SPDX-License-Identifier: GPL-3.0-or-later
// Host test for the controller mapping screen (src/sn64_mapscreen.c): what the buttons do
// (the cursor, the list that scrolls, the two controller lists, the choices for a button, the
// choices for the stick, the reset, leaving), and what is drawn (the right button lights in
// the right picture, the single-button pictures of the row light, nothing else changes, text
// stays on the screen).
//   test_mapscreen --screens <dir>   also writes the screens for tools/mock_screens.py:
//                                    <name>.ppm (the pixels) and <name>.txt (the text: x y colour text)
// Build with -DSN64_FAULT_MAPSCREEN_CANCEL_SETS (B takes a choice as A does): the test must fail.
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "sn64_mapscreen.h"

static int checks, failures;

static void expect(int ok, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static void expect(int ok, const char *fmt, ...)
{
    checks++;
    if (!ok) {
        va_list ap;
        failures++;
        printf("  FAIL ");
        va_start(ap, fmt);
        vprintf(fmt, ap);
        va_end(ap);
        printf("\n");
    }
}

// ---- what the buttons do

static sn64_mapscreen_t s;
static sn64_map_t map;

static bool tap(uint16_t button)        // down in one picture, up in the next
{
    bool left = sn64_mapscreen_input(&s, &map, button, 0);
    return sn64_mapscreen_input(&s, &map, 0, button) || left;
}

static void taps(uint16_t button, int times)
{
    while (times-- > 0) tap(button);
}

static void test_cursor(void)
{
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, SN64_PAD_N64, SN64_PAD_SNES);
    expect(s.row == SN64_MS_ROW_STICK && s.first == 0 && s.open == SN64_MS_CLOSED && sn64_mapscreen_entry(&s) == SN64_IN_STICK,
           "the screen opens with the cursor on the first row (the stick), the list at its top, nothing open");
    tap(N64_BTN_D_DOWN);
    expect(s.row == 1 && sn64_mapscreen_entry(&s) == SN64_IN_A, "Down: the first button's row (A)");
    taps(N64_BTN_D_DOWN, 8);
    expect(s.row == 9 && s.first == 0 && sn64_mapscreen_entry(&s) == SN64_IN_R, "eight times Down: the tenth row (R), still on the screen");
    tap(N64_BTN_D_DOWN);
    expect(s.row == 10 && s.first == 1 && sn64_mapscreen_entry(&s) == SN64_IN_START, "Down again: the list scrolls by one row");
    taps(N64_BTN_D_DOWN, 4);
    expect(s.row == 14 && s.first == 5 && sn64_mapscreen_entry(&s) == SN64_IN_D_RIGHT, "to the last row (D-Right): the last ten rows are shown");
    tap(N64_BTN_D_LEFT);
    tap(N64_BTN_D_RIGHT);
    expect(s.row == 14 && s.first == 5, "Left and Right do nothing on a row");
    tap(N64_BTN_D_DOWN);
    expect(s.row == SN64_MS_ROW_RESET && sn64_mapscreen_entry(&s) == -1 && s.first == 5, "Down from the last row: the reset field");
    tap(N64_BTN_D_DOWN);
    expect(s.row == SN64_MS_ROW_LISTS && s.col == 0 && sn64_mapscreen_entry(&s) == -1, "Down from the reset field: round to the lists");
    tap(N64_BTN_D_RIGHT);
    expect(s.row == SN64_MS_ROW_LISTS && s.col == 1, "Right: the other list");
    tap(N64_BTN_D_RIGHT);
    tap(N64_BTN_D_LEFT);
    expect(s.col == 1, "and back and forth");
    tap(N64_BTN_D_DOWN);
    expect(s.row == 0 && s.first == 0, "Down from a list: the first row, and the list is back at its top");
    tap(N64_BTN_D_UP);
    expect(s.row == SN64_MS_ROW_LISTS && s.col == 1, "Up from the first row: the list the cursor was on last");
    tap(N64_BTN_D_UP);
    expect(s.row == SN64_MS_ROW_RESET, "Up from a list: round to the reset field");
    tap(N64_BTN_D_UP);
    expect(s.row == 14 && s.first == 5, "Up from the reset field: the last row");
    taps(N64_BTN_D_UP, 9);
    expect(s.row == 5 && s.first == 5, "nine times Up: the first row shown");
    tap(N64_BTN_D_UP);
    expect(s.row == 4 && s.first == 4, "Up again: the list scrolls back by one row");
    sn64_mapscreen_open(&s);
    expect(s.row == 0 && s.first == 0 && s.col == 0, "opening the screen again puts the cursor back on the first row");
}

static void test_choices(void)
{
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, SN64_PAD_N64, SN64_PAD_SNES);
    tap(N64_BTN_D_DOWN);                                       // row A
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_TARGET && sn64_map_choice(s.pick) == 8, "A on a button's row opens its choices, on what the row gives now (A)");
    tap(N64_BTN_D_DOWN);
    expect(sn64_map_choice(s.pick) == 0 && sn64_map_target(&map, SN64_IN_A) == 8, "moving in the choices changes nothing yet");
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_CLOSED && sn64_map_target(&map, SN64_IN_A) == 0 &&
           sn64_map_buttons(&map, N64_BTN_A, 0, 0) == SNES_BTN_B, "A takes the choice: the A button now gives B");
    expect(s.row == 1, "the cursor stays on the row");
    // B gives the choice up
    tap(N64_BTN_A);
    tap(N64_BTN_D_RIGHT);
    expect(sn64_map_choice(s.pick) == 4, "Right from B: the second column, Up");
    expect(!tap(N64_BTN_B) && s.open == SN64_MS_CLOSED && sn64_map_target(&map, SN64_IN_A) == 0,
           "B closes the choices, the row stays as it was, and the screen is not left");
    // two columns, seven and six
    tap(N64_BTN_D_DOWN);                                       // row B, which gives B: the second choice
    tap(N64_BTN_A);
    expect(sn64_map_choice(s.pick) == 0 && s.pick == 1, "the choices open on B for the B row");
    tap(N64_BTN_D_RIGHT);
    tap(N64_BTN_D_UP);
    expect(s.pick == 7 && sn64_map_choice(s.pick) == 2, "Right and Up: the top of the second column, Select");
    tap(N64_BTN_D_UP);
    expect(s.pick == 12 && sn64_map_choice(s.pick) == -1, "Up again: round to its last line, nothing");
    tap(N64_BTN_D_LEFT);
    expect(s.pick == 5 && sn64_map_choice(s.pick) == 11, "Left: the same line of the first column, R");
    tap(N64_BTN_D_DOWN);
    expect(s.pick == 6 && sn64_map_choice(s.pick) == 3, "Down: Start, the seventh line");
    tap(N64_BTN_D_RIGHT);
    expect(s.pick == 12, "Right from the seventh line: the second column has six, so its last, nothing");
    tap(N64_BTN_D_DOWN);
    expect(s.pick == 7, "Down from the last line: round to the first");
    tap(N64_BTN_D_UP);
    tap(N64_BTN_A);
    expect(sn64_map_target(&map, SN64_IN_B) == -1 && sn64_map_buttons(&map, N64_BTN_B, 0, 0) == 0, "nothing can be chosen: B gives nothing");
    // every choice can be reached and taken
    {
        int ok = 1;
        for (int i = 0; i < SN64_MAP_CHOICES; i++) {
            sn64_mapscreen_open(&s);
            taps(N64_BTN_D_DOWN, 8);                           // row L
            tap(N64_BTN_A);
            if ((s.pick / 7) != (i / 7)) tap(N64_BTN_D_RIGHT);
            for (int guard = 0; guard < 7 && s.pick != i; guard++) tap(N64_BTN_D_DOWN);
            tap(N64_BTN_A);
            if (sn64_mapscreen_entry(&s) != SN64_IN_L || sn64_map_target(&map, SN64_IN_L) != sn64_map_choice(i)) ok = 0;
        }
        expect(ok, "each of the 13 choices can be reached with the D-pad and taken");
    }
}

// The stick's row: what the stick does and how far it has to be pushed, as one list of choices.
static void test_stick(void)
{
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, SN64_PAD_N64, SN64_PAD_SNES);
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_STICK && sn64_map_stick_choice(s.pick) == 50, "A on the stick's row opens its choices, on what is set now (the D-pad from 50 %%)");
    tap(N64_BTN_D_DOWN);
    expect(sn64_map_stick_choice(s.pick) == 60 && map.stick_percent == 50, "moving in the choices changes nothing yet");
    tap(N64_BTN_D_LEFT);
    tap(N64_BTN_D_RIGHT);
    expect(sn64_map_stick_choice(s.pick) == 60, "Left and Right do nothing here: it is one column");
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_CLOSED && map.stick_percent == 60 && s.row == SN64_MS_ROW_STICK &&
           sn64_map_stick(&map, 47, 0) == 0 && sn64_map_stick(&map, 48, 0) == SNES_BTN_RIGHT,
           "A takes the choice: the stick now presses the D-pad from 60 %% of its travel");
    tap(N64_BTN_A);
    taps(N64_BTN_D_UP, 5);
    expect(s.pick == SN64_STICK_CHOICES - 1 && sn64_map_stick_choice(s.pick) == 0, "Up past the first line: round to the last, nothing");
    expect(!tap(N64_BTN_B) && s.open == SN64_MS_CLOSED && map.stick_percent == 60, "B closes the choices, the stick stays as it was, and the screen is not left");
    tap(N64_BTN_A);
    taps(N64_BTN_D_UP, 5);
    tap(N64_BTN_A);
    expect(map.stick_percent == 0 && sn64_map_buttons(&map, 0, 127, 127) == 0, "nothing can be chosen: the stick presses nothing");
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_STICK && s.pick == SN64_STICK_CHOICES - 1, "the choices then open on nothing");
    tap(N64_BTN_D_DOWN);
    tap(N64_BTN_A);
    expect(map.stick_percent == 20, "Down from the last line: round to the first, 20 %%");
    {
        int ok = 1;
        for (int i = 0; i < SN64_STICK_CHOICES; i++) {
            sn64_mapscreen_open(&s);
            tap(N64_BTN_A);
            for (int guard = 0; guard < SN64_STICK_CHOICES && s.pick != i; guard++) tap(N64_BTN_D_DOWN);
            tap(N64_BTN_A);
            if (map.stick_percent != sn64_map_stick_choice(i) || s.open != SN64_MS_CLOSED) ok = 0;
        }
        expect(ok, "each of the eight choices can be reached and taken");
    }
    // the reset field brings the stick back as well
    tap(N64_BTN_D_UP);
    tap(N64_BTN_D_UP);
    tap(N64_BTN_A);
    expect(s.row == SN64_MS_ROW_RESET && map.stick_percent == SN64_STICK_PERCENT_DEFAULT && sn64_map_is_default(&map),
           "the reset field puts the stick back to the D-pad from 50 %%");
}

static void test_lists(void)
{
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, SN64_PAD_M64_PRO, SN64_PAD_SFC);
    expect(s.input_pad == SN64_PAD_M64_PRO && s.snes_pad == SN64_PAD_SFC, "the lists start on what they are told");
    tap(N64_BTN_D_UP);
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_LIST_INPUT && s.pick == SN64_PAD_M64_PRO, "A on the left list opens it on the controller chosen now");
    taps(N64_BTN_D_DOWN, 3);
    expect(s.pick == SN64_PAD_BRAWLER && s.input_pad == SN64_PAD_M64_PRO, "moving in the list changes nothing yet");
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_CLOSED && s.input_pad == SN64_PAD_BRAWLER, "A takes the controller");
    tap(N64_BTN_A);
    taps(N64_BTN_D_DOWN, 2);
    expect(s.pick == SN64_PAD_N64, "the list goes round from the last to the first");
    tap(N64_BTN_D_UP);
    expect(s.pick == SN64_PAD_8BITDO, "and back");
    expect(!tap(N64_BTN_B) && s.open == SN64_MS_CLOSED && s.input_pad == SN64_PAD_BRAWLER, "B closes the list and keeps the controller");
    tap(N64_BTN_D_RIGHT);
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_LIST_SNES && s.pick == SN64_PAD_SFC, "the right list opens on its own setting");
    tap(N64_BTN_D_DOWN);
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_CLOSED && s.snes_pad == SN64_PAD_SNES && s.input_pad == SN64_PAD_BRAWLER, "and sets only its own");
    expect(sn64_map_is_default(&map), "the lists do not touch the mapping");
    sn64_mapscreen_open(&s);
    expect(s.input_pad == SN64_PAD_BRAWLER && s.snes_pad == SN64_PAD_SNES, "opening the screen again keeps what the lists are set to");
    sn64_mapscreen_init(&s, 99, 99);
    expect(s.input_pad == 0 && s.snes_pad == 0, "a setting outside a list is taken as its first entry");
}

static void test_reset_and_leave(void)
{
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, SN64_PAD_N64, SN64_PAD_SNES);
    sn64_map_set_target(&map, SN64_IN_Z, 9);
    sn64_map_set_target(&map, SN64_IN_START, -1);
    tap(N64_BTN_D_UP);
    tap(N64_BTN_D_UP);
    expect(s.row == SN64_MS_ROW_RESET && !s.restored, "to the reset field");
    tap(N64_BTN_A);
    expect(sn64_map_is_default(&map) && s.restored && s.open == SN64_MS_CLOSED, "A on the reset field puts the defaults back and says so");
    tap(N64_BTN_Z);
    expect(!s.restored, "the note goes with the next button");
    // leaving: B down and up with nothing open
    expect(!sn64_mapscreen_input(&s, &map, N64_BTN_B, 0), "B going down does not leave yet (it can be seen to light)");
    expect(!sn64_mapscreen_input(&s, &map, 0, 0), "nor while it is held");
    expect(sn64_mapscreen_input(&s, &map, 0, N64_BTN_B), "letting B go leaves the screen");
    expect(!sn64_mapscreen_input(&s, &map, 0, N64_BTN_B), "a B that was down before the screen opened does not leave it");
    // B held, then A opens something: letting B go must not leave, nor must the B that closes it
    sn64_mapscreen_open(&s);
    sn64_mapscreen_input(&s, &map, N64_BTN_B, 0);
    sn64_mapscreen_input(&s, &map, N64_BTN_A, 0);
    expect(s.open == SN64_MS_STICK && !sn64_mapscreen_input(&s, &map, 0, N64_BTN_B | N64_BTN_A), "B held while A opens the choices: letting go does not leave");
    expect(!tap(N64_BTN_B) && s.open == SN64_MS_CLOSED, "the B that closes the choices does not leave either");
    expect(tap(N64_BTN_B), "the next B does");
    // the buttons that do nothing here, so they can be tried
    {
        static const uint16_t idle[] = { N64_BTN_Z, N64_BTN_L, N64_BTN_R, N64_BTN_START, N64_BTN_C_UP, N64_BTN_C_DOWN,
                                         N64_BTN_C_LEFT, N64_BTN_C_RIGHT, N64_BTN_C_ALL, 0x00C0u };
        int ok = 1;
        for (int open = 0; open < 4; open++) {
            sn64_map_default(&map);
            sn64_mapscreen_init(&s, SN64_PAD_CAPTAIN, SN64_PAD_SFC);
            if (open == 1) tap(N64_BTN_A);                                        // the stick's choices
            if (open == 2) { tap(N64_BTN_D_DOWN); tap(N64_BTN_A); }               // a button's choices
            if (open == 3) { tap(N64_BTN_D_UP); tap(N64_BTN_A); }                 // a list
            sn64_mapscreen_t before = s;
            for (unsigned i = 0; i < sizeof idle / sizeof idle[0]; i++)
                if (tap(idle[i]) || memcmp(&before, &s, sizeof s) != 0 || !sn64_map_is_default(&map)) ok = 0;
        }
        expect(ok, "Z, L, R, Start and the C buttons do nothing on this screen, whatever is open");
    }
}

// ---- what is drawn

#define W      320
#define H      240
#define GUARD  8
#define BW     (W + 2 * GUARD)
#define BH     (H + 2 * GUARD)
#define SENTINEL 0xF81Eu
#define BG     sn64_rgb(0x10, 0x18, 0x30)
#define COL_DIM sn64_rgb(0x80, 0x88, 0x98)
#define COL_HI  sn64_rgb(0xFF, 0xD8, 0x40)
// where the screen puts things (src/sn64_mapscreen.c)
#define X_LEFT   16
#define X_RIGHT  164
#define Y_PAD    23
#define Y_ROWS   96
#define ROW_H    12
#define Y_NOTE   202

typedef struct { int x, y; uint16_t colour; char s[48]; } text_t;
typedef struct {
    uint16_t buf[BW * BH];
    text_t   text[200];
    int      texts, bad_text;
} shot_t;

static void record(void *ctx, int x, int y, uint16_t colour, const char *str)
{
    shot_t *f = ctx;
    int len = (int)strlen(str);
    if (x < 16 || x + 8 * len > 304 || y < 8 || y + 8 > 240 || len > 47 || f->texts >= 200) {
        f->bad_text++;
        return;
    }
    f->text[f->texts].x = x;
    f->text[f->texts].y = y;
    f->text[f->texts].colour = colour;
    strcpy(f->text[f->texts].s, str);
    f->texts++;
}

static uint16_t *pixel(shot_t *f, int x, int y)
{
    return &f->buf[(y + GUARD) * BW + x + GUARD];
}

static void blank_shot(shot_t *f)
{
    for (int i = 0; i < BW * BH; i++) f->buf[i] = SENTINEL;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) *pixel(f, x, y) = BG;
    f->texts = f->bad_text = 0;
}

static void shoot(shot_t *f, const sn64_mapscreen_t *st, const sn64_map_t *m, uint16_t n64, int sx, int sy, unsigned frame)
{
    blank_shot(f);
    sn64_canvas_t c = { pixel(f, 0, 0), W, H, BW };
    sn64_mapscreen_draw(st, m, &c, record, f, n64, (int8_t)sx, (int8_t)sy, frame);
}

static int tidy(const shot_t *f)        // nothing outside the screen, no text off it
{
    for (int y = 0; y < BH; y++)
        for (int x = 0; x < BW; x++)
            if ((x < GUARD || x >= GUARD + W || y < GUARD || y >= GUARD + H) && f->buf[y * BW + x] != SENTINEL)
                return 0;
    return f->bad_text == 0;
}

static const text_t *find_text(const shot_t *f, const char *str)
{
    for (int i = 0; i < f->texts; i++)
        if (strcmp(f->text[i].s, str) == 0) return &f->text[i];
    return NULL;
}

static int has_text(const shot_t *f, const char *str)
{
    int n = 0;
    for (int i = 0; i < f->texts; i++)
        if (strcmp(f->text[i].s, str) == 0) n++;
    return n;
}

static const text_t *text_at(const shot_t *f, int x, int y)
{
    for (int i = 0; i < f->texts; i++)
        if (f->text[i].x == x && f->text[i].y == y) return &f->text[i];
    return NULL;
}

static int text_is(const shot_t *f, int x, int y, const char *str)
{
    const text_t *t = text_at(f, x, y);
    return t && strcmp(t->s, str) == 0;
}

// Pixels that differ between two shots inside a rectangle of the screen.
static int diff_in(shot_t *a, shot_t *b, int x0, int y0, int x1, int y1)
{
    int n = 0;
    for (int y = y0; y <= y1; y++)
        for (int x = x0; x <= x1; x++)
            if (*pixel(a, x, y) != *pixel(b, x, y)) n++;
    return n;
}

static int diff_all(shot_t *a, shot_t *b)
{
    return diff_in(a, b, 0, 0, W - 1, H - 1);
}

static int diff_box(shot_t *a, shot_t *b, int ox, int oy, const sn64_box_t *box)
{
    return diff_in(a, b, ox + box->x0, oy + box->y0, ox + box->x1, oy + box->y1);
}

static int diff_snes_picture(shot_t *a, shot_t *b)
{
    return diff_in(a, b, X_RIGHT, Y_PAD, X_RIGHT + SN64_PAD_W - 1, Y_PAD + SN64_PAD_SNES_H - 1);
}

// The single-button pictures of a row of the list, when `first` is the first row shown: the
// player's button and what it gives. Row 0 is the stick's, row 1 + e is entry e's.
static int list_row_y(int row, int first) { return Y_ROWS + (row - first) * ROW_H; }
static int row_y(int entry, int first) { return list_row_y(entry == SN64_IN_STICK ? 0 : entry + 1, first); }
static int diff_icon(shot_t *a, shot_t *b, int entry, int first, bool snes)
{
    int x = X_RIGHT + (snes ? 78 : 1), y = row_y(entry, first);
    return diff_in(a, b, x, y, x + SN64_ICON - 1, y + SN64_ICON - 1);
}

// The D-pad of the Super NES controller: how many of its four arms differ between two shots.
static int diff_arms(shot_t *a, shot_t *b, int *pixels)
{
    int arms = 0;
    *pixels = 0;
    for (int bit = 4; bit < 8; bit++) {
        sn64_box_t box;
        sn64_pad_snes_box(bit, &box);
        int n = diff_box(a, b, X_RIGHT, Y_PAD, &box);
        if (n) arms++;
        *pixels += n;
    }
    return arms;
}

// How many of the note line's five places for a small picture hold one (compared with a
// screen that has none).
static int note_icons(shot_t *a, shot_t *none)
{
    int n = 0;
    for (int i = 0; i < 5; i++) {
        int x = X_LEFT + 9 * 8 + 3 + i * (SN64_ICON + 1);
        if (diff_in(a, none, x, Y_NOTE - 2, x + SN64_ICON - 1, Y_NOTE - 2 + SN64_ICON - 1) >= 3) n++;
    }
    return n;
}

static void test_lighting(unsigned input_pad, unsigned snes_pad)
{
    static shot_t rest[2], lit;
    const uint8_t first_of[2] = { 0, SN64_MS_LIST_ROWS - SN64_MS_VISIBLE };     // the list at its top, and at its end
    sn64_box_t in, in2, out;
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, input_pad, snes_pad);
    s.row = SN64_MS_ROW_RESET;                 // the cursor on the reset field: nothing is marked
    for (int k = 0; k < 2; k++) {
        s.first = first_of[k];
        shoot(&rest[k], &s, &map, 0, 0, 0, 0);
    }
    expect(tidy(&rest[0]) && tidy(&rest[1]), "%s / %s: nothing is drawn or written off the screen",
           sn64_input_pad_name(input_pad), sn64_snes_pad_name(snes_pad));
    int ok = 1;
    for (int e = 0; e < SN64_MAP_ENTRIES; e++) {
        int t = sn64_map_target(&map, e), k = e + 1 < SN64_MS_VISIBLE ? 0 : 1;
        bool two = sn64_pad_input_box(input_pad, e, true, &in2);
        sn64_pad_input_box(input_pad, e, false, &in);
        sn64_pad_snes_box(t, &out);
        s.first = first_of[k];
        shoot(&lit, &s, &map, sn64_map_n64_bit(e), 0, 0, 0);
        int a = diff_box(&rest[k], &lit, X_LEFT, Y_PAD, &in), a2 = two ? diff_box(&rest[k], &lit, X_LEFT, Y_PAD, &in2) : 0;
        int b = diff_box(&rest[k], &lit, X_RIGHT, Y_PAD, &out);
        int c = diff_icon(&rest[k], &lit, e, s.first, false), d = diff_icon(&rest[k], &lit, e, s.first, true);
        int all = diff_all(&rest[k], &lit);
        if (a < 12 || (two && a2 < 12) || b < 12 || c < 6 || d < 6 || all != a + a2 + b + c + d || !tidy(&lit)) {
            ok = 0;
            printf("    %s: %d + %d in its picture, %d in the other, %d + %d in its row, %d in all\n",
                   sn64_map_n64_name(e), a, a2, b, c, d, all);
        }
    }
    expect(ok, "%s / %s: each button lights itself, the button it gives and the two small pictures of its row, and nothing else",
           sn64_input_pad_name(input_pad), sn64_snes_pad_name(snes_pad));
    // the stick, pushed to the right: itself, Right on the other controller, the two small pictures of its row
    {
        int pixels;
        s.first = 0;
        sn64_pad_input_box(input_pad, SN64_IN_STICK, false, &in);
        sn64_pad_snes_box(7, &out);
        shoot(&lit, &s, &map, 0, 80, 0, 0);
        int a = diff_box(&rest[0], &lit, X_LEFT, Y_PAD, &in), b = diff_box(&rest[0], &lit, X_RIGHT, Y_PAD, &out);
        int c = diff_icon(&rest[0], &lit, SN64_IN_STICK, 0, false), d = diff_icon(&rest[0], &lit, SN64_IN_STICK, 0, true);
        expect(a >= 30 && b >= 12 && c >= 4 && d >= 6 && diff_all(&rest[0], &lit) == a + b + c + d && diff_arms(&rest[0], &lit, &pixels) == 1,
               "%s / %s: the stick pushed right lights itself, Right, and the two small pictures of its row, and nothing else (%d, %d, %d, %d)",
               sn64_input_pad_name(input_pad), sn64_snes_pad_name(snes_pad), a, b, c, d);
    }
}

static void test_drawing(void)
{
    static shot_t rest0, rest, f, g, blank;
    sn64_box_t box;
    int pixels;
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, SN64_PAD_N64, SN64_PAD_SNES);
    shoot(&rest0, &s, &map, 0, 0, 0, 0);
    blank_shot(&blank);

    // the screen at rest: the two lists name the controllers, both are drawn, the stick's row and nine buttons
    {
        int names = 0, gives = 0;
        for (int e = 0; e < SN64_MS_VISIBLE - 1; e++) {
            if (text_is(&rest0, X_RIGHT + 14, row_y(e, 0) + 2, sn64_map_n64_name(e))) names++;
            if (text_is(&rest0, X_RIGHT + 91, row_y(e, 0) + 2, sn64_snes_button_name(sn64_map_target(&map, e)))) gives++;
        }
        expect(text_is(&rest0, X_RIGHT + 14, Y_ROWS + 2, "Stick") && text_is(&rest0, X_RIGHT + 91, Y_ROWS + 2, "50 %"),
               "the first row is the stick's: it presses the D-pad from 50 %%");
        expect(names == 9 && gives == 9, "nine button rows under it, each with the button's name and the name of what it gives (%d, %d)", names, gives);
        expect(has_text(&rest0, "N64 controller") && has_text(&rest0, "Super NES") && has_text(&rest0, "Restore defaults") &&
               has_text(&rest0, "A change   B back") && has_text(&rest0, "In a game, all") && has_text(&rest0, "four C buttons") &&
               has_text(&rest0, "bring up the menu") && has_text(&rest0, "Stick now: 0 %"),
               "the two lists name the two controllers; the reset field, the help, the shortcut, and how far the stick is pushed");
        expect(tidy(&rest0) && rest0.texts == 10 * 2 + 8, "all of it on the screen (%d pieces of text)", rest0.texts);
        expect(diff_in(&rest0, &blank, X_LEFT, Y_PAD, X_LEFT + SN64_PAD_W - 1, Y_PAD + SN64_PAD_INPUT_H - 1) > 6000 &&
               diff_snes_picture(&rest0, &blank) > 4000 &&
               diff_in(&rest0, &blank, 0, Y_PAD, X_LEFT - 1, H - 1) == 0 &&
               diff_in(&rest0, &blank, X_LEFT + SN64_PAD_W, 0, X_RIGHT - 1, H - 1) == 0 &&
               diff_in(&rest0, &blank, X_RIGHT + SN64_PAD_W, 0, W - 1, H - 1) == 0,
               "both controllers are drawn, each in its own half, with the margins left free");
    }
    // the list scrolls: a mark below while there are more rows below, one above when there are more above
    {
        int mx = X_RIGHT + SN64_PAD_W / 2 - 2, up = Y_ROWS - 4, down = Y_ROWS + SN64_MS_VISIBLE * ROW_H + 1;
        expect(diff_in(&rest0, &blank, mx, down, mx + 4, down + 2) == 9 && diff_in(&rest0, &blank, mx, up, mx + 4, up + 2) == 0,
               "at the top of the list: a mark below it, none above");
        s.first = 2;
        s.row = 5;
        shoot(&f, &s, &map, 0, 0, 0, 0);
        expect(diff_in(&f, &blank, mx, down, mx + 4, down + 2) == 9 && diff_in(&f, &blank, mx, up, mx + 4, up + 2) == 9,
               "in the middle: a mark above and one below");
        s.first = 5;
        s.row = 14;
        shoot(&f, &s, &map, 0, 0, 0, 0);
        expect(diff_in(&f, &blank, mx, down, mx + 4, down + 2) == 0 && diff_in(&f, &blank, mx, up, mx + 4, up + 2) == 9 &&
               text_is(&f, X_RIGHT + 14, Y_ROWS + 2, "C-Left") && has_text(&f, "D-Right") && !has_text(&f, "C-Up") &&
               !has_text(&f, "Stick") && tidy(&f),
               "at the end: a mark above only, and the rows from C-Left to D-Right");
        sn64_mapscreen_open(&s);
    }
    // the cursor's mark blinks in both pictures and nowhere else: on the stick's row, the stick and the whole D-pad
    {
        sn64_box_t a, b;
        sn64_pad_input_box(SN64_PAD_N64, SN64_IN_STICK, false, &a);
        shoot(&f, &s, &map, 0, 0, 0, 16);
        int x = diff_box(&rest0, &f, X_LEFT, Y_PAD, &a), arms = diff_arms(&rest0, &f, &pixels);
        expect(x >= 30 && arms == 4 && diff_all(&rest0, &f) == x + pixels, "on the stick's row the stick and the whole D-pad are marked, on the blink");
        shoot(&g, &s, &map, 0, 0, 0, 32);
        expect(diff_all(&rest0, &g) == 0, "and off again");
        // on a button's row: the button, and the button it gives
        tap(N64_BTN_D_DOWN);
        shoot(&rest, &s, &map, 0, 0, 0, 0);
        sn64_pad_input_box(SN64_PAD_N64, SN64_IN_A, false, &a);
        sn64_pad_snes_box(8, &b);
        shoot(&f, &s, &map, 0, 0, 0, 16);
        x = diff_box(&rest, &f, X_LEFT, Y_PAD, &a);
        int y = diff_box(&rest, &f, X_RIGHT, Y_PAD, &b);
        expect(x >= 12 && y >= 12 && diff_all(&rest, &f) == x + y, "on a button's row the button and the button it gives are marked");
        expect(!has_text(&rest, "Stick now: 0 %"), "and the line about the stick's travel is gone");
    }
    // opposite directions cancel: the game is given neither, and the screen shows that
    s.first = 5;
    shoot(&g, &s, &map, 0, 0, 0, 0);
    shoot(&f, &s, &map, N64_BTN_D_UP | N64_BTN_D_DOWN, 0, 0, 0);
    expect(diff_snes_picture(&g, &f) == 0 &&
           diff_icon(&g, &f, SN64_IN_D_UP, 5, false) && diff_icon(&g, &f, SN64_IN_D_DOWN, 5, false) &&
           !diff_icon(&g, &f, SN64_IN_D_UP, 5, true) && !diff_icon(&g, &f, SN64_IN_D_DOWN, 5, true),
           "Up and Down together: both light on the left, nothing on the right");
    s.first = 0;
    // the menu shortcut: all four C are held, the game is given none of them
    shoot(&f, &s, &map, N64_BTN_C_ALL, 0, 0, 0);
    expect(diff_snes_picture(&rest, &f) == 0 &&
           diff_icon(&rest, &f, SN64_IN_C_UP, 0, false) && !diff_icon(&rest, &f, SN64_IN_C_UP, 0, true) &&
           find_text(&f, "four C buttons")->colour == COL_HI && find_text(&rest, "four C buttons")->colour == COL_DIM,
           "all four C: they light on the left, nothing on the right, and the line about the shortcut lights up");
    shoot(&f, &s, &map, N64_BTN_C_ALL & ~N64_BTN_C_UP, 0, 0, 0);
    expect(diff_snes_picture(&rest, &f) > 0 && find_text(&f, "four C buttons")->colour == COL_DIM, "three C buttons are ordinary buttons");

    // the stick: past the set part of its travel it presses the D-pad, two directions towards a corner
    shoot(&f, &s, &map, 0, 80, 0, 0);
    expect(diff_arms(&rest, &f, &pixels) == 1, "the stick to the right lights Right on the Super NES controller");
    shoot(&f, &s, &map, 0, 30, 0, 0);
    expect(diff_arms(&rest, &f, &pixels) == 0, "short of half its travel it lights nothing");
    shoot(&f, &s, &map, 0, 57, 57, 0);
    sn64_pad_snes_box(4, &box);
    expect(diff_arms(&rest, &f, &pixels) == 2 && diff_box(&rest, &f, X_RIGHT, Y_PAD, &box) >= 12 && diff_icon(&rest, &f, SN64_IN_STICK, 0, true),
           "towards a corner it lights two directions at once, Up and Right");
    sn64_map_set_stick(&map, 80);
    shoot(&g, &s, &map, 0, 0, 0, 0);
    shoot(&f, &s, &map, 0, 63, 0, 0);
    expect(text_is(&g, X_RIGHT + 91, Y_ROWS + 2, "80 %") && diff_arms(&g, &f, &pixels) == 0, "set to 80 %%: the row says so, and 79 %% of the travel lights nothing");
    shoot(&f, &s, &map, 0, 64, 0, 0);
    expect(diff_arms(&g, &f, &pixels) == 1, "80 %% does");
    sn64_map_set_stick(&map, 0);
    shoot(&g, &s, &map, 0, 0, 0, 0);
    shoot(&f, &s, &map, 0, 127, 127, 0);
    sn64_pad_input_box(SN64_PAD_N64, SN64_IN_STICK, false, &box);
    expect(text_is(&g, X_RIGHT + 91, Y_ROWS + 2, "none") && diff_snes_picture(&g, &f) == 0 && !diff_icon(&g, &f, SN64_IN_STICK, 0, true) &&
           diff_box(&g, &f, X_LEFT, Y_PAD, &box) > 0 && !has_text(&g, "Unmapped:"),
           "set to nothing: the row says none, the cap still moves, nothing lights, and no direction is missing (the D-pad still gives them)");
    sn64_map_default(&map);
    tap(N64_BTN_D_UP);                                          // back on the stick's row
    shoot(&f, &s, &map, 0, 60, 0, 0);
    expect(has_text(&f, "Stick now: 75 %") && find_text(&f, "Stick now: 75 %")->colour == COL_HI, "on the stick's row: how far it is pushed now, lit while it presses");
    shoot(&f, &s, &map, 0, 0, -20, 0);
    expect(has_text(&f, "Stick now: 25 %") && find_text(&f, "Stick now: 25 %")->colour != COL_HI, "and plain while it does not");
    // its choices take the place of the list, and the one under the cursor can be tried before it is taken
    tap(N64_BTN_A);
    shoot(&g, &s, &map, 0, 0, 0, 0);
    {
        int labels = 0;
        char label[32];
        for (int i = 0; i < SN64_STICK_CHOICES - 1; i++) {
            snprintf(label, sizeof label, "D-pad from %u %%", sn64_map_stick_choice(i));
            if (has_text(&g, label) == 1) labels++;
        }
        expect(s.open == SN64_MS_STICK && labels == 7 && has_text(&g, "nothing") == 1 && has_text(&g, "Stick gives:") &&
               has_text(&g, "A pick   B cancel") && !has_text(&g, "C-Up") && has_text(&g, "Stick now: 0 %") && tidy(&g),
               "A on the stick's row: the D-pad from 20 to 80 %%, or nothing, in the place of the list (%d)", labels);
        taps(N64_BTN_D_DOWN, 3);                                // 80 %
        shoot(&g, &s, &map, 0, 0, 0, 0);
        shoot(&f, &s, &map, 0, 50, 0, 0);
        expect(sn64_map_stick_choice(s.pick) == 80 && map.stick_percent == 50 && diff_arms(&g, &f, &pixels) == 0,
               "with 80 %% under the cursor, a push of 62 %% lights nothing, though 50 %% is still what is set");
        taps(N64_BTN_D_DOWN, 2);                                // nothing, then round to 20 %
        shoot(&g, &s, &map, 0, 0, 0, 0);
        shoot(&f, &s, &map, 0, 20, 0, 0);
        expect(sn64_map_stick_choice(s.pick) == 20 && diff_arms(&g, &f, &pixels) == 1, "with 20 %% under the cursor, a push of 25 %% lights Right");
        tap(N64_BTN_B);
        shoot(&f, &s, &map, 0, 20, 0, 0);
        shoot(&g, &s, &map, 0, 0, 0, 0);
        expect(map.stick_percent == 50 && diff_arms(&g, &f, &pixels) == 0, "given up with B, the stick is as it was");
    }
    tap(N64_BTN_D_DOWN);                                        // row A again, as in `rest`

    // a changed row: the new name, and the new button lights
    sn64_map_set_target(&map, SN64_IN_Z, 9);                    // Z gives X
    sn64_pad_snes_box(9, &box);
    shoot(&g, &s, &map, 0, 0, 0, 0);
    shoot(&f, &s, &map, N64_BTN_Z, 0, 0, 0);
    expect(text_is(&g, X_RIGHT + 91, row_y(SN64_IN_Z, 0) + 2, "X") && diff_box(&g, &f, X_RIGHT, Y_PAD, &box) >= 12 &&
           has_text(&g, "Unmapped:") && note_icons(&g, &rest) == 1,
           "Z changed to X: the row says X, X lights, and Select is shown as a button nothing gives");
    sn64_map_set_target(&map, SN64_IN_START, -1);
    s.first = 1;
    shoot(&g, &s, &map, N64_BTN_START, 0, 0, 0);
    expect(text_is(&g, X_RIGHT + 91, row_y(SN64_IN_START, 1) + 2, "none") && has_text(&g, "Unmapped:") && note_icons(&g, &rest) == 2 &&
           diff_snes_picture(&rest, &g) == 0,
           "Start changed to nothing: the row says none, nothing lights on the right, both are shown");
    s.first = 0;
    sn64_map_set_target(&map, SN64_IN_L, -1);
    sn64_map_set_target(&map, SN64_IN_R, -1);
    sn64_map_set_target(&map, SN64_IN_B, -1);
    sn64_map_set_target(&map, SN64_IN_C_DOWN, -1);
    shoot(&g, &s, &map, 0, 0, 0, 0);
    expect(has_text(&g, "Unmapped:") && note_icons(&g, &rest) == 5 && tidy(&g), "up to five are shown as their small pictures");
    sn64_map_set_target(&map, SN64_IN_C_LEFT, -1);                 // Y, which only C-Left gave
    shoot(&g, &s, &map, 0, 0, 0, 0);
    expect(has_text(&g, "Unmapped: 6/12") && note_icons(&g, &rest) == 0 && tidy(&g), "more than five by their number");
    for (int e = 0; e < SN64_MAP_ENTRIES; e++) sn64_map_set_target(&map, e, -1);
    sn64_map_set_stick(&map, 0);
    shoot(&g, &s, &map, (uint16_t)(0xFFFF & ~N64_BTN_C_UP), 127, -128, 0);
    expect(has_text(&g, "Unmapped: 12/12") && has_text(&g, "none") == 10 && diff_snes_picture(&rest, &g) == 0 && tidy(&g),
           "with every row on nothing, nothing lights on the right and the note still fits");

    // the reset note
    sn64_map_default(&map);
    s.restored = true;
    shoot(&g, &s, &map, 0, 0, 0, 0);
    expect(has_text(&g, "Defaults are back"), "the note after a reset");
    s.restored = false;

    // the choices for a button take the place of the list; both pictures stay, the mark follows the choice
    tap(N64_BTN_D_DOWN);                                        // row B
    tap(N64_BTN_A);
    shoot(&f, &s, &map, 0, 0, 0, 16);
    {
        int names = 0;
        for (int i = 0; i < SN64_MAP_CHOICES; i++)
            if (has_text(&f, sn64_snes_button_name(sn64_map_choice(i)))) names++;
        expect(names == 13 && has_text(&f, "B gives:") && has_text(&f, "A pick   B cancel") && !has_text(&f, "C-Up") && tidy(&f),
               "A on a button's row: its 13 choices with their names in the place of the list (%d)", names);
        expect(diff_in(&f, &blank, X_LEFT, Y_PAD, X_LEFT + SN64_PAD_W - 1, Y_PAD + SN64_PAD_INPUT_H - 1) > 6000 &&
               diff_snes_picture(&f, &blank) > 4000,
               "both controllers stay in view beside and above the choices");
        sn64_pad_snes_box(0, &box);
        shoot(&g, &s, &map, 0, 0, 0, 0);
        expect(diff_box(&f, &g, X_RIGHT, Y_PAD, &box) >= 12, "the choice under the cursor (B) is marked on the Super NES controller");
        tap(N64_BTN_D_RIGHT);
        tap(N64_BTN_D_DOWN);                                    // the second column: Up, then Down
        sn64_pad_snes_box(sn64_map_choice(s.pick), &box);
        shoot(&f, &s, &map, 0, 0, 0, 16);
        shoot(&g, &s, &map, 0, 0, 0, 0);
        expect(sn64_map_choice(s.pick) == 5 && diff_box(&f, &g, X_RIGHT, Y_PAD, &box) >= 12, "and moves with it (Down)");
        // tried before it is taken: B held lights Down while Down is under the cursor
        shoot(&f, &s, &map, N64_BTN_B, 0, 0, 0);
        expect(diff_box(&f, &g, X_RIGHT, Y_PAD, &box) >= 12 && sn64_map_target(&map, SN64_IN_B) == 0,
               "the button held lights the choice under the cursor, before it is taken");
        tap(N64_BTN_B);
    }
    // an open list: all its names
    taps(N64_BTN_D_UP, 3);
    tap(N64_BTN_A);
    shoot(&f, &s, &map, 0, 0, 0, 0);
    {
        int names = 0;
        for (unsigned w = 0; w < SN64_PAD_INPUT_COUNT; w++)
            if (has_text(&f, sn64_input_pad_name(w)) >= 1) names++;
        expect(s.open == SN64_MS_LIST_INPUT && names == 6 && has_text(&f, "N64 controller") == 2 && tidy(&f),
               "the left list open: the six controllers by name");
    }
    tap(N64_BTN_B);
    tap(N64_BTN_D_RIGHT);
    tap(N64_BTN_A);
    shoot(&f, &s, &map, 0, 0, 0, 0);
    expect(s.open == SN64_MS_LIST_SNES && has_text(&f, "Super NES") == 2 && has_text(&f, "Super Famicom") == 1 && tidy(&f),
           "the right list open: the two Super NES controllers by name");
    tap(N64_BTN_B);
}

// ---- screens for the mock-ups

static int save(const char *dir, const char *name, shot_t *f)
{
    char path[512];
    static uint8_t rgb[W * H * 3];
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            uint16_t p = *pixel(f, x, y);
            rgb[(y * W + x) * 3 + 0] = (uint8_t)(((p >> 11) & 31) * 255 / 31);
            rgb[(y * W + x) * 3 + 1] = (uint8_t)(((p >> 6) & 31) * 255 / 31);
            rgb[(y * W + x) * 3 + 2] = (uint8_t)(((p >> 1) & 31) * 255 / 31);
        }
    snprintf(path, sizeof path, "%s/%s.ppm", dir, name);
    FILE *o = fopen(path, "wb");
    if (!o) { printf("cannot write %s\n", path); return 1; }
    fprintf(o, "P6\n%d %d\n255\n", W, H);
    fwrite(rgb, 3, W * H, o);
    fclose(o);
    snprintf(path, sizeof path, "%s/%s.txt", dir, name);
    o = fopen(path, "w");
    if (!o) { printf("cannot write %s\n", path); return 1; }
    for (int i = 0; i < f->texts; i++) {
        uint16_t p = f->text[i].colour;
        fprintf(o, "%d %d %02X%02X%02X %s\n", f->text[i].x, f->text[i].y,
                ((p >> 11) & 31) * 255 / 31, ((p >> 6) & 31) * 255 / 31, ((p >> 1) & 31) * 255 / 31, f->text[i].s);
    }
    fclose(o);
    return 0;
}

static int screens(const char *dir)
{
    static shot_t f;
    int bad = 0;
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, SN64_PAD_N64, SN64_PAD_SNES);
    shoot(&f, &s, &map, 0, 0, 0, 16);
    bad |= save(dir, "map-open", &f);
    shoot(&f, &s, &map, 0, 60, 62, 0);                          // the stick up and to the right
    bad |= save(dir, "map-stick", &f);
    tap(N64_BTN_A);                                             // the stick's choices, on 50 %
    tap(N64_BTN_D_DOWN);
    shoot(&f, &s, &map, 0, -45, 0, 0);                          // 60 % under the cursor, the stick at 56 %
    bad |= save(dir, "map-stick-choices", &f);
    tap(N64_BTN_B);
    tap(N64_BTN_D_DOWN);                                        // row A
    shoot(&f, &s, &map, N64_BTN_A, 0, 0, 0);
    bad |= save(dir, "map-a", &f);
    taps(N64_BTN_D_DOWN, 6);                                    // row Z
    shoot(&f, &s, &map, N64_BTN_Z, 0, 0, 0);
    bad |= save(dir, "map-z", &f);
    tap(N64_BTN_A);                                             // Z's choices, on Select
    tap(N64_BTN_D_LEFT);                                        // the first column: A
    taps(N64_BTN_D_DOWN, 3);                                    // Y
    shoot(&f, &s, &map, 0, 0, 0, 16);
    bad |= save(dir, "map-choices", &f);
    tap(N64_BTN_B);
    sn64_mapscreen_open(&s);
    tap(N64_BTN_D_UP);
    tap(N64_BTN_A);
    taps(N64_BTN_D_DOWN, 4);
    shoot(&f, &s, &map, 0, 0, 0, 0);
    bad |= save(dir, "map-list", &f);
    tap(N64_BTN_A);                                             // Brawler64
    tap(N64_BTN_D_RIGHT);
    tap(N64_BTN_A);
    tap(N64_BTN_D_DOWN);
    tap(N64_BTN_A);                                             // Super Famicom
    taps(N64_BTN_D_DOWN, 13);                                   // down the list: it scrolls to D-Down
    shoot(&f, &s, &map, N64_BTN_C_LEFT | N64_BTN_R | N64_BTN_Z, 0, 0, 0);
    bad |= save(dir, "map-other", &f);
    sn64_mapscreen_init(&s, SN64_PAD_M64_PRO, SN64_PAD_SNES);
    sn64_map_set_target(&map, SN64_IN_Z, 9);
    sn64_map_set_target(&map, SN64_IN_C_UP, 10);
    sn64_map_set_target(&map, SN64_IN_L, -1);
    taps(N64_BTN_D_DOWN, 3);                                    // row C-Up
    shoot(&f, &s, &map, N64_BTN_C_UP, 0, 0, 0);
    bad |= save(dir, "map-changed", &f);
    sn64_mapscreen_init(&s, SN64_PAD_8BITDO, SN64_PAD_SNES);
    sn64_map_default(&map);
    tap(N64_BTN_D_DOWN);
    shoot(&f, &s, &map, N64_BTN_C_ALL, 0, 0, 0);
    bad |= save(dir, "map-shortcut", &f);
    return bad;
}

int main(int argc, char **argv)
{
    test_cursor();
    test_choices();
    test_stick();
    test_lists();
    test_reset_and_leave();
    for (unsigned in = 0; in < SN64_PAD_INPUT_COUNT; in++)
        test_lighting(in, in % SN64_PAD_SNES_COUNT);
    test_lighting(SN64_PAD_N64, SN64_PAD_SFC);
    test_drawing();

    if (argc == 3 && strcmp(argv[1], "--screens") == 0 && screens(argv[2]))
        return 1;
    if (failures) {
        printf("FAIL: controller mapping screen, %d of %d checks failed\n", failures, checks);
        return 1;
    }
    printf("PASS: controller mapping screen, %d checks (cursor, the list that scrolls, the two controller lists, the choices "
           "for a button and for the stick, reset, leaving on B let go, buttons that do nothing; each button and the stick light "
           "themselves and what they give and nothing else)\n", checks);
    return 0;
}
