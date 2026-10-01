# SN64 v2 shell: N64 cartridge body with a rounded mushroom cap

**Status (2026-10-01): two halves with screw posts for the board, checked in CAD only. Nothing has
been printed or tried on parts, and several sizes are still assumptions (see "Open"). The console's
top surface is a measured height. The owner approved a 10 mm shorter geometry on 2026-10-01 and the
board was refitted to it the same day, so shell and board agree.**

Owner's direction, in order: one continuous vertical item with the SNES cartridge upright on top (a
first model with the cartridge flat on a shelf was rejected on sight); a mushroom cap so the shell
supports the inserted cartridge; then, with photos of an N64 cartridge, the part that plugs into
the console should look like that cartridge ("reuse part of an n64 cart stl") and the cap should
have "smoother rounder edges" in line with Nintendo's own design choices.

## Model

`mechanical/sn64-v2-shell/sn64_v2_shell.py` (build123d, code-first, diffable). Outputs in the same
folder: `sn64-v2-shell-assembly.step` (named bodies: shell_front, shell_back, board, socket, cartridge,
usbc, console_top), `sn64-v2-shell-front.stl` and `sn64-v2-shell-back.stl` for the two halves (the
assembly STL and the 41 MB board fit assembly are generated locally and kept out of git), renders
taken in FreeCAD:
`shell-front` (label side, what the player sees), `shell-back`, `shell-right`, `shell-bottom` and
`shell-port` (from low in front), `shell-iso`, `shell-iso-back`, `shell-low`, `shell-pocket` (looking into the empty
pocket), `shell-logo` (the logo on the front of the cap, close up), `shell-logo-back` (the owner's logo
on the back of the cap, close up), `shell-usb` (the USB-C port, close up), `halves-open` (both halves, insides up),
`half-front-with-board` (the board in the label-side half), `section-screw-post` (cut through a screw
post) and `section-centre` (cut through the middle). FreeCAD opens the STEP
directly; Blender imports the STL (File > Import > STL).

The script draws two geometries, picked by `VARIANT` near its top: `board-60`, the board as it is
(the tracked STEP, STL and `shell-*.png`), and `board-70`, the taller geometry of before 2026-10-01,
kept for comparison (its files carry `board-70` in the name and are generated locally, not tracked).
`compare-70-vs-60.png` shows the two side by side.

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
- **Flare**: a smooth S-curve from 44 to 60 mm (monotonic, one inflection, near-tangent to the
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
- **Cartridge** stands in the cap's pocket, held on all four sides, its bottom face on the pocket
  floor, which is level with the socket shoulder. The pocket is sized for the US cartridge and has
  no region tabs, so Super Famicom and PAL cartridges (about 6 mm narrower, same connector) go in
  too.
- **USB-C** in the side wall of the stem, centre 32.5 mm above the shoulders: 8 mm above the
  console's top surface and 5 mm below the flare. It is on the board's +X side, which is the
  player's left. The port has two steps with rounded ends (owner, 2026-10-01: the plain window
  was a placeholder): a recess for the cable plug's overmold, and through its floor an opening
  just larger than the receptacle's face. The recess is needed, not decoration: the receptacle's
  face is 2.06 mm behind the wall's outer surface, and a mated plug's overmold stops 1.95 mm in
  front of the receptacle, so against a flat wall a plug would stop 0.1 mm short of home.
- **Two halves**, like an N64 cartridge: the label-side half carries the board and the back half
  closes over it. They part at the board's back face, where SummerCart64's halves part. The
  brackets under the socket ears belong to the label-side half and stand 0.25 mm clear of the back
  half's wall.
- **Board mounting**, the way a Nintendo cartridge mounts its board (owner, 2026-10-01). At the four
  screw holes (H1, H2 at the bottom, H5, H6 at 44.5 mm) the label-side post has a shelf the board
  sits on and a hollow through-hole section, 3.8 mm across and 1.1 mm high, that passes through the
  board's 4.0 mm hole. The board therefore sits in one place and cannot shift. The through-hole
  section is 0.1 mm shorter than the board is thick, so the back half's post lands on the board and
  holds it on the shelf. The board sits 8.4 mm from the label face and 9.6 mm from the back face,
  which is where the N64 slot needs it. The screw runs through the middle of both posts.
- **Registration** (owner, 2026-10-01: nobody should be able to put the board in backward). Two solid
  2.3 mm pins on the label-side half go through board holes H3 and H4, which sit 6.5 mm and 9.5 mm
  above the shoulders, one left and one right. A board turned back to front has no holes under the
  pins: it stops on their tips 3.2 mm above the shelves and the back half cannot close. The pins
  stand 2 mm beyond the board and enter sockets in the back half, so they also line up the halves.
