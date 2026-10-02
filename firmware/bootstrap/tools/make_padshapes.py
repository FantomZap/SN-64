"""Outlines of the controller pictures on the mapping screen -> src/sn64_padshape_data.c.

Each outline is a closed curve through a few dozen points, given here as fractions of the
controller's own width and height. The script lays a smooth curve through them, fills it, and
writes one list of pixel runs per row for the picture code (src/sn64_padview.c) to draw.

Where the points come from (owner, 2026-10-01: "make the graphics closer to the right shapes"):
  three handles   proportions measured on a photograph of a Nintendo 64 controller lying flat
                  (Evan-Amos, public domain, Wikimedia Commons "Nintendo-64-Controller-Gray-Flat.jpg").
                  The M64 Pro Controller, the Hyperkin Captain and the Switch Online controller
                  have the same shape in their makers' pictures.
  two handles     proportions read by eye off the makers' product pictures of the Retro Fighters
                  Brawler64 and the 8BitDo 64 Controller. Approximate.
Only proportions were taken: no photograph, logo or lettering is in this repository. The Super NES
controller is two discs and a bar and is drawn by the picture code itself.

  python tools/make_padshapes.py            writes src/sn64_padshape_data.c
  python tools/make_padshapes.py --check    fails if that file is not what this script writes
  python tools/make_padshapes.py --show     prints the outlines as text, to look at
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'src' / 'sn64_padshape_data.c'

# Left half of each outline, from the top of the middle line round the left side to the bottom of
# the middle line; the right half is its mirror image. (x, y) as fractions of width and height.
TRIDENT = [
    (0.500, 0.000), (0.400, 0.000), (0.335, 0.015), (0.305, 0.045), (0.262, 0.066),     # the raised middle of the top
    (0.200, 0.100), (0.130, 0.110), (0.085, 0.145), (0.050, 0.195), (0.028, 0.260),     # the left wing
    (0.020, 0.340), (0.008, 0.400), (0.000, 0.470), (0.000, 0.560), (0.008, 0.640),     # down the outside of the left handle
    (0.020, 0.710), (0.036, 0.755), (0.060, 0.782), (0.085, 0.790),                     # its end
    (0.110, 0.780), (0.130, 0.750), (0.146, 0.705), (0.160, 0.660), (0.173, 0.615),     # up its inside
    (0.187, 0.567), (0.196, 0.525), (0.215, 0.498), (0.250, 0.485),                     # the arch between the handles
    (0.287, 0.498), (0.335, 0.520), (0.355, 0.548), (0.365, 0.592), (0.372, 0.650),     # down the middle handle
    (0.383, 0.704), (0.392, 0.770), (0.405, 0.818), (0.413, 0.863), (0.426, 0.908),
    (0.440, 0.945), (0.460, 0.978), (0.480, 0.995), (0.500, 1.000),                     # its end
]
BRAWLER = [
    (0.500, 0.015), (0.360, 0.010), (0.300, 0.000), (0.200, 0.010), (0.130, 0.060),     # top edge and shoulder
    (0.075, 0.150), (0.047, 0.270), (0.020, 0.420), (0.006, 0.580), (0.003, 0.720),     # down the outside of the handle
    (0.012, 0.850), (0.040, 0.950), (0.094, 1.000), (0.150, 0.985), (0.190, 0.930),     # its end
    (0.215, 0.840), (0.235, 0.740), (0.250, 0.670), (0.300, 0.650), (0.400, 0.655),     # up its inside, the underside
    (0.500, 0.660),
]
EIGHTBITDO = [
    (0.500, 0.020), (0.340, 0.010), (0.240, 0.000), (0.150, 0.030), (0.085, 0.110),     # a rounder top
    (0.045, 0.230), (0.020, 0.400), (0.005, 0.580), (0.000, 0.740), (0.012, 0.880),
    (0.050, 0.970), (0.110, 1.000), (0.170, 0.975), (0.215, 0.900), (0.245, 0.800),     # short round handles
    (0.275, 0.720), (0.330, 0.690), (0.420, 0.685), (0.500, 0.685),
]

# name, half outline, width and height of the controller in pixels, where it stands in the
# 140 x 134 picture box (left, top). Sizes follow each controller's own width-to-height: the
# three-handled one is as wide as the box allows, and that sets the box's height.
SHAPES = [
    ('trident', TRIDENT, 138, 132, 1, 1),
    ('brawler', BRAWLER, 138, 99, 1, 17),
    ('eightbitdo', EIGHTBITDO, 134, 92, 3, 21),
]
BOX_W, BOX_H = 140, 134             # SN64_PAD_W, SN64_PAD_INPUT_H in src/sn64_padview.h


def whole(half):
    """The closed outline: the left half, then its mirror image back up the right side."""
    right = [(1.0 - x, y) for x, y in reversed(half) if x < 0.5]
    return half + right


def smooth(points, steps=10):
    """A closed Catmull-Rom curve through the points, as a polygon."""
    n = len(points)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = points[(i - 1) % n], points[i], points[(i + 1) % n], points[(i + 2) % n]
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(
                0.5 * (2 * p1[a] + (-p0[a] + p2[a]) * t + (2 * p0[a] - 5 * p1[a] + 4 * p2[a] - p3[a]) * t2
                       + (-p0[a] + 3 * p1[a] - 3 * p2[a] + p3[a]) * t3)
                for a in (0, 1)))
    return out


def rows_of(half, width, height, left, top):
    """{row: [(first, last), ...]}: the pixels whose middles lie inside the outline."""
    poly = [(left + x * width, top + y * height) for x, y in smooth(whole(half))]
    rows = {}
    for row in range(BOX_H):
        yc = row + 0.5
        xs = []
        for i, (x0, y0) in enumerate(poly):
            x1, y1 = poly[(i + 1) % len(poly)]
            if (y0 <= yc < y1) or (y1 <= yc < y0):
                xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
        xs.sort()
        runs = []
        for a, b in zip(xs[0::2], xs[1::2]):
            first, last = int(-(-(a - 0.5) // 1)), int((b - 0.5) // 1)      # ceil, floor
            first, last = max(first, 0), min(last, BOX_W - 1)
            if last >= first:
                if runs and first <= runs[-1][1] + 1:
                    runs[-1] = (runs[-1][0], max(last, runs[-1][1]))
                else:
                    runs.append((first, last))
        if runs:
            rows[row] = runs
    return rows


def render():
    out = [
        '// SPDX-License-Identifier: GPL-3.0-or-later',
        '// Outlines of the controller pictures: one list of pixel runs per row. Generated by',
        '// tools/make_padshapes.py (`make padshapes`) from the outline points in that script; do not edit.',
        '#include "sn64_padshape.h"',
        '',
    ]
    for name, half, width, height, left, top in SHAPES:
        rows = rows_of(half, width, height, left, top)
        first, last = min(rows), max(rows)
        assert all(r in rows for r in range(first, last + 1)), name
        assert max(len(v) for v in rows.values()) <= 3, name
        data = []
        for r in range(first, last + 1):
            data.append(', '.join([str(len(rows[r]))] + ['%d, %d' % run for run in rows[r]]))
        out.append('// %s: %d x %d pixels, rows %d to %d of the picture box' % (name, width, height, first, last))
        out.append('static const uint8_t %s_runs[] = {' % name)
        out += ['    %s,' % d for d in data]
        out.append('};')
        out.append('const sn64_padshape_t sn64_padshape_%s = { %d, %d, %s_runs };' % (name, first, last - first + 1, name))
        out.append('')
    return '\n'.join(out)


def show():
    for name, half, width, height, left, top in SHAPES:
        rows = rows_of(half, width, height, left, top)
        print(name)
        for r in range(BOX_H):
            line = [' '] * BOX_W
            for a, b in rows.get(r, []):
                for x in range(a, b + 1):
                    line[x] = '#'
            print(''.join(line).rstrip())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--show', action='store_true')
    args = ap.parse_args()
    if args.show:
        show()
        return
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding='utf-8') != text:
            sys.exit('FAIL: %s is not what tools/make_padshapes.py writes now; run `make padshapes`' % OUT.name)
        print('PASS: controller outlines match tools/make_padshapes.py (%d shapes)' % len(SHAPES))
        return
    OUT.write_text(text, encoding='utf-8', newline='\n')
    print('wrote', OUT.name, len(text), 'bytes')


if __name__ == '__main__':
    main()
