# SN 64 Engineering Implementation Plan

**Status:** The full requirements register, cartridge/USB circuit draft, console-core evaluation and editable mechanical references exist. Power, socket and FPGA supply studies identify remaining integration decisions. This document defines the full work and its evidence requirements; it does not certify a completed electrical or mechanical design. See the [work log](../../project-work-log.md) and [current architecture](../../architecture.md).

**Goal:** Build one SN 64 adapter that satisfies every target in the supplied specification and works on both an original Nintendo 64 and ModRetro M64 without internal console modifications, with PCB and enclosure manufacturing through PCBWay.

**Architecture:** A single N64-compatible lower cartridge edge serves both hosts. An FPGA implements the SNES motherboard functions and the timing-sensitive host interface, connecting through protected circuitry to a complete female SNES/SFC cartridge socket. Firmware, enclosure, power, A/V, diagnostics, recovery, and manufacturing fixtures are part of the product.

**Toolchain:** KiCad 10.0.6 for schematic and PCB; FreeCAD 1.1.4 for dimensioned enclosure and assembly master models; FPGA synthesis, simulation, and programming tools selected with the FPGA. Both CAD installations and their command-line version responses have been verified. The user also has Blender installed; it is available for enclosure visualization, mesh work, and printable STL output.

**Verified executable paths:** `C:\Program Files\KiCad\10.0\bin\kicad-cli.exe` and `C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe`. KiCad's export command lists Gerber, drill, placement, STEP, and STL support. Native project and export verification remains part of stage 1.

**Source specification:** [SN 64 Engineering Specification Rev A](../../../SN_64_Engineering_Specification_Rev_A.docx). User clarifications govern interpretation: everything in the document is a target, and the same adapter must support both hosts.

## Global constraints

- Reuse existing working HDL, schematics, PCB layouts, connector footprints and shell CAD first. Adapt proven blocks instead of recreating them; the user's explicit preference is to concentrate original engineering on integration. The initial [reuse map](../../research/reusable-designs.md) and [dimension extraction](../../dimensions.md) are now available.
- Every specification requirement stays in scope, including PAL, future M64 single-HDMI integration, production provisions, and the items headed Additional Requirements Worth Adding.
- N64 and M64 share the standard N64 cartridge interface. Do not invent a second connector or assume private M64 capabilities.
- Original SNES/SFC cartridges, Super EverDrive X5 and X6, and FXPAK Pro are mandatory targets.
- Source connector dimensions online first. Use native CAD, actual component drawings, and corroborating designs; identify gaps before requesting measurements.
- The complete SNES interface includes expansion/enhancement contacts, relevant auxiliary signals, and cartridge audio. Verify the source signal list and physical pin mapping before assigning circuitry.
- Protect both console and cartridge. Default cartridge power OFF and external FPGA bus outputs high impedance until configuration and health checks succeed.
- USB-C is mandatory in the first hardware revision: a side-mounted data port for initial firmware/FPGA programming, updates and recovery from a computer, with supporting circuitry and an accessible enclosure opening. Operation must not require successful N64/M64 boot. A power-only connector or deferred hardware addition does not satisfy this requirement.
- Cartridges are not hot-swappable. Provide a deliberate power-down workflow before cartridge changes.
- Staged prototypes establish progress; they do not remove requirements or establish completion of the full target.
- The source explicitly omits the legacy TriStar NES subsystem, cheat hardware, memory editor, and analog-switch topology; those exclusions remain in force.
- Peripheral menu clarification: multitap is excluded at the user's request; Super Scope/Justifier remain undecided. Virtual SNES mouse control using an N64 controller is deferred to a later FPGA/firmware update. Preserve analog-stick/button input data, update capability, and justified FPGA/flash capacity margins for that addition. Do not treat other researched accessories as selected hardware or features; see [peripheral research](../../research/snes-peripherals.md).

## Review focus

