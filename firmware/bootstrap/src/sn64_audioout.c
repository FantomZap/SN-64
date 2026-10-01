// SPDX-License-Identifier: GPL-3.0-or-later
// Sound output queue of the game display. See sn64_audioout.h.
#include "sn64_audioout.h"

#include <string.h>

// Whole multiples of two pairs, and never ending on an 8 KiB boundary.
static int sendable(const int16_t *buf, int pairs)
{
    pairs &= ~1;
    if (pairs > 0 && (((uintptr_t)buf + (uintptr_t)pairs * 4u) & 0x1FFFu) == 0)
        pairs -= 2;
    return pairs;
}

int sn64_aout_start(sn64_aout_t *a, int16_t *const blocks[SN64_AOUT_BLOCKS], int picture_pairs)
{
    memset(a, 0, sizeof(*a));
    for (int i = 0; i < SN64_AOUT_BLOCKS; i++)
        a->block[i] = blocks[i];
    if (picture_pairs < 256) picture_pairs = 256;
    if (picture_pairs > 1024) picture_pairs = 1024;
    a->picture = picture_pairs;
    sn64_resample_reset(&a->rs);
    int silence = sendable(a->block[0], SN64_AOUT_TARGET_PAIRS + picture_pairs);
    memset(a->block[0], 0, (size_t)silence * 4u);
    a->cur = 1;
    a->queued = silence;
    return silence;
}

int sn64_aout_waiting(const sn64_aout_t *a, bool busy, int remaining_pairs, bool full)
{
    return a->staged + (busy ? remaining_pairs : 0) + (full ? a->queued : 0);
}

int16_t *sn64_aout_feed(sn64_aout_t *a, const int16_t *in, int n_in, uint64_t step_q32,
                        bool busy, int remaining_pairs, bool full, int *pairs)
{
    int used = 0;
    int16_t *buf = a->block[a->cur];
    a->staged += sn64_resample(&a->rs, in, n_in, &used, buf + 2 * a->staged, SN64_AOUT_BLOCK_PAIRS - a->staged, step_q32);
    *pairs = 0;
    if (used < n_in || a->staged >= SN64_AOUT_BLOCK_PAIRS) {
        // The console took nothing for several pictures: start the block again rather than
        // hang on to old sound.
        a->dropped += (uint32_t)(n_in - used) + (uint32_t)a->staged;
        a->staged = 0;
        return NULL;
    }
    // The console has two places. A block may only be added while the second is free, and it
    // must still be free one picture from now: so nothing is added while the block that plays
    // would last that long by itself, and blocks are kept to about one picture each. (One long
    // block after a late picture would still be playing two pictures on, with the next one
    // stuck behind it and no place for a third: found with the model in tests/test_audioout.c.)
    int left = busy ? remaining_pairs : 0;
    if (full || left >= a->picture)
        return NULL;
    // One picture's worth, plus a quarter of what is missing from the target if the picture was
    // late; never more than fills the console to one picture and the target. The rest waits here.
    int want = a->picture + (left < SN64_AOUT_TARGET_PAIRS ? (SN64_AOUT_TARGET_PAIRS - left) / 4 : 0);
    int room = SN64_AOUT_TARGET_PAIRS + a->picture - left;
    if (want > room) want = room;
    int send = sendable(buf, a->staged < want ? a->staged : want);
    if (send < SN64_AOUT_MIN_PAIRS)
        return NULL;
    int next = (a->cur + 1) % SN64_AOUT_BLOCKS, rest = a->staged - send;
#ifndef SN64_FAULT_AOUT_NO_CARRY
    memcpy(a->block[next], buf + 2 * send, (size_t)rest * 4u);   // the pairs held back start the next block
#endif                                                             // fault injection: they are lost (the test must fail)
    a->cur = next;
    a->staged = rest;
    a->queued = send;
    *pairs = send;
    return buf;
}
