# SN64 — working notes for Claude

## What this project is

SN64 is an FPGA-based SNES/Super Famicom cartridge adapter, a modern successor in concept to the TriStar 64. It plugs into the cartridge slot of an **original Nintendo 64 or a ModRetro M64**; both use the same standard N64 cartridge edge, and there are no console modifications. A real SNES cartridge sits in a full 62-contact socket on top. The FPGA recreates the SNES motherboard: CPU/PPU/APU/DMA and WRAM/VRAM/ARAM.

The N64 side does three jobs:
- supplies controller input,
- runs a bootstrap config/diagnostics menu,
- (on M64) optionally supplies supplemental USB power.

Original carts, Super EverDrive X5/X6 and FXPAK Pro are first-class targets. Manufacturing target: **PCBWay**. Source of truth: `SN_64_Engineering_Specification_Rev_A.docx`. It is expanded into 136 requirement IDs in `docs/requirements.md` and `test/acceptance-matrix.csv`, and **none are accepted yet**.

**Status (2026-09-29): early engineering, not fabrication-ready.**

| Area | What exists | Where |
|---|---|---|
| FPGA | Whole design (SNES core, cartridge bridge, N64 endpoint + CIC, SNES CIC lock, ROM-header region probe, power sequencer, Si5351 start-up, console video path (frame/audio window), cartridge audio, flash boot ROM) in `sn64_board_top`; full simulation suite passes; routed on the 85F with the real pinout, all clocks pass | `fpga/` |
| KiCad | Complete schematic draft: N64 edge J1, SNES socket J2, USB-C programmer, cartridge interface (rev 0.3.1), FPGA with real pinout, power, clock/audio sheets (HDMI output removed 2026-09-29); all static checks pass. **PCB: first autorouted draft (2026-09-30): fan-out, planes, ~80 % of signals; 75 nets and 219 plane pads still open, no DRC shorts; see `docs/design/pcb-routing.md`. `build_main_pcb.py --force` discards the routing.** | `hardware/sn64/` |
| Mechanical | FreeCAD fit references: SNES hole-pattern coupon, SummerCart64 N64 board reference. v2 shell: look-and-fit model (build123d): the real N64 cartridge lower body from SummerCart64's shell, the same outline as the stem, and a rounded mushroom cap that holds the upright SNES cartridge (`mechanical/sn64-v2-shell/`, `docs/design/v2-shell.md`); no manufacturable enclosure. Console top surface: 17.7 mm above the board's shoulders (owner measured 30 mm from it to the floor of the cartridge hole, N64 and M64, 2026-10-01). The script's `VARIANT` draws the board as it is (`board-70`) or a 10 mm shorter proposal (`short-60`: top edge 60, USB-C at 32.5) that waits for the owner's decision and is not applied to the board. | `mechanical/` |
| **v2 (branch `v2`, 2026-09-30)** | FPGA absorbs USB (TinyFPGA protocol on two pins), clocks (27 MHz + 3 PLLs), cartridge audio (sigma-delta) and rail telemetry (one I2C ADC); N64 bus switches dropped; four 16-bit translators + one hex open-drain driver. **One vertical board** (SummerCart64 edge geometry, 101.8 x 80.5 mm, 6 layers) with the SNES cartridge upright on top, in line (owner decision): the socket (console type with ears) goes on the board's top edge with its tails on both faces and its ears screwed into the shell; board refitted 2026-09-30 to the mushroom-cap tower shell (socket footprint on the top edge, outline 111 mm wide at the USB-C, USB-C 50 mm above the shoulders; `tools/refit_tower_v2.py`, `docs/design/v2-shell.md`), 213 of 218 signal nets fully connected. 176 parts. Generated schematic (ERC 0 errors), sim suite passes, FPGA routed with timing met, open items for hand routing in `hardware/sn64-v2/validation/pcb-open-connections.json`. **Write-up: `docs/design/v2-board.md`.** | `hardware/sn64-v2/`, `fpga/rtl/sn64_board_top.sv` |

## Decisions the user has made (keep them)

- **Video and audio go to the console over the cartridge bus (owner, 2026-09-29): the SN64 streams each SNES frame and its audio to the N64/M64 and the boot program shows them on the console's own output (N64 AV jack, M64 HDMI). This is the only A/V path: the board has no video output of its own (its HDMI port was removed the same day; never add a port, chip or cable the owner has not asked for).** See `docs/design/console-video-path.md`.
- **Every spec target stays in scope:** PAL, protection, save integrity, telemetry, recovery, factory test, and M64 single-HDMI (an unresolved dependency). One adapter must work on **both** N64 and M64.
- **Side-mounted USB-C data port is mandatory in rev 1.** It is used for initial FPGA/firmware load, updates and recovery, and must work without a successful console boot. PCBWay pre-programming is optional.
- **Peripherals:**
  - Standard configurable N64→SNES controller mapping.
  - **No multitap.**
  - Super Scope/Justifier undecided.
  - Virtual SNES mouse via the N64 stick is deferred to a later firmware update, but reserve input data and FPGA/flash margin for it now.
