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

Frame: X across the board, Y up with 0 at the N64 tongue shoulders, Z out of the board's F.Cu
face. F.Cu faces the back of the console: the N64 edge's pins 1-25 are on B.Cu and pin 1 is on the
front row of the slot. A player therefore sees the B.Cu side, and the USB-C (board +X) is on their
left. The exported files are turned so viewers see Z up with the F.Cu face toward -Y.

## How it goes together

- **Socket**: the 62-contact console-replacement SNES/SFC socket with ears. It sits on the board's
  top edge with its tails on pads on both faces: pins 1-31 on B.Cu, the face toward the front of
  the console and the cartridge label, with pin 1 at the left end seen from the front; pins 32-62
  on F.Cu. Its two rows are 7.0 mm apart and
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

## Board refit to this shell (done 2026-09-30)

`hardware/sn64-v2/tools/refit_tower_v2.py` changed the routed board in place of a full re-layout:

- J2 is now `SN64_V2:SNES_Slot_Console_Straddle` on the top edge at 70 mm: 62 pads 1.5 x 3.5 mm,
  0.5 mm from the edge, pins 1-31 on B.Cu and 32-62 on F.Cu at the old pin x positions (pin 1 at
  +42.5). Its 3D model (`libraries/3d/SNES_Slot_Console_Straddle.step`) shows the eared body above
  the edge. The face-mounted socket, its copper above the translator row and 226 leftover dangling
  pieces were removed and the socket nets routed again from the translators.
- Outline: 101.8 mm wide to 32 mm above the shoulders, 111 mm to 60 mm, then an 88 mm neck to the
  top edge at 70 mm; the SummerCart64 part below 26.4 mm is unchanged.
- USB-C J101 at the right edge 50 mm above the shoulders (22 mm above the assumed console line),
  turned to face outward with the JAE reference 0.5 mm front overhang. Its ESD part and VBUS
  capacitor moved with it; the series and pull-up resistors stay beside the FPGA with their routing.
  The five nets that reach the moved parts were cut at the old connector and routed again.
- Top mounting holes H5/H6 moved from 66.5 mm (inside the neck) to 38 mm in the widened part.
- Planes and outer GND pours enlarged to the new outline.

Result: 3,551 tracks, 1,034 vias, 213 of 218 signal nets fully connected, 6 unconnected items (FLASH_D2, FPGA_3V3, N64_AD6, N64_JOYBUS, USB_DP_F, USB_PU); DRC errors: 5 starved_thermal. Full list: `hardware/sn64-v2/validation/pcb-open-connections.json`.

Fit check: the KiCad board exported as STEP with every part model (`hardware/sn64-v2/exports/sn64-v2.step`,
288 solids including the socket) placed in this shell model has no interference with the shell or
the cartridge. Its envelope is 111 mm wide against the stem's 112.1 mm inside and 11.25 mm thick
(the socket) against 14.06 mm. The combined file is `sn64-v2-fit-assembly.step`, renders `fit-*.png`
(`fit-front` is seen from the front of the console, `fit-rear` from behind).

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
