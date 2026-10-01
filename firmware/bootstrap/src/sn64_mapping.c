// SPDX-License-Identifier: GPL-3.0-or-later
#include "sn64_mapping.h"

#include <string.h>

// Default mapping (owner, 2026-10-01): "the normal buttons should be mapped to their
// counterpart on the snes controller and the z button to the select button".
//  - A -> A, B -> B, L -> L, R -> R, Start -> Start, D-pad -> D-pad, Z -> Select.
//  - X and Y have no namesake on an N64 pad. The C-button diamond is laid out like the SNES
//    diamond (C-Up = X, C-Left = Y, C-Down = B, C-Right = A), so every SNES face button is
//    also reachable in its SNES position. The player can change any of it on the mapping screen.
//  - The analog stick also drives the D-pad beyond a threshold (about half of a typical
//    +/-80 stick range).
#ifndef SN64_FAULT_SWAP_AB
#define SN64_DEFAULT_A_TARGET SNES_BTN_A
#define SN64_DEFAULT_B_TARGET SNES_BTN_B
#else
// Fault injection for the host test: a wrong default table must be caught.
#define SN64_DEFAULT_A_TARGET SNES_BTN_B
#define SN64_DEFAULT_B_TARGET SNES_BTN_A
#endif

static const sn64_map_entry_t default_entries[SN64_MAP_ENTRIES] = {
    [SN64_IN_A]       = { N64_BTN_A,       SN64_DEFAULT_A_TARGET, "A"       },
    [SN64_IN_B]       = { N64_BTN_B,       SN64_DEFAULT_B_TARGET, "B"       },
    [SN64_IN_C_UP]    = { N64_BTN_C_UP,    SNES_BTN_X,            "C-Up"    },
    [SN64_IN_C_DOWN]  = { N64_BTN_C_DOWN,  SNES_BTN_B,            "C-Down"  },
    [SN64_IN_C_LEFT]  = { N64_BTN_C_LEFT,  SNES_BTN_Y,            "C-Left"  },
    [SN64_IN_C_RIGHT] = { N64_BTN_C_RIGHT, SNES_BTN_A,            "C-Right" },
    [SN64_IN_Z]       = { N64_BTN_Z,       SNES_BTN_SELECT,       "Z"       },
    [SN64_IN_L]       = { N64_BTN_L,       SNES_BTN_L,            "L"       },
    [SN64_IN_R]       = { N64_BTN_R,       SNES_BTN_R,            "R"       },
    [SN64_IN_START]   = { N64_BTN_START,   SNES_BTN_START,        "Start"   },
    [SN64_IN_D_UP]    = { N64_BTN_D_UP,    SNES_BTN_UP,           "D-Up"    },
    [SN64_IN_D_DOWN]  = { N64_BTN_D_DOWN,  SNES_BTN_DOWN,         "D-Down"  },
    [SN64_IN_D_LEFT]  = { N64_BTN_D_LEFT,  SNES_BTN_LEFT,         "D-Left"  },
    [SN64_IN_D_RIGHT] = { N64_BTN_D_RIGHT, SNES_BTN_RIGHT,        "D-Right" },
};

void sn64_map_default(sn64_map_t *map)
{
    memcpy(map->entry, default_entries, sizeof(default_entries));
    map->stick_threshold = 40;
}

uint16_t sn64_map_n64_bit(int entry)
{
    return (entry >= 0 && entry < SN64_MAP_ENTRIES) ? default_entries[entry].n64 : 0;
}

const char *sn64_map_n64_name(int entry)
{
    return (entry >= 0 && entry < SN64_MAP_ENTRIES) ? default_entries[entry].n64_name : "";
}

bool sn64_map_is_default(const sn64_map_t *map)
{
    for (int i = 0; i < SN64_MAP_ENTRIES; i++)
        if (map->entry[i].snes != default_entries[i].snes)
            return false;
    return true;
}

