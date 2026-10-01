// SPDX-License-Identifier: GPL-3.0-or-later
// N64 controller -> SNES button image mapping. Pure C, no libdragon
// dependency, so the same code is unit-tested on the host
// (firmware/bootstrap/tests/test_mapping.c).
#ifndef SN64_MAPPING_H
#define SN64_MAPPING_H

#include <stdbool.h>
#include <stdint.h>

// N64 buttons, bit positions of the 16-bit joybus controller status word
// (byte 0 = A B Z Start Up Down Left Right, byte 1 = RST - L R C-Up C-Down
// C-Left C-Right, MSB first). Independent of libdragon's bitfield layout.
#define N64_BTN_A        0x8000u
#define N64_BTN_B        0x4000u
#define N64_BTN_Z        0x2000u
#define N64_BTN_START    0x1000u
#define N64_BTN_D_UP     0x0800u
#define N64_BTN_D_DOWN   0x0400u
#define N64_BTN_D_LEFT   0x0200u
#define N64_BTN_D_RIGHT  0x0100u
#define N64_BTN_L        0x0020u
#define N64_BTN_R        0x0010u
#define N64_BTN_C_UP     0x0008u
#define N64_BTN_C_DOWN   0x0004u
#define N64_BTN_C_LEFT   0x0002u
#define N64_BTN_C_RIGHT  0x0001u
// All four C buttons together: the shortcut that brings up the SN64 menu while a game runs
// (owner, 2026-10-01).
#define N64_BTN_C_ALL    (N64_BTN_C_UP | N64_BTN_C_DOWN | N64_BTN_C_LEFT | N64_BTN_C_RIGHT)

// SNES button image written to JOY1_BUTTONS / JOY2_BUTTONS. Bit order is the
// SNES controller shift order (bit 0 is shifted out first). 1 = pressed.
// Bits 15:12 (controller ID) stay 0 for a standard pad.
#define SNES_BTN_B       0x0001u
#define SNES_BTN_Y       0x0002u
#define SNES_BTN_SELECT  0x0004u
#define SNES_BTN_START   0x0008u
#define SNES_BTN_UP      0x0010u
#define SNES_BTN_DOWN    0x0020u
#define SNES_BTN_LEFT    0x0040u
#define SNES_BTN_RIGHT   0x0080u
#define SNES_BTN_A       0x0100u
#define SNES_BTN_X       0x0200u
#define SNES_BTN_L       0x0400u
#define SNES_BTN_R       0x0800u
#define SNES_BTN_ALL     0x0FFFu
#define SNES_BUTTONS     12

// Table order, which is also the order of the rows on the mapping screen: seven in the left
// column (the face buttons and Z), seven in the right (shoulders, Start, the D-pad).
enum {
    SN64_IN_A, SN64_IN_B, SN64_IN_C_UP, SN64_IN_C_DOWN, SN64_IN_C_LEFT, SN64_IN_C_RIGHT, SN64_IN_Z,
    SN64_IN_L, SN64_IN_R, SN64_IN_START, SN64_IN_D_UP, SN64_IN_D_DOWN, SN64_IN_D_LEFT, SN64_IN_D_RIGHT,
    SN64_MAP_ENTRIES
};

typedef struct {
    uint16_t    n64;        // one N64_BTN_* bit
    uint16_t    snes;       // SNES_BTN_* mask it produces (may be 0 = unmapped)
    const char *n64_name;   // at most 7 characters
} sn64_map_entry_t;

typedef struct {
    sn64_map_entry_t entry[SN64_MAP_ENTRIES];
    int8_t           stick_threshold;   // |stick| >= threshold also presses the D-pad; 0 = off
} sn64_map_t;

// The default table (owner, 2026-10-01): every button to the SNES button of the same name
// (A, B, L, R, Start, the D-pad) and Z to Select. X and Y have no namesake on an N64 pad:
// the C buttons give the SNES diamond in its own positions (C-Up X, C-Left Y, C-Down B,
// C-Right A).
void sn64_map_default(sn64_map_t *map);
bool sn64_map_is_default(const sn64_map_t *map);
// The N64 button (one N64_BTN_* bit) and the name of a table entry; 0 and "" outside the table.
uint16_t    sn64_map_n64_bit(int entry);
const char *sn64_map_n64_name(int entry);

// Map one N64 controller state to a SNES button image. Opposing directions
// (Up+Down, Left+Right), which a real SNES D-pad cannot produce, cancel.
uint16_t sn64_map_buttons(const sn64_map_t *map, uint16_t n64_buttons,
                          int8_t stick_x, int8_t stick_y);

// The menu shortcut is not the game's business: with all four C buttons down, none of them
// is passed on. Returns the buttons to map.
uint16_t sn64_map_strip_menu_chord(uint16_t n64_buttons);

// ---- changing the table (the mapping screen) ----
// What an entry gives: the SNES button's bit number (0 = B ... 11 = R), or -1 for nothing.
int  sn64_map_target(const sn64_map_t *map, int entry);
void sn64_map_set_target(sn64_map_t *map, int entry, int snes_bit);
// The choices in the order the screen offers them: A, B, X, Y, L, R, Start, Select, Up, Down,
// Left, Right, nothing. sn64_map_choice() gives the SNES bit number of choice `index` (-1 for
// nothing, and for an index outside the list); sn64_map_choice_index() goes the other way.
#define SN64_MAP_CHOICES (SNES_BUTTONS + 1)
int  sn64_map_choice(int index);
int  sn64_map_choice_index(int snes_bit);
// The SNES buttons no entry of the table gives (the stick is not counted): a mask.
uint16_t sn64_map_unreachable(const sn64_map_t *map);
// "B", "Y", "Select", ... for a bit number; "nothing" for -1.
const char *sn64_snes_button_name(int snes_bit);

// Short SNES button name list for a mask, e.g. "B" or "A+X"; writes into buf.
const char *sn64_snes_mask_name(uint16_t snes_mask, char *buf, unsigned len);

#endif
