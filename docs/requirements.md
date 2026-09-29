# SN64 requirements and acceptance register

Baseline recorded 2026-09-29 from [Engineering Specification Rev A](../SN_64_Engineering_Specification_Rev_A.docx), with the user's clarifications in the [engineering plan](superpowers/plans/2026-09-28-sn64-engineering-plan.md) and [project README](../README.md). **Every specification target remains in scope. No completed prototype, hardware acceptance, or fabrication readiness is claimed.**

The authoritative row-level register is [test/acceptance-matrix.csv](../test/acceptance-matrix.csv). It contains **136 stable IDs: 110 source-item rows covering all 18 sections, 16 explicit compatibility subclasses, and 10 user-clarification rows**. Every original paragraph/bullet is retained verbatim in `source_text`; compound clauses remain binding together and their acceptance evidence names the required checks. Section 18 rows track source provenance rather than additional product functions.

## IDs and source mapping

`SN64-SS-II` identifies source section SS and paragraph/bullet II, counted in source order beneath that heading. These item numbers are register locators; Rev A itself only numbers sections. `SN64-14-02-X5`, for example, refines §14 item 2 without replacing its parent. `SN64-U-NN` records an explicit user clarification or its recorded project interpretation. Do not reuse or renumber IDs when the design changes; record supersession and keep traceability.

| Source section | Original items covered | Base IDs |
|---|---:|---|
| 1. Product Definition | 2 | `SN64-01-01`–`SN64-01-02` |
| 2. Hard Requirements | 9 | `SN64-02-01`–`SN64-02-09` |
| 3. Architecture | 2 | `SN64-03-01`–`SN64-03-02` |
| 4. SNES Cartridge Interface | 3 | `SN64-04-01`–`SN64-04-03` |
| 5. FPGA SNES Subsystem | 4 | `SN64-05-01`–`SN64-05-04` |
| 6. N64 and M64 Host Interface | 4 | `SN64-06-01`–`SN64-06-04` |
| 7. Video and Audio | 3 | `SN64-07-01`–`SN64-07-03` |
| 8. Safety and Protection | 13 | `SN64-08-01`–`SN64-08-13` |
| 9. Firmware and Recovery | 4 | `SN64-09-01`–`SN64-09-04` |
| 10. Mechanical Design | 7 | `SN64-10-01`–`SN64-10-07` |
| 11. PCB Architecture | 3 | `SN64-11-01`–`SN64-11-03` |
| 12. Manufacturing Package | 10 | `SN64-12-01`–`SN64-12-10` |
| 13. Bring-Up Procedure | 16 | `SN64-13-01`–`SN64-13-16` |
| 14. Compatibility Certification | 2 | `SN64-14-01`–`SN64-14-02` |
| 15. Additional Requirements Worth Adding | 12 | `SN64-15-01`–`SN64-15-12` |
| 16. Rev A Success Criteria | 2 | `SN64-16-01`–`SN64-16-02` |
| 17. Known Unknowns Before Fabrication | 7 | `SN64-17-01`–`SN64-17-07` |
| 18. Source Notes | 7 | `SN64-18-01`–`SN64-18-07` |

The 16 compatibility refinements distinguish LoROM, HiROM, battery SRAM, DSP, Super FX, SA-1, S-DD1, Cx4, physical X5, physical X6, FXPAK Pro ordinary ROMs, FXPAK enhancement implementations, representative N64 revisions, PAL, M64 stock timing and M64 overclock modes. Original SNES/SFC regions and shell families are also required by §1, §2 and §10; they must be represented in the actual test inventory.

Source fingerprint: DOCX SHA-256 `9d29fa2ec6e551718fd1fb2367175e7e6764853a06179bc2e7424c8235a84581`. The extraction used for item ordering was `.local/specification.txt`, SHA-256 `01445c56e40a48ba294c58872e9a5bb71c81f2eb692aab53b0db2b78d3038780`. If an extraction conflicts with the original document, use the original document and record the correction.

## Evidence is separate from acceptance

`evidence_level` describes the strongest **partial evidence actually referenced**, not completion of the entire row:

