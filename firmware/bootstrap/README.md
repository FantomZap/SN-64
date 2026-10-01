# SN64 bootstrap ROM (N64/M64 side)

The small program an N64 or M64 boots from the SN64 cartridge. It shows the SN64 menu, reads the N64 controllers, maps them to SNES button images and writes them to the SN64 mailbox every frame. It also lets the user request or drop SNES cartridge power. Built with [libdragon](https://github.com/DragonMinded/libdragon) (Unlicense). SN64 sources are GPL-3.0-or-later.

**Status:** builds, passes the CIC-6102 boot-checksum check, and passes host tests and an RTL co-simulation with the FPGA endpoint. **It has not run on an N64, an M64 or an emulator.** Design notes, evidence and limits are in [docs/design/n64-bootstrap.md](../../docs/design/n64-bootstrap.md).

## Layout

| Path | What |
|---|---|
| `src/main.c` | Menu, controller loop, mailbox access (libdragon `display`, `graphics`, `joypad`, `io_read`/`io_write`) |
| `src/sn64_mailbox.h` | Register map at `0x1FFF_0000`, the 32-bit register pairing, and the provisional STATUS bit layout, REGION_INFO/REGION_SOURCE layouts |
| `src/sn64_mapping.[ch]` | N64 to SNES mapping table and function (pure C, host-testable) |
| `rom.mk` | libdragon ROM build (runs inside the output directory) |
| `Makefile` | Entry point: `rom`, `check`, `words`, `test`, `test-negative`, `clean` |
| `tests/test_mapping.c` | Host unit test of the default mapping |
| `tests/tb_bootstrap_rom_window.sv` | Verilator bench: loads the converted image into `sn64_n64_endpoint`, reads it back over the PI model, and replays the per-frame mailbox traffic |
| `tools/setup_libdragon.sh` | Pinned, SHA-256-checked toolchain + libdragon install (no admin, no Docker, no WSL) |
| `tools/n64_cic_check.py` | CIC-6102 boot check (IPL2 hash of IPL3, ported from ares, ISC) |
| `tools/z64_to_rom_words.py` | `.z64` to FPGA ROM-window word image (`$readmemh`, big-endian 16-bit) |
| `tools/test_rom_tools.py` | Self-checking test of both tools, with `--inject-fault` |
| `tools/run_rom_window_sim.ps1` | Builds and runs the Verilator bench, then the fault-injected run |

## Build (Windows, Git Bash)

```bash
bash firmware/bootstrap/tools/setup_libdragon.sh          # once, ~1 min
export N64_INST="$(cygpath -m "$HOME")/.codex/tools/libdragon-gcc-toolchain-20260915/n64inst"
export PATH="$HOME/.codex/tools/libdragon-gcc-toolchain-20260915/n64inst/bin:$PATH"
cd firmware/bootstrap
make                 # -> build/n64-bootstrap/sn64_bootstrap.z64
make check           # CIC-6102 boot checksum
make words           # -> build/n64-bootstrap/sn64_bootstrap_words.mem (+ .json manifest)
make test HOST_CC=$HOME/.codex/tools/w64devkit-2.10.0/w64devkit/bin/gcc.exe
make test-negative HOST_CC=$HOME/.codex/tools/w64devkit-2.10.0/w64devkit/bin/gcc.exe
```

From the repository root in PowerShell, after `make words`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File firmware/bootstrap/tools/run_rom_window_sim.ps1
```

Build outputs stay under `build/n64-bootstrap/`. Do not commit ROM binaries.

## FPGA contract

- The ROM image needs **`ROM_ADDR_BITS = 16`** (64 Ki words = 128 KiB) with the default aPLib compression (`N64_ROM_ELFCOMPRESS=2`). It was 114,688 bytes before the console video path; with the display loop it is 131,072 bytes (exactly the 128 KiB window; the board top uses `ROM_ADDR_BITS = 17`, 256 KiB, for headroom). With libdragon's default LZ4 it is 147,456 bytes and needs 17. The endpoint's current default of 12 (8 KiB) is too small; the converter rejects the image for it.
- Word image: `word[i] = rom[2i] << 8 | rom[2i+1]`. Line *i* of the `.mem` file is `rom_waddr` *i*, with zero padding up to `2**ROM_ADDR_BITS`.
- Mailbox registers are accessed only as 32-bit pairs: `{MAGIC,VERSION}`, `{STATUS,SEQ}`, `{JOY1,JOY2}`, `{JOY1_STICK,CONTROL}`, `{COMMIT,REGION_INFO}` (COMMIT written, REGION_INFO read) and `{REGION_SOURCE,-}` (read). The bootstrap never writes unless MAGIC reads `0x534E`.
- SNES button image: bit 0 = B, then Y, Select, Start, Up, Down, Left, Right, A, X, L, R (bit 11). **1 = pressed.** Bits 15:12 are 0.

## Controls

- **Menu:** Up/Down to move, A to choose, B to go back.
- **Start SNES cartridge:** sets `CONTROL.run_request` and forwards both controllers. While the menu is shown, the SNES sees a neutral pad.
- **Returning to the menu:** hold **Z+L+R for about 1 s**. The cartridge keeps running.
- **Power down cartridge:** clears `run_request`.
