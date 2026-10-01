// SPDX-License-Identifier: GPL-3.0-or-later
// Sound path of the game display: the Super NES's 32 kHz stereo samples are fitted to the
// console's sound output, whose rate is a whole division of the video clock and never
// exactly the game's (docs/design/frame-lock.md). A four-point cubic resampler moves through
// the game's samples in steps a hair off 1.0; the step is nudged so the sound waiting in the
// console's output stays near a set amount. No sample is ever padded with silence or
// repeated in blocks, which is what made the first version buzz.
//
// Pure C, no libdragon dependency; unit-tested on the host (tests/test_resample.c).
#ifndef SN64_RESAMPLE_H
#define SN64_RESAMPLE_H

#include <stdint.h>

typedef struct {
    int16_t  h[4][2];           // the four newest input pairs, oldest first; output lies between h[1] and h[2]
    uint32_t frac;              // position between them, 32 fraction bits
    uint32_t need;              // input pairs still to take before the next output
} sn64_resample_t;

void sn64_resample_reset(sn64_resample_t *r);

// Takes up to `n_in` stereo pairs from `in` and writes up to `max_out` pairs to `out`, moving
// `step_q32` input pairs per output pair (2^32 = 1.0). Returns the pairs written; `*used` is
// the pairs taken (all of them unless `out` filled up first). Calling it with the input cut
// into any pieces gives the same output as one call.
int sn64_resample(sn64_resample_t *r, const int16_t *in, int n_in, int *used,
                  int16_t *out, int max_out, uint64_t step_q32);

// The step for the next block: `nominal_q32` nudged so the sound waiting to be played
// (`backlog` pairs) moves toward `target` pairs. More waiting than wanted: larger steps,
// fewer samples out. The nudge is held to +-0.5 % (under a tenth of a semitone).
#define SN64_AUDIO_TRIM_PPM 5000
uint64_t sn64_audio_step(uint64_t nominal_q32, int backlog, int target);

#endif
