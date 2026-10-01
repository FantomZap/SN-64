"""Write the straddle footprint for the SNES socket on the board's top edge (plain Python).

SN64 v2 is one vertical board with the SNES cartridge upright on top (owner, 2026-09-30). The
socket is the 62-contact console-replacement part with ears. It sits above the board's top edge
and its tails land on pads on both faces; its ears screw into the shell, not the board.

Geometry (sourced): OpenSFC CartSlot.kicad_mod (SHVC-CPU-01 Rev A, commit 6574450b, SHA-256
1f9b60dd...): 31 contacts per row, 2.5 mm pitch, 7.5 mm gaps between contacts 4-5 and 27-28,
85.0 mm first to last, pin 32 opposite pin 1.

Orientation (sourced, checked 2026-09-30):
  - N64 edge pin 1 is on the front row of the console slot (n64brew "Game Pak": pin 1 lower left
    seen from above with the controller ports toward you). On this board J1 pins 1-25 are on B.Cu,
    so B.Cu faces the front of the console.
  - SNES pins 1-31 face the front of the console and the cartridge label (SNESdev wiki "Cartridge
    connector"); on the OpenSFC console board pin 1 is the left end of the front row seen from the
    front (P1 pad 1 at x 64.35, pad 31 at x 149.35, controller ribbon toward +y).
  - Seen from the front (the B.Cu face), board +x is on the viewer's left, so pin 1 is at +42.5.
  Result: pins 1-31 on B.Cu from x +42.5 to -42.5, pins 32-62 on F.Cu at the same x. A mirrored
  footprint would put the cartridge's +5 V contacts (27, 58) on the ground pads (5, 36).

Pads are 1.5 x 3.5 mm, 0.5 mm from the edge (board edge rule 0.3 mm). How the tails reach them is
settled against a measured sample (owner: a small board redesign if needed). Footprint origin =
centre of the board's top edge; the body outline above the edge is drawn on F.Fab only.

  python make_socket_footprint.py [out.kicad_mod]
"""
import sys
import uuid
from pathlib import Path

NAME = 'SNES_Slot_Console_Straddle'
NS = uuid.UUID('0b7d3c61-5a2e-4c8f-9e14-6f2a8d9c1b33')
OUT = Path(__file__).resolve().parents[1] / 'libraries' / 'SN64_V2.pretty' / f'{NAME}.kicad_mod'

PAD_W, PAD_L, PAD_GAP = 1.5, 3.5, 0.5          # pad width (x), length (y), distance from the edge
X = [42.5, 40.0, 37.5, 35.0] + [27.5 - 2.5 * i for i in range(23)] + [-35.0, -37.5, -40.0, -42.5]
assert len(X) == 31 and abs(X[4] - X[3]) == 7.5 and abs(X[26] - X[27]) == 7.5 and X[0] - X[30] == 85.0


def u(s):
    return str(uuid.uuid5(NS, s))


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    yc = PAD_GAP + PAD_L / 2
    L = [f'(footprint "{NAME}" (version 20241229) (generator "sn64_v2_socket") (generator_version "10.0") (layer "F.Cu")',
         '(descr "SNES/SFC 62-contact cartridge socket, console-replacement family with ears, straddling the board top edge: '
         'pins 1-31 on B.Cu (front of the console), 32-62 on F.Cu, 2.5 mm pitch, 7.5 mm gaps, 85.0 mm first to last. '
         'Pin geometry from OpenSFC CartSlot (commit 6574450b). Body above the edge; ears screw to the shell. Unverified on a sample.")',
         '(tags "SNES SFC cartridge socket 62 straddle edge")',
         '(attr smd exclude_from_pos_files)',
         f'(property "Reference" "REF**" (at 0 {yc + 4.6:.2f} 0) (layer "F.SilkS") (uuid "{u("ref")}") (effects (font (size 1 1) (thickness 0.15))))',
         f'(property "Value" "{NAME}" (at 0 -8 0) (layer "F.Fab") (uuid "{u("value")}") (effects (font (size 1 1) (thickness 0.15))))',
         f'(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{u("ds")}") (effects (font (size 1.27 1.27))))',
         f'(property "Description" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{u("descr")}") (effects (font (size 1.27 1.27))))']
    # body above the edge (documentation only): base 99 x 6 with the ear holes, nose 94.9 x 10.55 (SNES Jr connector model)
    for name, (x0, y0, x1, y1) in (('base', (-49.5, -6.5, 49.5, -0.5)), ('nose', (-47.45, -17.05, 47.45, -6.5))):
        L.append(f'(fp_rect (start {x0} {y0}) (end {x1} {y1}) (stroke (width 0.1) (type default)) (fill no) (layer "F.Fab") (uuid "{u(name)}"))')
    for sx in (-1, 1):
        L.append(f'(fp_circle (center {sx * 47.5} -3.5) (end {sx * 47.5 + 1.6} -3.5) (stroke (width 0.1) (type default)) (fill no) (layer "F.Fab") (uuid "{u(f"ear{sx}")}"))')
    L.append(f'(fp_text user "board edge; socket body and ears above, ears screw to the shell" (at 0 -18.6 0) (layer "F.Fab") (uuid "{u("note")}") '
             '(effects (font (size 1 1) (thickness 0.15))))')
    # courtyards around the pads on both faces
    for side in ('F', 'B'):
        L.append(f'(fp_rect (start -43.5 0) (end 43.5 {PAD_GAP + PAD_L + 0.5}) (stroke (width 0.05) (type default)) (fill no) '
                 f'(layer "{side}.CrtYd") (uuid "{u("crt" + side)}"))')
    # pin number marks
    ys = PAD_GAP + PAD_L + 1.2
    for side, a, b_, mirror in (('B', '1', '31', ' (justify mirror)'), ('F', '32', '62', '')):
        for txt, x in ((a, X[0]), (b_, X[30])):
            L.append(f'(fp_text user "{txt}" (at {x} {ys:.2f} 0) (layer "{side}.SilkS") (uuid "{u("mark" + side + txt)}") '
                     f'(effects (font (size 0.8 0.8) (thickness 0.12)){mirror}))')
    # pads: 1-31 on B.Cu, 32-62 on F.Cu at the same x (pin 32 opposite pin 1)
    for i, x in enumerate(X):
        for num, side in ((i + 1, 'B'), (i + 32, 'F')):
            L.append(f'(pad "{num}" smd rect (at {x} {yc}) (size {PAD_W} {PAD_L}) (layers "{side}.Cu" "{side}.Mask") (uuid "{u(f"pad{num}")}"))')
    L.append(f'(model "${{KIPRJMOD}}/libraries/3d/{NAME}.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))')
    L.append(')')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(L) + '\n', encoding='utf-8', newline='\n')
    print(f'wrote {out} ({len(X) * 2} pads)')


if __name__ == '__main__':
    main()
