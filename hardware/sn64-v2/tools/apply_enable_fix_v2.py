"""Carry the schematic change of 2026-10-02 into the routed v2 board without losing its routing
(KiCad's python). Run once, after build_v2_schematic.py --force and the netlist export:

  python apply_enable_fix_v2.py [--board sn64-v2.kicad_pcb] [--dry-run]

What changed in the schematic, from the makers' data sheets (docs/design/board-verification.md):
  * U204 (SN74ALVC164245) byte 2 brings CIC data, /IRQ and /RESET from the socket to the FPGA.
    Its /OE (pin 25) was tied to ground: on all the time, also while the byte's 5 V side has no
    supply. TI SCAS416Q section 10: /OE is to be high until both supplies are up. It is now
    SENSE_OE_N, driven by the FPGA ball that carried the unused EXPAND sense (U19) and pulled up
    by a new 100 k (R214). The four unused channels have both pins on ground.
  * U6 (TLA2528) ADDR (pin 11) was tied to ground. TI SBAS961A table 2 lists eight settings; none
    is "straight to ground", and the address the logic uses (0x10) is the one with the pin open.
    The pin is now open.

On the board:
  1. every pad takes its net from validation/sn64-v2.xml (10 pads change);
  2. the trace of the old L_EXPAND net becomes SENSE_OE_N; its last 6 mm on F.Cu to U204 pad 30
     and the via there go, and it continues on B.Cu to R214 and to the via beside pad 25, which
     with its stub changes from GND to SENSE_OE_N;
  3. R214 (0603) is placed on the bottom side beside U204's 3.3 V via;
  4. U204 pads 26-30 are joined by a ground bar (pad 28 is ground and has its via), pad 19 is
     joined to pad 20 (ground);
  5. the ground stub at U6 pad 11 goes; the branch of SNES_EXPAND that ran to U204 pad 19 goes
     (dead ends of the two nets are pruned);
  6. the planes are filled again.
The new B.Cu tracks are found by a small grid search that keeps 0.15 mm from everything else on
that layer; KiCad's own DRC is the check (validation/pcb-drc.json).
"""
import argparse
import heapq
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
SHARE_FP = Path('C:/Program Files/KiCad/10.0/share/kicad/footprints')
mm = pcbnew.FromMM
MM = pcbnew.ToMM
V = pcbnew.VECTOR2I
TRACK_W, CLEAR, STEP = 0.15, 0.15, 0.05

R214_AT = (-39.0, -41.9)                    # bottom side, between U204's ground and 3.3 V vias
VIA_3V3 = (-38.75, -40.725)                 # U204 pin 31's via to the 3.3 V plane
VIA_PAD25 = (-42.6, -39.288)                # the via beside U204 pad 25 (was GND)
OLD_VIA = (-35.1, -43.3)                    # where the old trace came up to F.Cu for pad 30


def near(a, b, tol=0.02):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def xy(p):
    return (MM(p.x), MM(p.y))


def is_via(t):
    return t.GetClass() == 'PCB_VIA'


def seg_dist(p, a, b):
    """Distance from point p to segment a-b."""
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def rect_dist(p, r):
    dx = max(r[0] - p[0], 0.0, p[0] - r[2])
    dy = max(r[1] - p[1], 0.0, p[1] - r[3])
    return math.hypot(dx, dy)


