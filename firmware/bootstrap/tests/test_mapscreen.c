// SPDX-License-Identifier: GPL-3.0-or-later
// Host test for the controller mapping screen (src/sn64_mapscreen.c): what the buttons do
// (the cursor, the two controller lists, the choices for a row, the reset, leaving), and what
// is drawn (the right button lights in the right picture, the single-button pictures of the
// row light, nothing else changes, text stays on the screen).
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
    expect(s.col == 0 && s.row == 0 && s.open == SN64_MS_CLOSED && sn64_mapscreen_entry(&s) == SN64_IN_A,
           "the screen opens with the cursor on the first row (A) and nothing open");
    tap(N64_BTN_D_RIGHT);
    expect(s.col == 1 && sn64_mapscreen_entry(&s) == SN64_IN_L, "Right goes to the other column (L)");
    taps(N64_BTN_D_DOWN, 6);
    expect(s.row == 6 && sn64_mapscreen_entry(&s) == SN64_IN_D_RIGHT, "six times Down: the last row (D-Right)");
    tap(N64_BTN_D_LEFT);
    expect(s.col == 0 && sn64_mapscreen_entry(&s) == SN64_IN_Z, "Left: the last row of the left column (Z)");
    tap(N64_BTN_D_DOWN);
    expect(s.row == SN64_MS_ROW_RESET && sn64_mapscreen_entry(&s) == -1, "Down from the last row: the reset field");
    tap(N64_BTN_D_LEFT);
    tap(N64_BTN_D_RIGHT);
    expect(s.row == SN64_MS_ROW_RESET && s.col == 0, "Left and Right do nothing on the reset field");
    tap(N64_BTN_D_DOWN);
    expect(s.row == SN64_MS_ROW_LISTS && s.col == 0 && sn64_mapscreen_entry(&s) == -1, "Down from the reset field: round to the lists");
    tap(N64_BTN_D_RIGHT);
    expect(s.row == SN64_MS_ROW_LISTS && s.col == 1, "Right: the other list");
    tap(N64_BTN_D_DOWN);
    expect(s.row == 0 && s.col == 1, "Down from a list: the first row of its column");
    tap(N64_BTN_D_UP);
    tap(N64_BTN_D_UP);
    expect(s.row == SN64_MS_ROW_RESET, "Up from a list: round to the reset field");
    tap(N64_BTN_D_UP);
    expect(s.row == 6 && s.col == 1, "Up from the reset field: the last row, the column as it was");
    sn64_mapscreen_open(&s);
    expect(s.col == 0 && s.row == 0, "opening the screen again puts the cursor back on the first row");
}

