"""Refit the routed v2 board to the tower shell (KiCad's python). Owner decisions 2026-09-30:
one board, SNES cartridge upright on top, socket with ears on the top edge, USB-C above the
console line. Shell envelope: docs/design/v2-shell.md, mechanical/sn64-v2-shell/sn64_v2_shell.py.

Stage "clear" (its own process: KiCad 10's python breaks lookups after board.Remove()):
  - removes the face-mounted socket J2 and all copper above the translator row (y < -47.8; only
    socket nets live there),
  - cuts the five nets that run to the USB-C, its ESD part and VBUS capacitor at the old connector
    (x > 41); the series and pull-up resistors stay beside the FPGA with their routing untouched,
  - trims the remaining copper of those nets that no longer reaches a pad (dangling),
  - removes the outline above the SummerCart64 shell notches and the outer GND pours,
  - writes <out>.json: J2 pin -> net, and the nets to route.
Stage "place":
  - outline: 101.8 mm to 32 mm above the shoulders, 111 mm to 60 mm, 88 mm neck to the top at 70,
  - new J2 (SN64_V2:SNES_Slot_Console_Straddle) on the top edge, nets by pin number,
  - USB-C, ESD and VBUS capacitor to the right edge 50 mm above the shoulders, top mounting holes
    into the wide part,
  - GND / FPGA_3V3 planes enlarged to the new outline, every zone unfilled for routing,
  - every existing track and via LOCKED: KiCadRoutingTools never rips locked copper, so the routing
    that was already there cannot be disturbed (a first run without the lock broke 7 good nets).
Stage "unlock": unlocks every track and via after routing.

  python refit_tower_v2.py clear IN OUT
  python refit_tower_v2.py place IN OUT
  python refit_tower_v2.py unlock IN OUT
"""
import json
import math
import sys
from pathlib import Path

import pcbnew

MM = 1e6
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
HERE = Path(__file__).resolve().parents[1]
LIB = HERE / 'libraries' / 'SN64_V2.pretty'

PLANE_NETS = {'GND', 'FPGA_3V3', 'FPGA_1V1'}
USB_CUT = {'USB_DP', 'USB_DN', 'USB_CC1', 'USB_CC2', 'USB_VBUS'}   # nets that reach the moved parts
USB_MOVE = ('J101', 'U4', 'C301')
Y_CLEAR = -47.8                        # translator top pads end at -47.55
USB_BOX = (41.0, -32.0, 57.0, -10.0)   # x0, y0, x1, y1: the old connector and ESD part, right of R19-R21
POUR_TAG = 'sn64_finish_route'

OUTLINE = [(-50.9, -26.4), (-50.9, -32.0), (-55.5, -32.0), (-55.5, -60.0), (-44.0, -60.0), (-44.0, -70.0),
           (44.0, -70.0), (44.0, -60.0), (55.5, -60.0), (55.5, -32.0), (50.9, -32.0), (50.9, -26.4)]
MOVES = {'J101': (52.4, -50.0, 90), 'U4': (45.5, -50.0, 180), 'C301': (45.5, -45.3, 0),
         'H5': (-52.4, -38.0, 0), 'H6': (52.4, -38.0, 0)}
J2_AT = (0.0, -70.0)


def xy(v):
    return (v.x / MM, v.y / MM)


