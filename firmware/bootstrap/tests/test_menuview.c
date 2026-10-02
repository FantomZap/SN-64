// SPDX-License-Identifier: GPL-3.0-or-later
// Host test for the look of the boot menu (src/sn64_menuview.c, src/sn64_theme.c): the themes
// can be read and differ, the logo stands centred at the top with see-through edges and takes
// the theme's ink, the rows of the two menus stand left-justified in one block with the bar
// under the cursor, and everything stays on the screen.
//   test_menuview --screens <dir>   also writes the screens for tools/mock_screens.py:
//                                   <name>.ppm (the pixels) and <name>.txt (the text: x y colour text)
// Build with -DSN64_FAULT_TITLE_OFFCENTRE (the logo 6 pixels to the right): the test must fail.
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "sn64_mapping.h"
#include "sn64_menuview.h"

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

#define W      320
#define H      240
#define GUARD  8
#define BW     (W + 2 * GUARD)
#define BH     (H + 2 * GUARD)
#define SENTINEL 0xF81Eu

typedef struct { int x, y; uint16_t colour; char s[48]; } text_t;
typedef struct {
    uint16_t buf[BW * BH];
    text_t   text[64];
    int      texts, bad_text;
} shot_t;

static void record(void *ctx, int x, int y, uint16_t colour, const char *str)
{
    shot_t *f = ctx;
    int len = (int)strlen(str);
    if (x < 16 || x + 8 * len > 304 || y < 8 || y + 8 > 240 || len > 47 || f->texts >= 64) {
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

static sn64_canvas_t start(shot_t *f, uint16_t fill)
{
    for (int i = 0; i < BW * BH; i++) f->buf[i] = SENTINEL;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) *pixel(f, x, y) = fill;
    f->texts = f->bad_text = 0;
    sn64_canvas_t c = { pixel(f, 0, 0), W, H, BW };
    return c;
}

static int tidy(const shot_t *f)        // nothing outside the screen, no text off it
{
    for (int y = 0; y < BH; y++)
        for (int x = 0; x < BW; x++)
            if ((x < GUARD || x >= GUARD + W || y < GUARD || y >= GUARD + H) && f->buf[y * BW + x] != SENTINEL)
                return 0;
    return f->bad_text == 0;
}

static const text_t *text_at(const shot_t *f, int x, int y)
{
    for (int i = 0; i < f->texts; i++)
        if (f->text[i].x == x && f->text[i].y == y) return &f->text[i];
    return NULL;
}

static int text_is(const shot_t *f, int x, int y, const char *str, uint16_t colour)
{
    const text_t *t = text_at(f, x, y);
    return t && strcmp(t->s, str) == 0 && t->colour == colour;
}

static int has_text(const shot_t *f, const char *str)
{
    for (int i = 0; i < f->texts; i++)
        if (strcmp(f->text[i].s, str) == 0) return 1;
    return 0;
}

static int diff_in(shot_t *a, shot_t *b, int x0, int y0, int x1, int y1)
{
    int n = 0;
    for (int y = y0; y <= y1; y++)
        for (int x = x0; x <= x1; x++)
            if (*pixel(a, x, y) != *pixel(b, x, y)) n++;
    return n;
}

// How light a 16-bit colour is, 0 to 255.
static int light(uint16_t c)
{
    int r = (c >> 11) * 255 / 31, g = ((c >> 6) & 31) * 255 / 31, b = ((c >> 1) & 31) * 255 / 31;
    return (2 * r + 5 * g + b) / 8;
}

static int apart(uint16_t a, uint16_t b)        // how far two colours are apart, summed over the three parts
{
    int d = 0;
    for (int shift = 1; shift <= 11; shift += 5) {
        int x = (a >> shift) & 31, y = (b >> shift) & 31;
        d += x > y ? x - y : y - x;
    }
    return d;
}

static void test_themes(void)
{
    int names = 1, alike = 0;
    for (unsigned k = 0; k < SN64_THEMES; k++) {
        const sn64_theme_t *t = sn64_theme(k);
        if (!t->name[0] || strlen(t->name) > SN64_THEME_NAME_MAX) names = 0;
        for (unsigned j = 0; j < k; j++)
            if (strcmp(sn64_theme(j)->name, t->name) == 0 || apart(sn64_theme(j)->bg, t->bg) < 6) alike++;
        expect(light(t->text) - light(t->bg) >= 150 && light(t->text) - light(t->panel) >= 130 && light(t->text) - light(t->bar) >= 100,
               "%s: text can be read on the screen, on a panel and on the cursor's bar (%d, %d, %d lighter)", t->name,
               light(t->text) - light(t->bg), light(t->text) - light(t->panel), light(t->text) - light(t->bar));
        expect(light(t->hi) - light(t->bar) >= 100 && light(t->hi) - light(t->bg) >= 150 && apart(t->hi, t->text) >= 2,
               "%s: the row under the cursor stands out (%d lighter than its bar)", t->name, light(t->hi) - light(t->bar));
        expect(light(t->dim) - light(t->bg) >= 80 && light(t->text) - light(t->dim) >= 40,
               "%s: dim text can still be read and is plainly dimmer (%d, %d)", t->name,
               light(t->dim) - light(t->bg), light(t->text) - light(t->dim));
        expect(light(t->warn) - light(t->bg) >= 80 && apart(t->warn, t->text) >= 12 && apart(t->warn, t->hi) >= 12,
               "%s: a warning can be read and is neither the text's colour nor the highlight's", t->name);
        expect(light(t->bar) > light(t->panel) && light(t->panel) > light(t->bg) && light(t->bg) > light(t->box) &&
               light(t->ink) - light(t->bg) >= 150,
               "%s: box, screen, panel and bar go from dark to light, and the logo's ink is light on the screen", t->name);
        expect((t->bg & t->panel & t->bar & t->box & t->text & t->dim & t->hi & t->warn & t->ink & 1u) == 1u,
               "%s: every colour is a solid one", t->name);
    }
    expect(SN64_THEMES == 6 && names, "six themes, each with a name of at most %d characters", SN64_THEME_NAME_MAX);
    expect(alike == 0, "no two themes share a name or a background (%d alike)", alike);
    expect(sn64_theme(99) == sn64_theme(SN64_THEME_DEFAULT) && sn64_theme(0) == sn64_theme(SN64_THEME_DEFAULT),
           "an index outside the list is the first theme, which is the one the menu starts in");
}

// The logo: its picture data, and how it lands on the screen.
static void test_title(void)
{
    static shot_t a, b;
    const sn64_theme_t *t = sn64_theme(0);
    const sn64_title_image_t *img[2] = { &sn64_title_large, &sn64_title_small };
    for (int k = 0; k < 2; k++) {
        const sn64_title_image_t *im = img[k];
        const char *name = k ? "small" : "large";
        int ink = 0, own = 0, clear = 0, bad = 0;
        for (int i = 0; i < im->w * im->h; i++) {
            unsigned v = im->pixels[i], solid = v >> 5, index = v & 31u;
            if (!solid) { clear++; if (v) bad++; continue; }
            if (index >= im->colours) bad++;
            if (index) own++; else ink++;
        }
        expect(im->w * 10 >= im->h * 29 && im->w * 10 <= im->h * 32 && im->colours <= 32 && !bad,
               "%s title: about three times as wide as high (%d x %d), at most 32 colours, sound data", name, im->w, im->h);
        expect(ink * 5 >= im->w * im->h && own * 20 >= im->w * im->h && clear * 4 >= im->w * im->h,
               "%s title: ink (the ring and the letters), colours of its own (the buttons) and room to see through (%d, %d, %d)",
               name, ink, own, clear);
        // on the screen: only its own pixels change, the see-through ones do not
        sn64_canvas_t c = start(&a, t->bg);
        sn64_menu_logo(&c, 20, 30, im, t->ink);
        int changed = 0, wrong = 0, between = 1;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                bool inside = x >= 20 && x < 20 + im->w && y >= 30 && y < 30 + im->h;
                unsigned v = inside ? im->pixels[(y - 30) * im->w + (x - 20)] : 0u;
                uint16_t got = *pixel(&a, x, y), full = (v & 31u) ? im->palette[v & 31u] : t->ink;
                if (got != t->bg) changed++;
                if ((v >> 5) == 0u && got != t->bg) wrong++;
                if ((v >> 5) == 7u && got != full) wrong++;
                if ((v >> 5) > 0u && (v >> 5) < 7u)
                    for (int shift = 1; shift <= 11; shift += 5) {
                        int lo = (t->bg >> shift) & 31, hi = (full >> shift) & 31, g = (got >> shift) & 31;
                        if (lo > hi) { int s = lo; lo = hi; hi = s; }
                        if (g < lo || g > hi) between = 0;
                    }
            }
        expect(changed > 0 && wrong == 0 && between && tidy(&a),
               "%s title: solid pixels take their colour, see-through ones leave the screen alone, edges lie between the two", name);
        // the ink is the theme's: another ink changes the ink pixels and no others
        c = start(&b, t->bg);
        sn64_menu_logo(&c, 20, 30, im, SN64_RGB(0, 0, 0));
        int moved = diff_in(&a, &b, 0, 0, W - 1, H - 1);
        expect(moved == ink, "%s title: another ink colour changes the %d pixels of ink and nothing else (%d)", name, ink, moved);
    }
    // across the edge of the screen it is cut off
    {
        sn64_canvas_t c = start(&a, t->bg);
        sn64_menu_logo(&c, -40, -20, &sn64_title_large, t->ink);
        sn64_menu_logo(&c, W - 50, H - 12, &sn64_title_large, t->ink);
        expect(tidy(&a), "a logo drawn across the edge of the screen is cut off there");
    }
    // as the title: centred at the top, with the four-colour rule
    for (int large = 1; large >= 0; large--) {
        const sn64_title_image_t *im = large ? &sn64_title_large : &sn64_title_small;
        const char *name = large ? "large" : "small";
        const int top = large ? SN64_TITLE_LARGE_Y : SN64_TITLE_SMALL_Y;
        const int rule_y = large ? SN64_TITLE_LARGE_RULE_Y : SN64_TITLE_SMALL_RULE_Y;
        const int lx0 = (W - im->w) / 2 - 6, lx1 = (W + im->w) / 2 + 5;     // the logo's columns, and 6 either side
        sn64_canvas_t c = start(&a, t->bg);
        sn64_menu_title(&c, t, large);
        // the logo: what is drawn in its columns, the rule's two rows left out for the large one
        int x0 = W, x1 = -1, y0 = H, y1 = -1;
        for (int y = 0; y < H; y++)
            for (int x = lx0; x <= lx1; x++)
                if (*pixel(&a, x, y) != t->bg && !(large && (y == rule_y || y == rule_y + 1))) {
                    if (x < x0) x0 = x;
                    if (x > x1) x1 = x;
                    if (y < y0) y0 = y;
                    if (y > y1) y1 = y;
                }
        expect(x0 + x1 == W - 1 && x1 - x0 + 1 == im->w && y0 == top && y1 == top + im->h - 1,
               "%s title: the logo stands centred at the top (columns %d to %d, rows %d to %d)", name, x0, x1, y0, y1);
        // the rule: four parts of one length in the logo's four colours. Under the large logo and
        // as wide as it; beside the small one, from margin to margin, two parts a side.
        int rx0 = large ? (W - im->w) / 2 : SN64_TITLE_MARGIN, rx1 = W - 1 - rx0;
        int parts = 0, even = 1, length = -1, gaps_alike = 1, last_end = -1, first_gap = -1, middle_gap = -1;
        uint16_t seen[4] = { 0, 0, 0, 0 };
        for (int x = rx0; x <= rx1; ) {
            uint16_t p = *pixel(&a, x, rule_y);
            int n = 0;
            bool logo = !large && x >= (W - im->w) / 2 && x < (W + im->w) / 2;
            while (x + n <= rx1 && *pixel(&a, x + n, rule_y) == p) n++;
            if (p != t->bg && !logo) {
                if (parts < 4) seen[parts] = p;
                if (length < 0) length = n;
                if (n != length || *pixel(&a, x, rule_y + 1) != p || *pixel(&a, x, rule_y - 1) == p || *pixel(&a, x, rule_y + 2) == p) even = 0;
                if (last_end >= 0) {
                    int gap = x - last_end - 1;
                    if (!large && parts == 2) middle_gap = gap;         // the logo stands in this one
                    else if (first_gap < 0) first_gap = gap;
                    else if (gap != first_gap) gaps_alike = 0;
                }
                last_end = x + n - 1;
                parts++;
            }
            x += n;
        }
        expect(parts == 4 && even && gaps_alike && *pixel(&a, rx0, rule_y) != t->bg && *pixel(&a, rx1, rule_y) != t->bg &&
               *pixel(&a, rx0 - 1, rule_y) == t->bg && *pixel(&a, rx1 + 1, rule_y) == t->bg,
               "%s title: a rule two rows high in four equal parts of %d from column %d to %d", name, length, rx0, rx1);
        expect(seen[0] == SN64_RGB(0x1E, 0x9B, 0x55) && seen[1] == SN64_RGB(0x24, 0x49, 0xB8) &&
               seen[2] == SN64_RGB(0xF4, 0xB4, 0x00) && seen[3] == SN64_RGB(0xE0, 0x35, 0x2B),
               "%s title: the rule is green, blue, yellow, red, the logo's own colours in its own order", name);
        int below = 0, limit = large ? rule_y + 2 : top + im->h;
        for (int y = limit; y < H; y++)
            for (int x = 0; x < W; x++)
                if (*pixel(&a, x, y) != t->bg) below++;
        expect(below == 0 && tidy(&a), "%s title: nothing is drawn from row %d down", name, limit);
        if (!large)
            expect(middle_gap >= im->w + 12 && rule_y > top && rule_y + 1 < top + im->h - 1 && limit + 4 <= SN64_MENU_TEXT_TOP,
                   "small title: the rule runs out to both sides of the logo and stops short of it, and the screen is free "
                   "from row %d down with %d rows of room over the first line", SN64_MENU_TEXT_TOP, SN64_MENU_TEXT_TOP - limit);
    }
}

