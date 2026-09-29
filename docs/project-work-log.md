# SN 64 project work log

This log records local engineering artifacts and evidence. It does not certify working hardware, manufacturing readiness or publication to GitHub. Every target in [specification Rev A](../SN_64_Engineering_Specification_Rev_A.docx) remains in scope, subject to the explicit user decisions recorded in the [engineering plan](superpowers/plans/2026-09-28-sn64-engineering-plan.md).

## 2026-09-28 — References and cartridge-interface draft

- Collected native upstream schematics, layouts, HDL, footprints and mechanical references, with source revisions and license notes. The [reuse map](research/reusable-designs.md) distinguishes the MiSTer SNES core, sd2snes cartridge-side circuitry, OpenSFC donor-chip motherboard and SummerCart64 N64 endpoint. These are reusable blocks; they do not constitute a working SN 64 adapter.
- Recorded [connector and shell dimensions](dimensions.md), including source/derived dimensions and remaining fit checks. Created a native KiCad root sheet with the 50-contact N64 edge and complete 62-contact SNES/SFC socket, project libraries and signal maps.
- Checked cartridge signal identity, direction and special handling against the references. Documented the [SNES interface](design/snes-interface-notes.md), [N64 interface](design/n64-interface-notes.md) and [translator reuse limits](design/translation-reuse-review.md). Physical cartridge bridge logic, power switching and remaining interface circuits are still pending.

## 2026-09-29 — Side USB-C programmer circuit draft

- Added the real [USB programmer child schematic](../hardware/sn64/usb-programmer.kicad_sch), revision `0.2-usb`, to the cartridge-interface project. It includes the reused JAE receptacle geometry, independent 5.1 kΩ CC terminations, data/CC ESD arrays, bridge regulator, FT232HL revision C, 12 MHz crystal, optional DNP EEPROM, default-disabled JTAG translator and target-side service header.
- Documented [blank-board startup and the host programming contract](design/usb-programming-architecture.md), including the required `--status-pin 14` option. USB enumeration is designed to be independent of the main FPGA image; actual blank-board enumeration and programming have not been tested.
- Checked the [connector manufacturer's geometry and crystal requirements](design/usb-connector-mechanics.md). The crystal's two 11 pF load capacitors remain provisional pending layout parasitics, startup and frequency measurements. Final enclosure location and cable clearance remain open.
- Exported the schematic/netlist and ran independent static checks. The saved reports show [30 cartridge-interface checks passed](../hardware/sn64/validation/interface-check.json) and [64 USB checks passed](../hardware/sn64/validation/usb-check.json), with zero failures. The ERC report retains 90 isolated-label warnings at the unfinished cartridge interfaces. Static connectivity checks do not demonstrate hardware operation or USB compliance.

The first hardware revision must provide externally accessible, side-mounted USB-C for initial loading, later updates and recovery without a successful N64/M64 boot. The drawn bridge powers only its own interface; FPGA selection, persistent storage, target programming power and hookup, boot straps, loading software and cold-boot recovery tests are still required to fulfill that requirement.

## Remaining work

Select and validate the FPGA/storage and physical-cartridge bridge, complete system/cartridge power and protection, N64 endpoint, controller/firmware functions, clocks, A/V and diagnostics. Retain PAL and the required M64 single-HDMI target; its supported integration mechanism remains unresolved. Complete PCB placement/routing and the FreeCAD enclosure, then perform electrical, programming, compatibility and fit tests on prototypes before producing a PCBWay release. No working SN 64 hardware or fabrication-ready package exists yet.
