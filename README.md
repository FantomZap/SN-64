# SN 64

SN 64 is an active engineering project for an FPGA-based SNES/Super Famicom cartridge adapter. **The same adapter will work with both an original Nintendo 64 and ModRetro M64 through the standard N64 cartridge interface, without internal console modifications.**

The FPGA will recreate the SNES motherboard environment and provide a protected, complete SNES cartridge interface. Original SNES/SFC cartridges, Super EverDrive X5/X6, and FXPAK Pro are primary compatibility targets. The host console supplies controller input and runs the adapter's configuration and diagnostics bootstrap.

## Current status

**Planning and research. No completed or tested SN 64 hardware exists yet.** The repository currently contains the source specification, engineering plan, and peripheral research. It does not yet contain a validated schematic, PCB, FPGA implementation, or printable enclosure.

Every target in the original specification remains in scope, including PAL, protection, save integrity, telemetry, independent recovery, factory testing, and the additional requirements. Independent digital A/V is an initial validation path. M64 single-HDMI operation remains a required target with an unresolved dependency on a supported M64 integration mechanism; reserving resources does not establish compatibility.

## Documents

- [Engineering specification, Rev A](SN_64_Engineering_Specification_Rev_A.docx)
- [Engineering implementation plan](docs/superpowers/plans/2026-09-28-sn64-engineering-plan.md)
- [Peripheral research and current decisions](docs/research/snes-peripherals.md)

Current input decisions are standard, configurable N64-to-SNES controller mapping; no multitap; and undecided Super Scope/Justifier support. Virtual SNES mouse control using an N64 controller is deferred to a later FPGA/firmware update. The initial design must preserve the necessary input data, update path, and justified resource margins. Other researched accessories are candidates, not selected features.

## Tools and research approach

- **KiCad 10.0.6:** schematics, PCB layout, checks, and manufacturing exports.
- **FreeCAD 1.1.4:** dimensioned enclosure and mechanical assembly models.
- **Blender:** available for visualization and mesh work.
- FPGA synthesis, simulation, and programming tools will be selected with the FPGA.

Research starts with online native CAD, component drawings, public hardware sources, and developer documentation. Dimensions and interface assumptions must retain their provenance and be cross-checked. Physical measurements and fit tests will resolve remaining gaps before manufacturing release. CAD checks and manufacturer review do not replace functional hardware validation.

## Planned outputs

These directories describe future work; they are not claims that implementations already exist.

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
