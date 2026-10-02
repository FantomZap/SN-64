"""Carry the USB change of 2026-10-02 into the routed v2 board without losing its routing
(KiCad's python). Owner: "Add back just the usb loader chip and put the usb on the right side of
the cart", and the FPGA's own USB device is taken out.

What changes on the board
  * the USB-C receptacle J101, its ESD part U4 and the VBUS capacitor C301 go from the board's +X
    edge (the player's left) to the -X edge (the player's right), same height above the shoulders;
  * the loader chip U13 (FT231XS) with C41-C45 and the series resistors R19, R20 goes on the back
    of the board beside it; R41 pulls JTAG TCK down;
  * the open-drain driver U205 moves 5 mm toward the middle to make room for the receptacle's
    pads; its PROGRAMN gate is unused now;
  * R21 (D+ pull-up of the FPGA's USB device) and R201 (pull-up of the PROGRAMN gate's input) go,
    and so does every track of the four FPGA balls that carried USB and the reboot line.

Stages (each its own process: KiCad 10's python breaks lookups after board.Remove()):
  clear   removes the copper of the nets that end, the copper of the nets that lose or move a
          pad back to the first junction that still serves another pad, the plane stubs of the
          parts that move, and the two resistors. Writes <out>.json.
  place   every pad takes its net from validation/sn64-v2.xml; new parts are added, moved parts
          moved; every zone is unfilled.
  (add_plane_vias_v2.py here: the ground and 3.3 V pads of the new and moved parts get their
          vias while the area is still open. Added after routing, two ground pins found no spot.)
  lock    every track and via LOCKED: KiCadRoutingTools never rips locked copper
          (docs/design/pcb-routing.md).
  (KiCadRoutingTools routes the nets listed in <out>.json.)
  unlock  after routing.
  (finish_route_v2.py --refill-only --no-import, then KiCad's rule check.)
  tidy    removes what the router left behind on the routed nets: the vias and track ends that
          KiCad's rule check reports as leading nowhere (its report is the third argument). A
          first version judged that itself and took two good traces whose ends sit 0.015 mm
          outside their pad; KiCad counts the overlapping copper, and so does this now.
          Repeat check and tidy until nothing is removed. A via with two track ends inside it
          stays although KiCad lists it: its copper is what joins them.

  python apply_usb_loader_v2.py clear|place|lock|unlock IN.kicad_pcb OUT.kicad_pcb
  python apply_usb_loader_v2.py tidy IN.kicad_pcb OUT.kicad_pcb DRC.json
"""
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
SHARE_FP = Path('C:/Program Files/KiCad/10.0/share/kicad/footprints')
NETLIST = V2 / 'validation/sn64-v2.xml'
MM = 1e6
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
F, B = pcbnew.F_Cu, pcbnew.B_Cu

PLANE_NETS = {'GND', 'FPGA_3V3', 'FPGA_1V1'}
REMOVED = ('R21', 'R201')
# nets that end, or whose every pad moves: all their copper goes
FULL = {'USB_PU', 'PROGRAMN_PULL', 'USB_DP_F', 'USB_DN_F', 'USB_DP', 'USB_DN'}
# nets that lose a pad or have one moved: copper goes back to the first junction that still serves a pad
PARTIAL = {'USB_CC1', 'USB_CC2', 'USB_VBUS', 'FPGA_PROGRAMN', 'CIC_DATA0_OD', 'SNES_CIC_DATA0', 'CIC_DATA1_OD',
           'SNES_CIC_DATA1', 'SNES_RESET_N', 'RESET_PULL_OD'}