- **Screws**: six, all from the back. Four go through the board posts; two go through the back half
  into the ear brackets and hold the halves together under the cap.
- **Logo** stamped into the front of the cap the way a Game Boy cartridge carries its logo (owner,
  2026-10-01: "I dont want it proud of the surface"): a pill-shaped pocket, which is the inside of
  the logo's ring, with the button pads and the letters standing in it level with the face. The
  shapes come from `assets/logo/sn64-logo-mono.svg`.
- **The owner's FantomZap logo** stamped into the back of the cap the same way (owner, 2026-10-01:
  "use on the reverse side of the shell like we did with the front"): a pill-shaped pocket of the
  same height and depth, with the warning triangle, the bolt and the nine letters standing in it
  level with the face. It reads the right way round from behind and sits clear of the screws.
  The shapes are outlines traced from his artwork, `assets/logo/fantomzap/fantomzap-wordmark-mono.svg`.
  The FantomZap name and logo are his and are not under the open licences (see `NOTICE`).

| Item | Value (mm) | Basis |
|---|---|---|
| N64 body | 116.12 x 18.06, bottom 12.31 below the shoulders | SummerCart64 shell STEP (sourced, measured) |
| Board plane in the body | 8.4 to the label face, 9.6 to the screw face | SummerCart64 ledges and bosses (sourced) |
| Real shell kept up to | 24.5 above the shoulders | below SummerCart64's side openings |
| Flare | 44 to 60, S-curve | starts 5 above the USB-C window (owner), ends at the board's top edge |
| Cap | 146.6 x 30.5, front corners 9, back corners 6, centred on the pocket | pocket + 5 wall |
| Cartridge pocket | 136.6 x 20.5, floor at 66.5 (socket shoulder), 1.45 off-centre toward the label side | US cartridge 135.4 x 19.9 (measured, community) + 0.6 / 0.3 clearance; offset **assumed** |
| Rim | 88.0 at the centre, 82.0 at the ends, fillet 2.5 | assumed |
| Wall | 2.0 body and stem, 2.0 to 2.9 through the flare, 5.0 around the pocket | SummerCart64 2.0; rest assumed |
| Console top surface | 17.7 above the shoulders | **measured by the owner (2026-10-01)**: 30 mm from the top surface down to the floor of the cartridge hole, N64 and M64; the shell bottom is 12.31 below the shoulders |
| Socket body | 99.0 x 11.25, ear holes 3.2 at 95.0 | OpenSFC console footprint (sourced) |
| Socket base | 6 high | **assumed**; a marketplace listing gives 21 mm overall |
| Socket nose | 94.9 x 8.75, 10.55 high, slot 90.5 long with a key in each PCB gap | SNES Jr connector model (sourced, a different connector of the same family) |
| Board top edge | 60 | socket underside 0.5 above it |
| Cartridge | US shape: 135.4 wide, middle 92.2 x 19.9 x 87.5, sides 17.0 x 84.2; seat at 66.5, top at 154.0 | NESdev forum measurements (community, "a little rough") |
| USB-C port, recess | 13 x 7 with rounded ends, 1.0 deep, in the side wall at 32.5, 8.3 above the console top | plug overmold 12.35 x 6.5 at most **assumed**; depth chosen so the overmold ends 0.9 above the recess floor |
| USB-C port, opening | 9.6 x 3.8 with rounded ends through the 1.0 rim that is left | receptacle 8.94 x 3.16 (JAE drawing SJ122205, sourced) plus 0.33 all round (**assumed** clearance) |
| Plug against the wall | receptacle face 2.06 behind the outer surface; mated overmold 1.95 in front of the receptacle | wall 2.0 (model); 6.65 plug length less 4.7 engagement (JAE drawing, sourced) |
| Back logo pocket | 102.4 x 19.0, 0.6 deep, centred on the cap's back face 12.25 above the board's top edge; artwork 88.4 x 14.6 | owner's logo; same height and depth as the front pocket |
| Back logo detail at this size | triangle border 1.1, letter strokes 1.2 to 1.4; sharp tips under 0.7; tightest gaps under 0.35 | measured on the traced outlines |
| Logo pocket | 64.7 x 19.0, 0.6 deep, centred on the cap's front face 12.25 above the board's top edge; 4.4 of wall left behind it | owner's choice of logo and style; size fitted to the flat face (25 high), depth **assumed** |
| Logo detail at this size | letters 12.3 tall with 2.45 strokes; characters on the buttons 2.9 tall with 0.58 strokes; narrowest opening 0.46 (inside the 4 on its button) | derived from the logo file |
| Parting plane | the board's back face, 0.6 behind its mid-plane | SummerCart64 shell (sourced) |
| Screw posts | label side 6.5 post with a shelf and a 3.8 x 1.1 through-hole section; back 7.0 post (8.0 at the brackets) that lands on the board, the screw head 2.5 above the board in a well | owner's design (2026-10-01); head well as in SummerCart64's posts (sourced) |
| Board holes | H1, H2, H5, H6: 4.0 for the through-hole section; H3, H4: 2.5 for the registration pins | set on the board by `hardware/sn64-v2/tools/set_mounting_holes_v2.py` |
| Screw holes | pilot 1.7 x 5 deep below the shelf, 2.2 through the through-hole section (0.8 wall, no thread cut in it), clearance 2.4, head well 4.6: six M2 x 8 thread-forming screws | **assumed**: M2 is what SummerCart64's build guide uses |
| Registration pins | 2.3 in the board's 2.5 holes H3 and H4, standing 2.0 beyond the board, sockets 2.7 in the back half | **assumed** fit |
| Overall shell | 146.6 x 100.3 x 30.5, two valid solids | derived |

