"""Connect every plane-net SMD pad to its plane with a via (KiCad's python).

The autorouters skip GND / FPGA_3V3 / FPGA_1V1 because those nets own copper zones
(In1.Cu, In3.Cu, In4.Cu island); their pads outside the BGA fan-out are left open.
For each such pad without a same-net via nearby, this adds one 0.45 / 0.2 mm via at
the first free spot among candidates around the pad and a short 0.25 mm track to it
on the pad's layer. "Free" is checked against every pad, track and via on the board
(bucketed on a 1 mm grid so the check is fast) with the fab's hole-to-copper rule in
mind; pads that get no free spot are listed for hand work.

  python add_plane_vias.py board.kicad_pcb [--out routed.kicad_pcb]
"""
import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
PLANES = {'/GND': pcbnew.In1_Cu, '/FPGA_3V3': pcbnew.In3_Cu, '/FPGA_1V1': pcbnew.In4_Cu}
VIA_D, VIA_DRILL, STUB_W = 0.45, 0.20, 0.25
CLEAR = 0.10               # copper clearance
HOLE_CLEAR = 0.20          # hole edge to other copper (PCBWay >= 8 mil)
SAME_NET_REACH = 1.2       # a same-net via this close counts as already connected
CELL = 1.0                 # bucket size in mm; obstacles are indexed by every cell their bbox touches
REACH = 0.8                # farthest a via's copper/hole rule can reach (0.225 + 0.2 + margin)


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class Index:
    def __init__(self):
        self.cells = defaultdict(list)

    def add(self, x0, y0, x1, y1, item):
        for cx in range(int(math.floor(x0 / CELL)), int(math.floor(x1 / CELL)) + 1):
            for cy in range(int(math.floor(y0 / CELL)), int(math.floor(y1 / CELL)) + 1):
                self.cells[(cx, cy)].append(item)

    def near(self, x, y, r=REACH):
        seen = set()
        for cx in range(int(math.floor((x - r) / CELL)), int(math.floor((x + r) / CELL)) + 1):
            for cy in range(int(math.floor((y - r) / CELL)), int(math.floor((y + r) / CELL)) + 1):
                for item in self.cells.get((cx, cy), ()):
                    if id(item) not in seen:
                        seen.add(id(item))
                        yield item


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('board', type=Path)
    ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    board = pcbnew.LoadBoard(str(a.board))
    codes = {n: board.GetNetcodeFromNetname(n) for n in PLANES}
    idx = Index()
    same_net_vias = defaultdict(list)
    # Obstacles in mm: ('pad', x0, y0, x1, y1, net), ('via', x, y, net, dia), ('trk', ax, ay, bx, by, net, w)
    ALL = None   # layer tag meaning "every copper layer" (through vias, THT pads)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            lay = ALL if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else (pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
            it = ('pad', bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6, p.GetNetCode(), lay)
            idx.add(it[1], it[2], it[3], it[4], it)
    for t in board.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            x, y = t.GetPosition().x / 1e6, t.GetPosition().y / 1e6
            it = ('via', x, y, t.GetNetCode(), t.GetWidth(pcbnew.F_Cu) / 1e6)   # KiCad 10: GetWidth() without a layer asserts
            idx.add(x - 0.3, y - 0.3, x + 0.3, y + 0.3, it)
            same_net_vias[t.GetNetCode()].append((x, y))
        else:
            ax, ay, bx, by = t.GetStart().x / 1e6, t.GetStart().y / 1e6, t.GetEnd().x / 1e6, t.GetEnd().y / 1e6
            it = ('trk', ax, ay, bx, by, t.GetNetCode(), t.GetWidth() / 1e6, t.GetLayer())
            idx.add(min(ax, bx) - 0.3, min(ay, by) - 0.3, max(ax, bx) + 0.3, max(ay, by) + 0.3, it)

    r_cu, r_hole = VIA_D / 2, VIA_DRILL / 2
    need_other = max(r_cu + CLEAR, r_hole + HOLE_CLEAR)
    keepouts = [z for z in board.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowVias()]
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    edge_chains = [outline.Outline(i) for i in range(outline.OutlineCount())]
    edge_chains += [outline.Hole(i, j) for i in range(outline.OutlineCount()) for j in range(outline.HoleCount(i))]
    edge_segs = [ch.CSegment(k) for ch in edge_chains for k in range(ch.SegmentCount())]
    EDGE_KEEP = mm(0.55)   # via copper radius 0.225 + 0.3 copper-to-edge

    def free(x, y, net, layer=ALL):
        """layer=ALL: a via spot (copper on every layer matters); layer=F_Cu/B_Cu: a stub point on that layer."""
        pt = V(mm(x), mm(y))
        if not outline.Contains(pt):
            return False
        for s in edge_segs:          # (a closed chain's Collide() treats the inside as a hit, so use the segments)
            if s.Distance(pt) < EDGE_KEEP:
                return False
        for z in keepouts:
            if z.Outline().Contains(pt):
                return False
        for it in idx.near(x, y):
            if it[0] == 'pad':
                _, x0, y0, x1, y1, n, lay = it
                if layer is not ALL and lay is not ALL and lay != layer:
                    continue
                d = math.hypot(max(x0 - x, 0, x - x1), max(y0 - y, 0, y - y1))
                if n == net:
                    if layer is ALL and d < 0.05:     # a via must not sit on a same-net pad; a stub may cross its own pad
                        return False
                    continue
                if d < need_other:
                    return False
            elif it[0] == 'via':
                _, vx, vy, n, w = it
                if math.hypot(vx - x, vy - y) < r_cu + w / 2 + (CLEAR if n == net else HOLE_CLEAR) + 0.05:
                    return False
            else:
                _, ax, ay, bx, by, n, w, lay = it
                if layer is not ALL and lay != layer:
                    continue
                d = seg_dist(x, y, ax, ay, bx, by) - w / 2
                if (n != net and d < need_other) or (n == net and d < r_cu):
                    return False
        return True

    added, unplaced = 0, []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            net = p.GetNetname()
            if net not in PLANES or p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                continue
            px, py = p.GetPosition().x / 1e6, p.GetPosition().y / 1e6
            if any(math.hypot(vx - px, vy - py) < SAME_NET_REACH for (vx, vy) in same_net_vias[codes[net]]):
                continue
            layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
            bb = p.GetBoundingBox()
            hw, hh = bb.GetWidth() / 2e6, bb.GetHeight() / 2e6
            placed = False
            # The N64 edge fingers (J1) sit inside the finger keep-out: their vias go further up the board.
            # Nearest spots first; on a routed board the stub may have to reach a few mm (a longer
            # decoupling stub is a compromise to fix by hand later, an open pad is not usable at all).
            dists = (0.7, 0.85, 1.0, 1.2, 1.6, 2.0, 2.5, 3.0) if fp.GetReference() != 'J1' else (1.5, 2.0, 2.5, 3.0, 3.5)
            for dist in dists:
                for ang in (0, 180, 90, 270, 45, 135, 225, 315):
                    r = math.radians(ang)
                    x = px + math.cos(r) * (dist + hw * abs(math.cos(r)))
                    y = py + math.sin(r) * (dist + hh * abs(math.sin(r)))
                    if not free(x, y, codes[net]):
                        continue
                    n_pts = max(3, int(math.hypot(x - px, y - py) / 0.15))     # sample the stub every 0.15 mm
                    if any(not free(px + (x - px) * f, py + (y - py) * f, codes[net], layer)
                           for f in (k / n_pts for k in range(1, n_pts))):
                        continue
                    via = pcbnew.PCB_VIA(board)
                    via.SetViaType(pcbnew.VIATYPE_THROUGH)
                    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    via.SetPosition(V(mm(x), mm(y)))
                    via.SetDrill(mm(VIA_DRILL)); via.SetWidth(mm(VIA_D)); via.SetNetCode(codes[net])
                    board.Add(via)
                    t = pcbnew.PCB_TRACK(board)
                    t.SetStart(V(mm(px), mm(py))); t.SetEnd(V(mm(x), mm(y))); t.SetWidth(mm(STUB_W))
                    t.SetLayer(layer); t.SetNetCode(codes[net])
                    board.Add(t)
                    it = ('via', x, y, codes[net], VIA_D)
                    idx.add(x - 0.3, y - 0.3, x + 0.3, y + 0.3, it)
                    it2 = ('trk', px, py, x, y, codes[net], STUB_W, layer)
                    idx.add(min(px, x) - 0.3, min(py, y) - 0.3, max(px, x) + 0.3, max(py, y) + 0.3, it2)
                    same_net_vias[codes[net]].append((x, y))
                    added += 1
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                unplaced.append(f'{fp.GetReference()}.{p.GetNumber()} {net}')
    out = a.out or a.board
    pcbnew.SaveBoard(str(out), board)
    print(f'plane vias added: {added}; pads without a free spot: {len(unplaced)}')
    for u in unplaced:
        print('  ', u)
    sys.stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
