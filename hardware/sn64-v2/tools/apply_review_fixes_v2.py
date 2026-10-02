"""Carry the findings of the pre-order review of 2026-10-02 into the routed v2 board without losing
its routing (KiCad's python). docs/design/board-verification.md has the findings.

What changes on the board
  * U6 (TLA2528, TI package RTE0016C) gets the footprint its data sheet draws: an exposed pad of
    1.68 x 1.68 mm. The footprint it had was for a package with a 0.8 mm pad, and the router had put
    two signal vias (MON_CART_5V, ADC_SDA) under the area the chip's own pad covers.
  * R17, the pull-up of BOARD_RESET_N, sat on the label side right under U6's pad 2, where the
    cartridge-supply sense line has to come down once it may no longer pass under the chip. It moves
    to the nearest free place, which is on the back face (R17_PLACE), and its old 3.3 V via goes.
  * MON_CART_5V and ADC_SDA are taken up and laid again by the router. With the right exposed pad
    in place it cannot put a via under the chip. Of BOARD_RESET_N only the branch to R17 goes; the
    router joins R17 to the line at its new place.
  * C301 4.7 uF -> 2.2 uF and C304 10 uF -> 4.7 uF: 8.0 uF directly on VBUS where there was 15.8
    (USB allows a device 10 uF). C303 1 nF -> 10 nF: the input selector's output rises at about
    7 V/ms (TI SLVSEA3F figure 7-6), 0.3 A into the 42 uF behind it. Values only, same footprints.

Stages (each its own process: KiCad 10's python breaks lookups after board.Remove()):
  u6      swaps the footprint, sets the three values, moves R17, removes the copper of the two
          nets and R17's two old stubs, and unfills the zones. Refuses a board that already has it.
  (add_plane_vias_v2.py gives R17 its 3.3 V via at the new place.)
  lock    every track and via LOCKED: KiCadRoutingTools never rips locked copper.
  (KiCadRoutingTools routes MON_CART_5V and ADC_SDA; lock again; then BOARD_RESET_N. Command in
          docs/design/pcb-routing.md.)
  unlock  after routing.
  (finish_route_v2.py --refill-only --no-import, then KiCad's rule check.)
  tidy    removes, on the three nets only, the vias with one track end or none that KiCad's check
          lists. A via with two track ends inside it stays (docs/design/pcb-routing.md).

  python apply_review_fixes_v2.py u6 IN.kicad_pcb OUT.kicad_pcb [FACE X Y ROTATION]
  python apply_review_fixes_v2.py lock|unlock IN.kicad_pcb OUT.kicad_pcb
  python apply_review_fixes_v2.py tidy IN.kicad_pcb OUT.kicad_pcb DRC.json
"""
import json
import math
import sys
from pathlib import Path

import pcbnew

KICAD_FP = Path('C:/Program Files/KiCad/10.0/share/kicad/footprints')
U6_LIB, U6_NAME = 'Package_DFN_QFN', 'WQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm'
U6_OLD = 'Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm'
VALUES = {'C301': ('4.7uF 10V', '2.2uF 10V'), 'C304': ('10uF 10V', '4.7uF 10V'), 'C303': ('1nF', '10nF')}
NETS = ('MON_CART_5V', 'ADC_SDA')            # taken up whole
BRANCH = 'BOARD_RESET_N'                     # only its branch to R17 is taken up
R17_WAS = (-11.0, -17.0)
R17_PLACE = ('F', -19.75, -18.75, 90.0)      # face, x, y, rotation: the nearest free place, on the back face (found by a search
                                             # of the board; from the label-side places tried the router could not reach the line)
MM = pcbnew.ToMM
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I


def xy(v):
    return (MM(v.x), MM(v.y))


def is_via(t):
    return t.Type() == pcbnew.PCB_VIA_T


