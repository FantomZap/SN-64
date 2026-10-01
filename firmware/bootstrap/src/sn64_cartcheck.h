// SPDX-License-Identifier: GPL-3.0-or-later
// Cartridge check: what the screen says about a check result or a power fault.
// Pure C, no libdragon dependency, so the same code is unit-tested on the host
// (firmware/bootstrap/tests/test_cartcheck.c).
//
// The check itself is in the FPGA (docs/design/reversed-cartridge-detection.md):
// before the cartridge's 5 V is switched on, a small test current goes into the
// switched-off supply rail. A cartridge that is in back to front holds the rail
// at about half a volt; the right way round it rises higher. The rail reading
// and the verdict come back in the CART_CHECK mailbox word.
#ifndef SN64_CARTCHECK_H
#define SN64_CARTCHECK_H

#include <stdbool.h>
#include <stdint.h>

// Rail reading below this many counts (9.67 mV each) on a failed check: the rail
// did not rise at all, which is a short rather than a reversed cartridge.
// ASSUMED until measured: 15 counts = 0.145 V; a reversed cartridge is expected
// near 0.45 V.
#ifndef SN64_FAULT_CHECK_LEVELS
#define SN64_CHECK_SHORT_LEVEL 15u
#else
// Fault injection for the host test: a threshold above the reversed-cartridge
// reading turns "backwards" into "short"; the test must catch it.
#define SN64_CHECK_SHORT_LEVEL 150u
#endif

// Lines are drawn with the 8x8 font at x = 16 on the 320-pixel menu screen.
#define SN64_ALERT_COLUMNS 38
#define SN64_ALERT_MAX_LINES 8

typedef enum {
    SN64_ALERT_NONE,
    SN64_ALERT_CHECK_OK,            // check only: the rail rose
    SN64_ALERT_BACKWARDS,           // the rail stayed at a diode drop; nothing was powered
    SN64_ALERT_SHORT,               // the rail did not rise at all; nothing was powered
    SN64_ALERT_POWER_FAULT,         // any other latched power fault
    SN64_ALERT_FAULT_AFTER_WARNING, // report-only: the check had failed, power was applied, and it tripped
    SN64_ALERT_NO_CHECK,            // this FPGA build has no cartridge check
    SN64_ALERT_CHECK_TIMEOUT,       // the check never reported back
    SN64_ALERT_COUNT
} sn64_alert_t;

// Rail reading of the last check in millivolts (CART_CHECK level, 9.67 mV per count).
unsigned sn64_check_millivolts(uint16_t cart_check);

// What to tell the user. `fault` is the FAULT word read while the fault was
// still latched (0 if none); `check_only` is true when the request was the
// menu's "check cartridge" item, which never powers anything.
sn64_alert_t sn64_alert_for(uint16_t fault, uint16_t cart_check, bool check_only);

// The screen text of an alert: up to SN64_ALERT_MAX_LINES lines, NULL after the last.
const char *const *sn64_alert_lines(sn64_alert_t alert);

// "enforce", "report only", "off", "check only".
const char *sn64_check_mode_name(unsigned mode);

// One-line summary of the last check for the menu, e.g. "ok, 0.80 V" or
// "FAILED 0.47 V (backwards?)". Returns buf.
char *sn64_check_summary(uint16_t cart_check, char *buf, unsigned n);

#endif