- **Reuse existing open designs first; the user explicitly wants to "piggyback".** Sources: SNESTang (core), MiSTer SNES (reference), sd2snes (translators, SuperCIC), OpenSFC (motherboard netlist), SummerCart64 (N64 endpoint/edge/shell), Sanni cartreader (SNES socket footprint), ULX3S (ECP5 power/flash).
- **Never guess dimensions.** Every dimension carries its source, revision and hash, and is marked sourced/derived/verified.
- **Document everything as you go,** in the project folder **and** on GitHub. For every checkpoint, update `docs/project-work-log.md` plus the relevant design doc.
- FPGA baseline: LFE5U-85F BG381. `-8BG381I` is in stock; `-6BG381C` is not. The 45F plus external WRAM is only an alternative to evaluate.
- **Claude drives the project (granted 2026-09-29)** and may swap any named tool for a better-suited one.
  - Current choice: KiCad for the PCB; PCBWay and all reused upstream boards use KiCad.
  - OSS CAD Suite for the ECP5.
  - build123d (code-first, diffable) is the likely enclosure tool, exporting STEP/STL. The FreeCAD references remain.
  - Record any tool change in the work log.
- **Licensing and credit (owner, 2026-10-01).** Code is GPL-3.0-or-later, hardware and docs are CERN-OHL-S-2.0 (`LICENSING.md`, `NOTICE`, the two `LICENSE-*` texts at the top level). Credit line: "SN64 by FantomZap" with the repository as source location, also on the v2 board's silkscreen (`hardware/sn64-v2/tools/add_credit_silk.py`). Upstream credits live in `CREDITS.md`: add a row whenever something new is borrowed. The GitHub repository is public; only the owner's account can write to it.
- **Logo (owner, 2026-10-01).** Four coloured buttons on two slanted pads that read SN over 64, the name in heavy slanted letters beside them, and a ring around both; the buttons are about the height of the letters. Original artwork that copies no Nintendo logo or typeface. Files, one-colour versions for embossing and the script that draws them: `assets/logo/` (see its `README.md`). Not yet placed in the top-level README, on the board or on the shell.

## v2 rules (branch `v2`)

- Everything in `hardware/sn64-v2*` is generated: `tools/build_v2_schematic.py --force` (schematics, libraries, project files), `tools/pin_plan.py` (FPGA pin map + `fpga/constraints/sn64_board.lpf`), `tools/build_v2_pcb.py --force` (placement; discards routing), `tools/prepare_route_v2.py` (fan-out, planes), `tools/apply_netclasses_v2.py`, `tools/add_plane_vias_v2.py` (run on the prepared board before routing), KiCadRoutingTools (command in `docs/design/pcb-routing.md`, v2 paths under `build/route-v2/`), `tools/finish_route_v2.py --no-import` (pours). Edit the generators, not the KiCad files, until hand layout starts.
- FPGA synthesis for v2 needs the generated vendor copies: `fpga/tools/prepare_flash_pads.py` and `fpga/tools/prepare_usb_core.py` (both run by `evaluate.py`/`route_top.py`). `route_top.py --top board --speed 8`.
- Owner decisions recorded 2026-09-30: **one board, never a split** (ask before any second board or module); the cartridge stands upright on top, in line with the board (TriStar-style tower with a mushroom cap that holds the cartridge), on a socket with ears screwed into the shell and sitting on the board's top edge; under 1 mA leakage into a switched-off console in USB-only use is accepted (bus switches dropped); the 2.5 V rail is an LDO; no series resistor arrays on the cartridge bus until measured.
- Local scripts only. No agents or cloud tools for this project unless the owner asks.

## Evidence discipline (how this repo is written)

- Keep "simulated", "static check passed" and "hardware verified" strictly separate. Do not mark a requirement accepted without the evidence the register names.
- Keep failures, negative results and red/green regression evidence (see `fpga/reports/`).
- **Do not edit `fpga/vendor/snestang/`.** Changes go through generated copies made by `fpga/tools/prepare_core.py` under `build/`. Preserve upstream licenses and notices:
  - GPL-3.0 core; SN64 HDL is GPL-3.0-or-later.
  - Sanni CC-BY-4.0.
  - SummerCart64 CERN-OHL-S-2.0.
  - usagi_ CC-BY-3.0.
  - ULX3S MIT plus a silkscreen-logo condition.