Fit check with this shell: the KiCad board STEP with every part model, plus an envelope for the
FPGA (its model is missing from the STEP), has no interference with the shell or the cartridge.

## Cartridge in the slot (2026-10-01)

The plain box that stood in for the cartridge is replaced by a US SNES cartridge built from caliper
measurements (rainwarrior, NESdev forum; table in `docs/dimensions.md`): thick middle section, thinner
side sections, two rear notches, the front slot, the card-edge hole, and a 62-contact PCB edge with
its two tabs. No open North American shell model with a usable license was found (the one GitHub
reconstruction is CC BY-NC-ND and calls its own dimensions estimates), and the Super Famicom meshes in
`mechanical/downloads` are hobby models that fail a closed-mesh test.

What the cartridge checks, and the result (`interface_checks()` in the script):

| Check | Result |
|---|---|
| Socket contacts that land on the cartridge's PCB edge (our footprint's pin positions against the measured edge and tabs) | 31 of 31 per side, 1.45 mm of edge beyond the outer contacts |
| Connector nose in the card-edge hole | 1.3 mm clear each side in width, 1.08 mm front to back |
| Keys | the two gaps in the PCB edge (2.2 mm at +-31.05) line up with the 7.5 mm gaps in the pin pattern |
| Contact overlap on the PCB edge | 8.55 mm with the assumed 2.0 mm recess (the fingers reach 8 mm) |
| Real board with all part models, FPGA envelope, cartridge and its PCB | no interference |

One error found and fixed by this check: the socket nose had been guessed at 88 mm wide, which a
62-contact cartridge edge (89.9 mm) cannot enter. The nose is now the SNES Jr connector's
94.9 x 8.75 x 10.55 in the shell model and in the board's 3D model
(`hardware/sn64-v2/tools/socket_3d_model.py`).

Still assumed, and needing two caliper readings on a real US cartridge:

1. From the cartridge's back face to its PCB (drawn 8.5 mm to the PCB's mid-plane, with the back face
   flat and the thick middle section proud on the label side). This sets where the pocket sits front
   to back; the cap is drawn 1.45 mm off-centre toward the label side because of it.
2. From the cartridge's bottom face up to the PCB's edge (drawn 2.0 mm). This sets how far the
   contacts overlap the fingers.

## Shorter geometry (2026-10-01, approved by the owner and applied)

