// SPDX-License-Identifier: GPL-3.0-or-later
// Splash screens shown when the console starts, before the menu (owner, 2026-10-01): the SN64
// logo, then the FantomZap logo. Each fades in, holds and fades out; any of A, B or Start skips
// straight to the menu. The same ROM runs on the N64 and the M64, so both show them.
//
// Pure C, no libdragon dependency, so the drawing is unit-tested on the host
// (firmware/bootstrap/tests/test_splash.c). The pictures are in sn64_splash_data.c, which
// tools/make_splash.py generates from the logo files in assets/logo/.
#ifndef SN64_SPLASH_H
#define SN64_SPLASH_H

#include <stdint.h>

typedef struct {
    uint16_t w, h;                  // size in pixels (made for the 320 x 240 menu screen)
    uint16_t colours;               // palette entries; entry 0 is the black background
    const uint8_t (*palette)[3];    // red, green, blue
    const uint8_t *pixels;          // w * h palette indices, row by row from the top
} sn64_splash_image_t;

extern const sn64_splash_image_t sn64_splash_sn64;        // shown first
extern const sn64_splash_image_t sn64_splash_fantomzap;   // shown second

// One splash lasts 2 * FADE + HOLD frames: 2.0 s at 60 Hz, 2.4 s at 50 Hz.
#define SN64_SPLASH_FADE_FRAMES 20
#define SN64_SPLASH_HOLD_FRAMES 80
#define SN64_SPLASH_LEVEL_MAX   16

// Brightness for a frame of a splash, 0 (black) to SN64_SPLASH_LEVEL_MAX, or -1 once it is over.
int sn64_splash_level(int frame);

// Fills a 16-bit frame buffer (5 bits red, 5 green, 5 blue, 1 alpha) with black and draws the
// picture in its centre at the given brightness. `stride` is the buffer's row length in pixels.
// A picture larger than the buffer is clipped.
void sn64_splash_draw(uint16_t *fb, int width, int height, int stride,
                      const sn64_splash_image_t *img, int level);

#endif
