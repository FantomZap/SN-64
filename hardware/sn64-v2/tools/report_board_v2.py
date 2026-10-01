"""Summarise a KiCad DRC report of the v2 board into validation/pcb-open-connections.json (KiCad's python).

  python report_board_v2.py BOARD.kicad_pcb DRC.json OUT.json [--note TEXT]

Counts tracks, vias and track length on the board, signal nets with every pad connected, DRC
violations by type and severity, and lists each unconnected item for hand routing.
"""
import argparse
import datetime
import json
from collections import Counter, defaultdict
from pathlib import Path

import pcbnew

PLANES = {'GND', 'FPGA_3V3', 'FPGA_1V1'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('board')
    ap.add_argument('drc')
    ap.add_argument('out')
    ap.add_argument('--note', default='')
    a = ap.parse_args()
    b = pcbnew.LoadBoard(a.board)
    tracks = list(b.GetTracks())
    vias = [t for t in tracks if t.GetClass() == 'PCB_VIA']
    length = sum(t.GetLength() for t in tracks if t.GetClass() != 'PCB_VIA') / 1e6
    d = json.loads(Path(a.drc).read_text(encoding='utf-8'))
    unconnected = d.get('unconnected_items', [])
    open_nets = set()
    items = []
    for u in unconnected:
        names = [i.get('description', '') for i in u.get('items', [])]
        nets = sorted({n.split('[')[1].split(']')[0] for n in names if '[' in n})
        open_nets.update(nets)
        pos = [i.get('pos', {}) for i in u.get('items', [])]
        items.append({'nets': nets, 'items': names,
                      'from': pos[0] if pos else None, 'to': pos[1] if len(pos) > 1 else None})
    # signal nets that own two or more pads
    pads = defaultdict(int)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() and not p.GetNetname().startswith('unconnected-'):
                pads[p.GetNetname()] += 1
    signal = {n for n, c in pads.items() if c >= 2 and n not in PLANES}
    sev = Counter((v['severity'], v['type']) for v in d.get('violations', []))
    rep = {
        'date': datetime.date.today().isoformat(),
        'board': a.board.replace('\\', '/'),
        'note': a.note,
        'tracks': len(tracks) - len(vias),
        'vias': len(vias),
        'track_length_mm': round(length),
        'signal_nets_fully_connected': f'{len(signal - open_nets)} of {len(signal)}',
        'drc_errors': {t: c for (s, t), c in sorted(sev.items()) if s == 'error'},
        'drc_warnings': {t: c for (s, t), c in sorted(sev.items()) if s == 'warning'},
        'unconnected_items': len(unconnected),
        'open_items_for_hand_routing': items,
    }
    Path(a.out).write_text(json.dumps(rep, indent=1), encoding='utf-8')
    print(json.dumps({k: rep[k] for k in ('tracks', 'vias', 'track_length_mm', 'signal_nets_fully_connected',
                                           'drc_errors', 'unconnected_items')}))
    for it in items:
        print('  open:', it['nets'], it['from'], '->', it['to'])


if __name__ == '__main__':
    main()
