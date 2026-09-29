"""Render the generated STL reference meshes using FreeCAD's bundled Python."""
from pathlib import Path
import FreeCAD
import Mesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

root = Path(__file__).resolve().parent / 'fit-references'
fig = plt.figure(figsize=(14, 6), facecolor='#f4f6f8')
for i, (name, title) in enumerate([
    ('snes-hole-pattern-coupon', 'SNES hole-pattern coupon\n62 holes | nominal 2.5 mm pitch'),
    ('n64-sc64-board-reference', 'SummerCart64 board reference\n1.2 mm source thickness | not SN64 PCB')], 1):
    mesh = Mesh.Mesh(str(root / (name + '.stl')))
    b = mesh.BoundBox
    ax = fig.add_subplot(1, 2, i)
    # Draw only coplanar top facets: the STL's actual holes remain white.
    triangles = [[(v[0], v[1]) for v in f.Points] for f in mesh.Facets
                 if all(abs(v[2] - b.ZMax) < 1e-5 for v in f.Points)]
    coll = PolyCollection(triangles, facecolors='#41948f', edgecolors='#41948f',
                          linewidths=0, antialiased=False)
    ax.add_collection(coll)
    ax.set_xlim(b.XMin - 2, b.XMax + 2)
    ax.set_ylim(b.YMin - 2, b.YMax + 2)
    ax.set_aspect('equal')
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_title(title, fontsize=13, pad=8)
fig.suptitle('Nominal CAD references, plan view - physical fit not yet tested', fontsize=16)
fig.text(0.5, 0.03, 'Separate datums; no assembled adapter, approved socket body, shell or manufacturing release.',
         ha='center', fontsize=10)
fig.tight_layout(rect=[0.015, 0.065, 0.985, 0.9])
fig.savefig(root / 'preview.png', dpi=140)
print(root / 'preview.png')
