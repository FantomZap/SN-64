"""The SN64 logo as the title of the boot menu -> src/sn64_title_data.c.

Owner, 2026-10-01: "the title name on the menu can just be the logo centered on the top". The
menu has colour themes, so the title cannot be a picture on one fixed background, as the splash
screens are. It is stored with see-through edges, and the ring and the letters are stored as
"ink", which the menu draws in the colour the theme gives it.

Source, in this repository: assets/logo/sn64-logo-on-dark.svg and assets/logo/sn64-logo.svg
(make_logo.py). The two differ only in the colour of the ring and the four letters; a pixel
where they differ is ink, and a pixel where they agree keeps its own colour (the pads, the four
buttons and the characters on them).

Two sizes: one for the main menu and Settings, one for the top of the text screens.

Each pixel is one byte: the three top bits say how solid it is (0: nothing, 7: all of it), the
five low bits which colour (0: ink, 1 to 31: an entry of the palette). The palette is written as
the screen's own 16-bit colours.

  python tools/make_title.py            (needs PyMuPDF and Pillow)
  python tools/make_title.py --check    fails if the generated file is not from the logo files as they
                                        are now (compares their hashes; needs neither library)
"""
import argparse
import hashlib
import sys
import zlib
from pathlib import Path

try:
    import pymupdf
    from PIL import Image
except ImportError:                              # --check works without them
    pymupdf = Image = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OVERSAMPLE = 4
DARK = 'assets/logo/sn64-logo-on-dark.svg'
LIGHT = 'assets/logo/sn64-logo.svg'
SIZES = [('large', 160), ('small', 62)]          # name, width on the 320-pixel screen
COLOURS = 31                                     # palette entries beside the ink


def render(svg, width):
    """The artwork of the SVG (its page without the empty margins) `width` pixels wide, as an RGBA
    picture with plain (not premultiplied) colour. Drawn larger first and reduced for smooth edges."""
    page = pymupdf.open(svg)[0]

    def draw(zoom):
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
        return Image.frombytes('RGBa', (pix.width, pix.height), pix.samples)     # MuPDF gives colour times alpha
    probe = draw(600 / page.rect.width)
    x0, y0, x1, y1 = probe.split()[3].getbbox()
    share = (x1 - x0) / probe.width                         # how much of the page width the artwork takes
    big = draw(width * OVERSAMPLE / (page.rect.width * share))
    big = big.crop(big.split()[3].getbbox())
    small = big.resize((width, round(width * big.height / big.width)), Image.LANCZOS)   # reduced while premultiplied
    return small.convert('RGBA')