static int row_y(int row) { return SN64_MENU_ROWS_Y + row * SN64_MENU_ROW_H; }

static void main_shot(shot_t *f, const sn64_theme_t *t, const sn64_menu_view_t *v)
{
    sn64_canvas_t c = start(f, SENTINEL);       // the menu clears the screen itself
    sn64_menu_draw_main(&c, record, f, t, v);
}

static void settings_shot(shot_t *f, const sn64_theme_t *t, const sn64_menu_view_t *v, bool compat, unsigned theme)
{
    sn64_canvas_t c = start(f, SENTINEL);
    sn64_menu_draw_settings(&c, record, f, t, v, compat, theme);
}

static void test_main_menu(void)
{
    static shot_t f[SN64_MAIN_ITEMS], g;
    static const char *const names[SN64_MAIN_ITEMS] = { "Play", "Controller mapping", "Settings", "Power off cartridge" };
    const sn64_theme_t *t = sn64_theme(0);
    for (int cur = 0; cur < SN64_MAIN_ITEMS; cur++) {
        sn64_menu_view_t v = { .cursor = cur, .head = "Cartridge: off", .message = "" };
        main_shot(&f[cur], t, &v);
        int rows = 0, bars = 0, marks = 0;
        for (int i = 0; i < SN64_MAIN_ITEMS; i++) {
            if (text_is(&f[cur], SN64_MENU_TEXT_X, row_y(i) + 5, names[i], i == cur ? t->hi : t->text)) rows++;
            if ((*pixel(&f[cur], SN64_MENU_BAR_X0 + 3, row_y(i) + 8) == t->bar) == (i == cur) &&
                (*pixel(&f[cur], SN64_MENU_BAR_X1 - 3, row_y(i) + 8) == t->bar) == (i == cur)) bars++;
            // the mark: a disc of one of the four colours with a line round it, white under the cursor
            if (*pixel(&f[cur], SN64_MENU_X + 6 - 5, row_y(i) + 8) != t->bg && *pixel(&f[cur], SN64_MENU_X + 6 - 5, row_y(i) + 8) != t->bar &&
                (*pixel(&f[cur], SN64_MENU_X + 6 - 7, row_y(i) + 8) == SN64_RGB(255, 255, 255)) == (i == cur)) marks++;
        }
        expect(rows == 4 && bars == 4 && marks == 4 && tidy(&f[cur]),
               "main menu, cursor on %s: four rows left-justified at column %d, the bar and the lit mark on that row only (%d, %d, %d)",
               names[cur], SN64_MENU_TEXT_X, rows, bars, marks);
        if (cur) {
            // moving the cursor changes the two rows and nothing else
            int lo = row_y(cur - 1), hi = row_y(cur) + SN64_MENU_ROW_H - 1;
            expect(diff_in(&f[cur - 1], &f[cur], 0, lo, W - 1, hi) > 500 && diff_in(&f[cur - 1], &f[cur], 0, 0, W - 1, lo - 1) == 0 &&
                   diff_in(&f[cur - 1], &f[cur], 0, hi + 1, W - 1, H - 1) == 0, "and only the two rows it moved between change");
        }
    }
    {
        // the four marks carry the logo's four colours, in its order
        uint16_t m[4];
        for (int i = 0; i < 4; i++) m[i] = *pixel(&f[0], SN64_MENU_X + 6 - 5, row_y(i) + 8);
        expect(m[0] == SN64_RGB(0x1E, 0x9B, 0x55) && m[1] == SN64_RGB(0x24, 0x49, 0xB8) && m[2] == SN64_RGB(0xF4, 0xB4, 0x00) &&
               m[3] == SN64_RGB(0xE0, 0x35, 0x2B), "the rows' marks are green, blue, yellow and red");
        expect(*pixel(&f[0], 2, 2) == t->bg && *pixel(&f[0], W - 3, H - 3) == t->bg, "the menu clears the whole screen to the theme's background");
        expect(text_is(&f[0], SN64_MENU_X, SN64_MENU_HEAD_Y, "Cartridge: off", t->dim) && has_text(&f[0], "In a game:") &&
               has_text(&f[0], "= menu") && has_text(&f[0], "select") && has_text(&f[0], "choose") && !has_text(&f[0], "back"),
               "over the rows the cartridge in a word; under them how the menu is reached from a game and what the buttons do");
        // the logo stands over the middle of the screen, not over the block of rows
        int x0 = W, x1 = -1;
        for (int y = 8; y < 60; y++)
            for (int x = 0; x < W; x++)
                if (*pixel(&f[0], x, y) != t->bg) {
                    if (x < x0) x0 = x;
                    if (x > x1) x1 = x;
                }
        expect(x0 + x1 == W - 1, "the logo is centred over the screen (columns %d to %d)", x0, x1);
    }
    {
        // messages and warnings: a note is plain, a refusal and the standing warnings are in the warning colour
        sn64_menu_view_t v = { .cursor = 3, .head = "Cartridge: power fault", .head_bad = true, .message = "Power fault: not starting",
                               .message_bad = true, .warning = { "Cartridge check: report only", "Compatibility mode is on" } };
        int y = row_y(SN64_MAIN_ITEMS) + SN64_MENU_UNDER;
        main_shot(&g, t, &v);
        expect(text_is(&g, SN64_MENU_X, SN64_MENU_HEAD_Y, "Cartridge: power fault", t->warn) &&
               text_is(&g, SN64_MENU_X, y, "Power fault: not starting", t->warn) &&
               text_is(&g, SN64_MENU_X, y + 12, "Cartridge check: report only", t->warn) &&
               text_is(&g, SN64_MENU_X, y + 22, "Compatibility mode is on", t->warn) && tidy(&g),
               "a refusal and the standing warnings stand under the rows in the warning colour");
        v.message = "Cartridge is off";
        v.message_bad = false;
        main_shot(&g, t, &v);
        expect(text_is(&g, SN64_MENU_X, y, "Cartridge is off", t->text), "a plain note in the text colour");
        expect(strlen("Cartridge check: report only") <= SN64_MENU_COLUMNS && SN64_MENU_X + 8 * SN64_MENU_COLUMNS <= 304,
               "%d characters fit from the block's left edge to the screen's margin", SN64_MENU_COLUMNS);
    }
}