JTAG = ['JTAG_TCK', 'JTAG_TMS', 'JTAG_TDI', 'JTAG_TDO']
# reference: (x, y, side, footprint library, footprint, value, {pad: (x, y)} wanted after placing)
# The pad targets fix the rotation: the script tries the four rotations and keeps the one that fits.
NEW = {
    # loader chip on the back, long side up the board: USB and supply pins (11-16) toward the middle of
    # the board where their parts sit, JTAG pins (5, 7, 8, 9) on the edge side, leaving under the body
    'U13': (-43.1, -26.0, B, 'Package_SO', 'SSOP-20_3.9x8.7mm_P0.635mm', 'FT231XS-R',
            {'11': (-40.5, -28.857), '10': (-45.7, -28.857)}),
    'C41': (-38.0, -25.7, B, 'Capacitor_SMD', 'C_0603_1608Metric', '100nF 16V X7R', {'2': (-38.79, -25.7)}),    # GND toward pin 16
    'C42': (-38.0, -27.3, B, 'Capacitor_SMD', 'C_0603_1608Metric', '100nF 16V X7R', {'1': (-38.79, -27.3)}),    # 3V3OUT, pins 13/14
    'C43': (-45.4, -20.5, B, 'Capacitor_SMD', 'C_0603_1608Metric', '100nF 16V X7R', {'1': (-46.19, -20.5)}),    # VCCIO, pin 3
    'C44': (-46.5, -36.4, B, 'Capacitor_SMD', 'C_0603_1608Metric', '47pF 50V C0G', {'1': (-47.29, -36.4)}),     # D+
    'C45': (-46.5, -31.6, B, 'Capacitor_SMD', 'C_0603_1608Metric', '47pF 50V C0G', {'1': (-47.29, -31.6)}),     # D-
    'R41': (-41.9, -20.5, B, 'Resistor_SMD', 'R_0603_1608Metric', '4.7k', {'1': (-41.11, -20.5)}),              # GND end toward the ground vias
}
# reference: (x, y, {pad: (x, y)} wanted after moving, new value or None)
MOVE = {
    'J101': (-52.4, -32.5, {'A6': (-49.35, -32.75)}, None),
    'U4': (-45.5, -32.5, {'1': (-46.637, -33.45)}, None),
    'C301': (-45.5, -37.0, {'1': (-44.55, -37.0)}, None),
    'U205': (-39.0, -34.0, {'1': (-36.138, -32.05)}, None),
    'R19': (-46.5, -34.8, {'1': (-47.29, -34.8)}, '27'),
    'R20': (-46.5, -33.2, {'1': (-47.29, -33.2)}, '27'),
}
# The receptacle's metal body lies on the board from the edge to the outer ends of its signal pads
# (JAE drawing SJ122205: 8.94 wide, 6.9 deep). No track and no via under it on the component side;
# a first routing run put a JTAG line there.
USB_BODY = (-56.5, -37.3, -50.0, -27.7)
ROUTE = sorted((FULL - {'USB_PU', 'PROGRAMN_PULL'}) | PARTIAL | {'FT_3V3'} | set(JTAG))


def xy(v):
    return (v.x / MM, v.y / MM)


def seg_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def is_via(t):
    return t.GetClass() == 'PCB_VIA'


def pad_box(p):
    bb = p.GetBoundingBox()
    return (bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM)


def in_box(pt, box, tol=0.01):
    return box[0] - tol <= pt[0] <= box[2] + tol and box[1] - tol <= pt[1] <= box[3] + tol


