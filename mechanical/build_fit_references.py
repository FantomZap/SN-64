"""Create editable FreeCAD reference documents and neutral exports.

Run using FreeCAD's bundled Python. These are nominal fit references, not an SN64
assembly, an approved socket body, a board release or a finished enclosure.
"""
import hashlib
import json
import math
from pathlib import Path

import FreeCAD as App
import Part
import Sketcher
import Mesh
import MeshPart

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'fit-references'
OUT.mkdir(exist_ok=True)
data = json.loads((ROOT / 'source-datums.json').read_text(encoding='utf-8'))
reports = []

def metadata(obj, source, limitation):
    obj.addProperty('App::PropertyString', 'Source', 'Evidence').Source = source
    obj.addProperty('App::PropertyString', 'Status', 'Evidence').Status = limitation

def parameters(doc, rows):
    p = doc.addObject('Spreadsheet::Sheet', 'Parameters')
    for index, (name, value, status) in enumerate(rows, 1):
        p.set(f'A{index}', name)
        p.set(f'B{index}', f'{value} mm')
        p.setAlias(f'B{index}', name)
        p.set(f'C{index}', status)
    doc.recompute()
    return p

def cylinder(doc, name, x, y, diameter_expr, height_expr):
    c = doc.addObject('Part::Cylinder', name)
    c.Placement.Base = App.Vector(x, y, -0.5)
    c.setExpression('Radius', f'({diameter_expr}) / 2')
    c.setExpression('Height', height_expr)
    return c

def export(doc, final, name, expected_volume=None):
    doc.recompute()
    assert final.Shape.isValid() and len(final.Shape.Solids) == 1, name
    if expected_volume is not None:
        assert math.isclose(final.Shape.Volume, expected_volume, abs_tol=1e-5), name
    # Native feature visibility is persisted even when built without a GUI.
    for obj in doc.Objects:
        if hasattr(obj, 'Visibility'):
            obj.Visibility = obj == final
    doc.recompute()
    path = OUT / name
    doc.saveAs(str(path.with_suffix('.FCStd')))
    final.Shape.exportStep(str(path.with_suffix('.step')))
    mesh = MeshPart.meshFromShape(Shape=final.Shape, LinearDeflection=0.02,
                                 AngularDeflection=0.2, Relative=False)
    mesh.write(str(path.with_suffix('.stl')))
    assert mesh.isSolid(), name
    reimport = Part.Shape()
    reimport.read(str(path.with_suffix('.step')))
    assert reimport.isValid() and len(reimport.Solids) == 1
    assert math.isclose(reimport.Volume, final.Shape.Volume, abs_tol=1e-4)
    bb = final.Shape.BoundBox
    reports.append({'model': name, 'valid_solid': True, 'step_roundtrip_valid': True,
                    'stl_closed': True, 'volume_mm3': final.Shape.Volume,
                    'bounds_mm': [bb.XLength, bb.YLength, bb.ZLength],
                    'freecad_objects': len(doc.Objects),
                    'files': {ext: hashlib.sha256(path.with_suffix(ext).read_bytes()).hexdigest()
                              for ext in ['.FCStd', '.step', '.stl']}})
    App.closeDocument(doc.Name)

# Plate dimensions are coupon design choices. Only the hole pattern is sourced.
doc = App.newDocument('SNES_Socket_Hole_Coupon')
parameters(doc, [('PlateLength', 95, 'coupon design choice, not socket length'),
                 ('PlateWidth', 15, 'coupon design choice, not socket width'),
                 ('PlateThickness', 1.6, 'coupon choice, not final PCB thickness'),
                 ('HoleDiameter', 0.762, 'nominal Sanni finished-hole reference')])
base = doc.addObject('Part::Box', 'CouponBlank')
for prop, expr in [('Length', 'PlateLength'), ('Width', 'PlateWidth'), ('Height', 'PlateThickness')]:
    base.setExpression(prop, f'Parameters.{expr}')
base.setExpression('Placement.Base.x', '-Parameters.PlateLength / 2')
base.setExpression('Placement.Base.y', '-Parameters.PlateWidth / 2')
holes = []
for p in data['snes']['pads']:
    c = cylinder(doc, f'HolePin{p["pin"]}', p['x_mm'], p['y_mm'],
                 'Parameters.HoleDiameter', 'Parameters.PlateThickness + 1 mm')
    metadata(c, 'Sanni pin ' + str(p['pin']), 'Nominal source footprint centre; no fabrication tolerance specified.')
    holes.append(c)
cutters = doc.addObject('Part::Compound', 'HoleTools')
cutters.Links = holes
final = doc.addObject('Part::Cut', 'Coupon')
final.Base = base
final.Tool = cutters
metadata(final, data['source_files'][0]['url'], '62-hole placement coupon only; no socket body/mounts or measured fit.')
expected = (95 * 15 - 62 * math.pi * (0.762 / 2)**2) * 1.6
export(doc, final, 'snes-hole-pattern-coupon', expected)

# Full source board perimeter, including the edge footprint's six segments.
doc = App.newDocument('N64_SC64_Board_Reference')
parameters(doc, [('BoardThickness', data['n64']['thickness_mm'], 'source complete PCB thickness setting'),
                 ('MountHoleDiameter', 2.5, 'source mounting holes')])
outline = doc.addObject('Sketcher::SketchObject', 'SourceOutline')
for edge in data['n64']['outline_segments']:
    a, b = edge['start'], edge['end']
    i = outline.addGeometry(Part.LineSegment(App.Vector(*a, 0), App.Vector(*b, 0)), False)
    outline.addConstraint(Sketcher.Constraint('Block', i))
board = doc.addObject('Part::Extrusion', 'BoardBlank')
board.Base = outline
board.DirMode = 'Normal'
board.setExpression('LengthFwd', 'Parameters.BoardThickness')
board.Solid = True
holes = []
for index, h in enumerate(data['n64']['mounting_holes'], 1):
    holes.append(cylinder(doc, f'MountHole{index}', *h['xy_mm'],
                          'Parameters.MountHoleDiameter', 'Parameters.BoardThickness + 1 mm'))
tools = doc.addObject('Part::Compound', 'MountHoleTools')
tools.Links = holes
final = doc.addObject('Part::Cut', 'BoardReference')
final.Base = board
final.Tool = tools
metadata(final, data['source_files'][1]['url'],
         'SummerCart64 source board reference, not SN64 placement/outline approval. No copper or mating bevel.')
export(doc, final, 'n64-sc64-board-reference')

(OUT / 'validation.json').write_text(json.dumps({'freecad': App.Version(), 'models': reports,
    'limitations': ['Numerical/solid checks only; no printed-part, socket, cartridge or host fit test.',
                    'Independent references use separate datums; they are not an assembled adapter.']}, indent=2) + '\n', encoding='utf-8')
print(json.dumps(reports, indent=2))