static void test_settings(void)
{
    static shot_t f, g;
    static const char *const fixed[SN64_SET_ITEMS] = { NULL, NULL, "Status / diagnostics", "Credits", "About" };
    const sn64_theme_t *t = sn64_theme(0);
    for (int cur = 0; cur < SN64_SET_ITEMS; cur++) {
        sn64_menu_view_t v = { .cursor = cur, .head = "Settings", .message = "" };
        settings_shot(&f, t, &v, false, 0);
        int rows = 0, bars = 0;
        for (int i = 0; i < SN64_SET_ITEMS; i++) {
            const char *want = i == SN64_SET_COMPAT ? "Compatibility mode: off" : i == SN64_SET_THEME ? "Theme: Midnight" : fixed[i];
            if (text_is(&f, SN64_MENU_TEXT_X, row_y(i) + 5, want, i == cur ? t->hi : t->text)) rows++;
            if ((*pixel(&f, SN64_MENU_BAR_X0 + 3, row_y(i) + 8) == t->bar) == (i == cur)) bars++;
        }
        expect(rows == SN64_SET_ITEMS && bars == SN64_SET_ITEMS && tidy(&f) &&
               text_is(&f, SN64_MENU_X, SN64_MENU_HEAD_Y, "Settings", t->hi) && has_text(&f, "back"),
               "Settings, cursor on row %d: five rows at the same left edge as the main menu's, the bar on that row only (%d, %d)", cur, rows, bars);
    }
    {
        sn64_menu_view_t v = { .cursor = SN64_SET_THEME, .head = "Settings", .message = "Compatibility mode on" };
        int themes = 0;
        settings_shot(&g, t, &v, true, 0);
        expect(text_is(&g, SN64_MENU_TEXT_X, row_y(SN64_SET_COMPAT) + 5, "Compatibility mode: ON", t->text) &&
               text_is(&g, SN64_MENU_X, row_y(SN64_SET_ITEMS) + SN64_MENU_UNDER, "Compatibility mode on", t->text),
               "the first row says whether compatibility mode is on");
        for (unsigned k = 0; k < SN64_THEMES; k++) {
            char want[32];
            snprintf(want, sizeof want, "Theme: %s", sn64_theme(k)->name);
            settings_shot(&g, sn64_theme(k), &v, false, k);
            if (text_is(&g, SN64_MENU_TEXT_X, row_y(SN64_SET_THEME) + 5, want, sn64_theme(k)->hi) && *pixel(&g, 2, 2) == sn64_theme(k)->bg &&
                *pixel(&g, SN64_MENU_BAR_X0 + 3, row_y(SN64_SET_THEME) + 8) == sn64_theme(k)->bar && tidy(&g)) themes++;
        }
        expect(themes == SN64_THEMES, "the second row names the theme, and the screen is in that theme's colours (%d of %d)", themes, SN64_THEMES);
    }
}

