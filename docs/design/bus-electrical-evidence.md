# SNES cartridge data-bus evidence

Research snapshot: 2026-09-29. This records source evidence for the physical cartridge bridge. It does not establish measured SN64 socket timing or electrical qualification.

## Direct motherboard evidence

The pinned [OpenSFC SHVC-CPU-01 Rev A front schematic](https://github.com/starlightk7/OpenSFC/blob/6574450b1a4594b2aae436cf23869b0fb5808ce8/Motherboards/SHVC-CPU-01/Rev%20A/SHVC-CPU-01-Front.kicad_sch), commit `6574450b1a4594b2aae436cf23869b0fb5808ce8`, connects all eight `C.D0` through `C.D7` nets directly between the cartridge, S-CPU, S-WRAM, both PPUs, APU connector and expansion connector. The local KiCad XML export at `.local/interface-research/opensfc.xml` in the original project was inspected. For example, `C.D0` connects P1.19, U1.60, U2.21, U3.15, U6.60, P5.7 and P6.11; U6 is S-WRAM. The remaining seven data nets follow the same topology. There is no intervening A/B data-bus switch or cartridge isolation buffer.

This establishes one shared physical data bus with separate A/B addresses and strobes. Therefore an ordinary S-WRAM read drives the current RAM byte onto the cartridge data contacts, regardless of whether the CPU or another peripheral consumes it. A cartridge-source DMA byte already occupies the same wires as the B-side destination; an extra console data driver would conflict with it. This is a topology inference from primary design material, not a socket measurement. OpenSFC is a reproduction motherboard; direct continuity and waveform checks on an original console remain physical acceptance work.

The [machine-readable connectivity extract](../research/snes-data-bus-net-evidence.json) preserves every node on all eight nets, including their test points, component values, the netlist hash, original schematic hashes and export-tool identity. All eight nets contain the seven functional endpoints listed above plus one test point. This is a factual source extract, not a replacement SN64 circuit or a physical measurement.

## Read value is not necessarily external drive

| Read class | Evidence and bridge consequence |
|---|---|
| A-side WRAM, including low mirrors | S-WRAM shares every data contact with the cartridge. Export its current byte during the qualified read window; all eight data bits belong to the RAM responder. |
| B-side WRAM data port, PA=`80` | The same S-WRAM data pins respond. The upstream read predicate additionally requires A-side WRAM deselected. PA=`81` through `83` are address-write registers, not RAM-data read responders. |
| APU ports, PA=`40` through `7F` | The APU connector shares all eight cartridge data nets. The four port values are mirrored through this range; selected port data is an external bus response. Read-window timing remains to be characterized. |
| PPU readable registers | PPU data pins share the cartridge bus. Distinguish PPU-internal retained bits from undriven cartridge bits; a semantic register bit mask is not an external output-enable mask. Exact responder decoding must include the documented read aliases and exclude truly open-bus reads. |
| Ordinary CPU reads of 5A22 internal registers | The motherboard schematic cannot reveal the 5A22's internal output-enable behavior. The existing proposal to drive every internal CPU-register result onto the cartridge bus is unsupported by this audit and conflicts with the documented separation discussed below. Keep CPU input selection distinct from socket drive. |
| DMA using 5A22 internal registers | Requires separate evidence and tests. Do not infer its behavior from ordinary CPU reads or general peripheral DMA. |

[Anomie's original OpenBus document](https://raw.githubusercontent.com/gilligan/snesdev/master/docs/ob-wrap.txt), revision 1126, describes separate retained read values inside PPU1 and PPU2. Its discussion of CPU IO cycles concerns instruction-internal cycles; it is not proof of electrical behavior for reads of memory-mapped CPU registers.

The [SNESdev Open bus page](https://snes.nesdev.org/wiki/Open_bus) (retrieved revision `1174`) explicitly distinguishes CPU-internal register reads from the external bus, and describes selected PPU reads as driving their complete internal output byte externally. This is a secondary technical reference and a reason to reject the blanket CPU-register export assumption, not a replacement for primary socket captures. No first-hand CPU-register socket capture or chip output-enable specification was located in this bounded audit.

[Nocash Fullsnes](https://problemkaputt.de/fullsnes.htm#snesunpredictablethings), under “Open Bus for DMA,” reports that A-side DMA reads from `$4210–$421F` work, while other CPU-I/O classes differ. That report makes CPU-register DMA a separate unresolved class for this bridge. It must not silently inherit a general CPU-read drive rule. This audit did not reproduce those hardware tests.

## Upstream RTL is a functional source, not electrical evidence

Pinned SNESTang [SNES.v](https://github.com/nand2mario/snestang/blob/5f0ef193145f67bded7f73f2c477ac8da4d85f7e/src/SNES.v#L279) selects B-bus read data or `CPU_DO` for its cartridge output. [cpu.v](https://github.com/nand2mario/snestang/blob/5f0ef193145f67bded7f73f2c477ac8da4d85f7e/src/cpu.v#L750) assigns `CPU_DO` from MDR; its CPU-register read mux feeds the CPU internally. This cannot prove what a genuine 5A22 drives externally.

[swram.v](https://github.com/nand2mario/snestang/blob/5f0ef193145f67bded7f73f2c477ac8da4d85f7e/src/swram.v#L68) exposes current `RAM_Q`, with read qualification at lines 79–87. `RAM_OE_N` is forced low when `ENABLE` is low, so it must not be reused as a socket drive permit without explicit reset/enable qualification. The registered memory-read scheduling signal `RAM_RD_N` and actual read-window `RAM_OE_N` have different purposes.

The WRAM output correction is supported by the shared-net evidence. It is only a data-path correction: no translator OE, bit-level tri-state behavior, turnaround delay, cartridge contention measurement, open-bus decay or hardware timing margin is established by it. Further implementation should attach ownership to a verified responder and cycle class rather than expose the entire internal CPU input mux.