1. Incorrect edge-contact geometry, orientation, or connector footprint: validate against source CAD, the selected part, and a fit sample before an assembled board.
2. Powered/unpowered domains driving each other: simulate and measure reset, configuration failure, brownout, power-off isolation, and contention cases.
3. A core that works with loaded ROM data but fails with physical cartridges: prove cartridge bus latency, arbitration, clocks, and enhancement-chip behavior.
4. Save corruption during resets or interrupted updates: test persistent data before and after controlled fault cases and recovery.
5. Good fit with a small cartridge but excessive loading or interference with taller cartridges: check every shell family, support load path, access opening, and both host housings.

## Planned project structure

These are planned outputs, not files claimed to exist already.

| Location | Responsibility |
|---|---|
| `docs/requirements.md` | Numbered requirements, source section, implementation owner, acceptance evidence, and status |
| `docs/dimensions.md` | Dimensions, datums, units, tolerances, source/revision, confidence, and unresolved measurements |
| `docs/architecture.md` | Interfaces, power/clock/reset architecture, component selection, and engineering calculations |
| `references/` | Provenance and permitted reference CAD, drawings, datasheets, and license records |
| `hardware/sn64/` | KiCad project, schematic, PCB, custom symbols/footprints, and component models |
| `fpga/` | HDL, core integration, simulations, pin/timing constraints, and build instructions |
| `firmware/` | N64 bootstrap, configuration/controller code, diagnostics, and update/recovery tools |
| `mechanical/` | FreeCAD master model, drawings, fit samples, enclosure parts, and board assembly |
| `test/` | Bench procedures, compatibility matrix, measurements, test firmware, and fixture designs |
| `manufacturing/` | Versioned prototype and final PCBWay release packages |

## Work stages

### 1. Establish requirements and dimensional evidence

- [x] Expand every source requirement into a traceable entry with a checkable acceptance method. The [136-entry register](../../requirements.md) retains all 110 source items plus compatibility refinements and user clarifications; future and additional items remain targets.
- [x] Confirm KiCad and FreeCAD installations, record versions, and verify their command-line executables respond.
- [ ] Verify native file opening, checking, and exports. Establish a supported conversion route for any reference CAD format the installed tools cannot read directly.
- [ ] Obtain and inspect the reference N64 edge geometry, SNES socket footprint, cartridge shells, and published M64 mechanical files listed below.
- [ ] Select an obtainable, high-cycle SNES socket with all required contacts; reconcile its actual pin numbering, mounting pattern, body envelope, mating thickness, and insertion depth with the reference footprint.
- [ ] Record N64 contact positions, board thickness, plating/bevel requirements, seating depth, and shell datum relationships. Cross-check geometry before reuse.
- [ ] Record SNES/SFC and flashcart envelope/access requirements, both host clearance envelopes, and the M64 eject mechanism clearance.
- [ ] Mark each dimension as sourced, derived, or physically verified. Record the specific evidence still needed for any gap.

**Exit evidence:** Requirements register and source-backed dimensional model sufficient to make an interface fit sample. No numerical geometry is accepted solely from an illustrative picture.

### 2. Resolve architecture and prove critical interfaces

- [ ] Compare candidate open SNES FPGA cores and their license obligations. Synthesize the selected core with representative bridge/host logic before choosing the FPGA/package and external memory.
- [ ] Define and simulate the physical cartridge bridge, including all bus directions, peripheral accesses, clocks, resets, and cartridge-specific hardware remaining outside the FPGA.
- [ ] Define N64 endpoint timing, boot/lockout requirements, ROM/bootstrap behavior, mailbox registers, controller transfer, and diagnostic access on both hosts.
- [ ] Determine available host power and worst-case board/cartridge consumption; decide whether supplemental power is necessary before fixing connector openings.
- [ ] Compare translators, memory, oscillators, regulators, power switches, protection, and A/V components using timing, electrical, lifecycle, and availability evidence.
- [ ] Specify NTSC and PAL behavior. Use NTSC for initial validation while retaining the PAL implementation and validation work.
- [ ] Establish the independent digital A/V path and handling/mixing of cartridge audio inputs.
- [ ] Investigate a supported M64 single-HDMI integration path. Record the required host capability and evidence for it; if unavailable, retain this as an unresolved full-target dependency rather than claiming success from a reserved footprint.

