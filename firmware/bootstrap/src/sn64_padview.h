// SPDX-License-Identifier: GPL-3.0-or-later
// Controller pictures for the mapping screen (owner, 2026-10-01): the controller in the
// player's hands on the left, the controller the game sees on the right, each with buttons
// that light up, and a small picture of every single button for the mapping list.
//
// The pictures are diagrams in the controllers' real proportions (owner, 2026-10-01: "make
// the graphics closer to the right shapes"): each outline and each button's place follows a
// photograph of the controller lying flat (src/sn64_padshape_data.c, tools/make_padshapes.py).
// They carry no maker's logo or lettering (owner, 2026-10-01: no Nintendo logos on
// anything); the letters on the buttons are this file's own five-by-seven dot letters. The
// controllers that can be chosen are the ones ModRetro lists as working with the M64, which
// include the original Nintendo 64 controller: four have its three-handled shape, two have
// two handles. The body colour only tells the entries apart.
//
// Pure C, no libdragon dependency: everything is drawn into a 16-bit frame buffer (5 bits
// red, 5 green, 5 blue, 1 alpha) and unit-tested on the host (tests/test_padview.c).
#ifndef SN64_PADVIEW_H
#define SN64_PADVIEW_H

#include <stdbool.h>
#include <stdint.h>

#define SN64_PAD_W        140   // a controller picture's box is this wide ...
#define SN64_PAD_INPUT_H  134   // ... this high for the player's controller ...
#define SN64_PAD_SNES_H   68    // ... and this high for the Super NES controller, which is a flat one
#define SN64_ICON         11    // a single button's picture is 11 x 11

typedef struct {
    uint16_t *fb;
    int       width, height;    // pixels that may be written
    int       stride;           // row length in pixels
} sn64_canvas_t;

// The controller in the player's hands. All of them report the same 14 buttons and the
// stick to the console; the choice changes the picture and nothing else.
enum {
    SN64_PAD_N64,           // original Nintendo 64 controller: three handles
    SN64_PAD_M64_PRO,       // ModRetro M64 Pro Controller: three handles
    SN64_PAD_CAPTAIN,       // Hyperkin Captain: three handles
    SN64_PAD_NSO,           // the Nintendo Switch Online N64 controller: three handles
    SN64_PAD_BRAWLER,       // Retro Fighters Brawler64: two handles, two Z triggers
    SN64_PAD_8BITDO,        // 8BitDo 64: two handles, two Z triggers
    SN64_PAD_INPUT_COUNT
};
// The controller the game sees. Both have the same 12 buttons; the colours differ.
enum {
    SN64_PAD_SNES,          // Super NES, North America: purple and lavender buttons
    SN64_PAD_SFC,           // Super Famicom, and the Super NES of the PAL countries: four colours
    SN64_PAD_SNES_COUNT
};

#define SN64_PAD_NAME_MAX 16
const char *sn64_input_pad_name(unsigned which);    // at most SN64_PAD_NAME_MAX characters
const char *sn64_snes_pad_name(unsigned which);

// The player's controller in a SN64_PAD_W x SN64_PAD_INPUT_H box at (x0, y0). `n64_buttons`
// are the buttons held (N64_BTN_*), which light up; the stick's cap moves with the stick and
// lights while `stick_lit` says that the stick is pressing something. `cursor` is the mapping
// entry (SN64_IN_*, or SN64_IN_STICK for the stick) to mark, or -1: it is drawn white while
// `blink` is true.
void sn64_pad_draw_input(const sn64_canvas_t *c, int x0, int y0, unsigned which, uint16_t n64_buttons,
                         int8_t stick_x, int8_t stick_y, bool stick_lit, int cursor, bool blink);

// The controller the game sees, in a SN64_PAD_W x SN64_PAD_SNES_H box. `snes_buttons` light
// up (SNES_BTN_*); `cursor` is a SNES button's bit number to mark, SN64_OUT_DPAD for the
// whole D-pad, or -1.
void sn64_pad_draw_snes(const sn64_canvas_t *c, int x0, int y0, unsigned which, uint16_t snes_buttons,
                        int cursor, bool blink);

// A single button, SN64_ICON pixels square at (x, y): mapping entry `entry` of the player's
// controller (SN64_IN_STICK: the stick), or SNES button bit `snes_bit` (-1: the mark for
// "nothing"). And the whole D-pad, with the arms in `snes_dirs` (SNES_BTN_UP ...) lit.
void sn64_pad_icon_input(const sn64_canvas_t *c, int x, int y, int entry, bool lit);
void sn64_pad_icon_snes(const sn64_canvas_t *c, int x, int y, unsigned which, int snes_bit, bool lit);
void sn64_pad_icon_dpad(const sn64_canvas_t *c, int x, int y, uint16_t snes_dirs);

// Where a button is inside its picture: the rectangle it is drawn in, relative to the box.
// `second` asks for the second Z trigger of a two-handled controller. SN64_IN_STICK gives the
// stick's well. False if there is no such button. For the tests: lighting a button must change that rectangle and nothing else.
typedef struct { int x0, y0, x1, y1; } sn64_box_t;
bool sn64_pad_input_box(unsigned which, int entry, bool second, sn64_box_t *box);
bool sn64_pad_snes_box(int snes_bit, sn64_box_t *box);

// Plain shapes for the screen's own boxes: a filled rectangle and a one-pixel frame (corners
// included), a small triangle pointing down or up (the mark of a drop-down list, and of more
// rows above or below; 5 wide and 3 high) and a small arrow pointing right (5 wide and 5 high).
void sn64_pad_fill(const sn64_canvas_t *c, int x0, int y0, int x1, int y1, uint16_t colour);
void sn64_pad_frame(const sn64_canvas_t *c, int x0, int y0, int x1, int y1, uint16_t colour);
void sn64_pad_mark(const sn64_canvas_t *c, int x, int y, uint16_t colour);
void sn64_pad_mark_up(const sn64_canvas_t *c, int x, int y, uint16_t colour);
void sn64_pad_arrow(const sn64_canvas_t *c, int x, int y, uint16_t colour);
// A filled disc, and a filled rectangle with round corners of radius r.
void sn64_pad_disc(const sn64_canvas_t *c, int x, int y, int r, uint16_t colour);
void sn64_pad_round(const sn64_canvas_t *c, int x0, int y0, int x1, int y1, int r, uint16_t colour);

// 5-5-5-1 colour from 8-bit parts: as a constant for tables, and as a function.
#define SN64_RGB(r, g, b) ((uint16_t)((((r) >> 3) << 11) | (((g) >> 3) << 6) | (((b) >> 3) << 1) | 1u))
static inline uint16_t sn64_rgb(unsigned r, unsigned g, unsigned b)
{
    return SN64_RGB(r, g, b);
}

#endif
