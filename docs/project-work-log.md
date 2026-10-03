# SN 64 project work log

This log records engineering artifacts, evidence and publication. It does not certify working hardware or manufacturing readiness. Every target in [specification Rev A](../SN_64_Engineering_Specification_Rev_A.docx) remains in scope, subject to the explicit user decisions recorded in the [engineering plan](superpowers/plans/2026-09-28-sn64-engineering-plan.md).

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

## 2026-09-29 — GitHub publication

Published the current design and earlier reference/interface work as [draft pull request #1](https://github.com/FantomZap/SN-64/pull/1), branch `codex/usb-programmer`. A fresh Git fetch verified that the published design commit `d3db0f4f9429eb83c969087c73f5e3363d037a52` and local design commit `7094cacce50dbb26ff0d79bc2e650ac01cc8259c` have the identical file tree `20c06d39eb0ad66bb94ad47702d34fa73e29d65c`.

The main project folder contains the new work. GitHub's `main` branch remains at the earlier reviewed baseline; the complete current draft is on the linked pull request. Local commit history was retained. Publication used the connected GitHub app because command-line Git had no usable login, so the remote publication commit differs from the local development commits while preserving identical files. This work-log entry is a subsequent documentation update to that same pull request. No files were sent to PCBWay and no manufacturing order was placed.

## 2026-09-29 — Console evaluation, mechanical references and full requirements

- Created the [136-entry requirements register](requirements.md), retaining every one of the original document's 110 items, 16 compatibility refinements and 10 user clarifications. Partial design/simulation evidence remains separate from acceptance; no product or hardware requirement is marked accepted.
- Vendored 35 pinned SNESTang source/license files and added an auditable preparation script, memory wrapper and original diagnostic. The [current evaluation](../fpga/reports/evaluation.md) passes reset/native CPU, cartridge reads/writes, WRAM, raw mirror addressing, B-bus write, A-to-B DMA and PHI2 activity in 1,336 master clocks. Both PAL mode-bit values pass at the same test clock; this does not validate PAL clocks/video. An injected bad cartridge read produces the intended assertion failure.
- Independent review found upstream's open TURBO input and converted WRAM mirror address on the exported bus. Each issue was demonstrated before correction. Generated patches now tie normal speed low and export the raw CPU/DMA/HDMA address separately, retaining the core's internal memory path. [Physical D-bus ownership and further bridge work](design/physical-cartridge-bridge.md) remain open.
- Installed official portable OSS CAD Suite 20260928 and w64devkit 2.10.0 after checking their release-asset SHA-256 digests. Recorded tool versions and the Windows Make/path and XAIGER compatibility choices. The full current run synthesizes to 27,817 LUT4, 10,775 FF and 139 EBRs; trial ECP5-85F/BG381 grade-6 routing reaches 27.99 MHz against 21.477273 MHz. Arbitrary trial I/O and the incomplete system mean this is internal feasibility evidence only.
- Created two editable [FreeCAD reference models](../mechanical/README.md) with STEP and closed STL exports: the complete 62-hole Sanni pattern coupon and SummerCart64 board outline/thickness/mounting reference. Native solid/parameter checks and STEP round-trip checks passed; a separate root review checked six file hashes plus STEP validity, STL closure and native reopen/recompute. No socket, cartridge or host fit was physically tested.
- Strengthened the mechanical importer after review: both source hashes and revisions must match the trusted project manifest before parsing or writing. A regression first reproduced acceptance of modified source, then passed after the fix: both altered input files are rejected and existing datums remain untouched. Online socket leads are recorded, but no exact production socket has a qualified body/seating drawing yet.
- Recorded [power architecture](design/power-architecture.md), [FPGA availability/reuse](design/fpga-board-selection.md) and [system architecture](architecture.md). The M64 cartridge limiter's 500 mA setting is not a guaranteed load allocation. The user's M64 USB-port power idea is included: a short C-to-C cable is a candidate, while published standard-current advertisement, enumeration/startup policy and actual loads still need qualification. Unknown flashcart currents stay blank, not zero.
- Fresh existing KiCad checks passed again: 30 cartridge-interface and 64 USB static checks, zero failures. The USB circuit itself remains revision 0.2; the new power architecture still needs to be drawn and integrated. Nothing was ordered or sent to PCBWay.

These changes form the next engineering checkpoint for the existing draft pull request. Sources, generated reference models, reports and next tests are retained together; this checkpoint does not complete the multi-stage implementation plan.

## 2026-09-29 — First physical-bus data correction and evidence audit

- Continued the existing plan in the isolated `codex/cartridge-bus` worktree, starting from published checkpoint `f75c0e1201be7fe15c7889237ee1bf264077ba50`. The original project folder was clean and its file tree matched that published checkpoint before this work began.
- Audited the pinned OpenSFC netlist and original SNESTang WRAM logic. The [bus evidence note](design/bus-electrical-evidence.md) records exact source revisions, shared D0–D7 connectivity, a representative pin list and the distinction between primary motherboard evidence, upstream functional logic and secondary descriptions. Shared topology supports current WRAM read data reaching the cartridge contacts; it does not establish measured original-console timing.
- Corrected the earlier proposal to export all CPU-internal register reads onto the physical cartridge bus. Internal readback alone does not establish external drive. Ordinary CPU-register reads, DMA involving CPU registers and PPU-internal retained bits remain separate evidence/verification questions. The bridge contract and implementation plan now reflect that correction.
- Preserved a [machine-readable source-net extract](research/snes-data-bus-net-evidence.json) with all eight complete data nets, component values, original schematic/netlist SHA-256 hashes, source revision and export-tool identity. Each net contains the seven functional endpoints and its test point; no physical continuity or waveform measurement is implied.
- Added an original cartridge-output diagnostic before changing the data path. The [preserved failure](../fpga/reports/wram-regression-development.txt) shows stale `$7E` during a read expecting `$A5`. The candidate now selects current WRAM Q during its CE/OE read window and qualifies `cart_wram_read_valid` with reset and enable. The flag describes one data source; it does not implement translator OE, contention prevention or fault gating.
- The new diagnostic passes in 1,089 master clocks: direct WRAM reads, both low-memory mirror classes, two RAM data-port reads, two-byte B-to-A DMA and immediate source-valid disable under reset/pause with the master clock stopped. Added it to the reproducible evaluator beside the existing boot, PAL mode-bit and corrupt-read runs. Test programs are original diagnostic code; no commercial game image is included.
- Fresh-context independent review checked the upstream predicate, current test and source netlist, and reran the built WRAM diagnostic. It found no blocking issue. Remaining coverage includes a resolved physical-bus model, validity negatives across other responders, boundary cases, HDMA and hardware timing. These remain explicit next work rather than accepted compatibility.
- The fresh full evaluator completed successfully: both 1,336-clock boot mode-bit runs, the expected injected-read failure, the 1,089-clock WRAM regression, synthesis and trial routing. Current mapping uses 26,669 LUT4, 10,775 FF and 139 EBRs; the unconstrained trial ECP5-85F/BG381 grade-6 route reaches 29.91 MHz against 21.477273 MHz. Routing itself took 1,101.81 seconds. Each diagnostic compilation emitted 29 warnings, retained in the report. Verified all 38 recorded input hashes and all 11 command/log records before publication preparation. No external socket or final board timing is qualified by this result.
- Updated the bridge design, architecture, requirements evidence, plan checkpoint, FPGA documentation and document index together. The three partially simulated requirements retain `NOT_ACCEPTED`; all 136 requirements remain unaccepted. The user reiterated that sources, decisions, failures, tests and unresolved work must be retained in the project folder and GitHub.

The current [evaluation report](../fpga/reports/evaluation.md) and [JSON snapshot](../fpga/reports/evaluation.json) own exact build inputs, commands, results and limitations. Historical resource/timing figures above describe their original checkpoint; use the current report for the latest candidate.

## 2026-09-29 — Development moved to Claude Code; GitHub main updated

- Development continues from a complete copy of the Codex project folder: Git history, ignored research downloads, build evidence and the Codex worktrees' ignored scratch files. A hash comparison confirmed every original file is present and identical; only Git fetch metadata differs. The original folder is unchanged.
- Re-ran the existing checks from the new location. `evaluate.py --mode sim` passed both 1,336-clock boot runs (PAL flag 0 and 1). It rejected the injected corrupt read and passed the 1,089-clock WRAM regression. KiCad static checks again passed 30 interface and 64 USB checks. This repeats existing simulation/static evidence only; no hardware was tested.
- Published the full local development history to GitHub `main` as a fast-forward. Draft PR #1 held the identical file tree under different publication commits, so it was closed as superseded instead of merged.
- Added [CLAUDE.md](../CLAUDE.md) with working rules and check commands. The user handed project control to Claude and allowed replacing the named software where better-suited tools exist.
- Current tool assessment: keep KiCad, because PCBWay accepts it directly and every reused upstream board is KiCad. Keep the OSS CAD Suite ECP5 flow. New enclosure geometry may move to code-first build123d with STEP/STL exports, keeping the FreeCAD references. No tool change has been made yet.
- Recorded a quick [risk assessment](risk-assessment.md). Top risks are power, the video path, real-cartridge timing and BGA board layout. It recommends proving the cartridge path on development hardware before the custom board.

## 2026-09-29 — Physical cartridge bridge implemented in simulation

- Cross-referenced the pinned core's cartridge bus (`cpu.v` strobe generation and cycle counters, `SNES.v` data muxing, `P65C816.v` read-data latch point) with console-side hardware behaviour and wrote [sn64_cart_bridge.sv](../fpga/rtl/sn64_cart_bridge.sv): registered socket outputs gated by a hardware permission, a data-bus ownership state machine with a released clock at every owner change, look-ahead so turnarounds finish before the strobe edge reaches the cartridge, and one clock of write-data hold. Internal CPU-register reads are not exported, per the evidence audit. [Implementation notes](design/cartridge-bridge-implementation.md).
- Added a physical-bus testbench with a cartridge model that drives only when selected and a monitor that fails on contention, unpermitted output, missing write data or a missing turnaround. Passes in 1,411 clocks with 56 ownership changes and zero contention. A fault-injected build (turnaround removed) is rejected as required.
- Two bugs found and fixed during development: (1) deciding ownership from the delayed socket strobes shortened the effective write pulse; (2) the bench's SRAM model latched after the address had advanced. Both are recorded in the implementation note.
- `evaluate.py --mode sim` now runs seven checks. CIC, EXPAND, analog audio, HDMA/PPU/APU responder cases, fault-input wiring and hardware timing remain open.

## 2026-09-29 — N64/M64 host endpoint implemented in simulation

- Vendored SummerCart64's N64 PI controller, FIFO and bus interfaces unmodified (GPL-3.0, commit `a1e7996d`, [provenance](../fpga/vendor/summercart64/provenance.json)) and wrote [sn64_n64_endpoint.sv](../fpga/rtl/sn64_n64_endpoint.sv): a bootstrap ROM window at `0x1000_0000` and a mailbox register block at `0x1FFF_0000` for controller state, run request, status and build identity. The run request is cleared by host reset. [Implementation notes and register map](design/n64-endpoint-implementation.md).
- Added a host-model testbench driving the PI protocol (ALE_H/ALE_L latch, read/write strobes) with AD-bus ownership checks. Passes ROM burst/offset reads, mailbox read/write/readback and reset behaviour in 4,595 clocks. Added to `evaluate.py --mode sim`. Two host-model mistakes (ALE hold time, ALE order) were fixed in the bench and recorded as guidance for the bootstrap.
- CIC lockout (SummerCart64's soft-CPU implementation), /INT and the libdragon bootstrap remain open; the register map is the bootstrap's contract.

## 2026-09-29 — N64 CIC lockout and power-control state machine

- Vendored SummerCart64's CIC module, the SERV RISC-V core (ISC) and the UltraCIC_C-derived firmware (MIT), unmodified, and wired them into the endpoint as CIC-6102/7101 (seed `0x3F`, checksum `0xA536C0F1D859`). Installed the xPack RISC-V GCC 15.2.0-1 (checksum verified against GitHub's release digest) and added [build_cic.py](../fpga/tools/build_cic.py); the firmware uses 395 of 512 words. A console-side model now passes ID, seed and 64-bit checksum against independently computed references and enters compare mode; an altered expectation is rejected. [CIC notes](design/n64-cic-implementation.md).
- Design finding: the bit-serial soft CPU is too slow at 21.477 MHz; the endpoint now runs it from a separate 62.5 MHz PLL clock, as SummerCart64 does. The real PIF bit rate and phase gaps remain a hardware measurement item.
- Added [sn64_power_sequencer.sv](../fpga/rtl/sn64_power_sequencer.sv): ordered bring-up (reset held, 5 V, interface rail, reset release), combinational bus permission, shutdown on request loss or host reset, latched faults with codes and a deliberate clear. Its bench passes bring-up, shutdown, four fault classes and a rail timeout. [Notes](design/power-sequencer-implementation.md).

## 2026-09-29 — Parallel blocks: controllers, SNES CIC, N64 menu ROM; integration

Built by parallel helper agents with self-checking tests, then reviewed and integrated:

- **Controller path** ([notes](design/controller-path-implementation.md)): `sn64_snes_joypad` emulates two standard SNES pads from the mailbox images, reusing SNESTang's `controller_adapter.sv` unmodified (vendored with provenance). It forces the ID bits, keeps the multitap line idle (upstream's tie-low reads as a multitap, which is excluded) and supports an empty port. The serial protocol bench (82 cases) and a whole-core bench (auto-joypad and manual reads over two frames) pass; a B/Y swap is rejected. Default N64→SNES mapping v1 is frozen in the notes.
- **SNES CIC lock** ([notes](design/snes-cic-implementation.md)): original HDL written from published descriptions (segher's article, the Super Famicom dev wiki); no reusable code with a compatible, clean provenance was found. NTSC and PAL keys pass for four seeds, two cases match the wiki's reference program bit for bit, absent and corrupted keys are flagged, and two fault builds are rejected. Instruction-cycle timing is derived from SuperCIC and must be measured against a real key.
- **N64 bootstrap ROM** ([notes](design/n64-bootstrap.md)): libdragon toolchain installed without admin (checksum verified); the menu ROM (114,688 bytes) builds, its IPL checksum matches CIC-6102, mapping and ROM-tool tests pass with fault injection, and an endpoint co-simulation reads the image back and replays the mailbox traffic. Not yet run on an emulator or console.
- **Integration** ([notes](design/system-integration.md)): `sn64_top` connects all blocks across three clock domains with tested CDC helpers; `tb_system` passes the whole power-on sequence (STATUS `0x545F`) and found and fixed a /RESET deadlock. STATUS, FAULT and CONTROL layouts are reconciled between RTL and the menu.
- Design decisions recorded: the N64 endpoint runs from an always-on 62.5 MHz clock; the SNES master starts once at power-on at the detected region and never changes while running; a soft reset never removes cartridge power; the SNES CIC lock runs at 25 MHz / 8.
- Open: bootstrap ROM storage (64 block RAMs vs configuration flash or external RAM), A/V integration, board wrapper, ROM-header region fallback, whole-design place-and-route.

## 2026-09-29 — HDMI, round-2 blocks, board top level routed with real clocks

- **HDMI output** (720x480p frame-locked to the SNES, 32 kHz audio, [notes](design/av-output-implementation.md)) merged into `sn64_top`; the first whole-design place-and-route met all five clocks.
- **CIC data pins fixed in the schematic** (cart sheet rev 0.3.1): each CIC data pin has its own SN74LVC1T45 (U215/U216, LCSC C7843) with a dedicated DIR pin and provisional pull-downs; the shared-octet paths were removed. Cartridge checks 20/20 plus a 6-mutation negative test, ERC 0 errors (32 isolated_pin_label, 5 pin_to_pin), interface 30/30, USB 64/64. [sn64_cic_pad.sv](../fpga/rtl/sn64_cic_pad.sv) sequences DIR against the pad drive; its bench checks a translator model for contention (126 drive windows, none) and a fault build that switches both together is rejected.
- **ROM-header region fallback** ([notes](design/header-region-probe.md)): reads `$00:FFC0-$00:FFDF` twice with the cartridge held in /RESET and no SYSTEM_CLK; trusts it only if both reads match, the checksum pair complements, the map byte and country are known. Region priority is now forced > passing key CIC > valid header > NTSC. `tb_system` passes without a header (NTSC, STATUS `0x545F`) and with an EU header (PAL, `0x54DF`).
- **Bridge hardening:** the data octet's enable and direction are now also gated by bus permission combinationally, so they release even if the SNES clock has already stopped.
- **Bootstrap ROM from the configuration flash** ([notes](design/bootrom-flash.md)): SummerCart64 `memory_flash.sv` vendored unmodified behind the endpoint's ROM window. Bench with a QSPI flash model reads 1411 words in 15 bursts; 240 ns per word gives 1.53x margin at the standard ROM-header PI timing. Rule found: the menu must keep PI DOM1 LAT at the header's 0x40 (floor about 0x30) because the flash needs about 1 us for the first word.
- **Board top level** [sn64_board_top.sv](../fpga/rtl/sn64_board_top.sv): EHXPLLL 25 -> 62.5 MHz and pixel -> x5 (parameters from `ecppll`), one DCSC in glitchless falling-edge mode that both selects the NTSC/PAL master and starts/stops it (Lattice FPGA-TN-02200 Table 10.2: SEL 01 = CLK0, 10 = CLK1, 00 = held low), flash boot ROM through USRMCLK, CIC pads. Routed with trial constraints: all five clocks pass (SNES 27.3 MHz achieved vs 21.48 required); 41 % logic, 143/208 block RAMs. [Details](design/system-integration.md).
- Simulation suite: `evaluate.py --mode sim` passes all 30 recorded results, including every injected-fault run.
- Open: FPGA and power schematic sheets and the real pinout, clocks/HDMI/audio-ADC sheet, PAL HDMI raster, cartridge analog audio, header telemetry word, flash sysCONFIG/part selection.

## 2026-09-29 — Round 3: PAL HDMI, cartridge audio, telemetry, FPGA/power/A-V sheets, integration

Built by parallel helper agents with self-checking and fault-injection tests, then integrated into the shared files in one pass:

- **PAL HDMI 576p50** ([clock plan](design/clock-plan.md), [A/V notes](design/av-output-implementation.md)): 864x624 raster (CEA-861 VIC 17 timing with 624 lines so one 312-line SNES frame fills one HDMI frame), 4:3 AVI InfoFrame, pixel 27.0398584 MHz = PAL master x 108/85 from PLLB, MS2 31+13/27 (registers 58-65 = 00 1B 00 0D BD 00 00 11, register 18 = 0x2F), derived with Skyworks AN619 (SHA-256 recorded). `sn64_clock_init` rewrites only MS2 and register 18, never a PLL, and only while the SNES clock is stopped; the SNES clock waits for `pixel_clock_ready`. tb_clock_init passes and its new fault build (keeps writing after the SNES clock starts) fails; tb_av_out PAL passes (2,567,520 pixels exact, CTS 27288-27290) and a 625-line fault is rejected.
- **Finding (owner decision):** the prepared core's lines are 1360 master clocks in both regions (NTSC frame 356,320, PAL 424,320 clocks), not the 1364 the recorded NTSC 39/31 ratio assumes, so the NTSC HDMI raster re-phases every frame (about -1,328 px) and `av_locked` stays 0. The NTSC decision was not changed; options are in the clock plan.
- **Cartridge audio** ([notes](design/cart-audio-implementation.md)): `sn64_i2s_rx` oversamples the ADC's I2S lines at 62.5 MHz (sampling point justified from the 1996 Philips I2S spec, SHA-256 recorded); `sn64_audio_mix` crosses frames into clk_snes through an 8-frame elastic buffer that drops or repeats exactly one sample and adds them to the DSP stream with 16-bit saturation. Passes at ±500 ppm and at the core's real rate, also four-state in Icarus; four fault builds fail. Gain 1.0 and 0 dB headroom are provisional.
- **Finding (owner decision):** the pinned SNESTang DSP runs at 32,179.96 Hz (NTSC) / 31,886.43 Hz (PAL), not 32 kHz.
- **Region telemetry:** REGION_INFO (0x1A) and REGION_SOURCE (0x1C) mailbox words, snapshot at SNES clock start; the menu shows "Region: PAL via key CIC" and the header result; bootstrap rebuilt (114,688 bytes, CIC-6102 OK). `tb_system` now has the key CIC model on the CIC pins: a PAL key beats an NTSC header, an NTSC key beats a PAL header, and a corrupted key is rejected.
- **FPGA sheet** rev 0.4-fpga ([notes](design/fpga-schematic.md)): all 381 LFE5U-85F CABGA381 balls assigned; W25Q128JVSIQ configuration flash (LCSC C97521); master-SPI straps; PROGRAMN held until `fpga_rails_ok`; N64 edge through three host-gated SN74CB3Q3384A switches; the board pinout [sn64_board.lpf](../fpga/constraints/sn64_board.lpf) and pin-map CSV are generated from the same table.
- **Power sheet** ([notes](design/power-schematic.md)): TPS259470L priority mux of HOST_3V3 and USB_VBUS (USB allowed only when a TUSB320 sees 1.5 A or 3 A), TPS63070 5V_PRE, three TLV62569 FPGA rails, default-off cartridge eFuse and interface load switch, TPS3700/TPS3808/TMP302A monitors that read "not OK" when their supply is lost.
- **Clock/HDMI/cartridge-audio sheet** ([notes](design/av-clock-schematic.md)): Si5351A with a 25 MHz 10 pF crystal (matches register 183 = 0xD2, cross-checked from the RTL), 25 MHz FPGA oscillator, HDMI type-A with a TPD12S016 and ULX3S-style 22 nF TMDS coupling, PCM1808 I2S master at 384 fs from a 12.288 MHz oscillator (fs 32 kHz) behind a console-equivalent 196 ohm load and 0.5 gain. SNES audio is not routed to N64_AUDIO_L/R (no requirement).
- **Integration** ([details](design/system-integration.md#schematic-integration-round-3-2026-09-29)): the root (rev 0.4-r3, A2) now holds all five child sheets, every contract name wired by same-name labels; the USB sheet exports VBUS/USB_3V3/CC/JTAG/TARGET_VREF and R101/R102 are DNP (the TUSB320 presents Rd). Fixed on the way: about 80 duplicate designators between the FPGA and power sheets (FPGA sheet renumbered to 4xx in its generator), five duplicate PWR_FLAG ERC errors, and validator assumptions that only held for unattached sheets (each negative test still catches every fault; the FPGA JTAG check was tightened after a parallel USB-sheet pull masked one fault). Results on the real root: ERC 0 errors (5 isolated_pin_label on reserved N64 labels, 5 pin_to_pin unchanged); interfaces 30/30; USB 69/69 plus a fault injection; cartridge 20/20 and 6/6; power 23/23 and 11/11; A/V 30/30 and 12/12; FPGA 12/13 and 10/10; new root-connectivity check 4/4 (141 contract names) and 4/4. The PDF was regenerated but not visually inspected.
- **Integration finding (owner decision):** `efuse_fault_n` comes from a 12.1k/20k divider on 5V_PRE (a recorded power-sheet choice) and reaches FPGA ball K4, which the FPGA sheet's 5 V rule rejects; it is the one failing FPGA check. Also pending owner review: cartridge enable pull-ups R206-R208 10k vs 4.7k (FPGA sheet finding) and the TLV62569 input from 5V_PRE (power sheet).
- **RTL integration:** the PAL HDMI and cartridge-audio edits merged into `sn64_top`/`tb_system`/`evaluate.py`; `sn64_board_top` gained the pad adapters the schematic needs (cart_data inout, open-drain Si5351 I2C, cart_reset_pull_n, expand_sense, reserved JOYBUS/INT/HPD/DDC, adc_*). `route_top.py --top board` now uses the real LPF: all five clocks pass (SNES 28.94 MHz vs 21.48, host 86.26 vs 62.5, TMDS 170.85 vs 135.21; `si_clk2` constrained at the PAL 27.0399 MHz), 121/365 I/O, 43 % logic, 143/208 block RAMs.
- **Simulation suite:** `evaluate.py --mode sim` exit 0 with 86 recorded commands; all 23 non-zero exits are the intended fault injections.
- Open: board-level I/O timing, footprints left empty on purpose (eFuse, TPS63070, inductors, J701 -111RLF variant), PCB/SI/PDN, `sn64_pnr_wrap.sv` still lacks the ADC ports, license notes in `hardware/sn64/THIRD_PARTY.md` for the new ULX3S facts.

## 2026-09-29 — Two SNES core timing bugs fixed; HDMI locks in NTSC

- **Long dots (video timing).** The SNESTang Verilog port turned MiSTer's `H_CNT = 323 or H_CNT = 327` into `H_CNT == 323 && H_CNT == 327`, which is never true. Every scanline was 1360 master clocks instead of hardware's 1364, so the console ran about 0.3 % fast (60.27 Hz instead of 60.10 Hz) and scanline-timed behaviour differed from a real SNES. The bug is still on SNESTang master. `prepare_core.py` now patches the generated copy; measured afterwards: NTSC frames alternate 357,368 / 357,364 clocks (hardware short line), PAL frames are 425,568.
- **Audio rate.** SNESTang raised the S-DSP clock-enable target by 0.5625 % (`ACLK_FREQ 411904`, the original 409600 kept commented out) and divided by the NTSC master even in PAL. The DSP ran at 32,179.96 Hz (NTSC) / 31,886.43 Hz (PAL). Patched back to MiSTer behaviour: 32,000 Hz in both regions, so pitch and tempo are right and the 32 kHz cartridge-audio ADC almost never slips.
- **HDMI pixel clocks.** NTSC MS2 = 31 + 14887/18733 (27.0199459 MHz): one 858 x 524 frame equals the mean SNES frame, so the raster never re-phases; `LOCK_TOL` 2 -> 8 pixels absorbs the ±5-pixel short-line wobble. PAL MS2 = 31 + 31/54 (26.9605626 MHz, 50.007 Hz). `tb_system` now checks frame lock in NTSC too, with exact clock ratios.
- **Power/schematic decisions closed.** `efuse_fault_n` pulled up to FPGA_3V3 (a 5V_PRE divider would back-drive a non-hot-socket ECP5 bank, DS-02012 section 3.6); cartridge enable pull-ups 10k -> 4.7k (ECP5 configuration-time pull-down up to 150 µA, Table 3.7); FPGA bucks fed from 5V_PRE accepted (a buck cannot make 3.3 V from the host's 3.3 V).
- Sources: MiSTer `SNES_MiSTer` commit `c61bfd45171c62000417333cd4679890bcd091a6` (`rtl/PPU.vhd` lines 323-324, `rtl/DSP.vhd` lines 238-247).

## 2026-09-29 — Console video path: frames and audio to the N64 over the cartridge bus

- **Decision (owner):** the SNES picture and sound go to the console through the cartridge bus and the boot program shows them on the console's own output (N64 AV jack, M64 HDMI). This is the primary A/V path; the board's own HDMI is secondary and is to be removed unless kept on purpose. Design: [console-video-path.md](design/console-video-path.md).
- **FPGA side done in simulation:** `sn64_frame_window` (RGBA5551 frame buffer + audio ring) behind the vendored PI controller's SRAM window at `0x0800_0000` (PI domain 2, fast timing), three new mailbox words. Bench: a full frame reads back exactly at 128 ns/word (15.6 MB/s, 2.3× the 60 Hz need) while following the line counter; R/B-swap fault build fails; whole-system runs read frames from the real core in NTSC and PAL. Suite: 42/42.
- **Next:** the boot program's display loop (libdragon: PI domain-2 timing, frame DMA following `lines_done`, VI 256×224 16-bit, AI 32 kHz), then HDMI removal from the schematic/board, then routing.
- **PCB:** six shell-screw holes (2.5 mm), corrected SummerCart64 outline, connectivity-pulled placement.
- Setback acknowledged: the HDMI output block and its schematic corner were built on the spec's "independent digital output" line without confirming intent with the owner.

## 2026-09-29 — On-board HDMI output removed; the console output is the only video path

- **Decision (owner):** the SNES picture and sound must reach the TV through the console's own output (M64 HDMI, N64 AV jack) by way of the cartridge bus. The board's own HDMI port, built on the spec's "independent digital output" wording without confirming intent, is removed rather than kept as a secondary output. Retirement record: [av-output-implementation.md](design/av-output-implementation.md).
- **FPGA:** deleted `sn64_av_out`, `sn64_av_hdmi_tx`, `sn64_av_serializer`, `tb_av_out` and the vendored hdl-util/hdmi tree. `sn64_clock_init` no longer programs MultiSynth 2 or retargets CLK2: CLK2 stays powered down, register 3 = 0xFC, nothing is written after start-up, and the SNES clock waits only for lock and the region decision. The board top keeps one EHXPLLL (host) and loses `si_clk2` and the `hdmi_*` ports. `evaluate.py --mode sim` exit 0, 38 recorded results (the clock-init bench was rewritten: register image with CLK2 off, region latch stopped/running, zero I2C STARTs after start-up; the `+wrong_addr` negative run stays). Routed on the real pinout: 203/208 DP16KD, 113/365 I/O, 41 % logic, 1 PLL; host 72.5 MHz vs 62.5, SNES 26.7 vs 21.5, housekeeping 57.4 vs 25, all pass.
- **Schematic:** FPGA sheet rev 0.5-fpga (12 ports fewer: the four TMDS pairs, HPD/DDC and `si_clk2`; bank 1 spare; LPF and pin-map CSV regenerated from the same table), A/V sheet draft 0.2-av (J701, U702 TPD12S016, C704-C714, TP701, R705 gone; Si5351 pin 6 open with a no-connect), both root sheet symbols re-packed by a one-off script. ERC 0 errors and the same 10 warnings as before. Checks on the real root: interfaces 31/31, USB 69/69, cartridge 20/20 (negative 6/6), FPGA 14/14 with the Lattice CSV (negative 10/10; new check: no HDMI or `si_clk2` port in the LPF or board top), power 23/23 (negative 12/12), A/V 27/27 (negative 10/10; new check: CLK2 open on the sheet and disabled in the RTL, with a mutation that wires it back), root connectivity 4/4 (negative 4/4), socket joint 9/9 (negative 3/3). Power budget rows PWR-L37/L38 (HDMI +5 V, TPD12S016) removed.
- **Board:** rebuilt from the new netlist by `build_main_pcb.py` (410 parts, 530 nets; the right-edge zone that held the HDMI receptacle is free). The first rebuild left two 10 uF capacitors and a test point overlapping on the bottom side, so the FPGA-support bottom zone was widened; DRC now reports only the USB-C receptacle pads at the board edge (by design) and the N64 fingers' shared solder-mask opening (SummerCart64 footprint), no shorts or courtyard overlaps. Renders and the PDF regenerated. Still nothing routed.
- **Docs:** clock plan, FPGA schematic, system integration (new "HDMI output removed" section with the route numbers), cartridge audio, console video path, architecture, risk assessment, requirements register, acceptance matrix rows SN64-07-01/09-01, READMEs, THIRD_PARTY and CLAUDE.md updated; the retired HDMI sections in the clock plan are marked as such rather than deleted.
- Cost of the detour: about one evening of HDMI work; what survives is the two SNES core timing fixes found while locking the raster and the cartridge-audio path, which now feeds the console.

## 2026-09-30 — First routed draft of the main board

- **Preparation (scripted, KiCad python):** 240 dog-bone fan-out vias for the caBGA-381 (0.45/0.2 mm, 0.4 mm diagonal), GND plane on In1, FPGA_3V3 plane on In3, FPGA_1V1 island on In4, power/usb net classes, keep-out over the N64 finger tongue, plane vias beside plane-net pads where a spot is free. Decoupling moved out of the via field after the first fan-out landed on it; FPGA rotated 180° after the first autoroute left the whole N64 bus unrouted (bank 0 faced away from the bus switches); hole-to-copper relaxed to PCBWay's 0.2 mm.
- **Routers tried:** Freerouting 2.4.1 (local API server; single-threaded per run, time-slices jobs in one instance, so a second instance was scripted): about 335 nets after 2 h 20 min. KiCadRoutingTools v0.22 (Rust A*, per-user install): all 375 signal nets attempted in 5 min, 300 connected in 30-60 min; its default "fab tier" escalation narrowed 4,280 features below the board rules until pinned with `fab-pcbway.txt`; placing plane vias before routing (run 3) cost 90 signal nets; its plane-tap pass and a Freerouting finishing pass on its output both reverted or degraded the board.
- **Result on the tracked board:** run 2 routing + 157 plane vias + outer pours; DRC has no shorts, crossings, clearance or hole errors (18 USB-C edge pads by design, 79 starved thermals, N64 finger mask). Open: 75 signal/power nets (95 connections) and 219 plane pads. Renders and the open-connection list are in `hardware/sn64/exports` and `validation`. Notes: [pcb-routing.md](design/pcb-routing.md).
- **PCBWay capability check (2026-09-30):** hole-to-copper 8 mil, edge 0.25 mm, via drill 0.15 mm, annular 6 mil (board vias have 0.125 mm), trace/space 4/5 mil (board spacing 0.1 mm). Annular ring and spacing must be settled with the quote before the final layout pass.
- **KiCad 10 python finding:** `PCB_VIA.GetWidth()` without a layer argument raises an internal assertion that opens a hidden dialog and hangs the process; `board.Remove()` leaves later lookups as bare SWIG pointers in the same process. Both recorded in the scripts.
- Cost: the night of 2026-09-29/30. The owner asked for speed; the honest lesson is that autorouting a 381-ball BGA board on a block-zone placement leaves a fifth of the work for hand routing whichever tool is used, and that the placement (translator row) is the next thing to improve, not the router.

## Remaining work

Select and validate the FPGA/storage and physical-cartridge bridge, complete system/cartridge power and protection, N64 endpoint, controller/firmware functions, clocks, A/V and diagnostics. Retain PAL and the required M64 single-HDMI target; its supported integration mechanism remains unresolved. Complete PCB placement/routing and the FreeCAD enclosure, then perform electrical, programming, compatibility and fit tests on prototypes before producing a PCBWay release. No working SN 64 hardware or fabrication-ready package exists yet.

## 2026-09-30 — v2 board: FPGA absorbs USB, clocks, telemetry and audio; passive riser (branch `v2`)

Owner request (2026-09-30): fully optimise for fewer SMD parts and lower power, everything except the FPGA; make the whole v2 first, test once, write up the schematic, autoroute. Write-up: [v2-board.md](design/v2-board.md).

- **Schematic** ([hardware/sn64-v2](../hardware/sn64-v2), generated by `tools/build_v2_schematic.py`, three child sheets wired by global label; [riser](../hardware/sn64-v2-riser) with the N64 edge and a 2x20 header only). 176 parts on the main board (16 ICs, 62 R, 79 C, 3 L, 1 oscillator, 1 LED) against 380 in v1. ERC: 0 errors, 8 warnings (unused translator inputs tied to ground); riser ERC clean. Drawn symbols (TPS2121, TLA2528, TPS2553) from the TI pin tables via the LCSC pinouts, recorded in `libraries/v2-provenance.json` with the stock snapshot; the v1 libraries (socket, N64 edge, TPS63070, JAE USB-C) are reused unchanged.
- **FPGA pin plan** (`tools/pin_plan.py`): 111 signal balls, all on rings 1-3 (47/41/23), banks facing their connectors; the LPF is generated from the same table.
- **FPGA logic**: `sn64_board_top.sv` rewritten for one 27 MHz oscillator and three PLLs (NTSC exact, PAL +335 ppm, 48/61.7/12 MHz); new `sn64_sd_adc.sv` (sigma-delta cartridge audio), `sn64_rail_monitor.sv` (I2C to the TLA2528, thresholds in logic), `sn64_usb_prog.sv` (TinyFPGA bootloader core on two pins, vendored under `fpga/vendor/tinyfpga-bootloader`, Apache-2.0; generated copies under `build/generated/tinyfpga` for the synthesis front end); `sn64_bootrom_flash.sv` shares the flash between the boot-ROM reader and the USB programmer with one driver per pad through a generated split-pad copy of SummerCart64's `memory_flash` (`fpga/tools/prepare_flash_pads.py`); `sn64_clock_init.sv` and its bench removed. Simulation (`evaluate.py --mode sim`): every bench passes, including the four whole-system runs and the new `tb_sd_adc` (three DC levels within 1.6 % of full scale); the system bench's audio check now allows the modulator's 0.8 % noise. Not hardware evidence.
- **FPGA synthesis and route** (`route_top.py --top board --speed 8`, the grade in stock): 30,721 LUT4, 13,242 flops, 203 of 208 block RAMs, 3 PLLs, 111 I/O on the v2 pin plan; every clock meets timing (SNES 36.4 MHz achieved vs 21.48 needed, host 108.7 vs 61.7, USB 186.6 vs 48, 92.9 vs 12, oscillator 81 vs 27). Snapshot: [fpga/reports/v2-board-route.json](../fpga/reports/v2-board-route.json). First attempt had the PLL feedback formula wrong (outputs computed at the VCO rate); fixed to feedback-from-CLKOS dividers: NTSC exact, PAL 21.280788 MHz (-27 ppm).
- **Boards**: `tools/build_v2_pcb.py` places both boards (104 x 64 mm six-layer main board; 64.5 x 34 mm two-layer riser with the SummerCart64 tongue); `prepare_route_v2.py` fans out the FPGA (210 vias against 326 in v1) and adds the GND / 3.3 V planes and the 1.1 V island; KiCadRoutingTools routes (riser: 30/30 nets, DRC clean apart from silk and the shared finger mask).
- **Main board routing** (`build/route-v2/`): plane vias placed before routing (`add_plane_vias_v2.py`, 258 vias + links, one pad left), then one KiCadRoutingTools pass of 40 s: 212 of 218 signal nets (v1: 6 min for a first pass and 75 nets open at the end of the night). Rip-up passes on the six leftovers traded nets for other nets and were discarded; the pass-1 board was finished (outer GND pours, 1.1 V island extended over its regulator on the otherwise empty In4). **Result: 3,588 tracks, 922 vias, 7.5 m of track, DRC 0 errors apart from 5 single-spoke thermal reliefs; 7 open items for hand routing** (N64_AD6, N64_AD7, USB_PU, AUD_L_N, FLASH_D2, one SNES_5V_CART segment, the TLA2528 DVDD pin), listed in [validation/pcb-open-connections.json](../hardware/sn64-v2/validation/pcb-open-connections.json). Renders in `hardware/sn64-v2/exports/`. Not hardware evidence; the board has not been checked against PCBWay's quote rules (annular ring, spacing) any more than v1.
- Cost: 2026-09-30, one working day solo, no agents.

## 2026-09-30 — v2 as one board (owner decision), cartridge flat

The owner rejected the two-board arrangement ("i want 1 board") and, after the socket constraint was explained (every SNES socket needs a horizontal mounting surface; no right-angle part exists; upright-in-line needs a soldered socket strip or rigid-flex), chose one flat board with the cartridge lying flat. Riser project deleted; the N64 edge (SummerCart64 geometry) is on the main board. Conversion kept the routing: the finished v2 board was turned 180 degrees, the 40-pin joint replaced by the edge fingers, the outline changed to the SC64 profile (70 mm above the shoulders, 1.2 mm), three parts moved inside it, the finger keep-out rebuilt as strips between the fingers with a stub up each finger, and only the thirty finger nets plus the USB corner were re-routed. Result in [hardware/sn64-v2](../hardware/sn64-v2): 3,612 tracks, 997 vias, 211 of 218 signal nets, DRC 0 errors apart from 6 single-spoke thermal reliefs and the USB-C shield pad on the edge; 7 nets for hand routing listed in [validation/pcb-open-connections.json](../hardware/sn64-v2/validation/pcb-open-connections.json). Renders in `exports/`. Write-up updated: [v2-board.md](design/v2-board.md). Lessons recorded: KiCadRoutingTools honours KiCad rule areas (a keep-out over the finger pads makes them unreachable) and treats filled pours as walls (route before pouring); KiCad 10's python breaks lookups in a process after `board.Remove()` (do removals in their own step).

## 2026-09-30 — v2 shell envelope, first look (before any board change)

The owner asked for the shell before the board is resized and wanted to see it in 3D ("i strictly need to see the 3d shell for myself before anything"). First envelope model in build123d: [mechanical/sn64-v2-shell/sn64_v2_shell.py](../mechanical/sn64-v2-shell/sn64_v2_shell.py), write-up [docs/design/v2-shell.md](design/v2-shell.md). SummerCart64 outer width and thickness (116.1 x 18.06, from its shell STEP), tongue opening in the bottom, socket window in the front wall, USB-C window in the right wall 50 mm above the shoulders (22 mm above an assumed 28 mm console line), a 3 mm tray with rails and two ribs under the flat cartridge; board drawn 18 mm higher than the committed one (socket at 74.5, top at 85) as the proposal. Exports: STEP with named bodies, STL, four renders. Assumptions are listed in the script header and the write-up (console line, socket height, cartridge envelope, plug envelope). Finding for the owner: the 116.1 mm shell leaves a board-edge USB-C about 7 mm inside the right wall; the board must widen above the console line (about 110 mm) or the wall must step in. Nothing on the board changed; the board resize waits for the owner's review.

## 2026-09-30 — v2 shell: upright tower (flat cartridge rejected)

The owner rejected the first shell model on sight. It laid the SNES cartridge flat on a shelf out of the board's front face, which followed from the face-mounted socket, not from anything he asked for; he wants one continuous vertical item with the cartridge upright on top. Offered three ways to get it: a snap-off socket strip on the same panel, an in-line straddle connector, or rigid-flex. He chose the in-line straddle with the console-replacement socket with ears screwed into the plastic shell, and said the tails not reaching the board faces will be handled by a small board redesign.

Sourcing (web search, no orders): the eared 62-contact socket is sold as a console repair part (NES Repair Shop `snspt043`; Shenzhen Co-Growing "SNES-Slot" with or without ear, MOQ 50; Hexir `HXR-19-18637`; Amazon listings). None publishes a drawing and no 3D model was found. Geometry stays sourced from the OpenSFC console footprint (99.0 x 11.25 body, holes 95.0 apart, rows 7.0 apart, 2.5 pitch with two 7.5 gaps, 85.0 first to last); one listing's 137 mm "with ear" length conflicts with the hole spacing, so a measured sample decides height, nose, tails and ears. No stock straddle-mount card-edge connector matches: the 2.54 mm contiguous parts (EDAC, Sullins, TE, KEL) have no gaps and cannot take the outer contact groups, which carry cartridge audio on pins 31 and 62.

Model rewritten as the tower ([mechanical/sn64-v2-shell/sn64_v2_shell.py](../mechanical/sn64-v2-shell/sn64_v2_shell.py), write-up [docs/design/v2-shell.md](design/v2-shell.md)): SummerCart64-width stem, socket on the board's top edge at 70 mm with its ears on two shell brackets, USB-C in the right wall 22 mm above the assumed console line, then (at the owner's request, "more mushroom shaped to add support for the inserted snes cart") a bell flare from 57.5 to 68 mm into a 142.6 x 26.6 mm cap whose 20 mm pocket holds the cartridge on all four sides; cartridge top 136.5 mm above the console line. Shell 142.6 x 109.5 x 26.6 mm, walls 2.0 to 2.9 mm through the flare, all six bodies valid, no overlaps; STEP/STL and FreeCAD renders. Board changes it asks for are listed in the write-up and not made yet. Also corrected [cart-audio-implementation.md](design/cart-audio-implementation.md): cartridge audio is on pins 31 and 62, not 31/32.

## 2026-09-30 — v2 board refitted to the tower shell, SNES socket on the top edge

Owner: "make the pcb and include the snes female connector ... you already have the pcb but you know, make it fit the 3d model thing". The routed board was changed in place by [refit_tower_v2.py](../hardware/sn64-v2/tools/refit_tower_v2.py) instead of a new layout:

- New footprint `SN64_V2:SNES_Slot_Console_Straddle` ([make_socket_footprint.py](../hardware/sn64-v2/tools/make_socket_footprint.py)) with a 3D model of the eared socket ([socket_3d_model.py](../hardware/sn64-v2/tools/socket_3d_model.py)). Orientation checked against sources: N64 edge pin 1 is on the front row of the slot (n64brew "Game Pak") and sits on B.Cu here, so B.Cu faces the player; SNES pins 1-31 face the front with pin 1 at the left end seen from the front (SNESdev wiki; OpenSFC SHVC-CPU-01 P1 against its controller connector). Pins 1-31 therefore go on B.Cu at the old x positions; a mirrored footprint would have put the cartridge's +5 V contacts on the ground pads. The footprint lives in a v2-only library because the schematic generator re-copies `SN64.pretty` from v1; the generator now points J2 at it (schematic diff: J2's footprint and note only).
- Clear stage: removed the face socket and all copper above the translator row (socket nets only), cut the five USB-C nets at the old connector (685 items in all), and trimmed 226 dangling leftovers. Place stage: new outline (111 mm wide 32-60 mm, 88 mm neck to 70 mm), J2 on the top edge, USB-C with its ESD part and VBUS capacitor at the right edge 50 mm up (connector turned outward, JAE 0.5 mm overhang; series and pull-up resistors stay beside the FPGA), H5/H6 to 38 mm, planes enlarged, every existing track and via locked. 22 plane vias added, then KiCadRoutingTools routed the 64 affected nets.
- Result: 3,551 tracks, 1,034 vias, 213 of 218 signal nets fully connected, 6 unconnected items (FLASH_D2, FPGA_3V3, N64_AD6, N64_JOYBUS, USB_DP_F, USB_PU); DRC errors: 5 starved_thermal. Fit check: the KiCad board STEP with all part models has no interference with the shell or the cartridge.
- Router lesson (recorded in pcb-routing.md): the first run broke 7 good nets and a second run with `KICAD_RIP_PREEXISTING=0` still broke 5, because the end-of-run reconciliation rips "hinted blockers" anyway and because the first cut had removed the FPGA-side USB escapes. Keeping the series resistors and their routing beside the FPGA and **locking every existing track and via** (KiCadRoutingTools never rips locked copper) gave 64 of 64 nets with nothing broken. The router also writes relaxed floors into its output `.kicad_pro`; DRC was run against `sn64-v2.kicad_pro` instead.

## 2026-09-30 — v2 shell: real N64 cartridge body, rounded cap

The owner sent photos of an N64 cartridge (port, front, top, back) and asked that the part that plugs into the console look like it ("cant you just reuse part of an n64 cart stl") and that the mushroom cap have "smoother rounder edges" in line with Nintendo's own design choices.

- SummerCart64's shell STEP turned out to be in our frame already: origin at the board's shoulders, centred, mounting bosses at (+-47.5, -3.25) like H1/H2; only its board plane is 0.6 mm off ours. Measured on it: body 116.12 x 18.06 x 76.6 mm, flat back with 1 mm corners, 9 mm front corners, two 0.8 mm grooves on the label face, 2 mm walls, top arc radius 158.5 mm.
- [sn64_v2_shell.py](../mechanical/sn64-v2-shell/sn64_v2_shell.py) rebuilt: the real shell below 24.5 mm (port, feet, ledges, bosses), its outline extruded as the stem, an S-curve flare (checked monotonic with one inflection), and a cap with the same 9 mm front corners, an arched rim, a 2.5 mm rim fillet and a chamfered pocket lip. One valid solid, 146.6 x 110.3 x 30.6 mm. Derived work, so CERN-OHL-S-2.0 ([mechanical/README.md](../mechanical/README.md)).
- Fit: the KiCad board STEP with all part models plus an FPGA envelope has no interference. Two SummerCart64 features had to go: a support post under our FPGA, and 1.3 mm of the right locating post (our board mirrored the left notch; SummerCart64's right notch starts lower).
- Data point: SummerCart64's own USB-C opening starts 25.8 mm above the shoulders, so the console top line is below that; the model now draws it at 25 (was 28).
- New open item, a safety one: the cap pocket is a plain rectangle, so a cartridge can be inserted back to front, which swaps its 5 V and ground contacts; the pocket needs the console's keying. Write-up: [v2-shell.md](design/v2-shell.md).

## 2026-10-01 — a measured US SNES cartridge in the slot; socket nose corrected

Owner: "now we need a snes cart one for the cartridge slot up top to be sure the socket geometry is correct". No open North American shell model with a usable license turned up (the GitHub reconstruction found is CC BY-NC-ND and calls its dimensions estimates; the Super Famicom meshes already in `mechanical/downloads` are hobby models), so the cartridge is built from caliper measurements published on the NESdev forum (rainwarrior, t=23890) and cross-checked against the SNES Jr console connector model from kicad-snn-cpu-01 that was already on disk. Both are recorded in [dimensions.md](dimensions.md).

- [sn64_v2_shell.py](../mechanical/sn64-v2-shell/sn64_v2_shell.py): `us_cartridge()` (middle and side sections, rear notches, front slot, card-edge hole, 62-contact PCB edge) and `interface_checks()`. All 31 contacts per side land on the measured PCB edge with 1.45 mm to spare; the nose has 1.3 / 1.08 mm clearance in the 97.5 x 10.9 hole; contacts overlap the edge by 8.55 mm; the real board, FPGA envelope, cartridge and its PCB do not interfere.
- Error caught: the socket nose had been guessed at 88 x 9 mm, narrower than a 62-contact cartridge edge (89.9 mm). Nose now 94.9 x 8.75 x 10.55 (SNES Jr connector model) in the shell model and in the board's socket 3D model and footprint outline; board DRC unchanged (5 single-spoke thermal reliefs, 6 open items).
- Pocket sized for the US cartridge without region tabs, so Super Famicom and PAL cartridges fit too (owner's question). The cap is now centred on the pocket, 1.45 mm toward the label side, which rests on an assumption.
- Open: two caliper readings on a real cartridge (back face to PCB, bottom face to PCB edge); write-up in [v2-shell.md](design/v2-shell.md).

## 2026-10-01 — licences, attribution notice and credits

The repository turned out to be public already (created public on 2026-09-29; one account with write access). A scan of all four branches and the full history found no keys, tokens, passwords or e-mail addresses, and the reference downloads and local scratch folders were never uploaded; the Windows user folder name does appear in paths in 24 files. The owner then chose the licences and an attribution line:

- Code (`fpga/`, `firmware/`): GPL-3.0-or-later, forced by the GPL-3.0 SNES core and N64 bus controller it is combined with. Hardware (`hardware/`, `mechanical/`) and `docs/`: CERN-OHL-S-2.0, forced for what derives from SummerCart64 and OpenSFC. Texts at the top level, unmodified copies of the ones already vendored: [LICENSE-GPL-3.0-or-later.txt](../LICENSE-GPL-3.0-or-later.txt), [LICENSE-CERN-OHL-S-2.0.txt](../LICENSE-CERN-OHL-S-2.0.txt); guide in [LICENSING.md](../LICENSING.md).
- Attribution: "SN64 by FantomZap", source location the GitHub repository. [NOTICE](../NOTICE) states it as a GPL-3.0 section 7(b) additional term for the code and as a CERN-OHL-S notice for the hardware, whose section 4 lets a notice require the source location on every product. The line is on the v2 board's front silkscreen below the socket pads ([add_credit_silk.py](../hardware/sn64-v2/tools/add_credit_silk.py)); DRC unchanged (5 single-spoke thermal reliefs, 6 open items).
- [CREDITS.md](../CREDITS.md): everyone SN64 borrows from, what was used and under which licence, in two lists (built in; studied or measured), taken from the provenance records. The same licence, notice and credit files were added to `main`, the branch visitors land on.

## 2026-10-01 — local user-folder paths removed from the tracked files

The repository is public and its notes, scripts, check reports and KiCad netlists carried absolute paths with the Windows user folder in them. No file from outside the project was ever uploaded; the exposure was the folder name inside those paths. `tools/scrub_local_paths.py` now replaces that prefix in every tracked text file (`%USERPROFILE%` in notes, reports and netlists, `$env:USERPROFILE` in PowerShell scripts, `$HOME` in shell scripts and snippets); it reads the name from the PC at run time, so the tool does not contain it. Scripts still resolve their tools; JSON and XML reports still parse. A local pre-commit hook refuses commits that contain the path. Applied to the tips of all public branches. Earlier commits still hold the old text until the history is rewritten, which is the owner's call.

## 2026-10-01 — console top measured by the owner; shorter shell drawn as a proposal

The owner measured the cartridge hole on an N64 and an M64: 30 mm from the console's top surface down to the plastic floor the cartridge shell rests on, the same on both. With the SummerCart64 shell bottom 12.31 mm below the shoulders, the console's top surface is 17.7 mm above the shoulders. The shell model had it at an assumed 25 mm. Recorded in [dimensions.md](dimensions.md).

He had also asked whether the unit could be shorter with about 5 mm clear on each side of the USB port. [sn64_v2_shell.py](../mechanical/sn64-v2-shell/sn64_v2_shell.py) now draws two geometries, picked by `VARIANT`:

- `board-70`: the board as it is. Nothing moved except the console line; the USB-C window turns out to be 25.8 mm above the console top.
- `short-60`: USB-C centre at 32.5 mm (the lowest the board's side notches allow, and the height of SummerCart64's own port), 5 mm of plain wall above its window, flare from 44 to the board's top edge at 60. Shell 100.3 mm tall instead of 110.3; the cartridge sits 10 mm lower. One valid solid, no interference, cartridge and socket checks unchanged.

Picture of both side by side: [compare-70-vs-60.png](../mechanical/sn64-v2-shell/compare-70-vs-60.png) (relabelled and renamed when the board was refitted later that day). Details and the before/after table: [v2-shell.md](design/v2-shell.md), "Shorter proposal".

**The board is not changed.** The proposal needs the socket's fan-out routed again in 8 mm instead of 18 mm. Measured on the routed board: at most 24 of the 56 translator nets have to pass any one point sideways, which three routing layers hold in 8 mm, so it is expected to route but is not proven. Waiting for the owner's decision before touching the board.

## 2026-10-01 — logo options drawn (the owner chooses)

The owner asked for a simple logo that uses Nintendo-style design elements, with one-colour versions that can be embossed later. [assets/logo/make_logo.py](../assets/logo/make_logo.py) writes four options as SVG, each in colour and in one colour: buttons (four coloured buttons on two slanted pads that read SN over 64), a wordmark (heavy slanted letters over a four-colour bar), the two together, and a badge (the letters in a ring). The characters are drawn in the script as outlines, so no font is used. Preview sheet: [sn64-logo-options.png](../assets/logo/sn64-logo-options.png); notes, smallest feature sizes for embossing and the trademark position: [assets/logo/README.md](../assets/logo/README.md).

Original artwork: it copies no Nintendo logo, typeface or trademark. Nothing is chosen yet, so the logo is not in the README, on the board or on the shell.

## 2026-10-01 — logo chosen: buttons and letters in a ring

The owner picked the buttons together with the letters and asked for the ring of the badge option around both. He also pointed out that the symbol should be about the height of the letters; it had been 1.7 times taller. The buttons now measure 1.15 times the letter height, which looks equal because their tips are rounded.

Files in [assets/logo](../assets/logo/README.md): the logo in colour, for dark backgrounds, in one colour, and in one colour with plain buttons for small embossing; the same parts on their own (without the ring, buttons alone, letters alone). The badge option was removed; the earlier options stay in the history (commit `b71e1d2`). The README there lists the finest detail of each one-colour file and the size at which it reaches 1 mm: the full logo needs 147 mm of width, the plain-button logo 106 mm, the letters alone 45 mm.

The logo is not yet in the top-level README, on the board or on the shell.

## 2026-10-01 — board refitted to the shorter shell

The owner looked at the two shells side by side and approved the shorter one, so the routed board was refitted to it with the same script as the first refit ([refit_tower_v2.py](../hardware/sn64-v2/tools/refit_tower_v2.py), geometry `short-60`):

- Top edge from 70 to 60 mm above the shoulders; 111 mm wide from 26.4 to 50 mm, the 88 mm neck from 50 to 60.
- USB-C and its ESD part from 50 to 32.5 mm, the VBUS capacitor above them, mounting holes H5/H6 from 38 to 44.5 mm, the silkscreen credit line to 50.5 mm.
- 64 nets routed again (59 socket nets, 5 USB nets) with all other copper locked. The first run finished 63; the cartridge master clock on the corner pad was boxed in. The router's `bus` ordering finished all 64 on the same three layers. Notes in [pcb-routing.md](design/pcb-routing.md).

Result: 3,603 tracks, 1,066 vias, 213 of 218 signal nets fully connected, the same 6 open items as before, DRC errors 6 single-spoke thermal reliefs (5 before; the new one is a shield leg of the USB-C receptacle). The board STEP with all part models has no interference with the shorter shell, the cartridge or its PCB. Board renders, copper picture, STEP and check reports regenerated.

Shell model: `board-60` is now the default geometry and matches the board; `board-70` stays in the script for comparison. Before and after: [compare-70-vs-60.png](../mechanical/sn64-v2-shell/compare-70-vs-60.png).

Not changed: the schematic and the FPGA pin plan (no net moved), and `build_v2_pcb.py`, which still generates the earlier placement.

## 2026-10-01 — logo stamped into the shell's cap

The owner asked for the logo on the front of the mushroom cap, then made clear it must not stand proud of the surface and suggested doing it like a Game Boy cartridge. [sn64_v2_shell.py](../mechanical/sn64-v2-shell/sn64_v2_shell.py) now cuts a pill-shaped pocket into the cap's front face (the inside of the logo's ring, 64.7 x 19.0 mm, 0.6 mm deep) and leaves the button pads and the letters standing in it, level with the face. The shapes are read from [sn64-logo-mono.svg](../assets/logo/sn64-logo-mono.svg). The shell is still one valid solid of the same outside size, with 4.4 mm of wall behind the pocket. Close-up: [shell-logo.png](../mechanical/sn64-v2-shell/shell-logo.png).

A first version with the logo raised 0.6 mm was built and replaced before it was committed.

Two things found on the way:

- The CAD importer broke the slanted S and 6 of the logo file, because a slanted arc is a piece of an ellipse. [make_logo.py](../assets/logo/make_logo.py) now writes every letter in final coordinates with Bezier curves and no transform; the pictures are unchanged to within a few edge pixels.
- Imported faces keep the importer's own placement, so scaling them moves them unless it is done before measuring and centring. The shell script does it in that order.

Open: at this size the characters on the buttons have 0.58 mm strokes and a 0.46 mm opening, which a filament printer will not hold. The plain-button logo file is the fallback (one constant in the script).

## 2026-10-01 — shell in two halves with mounting for the board

The owner asked whether the shell has proper mounting holes for the board, and whether the screw posts are shouldered so the board is held between the two halves. It had neither: the shell was one fused piece, and only the two lower board holes had posts (SummerCart64's own).

[sn64_v2_shell.py](../mechanical/sn64-v2-shell/sn64_v2_shell.py) now builds two halves, like an N64 cartridge:

- The label-side half carries the board; the back half closes over it. They part at the board's back face, where SummerCart64's halves part.
- At board holes H1, H2, H5 and H6 a post on each side ends flat against the board, so the screw clamps the board between two shoulders at a fixed height. H1 and H2 keep SummerCart64's posts.
- Two pins on the label-side half go through board holes H3 and H4 and locate the board sideways.
- Two more screws go through the back half into the brackets under the socket ears. The brackets now belong to the label-side half.
- Six screws, all from the back. Hole sizes are for M2 x 8 thread-forming screws (assumed): SummerCart64's 2.5 mm pilot would need a screw too thick to pass the board's 2.5 mm holes. Its post dimensions are recorded in [dimensions.md](dimensions.md).

Checked in the model: each half is one valid solid; they do not overlap; the back half lifts straight off; the real board with its socket lifts straight out of the label-side half; every screw axis is open down to its pilot, has a full seat under the head and plastic for the thread; all six board holes have a full shoulder on both faces; no board part touches or comes within 0.3 mm of a post, pin or bracket. Pictures: [halves-open.png](../mechanical/sn64-v2-shell/halves-open.png), [half-front-with-board.png](../mechanical/sn64-v2-shell/half-front-with-board.png), [section-screw-post.png](../mechanical/sn64-v2-shell/section-screw-post.png).

Not done: a lip along the seam above the N64 body, any print or physical trial, and the socket leg forming, which waits for a sample (see the open list in [v2-shell.md](design/v2-shell.md)).

## 2026-10-01 — board posts redone the owner's way; registration pins; 4.0 mm board holes

The owner corrected the mounting: he did not want the board merely pinched between two flat post ends. He wants what a Nintendo cartridge has: the post on one half goes through the board so the board sits in place and cannot move, and the other half's post is shorter. He also asked for registration so the board cannot be put in backward. In a follow-up he set the through-hole part at 1.1 mm so the other post still presses the board down.

- Shell ([sn64_v2_shell.py](../mechanical/sn64-v2-shell/sn64_v2_shell.py)): at H1, H2, H5 and H6 the label-side post is 6.5 mm with a shelf at the board's front face and a hollow through-hole section 3.8 mm across and 1.1 mm high; the back post lands on the board. The screw runs through both; it cuts thread only below the shelf. SummerCart64's own posts at H1 and H2 are replaced by these.
- Board: a hollow post around an M2 screw does not fit a 2.5 mm hole, so H1, H2, H5 and H6 are now 4.0 mm ([set_mounting_holes_v2.py](../hardware/sn64-v2/tools/set_mounting_holes_v2.py)). No copper is within 4.5 mm of them. Zones refilled, checks unchanged: 6 single-spoke thermal reliefs, the same 6 open items. Board renders, copper picture and STEP regenerated.
- Registration: two solid pins through H3 and H4, which are 3 mm apart in height left and right. Checked with the real board model turned back to front: it is stopped at both pins, rests 3.2 mm above the shelves, and the back half cannot close over it. The right way round it drops in and lifts out freely.
- `finish_route_v2.py` got a `--refill-only` option because its pour removal breaks KiCad 10's python on a board that already has pours.

Checked in CAD only. Pictures: [section-screw-post.png](../mechanical/sn64-v2-shell/section-screw-post.png), [halves-open.png](../mechanical/sn64-v2-shell/halves-open.png), [half-front-with-board.png](../mechanical/sn64-v2-shell/half-front-with-board.png).

Still open on the same theme: the SNES cartridge can go into the cap's pocket back to front (see the open list in [v2-shell.md](design/v2-shell.md)).

## 2026-10-01 — cartridge check: a cartridge that is in back to front is detected before 5 V is switched on

The owner asked whether the FPGA could detect a cartridge that is in backwards and show a message, "something quippy but serious enough about what we dont do around here". While it was being built he asked for a way to test it in real life without false alarms blocking games.

What a reversed cartridge does was checked on the socket footprint first: contact k lands on contact 63 - k, so the cartridge's ground sits on the 5 V rail and its supply on ground. Until today the board would have pushed the switch's whole current limit (1.04 A) backwards through the cartridge for up to 10 ms before the switch's fault flag ended it.

- **How it is detected, with no added part.** The telemetry ADC (TLA2528) already reads the cartridge rail through 20 k and 10 k. Its channels can also be outputs. Before the switch is enabled the FPGA makes that channel an output at 3.3 V, so the 20 k feeds at most 0.165 mA into the switched-off rail, and reads the rail back about every 21 ms. A reversed cartridge holds the rail at a diode drop; the right way round it rises. /RESET is released during the check because its pull-up hangs from the same rail. [sn64_rail_monitor.sv](../fpga/rtl/sn64_rail_monitor.sv), [sn64_power_sequencer.sv](../fpga/rtl/sn64_power_sequencer.sv) (new states 7 to 9, fault code 0x01).
- **Modes, in one firmware** (mailbox `CONTROL` bits 5:4): check only (measures, never powers), report only (measures, starts anyway), enforce (refuses), off. The FPGA resets to enforce; the menu starts in report only until real cartridges have been measured. The check can be left out of a build (`SEQ_PROBE_ENABLE = 0`; the v1 wrapper has no ADC and is built that way).
- **Menu** ([main.c](../firmware/bootstrap/src/main.c), [sn64_cartcheck.c](../firmware/bootstrap/src/sn64_cartcheck.c)): "Check cartridge (no power)", a "Cartridge check:" setting, the last result on the main screen, and an alert screen: "WHOA. WRONG WAY ROUND. That cartridge is in backwards. We don't do that around here. Nothing was powered, so no harm done. Take it out, turn the label to the front, and try again." A rail that does not rise at all is reported as a short. Mock-up: [cart-check-screens.png](design/img/cart-check-screens.png). The menu also no longer enters the game display before the cartridge really runs; before, a start that ended in a power fault left it waiting for a picture.
- **Result register** `CART_CHECK` at mailbox 0x0A: done, pass, mode used, "this build has the check", rail reading.

Evidence, all simulation:

| Check | Result |
|---|---|
| `evaluate.py --mode sim` | all benches pass; new `tb_cart_check`, ten more cases in `tb_power_sequencer`, more in `tb_n64_endpoint` |
| Fault injection | `/RESET` kept pulled during the check, and a sequencer that does not enforce: both fail as required |
| `tb_cart_check` with the board's real capacitances | empty socket passes in 0.28 s, good cartridge in 0.38 s, reversed cartridge held at 0.47 V with 0.14 mA through it and the switch never closed |
| Boot ROM | builds, 131,072 bytes, CIC-6102 check OK; host tests pass (74 new checks) and their fault-injected builds fail; ROM/endpoint co-simulation passes |
| `route_top.py --top board --speed 8` | all five clocks pass; 30.2k LUT4, 13,348 flip-flops, 203 of 208 block RAMs |

Not measured on anything. The cartridge in the simulation is an assumption (nothing below 0.8 V, then 150 ohm; reversed: one silicon junction). The threshold (0.65 V) and the timeout (4 s) follow from that assumption. First job on a real board: check only on every cartridge to hand, both ways round, then set the threshold. Open points are listed in [reversed-cartridge-detection.md](design/reversed-cartridge-detection.md); the main ones are the unknown margin, what the four translators draw from the rail at low voltage, and that a cartridge with its own reverse protection is not seen. The keying in the shell's pocket is still needed.

Also fixed on the way: the notes for U6 and U12 cited document numbers that do not match the datasheets on TI's site; they now cite SBAS961A and SLVS841F, read today, and the pin tables were checked against them. The current limit with 24.9 k is 1.04 A nominal (0.96 to 1.12 A). The ROM co-simulation script was missing two source files since the console video path was added; it runs again.

## 2026-10-01 — the owner's logo on the back of the shell, two splash screens, a real USB-C port

Three requests from the owner in one sitting.

- **His logo.** He asked for a splash screen and said the logo was somewhere on his T7 drive: a lightning warning symbol with the word FantomZap. A file-name search of the drive (5 seconds) found it in several versions; he picked the one with the triangle and the word side by side. It is a pixel image, so it was traced into outlines with the potrace algorithm ([assets/logo/fantomzap/](../assets/logo/fantomzap/README.md)); drawn back at the artwork's size the outlines differ in 0.85 % of the logo's pixels, none more than a pixel from the edge. The full-size artwork stays on his drive. `NOTICE` and `LICENSING.md` now say that the FantomZap name and logo are his and are not under the open licences, as they already said for the SN64 name and logo.
- **Back of the shell.** "Upscale it and use on the reverse side of the shell like we did with the front": the back of the cap now carries the logo in a pocket 102.4 x 19.0 mm and 0.6 mm deep, its eleven pieces level with the face, readable from behind ([sn64_v2_shell.py](../mechanical/sn64-v2-shell/sn64_v2_shell.py), [shell-logo-back.png](../mechanical/sn64-v2-shell/shell-logo-back.png)).
- **Splash screens.** "Do sn64 logo splash followed by fantomzap logo splash", for the N64 and the M64: the boot program shows the SN64 logo, then the FantomZap logo, then the menu, about 2 s each, skippable ([n64-bootstrap.md](design/n64-bootstrap.md), [splash-screens.png](design/img/splash-screens.png)). Host tests pass (35 new checks, and the fault-injected build fails as required); the ROM builds at 131,072 bytes with 6,198 bytes left in the 128 KiB window.
- **USB-C port.** He noted the opening was a placeholder. It is now a rounded recess for the plug's overmold with a rounded opening around the receptacle ([shell-usb.png](../mechanical/sn64-v2-shell/shell-usb.png)). The JAE drawing's numbers show the recess is needed: against a flat 2 mm wall a plug would stop 0.1 mm short of fully mated.

Asked and answered: the board has the USB-C on its +X side, the player's left, as the render shows. He would rather have it on the right and accepts the left if moving it is costly. Looked at the board: the other side has the open-drain driver U205 and two capacitors where the receptacle would go, so the two corners would trade places, about twenty nets would be routed again, and the USB data pair would run about 95 mm across the board or the FPGA's USB pins would move. Not a redesign, not free; not done, waiting for his word.

- **Check items off the main menu.** "The 2 check things should be hiden and just be there and work upon clicking the start game option." The main menu is back to four items. Start runs the cartridge check and enforces it; the check-only run and the mode switch are on a service screen behind Status / diagnostics (Z). This reverses the morning's default of report only: with unmeasured thresholds the enforced check could refuse a good cartridge on the first board, and the service screen is then the way round it ([reversed-cartridge-detection.md](design/reversed-cartridge-detection.md)).
- **Menu ideas.** He asked for a brainstorm of menu features and said the menu could be repackaged: [menu-ideas.md](design/menu-ideas.md). Nothing decided.

ROM after all of this: 131,072 bytes, SHA-256 `2d3a8feab927c465a7ef447479a81e3da6cee084b980a5e85ce5f0d040395140`, 5,514 bytes left in the 128 KiB window; host tests and their fault-injected builds as required; ROM/endpoint co-simulation passes.

Checked in CAD and on the host only. Nothing printed, nothing run on a console. The shell's `fit-*.png` pictures predate the back logo and the port.

## 2026-10-01 — what the chosen hardware allows; two defects found in the boot program

The owner asked which quality functions the hardware on the v2 board can carry. Answer, with the numbers, in [menu-ideas.md](design/menu-ideas.md) under "What the chosen hardware allows". In short: plenty of logic (59 % free), flash (about 12 MB unused) and the whole console for picture and sound work; almost no block memory (5 of 208 blocks free), no current measurement, no spare pins brought out.

Two things found while checking the boot program against that, both by reading the code:

- The sound loop pads every 1,280-sample buffer with silence, because the FPGA's ring holds 1,024 samples. It would buzz. Software fix (`audio_push`).
- Nothing matches the console's picture rate to the Super NES's 60.10 Hz, so a picture is dropped every few seconds. Software fix (the console's video timing is programmable), to be tried on real displays.

Both are listed under "Still open" in [n64-bootstrap.md](design/n64-bootstrap.md). Neither is fixed.

## 2026-10-01 — frame lock, compatibility mode, and the sound path rebuilt

The owner asked whether the menu could keep the console's own picture rate and switch to the Super NES's only when a game starts, and whether a compatibility mode could go in the menu in case the changed timing does not work on an M64: something turned on through a confirmation screen that states how much slower the game then runs, at least until he has play-tested it. Both are built. Design note: [frame-lock.md](design/frame-lock.md).

What was decided on the way, and why:

- **The game follows the console.** The console's timing is written once when a game starts and not touched again. The other way round (steering the console every picture with its leap-line register) would leave the game at exact speed, but the N64brew documentation says a shortened leap line has side effects in the sync signal, and a register rewritten every picture is one more thing a display might not take. Cost: normal mode runs the game 0.04 % slow. Compatibility mode: 0.45 %.
- **Slowing the game without touching a clock pulse.** First idea: gate single pulses with the FPGA's clock gate. A small test design routes, but the gate's enable timing is not checked by the tools, and a shortened pulse on this clock would corrupt the game. Built instead: the PLLs make twice the master clock and a flip-flop halves it, holding an occasional low phase longer (`sn64_clock_pace`). PAL's master moved from -27 to +46 ppm, the closest a doubled PAL clock gets.
- **Sound.** The loop found faulty earlier today is replaced, not patched: the program drives the console's sound output itself, one block per picture, through a cubic resampler. A model of the console's two-place sound queue found a fault in the first version of the hand-over (after one late picture the queue refused a block and ran dry a picture later); the rule was changed to one picture's worth per block and the model now passes with pictures up to 10 ms late.
- **ROM size.** 147,456 bytes, 357 over a 128 KiB window. `ROM_ADDR_BITS` is 17 in the build files, as on the v2 board.
- **An older fault found on the way.** The clock select on the v2 board was written with its mode as a Verilog parameter. nextpnr-ecp5 reads that setting from an attribute, so every routed v2 build so far had the select in its default mode (idle high) instead of the one the source named (idle low). Seen in the text configuration of a small test build; fixed by adding the attribute; `route_top.py` now writes the configuration and checks it ([clock-plan.md](design/clock-plan.md)).

Evidence (PC only): FPGA suite 88 runs pass, 24 of them fault runs; the whole design routes with every clock passing; menu program host tests 343 checks in seven sets, eight fault builds rejected; ROM and endpoint co-simulation passes. Numbers in the design note.

Also answered: there is no simulated game cartridge and no simulated N64 with a screen. The tests are a tiny stand-in cartridge, the real FPGA design, a model of the N64's cartridge-slot wiring, and the menu program's logic run as PC tests; the menu ROM itself has never run. Two ways to close some of that gap before hardware were offered (an N64 emulator for the menu ROM, a free test cartridge in the FPGA simulation); neither is started.

**Nothing here has run on a console, a television or an M64.** The hardware checks are listed at the end of the design note; the reading to look at first is the slowdown the lock settles on, which measures how far a real console's clock is from the board's.

## 2026-10-01 — credits roll in the menu

The owner asked for a credits section: everyone the repository credits, then Claude, then his cats at the very end, and not his own name. His wording for the cats: "Manager: Scout (Cat)" and "Arbitrary code execution: Ash & Aurora (More cats)". The second is earned: during the frame lock work three messages made only of plus signs arrived, one of them in the middle of a build. They were not acted on. It turned out the cats had been on the number pad, where plus and Enter sit side by side.

- [CREDITS.md](../CREDITS.md) has a last section, "The SN64 crew": Engineer: Claude (AI by Anthropic), then the cats.
- The boot menu has a sixth row, "Credits", that rolls CREDITS.md up the screen. The text is generated from the file (`tools/make_credits.py`), so the two cannot drift; `make test` checks it. It opens with "SN64 by FantomZap" and the source location, as the notice terms ask of anything the program displays.
- His name is nowhere in it. The handle is the credit, as on the board and the splash screen.
- Names are kept two columns off the screen's edge.

ROM 147,456 bytes, SHA-256 `0b0f9f14a336bf9d24659761761e26e4349481ccaa4ae9158c68f13ddbd64d49`. Host tests 368 checks in eight sets, nine fault builds rejected, co-simulation passes. Mock-up: [credits-screens.png](design/img/credits-screens.png). Not run on a console.

## 2026-10-01 — main menu in four rows, a mapping screen with controllers that light up, all four C for the menu

The owner set the menu's shape: "the main menu should be play, controller mapping, settings and power off cartridge", the rest in a Settings sub-menu. For the mapping he asked for "an n64 controller and a snes controller side by side with light up buttons corresponding to button presses", "a dropdown list of controllers for m64 input sake and another dropdown for snes compatible controllers", buttons that light on each, "and also images of their singular buttons in the mapping part". Defaults: "the normal buttons should be mapped to their counterpart on the snes controller and the z button to the select button". "To bring up the sn64 menu they press all 4 c buttons together." While it was being built he added: "no actual nintendo logos on anything". All of it is built. Write-up: the last section of [n64-bootstrap.md](design/n64-bootstrap.md).

What was decided on the way, and why:

- **One screen, not a test mode and a change mode.** Only the D-pad, A and B do anything on the mapping screen, so every other button can be tried freely, and B leaves when it is let go, so it is seen to light first.
- **The choices for a row take the place of the rows,** not of a picture, so both controllers stay in view and the choice under the cursor can be marked on the right-hand one.
- **The right-hand controller shows what the game is given.** Up and Down together light nothing there, and neither do the four C buttons while they make the shortcut.
- **The two lists change the picture and nothing else.** Every controller the M64 accepts reports the same 14 buttons and the stick, so there is nothing else for the left list to change.
- **The pictures are diagrams the program draws** from discs and bars, with its own five-by-seven dot letters on the buttons. No maker's logo or lettering. The repository was searched for Nintendo logos the same day: there are none. The rule is recorded in `CLAUDE.md`, and `NOTICE` now names the controller makers' trademarks.
- **A tenth of a second for the shortcut.** All four C buttons have to be seen together on six pictures in a row before the menu opens. An addition of mine, so that plugging a controller in does not open the menu; to be tried by hand.
- **X and Y have no namesake on an N64 controller.** The C buttons give the Super NES diamond in its own positions (C-Up X, C-Left Y, C-Down B, C-Right A), so every Super NES button can be reached with the defaults. My choice.
- **A warning when a change leaves a Super NES button without any button.** "No button gives Start" under the rows, before a game is started.
- **The main menu lost its technical lines** (STATUS word, sequence count, region). They are on the Status screen, where they already were. One line says whether the cartridge is off, starting or running.
- **Notes are white, refusals red.** "Cartridge is off" is not a warning.
- **The co-simulation's first frame** now carries the new default (A and Start give 0x0108, not 0x0009).

Evidence (PC only): host tests 882 checks in ten sets (mapping 49, controller pictures 408, mapping screen 84, and the earlier seven), 11 fault builds rejected, among them a picture in which A lights B's place and a screen in which B takes a choice. ROM 147,456 bytes, SHA-256 `cd157a7235badb71fab0208b63fe89a824c156e2b2a8faf2ced7974f57297cbf`, 146,141 bytes used, 116,003 free in the v2 board's window; CIC-6102 check OK; ROM and endpoint co-simulation passes. Mock-ups made from the pixels the code under test drew: [mapping-screens.png](design/img/mapping-screens.png), [menu-screens.png](design/img/menu-screens.png); the other four sheets were redrawn for the new menu.

Open:

- **Not run on a console or an emulator.** How the pictures look on a television and whether the mapping screen keeps 60 pictures a second are not known (45,000 to 65,000 pixels are drawn a picture).
- **Nothing is kept when the console is switched off:** the mapping, the two lists and compatibility mode start from their defaults. The board has nowhere yet for the menu to store settings.
- **One mapping for both controllers; the pictures show controller 1.**
- **The controller list is my reading of ModRetro's compatibility list,** and none of those controllers was measured; the two-handled picture serves both the Brawler64 and the 8BitDo 64.

## 2026-10-01 — the controller pictures redrawn in their real shapes; the mapping list scrolls

The owner looked at the first mapping screen and asked: "can you please just make the graphics closer to the right shapes", "the controllers I mean". While it was being redone he added: "the button list below can be scrollable too if it helps fit things".

What was wrong: every controller was built from discs and bars to my own idea of its shape. The N64 controller came out wide and squat with stubby handles; the Super NES controller had a waist it does not have.

What was done:

- **Reference photographs, measured.** A photograph of each controller lying flat was looked at in the browser and its outline measured with a small script: for the N64 controller and the Super NES controller the public-domain photographs by Evan-Amos on Wikimedia Commons, for the others the makers' product pictures. The N64 controller is 1.04 times as wide as it is tall; the first drawing was about one and a half times.
- **Outlines from points, not from discs.** `tools/make_padshapes.py` holds each outline as a few dozen points, lays a smooth curve through them and writes pixel runs to `src/sn64_padshape_data.c`. The buttons are drawn at the places measured on the same photographs. Nothing of any photograph is in the repository.
- **The M64 Pro Controller and the Hyperkin Captain** were checked against ModRetro's product pictures: both have the N64 controller's three-handled shape, so they share its outline.
- **The Super NES controller** has its flat top, the shallow step along the bottom, the round hollow under the D-pad and the two slanted pads under the four buttons.
- **A new layout, made possible by the scrolling list.** The N64 controller now fills its half of the screen (138 x 132 pixels; it was about 122 x 82, and the wrong shape). The Super NES controller is a flat one, so the mapping list moved under it: one column, ten of the 14 rows on the screen, scrolling with the cursor. The choices for a row open in the same place. Both controllers stay in view the whole time.
- **Shoulder buttons and Z** are still shown where they can be seen and can light, which is not where they are on the controllers. That is said in the design note.

Evidence (PC only): `test_padview` 416 checks, eight of them on the shapes themselves; `test_mapscreen` 94; all host tests 900 checks in ten sets; 11 fault builds rejected. ROM 147,456 bytes, SHA-256 `ce7b45db1fec11f20e36e0a5c212ef05e89dacd14e31689e1416bf880d8f12a3`, 146,622 bytes used; CIC-6102 check OK; ROM and endpoint co-simulation passes. Mock-up from the code under test: [mapping-screens.png](design/img/mapping-screens.png).

Open: not run on a console. The 8BitDo 64 is the least certain shape: none of its maker's pictures is straight from the front. The Brawler64 was read by eye. Write-up: [n64-bootstrap.md](design/n64-bootstrap.md), "The right shapes".

## 2026-10-01 — the stick as a setting: the D-pad from a chosen part of its travel, in eight directions

The owner: "we ought to create an input method option for the joystick. I was thinking beyond a certain percent pushed in a direction it can press a directional button? Perhaps if pressed diagonally beyond that threshold it can press the appropriate 2 directions at once?"

The stick did press the D-pad already, which I had not told him plainly: at a fixed half of its travel, each axis judged on its own. It is now a setting and works the way he describes.

- **First row of the mapping list:** "Stick", the D-pad, a percentage. A opens one list: the D-pad from 20 to 80 % in steps of ten, or nothing. 50 % to begin with.
- **The rule changed, not only the menu.** How far is now measured from the middle, the same in every direction, and the direction is one of eight equal slices: one direction within 22.5 degrees of an axis, two between. With the old rule a diagonal push of 60 % of the travel pressed nothing while the same push to the right pressed Right.
- **A reading on the screen.** With the cursor on the row: "Stick now: 63 %". A worn stick reaches less than a new one, and this lets the player see what theirs reaches before choosing.
- **Try before taking.** While choices are open the pictures behave as if the one under the cursor were set. That now holds for a button's choices too.
- **The cap of the stick lights** while it presses something, and the cursor can mark the stick and the whole D-pad.
- **A full throw is 80 units,** from libdragon's figures for the controller (about 85 in good condition, as little as 60 when worn).
- **The mouse stays deferred;** the raw stick still goes to the mailbox. The stick's row is where that choice would go.

The ROM file grew from 147,456 to 163,840 bytes: it is padded in steps of 16 KiB and the used part went from 146,622 to 150,073. It fits the v2 board's 256 KiB window with 112,071 bytes to spare.

Evidence (PC only): `test_mapping` 69 checks, among them a full throw every 5 degrees round the circle; `test_padview` 438; `test_mapscreen` 127; all host tests 975 checks in ten sets; 12 fault builds rejected, the new one a stick judged one axis at a time. ROM SHA-256 `f7959a0e52404afffa0c89de313ec7d4497881fb5ab78fee6dac2c4e4078bfbf`, CIC-6102 check OK, ROM and endpoint co-simulation passes. Mock-up: [mapping-screens.png](design/img/mapping-screens.png), second and third screen.

Open: no real stick has been read, so 50 %, the steps and the slices are untried. No slack round the boundaries: a stick held exactly on one can flicker between two answers; to be judged on hardware. Not kept across power-off. Write-up: [n64-bootstrap.md](design/n64-bootstrap.md), "The stick".

## 2026-10-01 — the menu's look: the logo as the title, six themes, an About screen

The owner: "the title name on the menu can just be the logo centered on the top. We need some stylization I think. Maybe make a few themes?" While it was being built: "Move all the version stuff and odd info to an about section in settings too. Also left justify the menu but tabbed in a little", then "not indented but just moved right a bit to look more centered".

- **The logo is the title.** Large and centred at the top of the main menu and Settings, with a rule in its four colours under it. Small and centred at the top of every text screen, the rule running out to both sides. The two text lines that headed every screen are gone.
- **The rows are one left-justified block on a panel centred on the screen,** which is how I read his correction. The row under the cursor stands on a bar. The main menu's rows have round marks in the logo's four colours with a small sign each.
- **Six themes** under Settings, Theme: Midnight (the old colours, and the one it starts in), Smoke, Grape, Jungle, Ice, Fire. A goes to the next, Left and Right both ways. Every screen follows the theme; the controller pictures and the logo's buttons keep their own colours.
- **About** under Settings: the credit line, the source location, the menu program's version, the SN64 build and feature word, the console, the licences, no warranty and no affiliation. Everything the old header said is there.
- **The title picture is stored with see-through edges** and its ring and letters as "ink" that the theme colours, because the background is no longer one fixed colour. `tools/make_title.py` makes it from the two logo files; `make test` fails if they changed since.
- **A small thing put right on the way:** the play refusal with no SN64 answering no longer repeats the line over the rows, and Settings no longer repeats under its rows what its first row says about compatibility mode.
- **The mock-up tool** takes the main menu, Settings and the mapping screen whole from frames the host tests write, in every theme, and of the text screens the background, the small title and the colours.

Evidence (PC only): new `test_menuview` 87 checks; `test_mapscreen` 128; all host tests 1,063 checks in eleven sets; 13 fault builds rejected, the new one a title 6 pixels off centre. ROM 163,840 bytes, SHA-256 `16bb2243d451e40200a3348d84d5d5975f10b1159fd01f2466d2b6d621d5b297`, 157,046 bytes used, 105,098 free in the 256 KiB window; CIC-6102 check OK; ROM and endpoint co-simulation passes. Mock-ups from the code under test: [menu-screens.png](design/img/menu-screens.png), [theme-screens.png](design/img/theme-screens.png), [theme-other-screens.png](design/img/theme-other-screens.png).

Open: not run on a console, so the colours have only been seen on a PC screen and the menus' picture rate is not measured. The themes, their names and colours, the marks and what About says are my choices and wait for his word. The theme is not kept across power-off. Write-up: [n64-bootstrap.md](design/n64-bootstrap.md), "The menu's look".

## 2026-10-01 — first run in an emulator; the top lines blinked, and why

The owner tried the ROM in Project64: black screen. libdragon's own instructions name ares as the only emulator accurate enough, so with his yes ares v148 was fetched from its GitHub releases (portable zip, hash checked against the one GitHub publishes). The ROM came up at once: both logos, then the main menu at 60 pictures a second. He set up his Xbox controller in ares and drove the menus: "the menu works fine".

This is the first time the menu program has run anywhere but in unit tests and the co-simulation. It says "SN64 hardware not found", which is right in an emulator, so nothing past the menus is covered.

- **A fault it found.** He saw the picture flicker, and my captures showed the same: 10 of 40 had the top of the logo wiped. The menu was redrawing the buffer that had just left the screen, and ares takes its picture of that buffer a little late. On a console the buffer is no longer read by then, by my reading; not seen on one.
- **Fix.** Three picture buffers for the menu and the logos, and a new one taken only after the vertical interrupt. 120 captures in a row, none wiped.
- **A readout of how long a menu picture takes** was added to the service screen's readout. A text screen takes about 4 ms of the 16.7 ms a picture has, in ares.
- **Things that did not work, kept for the record.** ares has no keys set when new, and key presses made by a script did not reach it although its settings held the bindings; dropped when the owner said his controller was enough. The main menu and the mapping screen were not timed: another window covered the readout in those captures.

Evidence: host tests 1,063 checks, 13 fault builds rejected, ROM SHA-256 `977c1f5e4031186550530cb6b1bd0737cd5d26d102c6a078fdd1125746690eee` (163,840 bytes, 157,527 used), CIC-6102 check OK, co-simulation passes. Write-up: [n64-bootstrap.md](design/n64-bootstrap.md), "First run in an emulator".

Open: a console run. The owner has an EverDrive 64; the ROM can go on its card.

## 2026-10-01 — a real game through the simulated SN64; a fault in the cartridge bridge found and corrected

The owner, about ordering the board: "I'm not talking about isolated systems. I'm talking about testing a game somehow. I'm worried that I'll have PCBWay create this and it might be a paperweight." He was right to ask: no real program had ever run through the logic, only a stand-in cartridge of a few dozen bytes.

- **A bench that runs a real cartridge image** (`fpga/tests/tb_game.sv`, `fpga/tools/run_game.py`): the whole logic, a cartridge model that holds the image, and an N64 side that presses Play, sends the controller and fetches every picture through the cartridge port the way the boot program does. Pictures and sound are written out.
- **Images.** The owner gave a copy of his own Super Mario World cartridge; I did not fetch a commercial game and said so. With his yes, 49 free test programs were fetched from Peter Lemon's public collection. None of it is in the repository.
- **First run: a real fault.** A test program came up black and the bench counted half a million clocks with the FPGA and the cartridge both driving the data lines. The bridge drove on every write strobe, so a DMA copy out of the cartridge ROM had two drivers and the picture chip got a stale byte. This was the open "DMA matrix" item. Corrected in `sn64_cart_bridge.sv`: whoever answers the read owns the bus.
- **After the correction** the test program draws its text. Super Mario World runs for 660 pictures: opening screen, title, file menu on a Start press, "1 player game", the fade into the first scene, the first scene with sprites and status line, title music in the sound. No picture missed by the N64 side, no clock with two drivers.
- **Speed:** about 1.4 s of computing a picture, not the 8 s first estimated.
- **Also seen:** with no sound playing the output carries a small repeating pattern from the cartridge sound input, 54 dB below full scale. To be gated out in the logic.
- **The old tests still pass** (`evaluate.py --mode sim`), and the whole design routes on the board's pins with every clock passing after the correction (SNES master 37.2 MHz against 21.5 needed).

Write-up: [game-simulation.md](design/game-simulation.md). What stands between this and an order is in [board-verification.md](design/board-verification.md).

## 2026-10-01 — every signal of the board traced to its connector pin

`hardware/sn64-v2/tools/verify_board_wiring.py` reads the board file, the FPGA constraints and the two connector tables v1 drew from other people's working boards, and follows each of the logic's ports from its ball through the level shifter to the socket pin or edge finger. 19 checks pass. 16 deliberate mistakes (socket rows exchanged, socket mirrored, a byte pointing the wrong way, ports exchanged in the constraints and others) are each caught.

Found on the way: the status LED lights when its pin is low and the logic drives it high in a game; the cartridge's control lines have no pull resistors on the 5 V side. Both are recorded in [board-verification.md](design/board-verification.md).

Not covered by it: footprints, voltages, the socket's fit, the six connections the layout still lacks.

## 2026-10-01 — shell: the two lower screw posts level with the recess

The owner: the two bottom screw holes had a cylinder standing out of the stepped-in corners of the back; they should be flush with the indented portion. Measured on SummerCart64's back half, the recess floor is 5.6 mm from the board's mid-plane; our posts went to the back face at 9.6. They now end at 5.6. Checked in the model, nothing printed. Write-up: [v2-shell.md](design/v2-shell.md), last section.

## 2026-10-02 — the game through the board's own wiring; two wiring mistakes found in the data sheets and corrected

The owner asked for the board to be tested as a whole, with a game. The logic run of the day before joined the cartridge and the N64 to the logic signal by signal, so a wire on the board that goes to the wrong pin would not have shown. Three things were done.

**1. The test set's results.** The 49 free test programs through the logic: 23 processor tests, 7 sound-processor tests and 5 memory-map tests all pass (the words PASS and FAIL are read off the last picture in the tests' own font), 2 sound programs and the controller program pass, 11 picture programs were looked at and show what they draw. No picture missed, no two drivers on the data lines in any run. The first judging of the batch read the tables by position and called two tests failed; the pictures showed every row PASS, and the judge now looks for the words anywhere on the screen. Table in [game-simulation.md](design/game-simulation.md).

**2. A model of the board, made from the board file.** `hardware/sn64-v2/tools/make_board_sim.py` turns the board file's connection list into a netlist: the real top level `sn64_board_top` on its balls, a model of each part on its pads with the pin numbers of its maker's data sheet, the pull resistors, the dividers on the supply converter's inputs, the sound network. `fpga/tests/tb_board_game.sv` plugs the cartridge into the socket's pins and an N64 onto the edge fingers by number. Nothing of the start-up is shortened. Write-up: [board-simulation.md](design/board-simulation.md).

- The owner's Super Mario World boots and plays through it. From Play to a running game takes 0.45 s on the board: 0.38 s of that is the cartridge check charging the rail. The key chip in the cartridge is recognised through the board's open-drain lines and the header is read through the level shifters. The full run on the corrected board: 660 pictures with Start and A presses, into the first scene of the game, no picture missed, 1,858 rounds of the key exchange without a mismatch. 32 of its 33 written pictures are the same pixel for pixel as the logic run's; the board run starts one game picture later, and the one picture taken during a moving effect shows its next step.
- At the end of a run the cartridge is powered off as the menu does it, and the order is checked.
- A cartridge plugged in back to front is refused through the board's own parts: the check gives up after its 4.0 s limit with the rail at 0.46 V, and the 5 V is never switched on.

**3. The makers' data sheets, read again pin by pin.** Eleven kinds of part against their makers' sheets and one against its supplier's data: every pin number agrees with the board. Two wiring rules did not, and neither could have shown in a simulation with ideal parts:

- **One half of a level shifter was switched on all the time** (U204's byte from the socket to the FPGA had its enable on ground), also while its 5 V side has no supply in the menu. TI's sheet wants `/OE` high until both supplies are up. It now has an enable of its own, `SENSE_OE_N`, on the ball and trace of the EXPAND sense that nothing read, with a 100 k pull-up (R214). Unused channels have both pins on ground; the FPGA's pads on lines that can float have a pull.
- **The supply converter's address pin was on ground.** The sheet gives the address the logic uses for the pin left open, and has no setting for a pin tied to ground. On a board the converter might not have answered, and no cartridge would ever have been powered. The pin is now open.

Both were carried into the routed board by a script that changes only the copper involved (`apply_enable_fix_v2.py`): KiCad's rule check shows no new error and the same six open connections. The wiring check has a rule for each (21 checks, 20 deliberate mistakes caught), and the board run refuses a board with either mistake put back.

**What the board run found in the logic, corrected the same day:**

- The status LED was dark in a game (it lights with a low pin).
- The cartridge was out of reset for about 90 ns at every start with nothing driving its control pins, and at power-off the pins were let go in the same instant as `/RESET` was pulled. The pins are now held at rest whenever the cartridge has its 5 V, and `/RESET` is held low for 1 ms before the 5 V goes. Two fault builds put the old behaviour back and are refused.

**Evidence.** `evaluate.py --mode sim` passes with the two new fault builds. The logic run of Super Mario World gives the same 33 pictures as before the change, and the 49 test programs, run again on the final logic, give the same results and the same last pictures. The design routes on the board's pins with every clock passing (SNES master 36.6 MHz against 21.5 needed; `fpga/reports/v2-board-route.json`). Boot program rebuilt for two new credits (Peter Lemon's test programs, the ares emulator): 163,840 bytes, SHA-256 `f601658de41924e0776d60e85c05e68ba05d75f1c3bf1ddd9edcc603d644a718`, 157,551 used; host tests 1,065 checks.

**Found and not settled:**

- **A blank board cannot be loaded over USB.** On v2 the USB port is logic inside the FPGA. The first load needs the JTAG pads or a flash programmed before assembly. The specification asks for blank-target loading over USB. The owner's decision.
- Six connections of the board are still not routed, and each is needed: the converter's supply pin, a flash data line, USB D+ and its pull-up, N64 AD6, the N64 controller line.
- The cartridge sound input still adds a faint pattern to every game; a gate in the logic is still to do.

What stands between the design and an order is in [board-verification.md](design/board-verification.md).

## 2026-10-02 — the USB loader chip, the port on the player's right, and no USB logic in the FPGA

The morning's board-level run had found that a blank v2 board could not be loaded over USB: the port was logic inside the FPGA, and a blank FPGA has none. Three ways out were put to the owner. His answer: "Add back just the usb loader chip and put the usb on the right side of the cart". Asked whether the FPGA's own USB logic could stay in unused, to save the test runs: "no i want it clean so remove it".

**The loader chip.** An FTDI FT231XS (U13) between the USB-C socket and the FPGA's JTAG port, which works on a blank FPGA. It is wired like the open ULX3S board, so openFPGALoader drives it as it is (`-b ulx3s`) and the chip needs no programming: TCK on DSR#, TMS on DCD#, TDI on RI#, TDO on CTS#. The pin numbers are from FTDI's data sheet, the assignment from the PC program's source and the ULX3S schematic, and the wiring check holds the board to both. The chip is fed from the cable, with its I/O supply and its reset on its own 3.3 V output, as the data sheet draws it; with no cable it has no supply. Six small parts came with it: five capacitors, and the pull-down on TCK that Lattice's guide asks for and the board did not have. Write-up: [usb-loader.md](design/usb-loader.md).

**The FPGA.** The USB device, its two clocks, its share of the flash and the reboot line are gone from the logic, with the TinyFPGA core and the two tools that prepared it. The flash reader is SummerCart64's controller unmodified again. 28,955 LUT4 (30,820 before), 12,966 flip-flops (13,489), 107 pins (111), 4 clocks (6).

**The board.** `apply_usb_loader_v2.py` carried it into the routed board: the socket, its protection part and the VBUS capacitor to the other edge; the loader chip and its parts on the back behind them; the open-drain driver 5 mm toward the middle; R21 and R201 removed; the copper of the four freed FPGA balls removed. KiCadRoutingTools routed the 19 nets that changed with everything else locked. A keep-out now stops tracks under the socket's metal body (the first run had put a JTAG line there). The supply's way from the socket to the input switch is 55 mm, where it was 104 mm. With the room the old USB copper left, the router also finished N64 AD6, which had been open since the first routing. Method and lessons: [pcb-routing.md](design/pcb-routing.md).

**The last open connections.** After that change KiCad's check still listed three open connections and five thermal-relief errors, all older than it, and each connection was needed. `close_open_items_v2.py` closed them the same day. The N64 controller line had been complete all along: the check was reporting a via with no track on it. The supply converter's 3.3 V pin had no copper: 2.4 mm of track. The flash data line D2 sits on a ball in the corner of the FPGA and was boxed in by its two neighbours; the router laid the three together in a few seconds. Five ground pads that had room for one thermal spoke only are joined to the ground area solidly: 2.07 mm of copper against the pad where there was 0.30 mm. The check now lists **no error and no open connection, 217 of 217 signal nets complete**. The pad nets did not change, so the wiring check and the simulated board are the same.

One mistake of mine on the way, caught by the check: the router had ended two tracks inside one via, 0.2 mm apart, so that the via's copper was all that joined them. KiCad calls such a via dangling. My tidy pass removed it and cut the line it had just routed. It happened on a scratch copy; the pass now puts a short track where such a via was, and the rule is in [pcb-routing.md](design/pcb-routing.md): after any tidy pass the count of open connections must not have risen.

**The shell.** The port's recess and opening are on the player's right (`USB_SIDE = -1`); nothing else moved. The board's own 3D file was put into the shell again: nothing touches. Pictures redrawn ([v2-shell.md](design/v2-shell.md)).

**Evidence.**

| Check | Result |
|---|---|
| Schematic rule check | 0 errors, 13 warnings (unchanged); 182 parts |
| Wiring check | 22 of 22; 25 of 25 deliberate mistakes caught, five of them new for the loader chip |
| Board rule check | no error, no open connection, 217 of 217 signal nets complete; 3,891 tracks, 1,108 vias, 7,938 mm. In the morning: 6 thermal-relief errors and 6 open connections |
| `evaluate.py --mode sim` | passes: 44 entries, 92 commands |
| Route and timing | every clock passes: host 101.2 MHz (61.7 needed), SNES master 34.6 MHz (21.5 needed) |
| Game through the logic, 660 pictures | the same as before the change: all 33 pictures identical file for file, the sound identical byte for byte |
| The 49 test programs | not run again: the SNES logic under them did not change, and the game run is identical byte for byte |
| Hello World through the new board, 30 pictures | 173 pixels lit as before; same start-up times; power-off in the right order; nothing missed |
| Super Mario World through the new board, 240 pictures | Region NTSC by the key chip: 678 rounds through the board's open-drain lines, no mismatch. The game runs 456 ms after Play. The opening screen at picture 100 with 301 pixels lit, as on the board before. 240 pictures, none missed, none fetched twice, no two drivers on the data lines, no loose pins, LED lit. Power-off: `/RESET` low after 2.4 µs, pins let go after 1.0 ms, 5 V below 4.5 V after 2.4 ms, no battery RAM write. 12 of the 12 pictures written are the same, file for file, as the run on the board before the change. |
| Board with the converter's address pin on ground | refused at 40.5 ms |
| Board with the socket-to-FPGA byte enabled all the time | refused at 1.0 ms |
| Cartridge back to front, on the new board | **Refused**: the cartridge check gives up after 4.0 s with the rail at about 464 mV; the 5 V is never switched on. |
| Boot program | rebuilt for the credits: 163,840 bytes, SHA-256 `2b3f2c8d60d8e8ecf35a0feb066a3c8edfdc4c94ea458da3d3cc2221bb56e461`; host tests 1,065 checks |

The board run is quicker without the USB clocks: Hello World took 279 s where it took 438 s.

**Credits.** The TinyFPGA row is gone with the core. The ULX3S row names the loader chip's wiring. openFPGALoader is among the tools.

**Not known until a board exists:** that a real PC loads a real board through the chip. Neither the chip nor the FPGA's JTAG port is in any simulation here.

**Found and not settled:**

- The rule check still warns, about nothing that is a connection: 225 times about silkscreen text, 199 times about the mask at the N64 edge fingers, which is open across the row on purpose, and about 12 vias and 2 track ends left from the first routing. Removing those 14 on a copy opened nothing, but the stubs behind them have to be shortened, not deleted: one of them carries a line past a junction. For the hand pass.
- VBUS carries 15.8 µF by the numbers on its capacitors; USB allows a device 10 µF at plug-in. Older than this change; to settle before an order.
- The four JTAG lines are 85 to 125 mm long. Expected to be fine at the speed the PC drives them; to watch on the first board.

## 2026-10-02 — pre-order review: quote files, and four faults no simulation shows

The owner: "do everything except sending the files to pcbway because i need a quote from them first. you also need to ensure the usbc that we will use fits the hole you made, or rather vice versa". Write-up: [design/pre-order-review.md](design/pre-order-review.md). Nothing was sent to PCBWay.

**Made.**

- Manufacturing files and a sheet of values for PCBWay's forms: [hardware/sn64-v2/production](../hardware/sn64-v2/production) (`tools/make_production_v2.py`).
- A maker's part number on every bought part.
- The USB-C port in the shell from the receptacle's drawing, the USB-IF plug limits and SummerCart64's port; fit checked in CAD.
- `fpga/tools/pack_bitstream.py`: the FPGA image packed for a fast load, and the flash content as one file.

**Found and corrected on the board.**

| Fault | Correction |
|---|---|
| Ground fill between the N64 edge fingers and across the tip, inside the bare gold area | a rule area keeps fills out; the ground plane now reaches the ground fingers' vias |
| Power section laid out like signal wiring: capacitors 7 to 10 mm from the converters, coil currents through 0.15 mm tracks | laid out again by the makers' layout rules |
| Small capacitors in clumps, up to 36 mm from their chips | each at the pin it serves; the wiring check measures it |
| 5 V converter's enable tied straight to its supply; no small capacitor at its pins | R321 (10 k), C324, C325 |
| One capacitor for two supply pins at each level shifter; 100 nF where the measuring chip asks for 1 µF on each supply pin | C213 to C220; C35 now 1 µF, C46 added |
| Measuring chip's footprint with the wrong exposed pad | footprint changed, two lines laid again |
| 15.8 µF on the USB supply; a green lamp that 3.3 V cannot light | 8.0 µF; a yellow-green lamp |
| 14 routing leftovers, 225 silkscreen warnings, 218 differences between board records and schematic | removed, tidied, synced |

**Evidence.**

| Check | Result |
|---|---|
| Schematic rule check | 0 errors, 13 warnings; 194 parts |
| Board rule check with the schematic comparison | no error, no open connection, no difference; 199 notes, all at the edge fingers; 218 of 218 signal nets; 4,034 tracks, 1,118 vias, 7,914 mm |
| Wiring check | 24 of 24; 29 of 29 deliberate mistakes caught (2 checks and 4 mistakes are new) |
| Hello World through the new board, 30 pictures | 173 pixels lit as before; ends with DONE (`board-hello6`) |
| Every part against both shell halves | 307 solids, none touches. A first place for one capacitor touched the lower wall by 0.04 mm³ and was moved |
| Logic | not changed; its suite, game runs and timing stand |

**Not known until hardware or PCBWay answers:** how long a console waits before it first asks the cartridge (the FPGA is ready about 0.1 s after power-on); starting from an M64's limited cartridge supply, and power for a flash cartridge there; PCBWay's answer on 85 vias in pads, 802 vias with a 0.125 mm ring and one narrow oval hole; the cartridge socket against its footprint.

**A lesson about how the work was run.** The quote files were ready early. The layout faults then took several hours that the owner had not asked for, and he said so. From now on: report a finding with a time estimate and let him choose before spending hours on it.

**Tools added:** `apply_finger_clearance_v2.py`, `apply_review_fixes_v2.py`, `apply_power_layout_v2.py`, `make_power_plan.py`, `power_paths_v2.py`, `trim_leftovers_v2.py`, `tidy_silk_v2.py`, `sync_board_fields_v2.py`, `make_production_v2.py`, `fpga/tools/pack_bitstream.py`. The placement generator `build_v2_pcb.py` no longer makes this board; the board file is the source.

## 2026-10-02 — logos on the board, red mask, quote sheet corrected

The owner: "i want my sn64 and fantomzap logos screenprinted on there somewhere", "i want red btw", and of the board's name: "its actually v1 technically".

- `hardware/sn64-v2/tools/add_logo_silk_v2.py` prints the one-colour SN64 logo (the plain version, made for small sizes) and the FantomZap logo on the silkscreen of the back face, right of the FPGA, 30 mm wide each. The outlines come straight from the files under `assets/logo/`. The FantomZap name and logo are the owner's and are not under the open licences (`NOTICE` item 3).
- Board rule check with the schematic comparison after it: no error, no open connection, no difference, the same 199 notes at the edge fingers. No copper, hole or part was touched, so the wiring check, the board run and the shell fit stand as they are.
- Quote sheet and fabrication notes: solder mask red; inner copper 1 oz (PCBWay's form offers nothing thinner for inner layers; the sheet said 0.5 oz); the titles call the board v1, the file names keep `sn64-v2`.
- Manufacturing files and the two board pictures remade. Nothing has been sent to PCBWay.

## 2026-10-02 — the cartridge socket looked up again; PCBWay form filled

- **Socket** (owner: "Look up the socket. Theres measurments out ther"). No drawing exists for the part on sale. Forum posts and a seller's listing give: 2.5 mm pitch (as on the board); leg rows about 4.5 to 5 mm apart on the part on sale against 6 to 7 mm on original console parts; 137 x 21 x 9 mm overall with ears. The listing's photograph shows the ears as tabs beyond the ends of the body, which the shell's brackets (holes 95 mm apart, from the original console footprint) do not match. Recorded in [design/v2-shell.md](design/v2-shell.md), "Looked up again 2026-10-02". The board's pads stand; the shell's socket brackets wait for a sample.
- **PCBWay's quote form** filled in the owner's browser at his word: 111 x 70.5 mm, 5 pieces, 6 layers, 1.2 mm, red mask, white silkscreen, ENIG on board and fingers, 45 degree bevel, 1 oz copper inside and out, and the questions for their engineer in the remarks. No file attached, nothing in the cart, no price read yet.
- The owner wants PCBWay to make the shell too. The two STL halves exist; nothing uploaded.

## 2026-10-02 — shell drawn for the socket on sale

The owner: "Just use whichever sounds best". The shell now takes the copy with ears that can be bought today (137 x 21 x 9 mm by the seller) instead of the original console part, which is no longer made. No screw goes through the ears, so the unknown hole positions do not matter. The owner then: "we only need there to be room for the ears. Its held in at registration points and with screws already": the ears now have free room, 1 mm below, 0.8 mm above and 2.8 mm past their tips. The vertical screw holes at 95 mm are gone. The ears' thickness, 4.0 mm, is read from the listing's photograph and is an assumption. Both halves are valid solids; neither touches the socket, the board, the cartridge or the USB-C receptacle. Only material was taken away inside the shell, so the fit check of the board's 307 parts stands. STL and STEP files remade.

- Later the same day, before the owner sends the shell for a quote: the cartridge pocket has 1.0 mm of clearance all round (it was 0.6 mm in width and 0.3 mm front to back). The cartridge's front-to-back position on the socket rests on an assumed number (`CART_BACK_TO_PCB`), and 0.3 mm left no room for it to be wrong. The shell is now 147.4 x 100.3 x 31.9 mm. Material chosen by the owner for PCBWay: SLA resin, Somos Taurus, charcoal grey.