// The same main menu in every theme: its own colours, and the logo's own colours untouched.
static void test_every_theme(void)
{
    static shot_t f[SN64_THEMES];
    sn64_menu_view_t v = { .cursor = 0, .head = "Cartridge: off", .message = "" };
    int ok = 1, alike = 0;
    for (unsigned k = 0; k < SN64_THEMES; k++) {
        const sn64_theme_t *t = sn64_theme(k);
        main_shot(&f[k], t, &v);
        if (!tidy(&f[k]) || *pixel(&f[k], 2, 2) != t->bg || !text_is(&f[k], SN64_MENU_TEXT_X, row_y(0) + 5, "Play", t->hi) ||
            !text_is(&f[k], SN64_MENU_TEXT_X, row_y(1) + 5, "Controller mapping", t->text)) ok = 0;
        // the logo: its solid pixels are the same in every theme, except the ink, which is the theme's
        for (int y = 0; y < sn64_title_large.h; y++)
            for (int x = 0; x < sn64_title_large.w; x++) {
                unsigned px = sn64_title_large.pixels[y * sn64_title_large.w + x];
                uint16_t got = *pixel(&f[k], (W - sn64_title_large.w) / 2 + x, 8 + y);
                if ((px >> 5) == 7u && got != ((px & 31u) ? sn64_title_large.palette[px & 31u] : t->ink)) ok = 0;
            }
        for (unsigned j = 0; j < k; j++)
            if (diff_in(&f[j], &f[k], 0, 0, W - 1, H - 1) < 40000) alike++;
    }
    expect(ok, "in every theme: its background, its text colours, and the logo in its own colours with the theme's ink");
    expect(alike == 0, "no two themes give the same screen (%d pairs too much alike)", alike);
}

