// SPDX-License-Identifier: GPL-3.0-or-later
#include "sn64_menuview.h"

#include <stdio.h>
#include <string.h>

#include "sn64_mapping.h"

#define SCREEN_W   320

// The logo's four colours (assets/logo/make_logo.py), in the order of its buttons and of the
// bar under its letters: green, blue, yellow, red.
static const uint16_t logo_colours[4] = {
    SN64_RGB(0x1E, 0x9B, 0x55), SN64_RGB(0x24, 0x49, 0xB8), SN64_RGB(0xF4, 0xB4, 0x00), SN64_RGB(0xE0, 0x35, 0x2B),
};
#define MARK_EDGE  SN64_RGB(0x14, 0x16, 0x20)       // the dark line round a row's mark
#define MARK_LIT   SN64_RGB(0xFF, 0xFF, 0xFF)       // ... and the white one on the row under the cursor
#define INK_LIGHT  SN64_RGB(0xFF, 0xFF, 0xFF)
#define INK_DARK   SN64_RGB(0x25, 0x25, 0x2C)

#ifdef SN64_FAULT_TITLE_OFFCENTRE
// Fault injection for the host test: the logo stands 6 pixels to the right; the test must fail.
#define TITLE_SHIFT_X 6
#else
#define TITLE_SHIFT_X 0
#endif

// ---- the title

// `over` laid on `under`, `a` sevenths of it.
static uint16_t blend(uint16_t under, uint16_t over, unsigned a)
{
    unsigned r = ((under >> 11) * (7u - a) + (over >> 11) * a + 3u) / 7u;
    unsigned g = (((under >> 6) & 31u) * (7u - a) + ((over >> 6) & 31u) * a + 3u) / 7u;
    unsigned b = (((under >> 1) & 31u) * (7u - a) + ((over >> 1) & 31u) * a + 3u) / 7u;
    return (uint16_t)((r << 11) | (g << 6) | (b << 1) | 1u);
}

void sn64_menu_logo(const sn64_canvas_t *c, int x0, int y0, const sn64_title_image_t *img, uint16_t ink)
{
    for (int y = 0; y < (int)img->h; y++) {
        int sy = y0 + y;
        if (sy < 0 || sy >= c->height)
            continue;
        const uint8_t *row = img->pixels + (unsigned)y * img->w;
        uint16_t *out = c->fb + (long)sy * c->stride;
        for (int x = 0; x < (int)img->w; x++) {
            unsigned v = row[x], a = v >> 5, i = v & 31u;
            int sx = x0 + x;
            if (!a || sx < 0 || sx >= c->width)
                continue;
            uint16_t colour = (i && i < img->colours) ? img->palette[i] : ink;
            out[sx] = a == 7u ? colour : blend(out[sx], colour, a);
        }
    }
}

// A rule two pixels high in the logo's four colours, in four equal parts with small gaps.
static void rule(const sn64_canvas_t *c, int x0, int x1, int y)
{
    int part = (x1 - x0 + 1 - 3 * 4) / 4;
    for (int i = 0; i < 4; i++) {
        int x = x0 + i * (part + 4);
        sn64_pad_fill(c, x, y, x + part - 1, y + 1, logo_colours[i]);
    }
}

void sn64_menu_clear(const sn64_canvas_t *c, const sn64_theme_t *t)
{
    sn64_pad_fill(c, 0, 0, c->width - 1, c->height - 1, t->bg);
}

void sn64_menu_title(const sn64_canvas_t *c, const sn64_theme_t *t, bool large)
{
    const sn64_title_image_t *img = large ? &sn64_title_large : &sn64_title_small;
    int x = (SCREEN_W - (int)img->w) / 2 + TITLE_SHIFT_X;
    if (large) {
        sn64_menu_logo(c, x, SN64_TITLE_LARGE_Y, img, t->ink);
        rule(c, (SCREEN_W - (int)img->w) / 2, (SCREEN_W + (int)img->w) / 2 - 1, SN64_TITLE_LARGE_RULE_Y);
    } else {
        // the rule runs out to both sides of the logo, level with its middle: two colours a side
        const int inner = (SCREEN_W - (int)img->w) / 2 - 10;        // where the left half ends
        const int part = (inner - SN64_TITLE_MARGIN + 1 - 4) / 2;   // two parts with a gap of 4
        const int at[2] = { SN64_TITLE_MARGIN, inner - part + 1 };
        sn64_menu_logo(c, x, SN64_TITLE_SMALL_Y, img, t->ink);
        for (int i = 0; i < 2; i++) {
            sn64_pad_fill(c, at[i], SN64_TITLE_SMALL_RULE_Y, at[i] + part - 1, SN64_TITLE_SMALL_RULE_Y + 1, logo_colours[i]);
            sn64_pad_fill(c, SCREEN_W - at[i] - part, SN64_TITLE_SMALL_RULE_Y, SCREEN_W - 1 - at[i],
                          SN64_TITLE_SMALL_RULE_Y + 1, logo_colours[3 - i]);
        }
    }
}

