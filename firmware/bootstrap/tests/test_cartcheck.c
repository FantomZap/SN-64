// SPDX-License-Identifier: GPL-3.0-or-later
// Host unit test for the cartridge-check screens (src/sn64_cartcheck.c): which
// alert a FAULT / CART_CHECK pair gives, the rail reading in volts, and that
// every screen line fits the menu.
// Build with -DSN64_FAULT_CHECK_LEVELS to inject a wrong short/backwards
// level; the test must fail.
#include <stdio.h>
#include <string.h>

#include "sn64_cartcheck.h"
#include "sn64_mailbox.h"

static int checks, failures;

// CART_CHECK word: done, pass, mode, "check built in", level.
static uint16_t word(int done, int pass, unsigned mode, unsigned level)
{
    return (uint16_t)((done ? SN64_CHECK_DONE : 0u) | (pass ? SN64_CHECK_PASS : 0u) |
                      (mode << SN64_CHECK_MODE_SHIFT) | SN64_CHECK_PRESENT | (level & 0xFFu));
}

static void expect_alert(const char *what, uint16_t fault, uint16_t check, bool check_only, sn64_alert_t want)
{
    sn64_alert_t got = sn64_alert_for(fault, check, check_only);
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL %-46s fault %04X check %04X -> alert %d, want %d\n", what, fault, check, (int)got, (int)want);
    }
}

static void expect_text(const char *what, const char *got, const char *want)
{
    checks++;
    if (strcmp(got, want) != 0) {
        failures++;
        printf("  FAIL %-46s \"%s\", want \"%s\"\n", what, got, want);
    }
}

