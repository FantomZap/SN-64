"""Write what the v2 board connects to what, as the board file itself has it.

  "C:/Program Files/KiCad/10.0/bin/python.exe" hardware/sn64-v2/tools/export_board_nets.py [--out <file>]

Reads hardware/sn64-v2/sn64-v2.kicad_pcb with KiCad's own library (pcbnew) and writes JSON:
  components: {reference: {value, footprint, layer, pads: {pad number: net name}}}
  nets:       {net name: [[reference, pad number], ...]}
This is the list the board is made from: every pad carries the name of the net its copper belongs
to, and KiCad's design-rule check (validation/pcb-drc.json) says whether the copper really joins
the pads of a net and no others. The schematic's own list (validation/sn64-v2.xml) is compared
with it by tools/verify_board_wiring.py.
"""
import argparse
import json
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--board', type=Path, default=HERE.parent / 'sn64-v2.kicad_pcb')
    ap.add_argument('--out', type=Path, default=ROOT / 'build/board-sim/board-nets.json')
    args = ap.parse_args()
    board = pcbnew.LoadBoard(str(args.board))
    comps, nets = {}, {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pads = {}
        for pad in fp.Pads():
            num = pad.GetNumber()
            net = pad.GetNetname()
            if not num:
                continue
            if num in pads and pads[num] != net:
                raise SystemExit('%s pad %s is on two nets: %s and %s' % (ref, num, pads[num], net))
            pads[num] = net
            nets.setdefault(net, []).append([ref, num])
        comps[ref] = {'value': fp.GetValue(), 'footprint': str(fp.GetFPID().GetUniStringLibItemName()),
                      'layer': 'F' if fp.GetLayer() == pcbnew.F_Cu else 'B', 'pads': pads}
    for net in nets:
        nets[net] = sorted(set(map(tuple, nets[net])))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'board': args.board.name, 'components': comps, 'nets': nets}, indent=1, sort_keys=True),
                        encoding='utf-8', newline='\n')
    print('%d components, %d nets, %d pads -> %s' % (len(comps), len(nets), sum(len(c['pads']) for c in comps.values()), args.out.name))


if __name__ == '__main__':
    main()