| Level | Meaning |
|---|---|
| documented | Requirement, provenance, architecture decision or acceptance procedure recorded |
| designed | Relevant draft circuit, HDL, CAD or interface artifact exists; it may implement only part of the row |
| simulated | A reproducible passing simulation is cited with its exact tested scope and limitations |
| measured | Measurements on identified SN64 hardware are cited with instruments, conditions, limits and raw evidence |

Static schematic/footprint/CAD checks remain design evidence. They do not become electrical measurements, a USB-compliance result, cartridge compatibility or host-fit validation. A compiled simulation executable alone is not a passing simulation. A hardware measurement alone is not acceptance unless it covers the complete requirement under defined limits.

At this register snapshot, **47 rows have partial design evidence, 86 are documented and 3 have partial simulation evidence; zero are measured. All 136 rows remain `NOT_ACCEPTED`.** The referenced [30 interface checks](../hardware/sn64/validation/interface-check.json), [64 USB checks](../hardware/sn64/validation/usb-check.json) and [CAD validation](../mechanical/fit-references/validation.json) are useful limited design evidence.

The [preserved core evaluation](../fpga/reports/evaluation.md) and [machine-readable results](../fpga/reports/evaluation.json) support `simulated` for `SN64-05-01` through `SN64-05-03` only: a 1,336-clock diagnostic checks reset/native CPU execution, modeled external reads/writes, WRAM and its mirror address, a B-bus write, two-byte A-to-B DMA and PHI2 activity. A separate 1,089-clock regression checks current WRAM output during direct/two-mirror reads, RAM data-port reads, B-to-A DMA and reset/pause source-valid gating. It does not model physical output enables or prove bus ownership. The PAL mode-bit run uses the same 46.56 ns clock and does not qualify PAL clock/video/audio. Core synthesis and a trial internal route provide resource/timing feasibility evidence with unconstrained external I/O. Graphics, sound, HDMA, full clock/memory timing, physical bus ownership, real cartridges and whole-system operation remain unverified; no requirement is accepted by these results.

## Stage gates and scope decisions

- **Rev A:** independent digital SNES A/V, safe original-N64 and ordinary-cartridge M64 operation, representative real cartridges plus physical X5/X6/FXPAK Pro, saves, controls, fault reporting, reset/power-cycle resilience and invalid-image recovery without rework. §16 is a conjunction: all its criteria need evidence.
- **First-revision USB:** side-mounted externally accessible USB-C **data** circuitry and enclosure access are mandatory. USB enumeration, blank-target initial loading, persistent storage programming, power-off/cold-boot persistence, later updates and failed-image recovery are distinct tests. Operation must not require a working N64/M64 boot or preloaded main FPGA/MCU image. JTAG/service access remains required independently; a connector or FTDI enumeration alone does not satisfy the complete path.
- **Full target:** PAL and supported M64 single-HDMI remain required, along with every additional §15 provision and the complete compatibility inventory. NTSC-first work and independent A/V do not remove those targets. Resource reservation does not establish M64 integration.
- **Production:** complete §12 package, factory self-test, golden cartridge/fixture, lifecycle/license/branding work, pre-compliance and mechanical/thermal reliability evidence are required. §16.2 prohibits treating the design as a production candidate, reducing cost or miniaturizing before Rev A success. Later changes need affected regression checks.
- **User control decisions:** no multitap. Virtual mouse implementation is deferred, while initial analog/button transport, update path and justified capacity provision remain required. Super Scope/Justifier remain undecided; other researched accessories are not automatically selected.
- **Manufacturing route and reuse:** PCBWay is the intended PCB/assembly and enclosure provider. Reuse existing working designs with exact provenance; existing schematics or models do not automatically qualify a different device, socket or integration.

## Open interpretations and quantitative limits

These points need explicit engineering resolution; none is an implicit waiver or pass:

