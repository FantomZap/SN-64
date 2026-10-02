"""Take the leftovers of routing off the v2 board: the vias and track ends that KiCad's rule check
calls dangling (KiCad's python). One pass per call; repeat with a fresh report until it removes
nothing.

  python trim_leftovers_v2.py IN.kicad_pcb OUT.kicad_pcb DRC.json

What KiCad calls dangling is not always loose (docs/design/pcb-routing.md), so nothing is deleted on
its word alone:

  via    If two track ends of one layer lie inside it, its copper may be all that joins them. They
         are joined by a short track first. Then the via goes.
  track  One end is free. The track is cut back to the last place where anything else of its net
         touches it: another track's end, a via, a pad. Only a track that nothing touches beyond
         its connected end is removed whole.

The caller refills the zones and runs the check again after every pass. A pass after which the
check lists an open connection or an error is thrown away (the count must never rise). The tool
itself refuses a board whose report already lists an open connection.
"""
import json
import math
import sys
from pathlib import Path

import pcbnew

MM = pcbnew.ToMM
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
EPS = 0.006


def xy(v):
    return (MM(v.x), MM(v.y))


def is_via(t):
    return t.Type() == pcbnew.PCB_VIA_T


def seg_param(p, a, c):
    """(distance from p to the segment a-c, parameter of the nearest point, 0 at a and 1 at c)."""
    dx, dy = c[0] - a[0], c[1] - a[1]
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.dist(p, (a[0] + u * dx, a[1] + u * dy)), u


