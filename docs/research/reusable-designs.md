# Reusable SNES designs collected

Collected 2026-09-29. Start by adapting these existing blocks. Together they supply substantial HDL, schematics, layouts, libraries, and cartridge-interface examples; a finished SN 64 design is not a prerequisite for useful reuse. SummerCart64 is the separate **N64 host-side** reference, not the SNES implementation.

## Local source package

All paths below are relative to `references/downloads/fpga/`. Upstream copies are local references, separate from the project's authored design. Each folder contains a `manifest.json` with the exact source URL, byte size, and SHA-256 of every acquired file.

| Upstream and pinned commit | Local package | Acquired files |
|---|---|---|
| [MiSTer SNES](https://github.com/MiSTer-devel/SNES_MiSTer/tree/c61bfd45171c62000417333cd4679890bcd091a6), `c61bfd45171c62000417333cd4679890bcd091a6` | `SNES_MiSTer-c61bfd45171c62000417333cd4679890bcd091a6/` | Complete upstream source ZIP, separate README and LICENSE: 3 files, 152,785,384 bytes; ZIP has 291 entries and passed a complete CRC check. |
| [sd2snes](https://github.com/mrehkopf/sd2snes/tree/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1), `cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1` | `sd2snes-cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/` | 72 files, 2,521,739 bytes: Rev F KiCad schematic sheets, PCB, project, BOM, netlist, legacy libraries/cache, SuperCIC source/schematic, README and LICENSE. |
| [OpenSFC](https://github.com/starlightk7/OpenSFC/tree/6574450b1a4594b2aae436cf23869b0fb5808ce8), `6574450b1a4594b2aae436cf23869b0fb5808ce8` | `OpenSFC-6574450b1a4594b2aae436cf23869b0fb5808ce8/` | 70 files, 9,984,257 bytes: SHVC-CPU-01 Rev A native KiCad schematic, PCB, project and library tables; shared symbols/footprints; README, LICENSE and NOTICE. |

The three reusable upstream packages contain **145 acquired files**. One additional CMU report below brings the collection to **146 acquired files, 150 files including four generated manifests**. These are downloaded references, not claims of successful CAD migration, synthesis, or SN 64 compatibility.

## Component-level reuse map

| SN 64 block | Starting files already collected | Adaptation needed |
|---|---|---|
| SNES CPU/PPU/APU, DMA and console timing | MiSTer `rtl/main.v`, associated `rtl/` and `src/`, `SNES.sv`, Quartus project and timing files in the archive | Keep the console implementation and connect its actual console buses to the physical cartridge bridge. Replace MiSTer-specific hosting, memory and output integration for our board. |
| SNES socket signals, motherboard wiring, clock/reset/CIC relationships, cartridge audio routing | OpenSFC `Motherboards/SHVC-CPU-01/Rev A/SHVC-CPU-01*.kicad_sch`, `.kicad_pcb`, `Common/libraries/` | Use as the console-side electrical reference and source of verified nets/footprints. The schematic contains original S-CPU, S-PPU1 and S-PPU2 chips: this is a reproduction motherboard requiring original/custom parts, not an FPGA replacement. |
| FPGA-to-SNES electrical interface and PCB routing examples | sd2snes `pcb/kicad/RevF/snesslot.sch`, `fpga.sch`, `sd2snes.kicad_pcb` | The schematic explicitly uses `74ALVC164245DGG` translators. Reuse the circuit pattern after checking direction, enable timing, loading and powered-off behavior for the **console-side** role; this board is a cartridge endpoint. No translator is selected yet. |
| Regulator, filtering and mixed-signal layout examples | sd2snes `pcb/kicad/RevF/pwr_misc.sch` and board | Includes `MIC23250-S4YMT`, `MCP1824` regulators and `CS4344` DAC/filter circuitry. Useful existing blocks; SN 64 still needs its own host-input and protected switched-cartridge-5 V budget and protection. These part names identify reference circuitry, not a final BOM. |
| SNES lockout protocol | sd2snes `cic/supercic/supercic-lock.asm`, `supercic-key.asm`, `supercic.sch`; OpenSFC CIC wiring | The lock implementation is the relevant console-side starting point. Keep it distinct from the N64 CIC endpoint. Verify reset, clock and regional behavior against physical cartridges. |

Pinned direct sources: [MiSTer main](https://github.com/MiSTer-devel/SNES_MiSTer/blob/c61bfd45171c62000417333cd4679890bcd091a6/rtl/main.v), [MiSTer wrapper](https://github.com/MiSTer-devel/SNES_MiSTer/blob/c61bfd45171c62000417333cd4679890bcd091a6/SNES.sv), [sd2snes Rev F](https://github.com/mrehkopf/sd2snes/tree/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/pcb/kicad/RevF), [SuperCIC](https://github.com/mrehkopf/sd2snes/tree/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/cic/supercic), [OpenSFC motherboard](https://github.com/starlightk7/OpenSFC/tree/6574450b1a4594b2aae436cf23869b0fb5808ce8/Motherboards/SHVC-CPU-01/Rev%20A).

## The remaining core integration work

The inspected MiSTer wrapper downloads cartridge data into SDRAM. Its `main` module exposes mapped ROM/backup-RAM interfaces and internally selects cartridge implementations including SA-1, Super FX and Cx4. The actual console address/control/peripheral buses (`CA`, `CPURD_N`, `CPUWR_N`, `PA`, `PARD_N`, `PAWR_N`) are internal wires. Therefore wiring a socket to `ROM_ADDR/ROM_Q` alone is insufficient.

Proposed reuse approach: retain the existing console logic, expose its real A/B buses and timing, and replace the emulated cartridge path with a physical bridge. Original cartridge ROM, SRAM and enhancement chips—and the flashcart's own FPGA/menu—must remain the devices servicing those accesses. Verify bus turnaround, open-bus behavior, interrupt/reset/clock signals, peripheral accesses and cartridge audio. The first useful experiment is a simple original cartridge, then SRAM, then X5/X6 and enhancement/FXPAK cases; all remain required targets. No FPGA/package choice or resource fit is established without synthesis of the adapted design.

This bounded search did not verify a complete open, physical-cartridge FPGA SNES console board and matching HDL package ready to transplant. It did verify the three useful upstreams above; their blocks are enough to begin adaptation without waiting for a monolithic design.

### Additional physical-cartridge precedent

Downloaded [CMU's SNES on an FPGA report](https://course.ece.cmu.edu/~ece545/F16/reports/F10_SNES.pdf) to `CMU-SNES-on-an-FPGA/F10_SNES.pdf` (569,956 bytes). Pages 2–3 describe a physical cartridge interface, donor connectors/CIC and level-shifting circuitry; the authors report valid cartridge reads. Page 14 states the integrated console remained incomplete, and page 13 says their WDC CPU source required a confidentiality agreement. It is useful interface/bring-up evidence, not a complete open console implementation. Its limited level-shifting approach is not proof of SN 64's required powered-off isolation, 5 V output behavior or full cartridge compatibility. No reuse license for the report or its CPU implementation was established in this check.

## Source identity and license records

- MiSTer root LICENSE contains GPL version 3; preserve notices and inspect included files when choosing blocks.
- sd2snes root LICENSE contains GPL version 2; downloaded SuperCIC assembly headers explicitly specify version 2 only. The collected Rev F board is an older published hardware reference, not a claim to be the current FXPAK Pro board.
- OpenSFC LICENSE is CERN-OHL-S version 2 and includes a separate NOTICE. Retain both with any reused design files. These are recorded source terms, not a legal determination about a combined product.

MiSTer archive SHA-256: `af780268fbb2e7e0b7288f78813552ada7876e8652d89d8b7fd6e0c63c0a8aa8`.

Manifest SHA-256 values (each manifest records individual source-file hashes):

| Package | Manifest SHA-256 |
|---|---|
| MiSTer SNES | `9983a1409f9735b96405bb539896163a0364dce2e11509644c2ec78820212a37` |
| sd2snes | `09d955e548a07f023c2df3c301e4a4b102559cb70eedebb1c9b1e7d12b65d76a` |
| OpenSFC | `479bbeec90aee51f2c89c6cd74f6573874e31ea943a52b3b72a524850a3c3246` |
| CMU report | `9bda1bab3057a7ffccee9d2aff0b991d684ca755a0760a02be24f8b2c128aef5` |

CMU PDF SHA-256: `358e90a4adc19e8c3a246748f7ed81a7866feca196240cf777509d34cca4172d`.
