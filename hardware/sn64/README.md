# SN 64 KiCad schematic draft

Open **[sn64.kicad_pro](sn64.kicad_pro)** in KiCad 10, then open the schematic. The [PDF](exports/sn64-interface-draft.pdf) is a review export of the root cartridge sheet and [USB programmer child sheet](usb-programmer.kicad_sch). Revision `0.2-usb` contains two cartridge connectors and a USB-C programming circuit with project-local libraries. It is not a complete electrical design or a manufacturing package.

## What is present

| Item | Contents |
|---|---|
| J1 | 50-contact N64 edge, intended for both original N64 and M64 |
| J2 | Full 62-contact SNES/SFC female socket, including outer contacts and analog audio |
| USB child sheet | J101 JAE USB-C, separate CC resistors, data/CC ESD arrays, AP2112K-3.3 bridge regulator, FT232HL revision C, 12 MHz crystal, optional DNP EEPROM, SN74AXC4T774 JTAG isolation and J102 target-side service header |
| Symbol library | Editable native KiCad symbols, numbered from the checked pin maps |
| Footprint library | Sanni female-socket and SummerCart64 N64 edge references; local USB component footprints including the reused JAE receptacle geometry |
| Pin maps | [N64](interfaces/n64-pin-map.csv), [SNES](interfaces/snes-pin-map.csv) and [USB circuit nets](interfaces/usb-programmer-net-map.csv) |
| Validation | Exported netlist, ERC report, independent cartridge-interface checks and 64 USB static checks |

`GND` is the only net shared across the cartridge interfaces and USB boundary. `HOST_3V3`, `HOST_12V`, `SNES_5V_CART`, `USB_VBUS`, `USB_3V3` and `TARGET_VREF` are distinct. USB power currently supplies the bridge block only. The future FPGA programming rail must supply `TARGET_VREF`; it is not a USB target-power output. SNES and N64 resets, data, CIC and audio signals remain separate, awaiting their circuitry. `_N` in net names denotes active low; the cartridge symbols retain the source maps' slash notation.

Connector pins deliberately have the ordinary passive connector type. The CSV and [electrical notes](../../docs/design/snes-interface-notes.md), rather than these pin types, define endpoint direction and special handling. ERC cannot establish drive ownership, voltage tolerance or timing at these pending interfaces.

The USB bridge uses MPSSE JTAG with ACBUS6 controlling the translator's pulled-up, default-disabled `/OE`. The documented host command must include `--status-pin 14`. Its target JTAG nets are not yet connected to a selected FPGA or configuration storage. The [programming architecture](../../docs/design/usb-programming-architecture.md) records blank-EEPROM startup, power isolation, persistent-loading requirements and the remaining tests. [Connector and crystal notes](../../docs/design/usb-connector-mechanics.md) record the source geometry and provisional 11 pF crystal load capacitors.

## Reused geometry and its limits

The SNES footprint retains all 62 pads, 2.5 mm ordinary pitch, two 7.5 mm gaps per row, 5 mm row separation, 1.524 mm pads and 0.762 mm drills. A specific purchasable socket, body dimensions and mounting details still need approval before board layout.

The N64 footprint preserves all 50 source pads, 2.5 mm pitch and 1.5 x 7 mm copper dimensions. Pads 1-25 remain on B.Cu and 26-50 on F.Cu. Its origin corresponds to source board coordinates (150,125), so pads are at local Y=6 mm. Six retained `Edge.Cuts` segments form the open lower connector profile, ending at local (±32.25,0) with its bottom at Y=10.5 mm. **Do not duplicate these cuts** when extending the board outline. The footprint does not include a complete board perimeter, mounting holes, layer stack or bevel. Those are separate controlled dimensions in [the geometry record](../../docs/dimensions.md). No generic KiCad board thickness should be treated as the connector thickness.

See [THIRD_PARTY.md](THIRD_PARTY.md), [cartridge provenance](libraries/provenance.json) and [USB provenance](libraries/usb-provenance.json) for sources, modifications and retained licenses. All 24 USB footprint pad objects also match the source geometry in the [footprint review](validation/usb-footprint-review.json). The copies of upstream footprints are reference assets, not a fit-tested SN 64 board.

