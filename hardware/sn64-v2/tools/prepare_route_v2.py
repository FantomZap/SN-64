"""Prepare the placed SN64 v2 main board for the autorouter (KiCad's python).

In place on hardware/sn64-v2/sn64-v2.kicad_pcb (run on a fresh build_v2_pcb.py output):
  1. BGA fan-out for U1 (caBGA-381, 0.8 mm): every connected ball in rings 2-10 gets a dog-bone via
     0.4 mm diagonally outward (0.45/0.2 mm) and a 0.15 mm F.Cu stub; ring 1 escapes on F.Cu.
     Same-net neighbours (the inner ground/core balls) share vias where the diagonal lands on
     another ball of the same net.
  2. Planes: In1.Cu GND over the board; In3.Cu FPGA_3V3 over the board; In4.Cu FPGA_1V1 island over
     the core balls and the decoupling bands. F.Cu, In2.Cu, B.Cu (and In4 outside the island) are
     for signals.
  3. Fills the zones, saves, and writes build/route-v2/sn64-v2.dsn (Freerouting fallback).
The netclasses (power 0.4 mm / 0.6 via) come from sn64-v2.kicad_pro (build_v2_schematic.py).
"""
import re
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
PCB = HERE / 'sn64-v2.kicad_pcb'
OUT = REPO / 'build' / 'route-v2'
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
TAG = 'sn64_v2_prepare_route'
PLANES = {'GND': pcbnew.In1_Cu, 'FPGA_3V3': pcbnew.In3_Cu, 'FPGA_1V1': pcbnew.In4_Cu}


def fanout(board):
    u = board.FindFootprintByReference('U1')
    c = u.GetPosition()
    pitch = mm(0.8)
    pads = {}
    for p in u.Pads():
        i = round((p.GetPosition().x - c.x) / pitch + 9.5)
        j = round((p.GetPosition().y - c.y) / pitch + 9.5)
        pads[(i, j)] = p
    n_via = n_shared = 0
    for (i, j), p in pads.items():
        net = p.GetNetname()
        if not net or net.startswith('unconnected'):
            continue
        assert 0 <= i <= 19 and 0 <= j <= 19, (p.GetNumber(), i, j)
        if min(i, 19 - i, j, 19 - j) == 0:
            continue                                   # ring 1: surface escape
        sx = 1 if i >= 10 else -1
        sy = 1 if j >= 10 else -1
        pos = p.GetPosition()
        vpos = V(pos.x + sx * mm(0.4), pos.y + sy * mm(0.4))
        # a same-net ball on the diagonal neighbour: one via between the two, no second via
        nb = pads.get((i + sx, j + sy))
        if nb is not None and nb.GetNetname() == net and min(i + sx, 19 - i - sx, j + sy, 19 - j - sy) != 0:
            if (i + sx, j + sy) in fanout.done:
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pos); t.SetEnd(fanout.done[(i + sx, j + sy)]); t.SetWidth(mm(0.15)); t.SetLayer(pcbnew.F_Cu); t.SetNetCode(p.GetNetCode())
                board.Add(t)
                n_shared += 1
                continue
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetPosition(vpos)
        via.SetDrill(mm(0.2)); via.SetWidth(mm(0.45)); via.SetNetCode(p.GetNetCode())
        board.Add(via)
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pos); t.SetEnd(vpos); t.SetWidth(mm(0.15)); t.SetLayer(pcbnew.F_Cu); t.SetNetCode(p.GetNetCode())
        board.Add(t)
        fanout.done[(i, j)] = vpos
        n_via += 1
    return n_via, n_shared


fanout.done = {}


def add_zone(board, net, layer, pts, name):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNetCode(board.GetNetcodeFromNetname(net))
    z.SetAssignedPriority(0)
    z.SetZoneName(f'{TAG}:{name}')
    z.SetMinThickness(mm(0.15))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.2))
    z.SetThermalReliefSpokeWidth(mm(0.3))
    try:
        z.SetLocalClearance(mm(0.15))
    except Exception:
        pass
    for x, y in pts:
        z.AppendCorner(V(mm(x), mm(y)), -1)
    board.Add(z)
    return z


def planes(board):
    bb = board.GetBoardEdgesBoundingBox()
    x0, y0, x1, y1 = bb.GetLeft() / 1e6 - 1, bb.GetTop() / 1e6 - 1, bb.GetRight() / 1e6 + 1, bb.GetBottom() / 1e6 + 1
    whole = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    add_zone(board, 'GND', PLANES['GND'], whole, 'gnd_in1')
    add_zone(board, 'FPGA_3V3', PLANES['FPGA_3V3'], whole, 'fpga_3v3_in3')
    u = board.FindFootprintByReference('U1')
    c = u.GetPosition()
    xs, ys = [], []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == 'FPGA_1V1' and abs(p.GetPosition().x - c.x) < mm(25) and abs(p.GetPosition().y - c.y) < mm(25):
                xs.append(p.GetPosition().x / 1e6); ys.append(p.GetPosition().y / 1e6)
    m = 1.0
    island = [(min(xs) - m, min(ys) - m), (max(xs) + m, min(ys) - m), (max(xs) + m, max(ys) + m), (min(xs) - m, max(ys) + m)]
    add_zone(board, 'FPGA_1V1', PLANES['FPGA_1V1'], island, 'fpga_1v1_in4')
    return island


def main():
    board = pcbnew.LoadBoard(str(PCB))
    if any(z.GetZoneName().startswith(TAG) for z in board.Zones()) or board.GetTracks():
        raise SystemExit('board already prepared (zones/tracks present); rebuild it with build_v2_pcb.py --force first')
    nv, ns = fanout(board)
    print(f'fan-out vias: {nv} (+{ns} balls sharing a neighbour via)')
    print('1V1 island (mm):', [(round(x, 1), round(y, 1)) for x, y in planes(board)])
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(str(PCB), board)
    OUT.mkdir(parents=True, exist_ok=True)
    dsn = OUT / 'sn64-v2.dsn'
    ok = pcbnew.ExportSpecctraDSN(board, str(dsn))
    print('DSN export:', ok, dsn)
    for n in ('FPGA_1V1', 'FPGA_3V3', 'GND', 'USB_DP', 'N64_AD0'):
        print(f'  {n}: netclass {board.GetNetInfo().GetNetItem(n).GetNetClassName()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
