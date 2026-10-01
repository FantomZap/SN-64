// SPDX-License-Identifier: GPL-3.0-or-later
#include "sn64_padview.h"

#include <stddef.h>

#include "sn64_mapping.h"

// ---- colours

typedef struct { uint8_t r, g, b; } rgb_t;

#define RGB_WHITE      { 255, 255, 255 }
#define RGB_EDGE       {  20,  22,  32 }    // the dark line round a button at rest
#define RGB_INK_DARK   {  24,  24,  32 }
#define RGB_INK_LIGHT  { 244, 244, 250 }
#define RGB_GLOW       { 255, 224,  96 }    // a grey control when it is lit
#define RGB_TAB        { 124, 128, 142 }    // shoulder buttons and triggers
#define RGB_CROSS      {  58,  60,  70 }    // a D-pad, the well of the stick
#define RGB_CAP        { 204, 204, 212 }    // the stick's cap
#define RGB_ICON_DIM   {  88,  92, 108 }    // the part of a small picture that is not meant
#define RGB_ICON_ON    { 212, 212, 220 }    // the part that is

static uint16_t px(rgb_t c)
{
    return sn64_rgb(c.r, c.g, c.b);
}

static bool is_light(rgb_t c)
{
    return (2u * c.r + 5u * c.g + c.b) / 8u > 150u;
}

// ---- plain shapes, clipped to the canvas

static void span(const sn64_canvas_t *c, int x0, int x1, int y, uint16_t colour)
{
    if (y < 0 || y >= c->height) return;
    if (x0 < 0) x0 = 0;
    if (x1 >= c->width) x1 = c->width - 1;
    uint16_t *p = c->fb + (long)y * c->stride + x0;
    for (int n = x1 - x0 + 1; n > 0; n--)
        *p++ = colour;
}

void sn64_pad_fill(const sn64_canvas_t *c, int x0, int y0, int x1, int y1, uint16_t colour)
{
    for (int y = y0; y <= y1; y++)
        span(c, x0, x1, y, colour);
}

void sn64_pad_frame(const sn64_canvas_t *c, int x0, int y0, int x1, int y1, uint16_t colour)
{
    span(c, x0, x1, y0, colour);
    span(c, x0, x1, y1, colour);
    for (int y = y0 + 1; y < y1; y++) {
        span(c, x0, x0, y, colour);
        span(c, x1, x1, y, colour);
    }
}

void sn64_pad_mark(const sn64_canvas_t *c, int x, int y, uint16_t colour)
{
    for (int i = 0; i < 3; i++)
        span(c, x + i, x + 4 - i, y + i, colour);
}

void sn64_pad_arrow(const sn64_canvas_t *c, int x, int y, uint16_t colour)
{
    span(c, x + 2, x + 2, y, colour);
    span(c, x + 3, x + 3, y + 1, colour);
    span(c, x, x + 4, y + 2, colour);
    span(c, x + 3, x + 3, y + 3, colour);
    span(c, x + 2, x + 2, y + 4, colour);
}

// Half the width of a disc of radius r on the row dy away from its middle, or -1 outside it.
static int disc_half(int r, int dy)
{
    int lim = r * r + r - dy * dy;
    int dx = 0;
    if (lim < 0) return -1;
    while ((dx + 1) * (dx + 1) <= lim) dx++;
    return dx;
}

static void disc(const sn64_canvas_t *c, int x, int y, int r, uint16_t colour)
{
    for (int dy = -r; dy <= r; dy++) {
        int h = disc_half(r, dy);
        if (h >= 0) span(c, x - h, x + h, y + dy, colour);
    }
}

static void round_rect(const sn64_canvas_t *c, int x0, int y0, int x1, int y1, int r, uint16_t colour)
{
    for (int y = y0; y <= y1; y++) {
        int in = 0;
        if (y - y0 < r)      in = r - disc_half(r, r - (y - y0));
        else if (y1 - y < r) in = r - disc_half(r, r - (y1 - y));
        span(c, x0 + in, x1 - in, y, colour);
    }
}

