// SPDX-License-Identifier: GPL-3.0-or-later
// N64 controller -> SNES button image mapping. Pure C, no libdragon
// dependency, so the same code is unit-tested on the host
// (firmware/bootstrap/tests/test_mapping.c).
#ifndef SN64_MAPPING_H
#define SN64_MAPPING_H

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

#define SN64_MAP_ENTRIES 14

typedef struct {
    uint16_t    n64;        // one N64_BTN_* bit
    uint16_t    snes;       // SNES_BTN_* mask it produces (may be 0 = unmapped)
    const char *n64_name;
} sn64_map_entry_t;

typedef struct {
    sn64_map_entry_t entry[SN64_MAP_ENTRIES];
    int8_t           stick_threshold;   // |stick| >= threshold also presses the D-pad; 0 = off
} sn64_map_t;

// The default table (see docs/design/n64-bootstrap.md for the rationale).
void sn64_map_default(sn64_map_t *map);

// Map one N64 controller state to a SNES button image. Opposing directions
// (Up+Down, Left+Right), which a real SNES D-pad cannot produce, cancel.
uint16_t sn64_map_buttons(const sn64_map_t *map, uint16_t n64_buttons,
                          int8_t stick_x, int8_t stick_y);

// Short SNES button name list for a mask, e.g. "B" or "A+X"; writes into buf.
const char *sn64_snes_mask_name(uint16_t snes_mask, char *buf, unsigned len);

#endif
