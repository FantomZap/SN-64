"""Read pinned source CAD with KiCad Python; never modify upstream files."""
import argparse
import hashlib
import json
from pathlib import Path

import pcbnew

parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path, required=True)
args = parser.parse_args()
out = Path(__file__).resolve().parent
src = args.source_root
sanni = src / 'references/downloads/sanni/hardware/footprints/!OSCR.pretty/SNES Slot.kicad_mod'
sc64 = src / 'references/downloads/summercart64/hw/pcb/sc64v2.kicad_pcb'
# Trust this checkout's pinned manifest, not metadata supplied by --source-root.
# Validate before CAD parsing or publishing any derived coordinates.
manifest = json.loads((out.parent / 'references/source-manifest.json').read_text(encoding='utf-8'))
records = {record['local_path']: record for record in manifest['files']}
for path, revision in [(sanni, '060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d'),
                       (sc64, 'a1e7996d2cbece686820a5c785029c68514f17b0')]:
    record = records[path.relative_to(src).as_posix()]
    if record['commit'] != revision or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError(f'Upstream file changed or revision mismatch: {path}')
slot = pcbnew.FootprintLoad(str(sanni.parent), sanni.stem)
board = pcbnew.LoadBoard(str(sc64))

def mm(value):
    return round(pcbnew.ToMM(value), 6)

def xy(point):
    return [mm(point.x) - 150.0, 135.5 - mm(point.y)]

pads = []
for p in slot.Pads():
    at = p.GetPosition()
    pads.append({'pin': int(p.GetNumber()),
                 'x_mm': round(mm(at.y) - 42.5, 6),
                 'y_mm': round(mm(at.x) - 2.5, 6),
                 'hole_mm': mm(p.GetDrillSize().x)})
pads.sort(key=lambda p: p['pin'])
assert len(pads) == 62
assert {p['hole_mm'] for p in pads} == {0.762}
edges = []
drawings = list(board.GetDrawings())
for fp in board.GetFootprints():
    drawings.extend(fp.GraphicalItems())
for item in drawings:
    if item.GetLayer() == pcbnew.Edge_Cuts:
        assert item.GetShape() == pcbnew.SHAPE_T_SEGMENT, 'Unhandled source outline geometry'
        edges.append({'start': xy(item.GetStart()), 'end': xy(item.GetEnd())})
holes = []
for fp in board.GetFootprints():
    if fp.GetValue() == 'MountingHole_2.5mm':
        p = next(iter(fp.Pads()))
        holes.append({'xy_mm': xy(p.GetPosition()), 'diameter_mm': mm(p.GetDrillSize().x)})
assert len(edges) == 35 and len(holes) == 2
data = {
    'units': 'mm',
    'source_files': [
        {'path': str(sanni.relative_to(src)).replace('\\', '/'),
         'commit': '060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d',
         'url': 'https://github.com/sanni/cartreader/blob/060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d/hardware/footprints/%21OSCR.pretty/SNES%20Slot.kicad_mod',
         'sha256': hashlib.sha256(sanni.read_bytes()).hexdigest()},
        {'path': str(sc64.relative_to(src)).replace('\\', '/'),
         'commit': 'a1e7996d2cbece686820a5c785029c68514f17b0',
         'url': 'https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_pcb',
         'sha256': hashlib.sha256(sc64.read_bytes()).hexdigest()}
    ],
    'snes': {'datum': 'X=source footprint Y-42.5; Y=source footprint X-2.5; Z=bottom of coupon. No mating/body datum implied.', 'pads': pads},
    'n64': {'datum': 'X=source PCB X-150; Y=135.5-source PCB Y; Z=bottom face. Origin is insertion-tip midpoint.',
            'thickness_mm': mm(board.GetDesignSettings().GetBoardThickness()),
            'outline_segments': edges, 'mounting_holes': holes}
}
(out / 'source-datums.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
print('Extracted 62 SNES holes, 35 N64 outline segments and 2 mounting holes.')