// A line with round ends: a disc every three pixels or so along it.
static void thick_line(const sn64_canvas_t *c, int x0, int y0, int x1, int y1, int r, uint16_t colour)
{
    int len = (x1 > x0 ? x1 - x0 : x0 - x1) + (y1 > y0 ? y1 - y0 : y0 - y1);
    int steps = len / 3 + 1;
    for (int i = 0; i <= steps; i++)
        disc(c, x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps, r, colour);
}

// Five-by-seven dot letters and arrows for the buttons, one row per byte, the left column in bit 4.
enum { G_A, G_B, G_X, G_Y, G_L, G_R, G_Z, G_UP, G_DOWN, G_LEFT, G_RIGHT, G_NONE };

static const uint8_t glyph_rows[G_NONE][7] = {
    [G_A]     = { 0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11 },
    [G_B]     = { 0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E },
    [G_X]     = { 0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11 },
    [G_Y]     = { 0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04 },
    [G_L]     = { 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F },
    [G_R]     = { 0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11 },
    [G_Z]     = { 0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F },
    [G_UP]    = { 0x00, 0x00, 0x04, 0x0E, 0x1F, 0x00, 0x00 },
    [G_DOWN]  = { 0x00, 0x00, 0x1F, 0x0E, 0x04, 0x00, 0x00 },
    [G_LEFT]  = { 0x00, 0x02, 0x06, 0x0E, 0x06, 0x02, 0x00 },
    [G_RIGHT] = { 0x00, 0x08, 0x0C, 0x0E, 0x0C, 0x08, 0x00 },
};

static void glyph(const sn64_canvas_t *c, int x, int y, int g, uint16_t ink)
{
    if (g < 0 || g >= G_NONE) return;
    for (int row = 0; row < 7; row++)
        for (int col = 0; col < 5; col++)
            if (glyph_rows[g][row] & (0x10 >> col))
                span(c, x + col, x + col, y + row, ink);
}

// ---- controls

enum { K_DISC, K_TAB, K_ARM, K_CAPSULE };

typedef struct { uint16_t face, edge, ink; } look_t;

// A control at rest, lit (held: its bright colour and a white line round it) or marked by the
// cursor (white).
static look_t look(rgb_t rest, rgb_t lit_colour, bool lit, bool marked)
{
    static const rgb_t white = RGB_WHITE, edge = RGB_EDGE, dark = RGB_INK_DARK, pale = RGB_INK_LIGHT;
    rgb_t f = marked ? white : lit ? lit_colour : rest;
    look_t l = { px(f), px(lit ? white : edge), px(is_light(f) ? dark : pale) };
    return l;
}

static void draw_disc(const sn64_canvas_t *c, int x, int y, int r, int g, look_t l)
{
    disc(c, x, y, r + 1, l.edge);
    disc(c, x, y, r, l.face);
    glyph(c, x - 2, y - 3, g, l.ink);
}

// A shoulder button or a trigger: a bar nine high with its letter.
static void draw_tab(const sn64_canvas_t *c, int x, int y, int half, int g, look_t l)
{
    round_rect(c, x - half - 1, y - 5, x + half + 1, y + 5, 3, l.edge);
    round_rect(c, x - half, y - 4, x + half, y + 4, 2, l.face);
    glyph(c, x - 2, y - 3, g, l.ink);
}

// Select or Start of a Super NES controller: a short slanted bar.
static void draw_capsule(const sn64_canvas_t *c, int x, int y, look_t l)
{
    thick_line(c, x - 3, y + 2, x + 3, y - 2, 3, l.edge);
    thick_line(c, x - 3, y + 2, x + 3, y - 2, 2, l.face);
}

