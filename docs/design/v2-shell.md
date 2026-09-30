# SN64 v2 shell: upright tower with a mushroom cap (envelope model)

**Status (2026-09-30): envelope model for the owner's review. Not a manufacturable enclosure. The
board has not changed yet.**

The owner's arrangement is one continuous vertical item: the SN64 stands in the N64/M64 slot and
the SNES cartridge stands upright on top of it, in line, like a TriStar 64. A first model that laid
the cartridge flat on a shelf out of the board's front face was rejected on sight and replaced by
this one. The owner then asked for a mushroom shape so the shell supports the inserted cartridge:
above the USB-C the stem bells out into a cap whose pocket wraps the bottom of the cartridge.

## Model

`mechanical/sn64-v2-shell/sn64_v2_shell.py` (build123d, code-first, diffable). Outputs in the same
folder: `sn64-v2-shell-assembly.step` (named bodies: shell, board, socket, cartridge, usbc,
console_top), `sn64-v2-shell-assembly.stl`, `sn64-v2-shell-only.stl`, renders
`shell-{front,right,top,iso}.png` taken in FreeCAD. FreeCAD opens the STEP directly; Blender
imports the STL (File > Import > STL).

Frame: X across the board, Y up with 0 at the N64 tongue shoulders, Z out of the board's front
face. The exported files are turned so viewers see Z up with the front face toward -Y.

## How it goes together

- **Socket**: the 62-contact console-replacement SNES/SFC socket with ears. It sits on the board's
  top edge with its tails on pads on both faces: pins 1-31 on the front face (they face the front
  of the console and the cartridge label), pins 32-62 on the back. Its two rows are 7.0 mm apart and
  the board is 1.2 mm thick, so the tails do not reach the faces as supplied; the owner will adapt
  the board footprint to the measured sample.
- **Ears** rest on two brackets in the shell and are screwed from above, so the shell carries the
  cartridge insertion force and the solder joints carry none.
- **Cartridge** stands in a 20 mm deep pocket in the mushroom cap, which holds it on all four
  sides; its bottom face sits on the socket shoulder.
- **USB-C** in the right wall of the stem, centre 50 mm above the shoulders: 22 mm above the
  assumed console top and below the flare.

| Item | Value (mm) | Basis |
|---|---|---|
| Stem width x thickness | 116.1 x 18.06, from -13 (2.5 below the tongue tip) to 57.5 | SummerCart64 shell STEP (sourced); bottom margin assumed |
| Bell flare | 57.5 to 68, smooth loft from the stem to the cap | assumed; starts above the USB-C window |
| Cap | 142.6 x 26.6, corner radius 4, 68 to 96.5 | cartridge + 0.3 clearance + 3 wall |
| Cartridge pocket | 136.6 x 20.6, 20 deep, floor at 76.5 (socket shoulder) | depth assumed |
| Wall | 2.0 stem, 2.0 to 2.9 through the flare (checked), 3.0 around the pocket | assumed |
| Tongue opening | 66 x 3.2 in the bottom wall | board 64.5 x 1.2 plus clearance |
| Console top line | 28 above the shoulders | **assumed**; M64 opening unknown |
| Socket body | 99.0 x 11.25, ear holes 3.2 at 95.0 | OpenSFC console footprint (sourced) |
| Socket base / nose height | 6 / 9, nose 88 x 9 | **assumed**; a marketplace listing gives 21 mm overall |
| Board top edge | 70 (committed board height) | socket underside 0.5 above it |
| Cartridge | 136 x 88 x 20 upright, seat at 76.5, top at 164.5 | Wikipedia (unverified); 136.5 above the console top |
| USB-C window | 13 x 7 in the right wall at 50 | plug envelope 12.35 x 6.5 **assumed** |
| Overall shell | 142.6 x 109.5 x 26.6 | derived |

## Board changes this shell asks for (not made yet)

- J2 moves from the face (through-hole at 56.5) to a footprint on the top edge at 70, pins 1-31 on
  the front face. The existing routing can stay: the old J2 holes become vias with short stubs to
  the edge pads.
- Outline widened to 111 mm between 32 and 60 mm above the shoulders so the USB-C reaches the
  right wall; the top 10 mm narrowed to 88 mm so the ear screws pass beside the board. The two top
  mounting holes at 66.5 move into the wide section.
- USB-C J101 moves from 18 mm (inside the console) to 50 mm on the right edge; only the USB nets
  re-route.

## Socket sourcing (searched 2026-09-30)

The part is sold widely as a console repair part, "62 pin with ear". No seller publishes a drawing,
and no 3D model was found.

| Source | Evidence at inspection | Note |
|---|---|---|
| [NES Repair Shop `snspt043`](https://www.nesrepairsshop.com/Catalog/index.php?main_page=product_info&products_id=2262) | $9.99; 62 pins with soldering legs; fits SNES and SFC | sample candidate |
| [Shenzhen Co-Growing, Alibaba "SNES-Slot"](https://www.alibaba.com/product-detail/SFC-62-Pin-Game-Cartridge-Card_62358974795.html) | with ear / without ear; MOQ 50; $1.15 each at 50 | volume source; no dimensions |
| [Hexir `HXR-19-18637`](https://www.hexir.com/snes-62-pin-with-ear-cartridge-slot-connector-replacement-bulk-hexir/) | with ear; $10.28; pre-order; states 2.54 mm spacing | spacing claim conflicts with 2.5 mm |
| [Amazon B0H35742NX](https://www.amazon.com/SNES-Game-Slot-Connector-Replacement/dp/B0H35742NX) | with / without ears; search summary gives 13.7 x 2.1 x 0.9 cm with ears, 9.7 x 2.1 x 0.9 cm without | unverified; 137 mm conflicts with the 95 mm hole spacing |

Avoid listings for clone consoles that state a 2.54 mm gap.

Sourced geometry (OpenSFC footprint of the original console board, `docs/dimensions.md`): 62
contacts, 31 per row, 2.5 mm pitch with two 7.5 mm gaps (between contacts 4-5 and 27-28),
85.0 mm first to last, rows 7.0 mm apart, body 99.0 x 11.25 mm, holes 3.2 mm, 95.0 mm apart.
A 75 mm figure would be 31 contacts at 2.5 mm with no gaps; that part would miss the outer contact
groups, which carry the cartridge audio inputs (pins 31 and 62, used by FXPAK Pro MSU-1).

## Open

- Buy one sample and measure it: height, nose, tail length and section, ear shape and hole
  spacing, and how deep a cartridge seats.
- Console top line (N64) and the M64 opening.
- SFC and PAL cartridges are 130 mm wide against the 136.6 mm pocket: guide ribs to centre them.
- Pocket depth against grip: the cartridge must still be easy to pull out by its top.
- Split line, bosses at the board's mounting holes, the ear screw detail.
