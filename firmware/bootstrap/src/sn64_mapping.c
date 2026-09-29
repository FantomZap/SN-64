// SPDX-License-Identifier: GPL-3.0-or-later
#include "sn64_mapping.h"

#include <string.h>

// Default mapping.
//  - Specified: D-pad -> D-pad, Start -> Start, Z -> Select.
//  - Proposed: A/B are the thumb's primary pair -> SNES B/Y (the SNES bottom
//    and left face buttons, "jump"/"run" in most games); the C-button diamond
//    is laid out like the SNES diamond (C-Up=X, C-Right=A, C-Down=B,
//    C-Left=Y), so every SNES face button is reachable in its SNES position;
//    L/R shoulders -> L/R. The analog stick also drives the D-pad beyond a
//    threshold (about half of a typical +/-80 stick range).
#ifndef SN64_FAULT_SWAP_AB
#define SN64_DEFAULT_A_TARGET SNES_BTN_B
#define SN64_DEFAULT_B_TARGET SNES_BTN_Y
#else
// Fault injection for the host test: a wrong default table must be caught.
#define SN64_DEFAULT_A_TARGET SNES_BTN_Y
#define SN64_DEFAULT_B_TARGET SNES_BTN_B
#endif

static const sn64_map_entry_t default_entries[SN64_MAP_ENTRIES] = {
    { N64_BTN_A,       SN64_DEFAULT_A_TARGET, "A"       },
    { N64_BTN_B,       SN64_DEFAULT_B_TARGET, "B"       },
    { N64_BTN_Z,       SNES_BTN_SELECT,       "Z"       },
    { N64_BTN_START,   SNES_BTN_START,        "Start"   },
    { N64_BTN_D_UP,    SNES_BTN_UP,           "D-Up"    },
    { N64_BTN_D_DOWN,  SNES_BTN_DOWN,         "D-Down"  },
    { N64_BTN_D_LEFT,  SNES_BTN_LEFT,         "D-Left"  },
    { N64_BTN_D_RIGHT, SNES_BTN_RIGHT,        "D-Right" },
    { N64_BTN_L,       SNES_BTN_L,            "L"       },
    { N64_BTN_R,       SNES_BTN_R,            "R"       },
    { N64_BTN_C_UP,    SNES_BTN_X,            "C-Up"    },
    { N64_BTN_C_DOWN,  SNES_BTN_B,            "C-Down"  },
    { N64_BTN_C_LEFT,  SNES_BTN_Y,            "C-Left"  },
    { N64_BTN_C_RIGHT, SNES_BTN_A,            "C-Right" },
};

void sn64_map_default(sn64_map_t *map)
{
    memcpy(map->entry, default_entries, sizeof(default_entries));
    map->stick_threshold = 40;
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

const char *sn64_snes_mask_name(uint16_t snes_mask, char *buf, unsigned len)
{
    static const char *const names[12] = {
        "B", "Y", "Select", "Start", "Up", "Down", "Left", "Right", "A", "X", "L", "R"
    };
    unsigned pos = 0;
    if (len == 0) return buf;
    buf[0] = '\0';
    if ((snes_mask & SNES_BTN_ALL) == 0) {
        strncpy(buf, "-", len - 1);
        buf[len - 1] = '\0';
        return buf;
    }
    for (unsigned bit = 0; bit < 12; bit++) {
        if (!(snes_mask & (1u << bit))) continue;
        const char *n = names[bit];
        unsigned need = (unsigned)strlen(n) + (pos ? 1u : 0u);
        if (pos + need + 1 > len) break;
        if (pos) buf[pos++] = '+';
        memcpy(buf + pos, n, strlen(n));
        pos += (unsigned)strlen(n);
        buf[pos] = '\0';
    }
    return buf;
}