def stage_clear(src, dst):
    b = pcbnew.LoadBoard(str(src))
    if b.FindFootprintByReference('U13') is not None:
        sys.exit('U13 is already on this board: the change has been applied')
    lost = set(MOVE) | set(REMOVED)                 # footprints whose pads no longer hold copper where they are
    anchors, lost_plane_pads = {}, []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            n = p.GetNetname()
            if ref in lost:
                if n in PLANE_NETS:
                    lost_plane_pads.append((n, pad_box(p), [l for l in (F, B) if p.IsOnLayer(l)]))
                continue
            if ref == 'U1' and n in FULL:
                continue
            anchors.setdefault(n, []).append((pad_box(p), {l for l in (F, B) if p.IsOnLayer(l)},
                                              p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH))
    # U205 gate 1 changes its nets: its plane stub (none) and signal copper are covered by PARTIAL / FULL
    items = list(b.GetTracks())
    gone = set()
    for i, t in enumerate(items):
        if t.GetNetname() in FULL:
            gone.add(i)
    n_full = len(gone)

    def trim(nets, region=None):
        """Dangling copper of these nets (inside region if given) goes, again and again."""
        recs = []
        for i, t in enumerate(items):
            if i in gone or t.GetNetname() not in nets:
                continue
            if is_via(t):
                recs.append({'i': i, 'via': True, 'net': t.GetNetname(), 'p': xy(t.GetPosition()), 'r': t.GetWidth(F) / MM / 2})
            else:
                recs.append({'i': i, 'via': False, 'net': t.GetNetname(), 'layer': t.GetLayer(), 'a': xy(t.GetStart()),
                             'b': xy(t.GetEnd()), 'w': t.GetWidth() / MM})
        alive = {r['i'] for r in recs}

        def on_pad(net, layer, pt):
            for box, layers, pth in anchors.get(net, []):
                if (layer is None or pth or layer in layers) and in_box(pt, box):
                    return True
            return False

        def inside(r):
            if region is None:
                return True
            pts = [r['p']] if r['via'] else [r['a'], r['b']]
            return all(region[0] <= x <= region[2] and region[1] <= y <= region[3] for x, y in pts)

        changed = True
        while changed:
            changed = False
            live = [r for r in recs if r['i'] in alive]
            by_net = {}
            for r in live:
                by_net.setdefault(r['net'], []).append(r)
            for r in live:
                if r['i'] not in alive or not inside(r):
                    continue
                same = [o for o in by_net[r['net']] if o['i'] != r['i'] and o['i'] in alive]
                if r['via']:
                    n = sum(1 for o in same if not o['via'] and min(math.dist(o['a'], r['p']), math.dist(o['b'], r['p'])) <= r['r'] + 0.005)
                    if r['net'] in PLANE_NETS:
                        # a plane via lives on its plane: it is dead only when nothing at all hangs on it
                        if n == 0 and not on_pad(r['net'], None, r['p']):
                            alive.discard(r['i']); changed = True
                        continue
                    if on_pad(r['net'], None, r['p']):
                        n += 1
                    if n < 2:
                        alive.discard(r['i']); changed = True
                    continue
                for end in (r['a'], r['b']):
                    ok = on_pad(r['net'], r['layer'], end)
                    if not ok:
                        for o in same:
                            if o['via']:
                                if math.dist(o['p'], end) <= o['r'] + 0.005:
                                    ok = True; break
                            elif o['layer'] == r['layer'] and seg_dist(end, o['a'], o['b']) <= 0.01:
                                ok = True; break            # on the other track's centre line, as KiCad joins them
                    if not ok:
                        alive.discard(r['i']); changed = True
                        break
        dead = {r['i'] for r in recs} - alive
        gone.update(dead)
        return len(dead)

    n_partial = trim(PARTIAL)
    # Plane stubs of the pads that move or go: the track on the pad, then only what hung on it
    # (its via, a second segment). Nothing else of the plane nets is looked at.
    ends, n_stub = [], 0
    for net, box, layers in lost_plane_pads:
        for i, t in enumerate(items):
            if i in gone or is_via(t) or t.GetNetname() != net or t.GetLayer() not in layers:
                continue
            a, e = xy(t.GetStart()), xy(t.GetEnd())
            if in_box(a, box) or in_box(e, box):
                gone.add(i); n_stub += 1
                ends += [(net, a), (net, e)]
        for i, t in enumerate(items):                    # a via in the pad itself
            if i not in gone and is_via(t) and t.GetNetname() == net and in_box(xy(t.GetPosition()), box):
                ends.append((net, xy(t.GetPosition())))

    def plane_supported(net, layer, pt, me):
        for box, layers, pth in anchors.get(net, []):
            if (layer is None or pth or layer in layers) and in_box(pt, box):
                return True
        for j, o in enumerate(items):
            if j in gone or j == me or o.GetNetname() != net:
                continue
            if is_via(o):
                if layer is not None and math.dist(xy(o.GetPosition()), pt) <= o.GetWidth(F) / MM / 2 + 0.005:
                    return True
            elif (layer is None or o.GetLayer() == layer) and seg_dist(pt, xy(o.GetStart()), xy(o.GetEnd())) <= 0.01:
                return True
        return False

    n_plane, changed = 0, True
    while changed:
        changed = False
        for i, t in enumerate(items):
            if i in gone or t.GetNetname() not in PLANE_NETS:
                continue
            net = t.GetNetname()
            if is_via(t):
                p = xy(t.GetPosition())
                if any(n == net and math.dist(q, p) <= 0.3 for n, q in ends) and not plane_supported(net, None, p, i):
                    gone.add(i); n_plane += 1; changed = True
                continue
            a, e = xy(t.GetStart()), xy(t.GetEnd())
            for pt in (a, e):
                if any(n == net and math.dist(q, pt) <= 0.02 for n, q in ends) and not plane_supported(net, t.GetLayer(), pt, i):
                    gone.add(i); n_plane += 1; changed = True
                    ends += [(net, a), (net, e)]
                    break
    fps = [b.FindFootprintByReference(r) for r in REMOVED]
    info = {'removed': {'tracks_of_ended_nets': n_full, 'trimmed_to_a_junction': n_partial, 'plane_stubs': n_stub,
                        'plane_copper_left_hanging': n_plane, 'footprints': list(REMOVED)},
            'route_nets': ROUTE}
    for i in sorted(gone):
        b.Remove(items[i])
    for fp in fps:
        b.Remove(fp)
    pcbnew.SaveBoard(str(dst), b)
    Path(str(dst) + '.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
    print(json.dumps(info['removed']))


def set_rotation(fp, targets):
    """The rotation (of four) that puts the named pads nearest to where they are wanted."""
    best = None
    for rot in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot)
        err = 0.0
        for num, (tx, ty) in targets.items():
            p = next(q for q in fp.Pads() if q.GetNumber() == num)
            err += math.hypot(p.GetPosition().x / MM - tx, p.GetPosition().y / MM - ty)
        if best is None or err < best[0]:
            best = (err, rot)
    fp.SetOrientationDegrees(best[1])
    if best[0] > 0.1 * len(targets):
        sys.exit('%s: no rotation puts its pads where they are wanted (off by %.3f mm)' % (fp.GetReference(), best[0]))
    return best[1]