// ---- the rows

// Seven-by-seven signs for the marks of the main menu's rows, one row per byte, the left
// column in bit 6: play, a D-pad, two sliders, power.
static const uint8_t signs[SN64_MAIN_ITEMS][7] = {
    [SN64_MAIN_PLAY]      = { 0x10, 0x18, 0x1C, 0x1E, 0x1C, 0x18, 0x10 },
    [SN64_MAIN_MAPPING]   = { 0x1C, 0x1C, 0x7F, 0x7F, 0x7F, 0x1C, 0x1C },
    [SN64_MAIN_SETTINGS]  = { 0x10, 0x7F, 0x10, 0x00, 0x04, 0x7F, 0x04 },
    [SN64_MAIN_POWER_OFF] = { 0x08, 0x2A, 0x49, 0x41, 0x41, 0x22, 0x1C },
};

static void sign(const sn64_canvas_t *c, int x, int y, int which, uint16_t ink)
{
    for (int row = 0; row < 7; row++)
        for (int col = 0; col < 7; col++)
            if (signs[which][row] & (0x40 >> col))
                sn64_pad_fill(c, x + col, y + row, x + col, y + row, ink);
}

static int row_y(int row)
{
    return SN64_MENU_ROWS_Y + row * SN64_MENU_ROW_H;
}

// The panel the rows stand on, centred on the screen.
static void panel(const sn64_canvas_t *c, const sn64_theme_t *t, int rows)
{
    sn64_pad_round(c, SN64_MENU_PANEL_X0, SN64_MENU_ROWS_Y - 4, SN64_MENU_PANEL_X1, row_y(rows) + 1, 6, t->panel);
}

// The bar behind the row under the cursor.
static void bar(const sn64_canvas_t *c, const sn64_theme_t *t, int row)
{
    sn64_pad_round(c, SN64_MENU_BAR_X0, row_y(row), SN64_MENU_BAR_X1, row_y(row) + SN64_MENU_ROW_H - 3, 4, t->bar);
}

// A small triangle, 4 wide and 7 high, pointing left or right: the Theme row's sign that Left
// and Right change it.
static void triangle(const sn64_canvas_t *c, int x, int y, bool right, uint16_t colour)
{
    for (int i = 0; i < 4; i++) {
        int col = right ? x + i : x + 3 - i;
        sn64_pad_fill(c, col, y + i, col, y + 6 - i, colour);
    }
}

// The lines under the rows: the message, then the standing warnings.
static void lines_under(sn64_text_fn text, void *ctx, const sn64_theme_t *t, const sn64_menu_view_t *v, int y)
{
    if (v->message && v->message[0])
        text(ctx, SN64_MENU_X, y, v->message_bad ? t->warn : t->text, v->message);
    for (int i = 0; i < 2; i++)
        if (v->warning[i])
            text(ctx, SN64_MENU_X, y + 12 + i * 10, t->warn, v->warning[i]);
}

// What the buttons do, at the bottom: the D-pad, A and, where there is a way back, B, each as
// its small picture.
static void hints(const sn64_canvas_t *c, sn64_text_fn text, void *ctx, const sn64_theme_t *t, bool back)
{
    const int y = 228;
    sn64_pad_icon_dpad(c, SN64_MENU_X, y - 2, 0);
    text(ctx, SN64_MENU_X + 14, y, t->dim, "select");
    sn64_pad_icon_input(c, SN64_MENU_X + 72, y - 2, SN64_IN_A, false);
    text(ctx, SN64_MENU_X + 86, y, t->dim, "choose");
    if (back) {
        sn64_pad_icon_input(c, SN64_MENU_X + 144, y - 2, SN64_IN_B, false);
        text(ctx, SN64_MENU_X + 158, y, t->dim, "back");
    }
}

void sn64_menu_draw_main(const sn64_canvas_t *c, sn64_text_fn text, void *ctx, const sn64_theme_t *t,
                         const sn64_menu_view_t *v)
{
    static const char *const names[SN64_MAIN_ITEMS] = { "Play", "Controller mapping", "Settings", "Power off cartridge" };
    sn64_menu_clear(c, t);
    sn64_menu_title(c, t, true);
    if (v->head)
        text(ctx, SN64_MENU_X, SN64_MENU_HEAD_Y, v->head_bad ? t->warn : t->dim, v->head);
    panel(c, t, SN64_MAIN_ITEMS);
    for (int i = 0; i < SN64_MAIN_ITEMS; i++) {
        bool at = i == v->cursor;
        int y = row_y(i), cx = SN64_MENU_X + 6, cy = y + 8;
        if (at)
            bar(c, t, i);
        // the mark: a round button in one of the logo's four colours, with a white line round
        // it on the row under the cursor, as a button of the controller pictures has when it is lit
        sn64_pad_disc(c, cx, cy, 7, at ? MARK_LIT : MARK_EDGE);
        sn64_pad_disc(c, cx, cy, 6, logo_colours[i]);
        sign(c, cx - 3, cy - 3, i, i == SN64_MAIN_SETTINGS ? INK_DARK : INK_LIGHT);
        text(ctx, SN64_MENU_TEXT_X, y + 5, at ? t->hi : t->text, names[i]);
    }
    lines_under(text, ctx, t, v, row_y(SN64_MAIN_ITEMS) + SN64_MENU_UNDER);
    // how the menu is reached from a game: the four C buttons as their small pictures
    {
        const int y = 212;
        text(ctx, SN64_MENU_X, y, t->dim, "In a game:");
        for (int i = 0; i < 4; i++)
            sn64_pad_icon_input(c, SN64_MENU_X + 84 + i * 12, y - 2, SN64_IN_C_UP + i, false);
        text(ctx, SN64_MENU_X + 136, y, t->dim, "= menu");
    }
    hints(c, text, ctx, t, false);
}

