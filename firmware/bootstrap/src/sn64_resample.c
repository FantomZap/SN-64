// SPDX-License-Identifier: GPL-3.0-or-later
// Cubic resampler and its rate control. See sn64_resample.h.
#include "sn64_resample.h"

#include <string.h>

void sn64_resample_reset(sn64_resample_t *r)
{
    memset(r, 0, sizeof(*r));
}

// Catmull-Rom through p1 and p2 at t (15 fraction bits):
//   y = p1 + t (c + t (b + t a)) / 2,  a = -p0 + 3 p1 - 3 p2 + p3,  b = 2 p0 - 5 p1 + 4 p2 - p3,  c = p2 - p0
static inline int16_t cubic(int32_t p0, int32_t p1, int32_t p2, int32_t p3, int32_t t)
{
    int64_t a = -p0 + 3 * p1 - 3 * p2 + p3;
    int64_t b = 2 * p0 - 5 * p1 + 4 * p2 - p3;
    int64_t c = p2 - p0;
    int64_t y = (a * t) / 32768 + b;
    y = (y * t) / 32768 + c;
    y = (y * t) / 65536 + p1;
    if (y > 32767) y = 32767;                   // the curve can overshoot a full-scale edge
    if (y < -32768) y = -32768;
    return (int16_t)y;
}

int sn64_resample(sn64_resample_t *r, const int16_t *in, int n_in, int *used,
                  int16_t *out, int max_out, uint64_t step_q32)
{
    int i = 0, o = 0;
    for (;;) {
        while (r->need > 0 && i < n_in) {       // shift the history along
            memmove(r->h[0], r->h[1], 3 * sizeof(r->h[0]));
            r->h[3][0] = in[2 * i];
            r->h[3][1] = in[2 * i + 1];
            i++;
            r->need--;
        }
        if (r->need > 0 || o >= max_out)
            break;                              // out of input, or out of room
        int32_t t = (int32_t)(r->frac >> 17);
        out[2 * o]     = cubic(r->h[0][0], r->h[1][0], r->h[2][0], r->h[3][0], t);
        out[2 * o + 1] = cubic(r->h[0][1], r->h[1][1], r->h[2][1], r->h[3][1], t);
        o++;
        uint64_t next = (uint64_t)r->frac + step_q32;
#ifdef SN64_FAULT_RESAMPLE_NO_CARRY
        r->need = 1;                            // fault injection: the fraction's carry is lost (the test must fail)
#else
        r->need = (uint32_t)(next >> 32);
#endif
        r->frac = (uint32_t)next;
    }
    *used = i;
    return o;
}

uint64_t sn64_audio_step(uint64_t nominal_q32, int backlog, int target)
{
    if (target <= 0)
        return nominal_q32;
    int64_t ppm = ((int64_t)(backlog - target) * SN64_AUDIO_TRIM_PPM) / target;   // a full target out: the whole trim
    if (ppm > SN64_AUDIO_TRIM_PPM) ppm = SN64_AUDIO_TRIM_PPM;
    if (ppm < -SN64_AUDIO_TRIM_PPM) ppm = -SN64_AUDIO_TRIM_PPM;
    return (uint64_t)((int64_t)nominal_q32 + ((int64_t)(nominal_q32 / 1000000u)) * ppm);
}
