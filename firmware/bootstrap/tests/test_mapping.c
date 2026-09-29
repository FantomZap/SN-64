// SPDX-License-Identifier: GPL-3.0-or-later
// Host unit test for the default N64 -> SNES mapping (src/sn64_mapping.c).
// Build with -DSN64_FAULT_SWAP_AB to inject a wrong table; the test must fail.
#include <stdio.h>
#include <string.h>

#include "sn64_mapping.h"
#include "sn64_mailbox.h"

static int checks, failures;

static void expect_map(const sn64_map_t *m, const char *what, uint16_t n64, int sx, int sy, uint16_t want)
{
    uint16_t got = sn64_map_buttons(m, n64, (int8_t)sx, (int8_t)sy);
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL %-34s N64 %04X stick(%d,%d) -> SNES %04X, want %04X\n", what, n64, sx, sy, got, want);
    }
}

int main(void)
{
    sn64_map_t m;
    sn64_map_default(&m);

    // SNES image bit order contract (bit 0 = B ... bit 11 = R).
    checks++;
    if (!(SNES_BTN_B == 1u << 0 && SNES_BTN_Y == 1u << 1 && SNES_BTN_SELECT == 1u << 2 &&
          SNES_BTN_START == 1u << 3 && SNES_BTN_UP == 1u << 4 && SNES_BTN_DOWN == 1u << 5 &&
          SNES_BTN_LEFT == 1u << 6 && SNES_BTN_RIGHT == 1u << 7 && SNES_BTN_A == 1u << 8 &&
          SNES_BTN_X == 1u << 9 && SNES_BTN_L == 1u << 10 && SNES_BTN_R == 1u << 11)) {
        failures++;
        printf("  FAIL SNES bit order\n");
    }

    // Specified mappings.
    expect_map(&m, "D-Up -> Up",           N64_BTN_D_UP,    0, 0, SNES_BTN_UP);
    expect_map(&m, "D-Down -> Down",       N64_BTN_D_DOWN,  0, 0, SNES_BTN_DOWN);
    expect_map(&m, "D-Left -> Left",       N64_BTN_D_LEFT,  0, 0, SNES_BTN_LEFT);
    expect_map(&m, "D-Right -> Right",     N64_BTN_D_RIGHT, 0, 0, SNES_BTN_RIGHT);
    expect_map(&m, "Start -> Start",       N64_BTN_START,   0, 0, SNES_BTN_START);
    expect_map(&m, "Z -> Select",          N64_BTN_Z,       0, 0, SNES_BTN_SELECT);
    // Proposed defaults.
    expect_map(&m, "A -> B",               N64_BTN_A,       0, 0, SNES_BTN_B);
    expect_map(&m, "B -> Y",               N64_BTN_B,       0, 0, SNES_BTN_Y);
    expect_map(&m, "C-Up -> X",            N64_BTN_C_UP,    0, 0, SNES_BTN_X);
    expect_map(&m, "C-Right -> A",         N64_BTN_C_RIGHT, 0, 0, SNES_BTN_A);
    expect_map(&m, "C-Down -> B",          N64_BTN_C_DOWN,  0, 0, SNES_BTN_B);
    expect_map(&m, "C-Left -> Y",          N64_BTN_C_LEFT,  0, 0, SNES_BTN_Y);
    expect_map(&m, "L -> L",               N64_BTN_L,       0, 0, SNES_BTN_L);
    expect_map(&m, "R -> R",               N64_BTN_R,       0, 0, SNES_BTN_R);
    // Combinations, stick and sanitising.
    expect_map(&m, "nothing pressed",      0,               0, 0, 0);
    expect_map(&m, "all buttons, no conflicts cancel",
               0xFFFF & ~(N64_BTN_D_DOWN | N64_BTN_D_RIGHT) & ~0x00C0u, 0, 0,
               SNES_BTN_ALL & ~(SNES_BTN_DOWN | SNES_BTN_RIGHT));
    expect_map(&m, "Up+Down cancel",       N64_BTN_D_UP | N64_BTN_D_DOWN, 0, 0, 0);
    expect_map(&m, "Left+Right cancel",    N64_BTN_D_LEFT | N64_BTN_D_RIGHT | N64_BTN_A, 0, 0, SNES_BTN_B);
    expect_map(&m, "stick up past threshold",    0, 0, 40, SNES_BTN_UP);
    expect_map(&m, "stick up below threshold",   0, 0, 39, 0);
    expect_map(&m, "stick down-left",            0, -80, -80, SNES_BTN_DOWN | SNES_BTN_LEFT);
    expect_map(&m, "stick right",                0, 85, 0, SNES_BTN_RIGHT);
    expect_map(&m, "D-Up + stick down cancel",   N64_BTN_D_UP, 0, -60, 0);
    expect_map(&m, "RST/reserved bits ignored",  0x00C0u, 0, 0, 0);

    // Stick packing for JOY1_STICK = {y, x}.
    checks++;
    if (sn64_pack_stick(-1, 2) != 0x02FF || sn64_pack_stick(5, -128) != 0x8005) {
        failures++;
        printf("  FAIL stick packing %04X %04X\n", sn64_pack_stick(-1, 2), sn64_pack_stick(5, -128));
    }

    // Names used on the mapping screen.
    char buf[40];
    checks++;
    if (strcmp(sn64_snes_mask_name(SNES_BTN_A | SNES_BTN_X, buf, sizeof buf), "A+X") != 0 ||
        strcmp(sn64_snes_mask_name(0, buf, sizeof buf), "-") != 0) {
        failures++;
        printf("  FAIL mask names\n");
    }

    if (failures) {
        printf("FAIL: mapping table, %d of %d checks failed\n", failures, checks);
        return 1;
    }
    printf("PASS: mapping table, %d checks (spec D-pad/Start/Z->Select, proposed face/C/shoulder map, "
           "stick threshold %d, opposing directions cancel)\n", checks, m.stick_threshold);
    return 0;
}
