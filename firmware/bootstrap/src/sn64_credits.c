// SPDX-License-Identifier: GPL-3.0-or-later
// Credits roll geometry. See sn64_credits.h.
#include "sn64_credits.h"

// At scroll 0 the first line stands just below the window; each pixel of scroll lifts every
// line by one.
static int line_y(int index, int scroll, int bottom)
{
    return bottom + index * SN64_CREDITS_ROW_PX - scroll;
}

int sn64_credits_visible(int scroll, int top, int bottom, int line[], int y[], int max)
{
    int n = 0;
    for (int i = 0; i < sn64_credits_count && n < max; i++) {
        int at = line_y(i, scroll, bottom);
#ifdef SN64_FAULT_CREDITS_OVERRUN
        if (at < top || at >= bottom)                       // fault injection: a line may hang out of the window
#else
        if (at < top || at + SN64_CREDITS_CELL_PX > bottom) // wholly inside only
#endif
            continue;
        if (sn64_credits_lines[i][0] == '\0')
            continue;
        line[n] = i;
        y[n] = at;
        n++;
    }
    return n;
}

int sn64_credits_end(int top, int bottom)
{
    int middle = top + (bottom - top - SN64_CREDITS_CELL_PX) / 2;
    return bottom + (sn64_credits_count - 1) * SN64_CREDITS_ROW_PX - middle;
}