def build(width):
    """(palette as a list of (r, g, b), pixel bytes, width, height, number of ink pixels)."""
    dark = render(ROOT / DARK, width)
    light = render(ROOT / LIGHT, width)
    assert dark.size == light.size, (dark.size, light.size)
    w, h = dark.size
    pd, pl = dark.load(), light.load()
    solid = [[min(7, (pd[x, y][3] * 7 + 127) // 255) for x in range(w)] for y in range(h)]
    ink = [[solid[y][x] and sum(abs(pd[x, y][k] - pl[x, y][k]) for k in range(3)) > 90 for x in range(w)] for y in range(h)]
    # the colours of everything that is not ink, reduced to a palette
    own = Image.new('RGB', (w, h), (0xD8, 0xD6, 0xDD))      # the pad colour where there is nothing to count
    po = own.load()
    for y in range(h):
        for x in range(w):
            if solid[y][x] and not ink[y][x]:
                po[x, y] = pd[x, y][:3]
    q = own.quantize(colors=COLOURS, method=Image.Quantize.MAXCOVERAGE, kmeans=4, dither=Image.Dither.NONE)
    raw = q.getpalette()[:COLOURS * 3]
    pal = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    idx = q.tobytes()
    used = sorted({idx[y * w + x] for y in range(h) for x in range(w) if solid[y][x] and not ink[y][x]})
    remap = {old: new + 1 for new, old in enumerate(used)}
    pal = [pal[i] for i in used]
    px = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            a = solid[y][x]
            if a:
                px[y * w + x] = (a << 5) | (0 if ink[y][x] else remap[idx[y * w + x]])
    return pal, bytes(px), w, h, sum(sum(1 for v in row if v) for row in ink)


def rgb16(c):
    return ((c[0] >> 3) << 11) | ((c[1] >> 3) << 6) | ((c[2] >> 3) << 1) | 1


def c_bytes(data, per_line=32):
    return '\n'.join('    ' + ','.join(str(b) for b in data[i:i + per_line]) + ',' for i in range(0, len(data), per_line))


def preview(pal, px, w, h, back, ink):
    im = Image.new('RGB', (w, h), back)
    p = im.load()
    for y in range(h):
        for x in range(w):
            v = px[y * w + x]
            a, i = v >> 5, v & 31
            if a:
                fg = ink if i == 0 else pal[i - 1]
                p[x, y] = tuple(back[k] + ((fg[k] - back[k]) * a + 3) // 7 for k in range(3))
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=HERE.parent / 'src/sn64_title_data.c')
    ap.add_argument('--preview', type=Path, default=None, help='also write the pictures on a few backgrounds as a PNG')
    ap.add_argument('--check', action='store_true', help='only compare the logo files with the ones the generated file is from')
    args = ap.parse_args()
    shas = ', '.join('%s (SHA-256 %s...)' % (rel, hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:16]) for rel in (DARK, LIGHT))
    if args.check:
        have = [ln for ln in args.out.read_text(encoding='utf-8').splitlines() if ln.startswith('// From ')]
        if have != ['// From ' + shas]:
            print('FAIL: %s is not from the logo files as they are now; run tools/make_title.py' % args.out.name)
            return 1
        print('PASS: %s is from the logo files as they are now' % args.out.name)
        return 0
    if pymupdf is None:
        print('make_title.py needs PyMuPDF and Pillow')
        return 1
    parts = ['// SPDX-License-Identifier: GPL-3.0-or-later',
             '// The SN64 logo as the title of the boot menu. GENERATED by tools/make_title.py: do not edit.',
             '// The SN64 name and logo are not under the open licences (see NOTICE).',
             '// From ' + shas,
             '#include "sn64_menuview.h"', '']
    shots = []
    for name, width in SIZES:
        pal, px, w, h, inked = build(width)
        assert len(pal) <= COLOURS and len(px) == w * h
        parts += [f'// {name}: {w} x {h}, {len(pal)} colours beside the ink, {inked} pixels of ink',
                  f'static const uint16_t {name}_palette[{len(pal) + 1}] = {{',
                  '    0, ' + ', '.join('0x%04X' % rgb16(c) for c in pal) + ',', '};',
                  f'static const uint8_t {name}_pixels[{w * h}] = {{', c_bytes(px), '};',
                  f'const sn64_title_image_t sn64_title_{name} = {{ {w}, {h}, {len(pal) + 1}, {name}_palette, {name}_pixels }};', '']
        print(f'{name}: {w} x {h}, {len(pal)} colours, {inked} ink pixels, {w * h} bytes, about {len(zlib.compress(px, 9))} compressed')
        for back, ink in (((16, 24, 48), (242, 241, 245)), ((38, 20, 66), (242, 241, 245)), ((200, 200, 208), (37, 37, 44))):
            shots.append(preview(pal, px, w, h, back, ink))
    args.out.write_text('\n'.join(parts), encoding='utf-8', newline='\n')
    print('wrote', args.out.name)
    if args.preview:
        sheet = Image.new('RGB', (3 * 170, 2 * 62), (0, 0, 0))
        for i, im in enumerate(shots):
            cell = Image.new('RGB', (170, 62), im.getpixel((0, 0)))
            cell.paste(im, ((170 - im.width) // 2, (62 - im.height) // 2))
            sheet.paste(cell, ((i % 3) * 170, (i // 3) * 62))
        sheet.resize((sheet.width * 4, sheet.height * 4), Image.NEAREST).save(args.preview)
        print('wrote', args.preview.name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