// The four arms of a D-pad as rectangles: seven wide and `len` long round a 7 x 7 middle.
static sn64_box_t arm_box(int cx, int cy, int len, int dir)
{
    sn64_box_t b;
    switch (dir) {
    case G_UP:   b = (sn64_box_t){ cx - 3, cy - 3 - len, cx + 3, cy - 4 }; break;
    case G_DOWN: b = (sn64_box_t){ cx - 3, cy + 4, cx + 3, cy + 3 + len }; break;
    case G_LEFT: b = (sn64_box_t){ cx - 3 - len, cy - 3, cx - 4, cy + 3 }; break;
    default:     b = (sn64_box_t){ cx + 4, cy - 3, cx + 3 + len, cy + 3 }; break;
    }
    return b;
}

static void draw_cross(const sn64_canvas_t *c, int cx, int cy, int len)
{
    static const rgb_t face = RGB_CROSS, edge = RGB_EDGE;
    sn64_pad_fill(c, cx - 4, cy - 4 - len, cx + 4, cy + 4 + len, px(edge));
    sn64_pad_fill(c, cx - 4 - len, cy - 4, cx + 4 + len, cy + 4, px(edge));
    sn64_pad_fill(c, cx - 3, cy - 3 - len, cx + 3, cy + 3 + len, px(face));
    sn64_pad_fill(c, cx - 3 - len, cy - 3, cx + 3 + len, cy + 3, px(face));
}

static void draw_arm(const sn64_canvas_t *c, int cx, int cy, int len, int dir, bool lit, bool marked)
{
    static const rgb_t white = RGB_WHITE, glow = RGB_GLOW;
    if (!lit && !marked) return;
    sn64_box_t b = arm_box(cx, cy, len, dir);
    sn64_pad_fill(c, b.x0, b.y0, b.x1, b.y1, px(marked ? white : glow));
}

// The stick: a dark well and a cap that moves with the stick, three pixels at a full throw.
static void draw_stick(const sn64_canvas_t *c, int x, int y, int r, int8_t sx, int8_t sy)
{
    static const rgb_t well = RGB_CROSS, edge = RGB_EDGE, cap = RGB_CAP;
    int dx = sx * 3 / 80, dy = -(sy * 3 / 80);      // the N64 stick: +y is up; a full throw is about 80
    if (dx > 3) dx = 3;
    if (dx < -3) dx = -3;
    if (dy > 3) dy = 3;
    if (dy < -3) dy = -3;
    disc(c, x, y, r + 1, px(edge));
    disc(c, x, y, r, px(well));
    disc(c, x + dx, y + dy, r - 3, px(cap));
}

// The body of a controller: discs, bars with round ends and rectangles, all in one colour.
// A dark body gets a lighter line round it first (everything one pixel bigger), so its shape
// stands out on the dark screen; a light body does not need one.
enum { S_DISC, S_LINE, S_RECT };
typedef struct { uint8_t kind, x0, y0, x1, y1, r; } shape_t;

static void draw_body(const sn64_canvas_t *c, int ox, int oy, const shape_t *s, int n, rgb_t tint)
{
    rgb_t rim = { (uint8_t)(tint.r + (255 - tint.r) / 2), (uint8_t)(tint.g + (255 - tint.g) / 2),
                  (uint8_t)(tint.b + (255 - tint.b) / 2) };
    for (int pass = is_light(tint) ? 1 : 0; pass < 2; pass++) {
        int g = pass ? 0 : 1;
        uint16_t col = px(pass ? tint : rim);
        for (int i = 0; i < n; i++) {
            switch (s[i].kind) {
            case S_DISC:
                disc(c, ox + s[i].x0, oy + s[i].y0, s[i].r + g, col);
                break;
            case S_LINE:
                thick_line(c, ox + s[i].x0, oy + s[i].y0, ox + s[i].x1, oy + s[i].y1, s[i].r + g, col);
                break;
            default:
                round_rect(c, ox + s[i].x0 - g, oy + s[i].y0 - g, ox + s[i].x1 + g, oy + s[i].y1 + g, s[i].r + g, col);
                break;
            }
        }
    }
}

