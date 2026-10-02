// SPDX-License-Identifier: GPL-3.0-or-later
// Host test for the controller pictures (src/sn64_padview.c): the shapes are the right ones,
// every button lights its own place and no other, nothing is drawn outside a picture's box
// or outside the screen, the cursor's mark, the stick, the single-button pictures, the six
// controllers and the two Super NES colour sets.
//   test_padview --dump <file.ppm>   also writes all the pictures on one sheet, to look at
// Build with -DSN64_FAULT_PAD_WRONG_BUTTON (A lights where B is): the test must fail.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sn64_mapping.h"
#include "sn64_padview.h"

static int checks, failures;

static void expect(int ok, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
#include <stdarg.h>
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

// A picture's box with a margin round it. The margin holds a value no picture draws (every
// colour has its lowest bit set), so anything drawn outside the box shows.
#define GUARD    12
#define CW       (SN64_PAD_W + 2 * GUARD)
#define CH       (SN64_PAD_INPUT_H + 2 * GUARD)     // the taller of the two picture boxes
#define SENTINEL 0xF81Eu

typedef struct { uint16_t px[CW * CH]; } frame_t;

static sn64_canvas_t canvas(frame_t *f)
{
    for (int i = 0; i < CW * CH; i++) f->px[i] = SENTINEL;
    sn64_canvas_t c = { f->px, CW, CH, CW };
    return c;
}

static int margin_clean(const frame_t *f, int w, int h)
{
    for (int y = 0; y < CH; y++)
        for (int x = 0; x < CW; x++)
            if ((x < GUARD || x >= GUARD + w || y < GUARD || y >= GUARD + h) && f->px[y * CW + x] != SENTINEL)
                return 0;
    return 1;
}

static int in_box(const sn64_box_t *b, int x, int y)
{
    return x >= b->x0 && x <= b->x1 && y >= b->y0 && y <= b->y1;
}

// How many pixels differ between two frames, and how many of those lie outside both boxes
// (coordinates inside the picture; b2 may be NULL).
static int differ(const frame_t *a, const frame_t *b, const sn64_box_t *b1, const sn64_box_t *b2, int *outside)
{
    int n = 0;
    *outside = 0;
    for (int y = 0; y < CH; y++)
        for (int x = 0; x < CW; x++)
            if (a->px[y * CW + x] != b->px[y * CW + x]) {
                n++;
                if (!(b1 && in_box(b1, x - GUARD, y - GUARD)) && !(b2 && in_box(b2, x - GUARD, y - GUARD)))
                    (*outside)++;
            }
    return n;
}

static int differ_in(const frame_t *a, const frame_t *b, const sn64_box_t *box)
{
    int n = 0;
    for (int y = box->y0; y <= box->y1; y++)
        for (int x = box->x0; x <= box->x1; x++)
            if (a->px[(y + GUARD) * CW + x + GUARD] != b->px[(y + GUARD) * CW + x + GUARD])
                n++;
    return n;
}

static void input_frame(frame_t *f, unsigned which, uint16_t n64, int sx, int sy, int cursor, bool blink)
{
    sn64_canvas_t c = canvas(f);
    sn64_pad_draw_input(&c, GUARD, GUARD, which, n64, (int8_t)sx, (int8_t)sy, false, cursor, blink);
}

static void stick_frame(frame_t *f, unsigned which, bool lit, int cursor, bool blink)
{
    sn64_canvas_t c = canvas(f);
    sn64_pad_draw_input(&c, GUARD, GUARD, which, 0, 0, 0, lit, cursor, blink);
}

static void snes_frame(frame_t *f, unsigned which, uint16_t snes, int cursor, bool blink)
{
    sn64_canvas_t c = canvas(f);
    sn64_pad_draw_snes(&c, GUARD, GUARD, which, snes, cursor, blink);
}

static void test_input(unsigned which)
{
    static frame_t rest, lit, mark;
    static uint8_t owner[CW * CH];
    const char *name = sn64_input_pad_name(which);
    int overlaps = 0;
    input_frame(&rest, which, 0, 0, 0, -1, false);
    expect(margin_clean(&rest, SN64_PAD_W, SN64_PAD_INPUT_H), "%s: nothing is drawn outside the picture's box", name);
    memset(owner, 0, sizeof owner);
    for (int e = 0; e < SN64_MAP_ENTRIES; e++) {
        sn64_box_t b1, b2;
        int outside, n;
        bool two = sn64_pad_input_box(which, e, true, &b2);
        expect(sn64_pad_input_box(which, e, false, &b1) && b1.x0 >= 0 && b1.y0 >= 0 && b1.x1 < SN64_PAD_W && b1.y1 < SN64_PAD_INPUT_H,
               "%s: %s has a place inside the picture", name, sn64_map_n64_name(e));
        input_frame(&lit, which, sn64_map_n64_bit(e), 0, 0, -1, false);
        n = differ(&rest, &lit, &b1, two ? &b2 : NULL, &outside);
        expect(n >= 12 && outside == 0 && differ_in(&rest, &lit, &b1) >= 12 && (!two || differ_in(&rest, &lit, &b2) >= 12),
               "%s: %s lights its own place and nothing else (%d pixels change, %d elsewhere)",
               name, sn64_map_n64_name(e), n, outside);
        for (int i = 0; i < CW * CH; i++)
            if (rest.px[i] != lit.px[i]) {
                if (owner[i]) overlaps++;
                owner[i] = (uint8_t)(e + 1);
            }
        // the cursor's mark: the same place, white, only while the blink is on
        input_frame(&mark, which, 0, 0, 0, e, true);
        n = differ(&rest, &mark, &b1, two ? &b2 : NULL, &outside);
        input_frame(&lit, which, 0, 0, 0, e, false);
        expect(n >= 12 && outside == 0 && memcmp(&rest, &lit, sizeof rest) == 0,
               "%s: the cursor marks %s while the blink is on, and only then", name, sn64_map_n64_name(e));
    }
    expect(overlaps == 0, "%s: no two buttons light the same pixel (%d shared)", name, overlaps);
    // the stick's cap moves with the stick, each way differently, and stops at a full throw
    {
        static frame_t f[5], far;
        static const int dir[5][2] = { {0, 0}, {80, 0}, {-80, 0}, {0, 80}, {0, -80} };
        int moved = 1, distinct = 1, small = 1;
        for (int i = 0; i < 5; i++) input_frame(&f[i], which, 0, dir[i][0], dir[i][1], -1, false);
        for (int i = 1; i < 5; i++) {
            int x0 = CW, x1 = -1, y0 = CH, y1 = -1;
            if (memcmp(&f[0], &f[i], sizeof f[0]) == 0) moved = 0;
            for (int k = 1; k < i; k++)
                if (memcmp(&f[k], &f[i], sizeof f[0]) == 0) distinct = 0;
            for (int p = 0; p < CW * CH; p++)
                if (f[0].px[p] != f[i].px[p]) {
                    if (p % CW < x0) x0 = p % CW;
                    if (p % CW > x1) x1 = p % CW;
                    if (p / CW < y0) y0 = p / CW;
                    if (p / CW > y1) y1 = p / CW;
                }
            if (x1 - x0 > 18 || y1 - y0 > 18) small = 0;
            if (!margin_clean(&f[i], SN64_PAD_W, SN64_PAD_INPUT_H)) small = 0;
        }
        input_frame(&far, which, 0, 127, -128, -1, false);
        input_frame(&lit, which, 0, 80, -80, -1, false);
        expect(moved && distinct && small, "%s: the stick's cap moves four ways and stays in its well", name);
        expect(memcmp(&far, &lit, sizeof far) == 0, "%s: beyond a full throw the cap does not move further", name);
    }
    // the stick lights while it presses something, and the cursor can mark it; nothing else changes
    {
        sn64_box_t b;
        int outside, n, m, overlap = 0;
        expect(sn64_pad_input_box(which, SN64_IN_STICK, false, &b) && !sn64_pad_input_box(which, SN64_IN_STICK, true, &b) &&
               b.x0 >= 0 && b.y0 >= 0 && b.x1 < SN64_PAD_W && b.y1 < SN64_PAD_INPUT_H, "%s: the stick has a place inside the picture", name);
        stick_frame(&lit, which, true, -1, false);
        n = differ(&rest, &lit, &b, NULL, &outside);
        for (int i = 0; i < CW * CH; i++)
            if (rest.px[i] != lit.px[i] && owner[i]) overlap++;
        expect(n >= 30 && outside == 0 && overlap == 0, "%s: the stick lights in its own place and no button's (%d pixels change, %d elsewhere)", name, n, outside);
        stick_frame(&mark, which, false, SN64_IN_STICK, true);
        m = differ(&rest, &mark, &b, NULL, &outside);
        stick_frame(&lit, which, false, SN64_IN_STICK, false);
        expect(m >= 30 && outside == 0 && memcmp(&rest, &lit, sizeof rest) == 0, "%s: the cursor marks the stick while the blink is on, and only then", name);
    }
}

// The body on one row of a picture: how many separate stretches it has, and how wide it is
// from its first pixel to its last.
static int body_runs(const frame_t *f, int row, int *width)
{
    int runs = 0, first = -1, last = -1;
    for (int x = 0; x < CW; x++) {
        bool on = f->px[(row + GUARD) * CW + x] != SENTINEL;
        if (on && (x == 0 || f->px[(row + GUARD) * CW + x - 1] == SENTINEL)) runs++;
        if (on) {
            if (first < 0) first = x;
            last = x;
        }
    }
    if (width) *width = first < 0 ? 0 : last - first + 1;
    return runs;
}

// The right shapes (owner, 2026-10-01): three handles of which the middle one is the longest,
// two handles, and the Super NES controller's flat top and stepped underside.
static void test_shapes_of_bodies(void)
{
    static frame_t f;
    int w, wide, top, bottom;
    input_frame(&f, SN64_PAD_N64, 0, 0, 0, -1, false);
    wide = 0;
    top = bottom = -1;
    for (int row = 0; row < SN64_PAD_INPUT_H; row++)
        if (body_runs(&f, row, &w)) {
            if (top < 0) top = row;
            bottom = row;
            if (w > wide) wide = w;
        }
    expect(body_runs(&f, 93, NULL) == 3 && body_runs(&f, 125, &w) == 1 && w < 34,
           "N64 controller: three handles side by side, and only the middle one reaches the bottom");
    expect(body_runs(&f, 62, &w) == 1 && w == wide && wide >= 130, "N64 controller: one wide body above the handles (%d wide)", wide);
    expect(bottom - top + 1 >= wide * 9 / 10 && bottom - top + 1 <= wide,
           "N64 controller: nearly as tall as it is wide (%d by %d)", wide, bottom - top + 1);
    expect(body_runs(&f, 1, &w) == 1 && w < 50, "N64 controller: the top rises in the middle (%d wide there)", w);
    input_frame(&f, SN64_PAD_BRAWLER, 0, 0, 0, -1, false);
    expect(body_runs(&f, 110, NULL) == 2 && body_runs(&f, 60, &w) == 1 && w >= 125, "Brawler64: one wide body, two handles below it");
    input_frame(&f, SN64_PAD_8BITDO, 0, 0, 0, -1, false);
    expect(body_runs(&f, 105, NULL) == 2 && body_runs(&f, 60, &w) == 1 && w >= 120, "8BitDo 64: one wide body, two handles below it");
    snes_frame(&f, SN64_PAD_SNES, 0, -1, false);
    wide = 0;
    for (int row = 10; row <= 66; row++)
        if (body_runs(&f, row, &w) && w > wide) wide = w;
    expect(body_runs(&f, 38, &w) == 1 && w == wide && wide >= 130 && wide * 10 >= 57 * 22,
           "Super NES controller: more than twice as wide as it is high (%d by 57)", wide);
    expect(body_runs(&f, 10, &w) == 1 && w >= 76 && body_runs(&f, 64, NULL) == 2 && body_runs(&f, 67, NULL) == 0,
           "Super NES controller: a flat top between two round ends, and a step up along the bottom");
}

static uint16_t face_colour(const frame_t *f, int snes_bit)
{
    sn64_box_t b;
    sn64_pad_snes_box(snes_bit, &b);
    return f->px[((b.y0 + b.y1) / 2 + GUARD) * CW + (b.x0 + b.x1) / 2 + 4 + GUARD];   // beside the letter
}

static void test_snes(unsigned which)
{
    static frame_t rest, lit, mark;
    static uint8_t owner[CW * CH];
    const char *name = sn64_snes_pad_name(which);
    int overlaps = 0;
    snes_frame(&rest, which, 0, -1, false);
    expect(margin_clean(&rest, SN64_PAD_W, SN64_PAD_SNES_H), "%s: nothing is drawn outside the picture's box", name);
    memset(owner, 0, sizeof owner);
    for (int bit = 0; bit < SNES_BUTTONS; bit++) {
        sn64_box_t b;
        int outside, n;
        expect(sn64_pad_snes_box(bit, &b) && b.x0 >= 0 && b.y0 >= 0 && b.x1 < SN64_PAD_W && b.y1 < SN64_PAD_SNES_H,
               "%s: %s has a place inside the picture", name, sn64_snes_button_name(bit));
        snes_frame(&lit, which, (uint16_t)(1u << bit), -1, false);
        n = differ(&rest, &lit, &b, NULL, &outside);
        expect(n >= 12 && outside == 0, "%s: %s lights its own place and nothing else (%d pixels change, %d elsewhere)",
               name, sn64_snes_button_name(bit), n, outside);
        for (int i = 0; i < CW * CH; i++)
            if (rest.px[i] != lit.px[i]) {
                if (owner[i]) overlaps++;
                owner[i] = (uint8_t)(bit + 1);
            }
        snes_frame(&mark, which, 0, bit, true);
        n = differ(&rest, &mark, &b, NULL, &outside);
        snes_frame(&lit, which, 0, bit, false);
        expect(n >= 12 && outside == 0 && memcmp(&rest, &lit, sizeof rest) == 0,
               "%s: the cursor marks %s while the blink is on, and only then", name, sn64_snes_button_name(bit));
    }
    expect(overlaps == 0, "%s: no two buttons light the same pixel (%d shared)", name, overlaps);
    snes_frame(&lit, which, 0xF000u, -1, false);
    expect(memcmp(&rest, &lit, sizeof rest) == 0, "%s: the four bits above the buttons light nothing", name);
    {
        // the whole D-pad can be marked: its four arms, and nothing else
        int arms = 0, elsewhere = 0;
        snes_frame(&mark, which, 0, SN64_OUT_DPAD, true);
        for (int y = 0; y < CH; y++)
            for (int x = 0; x < CW; x++)
                if (rest.px[y * CW + x] != mark.px[y * CW + x]) {
                    int in = 0;
                    for (int bit = 4; bit < 8; bit++) {
                        sn64_box_t b;
                        sn64_pad_snes_box(bit, &b);
                        if (in_box(&b, x - GUARD, y - GUARD)) in = 1;
                    }
                    if (in) arms++; else elsewhere++;
                }
        snes_frame(&lit, which, 0, SN64_OUT_DPAD, false);
        expect(arms >= 4 * 40 && elsewhere == 0 && memcmp(&rest, &lit, sizeof rest) == 0,
               "%s: the cursor marks the whole D-pad, its four arms and nothing else (%d and %d pixels)", name, arms, elsewhere);
    }
}

// ---- single buttons

#define IW (SN64_ICON + 2 * GUARD)
typedef struct { uint16_t px[IW * IW]; } icon_t;

static sn64_canvas_t icon_canvas(icon_t *f)
{
    for (int i = 0; i < IW * IW; i++) f->px[i] = SENTINEL;
    sn64_canvas_t c = { f->px, IW, IW, IW };
    return c;
}

static int icon_pixels(const icon_t *f, int *stray)
{
    int n = 0;
    *stray = 0;
    for (int y = 0; y < IW; y++)
        for (int x = 0; x < IW; x++)
            if (f->px[y * IW + x] != SENTINEL) {
                n++;
                if (x < GUARD || x >= GUARD + SN64_ICON || y < GUARD || y >= GUARD + SN64_ICON) (*stray)++;
            }
    return n;
}

static void test_icons(void)
{
    static icon_t in[SN64_MAP_ENTRIES], lit, sn[SN64_PAD_SNES_COUNT][SN64_MAP_CHOICES];
    int stray, n, same = 0;
    for (int e = 0; e < SN64_MAP_ENTRIES; e++) {
        sn64_canvas_t c = icon_canvas(&in[e]);
        sn64_pad_icon_input(&c, GUARD, GUARD, e, false);
        n = icon_pixels(&in[e], &stray);
        c = icon_canvas(&lit);
        sn64_pad_icon_input(&c, GUARD, GUARD, e, true);
        expect(n >= 20 && stray == 0 && memcmp(&in[e], &lit, sizeof lit) != 0,
               "the single picture of %s is there, stays in its 11 x 11 and lights up (%d pixels, %d outside)",
               sn64_map_n64_name(e), n, stray);
        for (int k = 0; k < e; k++)
            if (memcmp(&in[k], &in[e], sizeof in[e]) == 0) same++;
    }
    expect(same == 0, "the 14 single pictures of the player's buttons are all different (%d alike)", same);
    {
        // the stick's own small picture, and the whole D-pad with any of its arms lit
        static icon_t stick, dpad[16];
        sn64_canvas_t c = icon_canvas(&stick);
        sn64_pad_icon_input(&c, GUARD, GUARD, SN64_IN_STICK, false);
        n = icon_pixels(&stick, &stray);
        c = icon_canvas(&lit);
        sn64_pad_icon_input(&c, GUARD, GUARD, SN64_IN_STICK, true);
        same = 0;
        for (int e = 0; e < SN64_MAP_ENTRIES; e++)
            if (memcmp(&in[e], &stick, sizeof stick) == 0) same++;
        expect(n >= 60 && stray == 0 && memcmp(&stick, &lit, sizeof lit) != 0 && same == 0,
               "the single picture of the stick is there, is no button's, and lights up (%d pixels, %d outside)", n, stray);
        same = 0;
        for (int d = 0; d < 16; d++) {
            c = icon_canvas(&dpad[d]);
            sn64_pad_icon_dpad(&c, GUARD, GUARD, (uint16_t)(d << 4));     // Up, Down, Left, Right are bits 4 to 7
            if (icon_pixels(&dpad[d], &stray) != 57 || stray) same += 100;   // a cross of two 3 x 11 bars
            for (int k = 0; k < d; k++)
                if (memcmp(&dpad[k], &dpad[d], sizeof lit) == 0) same++;
        }
        expect(same == 0, "the small picture of the whole D-pad: each of the 16 sets of arms lights its own (%d wrong)", same);
    }
    for (unsigned w = 0; w < SN64_PAD_SNES_COUNT; w++) {
        same = 0;
        for (int i = 0; i < SN64_MAP_CHOICES; i++) {
            int bit = sn64_map_choice(i);
            sn64_canvas_t c = icon_canvas(&sn[w][i]);
            sn64_pad_icon_snes(&c, GUARD, GUARD, w, bit, false);
            n = icon_pixels(&sn[w][i], &stray);
            c = icon_canvas(&lit);
            sn64_pad_icon_snes(&c, GUARD, GUARD, w, bit, true);
            expect(n >= (bit < 0 ? 3 : 20) && stray == 0 && (bit < 0 || memcmp(&sn[w][i], &lit, sizeof lit) != 0),
                   "%s: the single picture of %s is there, stays in its 11 x 11 and lights up (%d pixels, %d outside)",
                   sn64_snes_pad_name(w), sn64_snes_button_name(bit), n, stray);
            for (int k = 0; k < i; k++)
                if (memcmp(&sn[w][k], &sn[w][i], sizeof lit) == 0) same++;
        }
        expect(same == 0, "%s: the 13 single pictures are all different (%d alike)", sn64_snes_pad_name(w), same);
    }
    {
        // the two colour sets differ in A, B, X and Y and in nothing else
        int coloured = 0, others = 0;
        for (int i = 0; i < SN64_MAP_CHOICES; i++) {
            int bit = sn64_map_choice(i);
            bool differs = memcmp(&sn[0][i], &sn[1][i], sizeof lit) != 0;
            bool face = bit == 0 || bit == 1 || bit == 8 || bit == 9;
            if (face && differs) coloured++;
            if (!face && differs) others++;
        }
        expect(coloured == 4 && others == 0, "the two colour sets differ in A, B, X and Y only (%d and %d)", coloured, others);
    }
}

// ---- drawing next to and across the edge of the screen

static void test_clipping(void)
{
    // A canvas smaller than its buffer: the columns to the right of it and the rows below it
    // are not its own. Pictures drawn half outside must leave them alone.
    enum { BW = 200, BH = 120, VW = 150, VH = 90 };
    static uint16_t buf[BW * BH];
    static const int at[4][2] = { { -40, -30 }, { VW - 50, VH - 40 }, { -200, 10 }, { 10, 500 } };
    int stray = 0, drawn = 0;
    for (int i = 0; i < BW * BH; i++) buf[i] = SENTINEL;
    sn64_canvas_t c = { buf, VW, VH, BW };
    for (int i = 0; i < 4; i++) {
        sn64_pad_draw_input(&c, at[i][0], at[i][1], SN64_PAD_N64, 0xFFFF, 80, 80, true, SN64_IN_A, true);
        sn64_pad_draw_input(&c, at[i][0], at[i][1], SN64_PAD_BRAWLER, 0xFFFF, -80, -80, false, SN64_IN_STICK, true);
        sn64_pad_icon_dpad(&c, VW - 4, at[i][1] + 20, 0x00F0);
        sn64_pad_icon_input(&c, -5, VH - 6, SN64_IN_STICK, true);
        sn64_pad_draw_snes(&c, at[i][0], at[i][1], SN64_PAD_SFC, 0x0FFF, 3, true);
        sn64_pad_icon_input(&c, at[i][0] + 45, at[i][1] + 35, SN64_IN_L, true);
        sn64_pad_icon_snes(&c, VW - 5, VH - 5, SN64_PAD_SNES, 8, false);
    }
    sn64_pad_fill(&c, -10, -10, VW + 10, 3, sn64_rgb(1, 2, 3));
    sn64_pad_frame(&c, -3, -3, VW + 3, VH + 3, sn64_rgb(1, 2, 3));
    sn64_pad_mark(&c, VW - 2, VH - 1, sn64_rgb(1, 2, 3));
    sn64_pad_arrow(&c, -2, VH - 2, sn64_rgb(1, 2, 3));
    for (int y = 0; y < BH; y++)
        for (int x = 0; x < BW; x++)
            if (buf[y * BW + x] != SENTINEL) {
                drawn++;
                if (x >= VW || y >= VH) stray++;
            }
    expect(drawn > 2000 && stray == 0, "pictures drawn across the edge of the screen are cut off there (%d pixels outside)", stray);
}

static void test_shapes(void)
{
    static frame_t f;
    int n = 0, stray = 0;
    sn64_canvas_t c = canvas(&f);
    uint16_t col = sn64_rgb(255, 255, 255);
    sn64_pad_fill(&c, 20, 20, 22, 21, col);          // 3 x 2
    sn64_pad_frame(&c, 30, 20, 34, 23, col);         // 5 x 4: 14 round the edge
    sn64_pad_mark(&c, 40, 20, col);                  // 5 + 3 + 1
    sn64_pad_arrow(&c, 50, 20, col);                 // 1 + 1 + 5 + 1 + 1
    sn64_pad_mark_up(&c, 60, 20, col);               // 1 + 3 + 5
    for (int y = 0; y < CH; y++)
        for (int x = 0; x < CW; x++)
            if (f.px[y * CW + x] != SENTINEL) {
                n++;
                if (x < 20 || x > 64 || y < 20 || y > 24) stray++;
            }
    expect(n == 6 + 14 + 9 + 9 + 9 && stray == 0 && f.px[22 * CW + 54] == col && f.px[20 * CW + 52] == col &&
           f.px[20 * CW + 62] == col && f.px[22 * CW + 60] == col && f.px[20 * CW + 42] == col,
           "the plain shapes: a block, a frame, the two marks and the arrow (%d pixels)", n);
    expect(sn64_rgb(255, 255, 255) == 0xFFFF && sn64_rgb(0, 0, 0) == 0x0001 && sn64_rgb(255, 0, 0) == 0xF801 &&
           sn64_rgb(0, 255, 0) == 0x07C1 && sn64_rgb(0, 0, 255) == 0x003F, "colours are 5 bits each and the alpha bit");
}

// ---- a sheet of everything, to look at

static void put(uint8_t *rgb, int sw, int x, int y, uint16_t p)
{
    rgb[(y * sw + x) * 3 + 0] = (uint8_t)(((p >> 11) & 31) * 255 / 31);
    rgb[(y * sw + x) * 3 + 1] = (uint8_t)(((p >> 6) & 31) * 255 / 31);
    rgb[(y * sw + x) * 3 + 2] = (uint8_t)(((p >> 1) & 31) * 255 / 31);
}

static int dump(const char *path)
{
    enum { COLS = 4, ROWS = 4, CELLW = SN64_PAD_W + 8, CELLH = SN64_PAD_INPUT_H + 8, SW = COLS * CELLW, SH = ROWS * CELLH + 4 * 16 };
    static uint16_t sheet[SW * SH];
    static uint8_t rgb[SW * SH * 3];
    sn64_canvas_t c = { sheet, SW, SH, SW };
    int cell = 0;
    sn64_pad_fill(&c, 0, 0, SW - 1, SH - 1, sn64_rgb(0x10, 0x18, 0x30));
#define AT (4 + (cell % COLS) * CELLW), (4 + (cell / COLS) * CELLH)
    for (unsigned w = 0; w < SN64_PAD_INPUT_COUNT; w++, cell++)
        sn64_pad_draw_input(&c, AT, w, 0, 0, 0, false, -1, false);
    for (unsigned w = 0; w < SN64_PAD_SNES_COUNT; w++, cell++)
        sn64_pad_draw_snes(&c, AT, w, 0, -1, false);
    sn64_pad_draw_input(&c, AT, SN64_PAD_N64, 0xFFFF, 80, 80, true, -1, false); cell++;
    sn64_pad_draw_input(&c, AT, SN64_PAD_CAPTAIN, 0xFFFF, -80, -80, true, -1, false); cell++;
    sn64_pad_draw_input(&c, AT, SN64_PAD_8BITDO, 0xFFFF, 0, 0, false, -1, false); cell++;
    sn64_pad_draw_snes(&c, AT, SN64_PAD_SNES, 0x0FFF, -1, false); cell++;
    sn64_pad_draw_snes(&c, AT, SN64_PAD_SFC, 0x0FFF, -1, false); cell++;
    sn64_pad_draw_input(&c, AT, SN64_PAD_N64, N64_BTN_A, 0, 0, false, SN64_IN_STICK, true); cell++;
    sn64_pad_draw_snes(&c, AT, SN64_PAD_SNES, SNES_BTN_A, SN64_OUT_DPAD, true); cell++;
    sn64_pad_draw_input(&c, AT, SN64_PAD_BRAWLER, N64_BTN_Z | N64_BTN_C_LEFT, 0, 0, false, SN64_IN_D_UP, true); cell++;
#undef AT
    for (int lit = 0; lit < 2; lit++) {
        int y = ROWS * CELLH + 4 + lit * 32;
        for (int e = 0; e <= SN64_IN_STICK; e++)
            sn64_pad_icon_input(&c, 4 + e * 14, y, e, lit);
        sn64_pad_icon_dpad(&c, 4 + 16 * 14, y, lit ? SNES_BTN_UP | SNES_BTN_RIGHT : 0);
        for (unsigned w = 0; w < SN64_PAD_SNES_COUNT; w++)
            for (int i = 0; i < SN64_MAP_CHOICES; i++)
                sn64_pad_icon_snes(&c, 4 + i * 14 + (int)w * 200, y + 14, w, sn64_map_choice(i), lit);
    }
    for (int i = 0; i < SW * SH; i++) put(rgb, SW, i % SW, i / SW, sheet[i]);
    FILE *f = fopen(path, "wb");
    if (!f) { printf("cannot write %s\n", path); return 1; }
    fprintf(f, "P6\n%d %d\n255\n", SW, SH);
    fwrite(rgb, 3, SW * SH, f);
    fclose(f);
    return 0;
}

int main(int argc, char **argv)
{
    // names for the two lists
    {
        int ok = 1;
        for (unsigned w = 0; w < SN64_PAD_INPUT_COUNT; w++)
            if (!sn64_input_pad_name(w)[0] || strlen(sn64_input_pad_name(w)) > SN64_PAD_NAME_MAX) ok = 0;
        for (unsigned w = 0; w < SN64_PAD_SNES_COUNT; w++)
            if (!sn64_snes_pad_name(w)[0] || strlen(sn64_snes_pad_name(w)) > SN64_PAD_NAME_MAX) ok = 0;
        expect(ok && SN64_PAD_INPUT_COUNT == 6 && SN64_PAD_SNES_COUNT == 2, "six controllers and two colour sets, names of at most 16 characters");
        expect(!sn64_input_pad_name(99)[0] && !sn64_snes_pad_name(99)[0], "outside the lists the name is empty");
    }
    for (unsigned w = 0; w < SN64_PAD_INPUT_COUNT; w++)
        test_input(w);
    {
        // six pictures that can be told apart; the last two have a second Z trigger
        static frame_t f[SN64_PAD_INPUT_COUNT];
        sn64_box_t b;
        int same = 0, second = 0;
        for (unsigned w = 0; w < SN64_PAD_INPUT_COUNT; w++) {
            input_frame(&f[w], w, 0, 0, 0, -1, false);
            for (unsigned k = 0; k < w; k++)
                if (memcmp(&f[k], &f[w], sizeof f[w]) == 0) same++;
            if (sn64_pad_input_box(w, SN64_IN_Z, true, &b)) second |= 1 << w;
        }
        expect(same == 0, "the six controllers' pictures are all different");
        expect(second == ((1 << SN64_PAD_BRAWLER) | (1 << SN64_PAD_8BITDO)), "the two-handled controllers have two Z triggers, the others one");
        expect(!sn64_pad_input_box(SN64_PAD_BRAWLER, SN64_IN_A, true, &b) && !sn64_pad_input_box(99, SN64_IN_A, false, &b) &&
               !sn64_pad_input_box(0, SN64_IN_STICK + 1, false, &b) && !sn64_pad_snes_box(12, &b) && !sn64_pad_snes_box(-1, &b),
               "no place is reported for a button that is not there");
    }
    for (unsigned w = 0; w < SN64_PAD_SNES_COUNT; w++)
        test_snes(w);
    {
        // Super NES: A and B one colour, X and Y another. Super Famicom: four colours.
        static frame_t us, sfc;
        snes_frame(&us, SN64_PAD_SNES, 0, -1, false);
        snes_frame(&sfc, SN64_PAD_SFC, 0, -1, false);
        uint16_t a = face_colour(&us, 8), b = face_colour(&us, 0), x = face_colour(&us, 9), y = face_colour(&us, 1);
        expect(a == b && x == y && a != x, "Super NES: A and B share a colour, X and Y another");
        a = face_colour(&sfc, 8); b = face_colour(&sfc, 0); x = face_colour(&sfc, 9); y = face_colour(&sfc, 1);
        expect(a != b && a != x && a != y && b != x && b != y && x != y, "Super Famicom: A, B, X and Y have four colours");
    }
    test_shapes_of_bodies();
    test_icons();
    test_clipping();
    test_shapes();

    if (argc == 3 && strcmp(argv[1], "--dump") == 0 && dump(argv[2]))
        return 1;
    if (failures) {
        printf("FAIL: controller pictures, %d of %d checks failed\n", failures, checks);
        return 1;
    }
    printf("PASS: controller pictures, %d checks (six controllers and two colour sets: the right shapes, every button and the "
           "stick light their own place and no other, the cursor's mark, single buttons, nothing outside the box or the screen)\n", checks);
    return 0;
}
