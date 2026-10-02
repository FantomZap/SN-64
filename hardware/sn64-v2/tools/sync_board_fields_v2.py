"""Bring the part records of the v2 board in line with the schematic (KiCad's python).

  python sync_board_fields_v2.py [--board sn64-v2.kicad_pcb] [--netlist validation/sn64-v2.xml] [--out OUT.kicad_pcb]

The board was placed by a script, so its footprints never went through KiCad's "update PCB from
schematic": they carried no library name, no part numbers and no link to their symbols, and KiCad's
comparison of board and schematic (`kicad-cli pcb drc --schematic-parity`) listed 218 differences,
none of them a wiring difference. This tool does what that update does for everything except copper:

  * footprint name with its library, value, data sheet and description as the symbol has them;
  * every other field of the symbol (MPN, Manufacturer, LCSC, Source, Note ...) as a hidden field on
    the part's fabrication layer, so that the placement and parts lists can be made from the board;
  * the link to the symbol (sheet and symbol identifiers);
  * "not in the parts list" as the symbol says; the mounting holes, which have no symbol, are marked
    as belonging to the board only; the edge fingers and the hand-fitted socket stay out of the
    placement file.

Pads, nets, tracks and zones are not touched: the tool refuses to save if any pad's net differs from
the netlist, and it prints how many pads it compared.
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

V2 = Path(__file__).resolve().parents[1]
STANDARD = ('Reference', 'Value', 'Footprint', 'Datasheet', 'Description')
NOT_PLACED = ('J1', 'J2')          # copper fingers; the socket the owner solders by hand


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--board', type=Path, default=V2 / 'sn64-v2.kicad_pcb')
    ap.add_argument('--netlist', type=Path, default=V2 / 'validation' / 'sn64-v2.xml')
    ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    root = ET.parse(a.netlist).getroot()
    b = pcbnew.LoadBoard(str(a.board))
    fps = {f.GetReference(): f for f in b.GetFootprints()}

    # the wiring first: this tool must never be the thing that hides a difference
    want = {}
    for net in root.find('nets'):
        for node in net.findall('node'):
            want[(node.get('ref'), node.get('pin'))] = net.get('name')
    compared = 0
    for ref, f in fps.items():
        for p in f.Pads():
            name = p.GetNetname()
            exp = want.get((ref, p.GetNumber()))
            if exp is None:
                if name and not name.startswith('unconnected-'):
                    sys.exit('%s pad %s is on %s but the schematic has no such pin' % (ref, p.GetNumber(), name))
                continue
            compared += 1
            exp = exp.lstrip('/')
            if name != exp and not (exp.startswith('unconnected-') and name in ('', exp)):
                sys.exit('%s pad %s is on %r, the schematic says %r' % (ref, p.GetNumber(), name, exp))

    comps = {c.get('ref'): c for c in root.find('components')}
    missing = sorted(set(comps) - set(fps))
    if missing:
        sys.exit('in the schematic but not on the board: ' + ' '.join(missing))
    changed = {'name': 0, 'value': 0, 'field': 0, 'link': 0, 'flag': 0}
    stray = []
    for ref, c in comps.items():
        f = fps[ref]
        fab = pcbnew.F_Fab if f.GetLayer() == pcbnew.F_Cu else pcbnew.B_Fab
        name = c.findtext('footprint') or ''
        if f.GetFPIDAsString() != name:
            f.SetFPIDAsString(name)
            changed['name'] += 1
        value = c.findtext('value') or ''
        if f.GetValue() != value:
            f.SetValue(value)
            changed['value'] += 1
        fields = {x.get('name'): (x.text or '') for x in c.findall('fields/field')}
        fields.pop('Footprint', None)
        for key, text in fields.items():
            if f.HasField(key) and f.GetFieldText(key) == text:
                continue
            if key in STANDARD:
                f.GetField(key).SetText(text)
            else:
                f.SetField(key, text)
                fld = f.GetField(key)
                fld.SetVisible(False)
                fld.SetLayer(fab)
                fld.SetPosition(f.GetPosition())
            changed['field'] += 1
        for fld in f.GetFields():
            if fld.GetName() not in STANDARD and fld.GetName() not in fields and fld.GetName() != 'KiLib_Generator':
                stray.append((f, fld))
        props = {x.get('name') for x in c.findall('property')}
        sheet = c.find('sheetpath')
        path = sheet.get('tstamps') + (c.findtext('tstamps') or '').split()[0]
        if f.GetPath().AsString() != path or f.GetSheetname() != sheet.get('names') or f.GetSheetfile() != c_sheetfile(c):
            f.SetPath(pcbnew.KIID_PATH(path))
            f.SetSheetname(sheet.get('names'))
            f.SetSheetfile(c_sheetfile(c))
            changed['link'] += 1
        for now, to, setter in ((f.IsExcludedFromBOM(), 'exclude_from_bom' in props, f.SetExcludedFromBOM),
                                (f.IsDNP(), 'dnp' in props, f.SetDNP),
                                (f.IsExcludedFromPosFiles(), ref in NOT_PLACED or 'exclude_from_bom' in props, f.SetExcludedFromPosFiles),
                                (f.IsBoardOnly(), False, f.SetBoardOnly)):
            if now != to:
                setter(to)
                changed['flag'] += 1
    only_board = sorted(set(fps) - set(comps))
    for ref in only_board:
        f = fps[ref]
        if not ref.startswith('H'):
            sys.exit('on the board but not in the schematic: ' + ref)
        for now, setter in ((f.IsBoardOnly(), f.SetBoardOnly), (f.IsExcludedFromBOM(), f.SetExcludedFromBOM),
                            (f.IsExcludedFromPosFiles(), f.SetExcludedFromPosFiles)):
            if not now:
                setter(True)
                changed['flag'] += 1
    for f, fld in stray:                       # last: KiCad 10's python breaks every lookup after a Remove()
        f.Remove(fld)
    out = a.out or a.board
    pcbnew.SaveBoard(str(out), b)
    print('%d parts, %d pads compared with the netlist; names %d, values %d, fields %d, links %d, flags %d changed; '
          '%d leftover fields removed; board-only: %s; saved %s'
          % (len(comps), compared, changed['name'], changed['value'], changed['field'], changed['link'], changed['flag'],
             len(stray), ' '.join(only_board), Path(out).name))
    sys.stdout.flush()


def c_sheetfile(c):
    return next((x.get('value') for x in c.findall('property') if x.get('name') == 'Sheetfile'), '')


if __name__ == '__main__':
    main()
