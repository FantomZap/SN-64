# Console-core evaluation

This directory contains a reproducible **console-only engineering candidate** built from SNESTang. It is not programmable SN64 release firmware. The blocks listed below (bridge, N64 endpoint and CIC, console video path, power sequencing, clocks, flash boot ROM, cartridge audio) are integrated in `rtl/sn64_top.sv` and routed on the board pinout, but everything is simulated or synthesised only: no bitstream has been generated or run on hardware.

- [Pinned upstream selection and hashes](vendor/snestang/provenance.json), with original GPL license and file notices retained.
- [Candidate wrapper](rtl/sn64_console_candidate.sv): CPU/PPU/APU plus 128 KiB WRAM, 64 KiB VRAM and 64 KiB ARAM in synchronous inferred RAM.
- [Diagnostic](tests/tb_console_boot.sv): original instruction program; no commercial game image.
- [WRAM bus diagnostic](tests/tb_wram_bus.sv): active-cycle RAM data, direct/mirrored addresses, RAM port and B-to-A DMA.
- [Cartridge bridge](rtl/sn64_cart_bridge.sv) and [socket-facing top](rtl/sn64_console_with_bridge.sv): data-bus ownership with one released clock at every turnaround; [physical-bus diagnostic](tests/tb_cart_bridge.sv) with contention monitor and a fault-injected run. See [implementation notes](../docs/design/cartridge-bridge-implementation.md).
- [N64/M64 endpoint](rtl/sn64_n64_endpoint.sv): vendored [SummerCart64 PI controller](vendor/summercart64/provenance.json) (GPL-3.0, unmodified) with an SN64 bootstrap ROM window and mailbox; [host-model diagnostic](tests/tb_n64_endpoint.sv). See [endpoint notes](../docs/design/n64-endpoint-implementation.md).
- [N64 CIC lockout](../docs/design/n64-cic-implementation.md): vendored SummerCart64 CIC (SERV soft core, ISC) running the vendored UltraCIC_C firmware (MIT); build the image with `fpga/tools/build_cic.py` (xPack riscv-none-elf-gcc), then [tb_n64_cic.sv](tests/tb_n64_cic.sv) checks the ID, seed and checksum streams against an independent reference.
- [Recorded evaluation](reports/evaluation.md) and [machine-readable evidence](reports/evaluation.json).
- [Board top level](rtl/sn64_board_top.sv): one ECP5 PLL (25 -> 62.5 MHz), one DCSC that selects the NTSC/PAL SNES master and starts/stops it glitchlessly, bootstrap ROM from the configuration flash, CIC pads, and the pad adapters the FPGA schematic sheet needs (cart_data inout, open-drain Si5351 I2C, cart_reset_pull_n, reserved JOYBUS/INT, cartridge-audio ADC inputs). Its pins come from [constraints/sn64_board.lpf](constraints/sn64_board.lpf), generated with the [FPGA sheet](../docs/design/fpga-schematic.md). Route it with `python tools/route_top.py` (default `--top board` with the real LPF; `--lpf` selects another constraint file, e.g. the older `constraints/sn64_board_trial.lpf`; see [integration notes](../docs/design/system-integration.md)).
- [Cartridge analog audio](../docs/design/cart-audio-implementation.md): [sn64_i2s_rx.sv](rtl/sn64_i2s_rx.sv) (I2S receiver sampled by the 62.5 MHz host clock) and [sn64_audio_mix.sv](rtl/sn64_audio_mix.sv) (elastic buffer into the SNES domain, saturating mix with the DSP output); [bench](tests/tb_audio_mix.sv) with four fault builds.
- [Console video path](../docs/design/console-video-path.md): [sn64_frame_window.sv](rtl/sn64_frame_window.sv) (RGBA5551 frame buffer and audio ring behind the endpoint's PI domain-2 window at 0x0800_0000); [bench](tests/tb_frame_window.sv) with a PI host model at fast timing and a fault build. The board's own HDMI output was removed on 2026-09-29 ([retired notes](../docs/design/av-output-implementation.md)).
- [Frame lock](../docs/design/frame-lock.md): [sn64_clock_pace.sv](rtl/sn64_clock_pace.sv) makes the SNES master by halving a doubled PLL clock and can slow it in 0.5 ppm steps (mailbox `PACE`); the frame window reports where the SNES is in its picture (`FRAME_PHASE`). [Bench](tests/tb_clock_pace.sv): no shortened pulse, exact stretch counts; fault builds for the divider, the position counter and the register decode.
- [Bootstrap ROM from flash](rtl/sn64_bootrom_flash.sv): vendored SummerCart64 `memory_flash` (QSPI EBh, unmodified) behind the endpoint's ROM window, `ROM_FROM_FLASH=1`; [bench](tests/tb_bootrom_flash.sv) with a QSPI flash model. See [notes](../docs/design/bootrom-flash.md).
- [ROM-header region probe](rtl/sn64_header_probe.sv): reads the SNES header with the cartridge held in reset to pick NTSC/PAL when there is no key CIC; [bench](tests/tb_header_probe.sv). See [notes](../docs/design/header-region-probe.md).
- [CIC pad sequencing](rtl/sn64_cic_pad.sv): SN74LVC1T45 DIR against pad drive; [bench](tests/tb_cic_pad.sv).
- [Cartridge check](../docs/design/reversed-cartridge-detection.md): before the cartridge's 5 V is switched on, [sn64_rail_monitor.sv](rtl/sn64_rail_monitor.sv) feeds a small test current into the rail through the telemetry ADC and [sn64_power_sequencer.sv](rtl/sn64_power_sequencer.sv) refuses a cartridge that is in back to front (modes: enforce, report only, off, check only); [bench](tests/tb_cart_check.sv) with an ADC model and an electrical model of the rail. Simulated only.
- [A real game through the simulated SN64](../docs/design/game-simulation.md): [tb_game.sv](tests/tb_game.sv) is the whole-system bench with a cartridge that holds a real image and an N64 side that fetches every picture through the cartridge port as the boot program does. `tools/run_game.py` runs one image and writes pictures and sound; `tools/run_game_suite.py` runs a folder of test programs. No image is in the repository. Its first run found the DMA fault in the cartridge bridge.
- [Physical-cartridge bridge work](../docs/design/physical-cartridge-bridge.md) and [FPGA selection](../docs/design/fpga-board-selection.md).

## What is reused and changed

SummerCart64's PI controller is vendored separately under `vendor/summercart64/` with its own provenance and GPL-3.0 license. The 35 SNESTang files come from SNESTang commit `5f0ef193145f67bded7f73f2c477ac8da4d85f7e`. They retain their upstream content except newline normalization recorded per file. The ROM-loader/cartridge-emulation wrapper is excluded so the real cartridge retains its ROM, save memory and enhancement hardware.

`tools/prepare_core.py` verifies every source hash and writes generated copies under ignored `build/`. It selects the upstream `VERILATOR` inferred-memory branch, omits ten simulation-only diagnostic statements, connects HIGH_RES, exports PHI2, ties the open TURBO input low and exports the CPU/DMA/HDMA address **before** the upstream WRAM mirror conversion. Internal RAM decoding keeps its original address path. The generated preparation manifest lists changes and hashes. No vendor file is patched in place.

The diagnostic checks reset-vector fetch, native CPU execution, external 16-bit reads/writes, 16-bit WRAM readback, preservation of a low-bank mirrored address, a B-bus write, cartridge-to-WRAM DMA and PHI2 presence. A corrupted cartridge read must produce the expected failure. Both PAL mode-bit values run, but the test clock remains the same: this is **not PAL clock/video qualification**. It does not yet exercise graphics, sound, HDMA, cartridge select qualification, open bus, output-enable timing or real cartridges.

The wrapper now selects the current WRAM byte for `cart_data_out` during an active RAM read instead of the previous MDR byte. `cart_wram_read_valid` qualifies that source with core enable/reset and RAM CE/OE. It is **not** a complete translator output enable. The separate bus diagnostic checks direct reads, both low-memory mirrors, CPU RAM-port reads, B-to-A DMA and immediate source-valid removal during pause/reset with the clock stopped. CPU-internal register reads remain distinct from electrically visible data; see [source evidence](../docs/design/bus-electrical-evidence.md).

## Reproduction

CIC firmware (needed for the CIC test; otherwise that test is reported as skipped):

```powershell
python fpga/tools/build_cic.py --toolchain C:/path/to/xpack-riscv-none-elf-gcc/bin
```

Use [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-09-28) for Yosys/Slang, Verilator and nextpnr-ecp5. Windows also needs a C++ compiler and GNU Make; the inspected [w64devkit 2.10.0](https://github.com/skeeto/w64devkit/releases/tag/v2.10.0) provides both. These portable tools were installed under the user's `.codex/tools` folder without changing system PATH. [Tool versions and archive hashes](reports/toolchain.json) identify this run.

From the repository root, adapt the two installation paths:

```powershell
. 'C:/path/to/oss-cad-suite/environment.ps1'
$env:PATH = 'C:/path/to/w64devkit/bin;' + $env:PATH
& 'C:/Program Files/KiCad/10.0/bin/python.exe' fpga/tools/evaluate.py --sim-build-dir C:/sn64-build/sim-console --mode all
```

The Verilator object directory must contain no spaces, even if the repository does. On Windows the runner invokes `verilator_bin.exe` and sets its installed `VERILATOR_ROOT`; the extensionless Perl wrapper is not relied upon. Normal Python 3 works too; KiCad's bundled Python was convenient here. No network download is needed to prepare or evaluate the vendored core once tools are installed.

`--mode sim` runs all diagnostics, including the bridge bench and its fault-injected build (which must fail); `--mode synth` maps the core; `--mode pnr` uses the **existing** `build/console-ecp5.json` and does not independently establish that it matches current sources. Use `--mode all` for a current complete experiment. Logs and the fresh report are written to `build/evaluation/`; reviewed snapshots are copied into `fpga/reports/` deliberately.

Yosys uses `scratchpad -set abc9.xaiger 1`: the pinned Windows build's experimental XAIGER2 backend asserted during export. This selects its existing older XAIGER path; it does not skip logic mapping. The synthesis report explicitly checks that the mapped TURBO control is constant zero. Earlier static-function alias and unused-debug warnings are preserved, not represented as a warning-free build.

P&R targets an ECP5-85F, CABGA381, speed grade 6, at 21.477273 MHz **with unconstrained trial I/O locations**. No board pinout or external setup/hold constraints have been applied and no bitstream is generated. The result is evidence for internal resource/timing feasibility only; the full design must repeat it after host, A/V, protection and board constraints are added.

## License and source availability

The selected core is distributed with [upstream GPL-3.0 text](vendor/snestang/LICENSE) and retained file-level notices. SN64's wrapper and diagnostic use GPL-3.0-or-later. Keep this source, preparation patches, manifests and build instructions with future derived distributions; complete combined-project license review before releasing a product. Other hardware/CAD licenses are tracked in their own directories.