// ---- the player's controller

typedef struct { uint8_t kind, glyph; rgb_t rest, lit; } control_t;

#define RGB_C_REST  { 216, 176,  32 }
#define RGB_C_LIT   { 255, 246, 150 }

static const control_t input_controls[SN64_MAP_ENTRIES] = {
    [SN64_IN_A]       = { K_DISC, G_A,     {  48,  96, 208 }, { 150, 200, 255 } },
    [SN64_IN_B]       = { K_DISC, G_B,     {  40, 150,  70 }, { 150, 255, 170 } },
    [SN64_IN_C_UP]    = { K_DISC, G_UP,    RGB_C_REST, RGB_C_LIT },
    [SN64_IN_C_DOWN]  = { K_DISC, G_DOWN,  RGB_C_REST, RGB_C_LIT },
    [SN64_IN_C_LEFT]  = { K_DISC, G_LEFT,  RGB_C_REST, RGB_C_LIT },
    [SN64_IN_C_RIGHT] = { K_DISC, G_RIGHT, RGB_C_REST, RGB_C_LIT },
    [SN64_IN_Z]       = { K_TAB,  G_Z,     RGB_TAB, RGB_GLOW },
    [SN64_IN_L]       = { K_TAB,  G_L,     RGB_TAB, RGB_GLOW },
    [SN64_IN_R]       = { K_TAB,  G_R,     RGB_TAB, RGB_GLOW },
    [SN64_IN_START]   = { K_DISC, G_NONE,  { 200,  48,  48 }, { 255, 150, 140 } },
    [SN64_IN_D_UP]    = { K_ARM,  G_UP,    RGB_CROSS, RGB_GLOW },
    [SN64_IN_D_DOWN]  = { K_ARM,  G_DOWN,  RGB_CROSS, RGB_GLOW },
    [SN64_IN_D_LEFT]  = { K_ARM,  G_LEFT,  RGB_CROSS, RGB_GLOW },
    [SN64_IN_D_RIGHT] = { K_ARM,  G_RIGHT, RGB_CROSS, RGB_GLOW },
};

typedef struct { uint8_t x, y, r; } at_t;       // a disc's middle and radius; for a bar, r is half its width

typedef struct {
    at_t    at[SN64_MAP_ENTRIES];               // discs and bars (the D-pad's four entries are not used)
    at_t    z2;                                 // the second Z trigger; r = 0: there is none
    at_t    dpad;                               // the D-pad's middle; r is the length of an arm
    at_t    stick;                              // the stick's well
    uint8_t shapes;
    shape_t body[4];
} input_layout_t;

enum { LAYOUT_THREE_HANDLES, LAYOUT_TWO_HANDLES, LAYOUTS };