## Validation and reproducibility

KiCad 10.0.6 exports the two-sheet schematic to XML and PDF. Both PDF sheets were rendered and visually inspected. The saved ERC report contains **90 warnings**, all `isolated_pin_label`, at the pending cartridge interfaces, and **zero errors**. The USB sheet has no ERC violations. These warnings remain visible; the schematic is incomplete and is not an ERC-clean release. Rerun checks as actual circuitry is added.

The [independent validation script](tools/verify_interfaces.py) checks the exported connector pin/net assignments against the separately researched maps, rejects accidental cross-domain connections, and compares both footprints against the original downloaded sources. The corresponding [result](validation/interface-check.json) and [review](validation/interface-review.md) record the result and remaining limitations.

The saved reports record **30 cartridge-interface checks passed and 64 USB checks passed, with zero failed checks**. The [USB validator](tools/verify_usb_programmer.py) independently exports the schematic and compares it with fixed manufacturer pin tables, checking all USB component pins, rail separation, CC/data/ESD connections, bridge support, JTAG directions and disabled startup. See its [result](validation/usb-check.json) and [review](validation/usb-review.md). These are static checks; no USB enumeration, clock measurement, suspend-current measurement, programming, cold boot, electrical protection or compatibility test has been performed on SN 64 hardware.

To regenerate review files after editing, run these from this directory with KiCad's CLI on PATH:

```powershell
kicad-cli sch export netlist --format kicadxml -o validation/sn64.xml sn64.kicad_sch
kicad-cli sch export pdf -o exports/sn64-interface-draft.pdf sn64.kicad_sch
kicad-cli sch erc --format json --output validation/erc.json --exit-code-violations sn64.kicad_sch
```

The initial authoring script, [create_interface_draft.py](tools/create_interface_draft.py), uses KiCad's Python and downloaded upstream sources. It refuses to replace an existing schematic unless explicitly passed `--force`. Once circuit editing begins, edit the native KiCad files; do not regenerate the initial sheet over the circuit work.

[add_usb_programmer.py](tools/add_usb_programmer.py) records how the initial USB sheet was authored from the reference designs and installed KiCad libraries. It also refuses to replace its sheet without `--force`; use native KiCad editing for subsequent development. Regeneration requires `--source-root <original-project-with-downloads>` and `--kicad-share <KiCad-share-directory>`, and intentionally replaces the entire USB child sheet when forced.

## Remaining integration

**Required in the first revision:** a side-mounted USB-C data/programming port and matching enclosure opening, supporting initial firmware/FPGA loading, updates and recovery without successful host-console boot. The bridge and service-access circuit now exists; the complete programming path remains pending target integration and testing. Final side-port placement, cable access and shell clearances remain mechanical work.

1. Build the power budget for the FPGA, memory, digital A/V and real cartridges on both hosts. The M64 reference annotates a 500 mA cartridge limiter; that is not a guaranteed SN 64 allowance. There is no 5 V N64 edge supply. Select input power, no-backfeed paths and default-off protected cartridge power from the actual budget.
2. Adapt the sd2snes translator circuit using the [reuse review](../../docs/design/translation-reuse-review.md). Reverse address/strobe ownership for a console endpoint; define enable, read/write turnaround and power-off behavior for the exact part. Separately implement IRQ/reset, CIC, expansion and analog audio.
3. Integrate the reusable SNES FPGA core, physical cartridge bridge and N64 endpoint. Select FPGA/package and memory only after resource, I/O, clock and timing evidence. Connect the USB programmer to the selected target and persistent configuration storage, define programming power/boot straps and package the loading/recovery software. Add health monitoring and A/V, then review the complete schematic.
4. Place and route a PCB with the verified mechanical constraints; develop the FreeCAD enclosure around that assembly. Produce PCBWay files after electrical review and prototype/fit validation.

These are stages of the full specification. PAL, protection, save integrity, telemetry, factory testing and all remaining specification targets are retained. Independent digital A/V is the initial validation path; required M64 single-HDMI operation still depends on a supported host integration mechanism. No PCB layout, FPGA bitstream, working adapter, print-ready shell or PCBWay manufacturing release is included in this revision.
