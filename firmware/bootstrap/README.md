# SN64 bootstrap ROM (N64/M64 side)

The small program an N64 or M64 boots from the SN64 cartridge. It shows the SN64 menu, reads the N64 controllers, maps them to SNES button images and writes them to the SN64 mailbox every frame. It also lets the user request or drop SNES cartridge power. Built with [libdragon](https://github.com/DragonMinded/libdragon) (Unlicense). SN64 sources are GPL-3.0-or-later.

**Status:** builds, passes the CIC-6102 boot-checksum check, and passes host tests and an RTL co-simulation with the FPGA endpoint. **It has not run on an N64, an M64 or an emulator.** Design notes, evidence and limits are in [docs/design/n64-bootstrap.md](../../docs/design/n64-bootstrap.md).

## Layout

| Path | What |
|---|---|
| `src/main.c` | Menu, controller loop, mailbox access (libdragon `display`, `graphics`, `joypad`, `io_read`/`io_write`) |
| `src/sn64_mailbox.h` | Register map at `0x1FFF_0000`, the 32-bit register pairing, and the provisional STATUS bit layout, REGION_INFO/REGION_SOURCE layouts |
| `src/sn64_mapping.[ch]` | N64 to SNES mapping table and function, the menu shortcut, changing the table (pure C, host-testable) |
| `src/sn64_padview.[ch]` | Controller pictures in the controllers' real shapes, with buttons that light up, and the single-button pictures of the mapping screen (pure C, host-testable). No maker's logo |
| `src/sn64_padshape.h`, `src/sn64_padshape_data.c`, `tools/make_padshapes.py` | The outlines of the player's controllers as pixel runs, generated from the outline points in the script (`make padshapes`); `make test` fails if the file is stale |
| `src/sn64_mapscreen.[ch]` | The controller mapping screen: cursor, the two controller lists, the choices for a row, drawing (pure C, host-testable) |
| `src/sn64_credits.[ch]`, `src/sn64_credits_data.c` | Credits roll: which lines are on screen (pure C, host-testable) and the text, generated from `CREDITS.md` by `tools/make_credits.py` (`make credits`) |
| `src/sn64_framelock.[ch]` | Frame lock: timing numbers for each console and region, the compatibility-mode confirmation text, the control loop (pure C, host-testable) |
| `src/sn64_resample.[ch]`, `src/sn64_audioout.[ch]` | Sound: cubic resampler with rate control, and the queue that hands the console one block per picture (pure C, host-testable) |
| `rom.mk` | libdragon ROM build (runs inside the output directory) |
| `Makefile` | Entry point: `rom`, `check`, `words`, `test`, `test-negative`, `clean` |
| `tests/test_mapping.c` | Host unit test of the default mapping, the shortcut and changing the table |
| `tests/test_padview.c`, `tests/test_mapscreen.c` | Host tests of the controller pictures (every button lights its own place and no other) and of the mapping screen (what the buttons do, what is drawn). `test_mapscreen` also writes the screens for `tools/mock_screens.py` |
| `tests/test_framelock.c`, `tests/test_resample.c`, `tests/test_audioout.c` | Host tests of the frame lock (against a model of the two clocks), the resampler, and the sound queue (against a model of the console's sound output) |
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

- **Since 2026-10-01 the ROM image needs `ROM_ADDR_BITS = 17`** (256 KiB, what the v2 board has): the image is 163,840 bytes since the stick option (150,073 used); with the frame lock and the sound queue it was 147,456 bytes, 357 bytes over a 128 KiB window (2 KB over since the credits roll). The Makefile, the co-simulation bench and its script default to 17. History: the ROM image needed **`ROM_ADDR_BITS = 16`** (64 Ki words = 128 KiB) with the default aPLib compression (`N64_ROM_ELFCOMPRESS=2`). It was 114,688 bytes before the console video path; with the display loop it is 131,072 bytes (exactly the 128 KiB window; the board top uses `ROM_ADDR_BITS = 17`, 256 KiB, for headroom). With libdragon's default LZ4 it is 147,456 bytes and needs 17. The endpoint's current default of 12 (8 KiB) is too small; the converter rejects the image for it.
- Word image: `word[i] = rom[2i] << 8 | rom[2i+1]`. Line *i* of the `.mem` file is `rom_waddr` *i*, with zero padding up to `2**ROM_ADDR_BITS`.
- Mailbox registers are accessed only as 32-bit pairs: `{MAGIC,VERSION}`, `{STATUS,SEQ}`, `{FAULT,CART_CHECK}`, `{JOY1,JOY2}`, `{JOY1_STICK,CONTROL}`, `{COMMIT,REGION_INFO}` (COMMIT written, REGION_INFO read), `{REGION_SOURCE,FRAME_STATUS}`, `{AUDIO_WPTR,VIDEO_MODE}`, `{FEATURES,-}` (read) and `{FRAME_PHASE,PACE}` (read; a write sets PACE). The bootstrap never writes unless MAGIC reads `0x534E`.
- SNES button image: bit 0 = B, then Y, Select, Start, Up, Down, Left, Right, A, X, L, R (bit 11). **1 = pressed.** Bits 15:12 are 0.

## Controls

- **Main menu (owner, 2026-10-01):** Play, Controller mapping, Settings, Power off cartridge. Up/Down to move, A to choose, B to go back.
- **Settings:** Compatibility mode, Status / diagnostics (the service screen is behind Z there), Credits.
- **Play:** sets `CONTROL.run_request` and forwards both controllers, or goes back to a cartridge that is still running. While the menu is shown, the SNES sees a neutral pad.
- **Returning to the menu:** press **all four C buttons together** on controller 1 (they have to be down together for a tenth of a second). The cartridge keeps running, and the game is not given the four buttons.
- **Power off cartridge:** clears `run_request`.

## Controller mapping

Defaults (owner, 2026-10-01): every button gives the Super NES button of the same name (A, B, L, R, Start, the D-pad) and Z gives Select. X and Y have no namesake, so the C buttons give the Super NES diamond: C-Up X, C-Left Y, C-Down B, C-Right A.

**The stick** presses the D-pad when it is pushed past a set part of its travel: one direction within 22.5 degrees of an axis, two at once towards a corner. The first row of the mapping list sets it: the D-pad from 20 to 80 % in steps of ten (50 % to begin with), or nothing. How far is measured from the middle, a full throw being taken as 80 of the controller's units. With the cursor on that row the screen shows how far the stick is pushed now.

The mapping screen shows the controller in the player's hands and the controller the game sees side by side, in their real shapes. Buttons light up as they are pressed: on the left the button held, on the right the button the game is given. A list over each picture names the controller and chooses which one is drawn (left: N64 controller, M64 Pro, Hyperkin Captain, Switch N64 pad, Brawler64, 8BitDo 64; right: Super NES or Super Famicom colours); the lists change the picture only. Under the Super NES controller is the mapping: the stick's row and 14 button rows, ten on the screen at a time, each with a small picture of the single button and of the button it gives; the list scrolls with the cursor. A on a row opens its choices, "Restore defaults" puts the defaults back. Only the D-pad, A and B do anything on this screen, so every other button can be tried; B leaves when it is let go.

The outlines follow photographs of the controllers lying flat (`tools/make_padshapes.py` says which); the pictures carry no maker's logo. Nothing is kept when the console is switched off. Mock-ups: `docs/design/img/mapping-screens.png` and `menu-screens.png` (`make test-mapscreen`, then `python tools/mock_screens.py`).

## Credits

"Credits" under Settings rolls the repository's [CREDITS.md](../../CREDITS.md) up the screen: the credit line, everyone whose work SN64 builds on, the tools, and the SN64 crew at the end. A makes it quicker, B goes back. After changing `CREDITS.md` run `make credits`; `make test` fails if the roll is stale.

## Frame lock and compatibility mode

The menu and the logos run on the console's own picture timing. While a game is shown the console's timing takes the Super NES's shape and the game's clock is held to the console's, so no picture is dropped or shown twice. "Compatibility mode" under Settings leaves the console's timing alone and slows the game by 0.45 % instead (0.18 % on a 50 Hz console); choosing it shows a confirmation that says so. It is off after every start-up. If the picture is lost when a game starts, hold Z+L+R for a second or reset the console, then turn it on. Design, numbers and what is still to be checked on hardware: [docs/design/frame-lock.md](../../docs/design/frame-lock.md).

## Cartridge check

The check is in the FPGA: before the cartridge's 5 V is switched on, a small test current shows whether the cartridge is in back to front. It is not a menu option: "Play" runs it and a cartridge that fails is not powered (`SN64_CHECK_MODE_DEFAULT` in `src/main.c` is enforce). Its test tools are on a service screen the main menu does not show: Settings, Status / diagnostics, then Z (A: check now without power; L or R: enforce, report only or off until the console is reset). Screens and wording: `src/sn64_cartcheck.c`, tested on the host by `tests/test_cartcheck.c`. Design note: `docs/design/reversed-cartridge-detection.md`.

## Splash screens

At start-up the program shows the SN64 logo, then the owner's FantomZap logo, then the menu (about 2 s each; A, B or Start skips). The pictures are generated: `make splash` runs `tools/make_splash.py`, which draws the logo files in `assets/logo/` at screen size and writes `src/sn64_splash_data.c` (needs PyMuPDF and Pillow). Drawing code: `src/sn64_splash.c`, tested on the host by `tests/test_splash.c`. `tools/mock_screens.py` draws mock-ups of the splash and menu screens into `docs/design/img/`.
