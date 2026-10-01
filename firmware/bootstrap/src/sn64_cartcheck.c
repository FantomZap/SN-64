// SPDX-License-Identifier: GPL-3.0-or-later
// Cartridge check: screen text for check results and power faults (see sn64_cartcheck.h).
#include "sn64_cartcheck.h"

#include <stddef.h>
#include <stdio.h>

#include "sn64_mailbox.h"

unsigned sn64_check_millivolts(uint16_t cart_check)
{
    // One count = ADC code / 4 on a divide-by-3 input with a 3.3 V reference:
    // 3300 mV * 3 * 4 / 4096 = 2475 / 256 mV.
    return (unsigned)(cart_check & SN64_CHECK_LEVEL_MASK) * 2475u / 256u;
}

sn64_alert_t sn64_alert_for(uint16_t fault, uint16_t cart_check, bool check_only)
{
    bool done = (cart_check & SN64_CHECK_DONE) != 0;
    bool pass = (cart_check & SN64_CHECK_PASS) != 0;
    bool low  = (cart_check & SN64_CHECK_LEVEL_MASK) < SN64_CHECK_SHORT_LEVEL;
    unsigned code = SN64_FAULT_CODE(fault);

    if (code & SN64_FAULT_CHECK) {                  // enforce mode refused to power the cartridge
        if (done && pass)                           // the check passed, but the monitor did not hand the rail back
            return SN64_ALERT_POWER_FAULT;
        return low ? SN64_ALERT_SHORT : SN64_ALERT_BACKWARDS;
    }
    if (code != 0) {                                // some other trip; say so if the check had warned
        if (done && !pass)
            return SN64_ALERT_FAULT_AFTER_WARNING;
        return SN64_ALERT_POWER_FAULT;
    }
    if (check_only) {
        if (!(cart_check & SN64_CHECK_PRESENT))
            return SN64_ALERT_NO_CHECK;
        if (!done)
            return SN64_ALERT_CHECK_TIMEOUT;
        if (pass)
            return SN64_ALERT_CHECK_OK;
        return low ? SN64_ALERT_SHORT : SN64_ALERT_BACKWARDS;
    }
    return SN64_ALERT_NONE;
}

// Every line fits SN64_ALERT_COLUMNS (checked by the host test).
static const char *const lines_none[] = { NULL };
static const char *const lines_ok[] = {
    "Cartridge check: OK.",
    "",
    "The supply rail came up under the",
    "test current, so the cartridge is",
    "not in backwards.",
    "",
    "(An empty socket reads the same.)",
    NULL,
};
static const char *const lines_backwards[] = {
    "WHOA. WRONG WAY ROUND.",
    "",
    "That cartridge is in backwards.",
    "We don't do that around here.",
    "",
    "Nothing was powered, so no harm",
    "done. Take it out, turn the label",
    "to the front, and try again.",
    NULL,
};
static const char *const lines_short[] = {
    "CARTRIDGE POWER IS SHORTED.",
    "",
    "The cartridge supply would not",
    "rise at all. Nothing was powered.",
    "",
    "Take the cartridge out. Look for",
    "bent pins or dirt in the socket",
    "and on the cartridge edge.",
    NULL,
};
static const char *const lines_fault[] = {
    "POWER FAULT. Cartridge is off.",
    "",
    "The cartridge supply tripped.",
    "See Status / diagnostics.",
    NULL,
};
static const char *const lines_fault_warned[] = {
    "POWER FAULT. Cartridge is off.",
    "",
    "The cartridge check had failed.",
    "It was set to report only, so",
    "power was applied anyway, and the",
    "supply tripped.",
    "",
    "Is the cartridge in backwards?",
    NULL,
};
static const char *const lines_no_check[] = {
    "This FPGA build has no cartridge",
    "check.",
    NULL,
};
static const char *const lines_timeout[] = {
    "The cartridge check did not",
    "finish. See Status / diagnostics.",
    NULL,
};

const char *const *sn64_alert_lines(sn64_alert_t alert)
{
    switch (alert) {
    case SN64_ALERT_CHECK_OK:            return lines_ok;
    case SN64_ALERT_BACKWARDS:           return lines_backwards;
    case SN64_ALERT_SHORT:               return lines_short;
    case SN64_ALERT_POWER_FAULT:         return lines_fault;
    case SN64_ALERT_FAULT_AFTER_WARNING: return lines_fault_warned;
    case SN64_ALERT_NO_CHECK:            return lines_no_check;
    case SN64_ALERT_CHECK_TIMEOUT:       return lines_timeout;
    default:                             return lines_none;
    }
}

const char *sn64_check_mode_name(unsigned mode)
{
    switch (mode & 3u) {
    case SN64_CHECK_MODE_ENFORCE:    return "enforce";
    case SN64_CHECK_MODE_REPORT:     return "report only";
    case SN64_CHECK_MODE_OFF:        return "off";
    default:                         return "check only";
    }
}

char *sn64_check_summary(uint16_t cart_check, char *buf, unsigned n)
{
    unsigned mv = sn64_check_millivolts(cart_check);
    if (!(cart_check & SN64_CHECK_PRESENT))
        snprintf(buf, n, "not in this build");
    else if (!(cart_check & SN64_CHECK_DONE))
        snprintf(buf, n, "none yet");
    else if (cart_check & SN64_CHECK_PASS)
        snprintf(buf, n, "ok, %u.%02u V", mv / 1000u, (mv % 1000u) / 10u);
    else
        snprintf(buf, n, "FAILED %u.%02u V (%s)", mv / 1000u, (mv % 1000u) / 10u,
                 (cart_check & SN64_CHECK_LEVEL_MASK) < SN64_CHECK_SHORT_LEVEL ? "short?" : "backwards?");
    return buf;
}