def route(board, layer, net_name, a, b, window):
    """A polyline from a to b on one copper layer, CLEAR away from every other net's copper there."""
    x0, y0, x1, y1 = window
    nx, ny = int(round((x1 - x0) / STEP)) + 1, int(round((y1 - y0) / STEP)) + 1
    segs, discs, rects = [], [], []
    need = CLEAR + TRACK_W / 2
    for t in board.GetTracks():
        if t.GetNetname() == net_name:
            continue
        if is_via(t):
            p = xy(t.GetPosition())
            if x0 - 1 <= p[0] <= x1 + 1 and y0 - 1 <= p[1] <= y1 + 1:
                discs.append((p, MM(t.GetWidth(layer)) / 2))
        elif t.GetLayer() == layer:
            s, e = xy(t.GetStart()), xy(t.GetEnd())
            if min(s[0], e[0]) <= x1 + 1 and max(s[0], e[0]) >= x0 - 1 and min(s[1], e[1]) <= y1 + 1 and max(s[1], e[1]) >= y0 - 1:
                segs.append((s, e, MM(t.GetWidth()) / 2))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net_name or not (p.IsOnLayer(layer)):
                continue
            bb = p.GetBoundingBox()
            r = (MM(bb.GetLeft()), MM(bb.GetTop()), MM(bb.GetRight()), MM(bb.GetBottom()))
            if r[0] <= x1 + 1 and r[2] >= x0 - 1 and r[1] <= y1 + 1 and r[3] >= y0 - 1:
                rects.append(r)

    def blocked(i, j):
        p = (x0 + i * STEP, y0 + j * STEP)
        for c, r in discs:
            if math.hypot(p[0] - c[0], p[1] - c[1]) < r + need:
                return True
        for r in rects:
            if rect_dist(p, r) < need:
                return True
        for s, e, h in segs:
            if seg_dist(p, s, e) < h + need:
                return True
        return False

    cache = {}

    def free(i, j):
        if not (0 <= i < nx and 0 <= j < ny):
            return False
        if (i, j) not in cache:
            cache[(i, j)] = not blocked(i, j)
        return cache[(i, j)]

    def cell(p):
        return (int(round((p[0] - x0) / STEP)), int(round((p[1] - y0) / STEP)))

    start, goal = cell(a), cell(b)
    # the two ends sit on this net's own copper (a pad, a via): let the search leave and arrive
    for c in (start, goal):
        for di in range(-9, 10):
            for dj in range(-9, 10):
                if math.hypot(di, dj) * STEP <= 0.45:
                    cache.setdefault((c[0] + di, c[1] + dj), True)
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    best = {(start, None): 0.0}
    heap = [(0.0, 0.0, start, None)]
    came = {}
    end = None
    while heap:
        _, g, c, d = heapq.heappop(heap)
        if c == goal:
            end = (c, d)
            break
        if g > best.get((c, d), 1e18):
            continue
        for nd in dirs:
            n = (c[0] + nd[0], c[1] + nd[1])
            if not free(*n):
                continue
            cost = g + (1.4142 if nd[0] and nd[1] else 1.0) + (0.0 if d in (None, nd) else 3.0)      # a turn costs three steps
            if cost < best.get((n, nd), 1e18):
                best[(n, nd)] = cost
                came[(n, nd)] = (c, d)
                h = max(abs(n[0] - goal[0]), abs(n[1] - goal[1])) + 0.4142 * min(abs(n[0] - goal[0]), abs(n[1] - goal[1]))
                heapq.heappush(heap, (cost + h, cost, n, nd))
    if end is None:
        raise SystemExit('no path on %s from %s to %s' % (board.GetLayerName(layer), a, b))
    cells = []
    k = end
    while k in came or k[1] is None:
        cells.append(k[0])
        if k[1] is None:
            break
        k = came[k]
    cells.reverse()
    pts = [a]
    for idx, c in enumerate(cells):
        p = (round(x0 + c[0] * STEP, 3), round(y0 + c[1] * STEP, 3))
        if 0 < idx < len(cells) - 1:
            pc, nc = cells[idx - 1], cells[idx + 1]
            if (c[0] - pc[0], c[1] - pc[1]) == (nc[0] - c[0], nc[1] - c[1]):
                continue                                 # straight on: no corner here
        pts.append(p)
    pts.append(b)
    out = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--board', type=Path, default=V2 / 'sn64-v2.kicad_pcb')
    ap.add_argument('--netlist', type=Path, default=V2 / 'validation/sn64-v2.xml')
    ap.add_argument('--dry-run', action='store_true', help='do everything, report, but do not save')
    args = ap.parse_args()
    board = pcbnew.LoadBoard(str(args.board))
    if board.FindFootprintByReference('R214') is not None:
        sys.exit('R214 is already on this board: the change has been applied')
    F, B = pcbnew.F_Cu, pcbnew.B_Cu

    def net(name):
        ni = board.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
        return ni

    def add_track(layer, name, a, b, w=TRACK_W):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(V(mm(a[0]), mm(a[1]))); t.SetEnd(V(mm(b[0]), mm(b[1]))); t.SetWidth(mm(w)); t.SetLayer(layer); t.SetNet(net(name))
        board.Add(t)
        return t

    log = []
    # ---- 3. the new resistor, before the pads take their nets
    r214 = pcbnew.FootprintLoad(str(SHARE_FP / 'Resistor_SMD.pretty'), 'R_0603_1608Metric')
    r214.SetReference('R214'); r214.SetValue('100k')
    board.Add(r214)
    r214.SetPosition(V(mm(R214_AT[0]), mm(R214_AT[1])))
    r214.Flip(r214.GetPosition(), False)
    for rot in (0, 180):                                 # pad 1 (3.3 V) towards the 3.3 V via
        r214.SetOrientationDegrees(rot)
        pad1 = next(p for p in r214.Pads() if p.GetNumber() == '1')
        if MM(pad1.GetPosition().x) > R214_AT[0]:
            break
    log.append('R214 100k 0603 on %s at %s, rotation %d' % (board.GetLayerName(r214.GetLayer()), R214_AT, rot))

    # ---- 1. every pad takes its net from the netlist
    root = ET.parse(args.netlist).getroot()
    want = {(node.get('ref'), node.get('pin')): n.get('name') for n in root.find('nets') for node in n}
    changed = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            key = (fp.GetReference(), p.GetNumber())
            if key in want and p.GetNetname() != want[key]:
                changed[key] = (p.GetNetname(), want[key], xy(p.GetPosition()))
                p.SetNet(net(want[key]))
    for key, (old, new, pos) in sorted(changed.items()):
        log.append('pad %s.%s: %s -> %s' % (key[0], key[1], old or '(none)', new))
    # pads that had no net at all and are single-pad nets in the netlist (open edge fingers): a name only
    changed = {k: v for k, v in changed.items() if not (v[0] == '' and v[1].startswith('unconnected-'))}
    expect = {('R214', '1'), ('R214', '2'), ('U1', 'U19'), ('U204', '19'), ('U204', '25'), ('U204', '26'), ('U204', '27'),
              ('U204', '29'), ('U204', '30'), ('U6', '11')}
    if set(changed) != expect:
        sys.exit('pads changed are not the ten expected: %s' % sorted(set(changed) ^ expect))

    # ---- 2. the old L_EXPAND copper is SENSE_OE_N; its end at pad 30 goes
    sense = net('SENSE_OE_N')
    removed = []
    for t in list(board.GetTracks()):
        if t.GetNetname() != 'L_EXPAND':
            continue
        t.SetNet(sense)
        if is_via(t):
            if near(xy(t.GetPosition()), OLD_VIA):
                removed.append(t)
        elif t.GetLayer() == F and all(-39.7 <= p[0] <= -35.0 and -43.4 <= p[1] <= -39.7 for p in (xy(t.GetStart()), xy(t.GetEnd()))):
            removed.append(t)
    if len(removed) != 6:
        sys.exit('expected the via and five F.Cu segments of the old trace at U204 pad 30, found %d items' % len(removed))
    pad25 = xy(next(p for p in board.FindFootprintByReference('U204').Pads() if p.GetNumber() == '25').GetPosition())
    renet = 0
    for t in board.GetTracks():
        if t.GetNetname() != 'GND':
            continue
        if is_via(t) and near(xy(t.GetPosition()), VIA_PAD25):
            t.SetNet(sense); renet += 1
        elif not is_via(t) and t.GetLayer() == F and {True} == {near(p, pad25) or near(p, VIA_PAD25) for p in (xy(t.GetStart()), xy(t.GetEnd()))}:
            t.SetNet(sense); renet += 1
    if renet != 2:
        sys.exit('expected the stub and the via beside U204 pad 25, found %d' % renet)
    # ---- 5a. the ground stub at U6 pad 11
    pad11 = changed[('U6', '11')][2]
    for t in list(board.GetTracks()):
        if not is_via(t) and t.GetNetname() == 'GND' and t.GetLayer() == F and (near(xy(t.GetStart()), pad11) or near(xy(t.GetEnd()), pad11)):
            removed.append(t)
    if len(removed) != 7:
        sys.exit('expected one ground stub at U6 pad 11')
    for t in removed:
        board.Remove(t)
    log.append('removed: the via at %s, five F.Cu segments of the old trace to U204 pad 30, the ground stub at U6 pad 11' % (OLD_VIA,))

    # ---- 4. ground bars across the pads that are now ground
    u204 = {p.GetNumber(): xy(p.GetPosition()) for p in board.FindFootprintByReference('U204').Pads()}
    add_track(F, 'GND', u204['26'], u204['30'], 0.25)
    add_track(F, 'GND', u204['19'], u204['20'], 0.25)
    log.append('ground bars on F.Cu: U204 pads 26-30 and 19-20')

    # ---- 2b. the new B.Cu run: old trace end -> R214 pad 2 -> the via beside pad 25; R214 pad 1 -> the 3.3 V via
    pads214 = {p.GetNumber(): xy(p.GetPosition()) for p in r214.Pads()}
    window = (-46.0, -45.5, -34.0, -37.5)
    total = 0.0
    for a, b in ((OLD_VIA, pads214['2']), (pads214['2'], VIA_PAD25)):
        pts = route(board, B, 'SENSE_OE_N', a, b, window)
        for p, q_ in zip(pts, pts[1:]):
            add_track(B, 'SENSE_OE_N', p, q_)
            total += math.hypot(q_[0] - p[0], q_[1] - p[1])
        log.append('B.Cu SENSE_OE_N: ' + ' -> '.join('(%.2f, %.2f)' % p for p in pts))
    pts = route(board, B, 'FPGA_3V3', pads214['1'], VIA_3V3, window)
    for p, q_ in zip(pts, pts[1:]):
        add_track(B, 'FPGA_3V3', p, q_, 0.25)
    log.append('B.Cu FPGA_3V3: ' + ' -> '.join('(%.2f, %.2f)' % p for p in pts))
    log.append('new SENSE_OE_N track on B.Cu: %.1f mm' % total)

    # ---- 5b. dead ends of the two nets that lost a pad
    def prune(name):
        gone = 0
        while True:
            tracks = [t for t in board.GetTracks() if t.GetNetname() == name]
            pads = [(p, p.GetBoundingBox()) for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == name]

            def anchored(pt, layer, me):
                for p, bb in pads:
                    if (p.IsOnLayer(layer)) and MM(bb.GetLeft()) - 0.01 <= pt[0] <= MM(bb.GetRight()) + 0.01 and MM(bb.GetTop()) - 0.01 <= pt[1] <= MM(bb.GetBottom()) + 0.01:
                        return True
                for o in tracks:
                    if o is me:
                        continue
                    if is_via(o):
                        if math.hypot(pt[0] - MM(o.GetPosition().x), pt[1] - MM(o.GetPosition().y)) <= MM(o.GetWidth(layer)) / 2 + 0.01:
                            return True
                    elif o.GetLayer() == layer and seg_dist(pt, xy(o.GetStart()), xy(o.GetEnd())) <= MM(o.GetWidth()) / 2 + 0.01:
                        return True
                return False

            dead = []
            for t in tracks:
                if is_via(t):
                    c = xy(t.GetPosition())
                    touching = sum(1 for o in tracks if o is not t and not is_via(o) and
                                   min(math.hypot(c[0] - e[0], c[1] - e[1]) for e in (xy(o.GetStart()), xy(o.GetEnd()))) <= MM(t.GetWidth(F)) / 2 + 0.01)
                    on_pad = any(MM(bb.GetLeft()) <= c[0] <= MM(bb.GetRight()) and MM(bb.GetTop()) <= c[1] <= MM(bb.GetBottom()) for p, bb in pads)
                    if touching + (1 if on_pad else 0) < 2:
                        dead.append(t)
                elif not (anchored(xy(t.GetStart()), t.GetLayer(), t) and anchored(xy(t.GetEnd()), t.GetLayer(), t)):
                    dead.append(t)
            if not dead:
                return gone
            for t in dead:
                board.Remove(t)
            gone += len(dead)

    for name in ('SNES_EXPAND', 'SENSE_OE_N'):
        n = prune(name)
        log.append('%s: %d dead-end tracks and vias removed' % (name, n))

    # ---- every pad agrees with the netlist; planes again; save
    wrong = [(fp.GetReference(), p.GetNumber()) for fp in board.GetFootprints() for p in fp.Pads()
             if (fp.GetReference(), p.GetNumber()) in want and p.GetNetname() != want[(fp.GetReference(), p.GetNumber())]]
    if wrong:
        sys.exit('pads that do not agree with the netlist: %s' % wrong)
    board.BuildListOfNets()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    for line in log:
        print(line)
    if args.dry_run:
        print('dry run: not saved')
    else:
        pcbnew.SaveBoard(str(args.board), board)
        print('saved', args.board.name)


if __name__ == '__main__':
    main()