// About: who made it, the versions, the licences; every line fits the screen.
static void test_about(void)
{
    char text[SN64_ABOUT_LINES][SN64_ABOUT_COLUMNS + 1];
    uint8_t kind[SN64_ABOUT_LINES];
    sn64_about_t a = { .credit = "SN64 by FantomZap", .source = "github.com/FantomZap/SN-64", .menu_version = "0.1.0",
                       .present = true, .magic = 0x534E, .version = 0x0102, .features = 0x0003, .tv = 1 };
    int found = 0, fits = 1;
    sn64_menu_about(&a, text, kind);
    expect(strcmp(text[0], "About") == 0 && kind[0] == SN64_LINE_HI && strcmp(text[2], a.credit) == 0 && kind[2] == SN64_LINE_TEXT &&
           strcmp(text[3], a.source) == 0 && kind[3] == SN64_LINE_DIM,
           "About opens with its name, the credit line and where the source is");
    for (int i = 0; i < SN64_ABOUT_LINES; i++) {
        if (strlen(text[i]) > SN64_ABOUT_COLUMNS) fits = 0;
        if (strcmp(text[i], "Menu program   v0.1.0") == 0 || strcmp(text[i], "SN64 build     1.2 (0x0102)") == 0 ||
            strcmp(text[i], "Features       0x0003") == 0 || strcmp(text[i], "Console        NTSC, 60 Hz") == 0 ||
            strcmp(text[i], "Code           GPL-3.0-or-later") == 0 || strcmp(text[i], "Hardware, docs CERN-OHL-S-2.0") == 0)
            found += kind[i] == SN64_LINE_TEXT;
        if (kind[i] == SN64_LINE_WARN) found = -100;
    }
    expect(found == 6 && fits, "it gives the menu program's version, the SN64 build, its features, the console and the two licences (%d of 6)", found);
    expect(strstr(text[13], "No warranty") && strstr(text[14], "Nintendo") && strstr(text[13], "Not affiliated") &&
           kind[13] == SN64_LINE_DIM && kind[14] == SN64_LINE_DIM, "and ends with no warranty and no affiliation");
    expect(16 + 8 * SN64_ABOUT_COLUMNS <= 304 && 12 + 10 * (2 + SN64_ABOUT_LINES - 1) + 8 <= 12 + 10 * 22 &&
           12 + 10 * 2 >= SN64_MENU_TEXT_TOP,
           "its %d lines of at most %d characters stand under the small title and over the last line of the screen",
           SN64_ABOUT_LINES, SN64_ABOUT_COLUMNS);
    // no SN64 answered
    a.present = false;
    a.magic = 0xFFFF;
    a.tv = 0;
    sn64_menu_about(&a, text, kind);
    expect(strcmp(text[6], "SN64 build     not found (FFFF)") == 0 && kind[6] == SN64_LINE_WARN && strcmp(text[7], "Features       -") == 0 &&
           strcmp(text[8], "Console        PAL, 50 Hz") == 0, "with no SN64 answering it says so, in the warning colour");
    a.tv = 2;
    sn64_menu_about(&a, text, kind);
    expect(strcmp(text[8], "Console        M-PAL, 60 Hz") == 0, "the third kind of console is named too");
    a.tv = 9;
    a.credit = "a credit line that is far longer than the screen is wide, twice over";
    sn64_menu_about(&a, text, kind);
    expect(strcmp(text[8], "Console        ?") == 0 && strlen(text[2]) == SN64_ABOUT_COLUMNS,
           "an unknown console is a question mark, and a line that is too long is cut at the screen's edge");
}