def stage_u6(src, dst, place):
    b = pcbnew.LoadBoard(str(src))
    old = b.FindFootprintByReference('U6')
    if U6_OLD not in old.GetFPIDAsString():
        sys.exit('U6 is %s: the change has been applied' % old.GetFPIDAsString())
    new = pcbnew.FootprintLoad(str(KICAD_FP / (U6_LIB + '.pretty')), U6_NAME)
    if new is None:
        sys.exit('footprint %s:%s not found' % (U6_LIB, U6_NAME))
    nets = {p.GetNumber(): p.GetNet() for p in old.Pads() if p.GetNumber()}
    new.SetReference('U6')
    new.SetValue(old.GetValue())
    new.SetPath(old.GetPath())
    new.SetAttributes(old.GetAttributes())
    try:
        new.SetSheetname(old.GetSheetname()); new.SetSheetfile(old.GetSheetfile())
    except AttributeError:
        pass
    b.Add(new)                                  # FootprintLoad names it without a library nickname, as the board's other parts are
    new.SetPosition(old.GetPosition())
    new.SetOrientationDegrees(old.GetOrientationDegrees())
    missing = []
    for p in new.Pads():
        n = p.GetNumber()
        if not n:
            continue                            # paste-only pieces of the exposed pad
        if n not in nets:
            missing.append(n)
        else:
            p.SetNet(nets[n])
    if missing or len([p for p in new.Pads() if p.GetNumber()]) != len(nets):
        sys.exit('pad numbers do not agree: %s' % missing)
    moved = max(math.dist(xy(p.GetPosition()), xy(q.GetPosition())) for p in new.Pads() for q in old.Pads()
                if p.GetNumber() and p.GetNumber() == q.GetNumber())
    ep = next(p for p in new.Pads() if p.GetNumber() == '17')
    for ref, (was, now) in VALUES.items():
        f = b.FindFootprintByReference(ref)
        if f.GetValue() != was:
            sys.exit('%s is %s, expected %s' % (ref, f.GetValue(), was))
        f.SetValue(now)

    # R17 and the copper that served it where it was
    r17 = b.FindFootprintByReference('R17')
    if math.dist(xy(r17.GetPosition()), R17_WAS) > 0.01:
        sys.exit('R17 is not where it was expected')
    old_pads = {p.GetNumber(): (xy(p.GetPosition()), p.GetNetname()) for p in r17.Pads()}
    stub = []
    p33 = old_pads['1'][0]
    if old_pads['1'][1] != 'FPGA_3V3':
        sys.exit('R17 pad 1 is on %s' % old_pads['1'][1])
    for t in b.GetTracks():                     # the 3.3 V track that starts on R17's pad, and the via it ends in
        if t.GetNetname() == 'FPGA_3V3' and not is_via(t) and min(math.dist(xy(t.GetStart()), p33), math.dist(xy(t.GetEnd()), p33)) < 0.05:
            far = xy(t.GetEnd()) if math.dist(xy(t.GetStart()), p33) < 0.05 else xy(t.GetStart())
            stub.append(t)
            stub += [v for v in b.GetTracks() if is_via(v) and v.GetNetname() == 'FPGA_3V3' and math.dist(xy(v.GetPosition()), far) < 0.01]
    if len(stub) != 2:
        sys.exit('expected one 3.3 V track and one via at R17, found %d items' % len(stub))
    # the branch of BOARD_RESET_N from R17's pad to the first via: the via is on the line itself and stays
    box = next(p for p in r17.Pads() if p.GetNumber() == '2').GetBoundingBox()
    box = (MM(box.GetLeft()), MM(box.GetTop()), MM(box.GetRight()), MM(box.GetBottom()))
    at, branch = None, []
    while True:
        def here(q):                            # on R17's pad for the first piece, at the last piece's far end after that
            return (box[0] <= q[0] <= box[2] and box[1] <= q[1] <= box[3]) if at is None else math.dist(q, at) < 0.05
        nxt = [t for t in b.GetTracks() if t.GetNetname() == BRANCH and not is_via(t) and t not in branch and
               (here(xy(t.GetStart())) or here(xy(t.GetEnd())))]
        if len(nxt) != 1:
            break
        near_start = here(xy(nxt[0].GetStart()))
        branch.append(nxt[0])
        at = xy(nxt[0].GetEnd()) if near_start else xy(nxt[0].GetStart())
        if any(is_via(v) and v.GetNetname() == BRANCH and math.dist(xy(v.GetPosition()), at) < 0.05 for v in b.GetTracks()):
            break
    if not branch or len(branch) > 4:
        sys.exit('the branch of %s to R17 was not found as expected (%d pieces)' % (BRANCH, len(branch)))
    stub += branch
    face, x, y, rot = place
    if face == 'F' and r17.GetLayer() == pcbnew.B_Cu:
        r17.Flip(r17.GetPosition(), False)
    r17.SetPosition(V(mm(x), mm(y)))
    r17.SetOrientationDegrees(rot)
    where = {p.GetNumber(): (round(MM(p.GetPosition().x), 3), round(MM(p.GetPosition().y), 3), p.GetNetname()) for p in r17.Pads()}

    items = [t for t in b.GetTracks() if t.GetNetname() in NETS]
    for z in b.Zones():
        if not z.GetIsRuleArea():
            z.UnFill()
    for t in items + stub:                      # removals last
        b.Remove(t)
    b.Remove(old)
    pcbnew.SaveBoard(str(dst), b)
    print('U6 on %s: signal pads moved %.3f mm at most, exposed pad %.2f x %.2f on %s; %s; R17 to %s (%.2f, %.2f) rot %.0f, pads %s; '
          'removed %d tracks and vias of %s and the two stubs of R17 (%d pieces)'
          % (U6_NAME, moved, MM(ep.GetSize(pcbnew.F_Cu).x), MM(ep.GetSize(pcbnew.F_Cu).y), ep.GetNetname(),
             ', '.join('%s %s' % (r, v[1]) for r, v in VALUES.items()), face, x, y, rot, where, len(items), ', '.join(NETS), len(stub)))