- **KiCad:** edit the native files. Never rerun `create_interface_draft.py` or `add_usb_programmer.py` with `--force`; they regenerate whole sheets.
- Never send files to PCBWay or place orders without the user's explicit go-ahead.
- **No local paths in the repository (owner, 2026-10-01; the repository is public).** KiCad netlists, check reports and notes pick up absolute paths that contain the Windows user folder. Run `python tools/scrub_local_paths.py` before committing: it rewrites that prefix to `%USERPROFILE%`, `$env:USERPROFILE` or `$HOME`, and `--check` only reports. A local pre-commit hook refuses commits that still contain it. Tool locations for this PC belong in `CLAUDE.local.md`, which is not committed.

## Checks to run after changes (from repo root)

FPGA sim (≈20 s). Tool paths are in `CLAUDE.local.md`. The build dir must contain no spaces.

```powershell
& 'C:\Program Files\KiCad\10.0\bin\python.exe' fpga/tools/evaluate.py --sim-build-dir <no-space-dir> --mode sim
```

`--mode all` adds Yosys synthesis and nextpnr-ecp5; routing alone takes ~18 min. Logs go to `build/evaluation/`. Copy reviewed snapshots into `fpga/reports/` deliberately.

KiCad static checks. These **rewrite tracked** `hardware/sn64/validation/*` reports; commit them only when the schematic really changed.

```powershell
& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware/sn64/tools/verify_interfaces.py --source-root . --kicad-cli 'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'
& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware/sn64/tools/verify_usb_programmer.py --kicad-cli 'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'
```

Baselines (2026-09-29, after the HDMI removal; all five child sheets attached): ERC 0 errors + 10 warnings (5 `isolated_pin_label` on reserved N64 labels, 5 `pin_to_pin` on cart U206); `verify_interfaces` 31/31 (J2 is the socket-board joint); `verify_usb_programmer` 69/69; `verify_cart_interface` 20/20 (negative 6/6); `verify_fpga_sheet` 14/14 with `--lattice-csv build/fpga-sheet/datasheets/ECP5U-85-pinout.csv --datasheets build/fpga-sheet/datasheets` (13/13 without; negative 10/10); `verify_power_sheet` 23/23 (negative 12/12); `verify_av_clock_sheet` 27/27 (negative 10/10); `verify_root_connectivity` 4/4 (negative 4/4); `verify_socket_joint` 9/9 (negative 3/3) across hardware/sn64 and hardware/sn64-socket. The command block is in `hardware/sn64/README.md`. Mechanical scripts take `--source-root .` now that `references/downloads/` is local (see `mechanical/README.md`).

## Next engineering work (from the plan's "Next" section)

1. **Cartridge bridge:**
   - verified responder selection
   - bus-ownership/turnaround model with a bus-resolution testbench that fails on contention
   - DMA matrix, clock/reset checks, hardware fault gating
   - (`docs/design/physical-cartridge-bridge.md`)
2. **Socket:** select and dimension a real SNES socket. The sample candidate is NES Repair Shop `snspt043`. (`docs/design/socket-selection.md`)
3. **Power budget and paths:**
   - both hosts, and the M64 accessory-USB power option
   - TPS259470L cartridge eFuse, TPS3700 monitor, SN74LVC4245A translators (A=5 V cart)
   - (`docs/design/power-architecture.md`)
4. Add bridge and host logic to the synthesis/route evaluation, then fix the FPGA package, pins and memory.
5. Complete the protected schematic, then PCB layout (six layers preferred to evaluate), then the FreeCAD enclosure with the side USB-C opening, then the PCBWay prototype package.
6. **PCB routing, next steps:** loosen the translator row (the congested area), finish the 75 open nets and 219 plane pads by hand in KiCad or with KiCadRoutingTools (`%USERPROFILE%\Tools\KiCadRoutingTools`, venv `%USERPROFILE%\Tools\krt-venv`; pin it with `hardware/sn64/tools/fab-pcbway.txt`), settle PCBWay annular ring (6 mil) and spacing (5 mil) against the board's 0.125 / 0.1 mm rules with the quote. Freerouting is the fallback, not the default.

Key docs: `README.md` (index), `docs/architecture.md`, `docs/superpowers/plans/2026-09-28-sn64-engineering-plan.md`, `docs/project-work-log.md`, `fpga/README.md`, `hardware/sn64/README.md`, `mechanical/README.md`.
