"""Trace the FantomZap logo (a white-on-transparent PNG) into outlines, as an SVG.

The owner's logo exists as pixel artwork only. The shell needs outlines (it stamps the logo into the
back of the cap) and so does anything that has to show it at another size. This script traces the
artwork with the potrace algorithm and writes one black shape per piece of the logo, each with its
own holes, as absolute M/L/C/Z paths without transforms (what build123d's SVG import handles best).

The full-size artwork is the owner's and is not kept in this repository; pass its path:

  uv run --no-project --with potracer --with pillow --with numpy python assets/logo/fantomzap/trace_logo.py <logo.png>

Output next to this script: fantomzap-wordmark-mono.svg and trace-report.json (source name, size and
SHA-256, settings, and how far the outlines are from the pixels).
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import potrace
from PIL import Image

HERE = Path(__file__).resolve().parent
Image.MAX_IMAGE_PIXELS = None


def coverage(path):
    """How much of each pixel is logo, 0..255: the artwork is white with alpha, so alpha x brightness."""
    rgba = np.asarray(Image.open(path).convert('RGBA')).astype(np.uint16)
    lum = rgba[..., :3].mean(axis=2)
    return (rgba[..., 3] * lum / 255.0).astype(np.uint8)


def bezier_points(p0, p1, p2, p3, n=8):
    t = np.linspace(0.0, 1.0, n + 1)[1:, None]
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * (t ** 2) * p2 + (t ** 3) * p3


def trace(cov, turdsize, alphamax, opttolerance):
    """Closed curves as {'d': svg path data, 'poly': points along it, 'area': signed area}."""
    # potracer follows potrace: dark pixels are the shape, so the logo's pixels are passed as False
    plist = potrace.Bitmap(cov <= 127).trace(turdsize=turdsize, turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY,
                                            alphamax=alphamax, opticurve=True, opttolerance=opttolerance)
    curves = []
    for curve in plist:
        start = np.array([curve.start_point.x, curve.start_point.y])
        d = [f'M{start[0]:.2f} {start[1]:.2f}']
        poly, cur = [start], start
        for seg in curve.segments:
            end = np.array([seg.end_point.x, seg.end_point.y])
            if seg.is_corner:
                c = np.array([seg.c.x, seg.c.y])
                d.append(f'L{c[0]:.2f} {c[1]:.2f}L{end[0]:.2f} {end[1]:.2f}')
                poly += [c, end]
            else:
                c1, c2 = np.array([seg.c1.x, seg.c1.y]), np.array([seg.c2.x, seg.c2.y])
                d.append(f'C{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {end[0]:.2f} {end[1]:.2f}')
                poly += list(bezier_points(cur, c1, c2, end))
            cur = end
        d.append('Z')
        pts = np.array(poly)
        x, y = pts[:, 0], pts[:, 1]
        area = 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
        curves.append({'d': ''.join(d), 'poly': pts, 'area': area, 'segments': len(curve.segments)})
    return curves


def inside(pt, poly):
    x, y = pt
    px, py = poly[:, 0], poly[:, 1]
    qx, qy = np.roll(px, -1), np.roll(py, -1)
    cross = ((py > y) != (qy > y)) & (x < (qx - px) * (y - py) / (qy - py + 1e-12) + px)
    return bool(np.sum(cross) % 2)


def group(curves):
    """Outer shapes with their holes: a curve nested in an odd number of others is a hole of the
    smallest one that contains it."""
    order = sorted(range(len(curves)), key=lambda i: -abs(curves[i]['area']))
    parents = {}
    for i in order:
        probe = curves[i]['poly'][0]
        holders = [j for j in order if j != i and abs(curves[j]['area']) > abs(curves[i]['area'])
                   and inside(probe, curves[j]['poly'])]
        parents[i] = (len(holders), min(holders, key=lambda j: abs(curves[j]['area'])) if holders else None)
    shapes = []
    for i in order:
        depth, _ = parents[i]
        if depth % 2 == 0:
            holes = [j for j in order if parents[j][0] == depth + 1 and parents[j][1] == i]
            shapes.append((i, holes))
    return sorted(shapes, key=lambda s: curves[s[0]]['poly'][:, 0].min())      # left to right


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path, help='the logo artwork (PNG with transparency)')
    ap.add_argument('--turdsize', type=int, default=20, help='ignore specks up to this many pixels')
    ap.add_argument('--alphamax', type=float, default=1.0, help='potrace corner threshold')
    ap.add_argument('--opttolerance', type=float, default=0.4, help='potrace curve-joining tolerance')
    args = ap.parse_args()
    cov = coverage(args.source)
    h, w = cov.shape
    curves = trace(cov, args.turdsize, args.alphamax, args.opttolerance)
    shapes = group(curves)
    paths = []
    for outer, holes in shapes:
        d = curves[outer]['d'] + ''.join(curves[j]['d'] for j in holes)
        paths.append(f'  <path fill="#000" fill-rule="evenodd" d="{d}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n'
           '  <!-- FantomZap logo: outlines traced from the owner\'s artwork by trace_logo.py. The FantomZap name and\n'
           '       logo belong to the owner and are not under the project\'s open licences (see NOTICE). -->\n'
           + '\n'.join(paths) + '\n</svg>\n')
    out = HERE / 'fantomzap-wordmark-mono.svg'
    out.write_text(svg, encoding='utf-8', newline='\n')
    ys, xs = np.where(cov > 127)
    report = {
        'source_name': args.source.name, 'source_size': [w, h], 'source_bytes': args.source.stat().st_size,
        'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
        'artwork_box_px': [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
        'settings': {'threshold': 'coverage > 50 %', 'turdsize': args.turdsize, 'alphamax': args.alphamax,
                     'opttolerance': args.opttolerance, 'tracer': 'potracer (potrace algorithm)'},
        'shapes': len(shapes), 'holes': sum(len(hs) for _, hs in shapes),
        'segments': sum(c['segments'] for c in curves),
    }
    (HERE / 'trace-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))
    print('wrote', out.name, f'({len(svg)} bytes)')


if __name__ == '__main__':
    main()
