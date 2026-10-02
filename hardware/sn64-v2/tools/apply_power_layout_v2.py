"""Lay the power section of the routed v2 board out the way its makers' data sheets ask, and put
each chip's capacitor at the pin it serves, without touching the rest of the routing (KiCad's python).

Found in the pre-order review of 2026-10-02 (docs/design/board-verification.md): the placement tool
had put the parts where their nets pulled them and the router had then wired the supplies like
signals. The 1.1 V converter had no capacitor within 6.9 mm of its input pin, the 5 V converter's
output capacitors were 7 to 10 mm away behind one via, the coil currents ran through 0.15 mm tracks,
and the small capacitors of the level shifters sat in a clump up to 36 mm from their chips.

The rules it follows
  TPS63070 (TI SLVSC58B, 11.1)   "The input capacitor, output capacitor, and the inductor should be
                                 placed as close as possible to the IC"; one 0603 capacitor from VIN to
                                 ground and one from VOUT to ground at the pins, the 0805 ones behind
                                 them; wide and short traces; EN through 10 k when tied to VIN.
  TLV62569 (TI SLVSDG1C, 10.1)   "The input/output capacitors and the inductor should be placed as close
                                 as possible to the IC."
  TPS2121 (TI SLVSEA3F, 11, 12)  "Bypass capacitors on these pins should be placed as close to the device
                                 as possible"; short wide traces for IN1, IN2 and OUT.
  TPS2553 (TI SLVS841F)          a ceramic capacitor between IN and ground close to the device.
  every logic chip               its 100 nF at the supply pin it belongs to (the table AT_PIN in
                                 build_v2_schematic.py, written into libraries/v2-provenance.json).

Stages (each its own process: KiCad 10's python breaks lookups after board.Remove()):
  parts    adds the parts the schematic has and the board has not, and gives every pad the net the
           netlist gives it.
  clear    takes up the copper of the power section: everything on the back face (F.Cu) inside the
           section, the section's own nets on every layer, and the stubs of the capacitors that move.
           What is left dangling on other nets inside the section is trimmed; a trunk that leaves the
           section stays as it is, for the router to join to.
  place    moves the parts of the power section to the plan (power_layout_plan.json, written by
           make_power_plan.py).
  decouple moves each other capacitor to the nearest free place to the pin it serves, on either face.
  fit      outside the power section: removes only the tracks and vias that are in the way of a part of
           the plan (the supervisor and the measuring chip's capacitors).
  copper   draws the supply paths of the plan as wide tracks from pad to pad.
  (add_plane_vias_v2.py: ground, 3.3 V and 1.1 V pads get their vias.)
  lock / unlock   around the router, which then joins what is still open.

  python apply_power_layout_v2.py parts|clear|place|decouple|fit|copper|lock|unlock IN.kicad_pcb OUT.kicad_pcb
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
MM = pcbnew.ToMM
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
F, B = pcbnew.F_Cu, pcbnew.B_Cu

# the power section on the board: x0, y0, x1, y1
REGION = (-50.9, -27.6, -25.4, -0.2)
# nets that live inside the section: all their copper is laid again
SECTION_NETS = {'SYS_VIN', '5V_SYS', 'L1_5V', 'L2_5V', 'SW_3V3', 'SW_1V1', 'FB_5V', 'FB_3V3', 'FB_1V1', 'PG_5V', 'VAUX_5V',
                'MUX_SS', 'MUX_ILM', 'MUX_PR1', 'MUX_CP2', 'CART_ILIM', 'EN_5V'}
NEW_PARTS = {'R321': ('Resistor_SMD', 'R_0603_1608Metric'), 'C324': ('Capacitor_SMD', 'C_0603_1608Metric'),
             'C325': ('Capacitor_SMD', 'C_0603_1608Metric')}
NEW_PARTS.update({'C%d' % n: ('Capacitor_SMD', 'C_0603_1608Metric') for n in range(213, 221)})
NEW_PARTS['C46'] = ('Capacitor_SMD', 'C_0603_1608Metric')

# capacitors that go to the pin they serve by a search for the nearest free place (stage decouple); the
# power section's own capacitors are in the plan instead
DECOUPLE = (['C%d' % n for n in range(201, 209)] + ['C%d' % n for n in range(213, 221)] +
            ['C211', 'C31', 'C32', 'C209', 'C210'])
CAP = {'0603': (0.775, 0.9, 0.95, 3.05, 1.55), '0805': (0.95, 1.0, 1.45, 3.49, 2.05)}   # pad offset, pad along, pad across, courtyard
PAD_GAP = 0.2                 # a moved capacitor's pad to any other copper on its face
# reference: (face, x, y, rotation). Rotation as KiCad shows it.
PLAN = {}
# net: [(width, [points])]; a point is (x, y) or 'REF.PAD' (the pad's centre) or ('REF.PAD', dx, dy)
COPPER = {}


def is_via(t):
    return t.Type() == pcbnew.PCB_VIA_T


def xy(v):
    return (MM(v.x), MM(v.y))


def in_region(p, grow=0.0):
    x, y = p if isinstance(p, tuple) else xy(p)
    return REGION[0] - grow <= x <= REGION[2] + grow and REGION[1] - grow <= y <= REGION[3] + grow


def load_plan():
    plan = json.loads((HERE / 'power_layout_plan.json').read_text(encoding='utf-8'))
    PLAN.update({k: tuple(v) for k, v in plan['place'].items()})
    COPPER.update(plan['copper'])
    return plan


def stage_parts(src, dst):
    b = pcbnew.LoadBoard(str(src))
    root = ET.parse(NETLIST).getroot()
    comps = {c.get('ref'): c for c in root.find('components')}
    have = {f.GetReference() for f in b.GetFootprints()}
    log = []

    def net(name):
        ni = b.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(b, name)
            b.Add(ni)
        return ni

    park = [-20.0, 14.0]                         # off the board until the place stage
    for ref in sorted(set(comps) - have):
        if ref not in NEW_PARTS:
            sys.exit('%s is in the schematic, not on the board, and this tool does not know it' % ref)
        lib, name = NEW_PARTS[ref]
        fp = pcbnew.FootprintLoad(str(SHARE_FP / (lib + '.pretty')), name)
        fp.SetReference(ref)
        fp.SetValue(comps[ref].findtext('value'))
        b.Add(fp)
        fp.SetPosition(V(mm(park[0]), mm(park[1])))
        park[0] += 3.5
        log.append('%s added' % ref)
    want = {(node.get('ref'), node.get('pin')): n.get('name') for n in root.find('nets') for node in n}
    for f in b.GetFootprints():
        for p in f.Pads():
            key = (f.GetReference(), p.GetNumber())
            if key in want and p.GetNetname() != want[key]:
                if not (p.GetNetname() == '' and want[key].startswith('unconnected-')):
                    if f.GetReference() in have:
                        log.append('pad %s.%s: %s -> %s' % (key[0], key[1], p.GetNetname() or '(none)', want[key]))
                p.SetNet(net(want[key]))
    pcbnew.SaveBoard(str(dst), b)
    print('; '.join(log))


def stage_clear(src, dst):
    plan = load_plan()
    b = pcbnew.LoadBoard(str(src))
    moved = set(PLAN) | set(DECOUPLE)
    tracks = list(b.GetTracks())
    gone = set()
    stats = {'section nets': 0, 'back face in the section': 0, 'vias in the section': 0, 'stubs of moved parts': 0, 'trimmed': 0}
    moved_pads = []
    staying, far = set(), set()             # nets with a pad that stays; nets of plan parts outside the section
    for f in b.GetFootprints():
        for p in f.Pads():
            if f.GetReference() in moved:
                moved_pads.append((p, p.GetNetname()))
                if f.GetReference() in PLAN and not in_region(tuple(PLAN[f.GetReference()][1:3])):
                    far.add(p.GetNetname())
            else:
                staying.add(p.GetNetname())
    all_moved = {n for _, n in moved_pads} - staying - {'GND', 'FPGA_3V3', 'FPGA_1V1', ''}     # every pad of the net moves
    far -= {'GND', 'FPGA_3V3', 'FPGA_1V1', ''}
    for i, t in enumerate(tracks):
        n = t.GetNetname()
        if n in SECTION_NETS or n in all_moved:
            gone.add(i); stats['section nets'] += 1
        elif is_via(t):
            if in_region(t.GetPosition()) and n not in plan.get('keep_vias_of', []):
                gone.add(i); stats['vias in the section'] += 1
        elif t.GetLayer() == F and (in_region(t.GetStart()) or in_region(t.GetEnd())):
            gone.add(i); stats['back face in the section'] += 1
    # copper that ends in a pad of a part that moves (anywhere on the board): the piece up to the first junction
    def touches_pad(t, pad):
        for e in ((t.GetStart(), t.GetEnd()) if not is_via(t) else (t.GetPosition(),)):
            if pad.HitTest(e, mm(0.05)) and (is_via(t) or pad.IsOnLayer(t.GetLayer())):
                return True
        return False
    for i, t in enumerate(tracks):
        if i in gone:
            continue
        for pad, n in moved_pads:
            if t.GetNetname() == n and touches_pad(t, pad):
                gone.add(i); stats['stubs of moved parts'] += 1
                break

    # trim: a track end or via that now touches nothing else of its net goes, again and again
    pads_by_net = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            if f.GetReference() not in moved:
                pads_by_net.setdefault(p.GetNetname(), []).append(p)
    zone_nets = {z.GetNetname() for z in b.Zones() if not z.GetIsRuleArea()}
    by_net = {}
    for i, t in enumerate(tracks):
        by_net.setdefault(t.GetNetname(), []).append(i)
    touched = {tracks[i].GetNetname() for i in gone}

    def supported(i, pt, layers):
        t = tracks[i]
        n = t.GetNetname()
        for p in pads_by_net.get(n, []):
            if any(p.IsOnLayer(l) for l in layers) and p.HitTest(V(mm(pt[0]), mm(pt[1])), mm(0.05)):
                return True
        for j in by_net[n]:
            if j == i or j in gone:
                continue
            o = tracks[j]
            if is_via(o):
                if math.dist(xy(o.GetPosition()), pt) <= MM(o.GetWidth(F)) / 2 + 0.01:
                    return True
            elif o.GetLayer() in layers:
                a, c = xy(o.GetStart()), xy(o.GetEnd())
                dx, dy = c[0] - a[0], c[1] - a[1]
                L2 = dx * dx + dy * dy
                u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L2))
                if math.dist(pt, (a[0] + u * dx, a[1] + u * dy)) <= MM(o.GetWidth()) / 2 + 0.01:
                    return True
        return False

    all_layers = [l for l in b.GetEnabledLayers().CuStack()]
    plane_layer = {'GND': pcbnew.In1_Cu, 'FPGA_3V3': pcbnew.In3_Cu, 'FPGA_1V1': pcbnew.In4_Cu}
    changed = True
    while changed:
        changed = False
        for n in touched:
            for i in by_net.get(n, []):
                if i in gone:
                    continue
                t = tracks[i]
                # only inside the section: a trunk that leaves it stays, with its open end at the section's
                # edge, and the router joins the new place to it. (Trimmed all the way, a line to an inner
                # ball of the FPGA has to be laid anew through the ball field, and the router could not.)
                # The nets of the parts that move outside the section are trimmed everywhere: their old
                # trunks end in nothing, in a crowded place where the room is needed.
                if n not in SECTION_NETS and n not in far and not all(in_region(e, 0.6) for e in ((t.GetPosition(),) if is_via(t) else (t.GetStart(), t.GetEnd()))):
                    continue
                if is_via(t):
                    pt = xy(t.GetPosition())
                    ends = sum(1 for l in all_layers if supported(i, pt, [l]))
                    if n in plane_layer:
                        ends += 1                # the plane is its other end
                    if ends < 2:
                        gone.add(i); stats['trimmed'] += 1; changed = True
                else:
                    if not (supported(i, xy(t.GetStart()), [t.GetLayer()]) and supported(i, xy(t.GetEnd()), [t.GetLayer()])):
                        gone.add(i); stats['trimmed'] += 1; changed = True
    for z in b.Zones():
        if not z.GetIsRuleArea():
            z.UnFill()
    open_nets = sorted({tracks[i].GetNetname() for i in gone} - {'GND', 'FPGA_3V3', 'FPGA_1V1'})
    for i in gone:
        b.Remove(tracks[i])
    pcbnew.SaveBoard(str(dst), b)
    Path(str(dst) + '.json').write_text(json.dumps({'route_nets': open_nets, 'removed': stats}, indent=1), encoding='utf-8')
    print('removed %d tracks and vias: %s; nets to join again: %d' % (len(gone), stats, len(open_nets)))


def stage_place(src, dst):
    load_plan()
    b = pcbnew.LoadBoard(str(src))
    log = []
    for ref, (face, x, y, rot) in sorted(PLAN.items()):
        f = b.FindFootprintByReference(ref)
        if f is None:
            sys.exit('%s is not on the board' % ref)
        want = F if face == 'F' else B
        f.SetPosition(V(mm(x), mm(y)))
        if f.GetLayer() != want:
            f.Flip(f.GetPosition(), False)
        if isinstance(rot, str):                 # a two-pad part: the side its pad 1 is on
            ux, uy = {'N': (0, -1), 'S': (0, 1), 'E': (1, 0), 'W': (-1, 0)}[rot]
            for a in (0, 90, 180, 270):
                f.SetOrientationDegrees(a)
                p1 = next(p for p in f.Pads() if p.GetNumber() == '1')
                dx, dy = MM(p1.GetPosition().x) - x, MM(p1.GetPosition().y) - y
                if dx * ux + dy * uy > 0.3:
                    break
            else:
                sys.exit('%s: no turn puts pad 1 on the %s side' % (ref, rot))
        else:
            f.SetOrientationDegrees(rot)
        log.append(ref)
    pcbnew.SaveBoard(str(dst), b)
    print('placed %d parts' % len(log))


def stage_decouple(src, dst):
    """Each capacitor of DECOUPLE goes to the nearest free place to the pin it serves, on either face."""
    load_plan()
    b = pcbnew.LoadBoard(str(src))
    at = json.loads((V2 / 'libraries' / 'v2-provenance.json').read_text(encoding='utf-8'))['capacitor_at_pin']
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    outline = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(outline, False)
    going = set(DECOUPLE)
    obst = {F: {'pads': [], 'trk': [], 'court': []}, B: {'pads': [], 'trk': [], 'court': []}}
    vias = []
    for f in fps.values():
        if f.GetReference() in going:
            continue
        for face in (F, B):
            for p in f.Pads():
                if p.IsOnLayer(face) or p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                    bb = p.GetBoundingBox()
                    obst[face]['pads'].append((MM(bb.GetLeft()), MM(bb.GetTop()), MM(bb.GetRight()), MM(bb.GetBottom()), p.GetNetname()))
            c = f.GetCourtyard(face)
            if c.OutlineCount():
                bb = c.BBox()
                obst[face]['court'].append((MM(bb.GetLeft()), MM(bb.GetTop()), MM(bb.GetRight()), MM(bb.GetBottom())))
    for t in b.GetTracks():
        if is_via(t):
            vias.append((MM(t.GetPosition().x), MM(t.GetPosition().y), MM(t.GetWidth(F)) / 2, t.GetNetname()))
        elif t.GetLayer() in obst:
            obst[t.GetLayer()]['trk'].append((MM(t.GetStart().x), MM(t.GetStart().y), MM(t.GetEnd().x), MM(t.GetEnd().y), MM(t.GetWidth()) / 2, t.GetNetname()))
    no_parts = [(z, [l for l in (F, B) if z.IsOnLayer(l)]) for f in fps.values() for z in f.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowFootprints()]
    no_parts += [(z, [l for l in (F, B) if z.IsOnLayer(l)]) for z in b.Zones() if z.GetIsRuleArea() and (z.GetDoNotAllowFootprints() or z.GetDoNotAllowTracks())]

    def rect_gap(r, q):
        return math.hypot(max(r[0] - q[2], q[0] - r[2], 0), max(r[1] - q[3], q[1] - r[3], 0))

    def seg_rect(sg, r):
        n = max(2, int(math.dist(sg[:2], sg[2:4]) / 0.1) + 1)
        best = 1e9
        for i in range(n + 1):
            x = sg[0] + (sg[2] - sg[0]) * i / n
            y = sg[1] + (sg[3] - sg[1]) * i / n
            best = min(best, math.hypot(max(r[0] - x, 0, x - r[2]), max(r[1] - y, 0, y - r[3])))
        return best - sg[4]

    def fits(face, pads, court):
        cx, cy = (court[0] + court[2]) / 2, (court[1] + court[3]) / 2
        corners = ((court[0], court[1]), (court[2], court[1]), (court[0], court[3]), (court[2], court[3]), (cx, cy))
        for x, y in corners:
            if not outline.Contains(V(mm(x), mm(y))):
                return False
        for z, layers in no_parts:
            if face in layers and any(z.Outline().Contains(V(mm(x), mm(y))) for x, y in corners):
                return False
        if any(rect_gap(court, c) < 0.02 for c in obst[face]['court']):
            return False
        for r, net in pads:
            for q in obst[face]['pads']:
                if abs(q[0] - r[0]) > 6 or abs(q[1] - r[1]) > 6:
                    continue
                if rect_gap(r, q) < PAD_GAP:
                    return False
            for v in vias:
                if abs(v[0] - r[0]) > 3 or abs(v[1] - r[1]) > 3:
                    continue
                if math.hypot(max(r[0] - v[0], 0, v[0] - r[2]), max(r[1] - v[1], 0, v[1] - r[3])) - v[2] < (0.12 if v[3] == net else PAD_GAP):
                    return False
            for sg in obst[face]['trk']:
                if min(sg[0], sg[2]) - 1 > r[2] or max(sg[0], sg[2]) + 1 < r[0] or min(sg[1], sg[3]) - 1 > r[3] or max(sg[1], sg[3]) + 1 < r[1]:
                    continue
                if sg[5] != net and seg_rect(sg, r) < PAD_GAP:
                    return False
        return True

    log, failed = [], []
    for cap in DECOUPLE:
        chip, pin = at[cap]
        pad = next(q for q in fps[chip].Pads() if q.GetNumber() == pin)
        face_only = None
        net = pad.GetNetname()
        px, py = xy(pad.GetPosition())
        f = fps[cap]
        size = '0805' if '0805' in f.GetFPIDAsString() else '0603'
        off, along, across, cw, ch = CAP[size]
        other = next(q.GetNetname() for q in f.Pads() if q.GetNetname() != net)
        best = None
        for radius in (3.0, 5.0, 8.0):
            n = int(radius / 0.25)
            for ix in range(-n, n + 1):
                for iy in range(-n, n + 1):
                    x, y = round(px + ix * 0.25, 3), round(py + iy * 0.25, 3)
                    for face in ((face_only,) if face_only is not None else (F, B)):
                        same = face == fps[chip].GetLayer() or chip == 'J2'
                        for ux, uy in ((1, 0), (-1, 0), (0, 1), (0, -1)):         # the way from the centre to the rail pad
                            rx, ry = x + ux * off, y + uy * off
                            gx, gy = x - ux * off, y - uy * off
                            hw, hh = (along / 2, across / 2) if ux else (across / 2, along / 2)
                            pads = [((rx - hw, ry - hh, rx + hw, ry + hh), net), ((gx - hw, gy - hh, gx + hw, gy + hh), other)]
                            court = (x - cw / 2, y - ch / 2, x + cw / 2, y + ch / 2) if ux else (x - ch / 2, y - cw / 2, x + ch / 2, y + cw / 2)
                            score = math.hypot(rx - px, ry - py) + (0.0 if same else 0.3)
                            if best is not None and score >= best[0]:
                                continue
                            if fits(face, pads, court):
                                best = (score, face, x, y, ux, uy, pads, court, same)
            if best is not None:
                break
        if best is None:
            failed.append(cap)
            continue
        score, face, x, y, ux, uy, pads, court, same = best
        f.SetPosition(V(mm(x), mm(y)))
        if f.GetLayer() != face:
            f.Flip(f.GetPosition(), False)
        for a in (0, 90, 180, 270):
            f.SetOrientationDegrees(a)
            rail = next(q for q in f.Pads() if q.GetNetname() == net)
            if (MM(rail.GetPosition().x) - x) * ux + (MM(rail.GetPosition().y) - y) * uy > 0.3:
                break
        for r, n_ in pads:
            obst[face]['pads'].append((r[0], r[1], r[2], r[3], n_))
        obst[face]['court'].append(court)
        log.append('%s at %s.%s: %s face, %.2f mm from the pin' % (cap, chip, pin, 'same' if same else 'other', score if same else score - 0.3))
    pcbnew.SaveBoard(str(dst), b)
    print(chr(10).join(log))
    if failed:
        print('no free place within 8 mm: ' + ' '.join(failed))


def stage_fit(src, dst):
    """Outside the power section the routing stays. Only what is in the way of a part of the plan goes:
    a track or via of another net that comes nearer than 0.2 mm to one of its pads, or a via inside its
    courtyard. The nets that lose copper are added to the list for the router."""
    load_plan()
    b = pcbnew.LoadBoard(str(src))
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    info = json.loads(Path(str(src) + '.json').read_text(encoding='utf-8'))
    boxes = []
    for ref in PLAN:
        f = fps[ref]
        if in_region(f.GetPosition()):
            continue
        for p in f.Pads():
            bb = p.GetBoundingBox()
            layers = [l for l in (F, B) if p.IsOnLayer(l)]
            boxes.append(((MM(bb.GetLeft()), MM(bb.GetTop()), MM(bb.GetRight()), MM(bb.GetBottom())), p.GetNetname(), layers))
    for net, runs in COPPER.items():
        for r in runs:
            for a in r['path']:
                if not isinstance(a, str) and not in_region((a[0], a[1])):
                    boxes.append(((a[0] - r['w'] / 2, a[1] - r['w'] / 2, a[0] + r['w'] / 2, a[1] + r['w'] / 2), net, [{'F': F, 'B': B}[r.get('layer', 'F')]]))
    gone = []
    for t in b.GetTracks():
        for box, net, layers in boxes:
            if is_via(t):
                x, y = xy(t.GetPosition())
                d = math.hypot(max(box[0] - x, 0, x - box[2]), max(box[1] - y, 0, y - box[3])) - MM(t.GetWidth(F)) / 2
                if d < (0.12 if t.GetNetname() == net else 0.2):
                    gone.append(t)
                    break
            elif t.GetLayer() in layers and t.GetNetname() != net:
                a, c = xy(t.GetStart()), xy(t.GetEnd())
                n = max(2, int(math.dist(a, c) / 0.1) + 1)
                d = min(math.hypot(max(box[0] - (a[0] + (c[0] - a[0]) * i / n), 0, (a[0] + (c[0] - a[0]) * i / n) - box[2]),
                                   max(box[1] - (a[1] + (c[1] - a[1]) * i / n), 0, (a[1] + (c[1] - a[1]) * i / n) - box[3])) for i in range(n + 1))
                if d - MM(t.GetWidth()) / 2 < 0.2:
                    gone.append(t)
                    break
    nets = sorted({t.GetNetname() for t in gone} - {'GND', 'FPGA_3V3', 'FPGA_1V1'})
    info['route_nets'] = sorted(set(info['route_nets']) | set(nets))
    for t in gone:
        b.Remove(t)
    pcbnew.SaveBoard(str(dst), b)
    Path(str(dst) + '.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
    print('removed %d tracks and vias in the way of moved parts outside the power section; their nets: %s' % (len(gone), ' '.join(nets)))


def stage_copper(src, dst):
    load_plan()
    b = pcbnew.LoadBoard(str(src))
    fps = {f.GetReference(): f for f in b.GetFootprints()}

    def point(spec, net):
        if isinstance(spec, str):
            spec = [spec, 0.0, 0.0]
        if isinstance(spec[0], str):
            ref, num = spec[0].split('.')
            pads = [p for p in fps[ref].Pads() if p.GetNumber() == num]
            if not pads:
                sys.exit('no pad %s' % spec[0])
            if pads[0].GetNetname() != net:
                sys.exit('%s is on %s, the plan draws %s to it' % (spec[0], pads[0].GetNetname(), net))
            # several pads with one number (an L-shaped land): the mean of their centres
            x = sum(MM(p.GetPosition().x) for p in pads) / len(pads) if len(spec) > 3 else MM(pads[0].GetPosition().x)
            y = sum(MM(p.GetPosition().y) for p in pads) / len(pads) if len(spec) > 3 else MM(pads[0].GetPosition().y)
            return (x + spec[1], y + spec[2])
        return (spec[0], spec[1])

    n_trk = n_via = 0
    for net, runs in COPPER.items():
        code = b.GetNetcodeFromNetname(net)
        if code <= 0:
            sys.exit('no net %s' % net)
        for run in runs:
            layer = {'F': F, 'B': B}[run.get('layer', 'F')]
            pts = [point(s, net) for s in run.get('path', [])]
            for a, c in zip(pts, pts[1:]):
                if math.dist(a, c) < 0.001:
                    continue
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(V(mm(a[0]), mm(a[1]))); t.SetEnd(V(mm(c[0]), mm(c[1])))
                t.SetWidth(mm(run['w'])); t.SetLayer(layer); t.SetNetCode(code)
                b.Add(t)
                n_trk += 1
            for spec in run.get('vias', []):
                x, y = point(spec, net)
                v = pcbnew.PCB_VIA(b)
                v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(F, B)
                v.SetPosition(V(mm(x), mm(y))); v.SetDrill(mm(0.2)); v.SetWidth(mm(0.5))
                v.SetNetCode(code)
                b.Add(v)
                n_via += 1
    pcbnew.SaveBoard(str(dst), b)
    print('drew %d tracks and %d vias of the plan' % (n_trk, n_via))


def stage_lock(src, dst, state=True):
    b = pcbnew.LoadBoard(str(src))
    n = 0
    for t in b.GetTracks():
        t.SetLocked(state)
        n += 1
    pcbnew.SaveBoard(str(dst), b)
    print('%s %d tracks and vias' % ('locked' if state else 'unlocked', n))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    stage, src, dst = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    note = Path(str(src) + '.json')                # the list of nets for the router travels with the board
    if note.exists() and stage not in ('clear', 'fit') and src != dst:
        Path(str(dst) + '.json').write_text(note.read_text(encoding='utf-8'), encoding='utf-8')
    if stage == 'unlock':
        stage_lock(src, dst, False)
    else:
        {'parts': stage_parts, 'clear': stage_clear, 'place': stage_place, 'decouple': stage_decouple, 'fit': stage_fit, 'copper': stage_copper,
         'lock': stage_lock}[stage](src, dst)
    sys.stdout.flush()
