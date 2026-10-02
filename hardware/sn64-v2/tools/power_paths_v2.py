"""Follow each supply path of the v2 board through its copper and report the narrowest track on it,
its length, its vias and its resistance (KiCad's python). Read only.

  python power_paths_v2.py [--board sn64-v2.kicad_pcb] [--json OUT.json]

A supply net can be 0.4 mm wide almost everywhere and still pass through one thin piece. This tool
builds the net's copper as a graph (track pieces between junctions, vias, pads) and, for every path
it is asked about, finds the route whose narrowest piece is widest. It reports that width, the
route's length by layer, the number of vias, and the resistance at 20 C with the copper thickness
PCBWay is asked for (35 um outer, 17.5 um inner; a via barrel as 20 um of plating).

Copper fills are not followed: a path that needs a fill is reported as not found. The supply paths
asked about here run on tracks. The three plane nets (ground, 3.3 V, 1.1 V) are not asked about.
"""
import argparse
import heapq
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

V2 = Path(__file__).resolve().parents[1]
MM = pcbnew.ToMM
RHO = 1.72e-8                                   # ohm metre, copper at 20 C
T_OUTER, T_INNER, T_BARREL = 35e-6, 17.5e-6, 20e-6
# net, from (ref, pads), to (ref, pads), what it carries
PATHS = (
    ('HOST_3V3', ('J1', ('9', '17', '34', '42')), ('U7', ('2',)), "console's 3.3 V: edge fingers to the input selector"),
    ('USB_VBUS', ('J101', ('A4', 'A9', 'B4', 'B9')), ('U7', ('7',)), 'USB 5 V: socket to the input selector'),
    ('SYS_VIN', ('U7', ('1', '8')), ('U8', ('12', '13', '14')), 'input selector to the 5 V converter'),
    ('5V_SYS', ('U8', ('7', '8')), ('U9', ('4',)), '5 V converter to the 3.3 V converter'),
    ('5V_SYS', ('U8', ('7', '8')), ('U10', ('4',)), '5 V converter to the 1.1 V converter'),
    ('5V_SYS', ('U8', ('7', '8')), ('U12', ('1',)), '5 V converter to the cartridge switch'),
    ('SNES_5V_CART', ('U12', ('6',)), ('J2', ('27',)), 'cartridge switch to socket pin 27'),
    ('SNES_5V_CART', ('U12', ('6',)), ('J2', ('58',)), 'cartridge switch to socket pin 58'),
    ('FPGA_2V5', ('U11', ('5',)), ('U1', None), '2.5 V regulator to the FPGA (nearest ball)'),
)