def main(src, dst, report):
    b = pcbnew.LoadBoard(str(src))
    drc = json.loads(Path(report).read_text(encoding='utf-8'))
    if drc.get('unconnected_items'):
        sys.exit('the report lists %d open connection(s): nothing is trimmed on such a board' % len(drc['unconnected_items']))
    tracks = list(b.GetTracks())
    by_net = {}
    for t in tracks:
        by_net.setdefault(t.GetNetname(), []).append(t)
    pads = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            pads.setdefault(p.GetNetname(), []).append(p)
    zones = [z for z in b.Zones() if not z.GetIsRuleArea()]

    def touches(pt, layer, net, skip):
        """Does anything else of the net touch the point pt on that layer?"""
        P = V(mm(pt[0]), mm(pt[1]))
        for o in by_net.get(net, []):
            if o is skip or o in gone:
                continue
            if is_via(o):
                if math.dist(xy(o.GetPosition()), pt) <= MM(o.GetWidth(layer)) / 2 + EPS:
                    return True
            elif o.GetLayer() == layer:
                d, _ = seg_param(pt, xy(o.GetStart()), xy(o.GetEnd()))
                if d <= MM(o.GetWidth()) / 2 + EPS:
                    return True
        for p in pads.get(net, []):
            if p.IsOnLayer(layer) and p.HitTest(P, mm(0.005)):
                return True
        for z in zones:
            if z.GetNetname() == net and z.IsOnLayer(layer) and z.HitTestFilledArea(layer, P, 0):
                return True
        return False

    gone, added, cut, kept, what = [], 0, 0, [], []
    for v in drc.get('violations', []):
        if v['type'] not in ('via_dangling', 'track_dangling'):
            continue
        it = v['items'][0]
        d = it['description']
        net = d[d.index('[') + 1:d.index(']')]
        pos = (it['pos']['x'], it['pos']['y'])
        if v['type'] == 'via_dangling':
            via = next((t for t in by_net.get(net, []) if is_via(t) and t not in gone and math.dist(xy(t.GetPosition()), pos) <= EPS), None)
            if via is None:
                sys.exit('reported but not found on the board: ' + d)
            r = MM(via.GetWidth(pcbnew.F_Cu)) / 2
            by_layer = {}
            for t in by_net[net]:
                if is_via(t) or t in gone:
                    continue
                for e in (xy(t.GetStart()), xy(t.GetEnd())):
                    if math.dist(e, pos) <= r + EPS:
                        by_layer.setdefault(t.GetLayer(), []).append((t, e))
            for layer, ends in by_layer.items():
                if len(ends) < 2:
                    continue
                for t, e in ends:
                    if math.dist(e, pos) > 0.001:
                        n = pcbnew.PCB_TRACK(b)
                        n.SetStart(V(mm(e[0]), mm(e[1]))); n.SetEnd(V(mm(pos[0]), mm(pos[1]))); n.SetWidth(t.GetWidth()); n.SetLayer(layer)
                        n.SetNetCode(via.GetNetCode())
                        b.Add(n)
                        by_net[net].append(n)
                        added += 1
            gone.append(via)
            what.append('via %s (%.2f, %.2f)' % (net, pos[0], pos[1]))
            continue
        trk = next((t for t in by_net.get(net, []) if not is_via(t) and t not in gone and b.GetLayerName(t.GetLayer()) in d and
                    ('length %.4f mm' % MM(t.GetLength())) in d and
                    min(math.dist(xy(t.GetStart()), pos), math.dist(xy(t.GetEnd()), pos)) <= EPS), None)
        if trk is None:
            sys.exit('reported but not found on the board: ' + d)
        layer = trk.GetLayer()
        s, e = xy(trk.GetStart()), xy(trk.GetEnd())
        s_on, e_on = touches(s, layer, net, trk), touches(e, layer, net, trk)
        if s_on and e_on:
            if math.dist(s, e) <= MM(trk.GetWidth()) + EPS:
                # a piece no longer than it is wide, lying in the copper it joins (the router's neck-down
                # stubs): it carries nothing. The caller's check throws the pass away if that is wrong.
                gone.append(trk)
                what.append('track %s %.2f mm (%.2f, %.2f) removed, shorter than its width' % (net, math.dist(s, e), pos[0], pos[1]))
                continue
            kept.append('track %s (%.2f, %.2f): both ends are joined' % (net, pos[0], pos[1]))
            continue
        if not s_on and not e_on:
            a, c = s, e                         # nothing at either end: keep whatever lies between two junctions on it
        else:
            a, c = (s, e) if s_on else (e, s)   # a is the joined end, c the free one
        # the farthest place along the track, from a, where anything else of the net touches it
        w = MM(trk.GetWidth()) / 2
        far = 0.0 if (s_on or e_on) else None
        near = None
        for o in by_net[net]:
            if o is trk or o in gone:
                continue
            pts = [xy(o.GetPosition())] if is_via(o) else ([xy(o.GetStart()), xy(o.GetEnd())] if o.GetLayer() == layer else [])
            reach = w + (MM(o.GetWidth(layer)) / 2 if is_via(o) else 0.0)
            for q in pts:
                dist, u = seg_param(q, a, c)
                if dist <= reach + EPS:
                    far = u if far is None else max(far, u)
                    near = u if near is None else min(near, u)
        for p in pads.get(net, []):
            if not p.IsOnLayer(layer):
                continue
            for i in range(0, 41):
                u = i / 40
                q = (a[0] + (c[0] - a[0]) * u, a[1] + (c[1] - a[1]) * u)
                if p.HitTest(V(mm(q[0]), mm(q[1])), mm(0.005)):
                    far = u if far is None else max(far, u)
                    near = u if near is None else min(near, u)
        length = math.dist(a, c)
        if far is None or (far * length < 0.02 and (s_on or e_on)) or (not (s_on or e_on) and (near is None or (far - near) * length < 0.02)):
            gone.append(trk)
            what.append('track %s %.2f mm (%.2f, %.2f) removed' % (net, length, pos[0], pos[1]))
            continue
        if far >= 1.0 - 1e-6:
            kept.append('track %s (%.2f, %.2f): something of its net lies at its far end' % (net, pos[0], pos[1]))
            continue
        new_c = (a[0] + (c[0] - a[0]) * far, a[1] + (c[1] - a[1]) * far)
        new_a = a if (s_on or e_on) else (a[0] + (c[0] - a[0]) * near, a[1] + (c[1] - a[1]) * near)
        trk.SetStart(V(mm(new_a[0]), mm(new_a[1]))); trk.SetEnd(V(mm(new_c[0]), mm(new_c[1])))
        cut += 1
        what.append('track %s cut from %.2f to %.2f mm (%.2f, %.2f)' % (net, length, math.dist(new_a, new_c), pos[0], pos[1]))
    for t in gone:
        b.Remove(t)
    pcbnew.SaveBoard(str(dst), b)
    print('removed %d, cut back %d, joined with %d short tracks: %s' % (len(gone), cut, added, '; '.join(what)))
    if kept:
        print('left alone: ' + '; '.join(kept))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
    sys.stdout.flush()