| Issue | Source relationship and current interpretation |
|---|---|
| Future M64 interface versus “Before Fabrication” | §6.4/§7.3 reserve a future supported path, while §17 lists that unknown under a broad pre-fabrication heading. Track it as an unresolved full-target dependency. Any prototype release decision must explicitly state its limited scope; do not claim full completion or invent a private interface. |
| PAL sequencing versus full coverage | §5 starts validation with NTSC; §14 says PAL where available. PAL implementation/qualification remains required. Record missing samples as untested and track host region, cartridge region and SNES timing mode separately. |
| Representative Rev A set versus complete matrix | §16 permits a representative milestone set; §14 supplies the broader target inventory. Define the representative set before accepting Rev A and keep all uncovered classes open for full completion. |
| Controller default detail | §6 fixes D-pad, Start→Start and Z→Select, but does not specify each face/C/shoulder assignment. Freeze a complete A/B/X/Y/L/R mapping table and test it; do not infer a unique mapping from the prose. |
| Clock and peripheral completeness | SYSTEM CLK, PHI2 and REFRESH are real socket signals in the verified map. All outer contacts, EXPAND, shared reset/CIC behavior and L/R analog input handling remain required; a 62-hole count is insufficient. |
| Power available from either host | Host limits, cartridge loads and exact FPGA demand are not specified. The M64 limiter annotation is not a guaranteed system budget. Determine whether supplemental USB play power is required and supported; initial USB programming power must work independently. |
| Conditional implementation choices | BRAM is preferred where practical; external RAM requires characterized deterministic timing. A multilayer PCB is mandatory, but the source permits a justified four-layer design and prefers six where beneficial. Alternates are required where possible, with no assumed pin-compatible substitutes. |

The source gives few numeric performance or abuse-test limits. Define, review and version the following before their acceptance runs; candidate numbers from design notes are not source requirements or universal manufacturer guarantees.

| Owner | Limits/protocol still to freeze |
|---|---|
| Power/protection | Rail windows/ripple, source margin, inrush/peak/steady load, trip and discharge timing, reverse leakage and power-order cases |
| Signal integrity/clocks | Logic levels/leakage, OE/DIR dead time, setup/hold, frequency/jitter/duty, overshoot/ringing/edges and representative loading |
| Firmware/A/V | Controller update/latency/stale-input handling; output formats, frame/dropout/synchronization and cartridge-audio mixing/clipping/noise criteria |
| Reliability/save integrity | Cold/warm/power-cycle counts, extended-runtime duration, fault/brownout profiles, interruption phases and byte/state comparison method |
| Mechanical/thermal | Fit/cable/eject clearances, insertion/extraction forces, cycles, side load/wobble/permanent set, ambient/load range and thermal margin |
| EMC/ESD | Test setup, operating modes, levels/limits, acceptable recovery and remediation/retest criteria |

For example, the provisional 4.75–5.25 V window in a candidate power note is not certified as every cartridge's allowed supply range. Freeze the actual device/system tolerance budget before using any such window as a pass criterion.

## Required acceptance-run records

The CSV is the acceptance **plan/register**, not a fabricated log of completed runs. Each later run should record:

- Run ID/date/operator and linked requirement IDs; hardware revision, FPGA build ID, firmware/tool/source hashes and image versions.
- Host model/motherboard revision/region/firmware, M64 stock or exact overclock setting, cartridge title/board/chip/region, and flashcart hardware/firmware/core/SD details.
- SNES NTSC/PAL mode separately from host and cartridge region; supply source, enclosure configuration, ambient/load and instrument/probe settings.
- Versioned procedure and predeclared limits, repetitions/runtime, raw captures/measurements/save comparisons, and per-check pass/fail/not-run results. “Not applicable” needs a reason.
- All eight §14.1 outcomes for each applicable target pair: cold boot, warm reset, controls, video, audio, saves, cartridge reset and extended runtime.
- Fault/recovery state, anomalies, follow-up fixes and the exact evidence reviewed for acceptance.

Preserve §13 ordering: unpowered inspection, isolated current-limited bench power, rails/safe image, host fixture, dummy cartridge load, clocks/buses, diagnostic ROM, progressively more capable real cartridges, both hosts, and fault injection before extended compatibility testing. Do not attach valuable host/cartridge hardware before the fixture and protection checks that precede it.

Coverage verification for this revision checks unique IDs, all 110 original source items represented with matching source text, all 16 compatibility subclasses and all 10 user entries, and no accepted/measured row without evidence. This is a completeness check of the register, not verification of SN64 hardware.