static void test_choices(void)
{
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, SN64_PAD_N64, SN64_PAD_SNES);
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_TARGET && sn64_map_choice(s.pick) == 8, "A on a row opens its choices, on what the row gives now (A)");
    tap(N64_BTN_D_RIGHT);
    expect(sn64_map_choice(s.pick) == 0 && sn64_map_target(&map, SN64_IN_A) == 8, "moving in the choices changes nothing yet");
    tap(N64_BTN_A);
    expect(s.open == SN64_MS_CLOSED && sn64_map_target(&map, SN64_IN_A) == 0 &&
           sn64_map_buttons(&map, N64_BTN_A, 0, 0) == SNES_BTN_B, "A takes the choice: the A button now gives B");
    expect(s.col == 0 && s.row == 0, "the cursor stays on the row");
    // B gives the choice up
    tap(N64_BTN_A);
    tap(N64_BTN_D_DOWN);
    expect(sn64_map_choice(s.pick) == 11, "one line down from B: R");
    expect(!tap(N64_BTN_B) && s.open == SN64_MS_CLOSED && sn64_map_target(&map, SN64_IN_A) == 0,
           "B closes the choices, the row stays as it was, and the screen is not left");
    // the lines of four, with "nothing" alone on the last
    tap(N64_BTN_D_DOWN);                                       // row B, which gives B: the second choice
    tap(N64_BTN_A);
    expect(sn64_map_choice(s.pick) == 0 && s.pick == 1, "the choices open on B for the B row");
    tap(N64_BTN_D_LEFT);
    tap(N64_BTN_D_LEFT);
    expect(s.pick == 3, "Left twice from the second: round to the fourth (Y)");
    tap(N64_BTN_D_DOWN);
    expect(s.pick == 7 && sn64_map_choice(s.pick) == 2, "Down: Select");
    taps(N64_BTN_D_DOWN, 2);
    expect(s.pick == 12 && sn64_map_choice(s.pick) == -1, "Down twice: the last line, where nothing stands alone");
    tap(N64_BTN_D_RIGHT);
    tap(N64_BTN_D_LEFT);
    expect(s.pick == 12, "Left and Right stay on nothing");
    tap(N64_BTN_D_DOWN);
    expect(s.pick == 0, "Down from the last line: round to the first (A)");
    tap(N64_BTN_D_UP);
    expect(s.pick == 12, "Up from the first line: nothing");
    tap(N64_BTN_A);
    expect(sn64_map_target(&map, SN64_IN_B) == -1 && sn64_map_buttons(&map, N64_BTN_B, 0, 0) == 0, "nothing can be chosen: B gives nothing");
    // every choice can be reached and taken
    {
        int ok = 1;
        for (int i = 0; i < SN64_MAP_CHOICES; i++) {
            sn64_mapscreen_open(&s);
            tap(N64_BTN_D_RIGHT);                              // row L
            tap(N64_BTN_A);
            for (int guard = 0; guard < 4 && s.pick / 4 != i / 4; guard++) tap(N64_BTN_D_DOWN);
            for (int guard = 0; guard < 4 && s.pick != i; guard++) tap(N64_BTN_D_RIGHT);
            tap(N64_BTN_A);
            if (sn64_map_target(&map, SN64_IN_L) != sn64_map_choice(i)) ok = 0;
        }
        expect(ok, "each of the 13 choices can be reached with the D-pad and taken");
    }
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
    expect(s.open == SN64_MS_TARGET && !sn64_mapscreen_input(&s, &map, 0, N64_BTN_B | N64_BTN_A), "B held while A opens the choices: letting go does not leave");
    expect(!tap(N64_BTN_B) && s.open == SN64_MS_CLOSED, "the B that closes the choices does not leave either");
    expect(tap(N64_BTN_B), "the next B does");
    // the buttons that do nothing here, so they can be tried
    {
        static const uint16_t idle[] = { N64_BTN_Z, N64_BTN_L, N64_BTN_R, N64_BTN_START, N64_BTN_C_UP, N64_BTN_C_DOWN,
                                         N64_BTN_C_LEFT, N64_BTN_C_RIGHT, N64_BTN_C_ALL, 0x00C0u };
        int ok = 1;
        for (int open = 0; open < 3; open++) {
            sn64_map_default(&map);
            sn64_mapscreen_init(&s, SN64_PAD_CAPTAIN, SN64_PAD_SFC);
            if (open == 1) tap(N64_BTN_A);                                        // the choices
            if (open == 2) { tap(N64_BTN_D_UP); tap(N64_BTN_A); }                 // a list
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
// where the screen puts things (src/sn64_mapscreen.c)
#define X_LEFT   16
#define X_RIGHT  164
#define Y_PAD    33
#define Y_GRID   124
#define ROW_H    12

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
    if (x < 16 || x + 8 * len > 304 || y < 8 || y + 8 > 236 || len > 47 || f->texts >= 200) {
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

static void shoot(shot_t *f, const sn64_mapscreen_t *st, const sn64_map_t *m, uint16_t n64, int sx, int sy, unsigned frame)
{
    for (int i = 0; i < BW * BH; i++) f->buf[i] = SENTINEL;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) *pixel(f, x, y) = BG;
    f->texts = f->bad_text = 0;
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

// The single-button pictures of a row: the player's button and what it gives.
static int row_x(int entry) { return entry / SN64_MS_ROWS ? X_RIGHT : X_LEFT; }
static int row_y(int entry) { return Y_GRID + (entry % SN64_MS_ROWS) * ROW_H; }
static int diff_icon(shot_t *a, shot_t *b, int entry, bool snes)
{
    int x = row_x(entry) + (snes ? 78 : 1), y = row_y(entry);
    return diff_in(a, b, x, y, x + SN64_ICON - 1, y + SN64_ICON - 1);
}

static void test_lighting(unsigned input_pad, unsigned snes_pad)
{
    static shot_t rest, lit;
    sn64_box_t in, in2, out;
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, input_pad, snes_pad);
    tap(N64_BTN_D_UP);
    tap(N64_BTN_D_UP);                         // the cursor on the reset field: no button is marked
    shoot(&rest, &s, &map, 0, 0, 0, 0);
    expect(tidy(&rest), "%s / %s: nothing is drawn or written off the screen", sn64_input_pad_name(input_pad), sn64_snes_pad_name(snes_pad));
    int ok = 1;
    for (int e = 0; e < SN64_MAP_ENTRIES; e++) {
        int t = sn64_map_target(&map, e);
        bool two = sn64_pad_input_box(input_pad, e, true, &in2);
        sn64_pad_input_box(input_pad, e, false, &in);
        sn64_pad_snes_box(t, &out);
        shoot(&lit, &s, &map, sn64_map_n64_bit(e), 0, 0, 0);
        int a = diff_box(&rest, &lit, X_LEFT, Y_PAD, &in), a2 = two ? diff_box(&rest, &lit, X_LEFT, Y_PAD, &in2) : 0;
        int b = diff_box(&rest, &lit, X_RIGHT, Y_PAD, &out);
        int c = diff_icon(&rest, &lit, e, false), d = diff_icon(&rest, &lit, e, true);
        int all = diff_all(&rest, &lit);
        if (a < 12 || (two && a2 < 12) || b < 12 || c < 6 || d < 6 || all != a + a2 + b + c + d || !tidy(&lit)) {
            ok = 0;
            printf("    %s: %d + %d in its picture, %d in the other, %d + %d in its row, %d in all\n",
                   sn64_map_n64_name(e), a, a2, b, c, d, all);
        }
    }
    expect(ok, "%s / %s: each button lights itself, the button it gives and the two small pictures of its row, and nothing else",
           sn64_input_pad_name(input_pad), sn64_snes_pad_name(snes_pad));
}

static void test_drawing(void)
{
    static shot_t rest, f, g;
    sn64_box_t box;
    sn64_map_default(&map);
    sn64_mapscreen_init(&s, SN64_PAD_N64, SN64_PAD_SNES);
    shoot(&rest, &s, &map, 0, 0, 0, 0);

    // the text of the screen at rest
    {
        int names = 0, gives = 0;
        for (int e = 0; e < SN64_MAP_ENTRIES; e++) {
            const text_t *n = text_at(&rest, row_x(e) + 14, row_y(e) + 2), *t = text_at(&rest, row_x(e) + 91, row_y(e) + 2);
            if (n && strcmp(n->s, sn64_map_n64_name(e)) == 0) names++;
            if (t && strcmp(t->s, sn64_snes_button_name(sn64_map_target(&map, e))) == 0) gives++;
        }
        expect(names == 14 && gives == 14, "14 rows, each with the button's name and the name of what it gives (%d, %d)", names, gives);
        expect(has_text(&rest, "Your controller") && has_text(&rest, "The game sees") && has_text(&rest, "N64 controller") &&
               has_text(&rest, "Super NES") && has_text(&rest, "Restore defaults") && has_text(&rest, "A change   B back") &&
               has_text(&rest, "In a game, all four C open the menu"), "captions, the two lists' settings, the reset field, the help and the shortcut");
        expect(tidy(&rest) && rest.texts == 14 * 2 + 7, "all of it on the screen (%d pieces of text)", rest.texts);
    }
    // the cursor's mark blinks in both pictures and nowhere else
    {
        sn64_box_t a, b;
        sn64_pad_input_box(SN64_PAD_N64, SN64_IN_A, false, &a);
        sn64_pad_snes_box(8, &b);
        shoot(&f, &s, &map, 0, 0, 0, 16);
        int x = diff_box(&rest, &f, X_LEFT, Y_PAD, &a), y = diff_box(&rest, &f, X_RIGHT, Y_PAD, &b);
        expect(x >= 12 && y >= 12 && diff_all(&rest, &f) == x + y, "the row under the cursor is marked in both pictures, on the blink");
        shoot(&g, &s, &map, 0, 0, 0, 32);
        expect(diff_all(&rest, &g) == 0, "and off again");
    }
    // opposite directions cancel: the game is given neither, and the screen shows that
    shoot(&f, &s, &map, N64_BTN_D_UP | N64_BTN_D_DOWN, 0, 0, 0);
    expect(diff_in(&rest, &f, X_RIGHT, Y_PAD, X_RIGHT + SN64_PAD_W - 1, Y_PAD + SN64_PAD_H - 1) == 0 &&
           diff_icon(&rest, &f, SN64_IN_D_UP, false) && diff_icon(&rest, &f, SN64_IN_D_DOWN, false) &&
           !diff_icon(&rest, &f, SN64_IN_D_UP, true) && !diff_icon(&rest, &f, SN64_IN_D_DOWN, true),
           "Up and Down together: both light on the left, nothing on the right");
    // the menu shortcut: all four C are held, the game is given none of them
    shoot(&f, &s, &map, N64_BTN_C_ALL, 0, 0, 0);
    expect(diff_in(&rest, &f, X_RIGHT, Y_PAD, X_RIGHT + SN64_PAD_W - 1, Y_PAD + SN64_PAD_H - 1) == 0 &&
           diff_icon(&rest, &f, SN64_IN_C_UP, false) && !diff_icon(&rest, &f, SN64_IN_C_UP, true) &&
           has_text(&f, "All four C: in a game, the menu") && !has_text(&f, "In a game, all four C open the menu"),
           "all four C: they light on the left, nothing on the right, and the screen says what they do");
    shoot(&f, &s, &map, N64_BTN_C_ALL & ~N64_BTN_C_UP, 0, 0, 0);
    expect(diff_in(&rest, &f, X_RIGHT, Y_PAD, X_RIGHT + SN64_PAD_W - 1, Y_PAD + SN64_PAD_H - 1) > 0 &&
           !has_text(&f, "All four C: in a game, the menu"), "three C buttons are ordinary buttons");
    // the stick presses the D-pad of the Super NES controller
    sn64_pad_snes_box(7, &box);
    shoot(&f, &s, &map, 0, 80, 0, 0);
    expect(diff_box(&rest, &f, X_RIGHT, Y_PAD, &box) >= 12 && !diff_icon(&rest, &f, SN64_IN_D_RIGHT, true),
           "the stick to the right lights Right on the Super NES controller");
    shoot(&f, &s, &map, 0, 30, 0, 0);
    expect(diff_box(&rest, &f, X_RIGHT, Y_PAD, &box) == 0, "below its threshold it does not");

    // a changed row: the new name, and the new button lights
    sn64_map_set_target(&map, SN64_IN_Z, 9);                    // Z gives X
    sn64_pad_snes_box(9, &box);
    shoot(&g, &s, &map, 0, 0, 0, 0);
    shoot(&f, &s, &map, N64_BTN_Z, 0, 0, 0);
    {
        const text_t *t = text_at(&g, row_x(SN64_IN_Z) + 91, row_y(SN64_IN_Z) + 2);
        expect(t && strcmp(t->s, "X") == 0 && diff_box(&g, &f, X_RIGHT, Y_PAD, &box) >= 12 &&
               has_text(&g, "No button gives Select"), "Z changed to X: the row says X, X lights, and Select is reported as given by no button");
    }
    sn64_map_set_target(&map, SN64_IN_START, -1);
    shoot(&g, &s, &map, N64_BTN_START, 0, 0, 0);
    {
        const text_t *t = text_at(&g, row_x(SN64_IN_START) + 91, row_y(SN64_IN_START) + 2);
        expect(t && strcmp(t->s, "none") == 0 && has_text(&g, "No button gives Select+Start") &&
               diff_in(&rest, &g, X_RIGHT, Y_PAD, X_RIGHT + SN64_PAD_W - 1, Y_PAD + SN64_PAD_H - 1) == 0,
               "Start changed to nothing: the row says none, nothing lights on the right, both are reported");
    }
    sn64_map_set_target(&map, SN64_IN_L, -1);
    shoot(&g, &s, &map, 0, 0, 0, 0);
    expect(has_text(&g, "No button gives 3 Super NES buttons") && tidy(&g), "more than two are reported by their number");
    for (int e = 0; e < SN64_MAP_ENTRIES; e++) sn64_map_set_target(&map, e, -1);
    shoot(&g, &s, &map, (uint16_t)(0xFFFF & ~N64_BTN_C_UP), 0, 0, 0);
    expect(has_text(&g, "No button gives 12 Super NES buttons") && has_text(&g, "none") == 14 && tidy(&g),
           "with every row on nothing the longest note still fits");

    // the reset note
    sn64_map_default(&map);
    s.restored = true;
    shoot(&g, &s, &map, 0, 0, 0, 0);
    expect(has_text(&g, "The defaults are back"), "the note after a reset");
    s.restored = false;

    // the choices take the place of the rows; both pictures stay, the mark follows the choice
    tap(N64_BTN_D_DOWN);                                        // row B
    tap(N64_BTN_A);
    shoot(&f, &s, &map, 0, 0, 0, 16);
    {
        int names = 0;
        for (int i = 0; i < SN64_MAP_CHOICES; i++)
            if (has_text(&f, sn64_snes_button_name(sn64_map_choice(i)))) names++;
        expect(names == 13 && has_text(&f, "B gives:") && has_text(&f, "A pick   B cancel") && !has_text(&f, "C-Up") && tidy(&f),
               "A on a row: its 13 choices with their names in the place of the rows (%d)", names);
        sn64_pad_snes_box(0, &box);
        shoot(&g, &s, &map, 0, 0, 0, 0);
        expect(diff_box(&f, &g, X_RIGHT, Y_PAD, &box) >= 12, "the choice under the cursor (B) is marked on the Super NES controller");
        tap(N64_BTN_D_DOWN);
        tap(N64_BTN_D_DOWN);                                    // Down: one of the D-pad's
        sn64_pad_snes_box(sn64_map_choice(s.pick), &box);
        shoot(&f, &s, &map, 0, 0, 0, 16);
        shoot(&g, &s, &map, 0, 0, 0, 0);
        expect(sn64_map_choice(s.pick) == 5 && diff_box(&f, &g, X_RIGHT, Y_PAD, &box) >= 12, "and moves with it (Down)");
        tap(N64_BTN_B);
    }
    // an open list: all its names
    tap(N64_BTN_D_UP);
    tap(N64_BTN_D_UP);
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
    shoot(&f, &s, &map, N64_BTN_A, 0, 0, 0);
    bad |= save(dir, "map-a", &f);
    tap(N64_BTN_D_DOWN);
    taps(N64_BTN_D_DOWN, 5);                                    // row Z
    shoot(&f, &s, &map, N64_BTN_Z, 0, 0, 0);
    bad |= save(dir, "map-z", &f);
    tap(N64_BTN_A);                                             // Z's choices, on Select
    tap(N64_BTN_D_UP);                                          // one line up: Y
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
    tap(N64_BTN_D_DOWN);
    shoot(&f, &s, &map, N64_BTN_C_LEFT | N64_BTN_R | N64_BTN_Z, 60, 60, 0);
    bad |= save(dir, "map-other", &f);
    sn64_mapscreen_init(&s, SN64_PAD_M64_PRO, SN64_PAD_SNES);
    sn64_map_set_target(&map, SN64_IN_Z, 9);
    sn64_map_set_target(&map, SN64_IN_C_UP, 10);
    sn64_map_set_target(&map, SN64_IN_L, -1);
    taps(N64_BTN_D_DOWN, 2);
    shoot(&f, &s, &map, N64_BTN_C_UP, 0, 0, 0);
    bad |= save(dir, "map-changed", &f);
    shoot(&f, &s, &map, N64_BTN_C_ALL, 0, 0, 0);
    bad |= save(dir, "map-shortcut", &f);
    return bad;
}

int main(int argc, char **argv)
{
    test_cursor();
    test_choices();
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
    printf("PASS: controller mapping screen, %d checks (cursor, the two controller lists, the choices for a row, reset, "
           "leaving on B let go, buttons that do nothing; each button lights itself and what it gives and nothing else)\n", checks);
    return 0;
}
