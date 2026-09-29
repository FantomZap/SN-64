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