def stage_lock(src, dst, on):
    b = pcbnew.LoadBoard(str(src))
    n = 0
    for t in b.GetTracks():
        if t.IsLocked() != on:
            t.SetLocked(on); n += 1
    pcbnew.SaveBoard(str(dst), b)
    print('%s %d' % ('locked' if on else 'unlocked', n))


def stage_tidy(src, dst, report):
    b = pcbnew.LoadBoard(str(src))
    drc = json.loads(Path(report).read_text(encoding='utf-8'))
    if drc.get('unconnected_items'):
        sys.exit('the report lists %d open connection(s): nothing is tidied on such a board' % len(drc['unconnected_items']))
    tracks = [t for t in b.GetTracks() if t.GetNetname() in NETS + (BRANCH,)]
    gone, what = [], []
    for v in drc.get('violations', []):
        if v['type'] != 'via_dangling':
            continue
        it = v['items'][0]
        d = it['description']
        net = d[d.index('[') + 1:d.index(']')]
        if net not in NETS + (BRANCH,):
            continue
        pos = (it['pos']['x'], it['pos']['y'])
        via = next((t for t in tracks if is_via(t) and t.GetNetname() == net and math.dist(xy(t.GetPosition()), pos) <= 0.006), None)
        if via is None:
            sys.exit('reported but not found on the board: ' + d)
        r = MM(via.GetWidth(pcbnew.F_Cu)) / 2
        ends = sum(1 for t in tracks if not is_via(t) and t.GetNetname() == net
                   for e in (xy(t.GetStart()), xy(t.GetEnd())) if math.dist(e, pos) <= r + 0.005)
        if ends <= 1:
            gone.append(via)
            what.append('via %s (%.2f, %.2f)' % (net, pos[0], pos[1]))
    for t in gone:
        b.Remove(t)
    pcbnew.SaveBoard(str(dst), b)
    print('removed %d leftovers: %s' % (len(gone), '; '.join(what)))


if __name__ == '__main__':
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    stage, src, dst = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if stage == 'tidy':
        stage_tidy(src, dst, sys.argv[4])
    elif stage == 'u6':
        place = (sys.argv[4], float(sys.argv[5]), float(sys.argv[6]), float(sys.argv[7])) if len(sys.argv) > 7 else R17_PLACE
        stage_u6(src, dst, place)
    elif stage in ('lock', 'unlock'):
        stage_lock(src, dst, stage == 'lock')
    else:
        sys.exit(__doc__)
    sys.stdout.flush()
