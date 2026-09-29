# Official M64 reference files

Downloaded the relevant files linked by ModRetro's [M64 Open Source Files page](https://support.modretro.com/en_us/articles/m64-open-source-files-ByrpukdUGg). The published index reports an update on 2026-08-13. These are existing cartridge/host designs to reuse and cross-check; the SN 64 lower interface remains the same standard N64 cartridge interface for both hosts.

The [download manifest](../../references/downloads/m64/manifest.json) records each exact source URL, download time, byte count, SHA256, observed notices, and PDF page count. An [unchanged copy of the official index](../../references/downloads/m64/official-source-index.md) preserves the association between the files and ModRetro's labels.

## Downloaded files

| Official description | Local file | Bytes | Useful content |
|---|---|---:|---|
| M64 cartridge schematic | [M64_CART_SCH.pdf](../../references/downloads/m64/M64_CART_SCH.pdf) | 1,744,471 | Connector pin/net map, FPGA cartridge endpoint, flash/FRAM, clock, power and JTAG reference |
| M64 cartridge assembly drawing | [M64_CART_ASY.pdf](../../references/downloads/m64/M64_CART_ASY.pdf) | 156,646 | Top/bottom board views, connector placement and two mounting holes |
| M64 mainboard schematic | [M64_MLB_SCH.pdf](../../references/downloads/m64/M64_MLB_SCH.pdf) | 11,211,954 | Host cartridge connector and FPGA connections, cartridge power and host A/V circuitry |
| M64 mainboard assembly drawing | [M64_MLB_ASY.pdf](../../references/downloads/m64/M64_MLB_ASY.pdf) | 831,370 | Mainboard placement and connector-position reference |
| Cartridge front enclosure | [100-0442-01_64_CART_BODY_FRONT_GENERIC.x_t](../../references/downloads/m64/100-0442-01_64_CART_BODY_FRONT_GENERIC.x_t) | 2,017,186 | Native solid geometry for the front cartridge shell |
| Cartridge back enclosure | [100-0443-01_64_CART_BODY_BACK_GENERIC.x_t](../../references/downloads/m64/100-0443-01_64_CART_BODY_BACK_GENERIC.x_t) | 2,184,384 | Native solid geometry for the back cartridge shell |
| Console front door | [100-0523-01_M64_DOOR_FRONT.x_t](../../references/downloads/m64/100-0523-01_M64_DOOR_FRONT.x_t) | 678,778 | Front-door shape and interface geometry |
| Console back door | [100-0526-01_M64_DOOR_BACK.x_t](../../references/downloads/m64/100-0526-01_M64_DOOR_BACK.x_t) | 920,987 | Back-door shape and interface geometry |
| Cartridge eject button | [100-0530-01_M64_CART_EJECT_BUTTON.x_t](../../references/downloads/m64/100-0530-01_M64_CART_EJECT_BUTTON.x_t) | 2,979,797 | Eject-button solid geometry |

## Where to start

PDF page numbers here mean the physical PDF page, starting at 1; some printed sheet counts differ from the actual PDF length.

- **Cartridge schematic, page 1:** `Connectors`, J1 `M64_Cartridge_B2B`, gives the 50-contact pin/net map. Page 2 contains flash/FRAM circuitry; page 3 the cartridge FPGA; page 4 power, JTAG, oscillator, and `MTH1`/`MTH2`. The file has 6 PDF pages.
- **Mainboard schematic, page 5:** `N64_CART_CTRL`, J11 `M64_Cartridge_Connector`, gives the host side of that interface. Page 13, `FPGA_BANK85_86_CART`, follows cartridge nets into the host FPGA. The file has 31 PDF pages.
- **Cartridge assembly drawing, page 1:** identifies `MTH1`, `MTH2`, and J1, with top and bottom views labelled `Scale 1:1`. This is useful for matching hole/connector locations against the cartridge shell and the existing N64 reference board. It is not a dimensioned drill drawing; no numeric hole diameter or centre spacing has been certified from it here.
- **Mainboard assembly drawing:** 2 PDF pages for placement reference. It does not supply a complete positioned mechanical model of the console and eject assembly.

The cartridge schematic is a concrete starting reference for a working N64-style cartridge interface. Its FPGA/memory choices are reference components, not an established capacity or timing solution for the SNES motherboard core.

## Mechanical extraction

All five `.x_t` files identify themselves as **Parasolid text**, exported by SolidWorks 2025 using Parasolid 36.1. They are original solid-model files, not STL meshes.

With a compatible Parasolid reader or a verified conversion to STEP, we can measure the cartridge envelope, shell opening, internal locating features, screw bosses/holes and board supports that exist in the front/back models. The door and eject parts provide geometry to compare against the adapter's lower body. Their installed positions, rotation axes and travel must still be established before claiming a complete clearance check.

No Parasolid importer or conversion has been verified in this collection step. Keep these originals unchanged; use a Parasolid-capable CAD/conversion route to produce STEP, then check units and several reference dimensions before opening the converted solids in FreeCAD. Merely renaming `.x_t` to `.step` does not convert it. The source index does not provide a complete console enclosure/positioned assembly in this download set, so these parts alone do not establish the full M64 cartridge-bay clearance envelope.

## Notices and integrity

The schematic title blocks display **Copyright 2026 ModRetro Inc.** No explicit reuse license was found in the inspected official index, extracted PDF text, or CAD text. The page's “Open Source Files” title is recorded as provenance, not treated as a particular license grant. Preserve the original notices and resolve applicable reuse/distribution terms before incorporating or redistributing modified reference assets.

All nine downloaded files have SHA256 hashes and exact sizes in the manifest. The PDFs were opened successfully with a PDF parser and their text/page counts inspected. The CAD headers were inspected; the solids have not yet been imported, dimensioned or fit-tested. No SN 64 electrical or mechanical implementation is claimed by this collection.
