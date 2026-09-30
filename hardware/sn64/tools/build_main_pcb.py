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
    pts = SC64_LEFT + [(-x, y) for (x, y) in reversed(SC64_LEFT)]
    # extend the SC64 top (y = -47.3 in the original) upward to -TOP: replace the last left point and
    # first right point by the taller corners
    pts = [p for p in pts]
    pts[len(SC64_LEFT) - 1] = (-HALF_W, -TOP)
    pts[len(SC64_LEFT)] = (HALF_W, -TOP)
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
    ('n64if', 'top'):        (-30.0, -14.0, 30.0, -3.0),
    ('n64if', 'bottom'):     (-30.0, -14.0, 30.0, -3.0),
    ('fpga_support', 'top'): (-26.0, -53.5, 26.0, -47.0),
    ('fpga_support', 'bottom'): (-26.0, -53.5, 26.0, -47.0),
    ('cart', 'top'):         (-41.0, -64.5, 47.0, -54.0),
    ('cart', 'bottom'):      (-41.0, -64.5, 47.0, -54.0),
    ('power', 'top'):        (-49.0, -35.0, -22.0, -3.0),
    ('power', 'bottom'):     (-49.0, -35.0, -13.0, -3.0),
    ('usb', 'top'):          (-49.0, -55.0, -22.0, -36.0),
    ('usb', 'bottom'):       (-49.0, -55.0, -22.0, -36.0),
    ('av', 'top'):           (27.0, -58.0, 40.0, -18.0),
    ('av', 'bottom'):        (27.0, -58.0, 40.0, -18.0),
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
    'J101': (-47.5, -61.0, 90),      # USB-C on the left edge near the top corner, receptacle facing out
    'J701': (46.0, -38.0, 270),      # HDMI on the right edge
}


def courtyard_size(fp):
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else fp.GetBoundingBox(False, False)
    return bb.GetWidth() / 1e6, bb.GetHeight() / 1e6


def place_blocks(fps, blocks):
    """Row-fill each block rectangle with its footprints, largest first, 0.4 mm gaps."""
    for (name, side), (x0, y0, x1, y1) in BLOCKS.items():
        items = [f for f in blocks.get(name, []) if side_of(f) == side]
        items.sort(key=lambda f: -courtyard_size(f)[0] * courtyard_size(f)[1])
        x, y, row_h = x0, y0, 0.0
        for fp in items:
            if side == 'bottom':
                fp.Flip(fp.GetPosition(), False)
            w, h = courtyard_size(fp)
            w += 0.4
            h += 0.4
            if x + w > x1 and x > x0:
                x = x0
                y += row_h
                row_h = 0.0
            fp.SetPosition(pcbnew.VECTOR2I(mm(x + w / 2), mm(y + h / 2)))
            x += w
            row_h = max(row_h, h)
        if items and y + row_h > y1 + 0.01:
            print(f'  block {name}/{side}: overflows its rectangle by {y + row_h - y1:.1f} mm ({len(items)} parts)')


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
    for x in (-47.5, 47.5):
        h = load_footprint('MountingHole:MountingHole_2.5mm')
        h.SetReference('H1' if x < 0 else 'H2')
        h.SetPosition(pcbnew.VECTOR2I(mm(x), mm(3.25)))
        board.Add(h)
    fps = {}
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
    place_blocks(fps, blocks)
    # FPGA decoupling capacitors on the bottom side under the BGA, in a grid
    decaps = sorted(blocks.get('fpga_decap', []), key=lambda f: f.GetReference())
    cols = 6
    for i, fp in enumerate(decaps):
        fp.Flip(fp.GetPosition(), False)
        x = -7.5 + (i % cols) * 3.0
        y = -38.0 + (i // cols) * 2.2
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    board.BuildListOfNets()
    pcbnew.SaveBoard(str(a.out), board)
    print(f'wrote {a.out}: {len(fps)} footprints, {len(nets)} nets; blocks:', {k: len(v) for k, v in blocks.items()})


if __name__ == '__main__':
    main()