def stage_place(src, dst):
    b = pcbnew.LoadBoard(str(src))
    info = json.loads(Path(str(src) + '.json').read_text(encoding='utf-8'))
    log = []

    def net(name):
        ni = b.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(b, name)
            b.Add(ni)
        return ni

    for ref, (x, y, side, lib, name, value, targets) in NEW.items():
        fp = pcbnew.FootprintLoad(str(SHARE_FP / (lib + '.pretty')), name)
        fp.SetReference(ref); fp.SetValue(value)
        b.Add(fp)
        fp.SetPosition(V(mm(x), mm(y)))
        if side == B:
            fp.Flip(fp.GetPosition(), False)
        rot = set_rotation(fp, targets)
        log.append('%s %s on %s at (%.2f, %.2f), rotation %d' % (ref, value, b.GetLayerName(fp.GetLayer()), x, y, rot))
    for ref, (x, y, targets, value) in MOVE.items():
        fp = b.FindFootprintByReference(ref)
        old = xy(fp.GetPosition())
        fp.SetPosition(V(mm(x), mm(y)))
        rot = set_rotation(fp, targets)
        if value:
            fp.SetValue(value)
        log.append('%s moved from (%.2f, %.2f) to (%.2f, %.2f), rotation %d%s' % (ref, old[0], old[1], x, y, rot,
                                                                              ', value ' + value if value else ''))
    root = ET.parse(NETLIST).getroot()
    want = {(node.get('ref'), node.get('pin')): n.get('name') for n in root.find('nets') for node in n}
    refs = {c.get('ref') for c in root.find('components')}
    on_board = {fp.GetReference() for fp in b.GetFootprints() if not fp.GetReference().startswith('H')}
    if refs != on_board:
        sys.exit('parts differ between the netlist and the board: %s' % sorted(refs ^ on_board))
    changed = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            key = (fp.GetReference(), p.GetNumber())
            if key in want and p.GetNetname() != want[key]:
                if not (p.GetNetname() == '' and want[key].startswith('unconnected-')):
                    changed[key] = (p.GetNetname(), want[key])
                p.SetNet(net(want[key]))
    for key, (old, new) in sorted(changed.items()):
        if key[0] not in NEW:
            log.append('pad %s.%s: %s -> %s' % (key[0], key[1], old or '(none)', new))
    expect = {('U1', 'C9'), ('U1', 'C12'), ('U1', 'C13'), ('U1', 'C14'), ('U205', '1'), ('U205', '2')}
    got = {k for k in changed if k[0] not in NEW}
    if got != expect:
        sys.exit('pads of old parts that changed are not the six expected: %s' % sorted(got ^ expect))
    k = pcbnew.ZONE(b)
    k.SetIsRuleArea(True); k.SetDoNotAllowTracks(True); k.SetDoNotAllowVias(True)
    k.SetDoNotAllowZoneFills(False); k.SetDoNotAllowPads(False); k.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET(); ls.addLayer(F); k.SetLayerSet(ls)
    k.SetZoneName('usb_c_body_keepout')
    x0, y0, x1, y1 = USB_BODY
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        k.AppendCorner(V(mm(x), mm(y)), -1)
    b.Add(k)
    log.append('keep-out under the receptacle body on F.Cu: no tracks, no vias, x %.1f..%.1f, y %.1f..%.1f' % (x0, x1, y0, y1))
    for z in b.Zones():
        if not z.GetIsRuleArea():
            z.UnFill()
    pcbnew.SaveBoard(str(dst), b)
    info['placed'] = log
    Path(str(dst) + '.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
    print(chr(10).join(log))
    print('nets to route: %s' % ' '.join(info['route_nets']))


def stage_lock(src, dst):
    b = pcbnew.LoadBoard(str(src))
    n = 0
    for t in b.GetTracks():
        if not t.IsLocked():
            t.SetLocked(True); n += 1
    pcbnew.SaveBoard(str(dst), b)
    print('locked %d tracks and vias' % n)


def stage_unlock(src, dst):
    b = pcbnew.LoadBoard(str(src))
    n = 0
    for t in b.GetTracks():
        if t.IsLocked():
            t.SetLocked(False); n += 1
    pcbnew.SaveBoard(str(dst), b)
    print('unlocked %d tracks and vias' % n)


def stage_tidy(src, dst, report):
    b = pcbnew.LoadBoard(str(src))
    drc = json.loads(Path(report).read_text(encoding='utf-8'))
    want = []
    for v in drc.get('violations', []):
        if v['type'] not in ('track_dangling', 'via_dangling'):
            continue
        it = v['items'][0]
        d = it['description']
        net = d[d.index('[') + 1:d.index(']')] if '[' in d else ''
        if net in ROUTE:
            want.append((v['type'] == 'via_dangling', net, (it['pos']['x'], it['pos']['y']), d))
    items = [t for t in b.GetTracks() if t.GetNetname() in ROUTE]
    gone, what, kept = [], [], []
    for via, net, pos, d in want:
        for t in items:
            if t in gone or t.GetNetname() != net or is_via(t) != via:
                continue
            pts = [xy(t.GetPosition())] if via else [xy(t.GetStart()), xy(t.GetEnd())]
            if any(math.dist(q, pos) <= 0.006 for q in pts) and (via or b.GetLayerName(t.GetLayer()) in d):
                if via:
                    # two track ends inside one via: the via's copper is what joins them
                    # (close_open_items_v2.py found this the hard way). Such a via stays.
                    r = t.GetWidth(F) / MM / 2
                    ends = sum(1 for o in items if not is_via(o) and o.GetNetname() == net
                               for e in (xy(o.GetStart()), xy(o.GetEnd())) if math.dist(e, pos) <= r + 0.005)
                    if ends >= 2:
                        kept.append('via %s at (%.2f, %.2f)' % (net, pos[0], pos[1]))
                        break
                gone.append(t)
                what.append('%s %s at (%.2f, %.2f)' % ('via' if via else 'track', net, pos[0], pos[1]))
                break
        else:
            sys.exit('reported but not found on the board: ' + d)
    for t in gone:
        b.Remove(t)
    pcbnew.SaveBoard(str(dst), b)
    print('removed %d leftovers: %s' % (len(gone), '; '.join(what)))
    if kept:
        print('kept %d that join two track ends: %s' % (len(kept), '; '.join(kept)))


if __name__ == '__main__':
    stage, src, dst = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if stage == 'tidy':
        stage_tidy(src, dst, sys.argv[4])
    else:
        {'clear': stage_clear, 'place': stage_place, 'lock': stage_lock, 'unlock': stage_unlock}[stage](src, dst)
    sys.stdout.flush()
