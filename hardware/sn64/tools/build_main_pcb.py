"""Create hardware/sn64/sn64.kicad_pcb from the exported netlist: stack-up, rules, outline, parts, nets
and a first block placement. Run with KiCad's python.exe. Refuses to overwrite an existing board
unless --force (the board is then edited natively in KiCad / by later scripts, never regenerated).

Coordinates: the N64 edge footprint J1 sits at (0, 0): insertion tip at y = +10.5, tongue shoulders
at y = 0, board body upward (negative y). The lower outline is the SummerCart64 v2 profile
(references/downloads/summercart64/hw/pcb/sc64v2.kicad_pcb, source coords minus (150, 125)),
including the side blocks with the two 2.5 mm shell holes at (+-47.5, 3.25) and the shell-locating
notches; the top edge is extended to y = -TOP. The J1 footprint carries the tongue's Edge.Cuts,
so they are not drawn again.

Rules (PCBWay 6-layer, 1.2 mm to match the N64 edge): clearance 0.1 mm, track 0.15 mm (0.1 mm
allowed in the BGA escape), via 0.45 / 0.2 mm, copper 6 layers.
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parent.parent
SHARE_FP = Path(r'C:/Program Files/KiCad/10.0/share/kicad/footprints')
LOCAL_FP = {'SN64': PROJECT / 'libraries/SN64.pretty', 'SN64_USB': PROJECT / 'libraries/SN64_USB.pretty'}
TOP = 70.0            # provisional board height above the tongue shoulders (mm)
HALF_W = 50.9         # SummerCart64 half width

# SummerCart64 lower profile (local mm, y down, shoulders at 0), left half from the shoulder outward,
# then mirrored. Points go from the tongue shoulder (-32.25, 0) out and up to the top-left corner.
SC64_LEFT = [(-32.25, 0.0), (-37.6, 0.0), (-37.6, 1.5), (-39.55, 1.5), (-39.55, 0.0), (-44.1, 0.0),
             (-44.1, 6.5), (-50.9, 6.5), (-50.9, -21.9), (-49.4, -21.9), (-49.4, -24.9), (-46.9, -24.9),
             (-46.9, -26.4), (-50.9, -26.4)]


def mm(v):
    return pcbnew.FromMM(v)


def load_footprint(fpid):
    lib, name = fpid.split(':', 1)
    path = LOCAL_FP.get(lib) or (SHARE_FP / f'{lib}.pretty')
    fp = pcbnew.FootprintLoad(str(path), name)
    if fp is None:
        raise SystemExit(f'footprint not found: {fpid}')
    return fp


def outline(board):
    # SC64 left profile up to (-50.9, -26.4), then straight up to the taller top corners, then the
    # mirrored right profile back down to the tongue shoulder (the original top was y = -47.3)
    pts = SC64_LEFT + [(-HALF_W, -TOP), (HALF_W, -TOP)] + [(-x, y) for (x, y) in reversed(SC64_LEFT)]
    for a, b in zip(pts, pts[1:]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        seg.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)


def rules(board):
    board.SetCopperLayerCount(6)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(1.2))
    ds.m_MinClearance = mm(0.1)
    ds.m_TrackMinWidth = mm(0.1)
    ds.m_ViasMinSize = mm(0.45)
    ds.m_MinThroughDrill = mm(0.2)
    ds.m_ViasMinAnnularWidth = mm(0.125)
    ds.m_MinSilkTextHeight = mm(0.8)
    ds.m_SolderMaskMinWidth = mm(0.1)
    ds.m_HoleClearance = mm(0.25)
    ds.m_CopperEdgeClearance = mm(0.3)
    # The N64 edge fingers share one solder-mask opening (SummerCart64 footprint, mask polygons):
    # keep the mask-bridge check visible as a warning instead of an error.
    try:
        ds.m_DRCSeverities[pcbnew.DRCE_SOLDERMASK_BRIDGE] = pcbnew.RPT_SEVERITY_WARNING
    except Exception as e:
        print('mask-bridge severity not set:', e)
    try:
        nc = ds.m_NetSettings.GetDefaultNetclass()
        nc.SetClearance(mm(0.1))
        nc.SetTrackWidth(mm(0.15))
        nc.SetViaDiameter(mm(0.45))
        nc.SetViaDrill(mm(0.2))
        nc.SetDiffPairWidth(mm(0.15))
        nc.SetDiffPairGap(mm(0.15))
    except Exception as e:  # API differences between KiCad versions
        print('netclass defaults not set:', e)


def read_netlist(path):
    root = ET.parse(path).getroot()
    comps = []
    for c in root.find('components'):
        comps.append({'ref': c.get('ref'), 'value': c.findtext('value') or '', 'fp': c.findtext('footprint') or '',
                      'sheet': c.find('sheetpath').get('names'),
                      'dnp': any(p.get('name') == 'dnp' for p in c.findall('./property'))})
    nets = {}
    for n in root.find('nets'):
        nets[n.get('name')] = [(node.get('ref'), node.get('pin')) for node in n]
    return comps, nets


def block_of(c):
    ref, sheet, fp = c['ref'], c['sheet'], c['fp']
    if ref == 'J1':
        return 'edge'
    if ref == 'J2':
        return 'joint'
    if ref == 'U401':
        return 'fpga'
    if sheet.startswith('/FPGA/'):
        if ref in ('U402', 'U403', 'U404') or ref.startswith('R4') and int(ref[1:]) < 420:
            return 'n64if'
        if ref.startswith('C4') and 'C_0402' in fp:
            return 'fpga_decap'
        return 'fpga_support'
    if sheet.startswith('/SNES cartridge interface/'):
        return 'cart'
    if sheet.startswith('/Power/'):
        return 'power'
    if sheet.startswith('/USB-C programmer/'):
        return 'usb'
    if sheet.startswith('/AV clock'):
        return 'av'
    return 'misc'


# Block rectangles (x0, y0, x1, y1) in board mm per side; rows fill left-to-right, top-to-bottom.
# Chips, connectors, inductors and 0805/1206 capacitors go on the top side; 0402/0603 passives,
# resistor arrays and test points of the same block go on the bottom side under it.
BLOCKS = {
    ('n64if', 'top'):        (-20.0, -14.0, 30.0, -3.0),
    ('n64if', 'bottom'):     (-12.0, -16.0, 30.0, -3.0),
    ('fpga_support', 'top'): (-30.0, -52.0, 30.0, -43.0),
    ('fpga_support', 'bottom'): (-34.0, -56.0, 34.0, -43.0),
    ('cart', 'top'):         (-41.0, -64.5, 47.0, -51.0),
    ('cart', 'bottom'):      (-41.0, -66.0, 47.0, -45.0),
    ('power', 'top'):        (-49.0, -40.0, -13.0, -3.0),
    ('power', 'bottom'):     (-49.0, -50.0, -12.0, -3.0),
    ('usb', 'top'):          (-49.0, -57.0, -18.0, -34.0),
    ('usb', 'bottom'):       (-49.0, -66.0, -12.0, -36.0),
    ('av', 'top'):           (27.0, -58.0, 40.0, -18.0),
    ('av', 'bottom'):        (20.0, -58.0, 49.0, -12.0),
    ('misc', 'top'):         (27.0, -18.0, 49.0, -10.0),
    ('misc', 'bottom'):      (27.0, -18.0, 49.0, -10.0),
}


def side_of(fp):
    name = fp.GetFPIDAsString()
    return 'bottom' if any(k in name for k in ('0402', '0603', 'R_Array', 'TestPoint')) else 'top'
FIXED = {
    'J1': (0.0, 0.0, 0),
    'J2': (-39.0, -67.0, 90),        # 2x40 right-angle header along the top edge, pins pointing up (pad centroid at x = 0)
    'U401': (0.0, -32.0, 0),         # FPGA, centred
    'J101': (-47.5, -52.0, 90),      # USB-C on the left edge below the top-left screw hole, receptacle facing out
}


def courtyard_box(fp):
    """(x0, y0, x1, y1) in mm of the footprint's courtyard (either side) or bounding box, at its current place."""
    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        c = fp.GetCourtyard(layer)
        if c.OutlineCount():
            bb = c.BBox()
            break
    else:
        bb = fp.GetBoundingBox(False, False)
    return bb.GetLeft() / 1e6, bb.GetTop() / 1e6, bb.GetRight() / 1e6, bb.GetBottom() / 1e6