void sn64_menu_draw_settings(const sn64_canvas_t *c, sn64_text_fn text, void *ctx, const sn64_theme_t *t,
                             const sn64_menu_view_t *v, bool compat, unsigned theme_index)
{
    char label[SN64_SET_ITEMS][32];
    snprintf(label[SN64_SET_COMPAT], sizeof label[0], "Compatibility mode: %s", compat ? "ON" : "off");
    snprintf(label[SN64_SET_THEME], sizeof label[0], "Theme: %s", sn64_theme(theme_index)->name);
    snprintf(label[SN64_SET_STATUS], sizeof label[0], "Status / diagnostics");
    snprintf(label[SN64_SET_CREDITS], sizeof label[0], "Credits");
    snprintf(label[SN64_SET_ABOUT], sizeof label[0], "About");
    sn64_menu_clear(c, t);
    sn64_menu_title(c, t, true);
    if (v->head)
        text(ctx, SN64_MENU_X, SN64_MENU_HEAD_Y, v->head_bad ? t->warn : t->hi, v->head);
    panel(c, t, SN64_SET_ITEMS);
    for (int i = 0; i < SN64_SET_ITEMS; i++) {
        bool at = i == v->cursor;
        int y = row_y(i);
        if (at)
            bar(c, t, i);
        sn64_pad_disc(c, SN64_MENU_X + 6, y + 8, 2, at ? t->hi : t->dim);
        text(ctx, SN64_MENU_TEXT_X, y + 5, at ? t->hi : t->text, label[i]);
        if (at && i == SN64_SET_THEME) {        // Left and Right go through the themes
            triangle(c, SN64_MENU_BAR_X1 - 19, y + 5, false, t->hi);
            triangle(c, SN64_MENU_BAR_X1 - 10, y + 5, true, t->hi);
        }
    }
    lines_under(text, ctx, t, v, row_y(SN64_SET_ITEMS) + SN64_MENU_UNDER);
    hints(c, text, ctx, t, true);
}

// ---- About

void sn64_menu_about(const sn64_about_t *a, char text[SN64_ABOUT_LINES][SN64_ABOUT_COLUMNS + 1],
                     uint8_t kind[SN64_ABOUT_LINES])
{
    static const char *const tv[3] = { "PAL, 50 Hz", "NTSC, 60 Hz", "M-PAL, 60 Hz" };
    const size_t n = SN64_ABOUT_COLUMNS + 1;
    for (int i = 0; i < SN64_ABOUT_LINES; i++) {
        text[i][0] = 0;
        kind[i] = SN64_LINE_TEXT;
    }
    snprintf(text[0], n, "About");
    kind[0] = SN64_LINE_HI;
    snprintf(text[2], n, "%s", a->credit);
    snprintf(text[3], n, "%s", a->source);
    kind[3] = SN64_LINE_DIM;
    snprintf(text[5], n, "Menu program   v%s", a->menu_version);
    if (a->present) {
        snprintf(text[6], n, "SN64 build     %u.%u (0x%04X)", (unsigned)(a->version >> 8), (unsigned)(a->version & 0xFFu),
                 (unsigned)a->version);
        snprintf(text[7], n, "Features       0x%04X", (unsigned)a->features);
    } else {
        // no SN64 answered: say so, and what was read where its name should be
        snprintf(text[6], n, "SN64 build     not found (%04X)", (unsigned)a->magic);
        kind[6] = SN64_LINE_WARN;
        snprintf(text[7], n, "Features       -");
        kind[7] = SN64_LINE_DIM;
    }
    snprintf(text[8], n, "Console        %s", a->tv < 3 ? tv[a->tv] : "?");
    snprintf(text[10], n, "Code           GPL-3.0-or-later");
    snprintf(text[11], n, "Hardware, docs CERN-OHL-S-2.0");
    snprintf(text[13], n, "No warranty. Not affiliated with or");
    snprintf(text[14], n, "endorsed by Nintendo or ModRetro.");
    kind[13] = kind[14] = SN64_LINE_DIM;
}
