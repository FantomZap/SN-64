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
