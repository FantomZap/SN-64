// SPDX-License-Identifier: GPL-3.0-or-later
// Colour themes of the boot menu (owner, 2026-10-01: "We need some stylization I think.
// Maybe make a few themes?"). A theme is a set of colours; every screen of the menu takes
// its colours from the one that is chosen (Settings, Theme). The controller pictures and
// the single-button pictures keep their own colours in every theme: they show real things.
//
// All six are dark, so the logo's light ring and letters and the controller pictures stand
// out on each. Pure C, no libdragon dependency; tests/test_menuview.c checks that every
// theme can be read (text against its backgrounds) and that no two look alike.
#ifndef SN64_THEME_H
#define SN64_THEME_H

#include <stdint.h>

typedef struct {
    const char *name;           // at most SN64_THEME_NAME_MAX characters
    uint16_t bg;                // the screen
    uint16_t panel;             // behind a block of choices
    uint16_t bar;               // behind the row the cursor is on
    uint16_t box;               // inside a list box or a field
    uint16_t text, dim, hi;     // text, less important text, titles and the row under the cursor
    uint16_t warn;              // refusals and warnings
    uint16_t ink;               // the ring and the letters of the logo
} sn64_theme_t;

#define SN64_THEMES          6
#define SN64_THEME_NAME_MAX  9
#define SN64_THEME_DEFAULT   0

// Theme `index`; the first one for an index outside the list.
const sn64_theme_t *sn64_theme(unsigned index);

// Text is drawn by the caller of the screen code: 8 x 8 character cells, the top left corner
// at (x, y), nothing behind the letters.
typedef void (*sn64_text_fn)(void *ctx, int x, int y, uint16_t colour, const char *text);

#endif