static const input_layout_t layouts[LAYOUTS] = {
    [LAYOUT_THREE_HANDLES] = {
        // D-pad on the left wing, the stick on the middle handle with Z behind it, Start in the
        // middle, B and A with the four C buttons on the right wing, L and R on the top edge.
        .at = {
            [SN64_IN_A]       = { 104, 43,  5 },
            [SN64_IN_B]       = {  95, 34,  5 },
            [SN64_IN_C_UP]    = { 115, 18,  4 },
            [SN64_IN_C_DOWN]  = { 115, 34,  4 },
            [SN64_IN_C_LEFT]  = { 107, 26,  4 },
            [SN64_IN_C_RIGHT] = { 123, 26,  4 },
            [SN64_IN_Z]       = {  70, 70,  7 },
            [SN64_IN_L]       = {  34,  9, 12 },
            [SN64_IN_R]       = { 106,  9, 12 },
            [SN64_IN_START]   = {  70, 26,  3 },
        },
        .z2     = { 0, 0, 0 },
        .dpad   = { 31, 31, 8 },
        .stick  = { 70, 49, 8 },
        .shapes = 4,
        .body   = {
            { S_LINE,  24, 42,  17, 70,  9 },   // left handle
            { S_LINE, 116, 42, 123, 70,  9 },   // right handle
            { S_LINE,  70, 42,  70, 74, 11 },   // middle handle
            { S_RECT,  10, 12, 130, 50, 19 },   // the two wings and what is between them
        },
    },
    [LAYOUT_TWO_HANDLES] = {
        // The stick top left with the D-pad below it, the buttons as before on the right, L and
        // R on the top edge and a Z trigger beside each.
        .at = {
            [SN64_IN_A]       = { 100, 46,  5 },
            [SN64_IN_B]       = {  91, 37,  5 },
            [SN64_IN_C_UP]    = { 112, 19,  4 },
            [SN64_IN_C_DOWN]  = { 112, 35,  4 },
            [SN64_IN_C_LEFT]  = { 104, 27,  4 },
            [SN64_IN_C_RIGHT] = { 120, 27,  4 },
            [SN64_IN_Z]       = {  54,  8,  7 },
            [SN64_IN_L]       = {  33,  8, 10 },
            [SN64_IN_R]       = { 106,  8, 10 },
            [SN64_IN_START]   = {  70, 28,  3 },
        },
        .z2     = { 85, 8, 7 },
        .dpad   = { 54, 44, 8 },
        .stick  = { 31, 30, 8 },
        .shapes = 3,
        .body   = {
            { S_LINE,  28, 46,  21, 72, 11 },   // left handle
            { S_LINE, 111, 46, 118, 72, 11 },   // right handle
            { S_RECT,  12, 12, 127, 58, 16 },
        },
    },
};

typedef struct { const char *name; uint8_t layout; rgb_t tint; } input_pad_t;

static const input_pad_t input_pads[SN64_PAD_INPUT_COUNT] = {
    [SN64_PAD_N64]     = { "N64 controller",   LAYOUT_THREE_HANDLES, { 172, 172, 180 } },
    [SN64_PAD_M64_PRO] = { "M64 Pro",          LAYOUT_THREE_HANDLES, { 134, 110, 188 } },
    [SN64_PAD_CAPTAIN] = { "Hyperkin Captain", LAYOUT_THREE_HANDLES, {  84,  88, 104 } },
    [SN64_PAD_NSO]     = { "Switch N64 pad",   LAYOUT_THREE_HANDLES, { 118, 126, 150 } },
    [SN64_PAD_BRAWLER] = { "Brawler64",        LAYOUT_TWO_HANDLES,   { 196,  64,  64 } },
    [SN64_PAD_8BITDO]  = { "8BitDo 64",        LAYOUT_TWO_HANDLES,   { 226, 226, 232 } },
};

const char *sn64_input_pad_name(unsigned which)
{
    return which < SN64_PAD_INPUT_COUNT ? input_pads[which].name : "";
}

