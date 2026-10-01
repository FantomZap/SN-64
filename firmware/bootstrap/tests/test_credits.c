// SPDX-License-Identifier: GPL-3.0-or-later
// Host unit test for the credits roll (src/sn64_credits.c and the generated text in
// src/sn64_credits_data.c):
//   * every line fits 36 columns (a margin at both edges of the screen) and is plain 7-bit text;
//   * it opens with the credit line and the source location, and closes with the SN64 crew in
//     the owner's words, the cats at the very end;
//   * at every scroll position each line drawn lies wholly inside the window (the console's
//     text drawing does not clip), in order, a row apart, and never an empty one;
//   * every line with text is shown at some point, so nobody's credit is skipped;
//   * the roll stops with its last line in the middle of the window, the whole crew on screen.
// That the text matches CREDITS.md is checked by tools/make_credits.py --check (make test-credits).
// Build with -DSN64_FAULT_CREDITS_OVERRUN (a line may hang out of the window); the test must fail.
#include <stdio.h>
#include <string.h>

#include "sn64_credits.h"

// The window main.c gives the roll on the 320 x 240 menu screen.
#define TOP    22
#define BOTTOM 228

static int checks, failures;

static void expect(int ok, const char *what)
{
    checks++;
    if (!ok) {
        failures++;
        printf("  FAIL %s\n", what);
    }
}

static int has(const char *text)
{
    for (int i = 0; i < sn64_credits_count; i++)
        if (strstr(sn64_credits_lines[i], text)) return 1;
    return 0;
}

int main(void)
{
    const int n = sn64_credits_count;

    // ---- the text ----
    int fits = 1, plain = 1;
    for (int i = 0; i < n; i++) {
        const char *s = sn64_credits_lines[i];
        if (strlen(s) > SN64_CREDITS_COLUMNS) { fits = 0; printf("    too long: \"%s\"\n", s); }
        for (; *s; s++) if (*s < 32 || *s > 126) plain = 0;
    }
    expect(n > 40, "the roll has its lines");
    expect(fits, "every line fits 36 columns");
    expect(plain, "every line is plain 7-bit text");
    expect(strcmp(sn64_credits_lines[0], "SN64 by FantomZap") == 0, "opens with the credit line");
    expect(strncmp(sn64_credits_lines[1], "github.com/", 11) == 0, "then the source location");
    expect(strcmp(sn64_credits_lines[n - 4], "Engineer: Claude (AI by Anthropic)") == 0, "the crew: the engineer");
    expect(strcmp(sn64_credits_lines[n - 3], "Manager: Scout (Cat)") == 0, "the crew: the manager");
    expect(strcmp(sn64_credits_lines[n - 2], "Arbitrary code execution:") == 0, "the crew: arbitrary code execution");
    expect(strcmp(sn64_credits_lines[n - 1], "  Ash & Aurora (More cats)") == 0, "the cats are the very last line");
    {
        int crew = 0, titles = 0, kinds_ok = 1;
        for (int i = 0; i < n; i++) {
            if (sn64_credits_kind[i] > SN64_CREDIT_CREW) kinds_ok = 0;
            if (sn64_credits_kind[i] == SN64_CREDIT_CREW) crew++;
            if (sn64_credits_kind[i] == SN64_CREDIT_TITLE) titles++;
            if (sn64_credits_kind[i] == SN64_CREDIT_PEOPLE && sn64_credits_lines[i][0] == '\0') kinds_ok = 0;
        }
        expect(kinds_ok, "every line has a kind, and no empty line is a credit");
        expect(sn64_credits_kind[0] == SN64_CREDIT_TITLE && titles >= 4, "the credit line and the section titles are marked as titles");
        expect(crew == 4 && sn64_credits_kind[n - 4] == SN64_CREDIT_CREW && sn64_credits_kind[n - 1] == SN64_CREDIT_CREW,
               "the crew is the last four lines and nothing else");
    }
    {
        static const char *const people[] = {
            "nand2mario", "Sergiy Dvodnenko", "gyurco", "Mateusz Faderewski", "Olof Kindgren", "Jan Goldacker",
            "TinyFPGA", "starlightk7", "sanni", "KiCad library contributors", "DragonMinded", "Maximilian Rehkopf",
            "EMARD", "qwertymodo", "rainwarrior", "rgalland", "raphnet", "Michael Hirschmugl", "usagi_", "ModRetro",
            "drandyhaas",
        };
        int missing = 0;
        for (unsigned i = 0; i < sizeof(people) / sizeof(people[0]); i++)
            if (!has(people[i])) { missing++; printf("    not in the roll: %s\n", people[i]); }
        expect(missing == 0, "everyone the repository credits by name is in the roll");
    }

    // ---- where the lines stand ----
    const int end = sn64_credits_end(TOP, BOTTOM);
    static int seen[4096];
    int line[64], y[64];
    int inside = 1, ordered = 1, spaced = 1, no_empty = 1, bounded = 1, most = 0;
    expect(end > 0 && n < 4096, "the roll has somewhere to go");
    expect(sn64_credits_visible(0, TOP, BOTTOM, line, y, 64) == 0, "nothing on screen before it starts");
    for (int scroll = 0; scroll <= end; scroll++) {
        int k = sn64_credits_visible(scroll, TOP, BOTTOM, line, y, 64);
        if (k > most) most = k;
        for (int j = 0; j < k; j++) {
            if (y[j] < TOP || y[j] + SN64_CREDITS_CELL_PX > BOTTOM) inside = 0;
            if (line[j] < 0 || line[j] >= n) { bounded = 0; continue; }
            if (sn64_credits_lines[line[j]][0] == '\0') no_empty = 0;
            if (j > 0 && line[j] <= line[j - 1]) ordered = 0;
            if (j > 0 && y[j] - y[j - 1] != (line[j] - line[j - 1]) * SN64_CREDITS_ROW_PX) spaced = 0;
            seen[line[j]] = 1;
        }
    }
    expect(inside, "every line drawn lies wholly inside the window, at every scroll position");
    expect(bounded, "only lines of the roll are drawn");
    expect(ordered, "lines are drawn in order, top to bottom");
    expect(spaced, "lines stand a row apart");
    expect(no_empty, "empty lines are not drawn");
    expect(most <= (BOTTOM - TOP) / SN64_CREDITS_ROW_PX + 1 && most >= 18, "a screenful is about twenty lines");
    {
        int skipped = 0;
        for (int i = 0; i < n; i++) if (sn64_credits_lines[i][0] && !seen[i]) skipped++;
        expect(skipped == 0, "every line with text is shown on the way");
    }
    {
        int k = sn64_credits_visible(end, TOP, BOTTOM, line, y, 64);
        int crew = 0, last_y = -1;
        for (int j = 0; j < k; j++) {
            if (line[j] >= n - 4) crew++;
            if (line[j] == n - 1) last_y = y[j];
        }
        expect(crew == 4, "the roll stops with the whole crew on screen");
        expect(last_y == TOP + (BOTTOM - TOP - SN64_CREDITS_CELL_PX) / 2, "its last line in the middle of the window");
        expect(sn64_credits_visible(end, TOP, BOTTOM, line, y, 2) == 2, "no more lines are returned than asked for");
    }

    printf("%s: credits roll, %d checks, %d failures (%d lines, %d pixels of travel, up to %d lines on screen)\n",
           failures ? "FAIL" : "PASS", checks, failures, n, end, most);
    return failures ? 1 : 0;
}