The owner asked whether the unit could be shorter while keeping about 5 mm clear on each side of the
USB port, and measured the console: its top surface is 30 mm above the floor of the cartridge hole,
17.7 mm above the board's shoulders. He approved the result from the picture of the two side by side
(`compare-70-vs-60.png`), and the board was refitted the same day (see "Board refit to the shorter
shell" below).

| | Before (`board-70`) | Now (`board-60`) |
|---|---|---|
| Board top edge above the shoulders | 70 | 60 |
| USB-C centre | 50 | 32.5 |
| USB-C window | 43.5 to 56.5 | 26.0 to 39.0 |
| Console top to the window | 25.8 | 8.3 |
| Plain wall between the window and the flare | 1.0 | 5.0 |
| Flare | 57.5 to 70 | 44 to 60 |
| Cartridge seat | 76.5 | 66.5 |
| Rim, centre / ends | 98 / 92 | 88 / 82 |
| Shell height | 110.3 | 100.3 |
| Top of a US cartridge above the console top | 146.3 | 136.3 |

What sets each number:

- **USB-C at 32.5.** The receptacle needs the 111 mm wide part of the board, and that part cannot start
  below 26.4 mm: under it the board keeps SummerCart64's 101.8 mm width and the notches for the
  shell's two locating posts, which end at 26.4. 32.5 is also the height of SummerCart64's own USB-C
  opening (25.8 to 39.2), which is used with the cartridge in the console.
- **Flare from 44.** 5 mm of plain wall above the window, as asked.
- **Top edge at 60.** The flare ends at the board's top edge, where the socket sits. The translator
  row ends at 47.7 mm and the socket pads take 56.0 to 59.5, which leaves about 8 mm for the fan-out
  between them. It had 18 mm before.

Going shorter than this means moving the translator row down or giving the translators' channels
the socket's pin order (schematic, FPGA pin plan and a new route of that area). Neither is planned.

## Board refit to the tower shell (2026-09-30)

`hardware/sn64-v2/tools/refit_tower_v2.py` changed the routed board in place of a full re-layout:

- J2 is now `SN64_V2:SNES_Slot_Console_Straddle` on the top edge at 70 mm: 62 pads 1.5 x 3.5 mm,
  0.5 mm from the edge, pins 1-31 on B.Cu and 32-62 on F.Cu at the old pin x positions (pin 1 at
  +42.5). Its 3D model (`libraries/3d/SNES_Slot_Console_Straddle.step`) shows the eared body above
  the edge. The face-mounted socket, its copper above the translator row and 226 leftover dangling
  pieces were removed and the socket nets routed again from the translators.
- Outline: 101.8 mm wide to 32 mm above the shoulders, 111 mm to 60 mm, then an 88 mm neck to the
  top edge at 70 mm; the SummerCart64 part below 26.4 mm is unchanged.
- USB-C J101 at the right edge 50 mm above the shoulders (32 mm above the console's top surface as
  measured on 2026-10-01; the line was assumed 10 mm higher when this was done),
  turned to face outward with the JAE reference 0.5 mm front overhang. Its ESD part and VBUS
  capacitor moved with it; the series and pull-up resistors stay beside the FPGA with their routing.
  The five nets that reach the moved parts were cut at the old connector and routed again.
- Top mounting holes H5/H6 moved from 66.5 mm (inside the neck) to 38 mm in the widened part.
- Planes and outer GND pours enlarged to the new outline.

Result at the time: 3,551 tracks, 1,034 vias, 213 of 218 signal nets fully connected, 6 unconnected items; DRC errors: 5 starved_thermal.

## Board refit to the shorter shell (2026-10-01)

The same script with the `short-60` geometry (`refit_tower_v2.py clear|place IN OUT short-60`) applied
the shorter shell to the routed board:

- Outline: 111 mm wide from 26.4 to 50 mm above the shoulders, the 88 mm neck from 50 to 60, top edge
  at 60. J2's pads are 10 mm lower, at 56.0 to 59.5.
- USB-C J101 and its ESD part at 32.5 mm on the right edge, the VBUS capacitor above them at 37; top
  mounting holes H5/H6 at 44.5. The silkscreen credit line moved to 50.5.
- Removed: the socket's copper above the translator row and the five USB nets on the right side of
  the board (500 tracks and vias), then 307 dangling pieces. Everything else was locked and is
  untouched.
- Routed again: 64 nets (59 socket nets and 5 USB nets) on F.Cu, In2.Cu and B.Cu, the socket nets in
  the 8 mm between the translator row and the socket pads. The router's default ordering left the
  cartridge's master clock boxed in at the corner pad; its `bus` ordering routed all 64. A run with
  In4.Cu as a fourth layer also routed all 64 and was not used, so In4 still carries only the 1.1 V
  island.

Result: 3,603 tracks, 1,066 vias, 213 of 218 signal nets fully connected, the same 6 unconnected items as before (FLASH_D2, FPGA_3V3, N64_AD6, N64_JOYBUS, USB_DP_F, USB_PU); DRC errors: 6 starved_thermal. Five are the ones from before; the new one is a shield leg of the USB-C receptacle beside the board's side notch, which also connects to the ground plane inside. Full list: `hardware/sn64-v2/validation/pcb-open-connections.json`.

Fit check: the KiCad board exported as STEP with every part model (`hardware/sn64-v2/exports/sn64-v2.step`,
288 solids including the socket) placed in this shell model has no interference with the shell, the
cartridge or its PCB (checked again after the second refit). Its envelope is 111 mm wide against the stem's 112.1 mm inside and 11.25 mm thick
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
  cartridge only goes in label-forward. This is a safety item, not a cosmetic one. Since
  2026-10-01 the FPGA also checks for a reversed cartridge before it switches 5 V on
  ([reversed-cartridge-detection.md](reversed-cartridge-detection.md)). That is a second line,
  simulated only, and it does not cover a cartridge with its own reverse protection, so the
  keying is still needed.
- Two caliper readings on a real US cartridge (see "Cartridge in the slot"), and the same for a
  Super Famicom or PAL cartridge.
- Buy one sample socket and measure it: height, nose, tail length and section, ear shape and hole
  spacing, and how deep a cartridge seats.
- The shape of the console's top surface around the cartridge hole, N64 and M64. Its height is
  measured; what a part wider than the hole can meet on the way down is not.
- SFC and PAL cartridges are 130 mm wide against the 136.6 mm pocket: guide ribs to centre them.
- Pocket depth against grip: the cartridge must still be easy to pull out by its top.
- **USB-C on the other side.** The owner would rather have the port on the player's right
  (2026-10-01) and accepts the left if the move is costly. It is not a board redesign but it is not
  free either: on the other side the open-drain driver U205 and two capacitors (C209, C212) sit
  where the receptacle and its protection part would go, so the two corners trade places, about
  twenty nets are routed again, and the USB data pair either runs about 95 mm across the board to
  its series resistors or the FPGA's USB pins move. Not done; waiting for his word. The shell
  script has `USB_SIDE` for it.
- USB-C port in plastic: the 1.0 mm rim around the opening and the 0.33 mm clearance are untried.
  Try real cables, including ones with a thick overmold.
- Back logo against the process: its tips and its tightest gaps (under 0.35 mm) will fill in on a
  filament printer; the strokes themselves (1.1 mm and up) hold.
- Logo detail against the process that makes the shell: the characters on the buttons have 0.58 mm
  strokes and a 0.46 mm opening. Moulding or resin printing holds that; a filament printer does not.
  `LOGO_REL` in the script switches to `sn64-logo-mono-plain.svg` (no characters on the buttons,
  finest detail 0.64 mm).
- Screws: the hole sizes are for M2 thread-forming screws and are assumptions. Choose the screw, then
  try the pilot size in the plastic and process actually used.
- Board thickness: the through-hole section is 1.1 mm for a 1.2 mm board. A board at the thin end of
  the fabricator's tolerance (about 1.08 mm) would sit level with it and be held less firmly.
- Seam: above the N64 body the two halves meet on a plain flat face. A lip along the seam would align
  them and keep it closed between the screws. Whether six screws hold the cap shut against a cartridge
  being rocked in the pocket is untested.
- Socket legs: the two rows are 7.0 mm apart and the pads are on the faces of a 1.2 mm board, so each
  row has to come in 2.9 mm. The owner plans a double bend. That takes about 5 to 6 mm of leg, and
  the leg length is unknown until a sample is measured.
- The ear screws go in from above through the cartridge pocket; their size and the ears' own shape
  wait for the sample.
- Board: the right side notch is 1.3 mm higher than SummerCart64's; correct the outline so an
  unmodified SummerCart64 lower shell fits, or keep the trimmed post.

## 2026-10-01: the owner's logo on the back, and a real USB-C port

The owner chose one of his own logo files (warning triangle with a bolt, and the word FantomZap beside it) and asked for it on the back of the shell, done like the front. The artwork is a pixel image, so it was traced into outlines first ([assets/logo/fantomzap/](../../assets/logo/fantomzap/README.md)). The back of the cap now has a pocket 102.4 x 19.0 mm and 0.6 mm deep with the logo's eleven pieces standing in it level with the face. Checked in the model: both halves are single valid solids, nothing is higher than the back face, and the pocket ends 22 mm from the cap's corners and above the screw wells.

He also pointed out that the USB-C opening was a placeholder: a plain 13 x 7 window. It is now a recess with rounded ends for the plug's overmold and an opening with rounded ends around the receptacle (values in the table above). The model's receptacle does not touch the shell.

Pictures: [shell-back.png](../../mechanical/sn64-v2-shell/shell-back.png), [shell-logo-back.png](../../mechanical/sn64-v2-shell/shell-logo-back.png), [shell-iso-back.png](../../mechanical/sn64-v2-shell/shell-iso-back.png), [shell-usb.png](../../mechanical/sn64-v2-shell/shell-usb.png), [shell-right.png](../../mechanical/sn64-v2-shell/shell-right.png). The `fit-*.png` pictures were made before these two changes and do not show them.
