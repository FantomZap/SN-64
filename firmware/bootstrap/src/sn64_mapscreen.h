// SPDX-License-Identifier: GPL-3.0-or-later
// The controller mapping screen (owner, 2026-10-01): the player's controller and the
// controller the game sees side by side, in their real shapes, with buttons that light up
// as they are pressed; a drop-down list over each that names the controller and chooses
// which one is drawn; the mapping as a list with a small picture of each single button,
// every row changeable; and a field that puts the defaults back.
//
// The list stands under the Super NES controller, which is a flat one and leaves the room.
// Its first row is the stick (owner, 2026-10-01: "an input method option for the joystick"):
// what the stick does, and how far it has to be pushed. Then the 14 buttons. It shows ten
// rows and scrolls (owner: "the button list below can be scrollable too if it helps fit
// things"), so the player's controller can be as large as its half of the screen.
//
// Only the D-pad, A and B do anything on this screen, so every other button and the stick
// can be tried freely, and B leaves when it is let go, so it can be seen to light first.
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
#include "sn64_theme.h"

#define SN64_MS_LIST_ROWS  (SN64_MAP_ENTRIES + 1)   // rows of the list: the stick, then the 14 buttons
#define SN64_MS_VISIBLE    10                       // of which this many are on the screen at once
// Cursor rows: the two controller lists on top, the rows of the list (the stick first), the
// reset field after them.
#define SN64_MS_ROW_LISTS  (-1)
#define SN64_MS_ROW_STICK  0
#define SN64_MS_ROW_RESET  SN64_MS_LIST_ROWS

// What is open: nothing, one of the two controller lists, the choices for a button's row, or
// the choices for the stick.
enum { SN64_MS_CLOSED, SN64_MS_LIST_INPUT, SN64_MS_LIST_SNES, SN64_MS_TARGET, SN64_MS_STICK };

typedef struct {
    uint8_t input_pad, snes_pad;    // what the two lists are set to (SN64_PAD_*)
    int8_t  col;                    // which of the two lists the cursor is on, or was on last
    int8_t  row;                    // the cursor: -1 the lists, 0 the stick, 1 .. 14 a button, 15 the reset field
    uint8_t first;                  // the first row of the list on the screen (it scrolls)
    uint8_t open;                   // SN64_MS_*
    int8_t  pick;                   // the highlighted line of what is open
    bool    b_armed;                // B went down with nothing open: letting it go leaves the screen
    bool    restored;               // the defaults were just put back (a note until the next button)
} sn64_mapscreen_t;

// At start-up: what the two lists are set to, the cursor on the first row.
void sn64_mapscreen_init(sn64_mapscreen_t *s, unsigned input_pad, unsigned snes_pad);
// Every time the screen is opened: the cursor on the first row, nothing open. The lists keep
// their settings.
void sn64_mapscreen_open(sn64_mapscreen_t *s);

// One picture's worth of input from controller 1: the buttons that went down since the last
// picture and the ones that came up (N64_BTN_*). Returns true when the screen is left.
bool sn64_mapscreen_input(sn64_mapscreen_t *s, sn64_map_t *map, uint16_t pressed, uint16_t released);

// What the row under the cursor is about (also while its choices are open): a mapping entry
// (SN64_IN_*), SN64_IN_STICK for the stick's row, or -1 on the lists and the reset field.
int sn64_mapscreen_entry(const sn64_mapscreen_t *s);

// Draw the whole screen, 320 x 240, on a screen the caller has cleared to the theme's
// background, in the theme's colours. The text is drawn by the caller (sn64_theme.h).
// `n64_buttons` and the stick are controller 1 as read; `frame` counts pictures (the cursor's
// mark blinks with it).
void sn64_mapscreen_draw(const sn64_mapscreen_t *s, const sn64_map_t *map, const sn64_canvas_t *c,
                         sn64_text_fn text, void *ctx, const sn64_theme_t *t,
                         uint16_t n64_buttons, int8_t stick_x, int8_t stick_y, unsigned frame);

#endif
