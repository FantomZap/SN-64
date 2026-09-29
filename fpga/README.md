# Console-core evaluation

This directory contains a reproducible **console-only engineering candidate** built from SNESTang. It is not programmable SN64 release firmware: the physical bus drive/receive logic, hardware power interlocks, N64 endpoint/bootstrap, CIC, complete clocks, configuration storage, cartridge audio and digital A/V output are still being integrated.

- [Pinned upstream selection and hashes](vendor/snestang/provenance.json), with original GPL license and file notices retained.
- [Candidate wrapper](rtl/sn64_console_candidate.sv): CPU/PPU/APU plus 128 KiB WRAM, 64 KiB VRAM and 64 KiB ARAM in synchronous inferred RAM.
- [Diagnostic](tests/tb_console_boot.sv): original instruction program; no commercial game image.
- [Recorded evaluation](reports/evaluation.md) and [machine-readable evidence](reports/evaluation.json).
- [Physical-cartridge bridge work](../docs/design/physical-cartridge-bridge.md) and [FPGA selection](../docs/design/fpga-board-selection.md).

## What is reused and changed

The 35 vendored files come from SNESTang commit `5f0ef193145f67bded7f73f2c477ac8da4d85f7e`. They retain their upstream content except newline normalization recorded per file. The ROM-loader/cartridge-emulation wrapper is excluded so the real cartridge retains its ROM, save memory and enhancement hardware.

`tools/prepare_core.py` verifies every source hash and writes generated copies under ignored `build/`. It selects the upstream `VERILATOR` inferred-memory branch, omits ten simulation-only diagnostic statements, connects HIGH_RES, exports PHI2, ties the open TURBO input low and exports the CPU/DMA/HDMA address **before** the upstream WRAM mirror conversion. Internal RAM decoding keeps its original address path. The generated preparation manifest lists changes and hashes. No vendor file is patched in place.

The diagnostic checks reset-vector fetch, native CPU execution, external 16-bit reads/writes, 16-bit WRAM readback, preservation of a low-bank mirrored address, a B-bus write, cartridge-to-WRAM DMA and PHI2 presence. A corrupted cartridge read must produce the expected failure. Both PAL mode-bit values run, but the test clock remains the same: this is **not PAL clock/video qualification**. It does not yet exercise graphics, sound, HDMA, cartridge select qualification, open bus, output-enable timing or real cartridges.

## Reproduction

Use [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-09-28) for Yosys/Slang, Verilator and nextpnr-ecp5. Windows also needs a C++ compiler and GNU Make; the inspected [w64devkit 2.10.0](https://github.com/skeeto/w64devkit/releases/tag/v2.10.0) provides both. These portable tools were installed under the user's `.codex/tools` folder without changing system PATH. [Tool versions and archive hashes](reports/toolchain.json) identify this run.

From the repository root, adapt the two installation paths:

```powershell
. 'C:/path/to/oss-cad-suite/environment.ps1'
$env:PATH = 'C:/path/to/w64devkit/bin;' + $env:PATH
& 'C:/Program Files/KiCad/10.0/bin/python.exe' fpga/tools/evaluate.py --sim-build-dir C:/sn64-build/sim-console --mode all
```

The Verilator object directory must contain no spaces, even if the repository does. On Windows the runner invokes `verilator_bin.exe` and sets its installed `VERILATOR_ROOT`; the extensionless Perl wrapper is not relied upon. Normal Python 3 works too; KiCad's bundled Python was convenient here. No network download is needed to prepare or evaluate the vendored core once tools are installed.

`--mode sim` runs diagnostics; `--mode synth` maps the core; `--mode pnr` uses the **existing** `build/console-ecp5.json` and does not independently establish that it matches current sources. Use `--mode all` for a current complete experiment. Logs and the fresh report are written to `build/evaluation/`; reviewed snapshots are copied into `fpga/reports/` deliberately.

Yosys uses `scratchpad -set abc9.xaiger 1`: the pinned Windows build's experimental XAIGER2 backend asserted during export. This selects its existing older XAIGER path; it does not skip logic mapping. The synthesis report explicitly checks that the mapped TURBO control is constant zero. Earlier static-function alias and unused-debug warnings are preserved, not represented as a warning-free build.

P&R targets an ECP5-85F, CABGA381, speed grade 6, at 21.477273 MHz **with unconstrained trial I/O locations**. No board pinout or external setup/hold constraints have been applied and no bitstream is generated. The result is evidence for internal resource/timing feasibility only; the full design must repeat it after host, A/V, protection and board constraints are added.

## License and source availability

The selected core is distributed with [upstream GPL-3.0 text](vendor/snestang/LICENSE) and retained file-level notices. SN64's wrapper and diagnostic use GPL-3.0-or-later. Keep this source, preparation patches, manifests and build instructions with future derived distributions; complete combined-project license review before releasing a product. Other hardware/CAD licenses are tracked in their own directories.