**Exit evidence:** Architecture, resource/timing estimates, pin budget, power budget, component shortlist, host protocols, and explicit A/V dependency decisions. Do not freeze a production board while an unresolved target can require changing its interfaces.

### 3. Design schematic, firmware contracts, and recovery

- [ ] Set up the selected FPGA synthesis, simulation, and programming tools, record versions, and verify a reproducible minimal build and programming workflow.
- [ ] Create the schematic with verified symbols/footprints, protected cartridge power, domain translation, rail supervision, sensing, reset sequencing, watchdog, ESD, decoupling, and clock/bus damping and pull options. Include soft-start, current limiting, reverse-current blocking, and safe power-off isolation.
- [ ] Define register and image formats shared by FPGA and firmware, including hardware revision, FPGA build ID, firmware version, faults, and reset reason.
- [ ] Include N64 analog-stick axes and button states in the controller interface and version its format. Budget resources and image storage for a later virtual SNES mouse implementation; allow coordinated FPGA, bootstrap, and menu updates with independent recovery. Leave the mouse mode absent from the initial menu until implemented and tested.
- [ ] Expose cartridge voltage/current, FPGA rails, input voltage, temperature, configuration state, overcurrent history, and reset reason. Make bootstrap health checks refuse cartridge power on a reported fault.
- [ ] Implement configurable controller mapping and configuration/diagnostic behavior specified by Rev A.
- [ ] Define independent JTAG/service recovery and versioned, integrity-checked updates with a known-good recovery strategy.
- [ ] Implement the first-revision side-mounted USB-C programming path. Define initial loading of a blank board and recovery from an invalid image, including any factory bootstrap step; retain independent factory/service access. Verify computer-based firmware/FPGA loading and persistence after power cycling before accepting the first revision.
- [ ] Produce meaningful simulations for buses, fault transitions, and memory timing; review electrical ratings and the schematic in addition to ERC.

**Exit evidence:** Reviewed schematic, interface contracts, initial builds/simulations, and a recovery procedure that does not depend on successful N64 boot.

### 4. Lay out PCB and develop the enclosure together

- [ ] Agree the fabrication constraints and stack-up with PCBWay specifications. Evaluate six layers as the preferred starting point; decide using routing, return paths, cost, and signal-integrity needs.
- [ ] Place the top socket and bottom edge from the controlled dimensional model; place translators, FPGA, clocks, power, and A/V following the source architecture.
- [ ] Route with verified return paths, termination options, test access, thermal copper, and enclosure keep-outs. Concentrate manufacturing test pads on one side where practical.
- [ ] Export the populated board as STEP and design the FreeCAD enclosure around it, with universal cartridge opening, keyed insertion, structural support, fasteners, service access, and thermal provisions.
- [ ] Include the mandatory side USB-C opening and verify cable/plug clearance on both hosts in the first enclosure revision.
- [ ] Check clearances for SNES/SFC, X5/X6, and FXPAK Pro shells and their SD/cable access. Check both hosts and the M64 eject motion.
- [ ] Print interface/fit samples and test seating and interference before releasing the full enclosure. Specify material/process-dependent tolerances and assembly clearances.
- [ ] Run ERC/DRC, schematic/PCB parity, footprint and polarity checks, 3D interference checks, and an independent engineering review.

**Exit evidence:** Reviewed prototype board and enclosure, reproducible exports, resolved critical check findings, and fit-test results. CAD checks alone do not prove electrical function.

### 5. Manufacture and bring up prototypes

- [ ] Prepare PCBWay prototype fabrication/assembly files and separate enclosure files with consistent revision identifiers.
- [ ] Define a factory programming package with the tested firmware and FPGA configuration images, exact target devices/storage, programmer and connection instructions, required equipment/fixture, and verification/power-cycle tests. Confirm PCBWay can perform this specific programming and test scope before ordering preprogrammed assemblies.
- [ ] Inspect the unpowered assembly and check for shorts; use a current-limited bench supply without a console or game cartridge.
- [ ] Validate rails and sequencing, then a minimal FPGA image with external buses high impedance.
- [ ] Check N64 idle levels with a fixture, protected cartridge power with a dummy load, and SNES clocks/buses with measurement fixtures.
- [ ] Bring up N64 bootstrap, mailbox, controls, diagnostics, and independent A/V, then repeat host operation on M64.
- [ ] Progress through simple cartridges, SRAM cartridges, Super EverDrive, FXPAK Pro, and enhancement-chip cases.
- [ ] Run fault injection before extended compatibility testing. Track required board/firmware/enclosure revisions from measured evidence.

