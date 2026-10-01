# SN64 v2 shell: N64 cartridge body with a rounded mushroom cap (look-and-fit model)

**Status (2026-09-30): look-and-fit model for the owner's review. Not a manufacturable enclosure.**

Owner's direction, in order: one continuous vertical item with the SNES cartridge upright on top (a
first model with the cartridge flat on a shelf was rejected on sight); a mushroom cap so the shell
supports the inserted cartridge; then, with photos of an N64 cartridge, the part that plugs into
the console should look like that cartridge ("reuse part of an n64 cart stl") and the cap should
have "smoother rounder edges" in line with Nintendo's own design choices.

## Model

`mechanical/sn64-v2-shell/sn64_v2_shell.py` (build123d, code-first, diffable). Outputs in the same
folder: `sn64-v2-shell-assembly.step` (named bodies: shell, board, socket, cartridge, usbc,
console_top), `sn64-v2-shell-only.stl` (the assembly STL and the 39 MB board fit assembly are generated
locally and kept out of git), renders taken in FreeCAD:
`shell-front` (label side, what the player sees), `shell-back`, `shell-right`, `shell-bottom` and
`shell-port` (the port), `shell-iso`, `shell-iso-back`, `shell-low`. FreeCAD opens the STEP
directly; Blender imports the STL (File > Import > STL).

Frame: X across the board, Y up with 0 at the N64 tongue shoulders, Z out of the board's F.Cu
face. This is SummerCart64's own shell frame moved 0.6 mm in Z; its two mounting bosses are at
(+-47.5, -3.25), where our board has H1 and H2. F.Cu faces the back of the console (the N64 edge's
pins 1-25 are on B.Cu and pin 1 is on the front row of the slot), so +Z is the screw side of the
cartridge and the label side is -Z. A player sees the label side, and the USB-C (board +X) is on
their left. The exported files are turned so viewers see Z up.

License: the lower body and the outline are derived from SummerCart64's shell
(`references/downloads/summercart64/hw/shell/injection mold/sc64_shell.stp`, commit a1e7996d,
CERN-OHL-S-2.0), so the shell model is CERN-OHL-S-2.0 too (`mechanical/README.md`).

## How it is built

- **Lower body**: the real N64-shaped SummerCart64 shell, both halves fused, from its bottom
  (12.31 mm below the shoulders) up to 24.5 mm above them: port opening, feet, grooves, label
  recess, board ledges and the two mounting bosses exactly as SummerCart64 has them. Two changes:
  the support post at (-8.5, 21) is removed because it would sit under our FPGA and three small
  parts, and 1.3 mm is trimmed from the right locating post (our board mirrored the left notch;
  SummerCart64's right notch starts lower).
- **Stem**: that shell's outer outline at 24.5 mm extruded up to the flare: flat back with 1 mm
  corners, 9 mm front corners, two grooves on the label face, 2 mm walls. SummerCart64's own side
  openings (25.8 to 43.5 mm) are therefore not in our shell.
- **Flare**: a smooth S-curve from 57.5 to 70 mm (monotonic, one inflection, near-tangent to the
  stem and to the cap wall).
- **Cap**: 146.6 x 30.6 mm with the N64 cartridge's own 9 mm front corners and 6 mm back corners,
  5 mm walls around the pocket. The rim is arched like the top of an N64 cartridge (21.5 mm above
  the seat at the centre, 6 mm lower at the ends) with a 2.5 mm fillet, and the pocket lip has a
  0.8 mm chamfer.
- **Socket**: the 62-contact console-replacement SNES/SFC socket with ears on the board's top edge,
  tails on pads on both faces: pins 1-31 on B.Cu (toward the front of the console and the cartridge
  label, pin 1 at the left end seen from the front), pins 32-62 on F.Cu. Its rows are 7.0 mm apart
  and the board is 1.2 mm thick, so the tails do not reach the faces as supplied; the owner will
  adapt the board footprint to the measured sample.
- **Ears** rest on two brackets in the shell and are screwed from above, so the shell carries the
  cartridge insertion force and the solder joints carry none.
- **Cartridge** stands in the cap's pocket, held on all four sides, its bottom face on the socket
  shoulder.
- **USB-C** in the right wall of the stem, centre 50 mm above the shoulders, below the flare.

| Item | Value (mm) | Basis |
|---|---|---|
| N64 body | 116.12 x 18.06, bottom 12.31 below the shoulders | SummerCart64 shell STEP (sourced, measured) |
| Board plane in the body | 8.4 to the label face, 9.6 to the screw face | SummerCart64 ledges and bosses (sourced) |
| Real shell kept up to | 24.5 above the shoulders | below SummerCart64's side openings |
| Flare | 57.5 to 70, S-curve | assumed; starts above the USB-C window |
| Cap | 146.6 x 30.6, front corners 9, back corners 6 | cartridge + 0.3 clearance + 5 wall |
| Cartridge pocket | 136.6 x 20.6, floor at 76.5 (socket shoulder) | assumed seat |
| Rim | 98.0 at the centre, 92.0 at the ends, fillet 2.5 | assumed |
| Wall | 2.0 body and stem, 2.0 to 2.9 through the flare, 5.0 around the pocket | SummerCart64 2.0; rest assumed |
| Console top line | drawn at 25 | **assumed**: SummerCart64's own USB-C opening starts at 25.8, so the console top is lower |
| Socket body | 99.0 x 11.25, ear holes 3.2 at 95.0 | OpenSFC console footprint (sourced) |
| Socket base / nose height | 6 / 9, nose 88 x 9 | **assumed**; a marketplace listing gives 21 mm overall |
| Board top edge | 70 | socket underside 0.5 above it |
| Cartridge | 136 x 88 x 20 upright, seat at 76.5, top at 164.5 | Wikipedia (unverified) |
| USB-C window | 13 x 7 in the right wall at 50 | plug envelope 12.35 x 6.5 **assumed** |
| Overall shell | 146.6 x 110.3 x 30.6, one valid solid | derived |

Fit check with this shell: the KiCad board STEP with every part model, plus an envelope for the
FPGA (its model is missing from the STEP), has no interference with the shell or the cartridge.

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
(the socket) against 14.06 mm. The combined file `sn64-v2-fit-assembly.step` (35 MB) is generated locally and kept out of git; renders `fit-*.png`
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

- **Cartridge keying.** The pocket is a plain rectangle, so a cartridge can be put in back to
  front, which swaps its 5 V and ground contacts. The pocket needs the console's keying so a
  cartridge only goes in label-forward. This is a safety item, not a cosmetic one.
- Buy one sample socket and measure it: height, nose, tail length and section, ear shape and hole
  spacing, and how deep a cartridge seats.
- Console top line (N64) and the M64 opening.
- SFC and PAL cartridges are 130 mm wide against the 136.6 mm pocket: guide ribs to centre them.
- Pocket depth against grip: the cartridge must still be easy to pull out by its top.
- Split line (SummerCart64's halves part at the board's back face), screws for the upper part (the
  part that was replaced needs its own), bosses for H3 to H6, the ear screw detail.
- Board: the right side notch is 1.3 mm higher than SummerCart64's; correct the outline so an
  unmodified SummerCart64 lower shell fits, or keep the trimmed post.
