# SNES 5 V translation: reuse review

The sd2snes Rev F bus interface is a concrete starting circuit for SN 64. Reuse its dual-supply transceiver arrangement, decoupling and provision for signal conditioning; adapt its direction and enable logic for a **console** endpoint. Sanni's SNES adapter provides connector wiring, but no FPGA voltage translator. This review does not select a final manufacturer, FPGA I/O voltage or production BOM, and does not establish timing closure.

## Circuits verified in the references

Inspected the actual [Rev F SNES interface schematic][sd-sch], [PCB pad nets][sd-pcb] and [BOM][sd-bom], all pinned to `cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1`. The stored `.net` file has an older design header, so the findings below use the schematic and PCB instead.

| Reference block | Verified circuit | Reuse in SN 64 |
|---|---|---|
| U101, U102, U103 | `74ALVC164245DGG`, TSSOP48. A supply pins 31/42 = +3.3 V; B supply pins 7/18 = +5 V. BOM names TI/NXP. | Concrete 3.3 V ↔ 5 V bus topology, subject to selecting and checking the exact manufacturer's part. A different FPGA bank voltage requires a new check. |
| U102 and U103, both octets | DIR pins 1/24 and active-low OE pins 48/25 tied to ground: fixed B→A receivers. | Reverse to A→B for the same console-generated signals; provide deliberate enable control. |
| U101 first octet | DIR1 and /OE1 grounded; receives PA0–PA5, /WR and CPU_CLK/PHI2. | Also reverse to A→B and gate enable. |
| U101 second octet | D0–D7; pin 24 `DATABUS_DIR`, pin 25 `DATABUS_/OE`, connected to FPGA U201. No pull resistor on either control net in this PCB. | Keep a separately controlled data octet; add defined startup states in our design. |
| C101–C106, C111–C116 | Twelve 100 nF bypass capacitors across the two supply domains. | Preserve local bypass provision and short return paths; size the complete power network for our board. |
| RA101/102/105–112; RA113/114 | 100 Ω arrays on many cartridge-side signals; additional 100 Ω arrays on the FPGA side of D0–D7. | Keep tunable series-component footprints. Values and placement need review for the new driving direction, trace lengths and loads. |
| RA103/RA104, C121–C128 | Data-bus ferrite arrays marked `FB`, BOM `BK32164M241-T` (Taiyo Yuden); selected control paths have 10 pF shunt capacitors. | Existing filtering precedent, not an instruction to populate identical filters. Include their delay/loading in the bus budget. |
| Q101, R103, R102 | Schematic `2N2222A`, BOM `MMBT2222A`; open-collector IRQ sink, 4.7 kΩ base resistor and 100 kΩ base-emitter resistor. | Useful pull-low/release topology. SN 64 principally **receives** cartridge IRQ, so this circuit does not replace the required IRQ receiver. Check exact transistor pinout when adapting. |

These three packages cover 40 fixed incoming signals plus eight data signals in sd2snes. They do **not** implement the entire SN 64 socket interface: /WRAMSEL, EXPAND, CIC, reset and analog audio need the separate handling in [the full pin-map notes](snes-interface-notes.md). In particular, sd2snes connects cartridge /RESET directly to its LPC1754; that is not evidence that an arbitrary FPGA pin may accept this net.

## Direction and enable behavior

With A on the FPGA side and B on the cartridge side, the transceiver function is:

| /OE | DIR | Electrical path | SN 64 use |
|---|---|---|---|
| 1 | either | Both outputs high impedance | Startup, shutdown and bus turnaround |
| 0 | 1 | A→B | Console addresses, strobes and clocks; data writes |
| 0 | 0 | B→A | Cartridge data reads |

This truth table is shared by the [TI part][ti] and [Nexperia part][nxp]. An sd2snes **read response** drives cartridge FPGA data A→B; SN 64 reads that response B→A. Reusing the upstream names or grounded DIR settings unchanged would therefore give the wrong ownership. OE and direction must be coordinated with the FPGA's own output enables and cartridge strobes. Disable the relevant bank before changing ownership, then allow the proven release/settling interval before enabling the next driver. Include both A-bus and peripheral-bus accesses.

Do not combine ordinary push-pull outputs, shared /RESET, CIC protocol I/O and IRQ into one always-enabled octet merely to fill unused channels. Keep analog audio outside digital translation.

## Manufacturer checks and power-off limits