**Exit evidence:** Bring-up report with measured results and issues. The first fabrication is a prototype, not a claim of complete compatibility.

### 6. Complete compatibility, reliability, and factory testing

- [ ] Execute cold boot, warm reset, controls, video, audio, saves, cartridge reset, and extended-runtime tests for each applicable matrix target.
- [ ] Cover LoROM, HiROM, battery SRAM, DSP, Super FX, SA-1, S-DD1, Cx4, both Super EverDrive models, FXPAK Pro ordinary/enhancement implementations, representative N64 revisions, PAL, and M64 stock timing.
- [ ] Test M64 overclock modes as a separately reported category without substituting those results for stock operation.
- [ ] Test brownouts, interrupted configuration/update, invalid images, overcurrent handling, telemetry, power cycling, and save integrity.
- [ ] Validate worst-case thermal behavior in the enclosure, insertion cycles/forces, wobble/side loading, and EMI/EMC pre-compliance behavior.
- [ ] Develop the cartridge-free factory self-test image for RAM, buses, clocks, power telemetry, and host communication; develop the golden diagnostic cartridge and manufacturing fixture/test procedure.
- [ ] Validate the M64 single-HDMI path when its prerequisite integration is available; maintain its separate acceptance record until completed.

**Exit evidence:** Recorded results for every requirement. Rev A milestone success follows section 16; completion of the user's full target additionally requires the future/additional targets to be satisfied.

### 7. Release the complete manufacturing and support package

- [ ] Release KiCad sources, schematic PDF, Gerbers/drills, fabrication drawing/stack-up notes, BOM with manufacturer part numbers and approved alternates, PCBWay placement file, and assembly drawings.
- [ ] Release enclosure CAD, STEP/STL parts, dimensioned drawings, material/finish/fastener notes, and the complete mechanical assembly model.
- [ ] Release programming/initial-power-up instructions, test-point/JTAG documentation, factory-test assets, telemetry definitions, compatibility evidence, and recovery/update instructions.
- [ ] Complete third-party source/license obligations, branding review, component lifecycle records, and build identity documentation.
- [ ] Confirm PCBWay manufacturing review issues are resolved and release files agree on revision, board origin, units, placement side/rotation, and fitted components.
- [ ] Consider cost reduction and miniaturization only after the source success criteria are met; rerun affected validation after each change.

**Exit evidence:** A reproducible release with manufacturing files, editable sources, programming/test assets, and evidence supporting the actual compatibility claims.

## Source section coverage

| Specification section | Primary work stage |
|---|---|
| 1 Product definition | 1, 2, 6 |
| 2 Hard requirements | 1 through 7 |
| 3 Architecture and excluded legacy TriStar subsystems | 2 |
| 4 Complete SNES cartridge interface and protected power | 1 through 5 |
| 5 FPGA SNES subsystem, deterministic memory, and clocks | 2, 3, 6 |
| 6 N64/M64 endpoint, bootstrap, and configurable controls | 2, 3, 5, 6 |
| 7 Independent A/V and M64 single-HDMI target | 2 through 6 |
| 8 Safety, reset sequencing, thermal sensing, and telemetry | 2 through 6 |
| 9 Firmware, updates, watchdog, and independent recovery | 2, 3, 5, 6, 7 |
| 10 Mechanical design and M64 eject clearance | 1, 4, 6 |
| 11 PCB architecture and test access | 4, 6 |
| 12 Complete manufacturing package | 5, 7 |
| 13 Ordered bring-up procedure | 5 |
| 14 Recorded compatibility matrix | 6 |
| 15 All additional requirements | 2 through 7 |
| 16 Rev A success and later production decisions | 6, 7 |
| 17 Resolve known unknowns before the affected design is frozen | 1, 2, 4 |
| 18 Reference provenance and technical cross-checks | 1, 2, 7 |