void sn64_pad_draw_input(const sn64_canvas_t *c, int x0, int y0, unsigned which, uint16_t n64_buttons,
                         int8_t stick_x, int8_t stick_y, int cursor, bool blink)
{
    if (which >= SN64_PAD_INPUT_COUNT) which = 0;
    const input_pad_t *p = &input_pads[which];
    const input_layout_t *l = &layouts[p->layout];
    draw_body(c, x0, y0, l->body, l->shapes, p->tint);
    draw_cross(c, x0 + l->dpad.x, y0 + l->dpad.y, l->dpad.r);
    draw_stick(c, x0 + l->stick.x, y0 + l->stick.y, l->stick.r, stick_x, stick_y);
    for (int e = 0; e < SN64_MAP_ENTRIES; e++) {
        const control_t *k = &input_controls[e];
        const at_t *a = &l->at[e];
        uint16_t bit = sn64_map_n64_bit(e);
#ifdef SN64_FAULT_PAD_WRONG_BUTTON
        // Fault injection for the host test: A lights where B is and B where A is.
        if (e == SN64_IN_A) bit = N64_BTN_B;
        else if (e == SN64_IN_B) bit = N64_BTN_A;
#endif
        bool lit = (n64_buttons & bit) != 0, marked = blink && cursor == e;
        look_t lk = look(k->rest, k->lit, lit, marked);
        switch (k->kind) {
        case K_DISC:
            draw_disc(c, x0 + a->x, y0 + a->y, a->r, k->glyph, lk);
            break;
        case K_TAB:
            draw_tab(c, x0 + a->x, y0 + a->y, a->r, k->glyph, lk);
            if (e == SN64_IN_Z && l->z2.r)
                draw_tab(c, x0 + l->z2.x, y0 + l->z2.y, l->z2.r, k->glyph, lk);
            break;
        default:
            draw_arm(c, x0 + l->dpad.x, y0 + l->dpad.y, l->dpad.r, k->glyph, lit, marked);
            break;
        }
    }
}

bool sn64_pad_input_box(unsigned which, int entry, bool second, sn64_box_t *box)
{
    if (which >= SN64_PAD_INPUT_COUNT || entry < 0 || entry >= SN64_MAP_ENTRIES)
        return false;
    const input_layout_t *l = &layouts[input_pads[which].layout];
    const control_t *k = &input_controls[entry];
    const at_t *a = &l->at[entry];
    if (second) {
        if (entry != SN64_IN_Z || !l->z2.r)
            return false;
        a = &l->z2;
    }
    switch (k->kind) {
    case K_DISC: *box = (sn64_box_t){ a->x - a->r - 1, a->y - a->r - 1, a->x + a->r + 1, a->y + a->r + 1 }; break;
    case K_TAB:  *box = (sn64_box_t){ a->x - a->r - 1, a->y - 5, a->x + a->r + 1, a->y + 5 }; break;
    default:     *box = arm_box(l->dpad.x, l->dpad.y, l->dpad.r, k->glyph); break;
    }
    return true;
}

// ---- the controller the game sees

typedef struct {
    const char *name;
    rgb_t       rest[4], lit[4];                // A, B, X, Y
} snes_pad_t;

static const snes_pad_t snes_pads[SN64_PAD_SNES_COUNT] = {
    [SN64_PAD_SNES] = { "Super NES",
        { {  96,  68, 164 }, {  96,  68, 164 }, { 164, 148, 212 }, { 164, 148, 212 } },
        { { 208, 180, 255 }, { 208, 180, 255 }, { 240, 232, 255 }, { 240, 232, 255 } } },
    [SN64_PAD_SFC]  = { "Super Famicom",
        { { 208,  48,  56 }, { 224, 184,  40 }, {  48, 104, 208 }, {  40, 152,  80 } },
        { { 255, 156, 150 }, { 255, 244, 150 }, { 150, 200, 255 }, { 150, 255, 170 } } },
};

// By SNES bit number: what it is, its letter or direction, and which of A, B, X, Y it is.
static const struct { uint8_t kind, glyph, face; } snes_controls[SNES_BUTTONS] = {
    { K_DISC,    G_B,     1 },      // B
    { K_DISC,    G_Y,     3 },      // Y
    { K_CAPSULE, G_NONE,  0 },      // Select
    { K_CAPSULE, G_NONE,  0 },      // Start
    { K_ARM,     G_UP,    0 },
    { K_ARM,     G_DOWN,  0 },
    { K_ARM,     G_LEFT,  0 },
    { K_ARM,     G_RIGHT, 0 },
    { K_DISC,    G_A,     0 },      // A
    { K_DISC,    G_X,     2 },      // X
    { K_TAB,     G_L,     0 },      // L
    { K_TAB,     G_R,     0 },      // R
};