**Nexperia 74ALVC164245DGG, Rev. 13 (2024-04-24):** recommended high-speed ranges are A = 2.7–3.6 V, B = 2.7–5.5 V, with B ≥ A. At A = 3.0–3.6 V/B = 4.5–5.5 V, input thresholds are VIH ≥ 2.0 V and VIL ≤ 0.8 V. The datasheet advertises partial-power-down/high-impedance behavior, but its suspend description also requires A outputs tristated and A-bus voltage below the diode threshold (typically 0.7 V). Do not interpret this as unrestricted operation with a powered FPGA driving A while B is off. Table 7 specifies up to 5.8 ns propagation, 8.9 ns enable and 8.6 ns disable at those rails, 50 pF and −40…+85 °C; these are individual component limits, not a cartridge timing result. [Sections 1, 8–10][nxp]

**TI SN74ALVC164245, Rev. Q (2016-09):** 3.3 V A/5 V B operation is characterized; OE/DIR control is supplied from A. TI specifies ground first, then the control-side supply, OE pulled up to A, and DIR held low or ramped with A according to the intended direction. The document does not provide an `Ioff` guarantee equivalent to Nexperia's feature claim. Disabled `IOZ` with both rails powered is not a guarantee for an unpowered port. Inputs remain active with outputs disabled and need valid bias. [Sections 3, 6 and 10][ti]

**Proposed schematic requirement:** independent of manufacturer, hold bus enables inactive during FPGA configuration, invalid rails and power transitions. Define the actual A/B rail order and all FPGA pin states during cartridge-power-off; prove that no forbidden input drive or back-power path remains. An OE pull-up alone does not prove this. Qualify the exact ordered part rather than approving the family string or treating TI/Nexperia as automatically interchangeable.

## Alternatives actually present

The sd2snes [symbol library][sd-lib] includes `74LVC1T45`, but it is **not populated in the inspected Rev F sheets/PCB**. The [root schematic's revision notes][sd-root] describe replacement of an earlier single-gate IRQ translator with the transistor circuit above. This is not a second verified Rev F bus-translator implementation.

The [Sanni SNES adapter][sanni] is passive. Its [HW5 main board][sanni-main] connects cartridge buses to the Mega module and selects their common supply; [SNES firmware][sanni-fw] explicitly selects 5 V. [Microchip's ATmega2560 datasheet, page 355][avr] specifies ordinary GPIO voltage limits relative to VCC, consistent with a native 5 V interface, not 3.3 V FPGA protection. The optional [TPS2113PW VSelect circuit][sanni-vselect] is a **power mux**, not signal translation, as confirmed by its [TI datasheet][tps]. Sanni is useful for socket wiring and cartridge operations; it supplies no alternate populated SNES FPGA translator in these references.

## Next schematic and bench checks

1. Allocate separate direction/enable groups from the 62-pin map, including the additional console outputs omitted by sd2snes. Keep dedicated treatment for shared/releasing signals.
2. For the chosen FPGA I/O rail and exact translator, calculate worst-case output thresholds, loading, propagation, enable/disable and rail sequencing. Check full data turnaround, not just clock frequency.
3. Verify startup, controlled cartridge power removal, read/write/peripheral turnaround and representative flashcart reset activity on a prototype. Measure bus voltage, overlap current, overshoot and power-off injection before copying this block into a release PCB.

[sd-sch]: https://github.com/mrehkopf/sd2snes/blob/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/pcb/kicad/RevF/snesslot.sch
[sd-pcb]: https://github.com/mrehkopf/sd2snes/blob/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/pcb/kicad/RevF/sd2snes.kicad_pcb
[sd-bom]: https://github.com/mrehkopf/sd2snes/blob/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/pcb/kicad/RevF/sd2snes-BOM.ods
[sd-lib]: https://github.com/mrehkopf/sd2snes/blob/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/pcb/kicad/libs/misc-74.lib
[sd-root]: https://github.com/mrehkopf/sd2snes/blob/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/pcb/kicad/RevF/sd2snes.sch
[ti]: https://www.ti.com/lit/ds/symlink/sn74alvc164245.pdf
[nxp]: https://assets.nexperia.com/documents/data-sheet/74ALVC164245.pdf
[sanni]: https://github.com/sanni/cartreader/blob/060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d/hardware/snes_adapter/snes_adapter.kicad_sch
[sanni-main]: https://github.com/sanni/cartreader/blob/060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d/hardware/main_pcb_hw5/main_pcb_hw5.kicad_sch
[sanni-fw]: https://github.com/sanni/cartreader/blob/060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d/Cart_Reader/SNES.ino#L587
[sanni-vselect]: https://github.com/sanni/cartreader/blob/060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d/hardware/main_pcb_hw5/vselect.kicad_sch
[tps]: https://www.ti.com/lit/ds/symlink/tps2113.pdf
[avr]: https://ww1.microchip.com/downloads/en/devicedoc/atmega640-1280-1281-2560-2561-datasheet-ds40002211a.pdf#page=355