def courtyard_size(fp):
    x0, y0, x1, y1 = courtyard_box(fp)
    return x1 - x0, y1 - y0


def place_by_attraction(board, fps, blocks, fixed_refs):
    """Connectivity-aware placement inside the block rectangles.

    Parts are ordered by graph distance (over nets with at most BIG_NET pads) from the fixed
    anchors (connectors, FPGA). Each part is pulled to the centroid of the already-placed pads it
    connects to and dropped on the nearest free spot of its block/side, found by a spiral search
    over a 0.25 mm occupancy grid (courtyard + 0.3 mm margin). Chips are placed before passives
    at equal distance so they get the good spots.
    """
    BIG_NET = 12
    net_pads = {}                      # net -> [(ref, x, y)] for placed parts only (updated as we go)
    net_refs = {}                      # net -> set(refs) over small nets
    for fp in fps.values():
        for p in fp.Pads():
            n = p.GetNetname()
            if n:
                net_refs.setdefault(n, set()).add(fp.GetReference())
    small = {n: r for n, r in net_refs.items() if len(r) and sum(1 for fp in fps.values() for p in fp.Pads() if p.GetNetname() == n) <= BIG_NET}
    adj = {}
    for n, refs in small.items():
        for r in refs:
            adj.setdefault(r, set()).update(refs - {r})
    # BFS distance from anchors
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
    # occupancy grid per side
    CELL = 0.25
    occ = {'top': set(), 'bottom': set()}

    def cells(fp, x, y, side):
        """Grid cells the footprint's courtyard (+0.3 mm) would cover with its origin moved to (x, y)."""
        bx0, by0, bx1, by1 = courtyard_box(fp)
        dx = x - fp.GetPosition().x / 1e6
        dy = y - fp.GetPosition().y / 1e6
        x0, y0, x1, y1 = bx0 + dx - 0.15, by0 + dy - 0.15, bx1 + dx + 0.15, by1 + dy + 0.15
        cs = set()
        for i in range(int(x0 // CELL), int(x1 // CELL) + 1):
            for j in range(int(y0 // CELL), int(y1 // CELL) + 1):
                cs.add((i, j))
        return cs

    def record(fp, side):
        occ[side] |= cells(fp, fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6, side)
        if any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in fp.Pads()):   # through-hole parts block both sides
            other = 'top' if side == 'bottom' else 'bottom'
            occ[other] |= cells(fp, fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6, other)
        for p in fp.Pads():
            n = p.GetNetname()
            if n in small:
                net_pads.setdefault(n, []).append((p.GetPosition().x / 1e6, p.GetPosition().y / 1e6))

    # keep-outs: the SummerCart64 shell notches cut into the board sides, plus 1 mm inside every edge
    def block_rect(x0, y0, x1, y1):
        for side in occ:
            for i in range(int(x0 // CELL), int(x1 // CELL) + 1):
                for j in range(int(y0 // CELL), int(y1 // CELL) + 1):
                    occ[side].add((i, j))
    for sx in (-1, 1):
        block_rect(min(sx * 50.9, sx * 45.9) - 1.0, -27.4, max(sx * 50.9, sx * 45.9) + 1.0, -20.9)
    block_rect(-HALF_W - 1, -TOP - 1, HALF_W + 1, -TOP + 1.0)          # top edge band
    block_rect(-HALF_W - 1, -TOP, -HALF_W + 1.0, 8)                    # left edge band
    block_rect(HALF_W - 1.0, -TOP, HALF_W + 1, 8)                      # right edge band
    for r in fixed_refs:
        if r in fps:
            fp = fps[r]
            record(fp, 'bottom' if fp.IsFlipped() else 'top')

    def free(fp, x, y, side, rect):
        bx0, by0, bx1, by1 = courtyard_box(fp)
        dx = x - fp.GetPosition().x / 1e6
        dy = y - fp.GetPosition().y / 1e6
        x0, y0, x1, y1 = rect
        if bx0 + dx < x0 or bx1 + dx > x1 or by0 + dy < y0 or by1 + dy > y1:
            return False
        return not (cells(fp, x, y, side) & occ[side])

    grid_cache = {}

    def spot(fp, tx, ty, side, rect):
        """Nearest free position to (tx, ty) on a 0.5 mm grid inside rect (full search, sorted by distance)."""
        x0, y0, x1, y1 = rect
        key = rect
        if key not in grid_cache:
            xs = [x0 + 0.5 * i for i in range(int((x1 - x0) / 0.5) + 1)]
            ys = [y0 + 0.5 * j for j in range(int((y1 - y0) / 0.5) + 1)]
            grid_cache[key] = [(x, y) for x in xs for y in ys]
        cand = sorted(grid_cache[key], key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2)
        for (x, y) in cand:
            if free(fp, x, y, side, rect):
                return x, y
        return None

    order = []
    for name, items in blocks.items():
        if name == 'fpga_decap':
            continue
        for fp in items:
            r = fp.GetReference()
            big = courtyard_size(fp)[0] * courtyard_size(fp)[1]
            order.append((dist.get(r, 99), 0 if side_of(fp) == 'top' else 1, -big, r, name, fp))
    order.sort(key=lambda t: t[:4])
    unplaced = []
    for d, _, _, r, name, fp in order:
        side = side_of(fp)
        rect = BLOCKS.get((name, side)) or BLOCKS[('misc', side)]
        if side == 'bottom' and not fp.IsFlipped():
            fp.Flip(fp.GetPosition(), False)
        pts = [xy for p in fp.Pads() for xy in net_pads.get(p.GetNetname(), [])]
        if pts:
            tx = sum(x for x, _ in pts) / len(pts)
            ty = sum(y for _, y in pts) / len(pts)
        else:
            tx, ty = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
        tx = min(max(tx, rect[0]), rect[2])
        ty = min(max(ty, rect[1]), rect[3])
        s = spot(fp, tx, ty, side, rect)
        if s is None:
            unplaced.append(r)
            s = (tx, ty)
        fp.SetPosition(pcbnew.VECTOR2I(mm(s[0]), mm(s[1])))
        record(fp, side)
    if unplaced:
        print('  no free spot found for:', unplaced)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--netlist', type=Path, default=PROJECT / 'validation/sn64.xml')
    ap.add_argument('--out', type=Path, default=PROJECT / 'sn64.kicad_pcb')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    if a.out.exists() and not a.force:
        raise SystemExit(f'{a.out} exists; use --force to rebuild from the netlist (placement is lost)')
    comps, nets = read_netlist(a.netlist)
    board = pcbnew.BOARD()
    rules(board)
    outline(board)
    # shell mounting holes (SummerCart64: 2.5 mm at +-47.5, 7.25 above the tip)
    # Shell screw holes, 2.5 mm like SummerCart64: its two at (+-47.5, 3.25) plus four more because this
    # board is taller and carries the socket and USB insertion loads: mid-height and top corners.
    holes = []
    for i, (x, y) in enumerate(((-47.5, 3.25), (47.5, 3.25), (-47.5, -16.0), (47.5, -16.0), (-47.5, -66.0), (47.5, -66.0)), start=1):
        h = load_footprint('MountingHole:MountingHole_2.5mm')
        h.SetReference(f'H{i}')
        h.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        board.Add(h)
        holes.append(h)
    fps = {h.GetReference(): h for h in holes}
    blocks = {}
    for c in comps:
        fp = load_footprint(c['fp'])
        fp.SetReference(c['ref'])
        fp.SetValue(c['value'])
        if c['dnp']:
            fp.SetDNP(True)
        board.Add(fp)
        fps[c['ref']] = fp
        b = block_of(c)
        if c['ref'] in FIXED:
            x, y, rot = FIXED[c['ref']]
            fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
            fp.SetOrientationDegrees(rot)
        elif b == 'fpga_decap':
            blocks.setdefault(b, []).append(fp)
        else:
            blocks.setdefault(b, []).append(fp)
    # nets
    netinfo = {}
    for code, (name, nodes) in enumerate(nets.items(), start=1):
        ni = pcbnew.NETINFO_ITEM(board, name, code)
        board.Add(ni)
        netinfo[name] = ni
        for ref, pin in nodes:
            fp = fps.get(ref)
            if fp is None:
                continue
            found = False
            for pad in fp.Pads():
                if pad.GetNumber() == pin:
                    pad.SetNet(ni)
                    found = True
            if not found:
                print(f'  warning: {ref} pad {pin} not in footprint {fp.GetFPIDAsString()}')
    # FPGA decoupling capacitors on the bottom side in two bands just above and below the BGA's
    # dog-bone via field (x +-7.2, y -39.2..-24.8 for U401 at (0, -32); prepare_route.py), 12 per
    # row at 3.0 mm; placed before the attraction pass so the rest keeps clear of them. The 1.1 V
    # and ground/3.3 V caps reach their planes through vias; a via-in-pad or 0201 layout between
    # the balls would sit closer and is a later refinement.
    decaps = sorted(blocks.get('fpga_decap', []), key=lambda f: f.GetReference())
    rows = (-41.5, -43.7, -22.5, -20.3)
    cols = 12
    for i, fp in enumerate(decaps):
        fp.Flip(fp.GetPosition(), False)
        x = -16.5 + (i % cols) * 3.0
        y = rows[(i // cols) % len(rows)]
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    place_by_attraction(board, fps, blocks, list(FIXED) + [h.GetReference() for h in holes] + [f.GetReference() for f in decaps])
    board.BuildListOfNets()
    pcbnew.SaveBoard(str(a.out), board)
    # custom design rules: the two connectors that sit at the board edge by design
    (a.out.with_suffix('.kicad_dru')).write_text('''(version 1)
(rule "N64 edge fingers reach the board edge (SummerCart64 geometry)"
    (condition "A.memberOfFootprint('J1') || B.memberOfFootprint('J1')")
    (constraint edge_clearance (min 0mm)))
(rule "USB-C receptacle sits on the board edge"
    (condition "A.memberOfFootprint('J101') || B.memberOfFootprint('J101')")
    (constraint edge_clearance (min 0mm)))
''', encoding='utf-8', newline='\n')
    print(f'wrote {a.out}: {len(fps)} footprints, {len(nets)} nets; blocks:', {k: len(v) for k, v in blocks.items()})


if __name__ == '__main__':
    main()