def on_segment(p, a, c):
    dx, dy = c[0] - a[0], c[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.dist(p, a), 0.0
    u = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.dist(p, (a[0] + u * dx, a[1] + u * dy)), u


def net_graph(b, net):
    tracks = [t for t in b.GetTracks() if t.GetNetname() == net]
    segs = [(t.GetLayer(), (MM(t.GetStart().x), MM(t.GetStart().y)), (MM(t.GetEnd().x), MM(t.GetEnd().y)), MM(t.GetWidth()))
            for t in tracks if t.Type() != pcbnew.PCB_VIA_T]
    vias = [(MM(t.GetPosition().x), MM(t.GetPosition().y), MM(t.GetWidth(pcbnew.F_Cu)) / 2, MM(t.GetDrillValue())) for t in tracks if t.Type() == pcbnew.PCB_VIA_T]
    key = lambda lay, p: (lay, round(p[0], 3), round(p[1], 3))
    edges = defaultdict(list)                   # node -> [(node, width, length, layer or 'via')]

    reach = defaultdict(float)                  # node -> half the width of the widest track that ends there

    def link(n1, n2, w, length, what):
        edges[n1].append((n2, w, length, what))
        edges[n2].append((n1, w, length, what))
        if what not in ('via', 'pad'):
            reach[n1] = max(reach[n1], w / 2)
            reach[n2] = max(reach[n2], w / 2)

    points = defaultdict(list)                  # layer -> points that can split a segment
    for lay, a, c, w in segs:
        points[lay] += [a, c]
    for x, y, r, d in vias:
        for lay in {s[0] for s in segs}:
            points[lay].append((x, y))
    for lay, a, c, w in segs:
        cuts = {0.0: a, 1.0: c}
        for p in points[lay]:
            dist, u = on_segment(p, a, c)
            if dist <= w / 2 + 0.005 and 0.0 < u < 1.0:
                cuts[round(u, 6)] = p
        us = sorted(cuts)
        for u0, u1 in zip(us, us[1:]):
            p0, p1 = cuts[u0], cuts[u1]
            n0, n1 = key(lay, p0), key(lay, p1)
            if n0 != n1:
                link(n0, n1, w, math.dist(p0, p1), lay)
        # end points that lie on the segment but a little off its centre line
        for p in points[lay]:
            dist, u = on_segment(p, a, c)
            if 0.0005 < dist <= w / 2 + 0.005:
                q = (a[0] + u * (c[0] - a[0]), a[1] + u * (c[1] - a[1]))
                link(key(lay, p), key(lay, cuts.get(round(u, 6), q)) if round(u, 6) in cuts else key(lay, min(cuts.values(), key=lambda v: math.dist(v, q))), w, dist, lay)
    layers = sorted({s[0] for s in segs})
    for x, y, r, d in vias:
        hub = ('via', round(x, 3), round(y, 3))
        for lay in layers:
            for n in [n for n in list(edges) if n[0] == lay and math.dist((n[1], n[2]), (x, y)) <= r + 0.005]:
                link(hub, n, math.pi * d, 0.0, 'via')
    # a pad joins every track end and via that lies in it
    track_nodes = [n for n in list(edges) if n[0] not in ('via', 'pad')]
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() != net:
                continue
            hub = ('pad', f.GetReference(), p.GetNumber())
            size = min(MM(p.GetSize().x), MM(p.GetSize().y))
            for n in track_nodes:
                if p.IsOnLayer(n[0]) and p.HitTest(pcbnew.VECTOR2I(pcbnew.FromMM(n[1]), pcbnew.FromMM(n[2])), pcbnew.FromMM(reach[n] + 0.005)):
                    link(hub, n, size, 0.0, 'pad')
            edges[hub] += []
    return edges, segs, vias


def pad_nodes(b, edges, ref, numbers, net):
    return {n for n in edges if n[0] == 'pad' and n[1] == ref and (numbers is None or n[2] in numbers) and edges[n]}


def widest(edges, sources, targets):
    """The route from any source to any target whose narrowest piece is widest; ties go to the shorter one."""
    best = {}
    heap = [(-9.0, 0.0, i, n, None) for i, n in enumerate(sources)]
    count = len(heap)
    prev = {}
    while heap:
        negw, length, _, n, came = heapq.heappop(heap)
        if n in best:
            continue
        best[n] = (-negw, length)
        prev[n] = came
        if n in targets:
            route = []
            while prev[n] is not None:
                pn, w, ln, what = prev[n]
                route.append((w, ln, what))
                n = pn
            return -negw, route
        for m, w, ln, what in edges[n]:
            if m not in best:
                count += 1
                heapq.heappush(heap, (max(negw, -w), length + ln, count, m, (n, w, ln, what)))
    return None, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--board', type=Path, default=V2 / 'sn64-v2.kicad_pcb')
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()
    b = pcbnew.LoadBoard(str(a.board))
    graphs, rows = {}, []
    for net, (r1, p1), (r2, p2), what in PATHS:
        if net not in graphs:
            graphs[net] = net_graph(b, net)
        edges = graphs[net][0]
        src, dst = pad_nodes(b, edges, r1, p1, net), pad_nodes(b, edges, r2, p2, net)
        w, route = widest(edges, set(src), set(dst)) if src and dst else (None, [])
        if w is None:
            rows.append({'net': net, 'path': what, 'found': False})
            print('%-13s %-52s no route on tracks (from %d points to %d)' % (net, what, len(src), len(dst)))
            continue
        tr = [(wd, ln, lay) for wd, ln, lay in route if lay not in ('via', 'pad')]
        nvia = sum(1 for _, _, lay in route if lay == 'via') // 2
        by_layer = defaultdict(float)
        ohm = 0.0
        for wd, ln, lay in tr:
            name = b.GetLayerName(lay)
            by_layer[name] += ln
            ohm += RHO * ln * 1e-3 / (wd * 1e-3 * (T_OUTER if name in ('F.Cu', 'B.Cu') else T_INNER))
        ohm += nvia * RHO * 1.2e-3 / (math.pi * 0.2e-3 * T_BARREL)
        narrow = min((wd for wd, ln, lay in tr), default=0.0)
        thin_len = sum(ln for wd, ln, lay in tr if wd <= narrow + 1e-6)
        row = {'net': net, 'path': what, 'found': True, 'narrowest_mm': round(narrow, 3), 'length_at_narrowest_mm': round(thin_len, 1),
               'length_mm': round(sum(ln for _, ln, _ in tr), 1), 'by_layer_mm': {k: round(v, 1) for k, v in sorted(by_layer.items())},
               'vias': nvia, 'milliohm': round(ohm * 1e3, 1)}
        rows.append(row)
        print('%-13s %-52s narrowest %.2f mm (%.1f mm of it), %5.1f mm in all %s, %d vias, %5.1f mohm'
              % (net, what, narrow, thin_len, row['length_mm'], row['by_layer_mm'], nvia, row['milliohm']))
    if a.json:
        a.json.write_text(json.dumps({'board': a.board.name, 'copper_um': {'outer': 35, 'inner': 17.5, 'via_barrel': 20}, 'paths': rows}, indent=1) + '\n',
                          encoding='utf-8')
    sys.stdout.flush()


if __name__ == '__main__':
    main()
