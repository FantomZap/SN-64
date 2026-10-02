"""Put the part labels of the v2 board's silkscreen where they can be printed (KiCad's python).

  python tidy_silk_v2.py [--board sn64-v2.kicad_pcb] [--out OUT.kicad_pcb]

KiCad's rule check had 221 silkscreen warnings on the routed board, every one about a part label:
on a pad, across another part's outline, or on another label. Copper is not touched.

  * Every label becomes 0.8 mm high with 0.15 mm strokes, the smallest PCBWay prints.
  * Each label is tried at places round its own part (four sides, three places along each side,
    upright or on its side, three distances). The first place counts where the label keeps clear of
    every pad opening, every hole, every other silkscreen item and the board's edge.
  * A label that fits nowhere is hidden on the silkscreen. The part keeps its name on the
    fabrication layer, which the assembly drawing shows, and in the placement file.
  * Silkscreen lines of a part that reach to within 0.3 mm of the board's edge are removed (the
    USB-C receptacle overhangs the edge, and its outline with it).

Parts are taken largest first, so that the labels of the chips get the good places.
"""
import argparse
import sys
from pathlib import Path

import pcbnew

V2 = Path(__file__).resolve().parents[1]
MM = pcbnew.ToMM
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
HEIGHT, STROKE = 0.8, 0.15
GAP = 0.15                      # between a label and anything else
EDGE = 0.35                     # between a label and the board's edge
SIDES = ((pcbnew.F_Cu, pcbnew.F_SilkS, pcbnew.F_Mask), (pcbnew.B_Cu, pcbnew.B_SilkS, pcbnew.B_Mask))


def box(item, grow=0.0):
    bb = item.GetBoundingBox()
    return (MM(bb.GetLeft()) - grow, MM(bb.GetTop()) - grow, MM(bb.GetRight()) + grow, MM(bb.GetBottom()) + grow)


def hit(a, c):
    return a[0] < c[2] and c[0] < a[2] and a[1] < c[3] and c[1] < a[3]


class Index:
    def __init__(self):
        self.cells = {}

    def add(self, r):
        for gx in range(int(r[0] // 2), int(r[2] // 2) + 1):
            for gy in range(int(r[1] // 2), int(r[3] // 2) + 1):
                self.cells.setdefault((gx, gy), []).append(r)

    def any(self, r):
        for gx in range(int(r[0] // 2), int(r[2] // 2) + 1):
            for gy in range(int(r[1] // 2), int(r[3] // 2) + 1):
                for o in self.cells.get((gx, gy), ()):
                    if hit(r, o):
                        return True
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--board', type=Path, default=V2 / 'sn64-v2.kicad_pcb')
    ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    b = pcbnew.LoadBoard(str(a.board))
    outline = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(outline, False)

    def inside(r):
        pts = [(r[0] - EDGE, r[1] - EDGE), (r[2] + EDGE, r[1] - EDGE), (r[0] - EDGE, r[3] + EDGE), (r[2] + EDGE, r[3] + EDGE),
               ((r[0] + r[2]) / 2, r[1] - EDGE), ((r[0] + r[2]) / 2, r[3] + EDGE)]
        return all(outline.Contains(V(mm(x), mm(y))) for x, y in pts)

    doomed = []                                 # outlines that reach the board's edge; removed at the very end,
    for fp in b.GetFootprints():                # because KiCad 10's python breaks every lookup after a Remove()
        for g in fp.GraphicalItems():
            if g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) and not inside(box(g, -EDGE + 0.3)):
                doomed.append((fp, g))
    going = [g for _, g in doomed]

    placed = moved = hidden = 0
    for cu, silk, mask in SIDES:
        fixed = Index()                         # what a label on this face must keep clear of
        for fp in b.GetFootprints():
            for p in fp.Pads():
                d = p.GetDrillSize()
                if p.IsOnLayer(mask) or d.x > 0:
                    fixed.add(box(p, GAP))
            for g in fp.GraphicalItems():
                if g.GetLayer() == silk and not any(g is o or g == o for o in going):
                    fixed.add(box(g, GAP))
        for g in b.GetDrawings():
            if g.GetLayer() == silk:
                fixed.add(box(g, GAP))
        parts = [fp for fp in b.GetFootprints() if fp.GetLayer() == cu]
        parts.sort(key=lambda f: -(f.GetBoundingBox(False).GetWidth() * f.GetBoundingBox(False).GetHeight()))
        for fp in parts:
            ref = fp.Reference()
            if ref.GetLayer() != silk:
                continue
            was_visible = ref.IsVisible()
            ref.SetTextSize(V(mm(HEIGHT), mm(HEIGHT)))
            ref.SetTextThickness(mm(STROKE))
            ref.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
            ref.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
            ref.SetVisible(True)
            bb = fp.GetBoundingBox(False)
            x0, y0, x1, y1 = MM(bb.GetLeft()), MM(bb.GetTop()), MM(bb.GetRight()), MM(bb.GetBottom())
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            before = (ref.GetPosition().x, ref.GetPosition().y, ref.GetTextAngleDegrees())
            found = None
            for away in (0.2, 0.6, 1.1):
                for angle in (0.0, 90.0):
                    ref.SetTextAngleDegrees(angle)
                    ref.SetPosition(V(mm(cx), mm(cy)))
                    tb = box(ref)
                    tw, th = tb[2] - tb[0], tb[3] - tb[1]
                    spots = []
                    for f in (0.0, -0.5, 0.5):
                        spots += [(cx + f * (x1 - x0), y0 - away - th / 2), (cx + f * (x1 - x0), y1 + away + th / 2),
                                  (x0 - away - tw / 2, cy + f * (y1 - y0)), (x1 + away + tw / 2, cy + f * (y1 - y0))]
                    for sx, sy in spots:
                        ref.SetPosition(V(mm(sx), mm(sy)))
                        r = box(ref)
                        if inside(r) and not fixed.any(r):
                            found = (sx, sy, angle)
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                ref.SetTextAngleDegrees(found[2])
                ref.SetPosition(V(mm(found[0]), mm(found[1])))
                fixed.add(box(ref, GAP))
                placed += 1
                moved += (ref.GetPosition().x, ref.GetPosition().y, ref.GetTextAngleDegrees()) != before
            else:
                ref.SetTextAngleDegrees(0.0)
                ref.SetPosition(V(mm(cx), mm(cy)))
                ref.SetVisible(False)
                hidden += 1
    for fp, g in doomed:
        fp.Remove(g)
    out = a.out or a.board
    pcbnew.SaveBoard(str(out), b)
    print('labels printed %d (%d moved), hidden %d; %d silkscreen lines at the board edge removed; saved %s'
          % (placed, moved, hidden, len(doomed), Path(out).name))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
