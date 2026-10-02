"""Close the three open connections and the five thermal-relief errors that KiCad's rule check
listed on the v2 board on 2026-10-02 (KiCad's python). After it the check lists no error and no
open connection.

  python close_open_items_v2.py small [--board sn64-v2.kicad_pcb]
  python close_open_items_v2.py corner-clear IN.kicad_pcb OUT.kicad_pcb
  python close_open_items_v2.py corner-tidy IN.kicad_pcb OUT.kicad_pcb DRC.json
  python close_open_items_v2.py solid [--board sn64-v2.kicad_pcb]

small         Run once; a board that already has the change is refused.
  1. N64_JOYBUS. The line from the FPGA ball to the edge finger was complete all along. What the
     check reported was a via of that net at (0.0, -13.0) with no track on it, left over from the
     first routing. It is removed.
  2. FPGA_3V3 at the supply converter's digital supply pin (U6 pad 10). The pad had no copper at
     all. A 0.15 mm track on the component side joins it to the 3.3 V via at (-16.425, -16.0),
     found by the grid search of apply_enable_fix_v2.py, which keeps 0.15 mm from everything else
     on that layer.

corner-clear  FLASH_D2 between the flash and FPGA ball Y2 was the real one. Y2 is in the corner of
              the ball grid and was boxed in by the ways out of its two neighbours, DONE (ball Y3)
              and flash D0 (ball W2); the router could not reach it with those in place, on three
              layers or on four. This stage removes the copper of the three nets, unfills the
              zones and locks everything else, so that the router lays the three together:
                route.py IN OUT --nets FLASH_D2 FPGA_DONE FLASH_D0 --layers F.Cu In2.Cu B.Cu
                         --ordering mps   (other options as in docs/design/pcb-routing.md)
              All three are routed, with each of the three orderings.
corner-tidy   After routing: unlocks, and deals with the vias of the three nets that KiCad's check
              reports as joining nothing on a second layer. The router had used one as a patch of
              copper between two track ends on the component side, right beside ball Y2: taking it
              away cut the line, so it is replaced by a short track and the hole is gone. A via
              with one track end or none on it is a leftover and is removed. Then refill
              (finish_route_v2.py --refill-only --no-import) and check again. The count of open
              connections must not rise.
solid         Five ground pads had one thermal spoke where the board's rule asks for two: the four
              ground pads of the USB-C receptacle (J101 A1, B12, A12, B1) and pad 5 of the input
              switch U7. Their neighbours leave no room for a second spoke. They are joined to the
              ground pour without spokes; refill afterwards. Ground copper against the pad's edge:
              0.30 mm before and 2.07 mm after at the receptacle, 0.19 and 0.99 mm at U7.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_enable_fix_v2 import route, xy, is_via, MM, mm, V      # noqa: E402

V2 = Path(__file__).resolve().parents[1]
STRAY_VIA = ('N64_JOYBUS', (0.0, -13.0))
PAD = ('U6', '10', 'FPGA_3V3')
TARGET_VIA = (-16.425, -16.0)
WINDOW = (-17.8, -18.8, -14.2, -15.2)
CORNER = ('FLASH_D2', 'FPGA_DONE', 'FLASH_D0')
SOLID = (('J101', 'A1'), ('J101', 'B12'), ('J101', 'A12'), ('J101', 'B1'), ('U7', '5'))


def small(board_path):
    b = pcbnew.LoadBoard(str(board_path))
    F = pcbnew.F_Cu
    net, pos = STRAY_VIA
    tracks = list(b.GetTracks())
    stray = [t for t in tracks if is_via(t) and t.GetNetname() == net and math.dist(xy(t.GetPosition()), pos) < 0.01]
    if not stray:
        sys.exit('no %s via at %s: the change has been applied' % (net, pos))
    via = stray[0]
    r = MM(via.GetWidth(F)) / 2
    touching = [t for t in tracks if not is_via(t) and t.GetNetname() == net and
                min(math.dist(xy(t.GetStart()), pos), math.dist(xy(t.GetEnd()), pos)) <= r + 0.01]
    if touching:
        sys.exit('the via at %s has %d track(s) on it: it is not a leftover' % (pos, len(touching)))

    ref, num, name = PAD
    pad = next(p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == num)
    if pad.GetNetname() != name:
        sys.exit('%s pad %s is on %s' % (ref, num, pad.GetNetname()))
    target = [t for t in tracks if is_via(t) and t.GetNetname() == name and math.dist(xy(t.GetPosition()), TARGET_VIA) < 0.01]
    if len(target) != 1:
        sys.exit('no %s via at %s' % (name, TARGET_VIA))
    start = xy(pad.GetPosition())
    pts = route(b, F, name, start, TARGET_VIA, WINDOW)
    code = b.GetNetcodeFromNetname(name)
    length = 0.0
    for p, q in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(V(mm(p[0]), mm(p[1]))); t.SetEnd(V(mm(q[0]), mm(q[1]))); t.SetWidth(mm(0.15)); t.SetLayer(F); t.SetNetCode(code)
        b.Add(t)
        length += math.dist(p, q)
    print('F.Cu %s: %s (%.1f mm)' % (name, ' -> '.join('(%.2f, %.2f)' % p for p in pts), length))
    b.Remove(via)                                   # last: lookups break after a removal in KiCad 10's python
    pcbnew.SaveBoard(str(board_path), b)
    print('removed the leftover %s via at %s; saved %s' % (net, pos, Path(board_path).name))


def corner_clear(src, dst):
    b = pcbnew.LoadBoard(str(src))
    y2 = next(p for p in b.FindFootprintByReference('U1').Pads() if p.GetNumber() == 'Y2')
    if len(b.GetConnectivity().GetConnectedItems(y2)) > 1:
        sys.exit('ball Y2 already has copper: the change has been applied')
    items = [t for t in b.GetTracks() if t.GetNetname() in CORNER]
    for z in b.Zones():
        if not z.GetIsRuleArea():
            z.UnFill()
    locked = 0
    for t in b.GetTracks():
        if t.GetNetname() not in CORNER and not t.IsLocked():
            t.SetLocked(True); locked += 1
    for t in items:
        b.Remove(t)
    pcbnew.SaveBoard(str(dst), b)
    print('removed %d tracks and vias of %s; locked %d others' % (len(items), ', '.join(CORNER), locked))


def corner_tidy(src, dst, report):
    b = pcbnew.LoadBoard(str(src))
    unlocked = 0
    for t in b.GetTracks():
        if t.IsLocked():
            t.SetLocked(False); unlocked += 1
    drc = json.loads(Path(report).read_text(encoding='utf-8'))
    items = [t for t in b.GetTracks() if t.GetNetname() in CORNER]
    gone, what = [], []
    for v in drc.get('violations', []):
        if v['type'] != 'via_dangling':
            continue
        it = v['items'][0]
        d = it['description']
        net = d[d.index('[') + 1:d.index(']')] if '[' in d else ''
        if net not in CORNER:
            continue
        pos = (it['pos']['x'], it['pos']['y'])
        via = next((t for t in items if is_via(t) and t.GetNetname() == net and math.dist(xy(t.GetPosition()), pos) <= 0.006), None)
        if via is None:
            sys.exit('reported but not found on the board: ' + d)
        r = MM(via.GetWidth(pcbnew.F_Cu)) / 2
        ends = [(t, e) for t in items if not is_via(t) and t.GetNetname() == net
                for e in (xy(t.GetStart()), xy(t.GetEnd())) if math.dist(e, pos) <= r + 0.005]
        layers = {t.GetLayer() for t, _ in ends}
        if len(ends) >= 2 and len(layers) == 1:
            # The router used the via as a patch of copper between two track ends on one layer.
            # KiCad calls it loose, but without it the line is cut: put track where the patch was.
            layer = layers.pop()
            for t, e in ends:
                if math.dist(e, pos) > 0.001:
                    n = pcbnew.PCB_TRACK(b)
                    n.SetStart(V(mm(e[0]), mm(e[1]))); n.SetEnd(V(mm(pos[0]), mm(pos[1]))); n.SetWidth(t.GetWidth()); n.SetLayer(layer)
                    n.SetNetCode(via.GetNetCode())
                    b.Add(n)
            gone.append(via)
            what.append('via %s at (%.2f, %.2f) replaced by track on %s' % (net, pos[0], pos[1], b.GetLayerName(layer)))
        elif len(ends) <= 1:
            gone.append(via)
            what.append('via %s at (%.2f, %.2f) removed' % (net, pos[0], pos[1]))
    for t in gone:
        b.Remove(t)
    pcbnew.SaveBoard(str(dst), b)
    print('unlocked %d; %d vias dealt with: %s' % (unlocked, len(gone), '; '.join(what)))


def solid(board_path):
    b = pcbnew.LoadBoard(str(board_path))
    changed = []
    for ref, num in SOLID:
        pads = [p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == num]
        if len(pads) != 1 or pads[0].GetNetname() != 'GND':
            sys.exit('%s pad %s: expected one ground pad' % (ref, num))
        if pads[0].GetLocalZoneConnection() != pcbnew.ZONE_CONNECTION_FULL:
            pads[0].SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
            changed.append('%s.%s' % (ref, num))
    if not changed:
        sys.exit('the five pads are solid already: the change has been applied')
    pcbnew.SaveBoard(str(board_path), b)
    print('joined to the ground area without thermal spokes: %s; saved %s' % (', '.join(changed), Path(board_path).name))


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else ''
    if stage in ('small', 'solid'):
        ap = argparse.ArgumentParser()
        ap.add_argument('stage')
        ap.add_argument('--board', type=Path, default=V2 / 'sn64-v2.kicad_pcb')
        (small if stage == 'small' else solid)(ap.parse_args().board)
    elif stage == 'corner-clear':
        corner_clear(Path(sys.argv[2]), Path(sys.argv[3]))
    elif stage == 'corner-tidy':
        corner_tidy(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    else:
        sys.exit(__doc__)
    sys.stdout.flush()
