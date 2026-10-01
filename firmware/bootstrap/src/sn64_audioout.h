// SPDX-License-Identifier: GPL-3.0-or-later
// Sound output queue of the game display: the Super NES's samples, fitted to the console's
// rate by the resampler, are collected in a block and handed to the console's sound output
// one block per picture. The console holds two blocks at a time (the one it plays and one
// behind it); four take turns here, so a block is never refilled before it has been played.
//
// Pure C: the console's registers stay in main.c, which passes their state in and queues
// what comes back. Unit-tested on the host against a model of the console's sound output
// (tests/test_audioout.c).
#ifndef SN64_AUDIOOUT_H
#define SN64_AUDIOOUT_H

#include <stdbool.h>
#include <stdint.h>

#include "sn64_resample.h"

#define SN64_AOUT_BLOCKS      4
// Room for more than three pictures' sound: what the console cannot take yet waits here and
// goes out with the following blocks, with nothing lost.
#define SN64_AOUT_BLOCK_PAIRS 2048
// Sound left in the console's output just before a block is added: 12 ms. ASSUMED until
// heard on a console: less is less delay, more forgives a picture that comes late.
#define SN64_AOUT_TARGET_PAIRS 384
// A block shorter than this is not worth handing over; it waits for the next picture.
#define SN64_AOUT_MIN_PAIRS   16

typedef struct {
    int16_t *block[SN64_AOUT_BLOCKS];   // SN64_AOUT_BLOCK_PAIRS stereo pairs each
    int      picture;                   // pairs the console plays in one picture
    int      cur;                       // block being filled
    int      staged;                    // pairs in it
    int      queued;                    // pairs in the block last handed over
    uint32_t dropped;                   // pairs thrown away because the output took no block for too long
    sn64_resample_t rs;
} sn64_aout_t;

// `blocks`: four buffers of SN64_AOUT_BLOCK_PAIRS pairs. `picture_pairs`: what the console
// plays in one picture (about 533 at 60 Hz, 640 at 50 Hz). Returns the length in pairs of the
// silence to hand over first (block 0, already cleared): one picture and the target, so the
// first real block, a picture later, is added behind the target amount of sound.
int sn64_aout_start(sn64_aout_t *a, int16_t *const blocks[SN64_AOUT_BLOCKS], int picture_pairs);

// Sound not yet played, in pairs. `busy` and `remaining_pairs` describe the block the console
// is playing, `full` says a second one waits behind it.
int sn64_aout_waiting(const sn64_aout_t *a, bool busy, int remaining_pairs, bool full);

// Fits `n_in` new pairs to the output rate (`step_q32`, see sn64_resample.h) into the block
// being filled. If the console can take a block (`full` false), returns that block and its
// length in `*pairs`, and moves on to the next one; otherwise returns NULL and keeps filling.
//
// A block is cut so that the console is left with one picture and the target of sound: what
// is over stays here for the next picture (and the rate control works it off), so one late
// or early picture is not followed by a run of double blocks and refusals. Lengths are whole
// multiples of two pairs (the console counts in 8 bytes), and a block never ends on an 8 KiB
// address boundary (the console's sound DMA then plays the wrong memory: N64brew wiki, Audio
// Interface); the pairs held back go out with the next block.
int16_t *sn64_aout_feed(sn64_aout_t *a, const int16_t *in, int n_in, uint64_t step_q32,
                        bool busy, int remaining_pairs, bool full, int *pairs);

#endif