static const at_t snes_at[SNES_BUTTONS] = {
    { 106, 66, 6 }, { 93, 53, 6 }, { 61, 58, 0 }, { 75, 58, 0 },
    { 0, 0, 0 }, { 0, 0, 0 }, { 0, 0, 0 }, { 0, 0, 0 },
    { 119, 53, 6 }, { 106, 40, 6 }, { 33, 22, 12 }, { 106, 22, 12 },
};
static const at_t snes_dpad = { 33, 53, 9 };

#define RGB_SNES_TAB      { 150, 152, 166 }
#define RGB_SNES_CAPSULE  {  72,  74,  86 }

const char *sn64_snes_pad_name(unsigned which)
{
    return which < SN64_PAD_SNES_COUNT ? snes_pads[which].name : "";
}

void sn64_pad_draw_snes(const sn64_canvas_t *c, int x0, int y0, unsigned which, uint16_t snes_buttons,
                        int cursor, bool blink)
{
    // Two round ends and a lower middle between them; a darker round under the four buttons.
    static const shape_t shapes[3] = {
        { S_DISC, 33, 53, 0, 0, 27 }, { S_DISC, 106, 53, 0, 0, 27 }, { S_RECT, 33, 33, 106, 71, 0 },
    };
    static const rgb_t grey = { 200, 200, 208 }, under = { 132, 132, 146 };
    static const rgb_t tab = RGB_SNES_TAB, capsule = RGB_SNES_CAPSULE, glow = RGB_GLOW;
    if (which >= SN64_PAD_SNES_COUNT) which = 0;
    const snes_pad_t *p = &snes_pads[which];
    draw_body(c, x0, y0, shapes, 3, grey);
    disc(c, x0 + 106, y0 + 53, 22, px(under));
    draw_cross(c, x0 + snes_dpad.x, y0 + snes_dpad.y, snes_dpad.r);
    for (int bit = 0; bit < SNES_BUTTONS; bit++) {
        const at_t *a = &snes_at[bit];
        bool lit = (snes_buttons & (1u << bit)) != 0, marked = blink && cursor == bit;
        int face = snes_controls[bit].face, g = snes_controls[bit].glyph;
        switch (snes_controls[bit].kind) {
        case K_DISC:
            draw_disc(c, x0 + a->x, y0 + a->y, a->r, g, look(p->rest[face], p->lit[face], lit, marked));
            break;
        case K_TAB:
            draw_tab(c, x0 + a->x, y0 + a->y, a->r, g, look(tab, glow, lit, marked));
            break;
        case K_CAPSULE:
            draw_capsule(c, x0 + a->x, y0 + a->y, look(capsule, glow, lit, marked));
            break;
        default:
            draw_arm(c, x0 + snes_dpad.x, y0 + snes_dpad.y, snes_dpad.r, g, lit, marked);
            break;
        }
    }
}

bool sn64_pad_snes_box(int snes_bit, sn64_box_t *box)
{
    if (snes_bit < 0 || snes_bit >= SNES_BUTTONS)
        return false;
    const at_t *a = &snes_at[snes_bit];
    switch (snes_controls[snes_bit].kind) {
    case K_DISC:    *box = (sn64_box_t){ a->x - a->r - 1, a->y - a->r - 1, a->x + a->r + 1, a->y + a->r + 1 }; break;
    case K_TAB:     *box = (sn64_box_t){ a->x - a->r - 1, a->y - 5, a->x + a->r + 1, a->y + 5 }; break;
    case K_CAPSULE: *box = (sn64_box_t){ a->x - 6, a->y - 5, a->x + 6, a->y + 5 }; break;
    default:        *box = arm_box(snes_dpad.x, snes_dpad.y, snes_dpad.r, snes_controls[snes_bit].glyph); break;
    }
    return true;
}

// ---- single buttons, 11 x 11