uint16_t sn64_map_buttons(const sn64_map_t *map, uint16_t n64_buttons,
                          int8_t stick_x, int8_t stick_y)
{
    uint16_t snes = 0;
    for (unsigned i = 0; i < SN64_MAP_ENTRIES; i++)
        if (n64_buttons & map->entry[i].n64)
            snes |= map->entry[i].snes;

    if (map->stick_threshold > 0) {
        int t = map->stick_threshold;
        if (stick_y >=  t) snes |= SNES_BTN_UP;      // N64 stick: +y is up
        if (stick_y <= -t) snes |= SNES_BTN_DOWN;
        if (stick_x <= -t) snes |= SNES_BTN_LEFT;
        if (stick_x >=  t) snes |= SNES_BTN_RIGHT;
    }

    if ((snes & (SNES_BTN_UP | SNES_BTN_DOWN)) == (SNES_BTN_UP | SNES_BTN_DOWN))
        snes &= (uint16_t)~(SNES_BTN_UP | SNES_BTN_DOWN);
    if ((snes & (SNES_BTN_LEFT | SNES_BTN_RIGHT)) == (SNES_BTN_LEFT | SNES_BTN_RIGHT))
        snes &= (uint16_t)~(SNES_BTN_LEFT | SNES_BTN_RIGHT);

    return snes & SNES_BTN_ALL;
}

uint16_t sn64_map_strip_menu_chord(uint16_t n64_buttons)
{
    if ((n64_buttons & N64_BTN_C_ALL) == N64_BTN_C_ALL)
        n64_buttons &= (uint16_t)~N64_BTN_C_ALL;
    return n64_buttons;
}

// ---- changing the table ----

static const char *const snes_names[SNES_BUTTONS] = {
    "B", "Y", "Select", "Start", "Up", "Down", "Left", "Right", "A", "X", "L", "R"
};

// The order the mapping screen offers the choices in: the face buttons, the shoulders,
// Start and Select, the D-pad, then nothing.
static const int8_t offer_order[SN64_MAP_CHOICES] = { 8, 0, 9, 1, 10, 11, 3, 2, 4, 5, 6, 7, -1 };

int sn64_map_target(const sn64_map_t *map, int entry)
{
    if (entry < 0 || entry >= SN64_MAP_ENTRIES)
        return -1;
    uint16_t mask = map->entry[entry].snes & SNES_BTN_ALL;
    for (int bit = 0; bit < SNES_BUTTONS; bit++)
        if (mask & (1u << bit))
            return bit;
    return -1;
}

void sn64_map_set_target(sn64_map_t *map, int entry, int snes_bit)
{
    if (entry < 0 || entry >= SN64_MAP_ENTRIES)
        return;
    map->entry[entry].snes = (snes_bit >= 0 && snes_bit < SNES_BUTTONS) ? (uint16_t)(1u << snes_bit) : 0;
}

int sn64_map_choice(int index)
{
    return (index >= 0 && index < SN64_MAP_CHOICES) ? offer_order[index] : -1;
}

int sn64_map_choice_index(int snes_bit)
{
    for (int i = 0; i < SN64_MAP_CHOICES; i++)
        if (offer_order[i] == snes_bit)
            return i;
    return SN64_MAP_CHOICES - 1;                // anything else is "nothing"
}

uint16_t sn64_map_unreachable(const sn64_map_t *map)
{
    uint16_t reach = 0;
    for (int i = 0; i < SN64_MAP_ENTRIES; i++)
        reach |= map->entry[i].snes;
    return (uint16_t)(SNES_BTN_ALL & ~reach);
}

const char *sn64_snes_button_name(int snes_bit)
{
    return (snes_bit >= 0 && snes_bit < SNES_BUTTONS) ? snes_names[snes_bit] : "nothing";
}

const char *sn64_snes_mask_name(uint16_t snes_mask, char *buf, unsigned len)
{
    unsigned pos = 0;
    if (len == 0) return buf;
    buf[0] = '\0';
    if ((snes_mask & SNES_BTN_ALL) == 0) {
        strncpy(buf, "-", len - 1);
        buf[len - 1] = '\0';
        return buf;
    }
    for (unsigned bit = 0; bit < SNES_BUTTONS; bit++) {
        if (!(snes_mask & (1u << bit))) continue;
        const char *n = snes_names[bit];
        unsigned need = (unsigned)strlen(n) + (pos ? 1u : 0u);
        if (pos + need + 1 > len) break;
        if (pos) buf[pos++] = '+';
        memcpy(buf + pos, n, strlen(n));
        pos += (unsigned)strlen(n);
        buf[pos] = '\0';
    }
    return buf;
}
