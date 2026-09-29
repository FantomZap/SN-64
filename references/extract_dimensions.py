"""Run from any directory with KiCad's bundled Python. Reads upstream CAD only."""
import csv
import hashlib
import json
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'references/measurements'
OUT.mkdir(exist_ok=True)
manifest = json.loads((ROOT / 'references/source-manifest.json').read_text(encoding='utf-8'))
for record in manifest['files']:
    path = ROOT / record['local_path']
    if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError(f'Upstream file changed: {path}')

def mm(value):
    return round(pcbnew.ToMM(value), 6)

def rows(footprint):
    result = []
    for pad in footprint.Pads():
        at, size, drill = pad.GetPosition(), pad.GetSize(), pad.GetDrillSize()
        result.append(dict(pin=pad.GetNumber(), x_mm=mm(at.x), y_mm=mm(at.y),
                           width_mm=mm(size.x), height_mm=mm(size.y),
                           drill_x_mm=mm(drill.x), drill_y_mm=mm(drill.y),
                           layers=','.join(pcbnew.BOARD.GetStandardLayerName(layer) for layer in pad.GetLayerSet().Seq()),
                           net=pad.GetNetname()))
    return sorted(result, key=lambda row: int(row['pin']))

def write_csv(name, values):
    with (OUT / name).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=values[0].keys())
        writer.writeheader(); writer.writerows(values)

board = pcbnew.LoadBoard(str(ROOT / 'references/downloads/summercart64/hw/pcb/sc64v2.kicad_pcb'))
edge = next(f for f in board.GetFootprints() if f.GetReference() == 'J_N1')
n64 = rows(edge)
assert len(n64) == 50 and {r['pin'] for r in n64} == {str(n) for n in range(1, 51)}
assert all(n64[i]['x_mm'] - n64[i+1]['x_mm'] == 2.5 for i in range(24))
write_csv('n64-reference-pads.csv', n64)
slot = pcbnew.FootprintLoad(str(ROOT / 'references/downloads/sanni/hardware/footprints/!OSCR.pretty'), 'SNES Slot')
snes = rows(slot)
assert len(snes) == 62 and {r['pin'] for r in snes} == {str(n) for n in range(1, 63)}
write_csv('snes-socket-reference-pads.csv', snes)
holes=[]
for footprint in board.GetFootprints():
    if footprint.GetValue() == 'MountingHole_2.5mm':
        pad=next(iter(footprint.Pads()))
        holes.append(dict(x_mm=mm(pad.GetPosition().x),y_mm=mm(pad.GetPosition().y),diameter_mm=mm(pad.GetDrillSize().x)))
holes.sort(key=lambda row: row['x_mm'])
assert len(holes)==2 and holes[1]['x_mm']-holes[0]['x_mm']==95
report=dict(source_commit='a1e7996d2cbece686820a5c785029c68514f17b0',
            pcb_thickness_setting_mm=mm(board.GetDesignSettings().GetBoardThickness()),
            n64_footprint_origin_mm=[mm(edge.GetPosition().x),mm(edge.GetPosition().y)],
            mounting_holes=holes)
(OUT/'pcb-inspection.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('Verified source hashes; extracted 50 N64 pads, 62 SNES socket pads, and 2 shell mounting holes.')