// A small D-pad with one arm picked out.
static void icon_cross(const sn64_canvas_t *c, int x, int y, int dir, bool lit)
{
    static const rgb_t dim = RGB_ICON_DIM, on = RGB_ICON_ON, glow = RGB_GLOW;
    uint16_t arm = px(lit ? glow : on);
    sn64_pad_fill(c, x + 4, y, x + 6, y + 10, px(dim));
    sn64_pad_fill(c, x, y + 4, x + 10, y + 6, px(dim));
    switch (dir) {
    case G_UP:   sn64_pad_fill(c, x + 4, y, x + 6, y + 3, arm); break;
    case G_DOWN: sn64_pad_fill(c, x + 4, y + 7, x + 6, y + 10, arm); break;
    case G_LEFT: sn64_pad_fill(c, x, y + 4, x + 3, y + 6, arm); break;
    default:     sn64_pad_fill(c, x + 7, y + 4, x + 10, y + 6, arm); break;
    }
}

// Select and Start side by side as two slanted bars, one of them picked out.
static void icon_capsules(const sn64_canvas_t *c, int x, int y, bool right, bool lit)
{
    static const rgb_t dim = RGB_ICON_DIM, on = RGB_ICON_ON, glow = RGB_GLOW;
    for (int i = 0; i < 2; i++) {
        uint16_t col = px((i == 1) == right ? (lit ? glow : on) : dim);
        int ox = x + i * 5;
        span(c, ox + 3, ox + 4, y + 3, col);
        span(c, ox + 2, ox + 4, y + 4, col);
        span(c, ox + 1, ox + 3, y + 5, col);
        span(c, ox, ox + 2, y + 6, col);
        span(c, ox, ox + 1, y + 7, col);
    }
}

void sn64_pad_icon_input(const sn64_canvas_t *c, int x, int y, int entry, bool lit)
{
    if (entry < 0 || entry >= SN64_MAP_ENTRIES)
        return;
    const control_t *k = &input_controls[entry];
    look_t lk = look(k->rest, k->lit, lit, false);
    switch (k->kind) {
    case K_DISC:
        disc(c, x + 5, y + 5, k->glyph == G_NONE ? 4 : 5, lk.face);     // Start is the small one
        glyph(c, x + 3, y + 2, k->glyph, lk.ink);
        break;
    case K_TAB:
        round_rect(c, x, y + 1, x + 10, y + 9, 2, lk.face);
        glyph(c, x + 3, y + 2, k->glyph, lk.ink);
        break;
    default:
        icon_cross(c, x, y, k->glyph, lit);
        break;
    }
}

void sn64_pad_icon_snes(const sn64_canvas_t *c, int x, int y, unsigned which, int snes_bit, bool lit)
{
    static const rgb_t dim = RGB_ICON_DIM, tab = RGB_SNES_TAB, glow = RGB_GLOW;
    if (which >= SN64_PAD_SNES_COUNT) which = 0;
    if (snes_bit < 0 || snes_bit >= SNES_BUTTONS) {
        sn64_pad_fill(c, x + 3, y + 5, x + 7, y + 5, px(dim));         // nothing: a short dash
        return;
    }
    const snes_pad_t *p = &snes_pads[which];
    int face = snes_controls[snes_bit].face, g = snes_controls[snes_bit].glyph;
    look_t lk;
    switch (snes_controls[snes_bit].kind) {
    case K_DISC:
        lk = look(p->rest[face], p->lit[face], lit, false);
        disc(c, x + 5, y + 5, 5, lk.face);
        glyph(c, x + 3, y + 2, g, lk.ink);
        break;
    case K_TAB:
        lk = look(tab, glow, lit, false);
        round_rect(c, x, y + 1, x + 10, y + 9, 2, lk.face);
        glyph(c, x + 3, y + 2, g, lk.ink);
        break;
    case K_CAPSULE:
        icon_capsules(c, x, y, snes_bit == 3, lit);                    // bit 3 is Start, the right one
        break;
    default:
        icon_cross(c, x, y, g, lit);
        break;
    }
}
