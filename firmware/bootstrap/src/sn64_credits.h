// SPDX-License-Identifier: GPL-3.0-or-later
// Credits roll of the boot menu (owner, 2026-10-01): everyone the repository credits, then the
// SN64 crew, the cats last. The text is CREDITS.md put on the screen: sn64_credits_data.c is
// generated from it by tools/make_credits.py, so the two cannot drift apart.
//
// The text rises from the bottom of the screen, a line at a time into view, and stops with its
// last line in the middle. This file holds only where each line stands for a given scroll
// position: pure C, no libdragon dependency, unit-tested on the host (tests/test_credits.c).
#ifndef SN64_CREDITS_H
#define SN64_CREDITS_H

#define SN64_CREDITS_COLUMNS 36     // two short of the menu's 38 (8-pixel cells from x = 16 on a 320-pixel
                                    // screen): no name stands at the very edge, where a television may cut it
#define SN64_CREDITS_ROW_PX  10     // line spacing, as the rest of the menu
#define SN64_CREDITS_CELL_PX 8      // height of a character

// What a line of the roll is; the screen colours it by that.
typedef enum {
    SN64_CREDIT_TEXT,       // the thank-you paragraph, and empty lines
    SN64_CREDIT_TITLE,      // the credit line and the section titles
    SN64_CREDIT_PROJECT,    // a project's name; also the source location
    SN64_CREDIT_PEOPLE,     // who made it
    SN64_CREDIT_CREW        // the SN64 crew, at the very end
} sn64_credit_kind_t;

extern const char *const sn64_credits_lines[];
extern const unsigned char sn64_credits_kind[];     // sn64_credit_kind_t per line
extern const int sn64_credits_count;

// The lines to draw at scroll position `scroll` (pixels risen) inside a window from `top` to
// `bottom` (pixels, bottom exclusive). Fills `line` (index into sn64_credits_lines) and `y`
// (top pixel of the line) for up to `max` lines, top to bottom, and returns how many. Only
// lines that lie wholly inside the window are returned: the console's text drawing does not
// clip. Empty lines are left out.
int sn64_credits_visible(int scroll, int top, int bottom, int line[], int y[], int max);

// The scroll position at which the roll stops: its last line in the middle of the window.
int sn64_credits_end(int top, int bottom);

#endif
