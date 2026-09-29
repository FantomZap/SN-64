"""Inspect local upstream shells; keep their native reference copy in downloads/."""
import argparse
import hashlib
import json
from pathlib import Path

import FreeCAD as App
import Mesh
import Part

parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
folder = root / 'downloads/SNESDRONE-e54ac7577a127f62072267e417652432529e9fe1'
doc = App.newDocument('Upstream_Shell_References')
result = []
paths = [folder / 'sfc_cart.stl', folder / 'SnesDrone_Shell_Bottom_V0.1.1.stl',
         folder / 'SnesDrone_Shell_Top_V0.1.1.stl',
         args.source_root / 'references/downloads/summercart64/hw/shell/injection mold/sc64_shell.stp']
for i, path in enumerate(paths):
    if path.suffix == '.stl':
        mesh = Mesh.Mesh(str(path))
        obj = doc.addObject('Mesh::Feature', 'Reference' + str(i))
        obj.Mesh = mesh
        bb = mesh.BoundBox
        details = {'facets': mesh.CountFacets, 'closed_mesh': mesh.isSolid(),
                   'units_note': 'STL has no unit declaration; mm assumed from source application, not verified on a cartridge.'}
    else:
        shape = Part.Shape()
        shape.read(str(path))
        obj = doc.addObject('Part::Feature', 'Reference' + str(i))
        obj.Shape = shape
        bb = shape.BoundBox
        details = {'valid': shape.isValid(), 'solids': len(shape.Solids), 'units_note': 'STEP mm'}
    obj.Label = path.name
    obj.addProperty('App::PropertyString', 'Limitation', 'Evidence').Limitation = 'Independent upstream origin. Not assembled to SN64 or transformed to a common mating datum.'
    result.append({'filename': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                   'bounds': {'min': [bb.XMin, bb.YMin, bb.ZMin],
                              'max': [bb.XMax, bb.YMax, bb.ZMax],
                              'size': [bb.XLength, bb.YLength, bb.ZLength]}, **details})
doc.recompute()
doc.saveAs(str(root / 'downloads/Upstream-shell-references.FCStd'))
(root / 'shell-inspection.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