// ---- screens for the mock-ups

static int save_about(const char *dir, const char *name, const sn64_about_t *a)
{
    char path[512], text[SN64_ABOUT_LINES][SN64_ABOUT_COLUMNS + 1];
    uint8_t kind[SN64_ABOUT_LINES];
    sn64_menu_about(a, text, kind);
    snprintf(path, sizeof path, "%s/%s.txt", dir, name);
    FILE *o = fopen(path, "w");
    if (!o) { printf("cannot write %s\n", path); return 1; }
    for (int i = 0; i < SN64_ABOUT_LINES; i++)
        fprintf(o, "%u|%s\n", (unsigned)kind[i], text[i]);
    fclose(o);
    return 0;
}

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
    char name[40];
    int bad = 0;
    for (unsigned k = 0; k < SN64_THEMES; k++) {
        const sn64_theme_t *t = sn64_theme(k);
        sn64_menu_view_t v = { .cursor = (int)(k % SN64_MAIN_ITEMS), .head = "Cartridge: off", .message = "" };
        main_shot(&f, t, &v);
        snprintf(name, sizeof name, "menu-main-%u", k);
        bad |= save(dir, name, &f);
        // the top of a text screen in this theme: the mock-up tool writes the screen's lines on it
        sn64_canvas_t c = start(&f, t->bg);
        sn64_menu_title(&c, t, false);
        snprintf(name, sizeof name, "menu-text-%u", k);
        bad |= save(dir, name, &f);
        // the palette, for the mock-up tool: one line of text per colour, in that colour
        c = start(&f, t->bg);
        record(&f, 16, 8, t->text, "text");
        record(&f, 16, 18, t->dim, "dim");
        record(&f, 16, 28, t->hi, "hi");
        record(&f, 16, 38, t->warn, "warn");
        record(&f, 16, 48, t->bg, t->name);
        snprintf(name, sizeof name, "menu-colours-%u", k);
        bad |= save(dir, name, &f);
    }
    {
        const sn64_theme_t *t = sn64_theme(0);
        sn64_menu_view_t v = { .cursor = SN64_SET_THEME, .head = "Settings", .message = "" };
        settings_shot(&f, t, &v, false, 0);
        bad |= save(dir, "menu-settings", &f);
        v.cursor = SN64_SET_COMPAT;
        settings_shot(&f, t, &v, false, 0);
        bad |= save(dir, "menu-settings-compat", &f);
        v.message = "Compatibility mode on";       // Settings does not add the standing warning: its first row says it
        settings_shot(&f, t, &v, true, 0);
        bad |= save(dir, "menu-settings-compat-on", &f);
        v = (sn64_menu_view_t){ .cursor = SN64_SET_CREDITS, .head = "Settings", .message = "" };
        settings_shot(&f, t, &v, false, 0);
        bad |= save(dir, "menu-settings-credits", &f);
        v = (sn64_menu_view_t){ .cursor = SN64_SET_ABOUT, .head = "Settings", .message = "" };
        settings_shot(&f, t, &v, false, 0);
        bad |= save(dir, "menu-settings-about", &f);
        v = (sn64_menu_view_t){ .cursor = 0, .head = "Cartridge: running", .message = "Cartridge still running" };
        main_shot(&f, t, &v);
        bad |= save(dir, "menu-main-running", &f);
        v = (sn64_menu_view_t){ .cursor = SN64_SET_THEME, .head = "Settings", .message = "" };
        settings_shot(&f, sn64_theme(2), &v, false, 2);
        bad |= save(dir, "menu-settings-grape", &f);
        v = (sn64_menu_view_t){ .cursor = 0, .head = "Cartridge: off", .message = "", .warning = { "Compatibility mode is on" } };
        main_shot(&f, t, &v);
        bad |= save(dir, "menu-main-compat", &f);
        v = (sn64_menu_view_t){ .cursor = 0, .head = "SN64 hardware not found", .head_bad = true,
                                .message = "Cannot start a cartridge", .message_bad = true };
        main_shot(&f, t, &v);
        bad |= save(dir, "menu-main-missing", &f);
    }
    {
        // About, as the SN64 answers in the simulation, and with none answering
        sn64_about_t a = { .credit = "SN64 by FantomZap", .source = "github.com/FantomZap/SN-64", .menu_version = "0.1.0",
                           .present = true, .magic = 0x534E, .version = 0x0001, .features = 0x0003, .tv = 1 };
        bad |= save_about(dir, "about", &a);
        a.present = false;
        a.magic = 0xFFFF;
        bad |= save_about(dir, "about-missing", &a);
    }
    return bad;
}

int main(int argc, char **argv)
{
    test_themes();
    test_title();
    test_main_menu();
    test_settings();
    test_every_theme();
    test_about();

    if (argc == 3 && strcmp(argv[1], "--screens") == 0 && screens(argv[2]))
        return 1;
    if (failures) {
        printf("FAIL: menu look, %d of %d checks failed\n", failures, checks);
        return 1;
    }
    printf("PASS: menu look, %d checks (six themes that can be read and differ, the logo centred at the top with see-through "
           "edges and the theme's ink, the two menus' rows left-justified in one block with the bar under the cursor, "
           "the About text)\n", checks);
    return 0;
}
