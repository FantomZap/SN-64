# Sources and retained notices

## Sanni SNES female socket footprint

- Upstream: [sanni/cartreader](https://github.com/sanni/cartreader).
- Source: [`hardware/footprints/!OSCR.pretty/SNES Slot.kicad_mod`](https://github.com/sanni/cartreader/blob/060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d/hardware/footprints/%21OSCR.pretty/SNES%20Slot.kicad_mod).
- Commit: `060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d`.
- Hardware license: CC BY 4.0, retained as [Sanni-CC-BY-4.0.txt](licenses/Sanni-CC-BY-4.0.txt), from upstream `hardware/LICENSE.txt`.
- Local asset: `libraries/SN64.pretty/SNES Slot.kicad_mod`, an unmodified, byte-identical copy. Credit belongs to the upstream authors/contributors. No endorsement is implied.

## SummerCart64 N64 edge footprint

- Upstream: [SummerCart64](https://summercart64.dev), designed by Mateusz Faderewski.
- Source: connector `J_N1` in [`hw/pcb/sc64v2.kicad_pcb`](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_pcb), revision 2.1a.
- Commit: `a1e7996d2cbece686820a5c785029c68514f17b0`.
- Hardware license: CERN-OHL-S-2.0, retained as [SummerCart64-CERN-OHL-S-2.0.txt](licenses/SummerCart64-CERN-OHL-S-2.0.txt), from upstream `hw/pcb/LICENSE`. This is separate from the repository's software GPL license.
- Local derivative: `libraries/SN64.pretty/N64_Edge_SC64_Reference.kicad_mod`, under the same hardware license. Extracted on 2026-09-28 using KiCad 10: reference, value and library identifier renamed; footprint origin normalized to the source connector origin; pad net assignments removed. Original pad geometry, side assignments and footprint graphics retained, including six `Edge.Cuts` segments forming an open lower connector profile. The complete PCB perimeter and mounting holes are not included. Extend the retained profile during layout without duplicating its cuts.
- Retain this notice and the upstream license with further adaptations. The published source location for this project is [FantomZap/SN-64](https://github.com/FantomZap/SN-64); this local draft may precede publication there. No endorsement by the upstream author is implied.

## Pin identities and circuit research

The newly drawn connector symbols use the checked factual pin identities in `interfaces/*.csv`. The [SNES notes](../../docs/design/snes-interface-notes.md), [N64 notes](../../docs/design/n64-interface-notes.md), and [translation review](../../docs/design/translation-reuse-review.md) record the source revisions and interpretation. OpenSFC, sd2snes, SummerCart64, Sanni and ModRetro remain third-party projects; the SN 64 name does not replace their attribution.

No M64 CAD, SNES core implementation, sd2snes circuit sheet or FPGA implementation is copied into these connector symbols. Their use as research references does not establish that all associated files have the same license. Preserve the applicable notices as implementation blocks are brought into the design.

## SummerCart64 USB circuit and JAE USB-C footprint

The USB support block in `usb-programmer.kicad_sch` is adapted from SummerCart64's [native schematic](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_sch) at the same pinned revision above. Credit: SummerCart64, designed by Mateusz Faderewski, and its contributors. Retain its [CERN-OHL-S-2.0 hardware license](licenses/SummerCart64-CERN-OHL-S-2.0.txt) with the derivative circuit and extracted footprint; the repository's software license is separate.

Six symbols were copied from that schematic's embedded library: `Connector:USB_C_Receptacle_USB2.0`, `Device:R`, `Device:C`, `Device:L`, `Interface_USB:FT232H`, and `Memory_EEPROM:93AAxxBT-xOT`. They are now under the local `SN64_USB` namespace. The original KiCad library identifiers are recorded for attribution; the source is the pinned embedded content, not an assumed match to today's installed libraries. FT232H physical pins **44 EECLK and 45 EECS** had their electrical types corrected from input to output against FTDI datasheet table 3.3. Pin numbers and symbol geometry were retained. Both SummerCart64 and KiCad library notices are retained.

`libraries/SN64_USB.pretty/USB_C_JAE_DX07S016JA3R1500.kicad_mod` comes from source PCB **J1**. Its source identifier says `USB_C_Receptacle_JAE_DX07S016JA1R1500`, but its assigned part is **DX07S016JA3R1500**. The [mechanical evidence](../../docs/design/usb-connector-mechanics.md) compares native lands with JAE drawing SJ122205 revision 2 for JA3; it does not infer interchangeability from the names. Extraction normalized position/orientation, renamed the identifier/reference/value, removed pad nets and both source 3D-model links, and retained pad/drill geometry and graphics. The local copy uses LF line endings. No manufacturer 3D model is redistributed here.

Circuit changes from SummerCart64 are deliberate: MPSSE JTAG replaces its FT1248 path; the optional EEPROM is DNP; a 12 MHz Abracon crystal and provisional load capacitors replace the powered oscillator; USBLC6-2SC6 arrays add data/CC protection; a separate AP2112K-3.3 supplies the USB bridge; and a new SN74AXC4T774PW translator uses an ACBUS6-controlled, pulled-up `/OE`, with a target-side JTAG header and damping/bias resistors. SummerCart64's power mux, FT1248 EEPROM template and initial MCU-loading path were not copied. These changes still require PCB layout and hardware validation. See the [programming architecture](../../docs/design/usb-programming-architecture.md).

## KiCad USB library copies and new TI symbol

Credit for the standard library data belongs to **the KiCad library contributors**. The source is the installed **KiCad 10.0.6 library snapshot**; its Git revision was not established. The [USB provenance manifest](libraries/usb-provenance.json) records actual source and local SHA-256 hashes, sizes, paths and transformations, rather than assigning an unverified library commit.

Five symbols were copied from installed libraries: `Connector_Generic:Conn_01x06`, `Device:Crystal_GND24`, `Power_Protection:USBLC6-2SC6`, `Regulator_Linear:AP2112K-3.3`, and `power:PWR_FLAG`. Their identifiers were changed to `SN64_USB`; inherited symbols were resolved into standalone definitions. Nine standard footprints were copied from the installed Capacitor_SMD, Crystal, Inductor_SMD, Package_QFP, Connector_PinHeader_2.54mm, Resistor_SMD, Package_TO_SOT_SMD and Package_SO libraries. Only their CRLF line endings were normalized to LF; geometry and existing model references remain unchanged. The manifest enumerates every file.

The KiCad library copies use **CC-BY-SA 4.0 with the KiCad library exception**. The original official repository notices are retained byte-for-byte as [KiCad-symbols-LICENSE.md](licenses/KiCad-symbols-LICENSE.md) and [KiCad-footprints-LICENSE.md](licenses/KiCad-footprints-LICENSE.md); each includes the license link, exception and warranty notice. [KiCad's official explanation](https://www.kicad.org/libraries/license/) distinguishes use in electronic designs from redistribution of library collections. Retain these notices and attribution when redistributing this local collection. The pinned commits in the manifest identify the downloaded license documents only, not the installed library snapshot.

`SN64_USB:SN74AXC4T774PW` is newly drawn from the factual 16-pin PW pinout in [Texas Instruments' SN74AXC4T774 datasheet](https://www.ti.com/lit/ds/symlink/sn74axc4t774.pdf), revision C. It does not copy manufacturer artwork or an existing TI library symbol. Datasheets and the distributor-hosted JAE drawing are research references; no license for redistributing manufacturer CAD or documents is inferred from access to them. These asset-specific notices do not assign a blanket license to unrelated project material.

## ULX3S HDMI (GPDI) TMDS coupling
- Upstream: [emard/ulx3s](https://github.com/emard/ulx3s), sheet [`gpdi.sch`](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/gpdi.sch), commit `6a92cec6b177191c5b0f80e260013a1f8ec147dd`, SHA-256 `2ff8d987b7f167ec0c0f7396bb11f8040d79a0289ab2d4a73ebde4b0f5b1164d`.
- Reused as a circuit fact only in `av-clock.kicad_sch`: one 22 nF series capacitor per TMDS line (ULX3S C38-C45) between the FPGA's single-ended LVCMOS33D pins and the connector, and the connector part 10029449-111RLF. No ULX3S symbols, layout, artwork or silkscreen are imported.
- License: MIT-style with an additional logo condition (LICENSE.md SHA-256 `cdaaa3f0c2d1dbb538844077fd7a1d9d43c890d0745b20d8aa0717b583d6af9f`). Retain the notice if layout or artwork is ever adapted.
- OpenSFC SHVC-CPU-01 (R95/R96 200 ohm cartridge-audio load) and sd2snes Rev F (CS4344 output network) are cited as level/impedance evidence only; nothing is copied.

## Other round-3 reuse (facts only, no files copied)
- FPGA sheet: ULX3S `6a92cec6` flash pull values and HDMI ball pairs; SummerCart64 `a1e7996d` N64 pad treatment (no series resistors).
- Power sheet: the TLV62569 FPGA-rail stages follow the ULX3S rev 1.0.8 `power.sch` topology at commit `6a92cec` (MIT; no files copied).

## OpenSFC cartridge-slot geometry (socket board)
- Upstream: [starlightk7/OpenSFC](https://github.com/starlightk7/OpenSFC), `Common/libraries/OpenSFC.pretty/CartSlot.kicad_mod`, commit `6574450b1a4594b2aae436cf23869b0fb5808ce8`, SHA-256 `1f9b60ddd99989e69f4395c12e75292c88869fa6cf3515bcd9eee5485d48b5a0`.
- Reused as geometry in `libraries/SN64.pretty/SNES_Slot_Console_7mm.kicad_mod` (written by `tools/split_socket_board.py`): pad positions (2.5 mm pitch, 7.5 mm gaps, rows 7.0 mm apart), pad/drill sizes, body outline and the two Ø3.2 mm ear holes 95 mm apart. No upstream file is copied byte-for-byte.
- License: CERN-OHL-S-2.0 (retained as [licenses/OpenSFC-LICENSE.txt](licenses/OpenSFC-LICENSE.txt)). SN64 hardware is published under a compatible strongly-reciprocal licence; keep this notice with the footprint.
- The sd2snes Rev F board (mrehkopf/sd2snes, commit `cf7e21d7`) and qwertymodo's kicad-snn-cpu-01 (commit `a0018661`, CERN-OHL-S-2.0) were read for dimensions only (docs/dimensions.md); nothing copied.

