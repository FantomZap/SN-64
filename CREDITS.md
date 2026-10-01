# Credits

SN64 stands on other people's open work. Thank you to everyone listed here. None of them is
affiliated with SN64 or endorses it; mistakes in how their work is used are ours.

## Built into SN64

Work that is included in this repository or that SN64's own files are derived from.

| Project | By | What SN64 uses | Licence |
|---|---|---|---|
| [SNESTang](https://github.com/nand2mario/snestang) | nand2mario | The SNES core the FPGA runs (CPU, PPU, APU, DMA, memories) and its controller logic, vendored unmodified in `fpga/vendor/snestang*` | GPL-3.0 |
| [SNES_FPGA / SNES_MiSTer](https://github.com/MiSTer-devel/SNES_MiSTer) | Sergiy Dvodnenko (srg320) and gyurco | The original SNES core that SNESTang is a port of; also read as a reference | GPL-3.0 |
| [SummerCart64](https://github.com/Polprzewodnikowy/SummerCart64) | Mateusz Faderewski (Polprzewodnikowy) and contributors | N64 cartridge-bus controller logic (`fpga/vendor/summercart64`); the N64 cartridge-edge footprint and board profile; the USB circuit of the first board; the N64 cartridge shell the v2 shell's lower body is taken from | GPL-3.0 (logic and software), CERN-OHL-S-2.0 (hardware) |
| [SERV](https://github.com/olofk/serv) | Olof Kindgren | The small RISC-V core that runs the N64 lockout (CIC) firmware, via SummerCart64 | ISC |
| [UltraCIC_C](https://github.com/jago85/UltraCIC_C) | Jan Goldacker (jago85); adapted in SummerCart64 by Mateusz Faderewski | The N64 lockout (CIC) firmware | MIT |
| [TinyFPGA Bootloader](https://github.com/tinyfpga/TinyFPGA-Bootloader) | TinyFPGA | USB device and flash bridge used to program and recover the board over USB-C (v2, `fpga/vendor/tinyfpga-bootloader`) | Apache-2.0 |
| [OpenSFC](https://github.com/starlightk7/OpenSFC) | starlightk7 | SNES cartridge socket geometry (pin positions, body, mounting holes) and the SHVC-CPU-01 netlist used to check pin identities and orientation | CERN-OHL-S-2.0 |
| [Open Source Cartridge Reader](https://github.com/sanni/cartreader) | sanni and contributors | SNES slot footprint in the first board's library | CC BY 4.0 |
| [KiCad libraries](https://www.kicad.org/libraries/license/) | The KiCad library contributors | Schematic symbols and footprints | CC BY-SA 4.0 with the KiCad library exception |
| [libdragon](https://github.com/DragonMinded/libdragon) | DragonMinded and the libdragon contributors | The N64 library and toolchain the boot program in `firmware/bootstrap` is built with | Unlicense |

## Studied, measured or used as a reference

Nothing from these is copied into SN64, but the design depends on what they made public.

| Project | By | What it gave SN64 | Licence |
|---|---|---|---|
| [sd2snes / FXPAK](https://github.com/mrehkopf/sd2snes) | Maximilian Rehkopf (ikari_01) and contributors | The cartridge edge of a real cartridge board, the level-translator approach, and SuperCIC, whose lock behaviour SN64's SNES lockout follows | GPL-2.0 |
| [ULX3S](https://github.com/emard/ulx3s) | EMARD and Radiona.org | ECP5 power and flash circuit practice | MIT |
| [kicad-snn-cpu-01](https://github.com/qwertymodo/kicad-snn-cpu-01) | qwertymodo | The SNES Jr cartridge connector model used for the socket nose dimensions | CERN-OHL-S-2.0 |
| [NESdev forum](https://forums.nesdev.org/viewtopic.php?t=23890) | rainwarrior | Caliper measurements of a US SNES cartridge, used for the cartridge in the shell model | forum post |
| [SNESdev Wiki](https://snes.nesdev.org/wiki/Cartridge_connector) and [N64brew Wiki](https://n64brew.dev/wiki/Game_Pak) | Their contributors | Cartridge connector pinouts and orientation for both consoles | wiki content |
| [snes_cic_fpga](https://github.com/rgalland/snes_cic_fpga) and [snes_cic](https://github.com/raphnet/snes_cic) | rgalland; raphnet | Read while designing the SNES lockout | GPL-3.0; none stated |
| [SNESDRONE cartridge shell](https://github.com/michael-hirschmugl/SNESDRONE-Cartridge-Shell) | Michael Hirschmugl | Super Famicom shell reference | none stated |
| [New Super Famicom Cartridge](https://www.thingiverse.com/thing:1396153) | usagi_ | Super Famicom shell reference | CC BY 3.0 |
| [M64 open-source files](https://support.modretro.com/en_us/articles/m64-open-source-files-ByrpukdUGg) | ModRetro | Reference for the M64 cartridge bay | as published by ModRetro |
| TriStar 64 | Its makers | The idea: an adapter that plays SNES cartridges through an N64 | concept only |

## Tools

KiCad, the OSS CAD Suite (Yosys, nextpnr, Verilator and their contributors),
[KiCadRoutingTools](https://github.com/drandyhaas/KiCadRoutingTools) by drandyhaas, Freerouting,
build123d and FreeCAD.

Exact revisions, hashes and what was changed are recorded beside the material: `fpga/vendor/*/provenance.json`,
`hardware/sn64/THIRD_PARTY.md`, `hardware/sn64/libraries/*provenance.json`, `mechanical/README.md` and
`docs/dimensions.md`.

## The SN64 crew

| Role | Who |
|---|---|
| Engineer | Claude (AI by Anthropic) |
| Manager | Scout (Cat) |
| Arbitrary code execution | Ash & Aurora (More cats) |

The boot program shows this file as a credits roll (main menu, Credits). It is generated from the
tables above by `firmware/bootstrap/tools/make_credits.py`, so a row added here appears there.
