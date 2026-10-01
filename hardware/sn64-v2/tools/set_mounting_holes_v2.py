"""Give board holes H1, H2, H5 and H6 the 4.0 mm size the shell's through-hole posts need (KiCad's python).

Owner, 2026-10-01: the board must not be squeezed between the shell's screw posts. The label-side
post has a shelf for the board and a hollow 3.8 mm spigot that passes through the board, the way a
Nintendo cartridge's post passes through its board, and the back post lands on the spigot. A hollow
spigot around an M2 screw does not fit a 2.5 mm hole, so the four holes that take screws become
4.0 mm (KiCad's MountingHole_4mm). H3 and H4 stay 2.5 mm: they take the two registration pins that
stop the board going in back to front.

Each footprint is replaced in place and keeps its reference and the position of its label. Refill
the zones afterwards:

  python set_mounting_holes_v2.py [board.kicad_pcb]
  python finish_route_v2.py --no-import --board board.kicad_pcb
"""
import sys
from pathlib import Path

import pcbnew

PCB = Path(__file__).resolve().parents[1] / 'sn64-v2.kicad_pcb'
LIB = Path(sys.executable).resolve().parents[1] / 'share' / 'kicad' / 'footprints' / 'MountingHole.pretty'
REFS = ('H1', 'H2', 'H5', 'H6')
NEW = 'MountingHole_4mm'


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else PCB
    b = pcbnew.LoadBoard(str(path))
    # every lookup first: KiCad 10's python loses its footing after board.Remove()
    jobs = []
    for ref in REFS:
        old = b.FindFootprintByReference(ref)
        if old is None:
            raise SystemExit(f'{ref} not found')
        if str(old.GetFPID().GetLibItemName()) == NEW:
            continue
        jobs.append((ref, old, old.GetPosition(), old.Reference().GetPosition(), old.Reference().IsVisible()))
    for ref, old, pos, ref_pos, ref_visible in jobs:
        fp = pcbnew.FootprintLoad(str(LIB), NEW)
        if fp is None:
            raise SystemExit(f'{NEW} not found in {LIB}')
        fp.SetFPID(pcbnew.LIB_ID('MountingHole', NEW))
        fp.SetReference(ref)
        fp.SetValue(NEW)
        b.Add(fp)
        fp.SetPosition(pos)
        fp.Reference().SetPosition(ref_pos)
        fp.Reference().SetVisible(ref_visible)
    for _, old, *_ in jobs:
        b.Remove(old)
    pcbnew.SaveBoard(str(path), b)
    print(f'{len(jobs)} mounting holes set to {NEW}: {", ".join(j[0] for j in jobs) or "none (already done)"}')
    sys.stdout.flush()


if __name__ == '__main__':
    main()
