"""Import a Freerouting session into hardware/sn64/sn64.kicad_pcb, add GND pours on the outer
layers, refill every zone and save (KiCad's python).

  python finish_route.py [--ses build/route-pcb/sn64.ses] [--no-pour]
"""
import argparse
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
PCB = HERE / 'sn64.kicad_pcb'
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
TAG = 'sn64_finish_route'


def pour(board, layer, name):
    bb = board.GetBoardEdgesBoundingBox()
    x0, y0, x1, y1 = bb.GetLeft() / 1e6 - 1, bb.GetTop() / 1e6 - 1, bb.GetRight() / 1e6 + 1, bb.GetBottom() / 1e6 + 1
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNetCode(board.GetNetcodeFromNetname('/GND'))
    z.SetAssignedPriority(0)
    z.SetZoneName(f'{TAG}:{name}')
    z.SetMinThickness(mm(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.2))
    z.SetThermalReliefSpokeWidth(mm(0.3))
    try:
        z.SetLocalClearance(mm(0.2))
    except Exception:
        pass
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        z.AppendCorner(V(mm(x), mm(y)), -1)
    board.Add(z)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ses', type=Path, default=REPO / 'build' / 'route-pcb' / 'sn64.ses')
    ap.add_argument('--board', type=Path, default=PCB, help='board to finish (default: the tracked main board)')
    ap.add_argument('--no-import', action='store_true', help='board already carries the routing (e.g. KiCadRoutingTools output)')
    ap.add_argument('--no-pour', action='store_true')
    a = ap.parse_args()
    board = pcbnew.LoadBoard(str(a.board))
    before = len(list(board.GetTracks()))
    ok = True if a.no_import else pcbnew.ImportSpecctraSES(board, str(a.ses))
    tracks = list(board.GetTracks())
    n_via = sum(1 for t in tracks if t.GetClass() == 'PCB_VIA')
    print(f'SES import: {ok}; tracks+vias {before} -> {len(tracks)} ({n_via} vias)')
    # The importer gives the plane-net (power class) vias the class drill (0.3 mm) while the BGA
    # dog-bones keep their 0.45 mm diameter, which breaks the annular-ring rule: pin every via's
    # drill to its diameter (0.45 -> 0.2, 0.6 -> 0.3), and never widen a via inside the BGA field.
    u = board.FindFootprintByReference('U401')
    c = u.GetPosition()
    fixed = 0
    for t in tracks:
        if t.GetClass() != 'PCB_VIA':
            continue
        w = t.GetWidth(pcbnew.F_Cu)      # KiCad 10: PCB_VIA.GetWidth() without a layer asserts (and hangs in a dialog)
        in_bga = abs(t.GetPosition().x - c.x) < mm(8.2) and abs(t.GetPosition().y - c.y) < mm(8.2)
        if in_bga and w != mm(0.45):
            t.SetWidth(mm(0.45)); w = mm(0.45); fixed += 1
        drill = mm(0.2) if w <= mm(0.5) else mm(0.3)
        if t.GetDrillValue() != drill:
            t.SetDrill(drill); fixed += 1
    print(f'via geometry corrected on {fixed} vias')
    for z in list(board.Zones()):
        if z.GetZoneName().startswith(TAG):
            board.Remove(z)
    if not a.no_pour:
        pour(board, pcbnew.F_Cu, 'gnd_fcu')
        pour(board, pcbnew.B_Cu, 'gnd_bcu')
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(a.board), board)
    print('saved', a.board)
    sys.stdout.flush()
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
