// SPDX-License-Identifier: GPL-3.0-or-later
// Splash screens: fade envelope and drawing (see sn64_splash.h).
#include "sn64_splash.h"

#ifdef SN64_FAULT_SPLASH_OFFCENTRE
// Fault injection for the host test: the picture is drawn 8 pixels to the right; the test must fail.
#define SPLASH_SHIFT_X 8
#else
#define SPLASH_SHIFT_X 0
#endif

#define BLACK 0x0001u                   // 5-5-5-1: all colour bits clear, alpha set

int sn64_splash_level(int frame)
{
    const int fade = SN64_SPLASH_FADE_FRAMES, hold = SN64_SPLASH_HOLD_FRAMES, max = SN64_SPLASH_LEVEL_MAX;
    if (frame < 0)
        return 0;
    if (frame < fade)                                   // up: the last fade frame is at full brightness
        return (frame + 1) * max / fade;
    if (frame < fade + hold)
        return max;
    if (frame < 2 * fade + hold)                        // down: the last frame is black
        return (2 * fade + hold - 1 - frame) * max / fade;
    return -1;
}

void sn64_splash_draw(uint16_t *fb, int width, int height, int stride,
                      const sn64_splash_image_t *img, int level)
{
    uint16_t colour[256];
    if (level < 0) level = 0;
    if (level > SN64_SPLASH_LEVEL_MAX) level = SN64_SPLASH_LEVEL_MAX;
    for (int i = 0; i < 256; i++) {
        if (i < img->colours) {
            unsigned r = (unsigned)img->palette[i][0] * (unsigned)level / SN64_SPLASH_LEVEL_MAX;
            unsigned g = (unsigned)img->palette[i][1] * (unsigned)level / SN64_SPLASH_LEVEL_MAX;
            unsigned b = (unsigned)img->palette[i][2] * (unsigned)level / SN64_SPLASH_LEVEL_MAX;
            colour[i] = (uint16_t)(((r >> 3) << 11) | ((g >> 3) << 6) | ((b >> 3) << 1) | 1u);
        } else {
            colour[i] = BLACK;
        }
    }
    for (int y = 0; y < height; y++)
        for (int x = 0; x < width; x++)
            fb[y * stride + x] = BLACK;
    int x0 = (width - (int)img->w) / 2 + SPLASH_SHIFT_X;
    int y0 = (height - (int)img->h) / 2;
    for (int y = 0; y < (int)img->h; y++) {
        int sy = y0 + y;
        if (sy < 0 || sy >= height)
            continue;
        const uint8_t *row = img->pixels + (unsigned)y * img->w;
        for (int x = 0; x < (int)img->w; x++) {
            int sx = x0 + x;
            if (sx < 0 || sx >= width)
                continue;
            fb[sy * stride + sx] = colour[row[x]];
        }
    }
}
