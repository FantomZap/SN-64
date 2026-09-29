# Downloaded design starting points

The collection is intended for direct reuse and adaptation. Upstream downloads live locally under `references/downloads/`; they are ignored by Git, while source URLs, hashes and our measurements are retained. Downloading an upstream design does not select all its components for SN 64.

| Part of SN 64 | Reuse starting point | Local folder |
|---|---|---|
| SNES FPGA logic | MiSTer SNES CPU/PPU/APU and timing implementation | `downloads/fpga/SNES_MiSTer-c61bfd45171c62000417333cd4679890bcd091a6/` |
| SNES motherboard wiring and footprints | OpenSFC SHVC-CPU-01 Rev A KiCad project and libraries | `downloads/fpga/OpenSFC-6574450b1a4594b2aae436cf23869b0fb5808ce8/` |
| SNES electrical interface, regulator/audio examples, CIC | sd2snes Rev F schematics, PCB, libraries and SuperCIC | `downloads/fpga/sd2snes-cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/` |
| Female SNES socket and adapter layout | sanni/cartreader footprint and SNES adapter KiCad project | `downloads/sanni/` |
| N64/M64 lower cartridge edge, host circuitry and shell | SummerCart64 PCB, schematic, STEP and STL shell files | `downloads/summercart64/` |
| M64 host-side cross-check and surrounding mechanics | Official cartridge/mainboard schematics, assembly drawings and cartridge/door/eject CAD | `downloads/m64/` |
| Alternative standalone SNES FPGA integration | SNESTang source archive, HDMI/memory design notes and board constraints | `downloads/snestang/` |

Read the [SNES reuse map](../docs/research/reusable-designs.md), [dimension sheet](../docs/dimensions.md) and [M64 file index](../docs/research/m64-reference-files.md) for exact roles and source links.

## SNESTang alternative

[SNESTang](https://github.com/nand2mario/snestang/tree/5f0ef193145f67bded7f73f2c477ac8da4d85f7e) is an existing port of the SNES core to Sipeed Tang boards. Its working board integration, HDMI path and memory controller are useful alternatives to porting the MiSTer wrapper directly. It loads ROMs from microSD, so a physical cartridge interface is still adaptation work. Its [design notes](https://github.com/nand2mario/snestang/blob/5f0ef193145f67bded7f73f2c477ac8da4d85f7e/doc/design.md) discuss clock changes for HDMI synchronization; those cannot be copied blindly into a physical-cartridge timing design. This is a candidate, not a final FPGA selection.

The board vendor publishes [Tang Console schematics, BOM and mechanical resources](https://wiki.sipeed.com/hardware/en/tang/tang-console/mega-console.html#Hardware-Resources). Those board-resource links were located; the vendor files themselves have not been downloaded in this collection. SNESTang's source archive, README, license and design notes were downloaded and hashed in [its manifest](snestang-manifest.json).

## Provenance and practical outputs

- [SummerCart64 and sanni manifest](source-manifest.json): pinned commits, download URLs, byte counts and SHA-256.
- [SNESTang manifest](snestang-manifest.json): pinned source archive and documentation.
- Other download folders contain their own `manifest.json` with provenance and checksums; the research notes identify pinned upstream versions and source notices.
- [Extracted dimensions](measurements/): full N64 and SNES pad-coordinate CSVs, hole positions, STEP validity and shell bounds.
- [Extraction script](extract_dimensions.py): verifies the upstream hashes before reading the KiCad geometry.
- `.local/research/exports/`: locally generated schematic PDFs, N64 board STEP and a FreeCAD shell reference document.

OpenSFC is a motherboard reproduction using original custom chips. sd2snes is a cartridge, and SummerCart64 is an N64 cartridge. Their useful circuitry is reused according to its role; the SNES motherboard behavior comes from the SNES FPGA core.