def seg_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def stage_clear(src, dst):
    b = pcbnew.LoadBoard(str(src))
    j2 = b.FindFootprintByReference('J2')
    pin_net = {p.GetNumber(): p.GetNetname() for p in j2.Pads() if p.GetNumber()}
    j2nets = set(pin_net.values()) - {''}
    skip = {'J2', *USB_MOVE}
    anchors = {}
    for fp in b.GetFootprints():
        if fp.GetReference() in skip:
            continue
        for p in fp.Pads():
            anchors.setdefault(p.GetNetname(), []).append(p)

    items = list(b.GetTracks())
    gone = set()
    for i, t in enumerate(items):
        n = t.GetNetname()
        s, e = xy(t.GetStart()), xy(t.GetEnd())
        if n in j2nets and min(s[1], e[1]) < Y_CLEAR:
            gone.add(i)
        elif n in USB_CUT:
            x0, y0, x1, y1 = USB_BOX
            if any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in (s, e)):
                gone.add(i)
    first = len(gone)

    # trim dangling copper of the affected signal nets (plane nets are anchored by their planes)
    dangle_nets = (j2nets | USB_CUT) - PLANE_NETS
    recs = []
    for i, t in enumerate(items):
        if i in gone or t.GetNetname() not in dangle_nets:
            continue
        if t.GetClass() == 'PCB_VIA':
            recs.append({'i': i, 'via': True, 'net': t.GetNetname(), 'p': xy(t.GetPosition()),
                         'r': t.GetWidth(pcbnew.F_Cu) / MM / 2})
        else:
            recs.append({'i': i, 'via': False, 'net': t.GetNetname(), 'layer': t.GetLayer(),
                         'a': xy(t.GetStart()), 'b': xy(t.GetEnd())})
    alive = {r['i'] for r in recs}

    def pad_hit(net, layer, pt):
        for p in anchors.get(net, []):
            if layer is not None and not p.IsOnLayer(layer):
                continue
            if p.HitTest(V(int(pt[0] * MM), int(pt[1] * MM))):
                return True
        return False

    changed = True
    while changed:
        changed = False
        live = [r for r in recs if r['i'] in alive]
        for r in live:
            same = [o for o in live if o['net'] == r['net'] and o['i'] != r['i'] and o['i'] in alive]
            if r['via']:
                n = sum(1 for o in same if not o['via'] and
                        min(math.dist(o['a'], r['p']), math.dist(o['b'], r['p'])) <= r['r'] + 0.005)
                if pad_hit(r['net'], None, r['p']):
                    n += 1
                if n < 2:
                    alive.discard(r['i']); changed = True
                continue
            for end in (r['a'], r['b']):
                ok = pad_hit(r['net'], r['layer'], end)
                if not ok:
                    for o in same:
                        if o['via']:
                            if math.dist(o['p'], end) <= o['r'] + 0.005:
                                ok = True; break
                        elif o['layer'] == r['layer'] and seg_dist(end, o['a'], o['b']) < 0.01:
                            ok = True; break
                if not ok:
                    alive.discard(r['i']); changed = True
                    break
    trimmed = {r['i'] for r in recs} - alive
    gone |= trimmed

    edges = []
    for d in b.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        ys = (d.GetStart().y / MM, d.GetEnd().y / MM)
        if max(ys) <= -26.39 and min(ys) < -26.5:
            edges.append(d)
    pours = [z for z in b.Zones() if z.GetZoneName().startswith(POUR_TAG)]

    route_nets = sorted((j2nets - PLANE_NETS) | USB_CUT)
    info = {'j2_pin_net': pin_net, 'route_nets': route_nets,
            'removed': {'above_translators_and_usb': first, 'dangling': len(trimmed),
                        'edge_segments': len(edges), 'pours': len(pours)}}
    # every lookup is done; now remove
    for i in sorted(gone):
        b.Remove(items[i])
    for d in edges:
        b.Remove(d)
    for z in pours:
        b.Remove(z)
    b.Remove(j2)
    pcbnew.SaveBoard(str(dst), b)
    Path(str(dst) + '.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
    print(json.dumps(info['removed']), f'route nets: {len(route_nets)}')


def stage_place(src, dst):
    b = pcbnew.LoadBoard(str(src))
    info = json.loads(Path(str(src) + '.json').read_text(encoding='utf-8'))
    for (x0, y0), (x1, y1) in zip(OUTLINE, OUTLINE[1:]):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetStart(V(mm(x0), mm(y0)))
        s.SetEnd(V(mm(x1), mm(y1)))
        s.SetWidth(mm(0.05))
        b.Add(s)

    fp = pcbnew.FootprintLoad(str(LIB), 'SNES_Slot_Console_Straddle')
    fp.SetFPID(pcbnew.LIB_ID('SN64_V2', 'SNES_Slot_Console_Straddle'))
    fp.SetReference('J2')
    fp.SetValue('SNES cartridge socket 62')
    b.Add(fp)
    fp.SetPosition(V(mm(J2_AT[0]), mm(J2_AT[1])))
    missing = []
    for p in fp.Pads():
        n = info['j2_pin_net'].get(p.GetNumber())
        net = b.FindNet(n) if n else None
        if net is None:
            missing.append(p.GetNumber())
        else:
            p.SetNet(net)
    for ref, (x, y, rot) in MOVES.items():
        f = b.FindFootprintByReference(ref)
        f.SetOrientationDegrees(rot)
        f.SetPosition(V(mm(x), mm(y)))

    for z in b.Zones():
        if z.GetIsRuleArea():
            continue
        layers = [b.GetLayerName(l) for l in z.GetLayerSet().Seq()]
        if z.GetNetname() in ('GND', 'FPGA_3V3') and layers in (['In1.Cu'], ['In3.Cu']):
            o = z.Outline()
            o.RemoveAllContours()
            o.NewOutline()
            for x, y in ((-57.0, -71.0), (57.0, -71.0), (57.0, -1.0), (-57.0, -1.0)):
                o.Append(mm(x), mm(y))
        z.UnFill()
    locked = 0
    for t in b.GetTracks():
        if not t.IsLocked():
            t.SetLocked(True)
            locked += 1
    pcbnew.SaveBoard(str(dst), b)
    Path(str(dst) + '.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
    print(f'placed J2 ({len(list(fp.Pads()))} pads, unmatched {missing}), moved {len(MOVES)} parts, '
          f'outline {len(OUTLINE) - 1} segments, locked {locked} tracks/vias')


def stage_unlock(src, dst):
    b = pcbnew.LoadBoard(str(src))
    n = 0
    for t in b.GetTracks():
        if t.IsLocked():
            t.SetLocked(False)
            n += 1
    pcbnew.SaveBoard(str(dst), b)
    print(f'unlocked {n} tracks/vias')


if __name__ == '__main__':
    stage, src, dst = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    {'clear': stage_clear, 'place': stage_place, 'unlock': stage_unlock}[stage](src, dst)
    sys.stdout.flush()