int main(void)
{
    char buf[40];
    const unsigned ENF = SN64_CHECK_MODE_ENFORCE, REP = SN64_CHECK_MODE_REPORT, ONLY = SN64_CHECK_MODE_CHECK_ONLY;

    // Levels from the simulation (fpga/tests/tb_cart_check.sv): a reversed cartridge reads
    // about 45 counts (0.47 V), a good one about 82 (0.80 V), a short 0.
    // Enforce mode: fault code 0x01 with the rail at a diode drop is the reversed cartridge.
    expect_alert("enforce, rail at a diode drop",      0x0100, word(1, 0, ENF, 45), false, SN64_ALERT_BACKWARDS);
    expect_alert("enforce, rail at 0 V",               0x0100, word(1, 0, ENF, 0),  false, SN64_ALERT_SHORT);
    expect_alert("enforce, just under the short level", 0x0100, word(1, 0, ENF, 14), false, SN64_ALERT_SHORT);
    expect_alert("enforce, at the short level",        0x0100, word(1, 0, ENF, 15), false, SN64_ALERT_BACKWARDS);
    expect_alert("check passed but fault 0x01",        0x0100, word(1, 1, ENF, 82), false, SN64_ALERT_POWER_FAULT);
    // Other faults.
    expect_alert("switch fault, check had passed",     0x4000, word(1, 1, ENF, 82), false, SN64_ALERT_POWER_FAULT);
    expect_alert("switch fault, no check in the build", 0x4000, 0x0000,              false, SN64_ALERT_POWER_FAULT);
    expect_alert("report only: failed, then tripped",  0x4000, word(1, 0, REP, 45), false, SN64_ALERT_FAULT_AFTER_WARNING);
    // Check only.
    expect_alert("check only, rail rose",              0x0000, word(1, 1, ONLY, 82), true, SN64_ALERT_CHECK_OK);
    expect_alert("check only, rail at a diode drop",   0x0000, word(1, 0, ONLY, 45), true, SN64_ALERT_BACKWARDS);
    expect_alert("check only, rail at 0 V",            0x0000, word(1, 0, ONLY, 0),  true, SN64_ALERT_SHORT);
    expect_alert("check only, build without the check", 0x0000, 0x3000,              true, SN64_ALERT_NO_CHECK);
    expect_alert("check only, not finished",           0x0000, word(0, 0, ONLY, 0),  true, SN64_ALERT_CHECK_TIMEOUT);
    // A normal start with nothing wrong shows nothing.
    expect_alert("running, check passed",              0x0000, word(1, 1, ENF, 82), false, SN64_ALERT_NONE);
    expect_alert("running, report-only warning",       0x0000, word(1, 0, REP, 45), false, SN64_ALERT_NONE);

    // Rail reading: 9.67 mV per count.
    checks++;
    if (sn64_check_millivolts(word(1, 0, ENF, 45)) != 435 || sn64_check_millivolts(word(1, 1, ENF, 82)) != 792 ||
        sn64_check_millivolts(word(1, 1, ENF, 255)) != 2465 || sn64_check_millivolts(0) != 0) {
        failures++;
        printf("  FAIL millivolts: %u %u %u\n", sn64_check_millivolts(word(1, 0, ENF, 45)),
               sn64_check_millivolts(word(1, 1, ENF, 82)), sn64_check_millivolts(word(1, 1, ENF, 255)));
    }

    // One-line summaries for the menu ("Last check: " + 26 characters fills the 38 columns).
    expect_text("summary: none yet",   sn64_check_summary(word(0, 0, ENF, 0), buf, sizeof(buf)),  "none yet");
    expect_text("summary: passed",     sn64_check_summary(word(1, 1, ENF, 82), buf, sizeof(buf)), "ok, 0.79 V");
    expect_text("summary: backwards",  sn64_check_summary(word(1, 0, REP, 45), buf, sizeof(buf)), "FAILED 0.43 V (backwards?)");
    expect_text("summary: short",      sn64_check_summary(word(1, 0, ENF, 0), buf, sizeof(buf)),  "FAILED 0.00 V (short?)");
    expect_text("summary: no check",   sn64_check_summary(0x0000, buf, sizeof(buf)),              "not in this build");
    checks++;
    if (strlen("Last check: ") + strlen(sn64_check_summary(word(1, 0, REP, 255), buf, sizeof(buf))) > SN64_ALERT_COLUMNS) {
        failures++;
        printf("  FAIL summary line too long: \"%s\"\n", buf);
    }

    expect_text("mode name 0", sn64_check_mode_name(0), "enforce");
    expect_text("mode name 1", sn64_check_mode_name(1), "report only");
    expect_text("mode name 2", sn64_check_mode_name(2), "off");
    expect_text("mode name 3", sn64_check_mode_name(3), "check only");

    // Every alert has text (except NONE), ends within the line limit, and every line fits the screen.
    for (int a = 0; a < SN64_ALERT_COUNT; a++) {
        const char *const *text = sn64_alert_lines((sn64_alert_t)a);
        int n = 0;
        while (n <= SN64_ALERT_MAX_LINES && text[n]) {
            checks++;
            if (strlen(text[n]) > SN64_ALERT_COLUMNS) {
                failures++;
                printf("  FAIL alert %d line %d is %u characters: \"%s\"\n", a, n, (unsigned)strlen(text[n]), text[n]);
            }
            n++;
        }
        checks++;
        if (n > SN64_ALERT_MAX_LINES || (a != SN64_ALERT_NONE && n == 0)) {
            failures++;
            printf("  FAIL alert %d has %d lines\n", a, n);
        }
    }
    // The reversed-cartridge screen says what it has to: which way, and that nothing was powered.
    {
        const char *const *text = sn64_alert_lines(SN64_ALERT_BACKWARDS);
        int backwards = 0, unpowered = 0;
        for (int i = 0; text[i]; i++) {
            if (strstr(text[i], "backwards")) backwards = 1;
            if (strstr(text[i], "Nothing was powered")) unpowered = 1;
        }
        checks++;
        if (!backwards || !unpowered) {
            failures++;
            printf("  FAIL reversed-cartridge screen text\n");
        }
    }

    printf("%s: cartridge-check screens, %d checks, %d failures\n", failures ? "FAIL" : "PASS", checks, failures);
    return failures ? 1 : 0;
}
