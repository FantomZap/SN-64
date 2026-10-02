"""Print the SN64 logo and the owner's FantomZap logo on the v2 board's silkscreen (KiCad's python).

  python add_logo_silk_v2.py [board.kicad_pcb]

Owner, 2026-10-02: "i want my sn64 and fantomzap logos screenprinted on there somewhere". Both come
from the one-colour files under assets/logo/ and go on the back face (F.SilkS), in the clear area
beside the FPGA. The FantomZap name and logo are the owner's and are not under the open licences
(NOTICE item 3). Refuses a board that already carries them.
"""
import math
import re
import sys
from pathlib import Path

import pcbnew

V2 = Path(__file__).resolve().parents[1]
REPO = V2.parents[1]
mm = pcbnew.FromMM
# file, centre x, centre y, width in mm
LOGOS = (('assets/logo/sn64-logo-mono-plain.svg', 27.0, -17.5, 30.0),
         ('assets/logo/fantomzap/fantomzap-wordmark-mono.svg', 27.0, -8.0, 30.0))
TAG = 'sn64_logo_silk'


def arc(p0, rx, ry, phi, large, sweep, p1, n=24):
    """SVG elliptical arc as points (end point included)."""
    x0, y0 = p0; x1, y1 = p1
    if rx == 0 or ry == 0:
        return [p1]
    c, s = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    xp, yp = c * dx + s * dy, -s * dx + c * dy
    lam = xp * xp / (rx * rx) + yp * yp / (ry * ry)
    if lam > 1:
        rx *= math.sqrt(lam); ry *= math.sqrt(lam)
    num = max(0.0, rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp)
    k = math.sqrt(num / (rx * rx * yp * yp + ry * ry * xp * xp)) * (-1 if large == sweep else 1)
    cxp, cyp = k * rx * yp / ry, -k * ry * xp / rx
    cx, cy = c * cxp - s * cyp + (x0 + x1) / 2, s * cxp + c * cyp + (y0 + y1) / 2
    a0 = math.atan2((yp - cyp) / ry, (xp - cxp) / rx)
    a1 = math.atan2((-yp - cyp) / ry, (-xp - cxp) / rx)
    da = a1 - a0
    if sweep and da < 0:
        da += 2 * math.pi
    if not sweep and da > 0:
        da -= 2 * math.pi
    out = []
    for i in range(1, n + 1):
        a = a0 + da * i / n
        out.append((cx + rx * math.cos(a) * c - ry * math.sin(a) * s, cy + rx * math.cos(a) * s + ry * math.sin(a) * c))
    return out


def subpaths(d):
    """The closed outlines of one SVG path (absolute M, L, C, A, Z only: what the logo files use)."""
    tok = re.findall(r'[MLCAZ]|-?\d*\.?\d+(?:e-?\d+)?', d)
    out, cur, i, cmd, pos = [], [], 0, None, (0.0, 0.0)
    while i < len(tok):
        if tok[i] in 'MLCAZ':
            cmd = tok[i]; i += 1
            if cmd == 'Z':
                if len(cur) > 2:
                    out.append(cur)
                cur = []
            continue
        if cmd == 'M':
            if len(cur) > 2:
                out.append(cur)
            pos = (float(tok[i]), float(tok[i + 1])); i += 2
            cur = [pos]; cmd = 'L'
        elif cmd == 'L':
            pos = (float(tok[i]), float(tok[i + 1])); i += 2
            cur.append(pos)
        elif cmd == 'C':
            a = [float(t) for t in tok[i:i + 6]]; i += 6
            p0 = pos
            for k in range(1, 13):
                t = k / 12
                cur.append(tuple((1 - t) ** 3 * p0[j] + 3 * (1 - t) ** 2 * t * a[j] + 3 * (1 - t) * t * t * a[2 + j] + t ** 3 * a[4 + j] for j in (0, 1)))
            pos = (a[4], a[5])
        elif cmd == 'A':
            a = [float(t) for t in tok[i:i + 7]]; i += 7
            pts = arc(pos, a[0], a[1], math.radians(a[2]), int(a[3]), int(a[4]), (a[5], a[6]))
            cur += pts
            pos = (a[5], a[6])
    if len(cur) > 2:
        out.append(cur)
    return out


def inside(pt, poly):
    x, y = pt
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else V2 / 'sn64-v2.kicad_pcb'
    b = pcbnew.LoadBoard(str(path))
    if any(g.GetName() == TAG for g in b.Groups()):
        sys.exit('the board already carries the logos')
    group = pcbnew.PCB_GROUP(b)
    group.SetName(TAG)
    b.Add(group)
    for rel, cx, cy, width in LOGOS:
        text = (REPO / rel).read_text(encoding='utf-8')
        vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', text).group(1).split()]
        scale = width / vb[2]
        x0, y0 = cx - width / 2, cy - vb[3] * scale / 2
        n = 0
        for d in re.findall(r' d="([^"]+)"', text):
            subs = subpaths(d)
            # even-odd: an outline inside an odd number of the others is a hole
            depth = [sum(1 for j, o in enumerate(subs) if j != i and inside(s[0], o)) for i, s in enumerate(subs)]
            for i, s in enumerate(subs):
                if depth[i] % 2:
                    continue
                ps = pcbnew.SHAPE_POLY_SET()
                ps.NewOutline()
                for x, y in s:
                    ps.Append(mm(x0 + (x - vb[0]) * scale), mm(y0 + (y - vb[1]) * scale))
                for j, h in enumerate(subs):
                    if depth[j] == depth[i] + 1 and inside(h[0], s):
                        ps.NewHole()
                        for x, y in h:
                            ps.Append(mm(x0 + (x - vb[0]) * scale), mm(y0 + (y - vb[1]) * scale), 0, ps.HoleCount(0) - 1)
                sh = pcbnew.PCB_SHAPE(b)
                sh.SetShape(pcbnew.SHAPE_T_POLY)
                sh.SetPolyShape(ps)
                sh.SetFilled(True)
                sh.SetWidth(0)
                sh.SetLayer(pcbnew.F_SilkS)
                b.Add(sh)
                group.AddItem(sh)
                n += 1
        print('%s: %d shapes, %.1f x %.1f mm at (%.1f, %.1f)' % (Path(rel).name, n, width, vb[3] * scale, cx, cy))
    pcbnew.SaveBoard(str(path), b)


if __name__ == '__main__':
    main()
    sys.stdout.flush()
