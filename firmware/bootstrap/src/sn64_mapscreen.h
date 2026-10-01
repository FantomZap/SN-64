// SPDX-License-Identifier: GPL-3.0-or-later
// The controller mapping screen (owner, 2026-10-01): the player's controller and the
// controller the game sees side by side, with buttons that light up as they are pressed;
// a drop-down list over each to choose which controller is drawn; below them the mapping
// as 14 rows with a small picture of each single button, every row changeable; and a
// field that puts the defaults back.
//
// Only the D-pad, A and B do anything on this screen, so every other button can be tried
// freely, and B leaves when it is let go, so it can be seen to light first.
//
// Pure C, no libdragon dependency: the state, what the buttons do and where everything is
// drawn are unit-tested on the host (tests/test_mapscreen.c), which also writes the screens
// out for the mock-ups. Text is drawn by the caller.
#ifndef SN64_MAPSCREEN_H
#define SN64_MAPSCREEN_H

#include <stdbool.h>
#include <stdint.h>

#include "sn64_mapping.h"
#include "sn64_padview.h"

#define SN64_MS_ROWS       7                // mapping rows in each of the two columns
// Cursor rows: the two lists on top, the seven mapping rows, the reset field below them.
#define SN64_MS_ROW_LISTS  (-1)
#define SN64_MS_ROW_RESET  SN64_MS_ROWS

// What is open: nothing, one of the two controller lists, or the choices for a mapping row.
enum { SN64_MS_CLOSED, SN64_MS_LIST_INPUT, SN64_MS_LIST_SNES, SN64_MS_TARGET };

typedef struct {
    uint8_t input_pad, snes_pad;    // what the two lists are set to (SN64_PAD_*)
    int8_t  col, row;               // the cursor: column 0 or 1, row -1 .. 7
    uint8_t open;                   // SN64_MS_*
    int8_t  pick;                   // the highlighted line of what is open
    bool    b_armed;                // B went down with nothing open: letting it go leaves the screen
    bool    restored;               // the defaults were just put back (a note until the next button)
} sn64_mapscreen_t;

// At start-up: what the two lists are set to, the cursor on the first mapping row.
void sn64_mapscreen_init(sn64_mapscreen_t *s, unsigned input_pad, unsigned snes_pad);
// Every time the screen is opened: the cursor on the first row, nothing open. The lists keep
// their settings.
void sn64_mapscreen_open(sn64_mapscreen_t *s);

// One picture's worth of input from controller 1: the buttons that went down since the last
// picture and the ones that came up (N64_BTN_*). Returns true when the screen is left.
bool sn64_mapscreen_input(sn64_mapscreen_t *s, sn64_map_t *map, uint16_t pressed, uint16_t released);

// The mapping entry under the cursor (also while its choices are open), or -1.
int sn64_mapscreen_entry(const sn64_mapscreen_t *s);

// Text is drawn by the caller: 8 x 8 character cells, the top left corner at (x, y), nothing
// behind the letters.
typedef void (*sn64_text_fn)(void *ctx, int x, int y, uint16_t colour, const char *text);

// Draw the whole screen, 320 x 240, on a screen the caller has cleared. `n64_buttons` and the
// stick are controller 1 as read; `frame` counts pictures (the cursor's mark blinks with it).
void sn64_mapscreen_draw(const sn64_mapscreen_t *s, const sn64_map_t *map, const sn64_canvas_t *c,
                         sn64_text_fn text, void *ctx, uint16_t n64_buttons, int8_t stick_x, int8_t stick_y,
                         unsigned frame);

#endif
