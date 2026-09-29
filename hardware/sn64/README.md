# SN 64 KiCad interface draft

Open **[sn64.kicad_pro](sn64.kicad_pro)** in KiCad 10, then open the schematic. The [PDF](exports/sn64-interface-draft.pdf) is a review copy of the same sheet. This is revision `0.1-interface`: two physical connectors with source-verified pin identities and project-local libraries. It is not a complete electrical design or a manufacturing package.

## What is present

| Item | Contents |
|---|---|
| J1 | 50-contact N64 edge, intended for both original N64 and M64 |
| J2 | Full 62-contact SNES/SFC female socket, including outer contacts and analog audio |
| Symbol library | Editable native KiCad symbols, numbered from the checked pin maps |
| Footprint library | Unmodified Sanni female-socket footprint and extracted SummerCart64 N64 edge footprint |
| Pin maps | [N64](interfaces/n64-pin-map.csv) and [SNES](interfaces/snes-pin-map.csv), including endpoint directions, domains and sources |
| Validation | Exported netlist, unfiltered ERC report, and independent pin/footprint checks |

`GND` is the only shared connector net. `HOST_3V3`, `HOST_12V` and `SNES_5V_CART` are distinct. SNES and N64 resets, data, CIC and audio signals are also distinct. `_N` in net names denotes active low; the symbols retain the source map's slash notation. Labels identify future circuit connections; they do not implement translation, power switching or functional behavior.

Connector pins deliberately have the ordinary passive connector type. The CSV and [electrical notes](../../docs/design/snes-interface-notes.md), rather than these pin types, define endpoint direction and special handling. A connector-only ERC cannot validate drive ownership, voltage tolerance or timing.

## Reused geometry and its limits

The SNES footprint retains all 62 pads, 2.5 mm ordinary pitch, two 7.5 mm gaps per row, 5 mm row separation, 1.524 mm pads and 0.762 mm drills. A specific purchasable socket, body dimensions and mounting details still need approval before board layout.

The N64 footprint preserves all 50 source pads, 2.5 mm pitch and 1.5 x 7 mm copper dimensions. Pads 1-25 remain on B.Cu and 26-50 on F.Cu. Its origin corresponds to source board coordinates (150,125), so pads are at local Y=6 mm. Six retained `Edge.Cuts` segments form the open lower connector profile, ending at local (±32.25,0) with its bottom at Y=10.5 mm. **Do not duplicate these cuts** when extending the board outline. The footprint does not include a complete board perimeter, mounting holes, layer stack or bevel. Those are separate controlled dimensions in [the geometry record](../../docs/dimensions.md). No generic KiCad board thickness should be treated as the connector thickness.

See [THIRD_PARTY.md](THIRD_PARTY.md) and [provenance.json](libraries/provenance.json) for sources, modifications and retained licenses. The copies of upstream footprints are reference assets, not a fit-tested SN 64 board.

## Validation and reproducibility

KiCad 10.0.6 successfully loads and exports this schematic to XML and PDF. The PDF was rendered and visually inspected. ERC reports **90 warnings**, all `isolated_pin_label`: each pending signal net currently reaches only its connector contact. No warnings were suppressed or replaced with no-connect flags merely to make the report pass. This is an incomplete design, and the ERC command intentionally returns a nonzero result. The check must be rerun as actual circuitry is added.

The [independent validation script](tools/verify_interfaces.py) checks the exported connector pin/net assignments against the separately researched maps, rejects accidental cross-domain connections, and compares both footprints against the original downloaded sources. The corresponding [result](validation/interface-check.json) and [review](validation/interface-review.md) record the result and remaining limitations.

To regenerate review files after editing, run these from this directory with KiCad's CLI on PATH:

```powershell
kicad-cli sch export netlist --format kicadxml -o validation/sn64.xml sn64.kicad_sch
kicad-cli sch export pdf -o exports/sn64-interface-draft.pdf sn64.kicad_sch
kicad-cli sch erc --format json --output validation/erc.json --exit-code-violations sn64.kicad_sch
```

The initial authoring script, [create_interface_draft.py](tools/create_interface_draft.py), uses KiCad's Python and downloaded upstream sources. It refuses to replace an existing schematic unless explicitly passed `--force`. Once circuit editing begins, edit the native KiCad files; do not regenerate the initial sheet over the circuit work.

## Next circuitry

1. Build the power budget for the FPGA, memory, digital A/V and real cartridges on both hosts. The M64 reference annotates a 500 mA cartridge limiter; that is not a guaranteed SN 64 allowance. There is no 5 V N64 edge supply. Select input power, no-backfeed paths and default-off protected cartridge power from the actual budget.
2. Adapt the sd2snes translator circuit using the [reuse review](../../docs/design/translation-reuse-review.md). Reverse address/strobe ownership for a console endpoint; define enable, read/write turnaround and power-off behavior for the exact part. Separately implement IRQ/reset, CIC, expansion and analog audio.
3. Integrate the reusable SNES FPGA core, physical cartridge bridge and N64 endpoint. Select FPGA/package and memory only after resource, I/O, clock and timing evidence. Add independent recovery, health monitoring and A/V, then review the complete schematic.
4. Place and route a PCB with the verified mechanical constraints; develop the FreeCAD enclosure around that assembly. Produce PCBWay files after electrical review and prototype/fit validation.

These are the next stages of the full specification, not a reduced product target. No PCB, FPGA bitstream, working adapter, print-ready shell or PCBWay release is included in this interface revision.
