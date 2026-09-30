"""Create the SN64 v2 boards from their exported netlists (KiCad's python).

Main board (hardware/sn64-v2/sn64-v2.kicad_pcb): 104 x 64 mm, six layers, horizontal on top of the
riser. Front edge (+y) carries the SNES socket, the translator row sits between it and the FPGA,
the riser socket is on the bottom side at the rear edge (-y), USB-C on the left edge, power on the
right. Fixed parts are placed by hand below; everything else goes by connectivity attraction into
block rectangles (the v1 placer, hardware/sn64/tools/build_main_pcb.py, with v2 geometry).
Riser (hardware/sn64-v2-riser/sn64-v2-riser.kicad_pcb): SummerCart64 tongue + a rectangle up to
the right-angle header, two layers.

  python build_v2_pcb.py [--force]      # rebuilds both boards from validation/*.xml (placement is lost)
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
REPO = V2.parents[1]
RISER = REPO / 'hardware/sn64-v2-riser'
SHARE_FP = Path('C:/Program Files/KiCad/10.0/share/kicad/footprints')
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
HALF_W, HALF_H = 52.0, 32.0
FPGA_Y = -12.0


def load_footprint(fpid, local):
    lib, name = fpid.split(':', 1)
    path = local.get(lib) or (SHARE_FP / f'{lib}.pretty')
    fp = pcbnew.FootprintLoad(str(path), name)
    if fp is None:
        raise SystemExit(f'footprint not found: {fpid}')
    return fp


def read_netlist(path):
    root = ET.parse(path).getroot()
    comps = [{'ref': c.get('ref'), 'value': c.findtext('value') or '', 'fp': c.findtext('footprint') or '',
              'sheet': c.find('sheetpath').get('names'), 'dnp': any(p.get('name') == 'dnp' for p in c.findall('./property'))}
             for c in root.find('components')]
    nets = {n.get('name'): [(node.get('ref'), node.get('pin')) for node in n] for n in root.find('nets')}
    return comps, nets


def rules(board, layers=6, thickness=1.2):
    board.SetCopperLayerCount(layers)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(thickness))
    ds.m_MinClearance = mm(0.1)
    ds.m_TrackMinWidth = mm(0.1)
    ds.m_ViasMinSize = mm(0.45)
    ds.m_MinThroughDrill = mm(0.2)
    ds.m_ViasMinAnnularWidth = mm(0.125)
    ds.m_MinSilkTextHeight = mm(0.8)
    ds.m_SolderMaskMinWidth = mm(0.1)
    ds.m_HoleClearance = mm(0.2)          # PCBWay: hole to copper >= 8 mil
    ds.m_CopperEdgeClearance = mm(0.3)
    try:
        ds.m_DRCSeverities[pcbnew.DRCE_SOLDERMASK_BRIDGE] = pcbnew.RPT_SEVERITY_WARNING
    except Exception:
        pass
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(mm(0.1)); nc.SetTrackWidth(mm(0.15)); nc.SetViaDiameter(mm(0.45)); nc.SetViaDrill(mm(0.2))


def rect_outline(board, pts):
    for a, b in zip(pts, pts[1:] + pts[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(V(mm(a[0]), mm(a[1]))); seg.SetEnd(V(mm(b[0]), mm(b[1])))
        seg.SetLayer(pcbnew.Edge_Cuts); seg.SetWidth(mm(0.1))
        board.Add(seg)


def courtyard_box(fp):
    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        c = fp.GetCourtyard(layer)
        if c.OutlineCount():
            bb = c.BBox()
            break
    else:
        bb = fp.GetBoundingBox(False, False)
    return bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6


def place_centred(fp, x, y, rot, flip=False):
    """Put the footprint's courtyard centre at (x, y) with the given rotation (and side)."""
    fp.SetOrientationDegrees(rot)
    if flip and not fp.IsFlipped():
        fp.Flip(fp.GetPosition(), False)
    fp.SetPosition(V(0, 0))
    x0, y0, x1, y1 = courtyard_box(fp)
    fp.SetPosition(V(mm(x - (x0 + x1) / 2), mm(y - (y0 + y1) / 2)))


def side_of(fp):
    name = fp.GetFPIDAsString()
    return 'bottom' if any(k in name for k in ('0402', '0603', 'R_Array', 'TestPoint')) else 'top'


