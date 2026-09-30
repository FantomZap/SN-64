# SN64 v2 shell: envelope model (first look)

**Status (2026-09-30): envelope only, for the owner to look at before the board is resized. Not a
manufacturable enclosure. Nothing on the board changed.**

The owner set the order of work: shell first, then the board's height, shape and USB-C position
follow from it ("the shell needs to be set so we know where the usbc can be located").

## Model

`mechanical/sn64-v2-shell/sn64_v2_shell.py` (build123d, code-first, diffable). Outputs in the same
folder: `sn64-v2-shell-assembly.step` (named bodies: shell, board, socket, cartridge, usbc),
`sn64-v2-shell-assembly.stl`, `sn64-v2-shell-only.stl`, renders `shell-{iso,front,right,top}.png`.
FreeCAD opens the STEP directly; Blender imports the STL (File > Import > STL).

Frame: X across the board, Y up with 0 at the N64 tongue shoulders, Z out of the board's front
face. The exported files are turned so viewers see Z up with the front face toward -Y.

| Item | Value | Basis |
|---|---|---|
| Outer width x thickness | 116.1 x 18.06 mm | SummerCart64 shell STEP (sourced) |
| Height | -13 (2.5 below the tongue tip) to +88 | assumed bottom margin; top = board top 85 + 1 + wall |
| Wall | 2.0 mm | assumed |
| Tongue opening | 66 x 3.2 mm in the bottom wall | board 64.5 x 1.2 plus clearance (derived) |
| Console top line | 28 mm above the shoulders | **assumed**; to measure on the SC64 shell / a console |
| Socket window | 100.5 x 12.5 mm in the front wall at Y = 74.5 | socket body 99 x 11.25 (sourced) plus clearance |
| Socket height above the board | 12 mm | **assumed**; measure the sample socket |
| Cartridge | 136 x 88 x 20 mm lying flat, underside at Y = 64.5 | nominal; measure a real cartridge |
| Cartridge tray | 3 mm plate at Y = 61.5..64.5, 10 mm rails, two ribs to the front wall | first idea, not engineered |
| USB-C window | 13 x 7 mm in the right wall at Y = 50 | plug envelope 12.35 x 6.5 **assumed**; 22 above the console line, plug top 5 under the tray |
| Board in this model | socket centreline 74.5, board top 85 | proposal: 18 mm higher than the committed board (socket at 56.5, top 70) |
| Over-all | 142 x 101 x 108 mm including the tray | derived |

## What the model shows

- With the socket 74.5 mm up, the flat cartridge sits 20 mm clear of the console top line and the
  USB-C port has 22 mm of clear wall above the console for a plug and fingers.
- The shell is 116.1 mm wide (SummerCart64) but the board is 101.8 mm wide, so a USB-C receptacle on
  the board's right edge ends about 7 mm inside the right wall. Either the board widens above the
  console line (to about 110 mm; the SC64 profile only constrains the lower 26 mm) or the right wall
  steps in at the port. This is the decision the owner's review should settle.
- The cartridge overhangs the shell by 10 mm each side (136 vs 116), so the tray is wider than
  the body; a real shell would take the cartridge width as its upper width.

## Open

- Console line (N64) and the M64 opening: measure, do not assume.
- Socket height and nose reach: from the sample socket (`docs/design/socket-selection.md`).
- Split line, screw bosses at the board's six holes, how the tray carries insertion force.
- Board height and width, USB-C position: after the owner's review of this model.
