# SN 64

SN 64 is an active engineering project for an FPGA-based SNES/Super Famicom cartridge adapter. **The target is one adapter for both an original Nintendo 64 and ModRetro M64 through the standard N64 cartridge interface, without internal console modifications.** Compatibility has not yet been demonstrated on hardware.

The FPGA will recreate the SNES motherboard environment and provide a protected, complete SNES cartridge interface. Original SNES/SFC cartridges, Super EverDrive X5/X6, and FXPAK Pro are primary compatibility targets. The host console supplies controller input and runs the adapter's configuration and diagnostics bootstrap.

## Current status

**The project now includes a simulated SNES console candidate with a contention-checked physical cartridge bridge and a simulated N64/M64 host endpoint (reused SummerCart64 PI controller with an SN64 ROM window and mailbox), editable mechanical reference parts, and the KiCad cartridge/USB circuit draft. No completed or tested SN 64 hardware exists yet.** The [core evaluation](fpga/README.md) reuses pinned SNESTang sources and includes original diagnostics, synthesis and internal FPGA fit experiments. The [mechanical package](mechanical/README.md) contains FreeCAD, STEP and STL files for a socket hole-pattern coupon and source N64 board reference; these are not a final enclosure. The [editable schematic](hardware/sn64/README.md), revision `0.2-usb`, contains both cartridge connectors and a real [USB programmer child sheet](hardware/sn64/usb-programmer.kicad_sch): USB-C, protection, bridge power, FT232HL, crystal, optional EEPROM, isolated JTAG and service access.

Independent static checks passed **30 cartridge-interface checks and 64 USB checks**. These verify source agreement and schematic connectivity, not working hardware or USB compliance. The [136-entry requirements register](docs/requirements.md) preserves every specification target and records partial evidence separately from acceptance. Final FPGA/BOM selection, configuration storage and its programming hookup, system/cartridge power circuitry, the physical bus bridge, host and A/V integration, PCB layout, enclosure and hardware tests remain pending. **This is not fabrication ready.**

Every target in the original specification remains in scope, including PAL, protection, save integrity, telemetry, independent recovery, factory testing, and the additional requirements. Independent digital A/V is an initial validation path. M64 single-HDMI operation remains a required target with an unresolved dependency on a supported M64 integration mechanism; reserving resources does not establish compatibility.

## Documents

- [Engineering specification, Rev A](SN_64_Engineering_Specification_Rev_A.docx)
- [Engineering implementation plan](docs/superpowers/plans/2026-09-28-sn64-engineering-plan.md)
- [Full requirements and acceptance register](docs/requirements.md)
- [System architecture and integration status](docs/architecture.md)
- [Console-core evaluation and reproducible builds](fpga/README.md)
- [Physical cartridge bridge design and open tests](docs/design/physical-cartridge-bridge.md)
- [Cartridge bridge implementation and simulation evidence](docs/design/cartridge-bridge-implementation.md)
- [N64/M64 endpoint implementation and mailbox map](docs/design/n64-endpoint-implementation.md)
- [N64 CIC lockout implementation](docs/design/n64-cic-implementation.md)
- [Power-control state machine](docs/design/power-sequencer-implementation.md)
- [Clock plan and region selection](docs/design/clock-plan.md)
- [Controller path and default N64 mapping](docs/design/controller-path-implementation.md)
- [SNES CIC lock and region detection](docs/design/snes-cic-implementation.md)
- [N64 bootstrap menu ROM](docs/design/n64-bootstrap.md)
- [Integrated top level and system simulation](docs/design/system-integration.md)
- [Cartridge data-bus source evidence and unresolved behavior](docs/design/bus-electrical-evidence.md)
- [FPGA/package, supply and board reuse review](docs/design/fpga-board-selection.md)
- [Power architecture, including M64 USB power](docs/design/power-architecture.md)
- [Socket selection and missing manufacturer dimensions](docs/design/socket-selection.md)
- [Editable mechanical references and fit coupon](mechanical/README.md)
- [Peripheral research and current decisions](docs/research/snes-peripherals.md)
- [Reusable SNES circuits, layouts and FPGA source](docs/research/reusable-designs.md)
- [Connector, cartridge and mounting dimensions](docs/dimensions.md)
- [Official M64 schematics and mechanical references](docs/research/m64-reference-files.md)
- [Local reference collection and source manifests](references/README.md)
- [KiCad cartridge-interface draft and verification](hardware/sn64/README.md)
- [SNES signal directions and electrical notes](docs/design/snes-interface-notes.md)
- [N64/M64 signal directions and power references](docs/design/n64-interface-notes.md)
- [sd2snes level-shifter reuse review](docs/design/translation-reuse-review.md)
- [USB programming architecture and remaining integration](docs/design/usb-programming-architecture.md)
- [USB connector mechanics and crystal selection](docs/design/usb-connector-mechanics.md)
- [Dated project work log](docs/project-work-log.md)