# ---------------------------------------------------------------------------
# Main board plan
# ---------------------------------------------------------------------------
# ref: (x, y, rotation, flipped)   courtyard centres, mm, y positive = front (socket)
FIXED = {
    'J2':   (0.0, 22.5, 0, False),          # SNES socket along the front edge, nose up
    'J1':   (0.0, -27.5, 90, True),         # riser socket 2x20 on the bottom, rear edge
    'U1':   (0.0, FPGA_Y, 0, False),        # FPGA: banks 0/1 to the rear (riser), 7/6 left, 2/3 right, 8 front (flash)
    'U201': (-36.0, 9.0, 90, False),        # translators: A side (pins 25-48) toward the FPGA, B side toward the socket
    'U202': (-12.0, 9.0, 90, False),
    'U203': (12.0, 9.0, 90, False),
    'U204': (36.0, 9.0, 90, False),
    'U2':   (-22.0, -1.0, 90, False),       # flash beside bank 8, left of the FPGA's front edge
    'X1':   (26.0, -24.0, 0, False),        # 27 MHz near ball B12 (rear, right of centre)
    'J101': (-47.5, -16.0, 90, False),      # USB-C on the left edge, receptacle facing out
}
BLOCKS = {
    ('usb', 'top'):           (-51.0, -31.0, -26.0, -6.0),
    ('usb', 'bottom'):        (-51.0, -31.0, -24.0, -6.0),
    ('power', 'top'):         (26.0, -31.0, 51.0, -6.0),
    ('power', 'bottom'):      (26.0, -31.0, 51.0, -6.0),
    ('fpga_support', 'top'):  (11.0, -22.0, 26.0, 3.0),
    ('fpga_support', 'bottom'): (-51.0, -24.0, 51.0, 3.0),
    ('cart', 'top'):          (40.0, -9.0, 51.0, 3.0),
    ('cart', 'bottom'):       (-51.0, 3.0, 51.0, 15.0),
    ('misc', 'top'):          (26.0, -6.0, 43.0, 4.0),
    ('misc', 'bottom'):       (-51.0, -24.0, 51.0, 3.0),
}
HOLES = ((-48.0, -28.5), (48.0, -28.5), (-48.0, 13.5), (48.0, 13.5))


def block_of(c):
    ref, sheet, fp = c['ref'], c['sheet'], c['fp']
    if sheet.startswith('/FPGA'):
        if ref.startswith('C') and int(ref[1:]) <= 30:
            return 'fpga_decap'
        if ref in ('R19', 'R20', 'R21'):
            return 'usb'
        return 'fpga_support'
    if sheet.startswith('/Cartridge'):
        return 'cart'
    if sheet.startswith('/Power'):
        return 'usb' if ref in ('J101', 'U4', 'R301', 'R302', 'C301', 'C302') else 'power'
    return 'misc'


