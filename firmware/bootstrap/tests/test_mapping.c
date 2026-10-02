// SPDX-License-Identifier: GPL-3.0-or-later
// Host unit test for the N64 -> SNES mapping (src/sn64_mapping.c): the default table, the
// stick, the cancelling of opposite directions, the menu shortcut, and changing the table as
// the mapping screen does.
// Build with -DSN64_FAULT_SWAP_AB to inject a wrong table; the test must fail.
// Build with -DSN64_FAULT_STICK_AXES (each axis of the stick on its own against the threshold);
// the test must fail.
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

static void expect(int ok, const char *what)
{
    checks++;
    if (!ok) {
        failures++;
        printf("  FAIL %s\n", what);
    }
}

int main(void)
{
    sn64_map_t m;
    sn64_map_default(&m);

    // SNES image bit order contract (bit 0 = B ... bit 11 = R).
    expect(SNES_BTN_B == 1u << 0 && SNES_BTN_Y == 1u << 1 && SNES_BTN_SELECT == 1u << 2 &&
           SNES_BTN_START == 1u << 3 && SNES_BTN_UP == 1u << 4 && SNES_BTN_DOWN == 1u << 5 &&
           SNES_BTN_LEFT == 1u << 6 && SNES_BTN_RIGHT == 1u << 7 && SNES_BTN_A == 1u << 8 &&
           SNES_BTN_X == 1u << 9 && SNES_BTN_L == 1u << 10 && SNES_BTN_R == 1u << 11, "SNES bit order");

    // The owner's defaults: each button to its namesake, Z to Select.
    expect_map(&m, "A -> A",               N64_BTN_A,       0, 0, SNES_BTN_A);
    expect_map(&m, "B -> B",               N64_BTN_B,       0, 0, SNES_BTN_B);
    expect_map(&m, "L -> L",               N64_BTN_L,       0, 0, SNES_BTN_L);
    expect_map(&m, "R -> R",               N64_BTN_R,       0, 0, SNES_BTN_R);
    expect_map(&m, "Start -> Start",       N64_BTN_START,   0, 0, SNES_BTN_START);
    expect_map(&m, "Z -> Select",          N64_BTN_Z,       0, 0, SNES_BTN_SELECT);
    expect_map(&m, "D-Up -> Up",           N64_BTN_D_UP,    0, 0, SNES_BTN_UP);
    expect_map(&m, "D-Down -> Down",       N64_BTN_D_DOWN,  0, 0, SNES_BTN_DOWN);
    expect_map(&m, "D-Left -> Left",       N64_BTN_D_LEFT,  0, 0, SNES_BTN_LEFT);
    expect_map(&m, "D-Right -> Right",     N64_BTN_D_RIGHT, 0, 0, SNES_BTN_RIGHT);
    // X and Y have no namesake: the C diamond is the SNES diamond.
    expect_map(&m, "C-Up -> X",            N64_BTN_C_UP,    0, 0, SNES_BTN_X);
    expect_map(&m, "C-Left -> Y",          N64_BTN_C_LEFT,  0, 0, SNES_BTN_Y);
    expect_map(&m, "C-Down -> B",          N64_BTN_C_DOWN,  0, 0, SNES_BTN_B);
    expect_map(&m, "C-Right -> A",         N64_BTN_C_RIGHT, 0, 0, SNES_BTN_A);
    expect(sn64_map_is_default(&m), "a fresh table is the default");
    {
        uint16_t reach = 0;
        for (int i = 0; i < SN64_MAP_ENTRIES; i++) reach |= m.entry[i].snes;
        expect(reach == SNES_BTN_ALL, "every SNES button can be reached with the default table");
    }
    // Combinations, stick and sanitising.
    expect_map(&m, "nothing pressed",      0,               0, 0, 0);
    expect_map(&m, "all buttons, no conflicts cancel",
               0xFFFF & ~(N64_BTN_D_DOWN | N64_BTN_D_RIGHT) & ~0x00C0u, 0, 0,
               SNES_BTN_ALL & ~(SNES_BTN_DOWN | SNES_BTN_RIGHT));
    expect_map(&m, "Up+Down cancel",       N64_BTN_D_UP | N64_BTN_D_DOWN, 0, 0, 0);
    expect_map(&m, "Left+Right cancel",    N64_BTN_D_LEFT | N64_BTN_D_RIGHT | N64_BTN_A, 0, 0, SNES_BTN_A);
    expect_map(&m, "RST/reserved bits ignored",  0x00C0u, 0, 0, 0);

    // The stick (owner, 2026-10-01): pushed past a set part of its travel it presses the D-pad
    // in the direction it points, two directions at once towards a corner. Half its travel
    // (40 of 80) to begin with.
    expect(m.stick_percent == 50 && SN64_STICK_FULL == 80, "the stick starts at half its travel, a full throw being 80");
    expect_map(&m, "stick up at half its travel",       0, 0, 40, SNES_BTN_UP);
    expect_map(&m, "stick up just short of it",         0, 0, 39, 0);
    expect_map(&m, "stick right at half its travel",    0, 40, 0, SNES_BTN_RIGHT);
    expect_map(&m, "stick left, down",                  0, -40, 0, SNES_BTN_LEFT);
    expect_map(&m, "stick down",                        0, 0, -40, SNES_BTN_DOWN);
    // how far is measured from the middle, the same in every direction
    expect_map(&m, "towards a corner, 41 from the middle",  0, 29, 29, SNES_BTN_UP | SNES_BTN_RIGHT);
    expect_map(&m, "towards a corner, 39.6 from the middle", 0, 28, 28, 0);
    expect_map(&m, "exactly 40 from the middle, off the axes", 0, 24, 32, SNES_BTN_UP | SNES_BTN_RIGHT);
    {
        // a full throw every 5 degrees round the circle: eight equal slices of 45 degrees
        static const struct { int deg, x, y; uint16_t want; } at[] = {
            {   0,  80,   0, SNES_BTN_RIGHT },                   {  20,  75,  27, SNES_BTN_RIGHT },
            {  25,  73,  34, SNES_BTN_RIGHT | SNES_BTN_UP },     {  45,  57,  57, SNES_BTN_RIGHT | SNES_BTN_UP },
            {  65,  34,  73, SNES_BTN_RIGHT | SNES_BTN_UP },     {  70,  27,  75, SNES_BTN_UP },
            {  90,   0,  80, SNES_BTN_UP },                      { 110, -27,  75, SNES_BTN_UP },
            { 115, -34,  73, SNES_BTN_LEFT | SNES_BTN_UP },      { 135, -57,  57, SNES_BTN_LEFT | SNES_BTN_UP },
            { 155, -73,  34, SNES_BTN_LEFT | SNES_BTN_UP },      { 160, -75,  27, SNES_BTN_LEFT },
            { 180, -80,   0, SNES_BTN_LEFT },                    { 200, -75, -27, SNES_BTN_LEFT },
            { 205, -73, -34, SNES_BTN_LEFT | SNES_BTN_DOWN },    { 225, -57, -57, SNES_BTN_LEFT | SNES_BTN_DOWN },
            { 245, -34, -73, SNES_BTN_LEFT | SNES_BTN_DOWN },    { 250, -27, -75, SNES_BTN_DOWN },
            { 270,   0, -80, SNES_BTN_DOWN },                    { 290,  27, -75, SNES_BTN_DOWN },
            { 295,  34, -73, SNES_BTN_RIGHT | SNES_BTN_DOWN },   { 315,  57, -57, SNES_BTN_RIGHT | SNES_BTN_DOWN },
            { 335,  73, -34, SNES_BTN_RIGHT | SNES_BTN_DOWN },   { 340,  75, -27, SNES_BTN_RIGHT },
        };
        int ok = 1;
        for (unsigned i = 0; i < sizeof at / sizeof at[0]; i++)
            if (sn64_map_stick(&m, (int8_t)at[i].x, (int8_t)at[i].y) != at[i].want) {
                ok = 0;
                printf("    stick at %d degrees (%d, %d): %04X, want %04X\n", at[i].deg, at[i].x, at[i].y,
                       sn64_map_stick(&m, (int8_t)at[i].x, (int8_t)at[i].y), at[i].want);
            }
        expect(ok, "round the circle: one direction within 22.5 degrees of an axis, two towards the corners");
    }
    expect_map(&m, "the far corners of the numbers",    0, -128, -128, SNES_BTN_DOWN | SNES_BTN_LEFT);
    expect_map(&m, "and of one axis",                   0, 127, 0, SNES_BTN_RIGHT);
    // the stick and the D-pad together
    expect_map(&m, "D-Up + stick down cancel",          N64_BTN_D_UP, 0, -60, 0);
    expect_map(&m, "D-Right + stick right",             N64_BTN_D_RIGHT, 80, 0, SNES_BTN_RIGHT);
    expect_map(&m, "D-Left + stick up and right",       N64_BTN_D_LEFT, 57, 57, SNES_BTN_UP);
    {
        // how far is far enough: the seven choices, then nothing
        int ok = 1, list = 1;
        for (int i = 0; i < SN64_STICK_CHOICES - 1; i++) {
            unsigned p = sn64_map_stick_choice(i);
            int t = (int)p * SN64_STICK_FULL / 100;
            sn64_map_set_stick(&m, p);
            if (p != 20u + 10u * (unsigned)i || sn64_map_stick_choice_index(p) != i) list = 0;
            if (sn64_map_stick(&m, (int8_t)t, 0) != SNES_BTN_RIGHT || sn64_map_stick(&m, (int8_t)(t - 1), 0) != 0 ||
                sn64_map_stick(&m, 0, (int8_t)-t) != SNES_BTN_DOWN) ok = 0;
        }
        expect(SN64_STICK_CHOICES == 8 && list && sn64_map_stick_choice(7) == 0 && sn64_map_stick_choice_index(0) == 7 &&
               sn64_map_stick_choice(-1) == 0 && sn64_map_stick_choice(8) == 0 && sn64_map_stick_choice_index(55) == 7,
               "the choices are 20, 30 ... 80 percent and nothing");
        expect(ok, "each percentage presses exactly from that part of the travel");
        expect(!sn64_map_is_default(&m), "a changed stick is not the default");
        sn64_map_set_stick(&m, 0);
        expect_map(&m, "the stick set to nothing presses nothing", 0, 127, 127, 0);
        expect_map(&m, "and leaves the buttons alone",             N64_BTN_A, -128, 0, SNES_BTN_A);
        sn64_map_set_stick(&m, 250);
        expect(m.stick_percent == 100, "a percentage out of range is cut to 100");
        sn64_map_default(&m);
        expect(m.stick_percent == 50 && sn64_map_is_default(&m), "the defaults bring the stick back to half");
    }
    // the reading the screen shows: how far the stick is pushed now
    expect(sn64_stick_push(0, 0) == 0 && sn64_stick_push(40, 0) == 50 && sn64_stick_push(24, 32) == 50 &&
           sn64_stick_push(-60, 0) == 75 && sn64_stick_push(80, 0) == 100 && sn64_stick_push(127, 127) == 100 &&
           sn64_stick_push(0, -128) == 100, "how far the stick is pushed, in percent, 100 at most");

    // The menu shortcut: all four C buttons. They are not passed on to the game while all are down.
    expect(sn64_map_strip_menu_chord(N64_BTN_C_ALL | N64_BTN_A) == N64_BTN_A, "all four C down: none of them is passed on");
    expect(sn64_map_strip_menu_chord(N64_BTN_C_ALL & ~N64_BTN_C_LEFT) == (N64_BTN_C_ALL & ~N64_BTN_C_LEFT),
           "three C buttons are ordinary buttons");
    expect(sn64_map_strip_menu_chord(N64_BTN_Z | N64_BTN_L | N64_BTN_R) == (N64_BTN_Z | N64_BTN_L | N64_BTN_R),
           "the old shortcut (Z+L+R) is ordinary buttons now");

    // Stick packing for JOY1_STICK = {y, x}.
    expect(sn64_pack_stick(-1, 2) == 0x02FF && sn64_pack_stick(5, -128) == 0x8005, "stick packing");

    // Changing the table, as the mapping screen does.
    expect(sn64_map_target(&m, SN64_IN_A) == 8 && sn64_map_target(&m, SN64_IN_Z) == 2, "targets read back as SNES bit numbers");
    sn64_map_set_target(&m, SN64_IN_A, 1);                               // A now gives Y
    expect_map(&m, "A remapped to Y",      N64_BTN_A,       0, 0, SNES_BTN_Y);
    expect_map(&m, "B unchanged",          N64_BTN_B,       0, 0, SNES_BTN_B);
    expect(!sn64_map_is_default(&m), "a changed table is not the default");
    sn64_map_set_target(&m, SN64_IN_Z, -1);                              // Z now gives nothing
    expect_map(&m, "Z set to nothing",     N64_BTN_Z,       0, 0, 0);
    expect(sn64_map_target(&m, SN64_IN_Z) == -1, "nothing reads back as -1");
    sn64_map_set_target(&m, 99, 3);
    sn64_map_set_target(&m, -1, 3);
    expect(sn64_map_target(&m, 99) == -1, "entries outside the table are ignored");
    {
        // the 13 choices the screen offers, in its order, and back from a bit number to its place
        static const int order[SN64_MAP_CHOICES] = { 8, 0, 9, 1, 10, 11, 3, 2, 4, 5, 6, 7, -1 };
        int ok = 1, back = 1;
        for (int i = 0; i < SN64_MAP_CHOICES; i++) {
            if (sn64_map_choice(i) != order[i]) ok = 0;
            if (sn64_map_choice_index(order[i]) != i) back = 0;
        }
        expect(SN64_MAP_CHOICES == 13 && ok, "the choices are A, B, X, Y, L, R, Start, Select, Up, Down, Left, Right, nothing");
        expect(back, "every choice is found again from its bit number");
        expect(sn64_map_choice(-1) == -1 && sn64_map_choice(13) == -1 && sn64_map_choice_index(99) == 12,
               "outside the list is nothing");
    }
    // Buttons the table no longer gives are reported (the screen warns about them).
    expect(sn64_map_unreachable(&m) == SNES_BTN_SELECT, "A moved to Y, Z to nothing: only Select is left without a button");
    sn64_map_default(&m);
    expect(sn64_map_is_default(&m), "the defaults come back");
    expect(sn64_map_unreachable(&m) == 0, "with the defaults every SNES button is given by some button");
    sn64_map_set_target(&m, SN64_IN_START, -1);
    sn64_map_set_target(&m, SN64_IN_Z, -1);
    expect(sn64_map_unreachable(&m) == (SNES_BTN_START | SNES_BTN_SELECT), "Start and Z set to nothing: Start and Select are reported");
    sn64_map_default(&m);
    for (int e = SN64_IN_D_UP; e <= SN64_IN_D_RIGHT; e++) sn64_map_set_target(&m, e, -1);
    expect(sn64_map_unreachable(&m) == 0, "the D-pad's four set to nothing: the stick still gives the directions");
    sn64_map_set_stick(&m, 0);
    expect(sn64_map_unreachable(&m) == (SNES_BTN_UP | SNES_BTN_DOWN | SNES_BTN_LEFT | SNES_BTN_RIGHT),
           "and the stick to nothing as well: the four directions are reported");
    sn64_map_default(&m);
    {
        // The rows of the mapping screen: 14, and no name longer than its column.
        int ok = 1;
        for (int i = 0; i < SN64_MAP_ENTRIES; i++)
            if (strlen(m.entry[i].n64_name) > 7) ok = 0;
        expect(SN64_MAP_ENTRIES == 14 && ok, "14 rows, names of at most 7 characters");
        expect(SN64_IN_A == 0 && SN64_IN_Z == 6 && SN64_IN_L == 7 && SN64_IN_D_RIGHT == 13,
               "the rows run from A through the C buttons and Z to the shoulders, Start and the D-pad");
    }

    // Names used on the mapping screen.
    char buf[40];
    expect(strcmp(sn64_snes_mask_name(SNES_BTN_A | SNES_BTN_X, buf, sizeof buf), "A+X") == 0 &&
           strcmp(sn64_snes_mask_name(0, buf, sizeof buf), "-") == 0, "mask names");
    expect(strcmp(sn64_snes_button_name(8), "A") == 0 && strcmp(sn64_snes_button_name(2), "Select") == 0 &&
           strcmp(sn64_snes_button_name(-1), "nothing") == 0, "button names");

    if (failures) {
        printf("FAIL: mapping table, %d of %d checks failed\n", failures, checks);
        return 1;
    }
    printf("PASS: mapping table, %d checks (namesake defaults with Z->Select and the C diamond, the stick as a D-pad "
           "from %d %% of its travel in eight directions, opposing directions cancel, menu shortcut, remapping)\n",
           checks, m.stick_percent);
    return 0;
}
