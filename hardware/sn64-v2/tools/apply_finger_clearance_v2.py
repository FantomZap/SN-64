"""Keep the ground fill out of the N64 edge fingers of the routed v2 board, and give the ground
fingers the ground plane instead (KiCad's python).

  python apply_finger_clearance_v2.py [--board sn64-v2.kicad_pcb] [--out OUT.kicad_pcb]

Found in the pre-order review of 2026-10-02 (docs/design/board-verification.md). The solder mask is
open across the whole row of fingers, as on SummerCart64's edge, so every piece of copper in that
window is bare and gold-plated like the fingers themselves. The outer ground fills had been poured
over the whole board, and the keep-out strips between the fingers only kept tracks and vias out:
the fill ran between every two fingers, 0.2 mm from each, and joined into a band across the tip
0.3 mm from the board's edge, where the bevel is cut. A contact of the console's connector that
sits a little to one side would have joined a finger to ground. SummerCart64's own board has no
fill there at all (references/downloads/summercart64/hw/pcb/sc64v2.kicad_pcb: the fill ends 0.4 mm
above the finger pads).

Two changes, then every zone is filled again. Tracks, vias and pads are not touched.

  1. One rule area over the finger zone on both outer layers keeps copper fills out, from 0.2 mm
     above the pads' upper ends to beyond the tip.
  2. The ground plane on In1 ended 3.5 mm above the fingers, because it was drawn before the board
     had its tongue. Its lower edge moves down to the same line, so that the via at the top of
     every ground finger lands in the plane. Until now those vias only joined the two outer fills,
     and one pair of ground fingers (6 and 31) reached the rest of the ground only through the
     copper between the fingers. The inner layers stay free of copper under the fingers.

Before it saves, the tool asks KiCad's own connectivity whether every ground pad, via and track of
the board is one piece, and whether the finger window is free of fill.
"""
import argparse
import sys
from pathlib import Path

import pcbnew

V2 = Path(__file__).resolve().parents[1]
MM = pcbnew.ToMM
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
NAME = 'finger_no_fill'
PLANE = 'sn64_v2_prepare_route:gnd_in1'
X = 33.0                         # the tongue is 64.6 mm wide (SummerCart64 outline)
Y_TIP = 11.0                     # beyond the tip at y = 10.5
GAP = 0.2                        # the fill's own clearance to a pad; the area starts that far above the pads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--board', type=Path, default=V2 / 'sn64-v2.kicad_pcb')
    ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    b = pcbnew.LoadBoard(str(a.board))
    if any(z.GetZoneName() == NAME for z in b.Zones()):
        sys.exit('the board already has the area %s' % NAME)
    j1 = b.FindFootprintByReference('J1')
    top = min(MM(p.GetBoundingBox().GetTop()) for p in j1.Pads())
    y0 = round(top - GAP, 3)
    k = pcbnew.ZONE(b)
    k.SetIsRuleArea(True)
    k.SetDoNotAllowZoneFills(True)
    k.SetDoNotAllowTracks(False); k.SetDoNotAllowVias(False); k.SetDoNotAllowPads(False); k.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET(); ls.addLayer(pcbnew.F_Cu); ls.addLayer(pcbnew.B_Cu)
    k.SetLayerSet(ls)
    k.SetZoneName(NAME)
    for x, y in ((-X, y0), (X, y0), (X, Y_TIP), (-X, Y_TIP)):
        k.AppendCorner(V(mm(x), mm(y)), -1)
    b.Add(k)

    plane = next(z for z in b.Zones() if z.GetZoneName() == PLANE)
    o = plane.Outline()
    low = max(o.CVertex(i).y for i in range(o.TotalVertices()))
    moved = 0
    for i in range(o.TotalVertices()):
        v = o.CVertex(i)
        if v.y == low:
            o.SetVertex(i, V(v.x, mm(y0)))
            moved += 1
    if moved != 2:
        sys.exit('the ground plane outline is not the rectangle this tool expects')
    plane.HatchBorder()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.BuildConnectivity()

    fills = [z for z in b.Zones() if not z.GetIsRuleArea()]
    left = 0
    for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
        for z in fills:
            if not z.IsOnLayer(lay):
                continue
            for ix in range(-131, 132):
                for iy in range(0, 42):
                    if z.HitTestFilledArea(lay, V(mm(ix * 0.25), mm(y0 + 0.05 + iy * 0.2)), 0):
                        left += 1
    if left:
        sys.exit('%d points of the finger window still carry fill' % left)
    inner = 0
    for z in fills:
        for lay in z.GetLayerSet().Seq():
            if lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                continue
            for ix in range(-131, 132):
                for iy in range(0, 42):
                    if z.HitTestFilledArea(lay, V(mm(ix * 0.25), mm(top + iy * 0.2)), 0):
                        inner += 1
    if inner:
        sys.exit('%d points under the fingers carry copper on an inner layer' % inner)
    conn = b.GetConnectivity()
    ref = next(p for p in b.FindFootprintByReference('U1').Pads() if p.GetNetname() == 'GND')
    main_piece = {i.m_Uuid.AsString() for i in conn.GetConnectedItems(ref, 0)} | {ref.m_Uuid.AsString()}
    loose = ['%s.%s' % (f.GetReference(), p.GetNumber()) for f in b.GetFootprints() for p in f.Pads()
             if p.GetNetname() == 'GND' and p.m_Uuid.AsString() not in main_piece]
    loose += ['%s (%.2f, %.2f)' % (t.GetClass(), MM(t.GetStart().x), MM(t.GetStart().y)) for t in b.GetTracks()
              if t.GetNetname() == 'GND' and t.m_Uuid.AsString() not in main_piece]
    if loose:
        sys.exit('ground no longer in one piece: ' + ', '.join(loose[:12]))
    if conn.GetUnconnectedCount(True):
        sys.exit('%d open connection(s) after the change' % conn.GetUnconnectedCount(True))
    in_plane = sum(1 for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == 'GND'
                   and abs(t.GetPosition().x) < mm(X) and mm(-1.0) < t.GetPosition().y < mm(y0)
                   and plane.HitTestFilledArea(pcbnew.In1_Cu, t.GetPosition(), 0))
    out = a.out or a.board
    pcbnew.SaveBoard(str(out), b)
    print('rule area %s on F.Cu and B.Cu, x %.1f..%.1f, y %.2f..%.1f; ground plane on In1 down to y %.2f, %d ground vias at the '
          'fingers now in it; no fill in the finger window, no inner copper under the fingers; ground is one piece '
          '(%d items); saved %s' % (NAME, -X, X, y0, Y_TIP, y0, in_plane, len(main_piece), Path(out).name))
    sys.stdout.flush()


if __name__ == '__main__':
    main()