def place_by_attraction(board, fps, blocks, fixed_refs, blocked_rects):
    BIG_NET = 12
    net_pads, net_refs = {}, {}
    for fp in fps.values():
        for p in fp.Pads():
            n = p.GetNetname()
            if n:
                net_refs.setdefault(n, set()).add(fp.GetReference())
    pad_count = {}
    for fp in fps.values():
        for p in fp.Pads():
            pad_count[p.GetNetname()] = pad_count.get(p.GetNetname(), 0) + 1
    small = {n: r for n, r in net_refs.items() if pad_count.get(n, 0) <= BIG_NET}
    adj = {}
    for n, refs in small.items():
        for r in refs:
            adj.setdefault(r, set()).update(refs - {r})
    dist = {r: 0 for r in fixed_refs if r in fps}
    frontier = list(dist)
    while frontier:
        nxt = []
        for r in frontier:
            for q in adj.get(r, ()):
                if q not in dist:
                    dist[q] = dist[r] + 1
                    nxt.append(q)
        frontier = nxt
    CELL = 0.25
    occ = {'top': set(), 'bottom': set()}

    def cells(fp, x, y):
        bx0, by0, bx1, by1 = courtyard_box(fp)
        dx, dy = x - fp.GetPosition().x / 1e6, y - fp.GetPosition().y / 1e6
        x0, y0, x1, y1 = bx0 + dx - 0.15, by0 + dy - 0.15, bx1 + dx + 0.15, by1 + dy + 0.15
        return {(i, j) for i in range(int(x0 // CELL), int(x1 // CELL) + 1) for j in range(int(y0 // CELL), int(y1 // CELL) + 1)}

    def record(fp, side):
        cs = cells(fp, fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6)
        occ[side] |= cs
        if any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in fp.Pads()):
            occ['top' if side == 'bottom' else 'bottom'] |= cs
        for p in fp.Pads():
            n = p.GetNetname()
            if n in small:
                net_pads.setdefault(n, []).append((p.GetPosition().x / 1e6, p.GetPosition().y / 1e6))

    def block_rect(x0, y0, x1, y1, sides=('top', 'bottom')):
        for side in sides:
            for i in range(int(x0 // CELL), int(x1 // CELL) + 1):
                for j in range(int(y0 // CELL), int(y1 // CELL) + 1):
                    occ[side].add((i, j))
    for r in blocked_rects:
        block_rect(*r)
    block_rect(-HALF_W - 1, -HALF_H - 1, HALF_W + 1, -HALF_H + 1.0)
    block_rect(-HALF_W - 1, HALF_H - 1.0, HALF_W + 1, HALF_H + 1)
    block_rect(-HALF_W - 1, -HALF_H, -HALF_W + 1.0, HALF_H)
    block_rect(HALF_W - 1.0, -HALF_H, HALF_W + 1, HALF_H)
    for r in fixed_refs:
        if r in fps:
            record(fps[r], 'bottom' if fps[r].IsFlipped() else 'top')

    def free(fp, x, y, side, rect):
        bx0, by0, bx1, by1 = courtyard_box(fp)
        dx, dy = x - fp.GetPosition().x / 1e6, y - fp.GetPosition().y / 1e6
        x0, y0, x1, y1 = rect
        if bx0 + dx < x0 or bx1 + dx > x1 or by0 + dy < y0 or by1 + dy > y1:
            return False
        return not (cells(fp, x, y) & occ[side])

    grid_cache = {}

    def spot(fp, tx, ty, side, rect):
        x0, y0, x1, y1 = rect
        if rect not in grid_cache:
            xs = [x0 + 0.5 * i for i in range(int((x1 - x0) / 0.5) + 1)]
            ys = [y0 + 0.5 * j for j in range(int((y1 - y0) / 0.5) + 1)]
            grid_cache[rect] = [(x, y) for x in xs for y in ys]
        for (x, y) in sorted(grid_cache[rect], key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2):
            if free(fp, x, y, side, rect):
                return x, y
        return None

    order = []
    for name, items in blocks.items():
        for fp in items:
            r = fp.GetReference()
            x0, y0, x1, y1 = courtyard_box(fp)
            order.append((dist.get(r, 99), 0 if side_of(fp) == 'top' else 1, -(x1 - x0) * (y1 - y0), r, name, fp))
    order.sort(key=lambda t: t[:4])
    unplaced = []
    for d, _, _, r, name, fp in order:
        side = side_of(fp)
        rect = BLOCKS.get((name, side)) or BLOCKS[('misc', side)]
        if side == 'bottom' and not fp.IsFlipped():
            fp.Flip(fp.GetPosition(), False)
        pts = [xy for p in fp.Pads() for xy in net_pads.get(p.GetNetname(), [])]
        tx, ty = (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)) if pts else ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
        tx, ty = min(max(tx, rect[0]), rect[2]), min(max(ty, rect[1]), rect[3])
        s = spot(fp, tx, ty, side, rect)
        if s is None:
            unplaced.append(r)
            s = (tx, ty)
        fp.SetPosition(V(mm(s[0]), mm(s[1])))
        record(fp, side)
    if unplaced:
        print('  no free spot found for:', unplaced)


def build_main(force):
    out = V2 / 'sn64-v2.kicad_pcb'
    if out.exists() and not force:
        raise SystemExit(f'{out} exists; use --force to rebuild (placement is lost)')
    local = {'SN64': V2 / 'libraries/SN64.pretty', 'SN64_USB': V2 / 'libraries/SN64_USB.pretty'}
    comps, nets = read_netlist(V2 / 'validation/sn64-v2.xml')
    board = pcbnew.BOARD()
    rules(board)
    rect_outline(board, [(-HALF_W, -HALF_H), (HALF_W, -HALF_H), (HALF_W, HALF_H), (-HALF_W, HALF_H)])
    fps, blocks = {}, {}
    for i, (x, y) in enumerate(HOLES, start=1):
        h = load_footprint('MountingHole:MountingHole_2.5mm', local)
        h.SetReference(f'H{i}'); h.SetPosition(V(mm(x), mm(y))); board.Add(h); fps[h.GetReference()] = h
    for c in comps:
        fp = load_footprint(c['fp'], local)
        fp.SetReference(c['ref']); fp.SetValue(c['value'])
        if c['dnp']:
            fp.SetDNP(True)
        board.Add(fp)
        fps[c['ref']] = fp
        if c['ref'] in FIXED:
            x, y, rot, flip = FIXED[c['ref']]
            place_centred(fp, x, y, rot, flip)
        else:
            blocks.setdefault(block_of(c), []).append(fp)
    # translators: pins 1-24 (B side, cartridge) must face the socket (+y)
    for ref in ('U201', 'U202', 'U203', 'U204'):
        fp = fps[ref]
        b = [p.GetPosition().y for p in fp.Pads() if int(p.GetNumber()) <= 24]
        a = [p.GetPosition().y for p in fp.Pads() if int(p.GetNumber()) > 24]
        if sum(b) / len(b) < sum(a) / len(a):
            x, y, _, _ = FIXED[ref]
            place_centred(fp, x, y, 270)
    netinfo = {}
    for code, (name, nodes) in enumerate(nets.items(), start=1):
        ni = pcbnew.NETINFO_ITEM(board, name, code)
        board.Add(ni); netinfo[name] = ni
        for ref, pin in nodes:
            fp = fps.get(ref)
            if fp is None:
                continue
            found = False
            for pad in fp.Pads():
                if pad.GetNumber() == pin:
                    pad.SetNet(ni); found = True
            if not found:
                print(f'  warning: {ref} pad {pin} not in footprint {fp.GetFPIDAsString()}')
    # FPGA decoupling on the bottom in three bands outside the dog-bone field (balls to +-7.6 mm, vias to +-8.0)
    decaps = sorted(blocks.pop('fpga_decap', []), key=lambda f: int(f.GetReference()[1:]))
    rows = (FPGA_Y - 10.4, FPGA_Y + 10.4, FPGA_Y + 12.8)
    cols = 10
    for i, fp in enumerate(decaps):
        fp.Flip(fp.GetPosition(), False)
        fp.SetPosition(V(mm(-16.2 + (i % cols) * 3.6), mm(rows[(i // cols) % len(rows)])))
    fixed = list(FIXED) + [f'H{i}' for i in range(1, len(HOLES) + 1)] + [f.GetReference() for f in decaps]
    # keep passives off the BGA field on the bottom (fan-out vias) and off the riser socket zone
    blocked = [(-9.0, FPGA_Y - 9.0, 9.0, FPGA_Y + 9.0, ('bottom',))]
    place_by_attraction(board, fps, blocks, fixed, blocked)
    board.BuildListOfNets()
    pcbnew.SaveBoard(str(out), board)
    (out.with_suffix('.kicad_dru')).write_text('''(version 1)
(rule "USB-C receptacle sits on the board edge"
    (condition "A.memberOfFootprint('J101') || B.memberOfFootprint('J101')")
    (constraint edge_clearance (min 0mm)))
''', encoding='utf-8', newline='\n')
    print(f'wrote {out}: {len(fps)} footprints, {len(nets)} nets; blocks:', {k: len(v) for k, v in blocks.items()})


def build_riser(force):
    out = RISER / 'sn64-v2-riser.kicad_pcb'
    if out.exists() and not force:
        raise SystemExit(f'{out} exists; use --force to rebuild')
    local = {'SN64': RISER / 'libraries/SN64.pretty'}
    comps, nets = read_netlist(RISER / 'validation/sn64-v2-riser.xml')
    board = pcbnew.BOARD()
    rules(board, layers=2, thickness=1.6)
    # Outline: the SummerCart64 tongue (the N64 edge footprint's own Edge.Cuts: +y is the tip, fingers
    # at y 1.25 and 6.0) plus a straight body up to the header, 64.5 mm wide, 24 mm above the shoulders.
    pts = [(-32.25, 0.0), (-32.25, 9.5), (-31.25, 10.5), (31.25, 10.5), (32.25, 9.5), (32.25, 0.0), (32.25, -24.0), (-32.25, -24.0)]
    rect_outline(board, pts)
    fps = {}
    for c in comps:
        fp = load_footprint(c['fp'], local)
        fp.SetReference(c['ref']); fp.SetValue(c['value']); board.Add(fp); fps[c['ref']] = fp
    j1 = fps['J1']
    j1.SetPosition(V(0, 0)); j1.SetOrientationDegrees(0)                 # footprint frame = board frame
    for d in j1.GraphicalItems():                                         # its tongue outline is drawn above
        if d.GetLayerName() == 'Edge.Cuts':
            d.SetLayer(pcbnew.Cmts_User)
    # Right-angle header along the top edge: holes inside the board, bent pins leaving over the edge (-y).
    j2 = fps['J2']
    j2.SetOrientationDegrees(90); j2.SetPosition(V(0, 0))
    pads = [pp.GetPosition() for pp in j2.Pads()]
    x0, y0, x1, y1 = courtyard_box(j2)
    pad_y = sum(pp.y for pp in pads) / len(pads) / 1e6
    if pad_y - (y0 + y1) / 2 < 0:                                         # pads must be on the +y (board) side of the body
        j2.SetOrientationDegrees(270); j2.SetPosition(V(0, 0))
        pads = [pp.GetPosition() for pp in j2.Pads()]
        x0, y0, x1, y1 = courtyard_box(j2)
        pad_y = sum(pp.y for pp in pads) / len(pads) / 1e6
    pad_x = sum(pp.x for pp in pads) / len(pads) / 1e6
    j2.SetPosition(V(mm(-pad_x), mm(-21.0 - pad_y)))                      # pad rows centred at y = -21 (+-1 mm)
    # Keep-out over the contact fingers on both outer layers (the console connector wipes there; the
    # SummerCart64 footprint's single mask opening spans y 3.44-10.56): tracks attach at the pads' top ends.
    k = pcbnew.ZONE(board)
    k.SetIsRuleArea(True); k.SetDoNotAllowTracks(True); k.SetDoNotAllowVias(True)
    k.SetDoNotAllowZoneFills(False); k.SetDoNotAllowPads(False); k.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET(); ls.addLayer(pcbnew.F_Cu); ls.addLayer(pcbnew.B_Cu); k.SetLayerSet(ls)
    k.SetZoneName('finger_keepout')
    for x, y in ((-33.0, 3.1), (33.0, 3.1), (33.0, 11.0), (-33.0, 11.0)):
        k.AppendCorner(V(mm(x), mm(y)), -1)
    board.Add(k)
    for code, (name, nodes) in enumerate(nets.items(), start=1):
        ni = pcbnew.NETINFO_ITEM(board, name, code)
        board.Add(ni)
        for ref, pin in nodes:
            for pad in fps[ref].Pads():
                if pad.GetNumber() == pin:
                    pad.SetNet(ni)
    for x, y in ((-27.0, -19.0), (27.0, -19.0)):
        h = load_footprint('MountingHole:MountingHole_2.5mm', local)
        h.SetReference('H'); h.SetPosition(V(mm(x), mm(y))); board.Add(h)
    board.BuildListOfNets()
    pcbnew.SaveBoard(str(out), board)
    (out.with_suffix('.kicad_dru')).write_text('''(version 1)
(rule "N64 edge fingers reach the board edge (SummerCart64 geometry)"
    (condition "A.memberOfFootprint('J1') || B.memberOfFootprint('J1')")
    (constraint edge_clearance (min 0mm)))
''', encoding='utf-8', newline='\n')
    print(f'wrote {out}: {len(fps)} footprints, {len(nets)} nets')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--only', choices=['main', 'riser'])
    a = ap.parse_args()
    if a.only != 'riser':
        build_main(a.force)
    if a.only != 'main':
        build_riser(a.force)


if __name__ == '__main__':
    sys.exit(main())
