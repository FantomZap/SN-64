// SPDX-License-Identifier: GPL-3.0-or-later
// Host unit test for the splash screens (src/sn64_splash.c and the generated pictures in
// src/sn64_splash_data.c): the fade envelope, that each picture is drawn centred and inside
// the frame buffer, that brightness scales, and that the picture data is consistent.
// Build with -DSN64_FAULT_SPLASH_OFFCENTRE to inject a shifted picture; the test must fail.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sn64_splash.h"

#define BLACK 0x0001u
#define GUARD 64
#define GUARD_WORD 0xA5C3u

static int checks, failures;

static void expect(int ok, const char *what)
{
    checks++;
    if (!ok) {
        failures++;
        printf("  FAIL %s\n", what);
    }
}

typedef struct { int n, x0, y0, x1, y1; unsigned brightest; } lit_t;

// Draw into a guarded buffer; report the lit pixels and whether the guards survived.
static lit_t draw(const sn64_splash_image_t *img, int w, int h, int stride, int level, int *guards_ok)
{
    size_t words = (size_t)stride * (size_t)h + 2 * GUARD;
    uint16_t *buf = malloc(words * sizeof(uint16_t));
    for (size_t i = 0; i < words; i++) buf[i] = GUARD_WORD;
    uint16_t *fb = buf + GUARD;
    sn64_splash_draw(fb, w, h, stride, img, level);
    lit_t r = { 0, w, h, -1, -1, 0 };
    *guards_ok = 1;
    for (int i = 0; i < GUARD; i++)
        if (buf[i] != GUARD_WORD || buf[words - 1 - i] != GUARD_WORD) *guards_ok = 0;
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < stride; x++) {
            uint16_t v = fb[y * stride + x];
            if (x >= w) {                       // padding between rows must not be touched
                if (v != GUARD_WORD) *guards_ok = 0;
                continue;
            }
            if (v == BLACK) continue;
            r.n++;
            if (x < r.x0) r.x0 = x;
            if (x > r.x1) r.x1 = x;
            if (y < r.y0) r.y0 = y;
            if (y > r.y1) r.y1 = y;
            unsigned sum = ((v >> 11) & 31u) + ((v >> 6) & 31u) + ((v >> 1) & 31u);
            if (sum > r.brightest) r.brightest = sum;
        }
    }
    free(buf);
    return r;
}

static void check_picture(const sn64_splash_image_t *img, const char *name)
{
    char what[96];
    int ok;

    // The data: every index inside the palette, entry 0 black, something to show.
    int bad = 0, shown = 0;
    int cx0 = img->w, cx1 = -1, cy0 = img->h, cy1 = -1;       // box of what is not background
    for (int y = 0; y < img->h; y++) {
        for (int x = 0; x < img->w; x++) {
            unsigned v = img->pixels[y * img->w + x];
            if (v >= img->colours) { bad++; continue; }
            const uint8_t *c = img->palette[v];
            if ((c[0] >> 3) || (c[1] >> 3) || (c[2] >> 3)) {   // visible at 5 bits per channel
                shown++;
                if (x < cx0) cx0 = x;
                if (x > cx1) cx1 = x;
                if (y < cy0) cy0 = y;
                if (y > cy1) cy1 = y;
            }
        }
    }
    snprintf(what, sizeof(what), "%s: palette indices in range", name);
    expect(bad == 0, what);
    snprintf(what, sizeof(what), "%s: palette entry 0 is black", name);
    expect(img->palette[0][0] == 0 && img->palette[0][1] == 0 && img->palette[0][2] == 0, what);
    snprintf(what, sizeof(what), "%s: fits the 320 x 240 screen with 16 pixels to spare each side", name);
    expect(img->w <= 288 && img->h <= 208 && img->colours <= 256, what);
    snprintf(what, sizeof(what), "%s: the artwork reaches all four edges of its picture", name);
    expect(cx0 == 0 && cy0 == 0 && cx1 == img->w - 1 && cy1 == img->h - 1, what);

    // Black at level 0, whatever the picture.
    lit_t z = draw(img, 320, 240, 320, 0, &ok);
    snprintf(what, sizeof(what), "%s: level 0 is all black", name);
    expect(z.n == 0 && ok, what);

    // Full brightness on the menu screen: centred, every visible pixel drawn, nothing outside.
    lit_t f = draw(img, 320, 240, 320, SN64_SPLASH_LEVEL_MAX, &ok);
    snprintf(what, sizeof(what), "%s: nothing written outside the frame buffer", name);
    expect(ok, what);
    snprintf(what, sizeof(what), "%s: every visible pixel drawn (%d of %d)", name, f.n, shown);
    expect(f.n == shown, what);
    int left = f.x0, right = 319 - f.x1, top = f.y0, bottom = 239 - f.y1;
    snprintf(what, sizeof(what), "%s: centred (margins left %d right %d top %d bottom %d)", name, left, right, top, bottom);
    expect(abs(left - right) <= 1 && abs(top - bottom) <= 1, what);
    snprintf(what, sizeof(what), "%s: drawn at its own size", name);
    expect(f.x1 - f.x0 + 1 == img->w && f.y1 - f.y0 + 1 == img->h, what);

    // Half brightness is about half as bright; a row stride longer than the width is respected.
    lit_t hlf = draw(img, 320, 240, 336, SN64_SPLASH_LEVEL_MAX / 2, &ok);
    snprintf(what, sizeof(what), "%s: half level about half as bright (%u against %u), row padding untouched", name, hlf.brightest, f.brightest);
    expect(ok && hlf.brightest * 2 >= f.brightest - 6 && hlf.brightest * 2 <= f.brightest + 6, what);

    // The 256-pixel game screen is narrower than the pictures: clipped, not written outside.
    lit_t c = draw(img, 256, 240, 256, SN64_SPLASH_LEVEL_MAX, &ok);
    snprintf(what, sizeof(what), "%s: clipped on a 256-pixel screen", name);
    expect(ok && c.x0 >= 0 && c.x1 <= 255 && c.n > 0 && c.n <= shown, what);
    lit_t t = draw(img, 64, 32, 64, SN64_SPLASH_LEVEL_MAX, &ok);
    snprintf(what, sizeof(what), "%s: clipped on a tiny screen", name);
    expect(ok && t.x1 <= 63 && t.y1 <= 31, what);
    // Out-of-range levels are limited, not wrapped.
    lit_t over = draw(img, 320, 240, 320, 99, &ok);
    snprintf(what, sizeof(what), "%s: level above the maximum is limited", name);
    expect(ok && over.brightest == f.brightest && over.n == f.n, what);
}

