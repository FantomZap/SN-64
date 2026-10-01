"""Put the attribution and source location on the board's silkscreen (KiCad's python).

NOTICE asks that products made from the hardware design show the source location
(CERN-OHL-S-2.0 section 4). This writes one line on F.SilkS in the clear strip below the SNES
socket pads; running it again updates the line in place instead of adding a second one.

  python add_credit_silk.py [board.kicad_pcb]
"""
import sys
from pathlib import Path

import pcbnew

PCB = Path(__file__).resolve().parents[1] / 'sn64-v2.kicad_pcb'
TEXT = 'SN64 by FantomZap   github.com/FantomZap/SN-64   CERN-OHL-S-2.0'
AT = (0.0, -61.0)          # mm: centred, 9 mm below the top edge, clear of J2's reference
SIZE, THICK = 1.0, 0.15
mm = pcbnew.FromMM


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else PCB
    b = pcbnew.LoadBoard(str(path))
    t = None
    for d in b.GetDrawings():
        if d.GetClass() == 'PCB_TEXT' and d.GetText().startswith('SN64 by FantomZap'):
            t = d
            break
    new = t is None
    if new:
        t = pcbnew.PCB_TEXT(b)
        b.Add(t)
    t.SetText(TEXT)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetPosition(pcbnew.VECTOR2I(mm(AT[0]), mm(AT[1])))
    t.SetTextSize(pcbnew.VECTOR2I(mm(SIZE), mm(SIZE)))
    t.SetTextThickness(mm(THICK))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    bb = t.GetBoundingBox()
    pcbnew.SaveBoard(str(path), b)
    print(f"{'added' if new else 'updated'} silkscreen credit: x {bb.GetLeft() / 1e6:.1f}..{bb.GetRight() / 1e6:.1f} "
          f"y {bb.GetTop() / 1e6:.1f}..{bb.GetBottom() / 1e6:.1f}")


if __name__ == '__main__':
    main()