## Starting references

These are research starting points, not an assertion that their dimensions or circuitry have already been validated for SN 64. Record revisions and licensing before copying reusable content.

- [SNES female connector footprint](https://github.com/sanni/cartreader/blob/master/hardware/footprints/%21OSCR.pretty/SNES%20Slot.kicad_mod)
- [Sanni SNES adapter board](https://github.com/sanni/cartreader/blob/master/hardware/snes_adapter/snes_adapter.kicad_pcb)
- [SummerCart64 N64 board geometry](https://github.com/Polprzewodnikowy/SummerCart64/blob/main/hw/pcb/sc64v2.kicad_pcb)
- [SummerCart64 shell models](https://github.com/Polprzewodnikowy/SummerCart64/tree/main/hw/shell)
- [Official M64 mechanical and electrical downloads](https://support.modretro.com/en_us/articles/m64-open-source-files-ByrpukdUGg)
- [Official M64 console repository](https://github.com/ModRetro/oss-m64-console)
- [KiCad CLI checks and exports](https://docs.kicad.org/10.0/en/cli/cli.html)
- [FreeCAD capabilities](https://www.freecad.org/features.php)
- [Blender STL import and export](https://docs.blender.org/manual/en/3.6/files/import_export/stl.html)
- [Onshape import/export formats](https://cad.onshape.com/help/Content/File/supported_file_formats.htm), a possible conversion route for published Parasolid reference parts
- [PCBWay assembly file requirements](https://www.pcbway.com/assembly-file-requirements.html)
- [PCBWay accepted 3D printing formats](https://www.pcbway.com/helpcenter/3d_ordering/What_file_formats_are_accepted_for_3D_printing_.html)

The inspected M64 downloads include individual Parasolid mechanical parts, not a verified complete positioned console assembly. The public console repository inspected during planning describes software as forthcoming. Recheck those sources during architecture work; neither observation changes the requirement to support both hosts or the single-HDMI target.

## Immediate next work

The reference collection now includes source SNES FPGA implementations, OpenSFC and sd2snes electrical designs, Sanni connector CAD, SummerCart64 host-side PCB/shell files, and official M64 reference files. Native KiCad/STEP imports and exports have been exercised; connector/pad/hole dimensions are recorded in [the dimension register](../../dimensions.md). M64 Parasolid conversion and complete host/socket envelope verification remain unresolved.

The [first editable KiCad interface draft](../../../hardware/sn64/README.md) implements the checked 50-contact N64/M64 edge and 62-contact SNES socket with reused footprints. The [SNES pin notes](../../design/snes-interface-notes.md), [N64 pin notes](../../design/n64-interface-notes.md), and [translator reuse review](../../design/translation-reuse-review.md) establish pin identities, domain boundaries and concrete upstream circuits to adapt. This is early interface work, not completion of stage 3 or permission to skip architecture evidence.

Revision `0.2-usb` adds the [native USB programmer sheet](../../../hardware/sn64/usb-programmer.kicad_sch): the side USB-C receptacle, separate CC resistors, ESD protection, USB-only regulator, FT232HL support circuit, default-disabled JTAG translator and service header. The [programming contract](../../design/usb-programming-architecture.md), [connector/crystal dimensions](../../design/usb-connector-mechanics.md), and [independent circuit review](../../../hardware/sn64/validation/usb-review.md) record the evidence and limitations. USB enumeration is designed to work from a blank board; target power, final FPGA/flash hookup, persistent images and hardware validation are still required. The stage 3 USB task remains open until that complete path is demonstrated.

Next: finish the traceable requirements register, select and dimension the actual SNES socket, establish the combined power budget and power paths on both hosts, and adapt the existing translator circuitry with verified power-off behavior. Compare/synthesize reusable SNES core and bridge/host logic before fixing the FPGA package and memory. Use those results to complete the protected circuit schematic, then PCB placement and the FreeCAD assembly/enclosure.