int main(void)
{
    // Fade envelope: up, hold, down, over.
    const int fade = SN64_SPLASH_FADE_FRAMES, hold = SN64_SPLASH_HOLD_FRAMES, max = SN64_SPLASH_LEVEL_MAX;
    int total = 0, rising = 1, falling = 1, held = 0, peak = 0;
    while (sn64_splash_level(total) >= 0 && total < 10000) total++;
    for (int f = 1; f < fade; f++)
        if (sn64_splash_level(f) < sn64_splash_level(f - 1)) rising = 0;
    for (int f = fade + hold + 1; f < total; f++)
        if (sn64_splash_level(f) > sn64_splash_level(f - 1)) falling = 0;
    for (int f = 0; f < total; f++) {
        if (sn64_splash_level(f) == max) held++;
        if (sn64_splash_level(f) > peak) peak = sn64_splash_level(f);
    }
    expect(total == 2 * fade + hold, "one splash lasts 2 x fade + hold frames");
    expect(rising && falling, "brightness only rises during the fade-in and only falls during the fade-out");
    expect(peak == max && held >= hold, "full brightness is reached and held");
    expect(sn64_splash_level(0) <= max / 4 && sn64_splash_level(fade - 1) == max, "the fade-in starts dark and ends at full brightness");
    expect(sn64_splash_level(total - 1) == 0, "the last frame is black");
    expect(sn64_splash_level(total) == -1 && sn64_splash_level(total + 500) == -1, "afterwards the splash reports that it is over");
    expect(sn64_splash_level(-3) == 0, "a negative frame number is black, not an error");

    check_picture(&sn64_splash_sn64, "SN64 logo");
    check_picture(&sn64_splash_fantomzap, "FantomZap logo");
    // The first picture has colour, the second is white on black.
    int coloured = 0, grey = 1;
    for (unsigned i = 0; i < sn64_splash_sn64.colours; i++) {
        const uint8_t *c = sn64_splash_sn64.palette[i];
        if (abs((int)c[0] - (int)c[2]) > 60) coloured = 1;
    }
    for (unsigned i = 0; i < sn64_splash_fantomzap.colours; i++) {
        const uint8_t *c = sn64_splash_fantomzap.palette[i];
        if (c[0] != c[1] || c[1] != c[2]) grey = 0;
    }
    expect(coloured, "the SN64 picture keeps its button colours");
    expect(grey, "the FantomZap picture is white on black");

    printf("%s: splash screens, %d checks, %d failures (SN64 logo %u x %u in %u colours, FantomZap logo %u x %u in %u, %d frames each)\n",
           failures ? "FAIL" : "PASS", checks, failures, sn64_splash_sn64.w, sn64_splash_sn64.h, sn64_splash_sn64.colours,
           sn64_splash_fantomzap.w, sn64_splash_fantomzap.h, sn64_splash_fantomzap.colours, total);
    return failures ? 1 : 0;
}
