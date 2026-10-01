# Reusable connector and cartridge geometry

Collected 2026-09-28 local time. These are exact dimensions in the downloaded upstream CAD, **not measurements of an SN 64 prototype**. Use them as the starting geometry and retain the original pin orientation. All dimensions below are millimetres.

## SNES female socket: existing footprint

Source: [sanni/cartreader, SNES Slot footprint](https://github.com/sanni/cartreader/blob/060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d/hardware/footprints/%21OSCR.pretty/SNES%20Slot.kicad_mod). This gives a ready-made PCB footprint rather than a drawing we need to recreate.

| Feature | CAD value |
|---|---:|
| Contacts / rows | 62 / 2 rows of 31 |
| Normal pitch along a row | 2.5 |
| Row separation | 5.0 |
| Pad diameter | 1.524 |
| Hole diameter | 0.762 |
| First-to-last pad centre distance | 85.0 |
| Gaps between pins 4–5 and 27–28, repeated on opposite row | 7.5 |

Footprint coordinates: pin 1 is (0, 0); pin 31 is (0, 85); pin 32 is (5, 0); pin 62 is (5, 85). The two enlarged gaps matter; this is not an unbroken 31-contact row. [All 62 pad coordinates](../references/measurements/snes-socket-reference-pads.csv).

This footprint has no connector body/courtyard or mounting-ear geometry. The selected physical socket must match these pins; its body, board seating height, mounting ears, mating depth and rated insertion life remain to be established. Do not treat these PCB solder-hole dimensions as cartridge contact dimensions.

Also downloaded: the existing SNES adapter schematic, PCB and KiCad project from the same repository for pin mapping and layout reuse.

## N64/M64 lower interface: SummerCart64 reference

Source: [SummerCart64 PCB revision 2.1a](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_pcb). This is the **host-facing lower connector and cartridge geometry**, not the SNES implementation. Both hosts use this standard N64 interface.

| Feature | CAD value |
|---|---:|
| Contacts | 50, 25 on each face |
| Contact centre spacing | 2.5 |
| Individual contact pad | 1.5 wide × 7.0 long |
| First-to-last contact centre span | 60.0 |
| PCB thickness setting | 1.2 |
| Straight connector tongue width | 64.5 |
| Tongue shoulder to insertion tip | 10.5 |
| Lower plan-view corner cuts | 1.0 × 1.0 |
| Mounting holes | 2 holes, diameter 2.5 |
| Mounting-hole centre separation | 95.0 |
| Hole centres above insertion-tip datum | 7.25 |
| Entire upstream board outline envelope | 101.8 × 57.8 |

Original KiCad coordinates: connector origin (150, 125); tongue sides x=117.75 and 182.25; insertion tip y=135.5; pad centres y=131. Pin 1 is at (180, 131), pin 25 at (120, 131), both **B.Cu**. Pins 26–50 repeat those positions on **F.Cu**. Holes are at (102.5, 128.25) and (197.5, 128.25). [All pads and source net names](../references/measurements/n64-reference-pads.csv).

With the insertion-tip midpoint as (0,0) and positive Y upward: holes are at (-47.5, 7.25) and (47.5, 7.25), pad centres at Y=4.5, shoulders at Y=10.5. The 1 mm corner cuts are in the board's outline; they do **not** specify the through-thickness mating bevel angle.

The downloaded board uses a two-layer stack-up and ENIG. Reuse its mechanical interface; SN 64's multilayer stack-up and repeated-insertion contact finish still follow our own requirements. Its 1.2 mm stack-up includes a 1.11 mm FR4 core, two 0.035 mm copper layers and two 0.01 mm soldermask layers. KiCad's board-only STEP export reports **1.11 mm** because it exports that core; do not substitute that number for the PCB thickness setting.

## SNES socket body and cartridge edge (looked up 2026-09-29, unverified on parts)

Two socket families exist and their solder-tail rows differ; the footprint must match the purchased part:

| Source | Row spacing | Body / mounting | Notes |
|---|---|---|---|
| [OpenSFC `CartSlot.kicad_mod`](https://github.com/starlightk7/OpenSFC/blob/6574450b1a4594b2aae436cf23869b0fb5808ce8/Common/libraries/OpenSFC.pretty/CartSlot.kicad_mod) (original SHVC-CPU-01 console socket; SHA-256 `1f9b60ddd99989e69f4395c12e75292c88869fa6cf3515bcd9eee5485d48b5a0`) | **7.0** (pads at y = ±3.5) | Silkscreen body 99.0 × 11.25 mm (x ±49.5, y −5.65..+5.60); two Ø3.2 mm mounting holes at x = ±47.5 (95.0 mm apart), y ≈ 0 | 62 pads 1.5 mm / drill 1.0 mm; 2.5 mm pitch with the two 7.5 mm gaps; 85.0 mm first-to-last, same as Sanni |
| Sanni cartreader `SNES Slot` (already in this project) | **5.0** | none drawn | the cart-reader style socket |

**Decision (2026-09-29): the socket board uses the console-replacement family (7.0 mm rows, Ø3.2 mm ears 95.0 mm apart, OpenSFC geometry).** The ears give mechanical retention against cartridge insertion loads, and console-replacement sockets are sold by several retro repair suppliers (Hexir HXR-19-18637 "with ear", NES Repair Shop `snspt043`). The purchased sample is checked against this footprint before the socket board is ordered; if it turns out to be the 5.0 mm cart-reader type, the footprint changes, not the design.

Height above board and contact position are still not sourced for this family. Data point only: qwertymodo's SNES Jr recreation ([kicad-snn-cpu-01](https://github.com/qwertymodo/kicad-snn-cpu-01), commit `a0018661`, CERN-OHL-S-2.0) ships `SNES_Cartridge_Connector_1pc.step` (SHA-256 `7621e92d0a66c396b1f0f81db2e5cff8047f6773d7d9f0b3b197c602b1dd8e2d`): the SNES Jr's one-piece connector with its guide frame, 151.8 × 15.0 mm at the base, 23.55 mm tall, 94.9 × 8.76 mm at the top; a simplified model without slot or pins, and a different part from the original SHVC socket. These heights matter for the shell, not for the boards.

Cartridge edge, from the [sd2snes Rev F board](https://github.com/mrehkopf/sd2snes/blob/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/pcb/kicad/RevF/sd2snes.kicad_pcb) (SHA-256 `4255ad5c5b5ac93a13cf587f136c206f534536050f01960bcf7d00ebcc313dcf`, footprint `SNESCART_EXT2_SMTUSB`): 31 fingers per side, 1.5 × 7.0 mm (three wider 2.0 mm), 85.0 mm first-to-last, fingers from 1.0 mm to 8.0 mm above the board's bottom edge; board outline 101.5 × 83.0 mm. The file's thickness setting is 1.6 mm (a default); cartridge PCBs are 1.2 mm per community sources (MouseBiteLabs) and the N64 reference; measure before relying on it. So a socket engages roughly the bottom 8 mm of a cartridge; the exact seated depth depends on the socket's contact position.

## Cartridge shells (looked up 2026-09-29, encyclopaedic values, unverified)

[Wikipedia, "Super Nintendo Entertainment System Game Pak"](https://en.wikipedia.org/wiki/Super_Nintendo_Entertainment_System_Game_Pak): North American shell about **136 × 88 × 20 mm** (width × height × thickness); Super Famicom / PAL shell about **130 × 86 × 20 mm**. The same article records that the North American console slot is larger and has two plastic tabs near the connector that fit spaces in the wider North American shell; Super Famicom and PAL shells are the same shape as each other. For the SN64's universal opening this means: width for the 136 mm shell, guidance that also centres a 130 mm shell, and no region tabs. Community-sourced numbers; measure both shell types (bottom-edge profile, thickness, the notch positions) before the enclosure is cut.

## Existing N64 cartridge shell

Downloaded [SummerCart64 front/back STL and STEP shell parts](https://github.com/Polprzewodnikowy/SummerCart64/tree/a1e7996d2cbece686820a5c785029c68514f17b0/hw/shell). FreeCAD opened the combined STEP as two valid solids. Its assembled XYZ envelope is approximately **116.116 × 89.371 × 18.056 mm**. The separate halves have different transforms; use the combined assembly to preserve their alignment.

This is usable starting CAD for the lower enclosure. SN 64 still needs an upper SNES socket enclosure and structural support for tall cartridges; it is not an unchanged N64 shell. M64 bay/eject clearance is a separate surrounding-housing check.

## Files and verification

- [Download manifest with pinned commits and SHA-256](../references/source-manifest.json)
- [PCB and hole extraction](../references/measurements/pcb-inspection.json)
- [STEP validity, solids and bounds](../references/measurements/step-inspection.json)
- [Repeatable KiCad extraction script](../references/extract_dimensions.py)
- Upstream originals: `references/downloads/sanni/` and `references/downloads/summercart64/` locally. The manifest gives exact file paths and URLs; downloads are excluded from Git pending deliberate upstream attribution/reuse packaging.
- Local exports: `.local/research/exports/` contains both schematic PDFs, a board STEP, and `SummerCart64-reference.FCStd`.

Checked with KiCad 10.0.6 and FreeCAD 1.1.4: both native schematics export to PDF, the N64 PCB loads and exports a valid STEP solid, the downloaded shell STEP imports as valid solids, and a FreeCAD reference document saves successfully. No electrical or physical fit test has been claimed.

## US cartridge and console connector nose (looked up 2026-10-01, unverified on parts)

US SNES cartridge, caliper measurements by rainwarrior, [NESdev forum t=23890](https://forums.nesdev.org/viewtopic.php?t=23890), 2022-05-21, described by their author as "a little rough". "Depth" is front to back.

| Feature | mm |
|---|---|
| Total width / middle section width | 135.4 / 92.2 |
| Thickness: side sections / middle section | 17.0 / 19.9 |
| Height: side sections / middle section | 84.2 / 87.5 |
| Rear notches (both sides): outer edge from the side, width, height | 10.0, 4.9, 12.1 |
| Front slot: from the bottom, height, width, depth, depth across a 24.8 wide centre trench | 28.9, 5.0, 83.6, 5.4, 3.9 |
| Card-edge hole in the bottom face: width x front-to-back | 97.5 x 10.9 |
| PCB edge: width, thickness | 59.9, 1.27 |
| Extended (62-contact) edge: width, each tab, gap between tab and normal edge | 89.9, 12.55, 2.2 |
| Contact pitch | 2.5 |

The same thread gives a Super Famicom cartridge as 129 x 87 x 20 (jeffythedragonslayer). Not in the thread: which face the thicker middle section stands proud on, how far the PCB edge is from the bottom face, and where the PCB lies front to back; these need two caliper readings on a real cartridge.

Console connector nose, from the SNES Jr connector model in [kicad-snn-cpu-01](https://github.com/qwertymodo/kicad-snn-cpu-01) (commit `a0018661`, CERN-OHL-S-2.0, `SNES_Cartridge_Connector_1pc.step`, SHA-256 `7621e92d...`; simplified, no slot or pins), sectioned 2026-10-01: base 151.8 x 15.0 up to 4.0, then 107.95 x 15.0 to 8.0, 107.95 x 8.75 to 13.0, and the nose 94.9 x 8.75 from 13.0 to 23.55 (10.55 high). The nose has 1.3 mm each side in width and 1.08 mm front to back in the measured 97.5 x 10.9 hole, so the two sources agree. It is a different connector from the SHVC replacement socket SN64 uses; its nose stands in for ours until the sample is measured.

## Console cartridge hole depth (measured by the owner, 2026-10-01)

Measured by the owner on an original N64 and on a ModRetro M64: **30 mm** from the console's top surface down to the plastic floor of the cartridge hole, which is the surface the bottom face of a cartridge shell rests on. The same on both consoles. The instrument and its tolerance were not recorded; treat the figure as good to about a millimetre until it is taken again with calipers.

Derived: the bottom face of the SummerCart64 shell is 12.31 mm below the board's tongue shoulders (its STEP), so the console's top surface is **17.7 mm above the shoulders** (17.69 in the shell model). This replaces the assumed 25 mm (28 mm before that). Cross-check: SummerCart64's own USB-C opening spans 25.8 to 39.2 mm above the shoulders, 8.1 mm above this surface, and that port is made to be used while the cartridge sits in the console.

Not measured: the shape of the top surface around the hole and how far a part wider than the hole can come down before it meets the console. The shell starts to widen toward its cap 26 mm above the surface (40 mm before the board was shortened on 2026-10-01; `docs/design/v2-shell.md`).

## SummerCart64 shell screw posts (measured on its STEP, 2026-10-01)

Measured on `references/downloads/summercart64/hw/shell/injection mold/sc64_shell.stp` at its two mounting holes, in our frame (board mid-plane at z = 0, board faces at -0.6 and +0.6):

| Feature | Value (mm) |
|---|---|
| Label-side post | 5.0 diameter, from the inside of the wall (z -6.4) to the board's front face (z -0.6) |
| Hole in it | 2.5 diameter, blind, the full 5.8 length |
| Back post | starts at the board's back face (z +0.6); hole tapering from 3.25 to about 2.7 |
| Screw head seat | flat ring at z 3.1, 2.5 above the board |
| Head well | 5.57 at the seat widening to 5.83, open to the back of the shell |

So in SummerCart64 the board is clamped between the two post ends and the screw head sits deep in a well, as on a Nintendo cartridge. Its build guide gives M2 x 10 and M2 x 8 screws for its 3D-printed shell ([docs/06_build_guide.md](https://github.com/Polprzewodnikowy/SummerCart64/blob/main/docs/06_build_guide.md), read 2026-10-01). The 2.5 mm hole of the injection-mould model would need a screw of about 3 mm, which cannot pass a 2.5 mm board hole, so the SN64 shell keeps the shape of these posts and sizes the holes for M2 (assumed values in `docs/design/v2-shell.md`).