Current input decisions are standard, configurable N64-to-SNES controller mapping; no multitap; and undecided Super Scope/Justifier support. Virtual SNES mouse control using an N64 controller is deferred to a later FPGA/firmware update. The initial design must preserve the necessary input data, update path, and justified resource margins. Other researched accessories are candidates, not selected features.

**USB-C is mandatory in the first hardware revision.** Provide a side-mounted, externally accessible USB-C data port for initial firmware/FPGA programming, subsequent updates and recovery from a computer. It must be usable without a successful N64 or M64 boot. Include the connector, supporting programming circuitry and enclosure opening in the initial design; a power-only port or a future hardware addition does not satisfy this requirement. The bridge circuit is now drawn, but blank-board loading, persistent image programming and recovery still require the selected FPGA/storage, their power design, host software and bench validation.

## Tools and research approach

- **KiCad 10.0.6:** schematics, PCB layout, checks, and manufacturing exports.
- **FreeCAD 1.1.4:** dimensioned enclosure and mechanical assembly models.
- **Blender:** available for visualization and mesh work.
- **OSS CAD Suite 2026-09-28:** Yosys/Slang, Verilator, nextpnr-ecp5 and programming utilities; [pinned toolchain](fpga/reports/toolchain.json). Initial loading of actual SN64 hardware is still untested.

Start by adapting working upstream designs: reuse their HDL, circuits, layouts, footprints and mechanical CAD where they fit. The main custom work is integrating the physical SNES cartridge bridge with the SNES core, protected power, the N64 host endpoint, A/V and enclosure. Dimensions and interface assumptions retain their provenance and are cross-checked. Physical fit and functional tests follow adaptation.

## Planned outputs

These directories describe the intended outputs. Cartridge/USB schematics, the core candidate/tests, mechanical reference models and the acceptance register exist; the complete product implementations remain in progress.

| Planned directory | Contents |
|---|---|
| `references/` | Reference drawings, datasheets, CAD provenance, and license records |
| `hardware/sn64/` | KiCad schematic, PCB, libraries, and component models |
| `fpga/` | HDL, core integration, simulations, and constraints |
| `firmware/` | N64 bootstrap, controls, diagnostics, updates, and recovery |
| `mechanical/` | Enclosure CAD, drawings, fit samples, and assembly models |
| `test/` | Bring-up procedures, fixtures, measurements, and compatibility results |
| `manufacturing/` | Versioned PCBWay fabrication, assembly, and enclosure packages |

PCBWay is the intended manufacturing provider. Release deliverables include editable KiCad sources, schematic PDFs, Gerbers and NC drills, stack-up/fabrication notes, BOM with manufacturer part numbers and approved alternates, placement files, assembly drawings, programming/test instructions, and test-point/JTAG documentation. Enclosure deliverables include editable CAD, STEP/STL parts, dimensioned drawings, material/finish/fastener notes, and verified interface dimensions.

Manufacturing and compatibility claims will follow prototype bring-up, physical fit checks, and recorded validation on both hosts.
