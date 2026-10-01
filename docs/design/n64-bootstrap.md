# N64 bootstrap ROM: implementation and evidence

Implemented 2026-09-29. This is the first version of the program the N64 or M64 runs from the SN64 cartridge. It is built with libdragon and passes a boot-checksum check, host unit tests and a co-simulation against the FPGA N64 endpoint. **It has not run on an N64, an M64 or an emulator.** The register contract is the [endpoint note](n64-endpoint-implementation.md). Relevant requirements are SN64-06-01, -06-02, -06-03, -09-02 and -08-13; none is accepted by this work.

## Plain-language summary

When the console powers on, it runs whatever program the cartridge holds. For SN64, that program is a small menu. It shows the adapter's version and power status, and offers four items: start the SNES cartridge, show the controller mapping, show diagnostics, and power the cartridge down. Every frame it reads the N64 controllers, converts the buttons to SNES buttons, and hands them to the FPGA through the mailbox registers. A default mapping is built in: the D-pad and Start go straight across, Z becomes Select, and the face and C buttons form the SNES A/B/X/Y diamond. Nothing is written to the adapter unless it first answers with the SN64 signature, and the cartridge stays unpowered until the user chooses to start it.

## Files

| File | Role |
|---|---|
| [firmware/bootstrap/src/main.c](../../firmware/bootstrap/src/main.c) | Menu, 60 Hz controller/mailbox loop, screens |
| [firmware/bootstrap/src/sn64_mailbox.h](../../firmware/bootstrap/src/sn64_mailbox.h) | Register map, 32-bit pairing rule, provisional STATUS layout |
| [firmware/bootstrap/src/sn64_mapping.c](../../firmware/bootstrap/src/sn64_mapping.c) / `.h` | Default N64 to SNES table and mapping function; no libdragon dependency |
| [firmware/bootstrap/Makefile](../../firmware/bootstrap/Makefile), `rom.mk` | Build, check, convert, test, fault-injection targets |
| [firmware/bootstrap/tools/setup_libdragon.sh](../../firmware/bootstrap/tools/setup_libdragon.sh) | Pinned toolchain install with SHA-256 check |
| [firmware/bootstrap/tools/n64_cic_check.py](../../firmware/bootstrap/tools/n64_cic_check.py) | CIC-6102 boot check (IPL2 hash of the IPL3 block) |
| [firmware/bootstrap/tools/z64_to_rom_words.py](../../firmware/bootstrap/tools/z64_to_rom_words.py) | `.z64` to ROM-window word image, with a hard size check |
| [firmware/bootstrap/tools/test_rom_tools.py](../../firmware/bootstrap/tools/test_rom_tools.py) | Self-checking tool test with `--inject-fault` |
| [firmware/bootstrap/tests/test_mapping.c](../../firmware/bootstrap/tests/test_mapping.c) | Host mapping test; `-DSN64_FAULT_SWAP_AB` injects a wrong table |
| [firmware/bootstrap/tests/tb_bootstrap_rom_window.sv](../../firmware/bootstrap/tests/tb_bootstrap_rom_window.sv) | Verilator bench: converted image into `sn64_n64_endpoint`, PI read-back, per-frame mailbox traffic; `+corrupt_load` injects a fault |
| [firmware/bootstrap/tools/run_rom_window_sim.ps1](../../firmware/bootstrap/tools/run_rom_window_sim.ps1) | Builds and runs that bench plus its negative run |

## What is reused

| Source | Version | License | Use |
|---|---|---|---|
| libdragon | trunk `e356bf3f56f7afbf7e5246329562f145965cfdfc` (2026-09-15) | Unlicense | Linked into the ROM. Its IPL3 (`tools/ipl3.h`, the production build) is signed for CIC-6102 (libdragon `boot/README.md`), so no header CRC is needed. Its `n64tool`, `n64sym` and `n64elfcompress` build the image. |
| libdragon toolchain | `gcc-toolchain-mips64-win64.zip`, release `toolchain-continuous-prerelease`, asset of 2026-09-15, GCC 16.2.0 | GPL (GCC/binutils); tools only | `mips64-elf-*` and `make.exe` |
| ares | `mia/medium/nintendo-64.cpp` at `433d07fbdb90b02e6a0947b9de0fe5670378c375` | ISC | `ipl2checksum` ported to Python in `n64_cic_check.py`; the ISC notice is kept in the file |
| SN64 `tb_n64_endpoint.sv` | this repo | GPL-3.0-or-later | PI host-model tasks copied into the integration bench |

Toolchain SHA-256: `bd201c35afee4aceb9d2a80c6dc9d25eb2a4d426b1b26ef38e33881641b4d1d0`, matching the digest GitHub publishes for the asset. Install locations:

- toolchain: `%USERPROFILE%\.codex\tools\libdragon-gcc-toolchain-20260915\n64inst` (this is `N64_INST`)
- libdragon source: `...\libdragon-trunk-e356bf3`

Everything runs from Git Bash and w64devkit 2.10.0 with no admin rights, Docker, WSL or MSYS2. libdragon's tools Makefile asks `pacman` for an MSYS2 date; the setup script passes `MSYS2_AGE=20260101`, which turns on libdragon's own `strndup` fallback. The libdragon build shows only upstream deprecation warnings. No code was vendored into `fpga/vendor/`.

## Mailbox use

The CPU makes only 32-bit PI accesses; libdragon's `io_write` waits for the PI to go idle before each one. The PI splits each 32-bit access into two 16-bit bus cycles, upper half first. Each frame the bootstrap therefore does the following:

1. Reads `{MAGIC,VERSION}` at `0x00`. If MAGIC is not `0x534E`, it stops there and never writes.
2. Reads `{STATUS,SEQ}` at `0x04` and reads back `{JOY1,JOY2}` and `{STICK,CONTROL}`.
3. Writes `{JOY1,JOY2}` to `0x10`, `{JOY1_STICK,CONTROL}` to `0x14`, then `0x0001_0000` to `0x18`. That last write is COMMIT at `0x18`; the RTL ignores the `0x1A` half, so SEQ goes up exactly once per frame.

After every boot the bootstrap writes `CONTROL = 0` before anything else, in line with the default-off rule. While the menu is on screen it sends a neutral pad. **Start** sets `run_request` and forwards both controllers. Holding **Z+L+R for 60 frames** returns to the menu while the cartridge keeps running. **Power down** clears `run_request`. Start is refused while STATUS shows a latched fault.

**STATUS layout is provisional.** The RTL passes `status_flags` through with no defined layout. `sn64_mailbox.h` proposes one, taken from the `sn64_power_sequencer` ports:

| Bit | Meaning |
|---|---|
| 0 | configured |
| 1 | host/FPGA rails ok |
| 2 | cart 5 V ok |
| 3 | interface rail ok |
| 4 | bus_permit |
| 5 | fault_latched |
| 6 | run_request seen |
| 7 | PAL |
| 11:8 | sequencer `state` |
| 15:12 | reserved |

The top level still has to wire it.

## Default mapping

The SNES image uses the shift order: bit 0 = B, then Y, Select, Start, Up, Down, Left, Right, A, X, L, R. **1 = pressed.** Bits 15:12 are 0.

| N64 | SNES | Basis |
|---|---|---|
| D-pad | D-pad | spec |
| Start | Start | spec |
| Z | Select | spec |
| A | B | proposed: primary thumb button to SNES primary (bottom) |
| B | Y | proposed: secondary thumb button to SNES left ("run") |
| C-Up / C-Right / C-Down / C-Left | X / A / B / Y | proposed: C diamond laid out like the SNES diamond |
| L / R | L / R | proposed |
| Analog stick beyond ±40 | D-pad | proposed; roughly half of a typical ±80 stick range |

Opposing directions (Up+Down, Left+Right) cancel, because a real SNES D-pad cannot produce them. The raw stick is still written to JOY1_STICK for the deferred virtual mouse.

## Verification

All results below were run on 2026-09-29 with the toolchain above.

- **Build.** `make` produces `build/n64-bootstrap/sn64_bootstrap.z64`, **114,688 bytes** (aPLib, `N64_ROM_ELFCOMPRESS=2`). The build uses libdragon's `-Werror` flags and gives no warnings. ELF: 115,256 text, 23,388 data, 3,036 bss. SHA-256 of this build: `a00cabcb80a30d368eae80f5d2dba546b70be8eaf612c56b8f91610f8923904b`. Reproducibility across machines has not been checked.
- **CIC-6102 boot check.** `make check` reports `IPL2 checksum (seed 0x3F) = 0xA536C0F1D859, CIC-6102 expects 0xA536C0F1D859` and `OK: ... is bootable with CIC-6102`. The port and libdragon's signing are independent sources, and they agree.
- **Word image.** `make words` reports `OK: 114688 bytes -> 57344 words in a 65536-word window (ROM_ADDR_BITS=16, minimum 16)`.
- **Mapping.** `make test`: `PASS: mapping table, 27 checks`.
- **Tools.** `PASS: ROM tools, 17 checks`. The checks are:
  - the built ROM passes;
  - a flipped bit at IPL3 `0x800`, a flipped bit at `0xFFC`, a `.v64` header and an all-zero IPL3 all fail;
  - the word image round-trips all 114,688 bytes, and word 0/1 = `0x8037 0x1240`;
  - the image is rejected for `ROM_ADDR_BITS` 12 and 15;
  - the CLIs return exit codes 0 and 1.
- **Negative runs.** Each of these must fail, and `make test-negative` passes only if all do (`NEGATIVE: all fault-injected runs failed as required`):
  - `-DSN64_FAULT_SWAP_AB` fails 3 of 27 checks;
  - `--inject-fault size-guard` fails 2 of 17 (`image rejected for ROM_ADDR_BITS=12: accepted`);
  - `--inject-fault checksum` fails 3 of 17 (a header-only checker lets corrupted IPL3 through).
- **Bug found in the test itself.** On an early rerun, a stale `words.mem` from the previous run made the check "converter writes nothing when it rejects" fail. The test now deletes the file first. Two back-to-back reruns then passed.
- **Co-simulation with the FPGA endpoint.** `run_rom_window_sim.ps1` (Verilator, `sn64_n64_endpoint` with `ROM_ADDR_BITS=16`) reports `PASS: bootstrap image (65536 words, last non-zero word 55547) loaded via rom_we, 76 words read back over PI, mailbox frame traffic (32-bit pairs, COMMIT once per frame, run/power-down) correct (68015 clocks)`. It reads back the header, both ends of IPL3, the start of the program and the last program word, then replays three bootstrap frames and checks JOY1/JOY2, the stick, run_request and SEQ = 1, 2, 3. With `+corrupt_load` it fails with `FAIL ROM word 32 (byte 0x40): read 3045 expected 3044`. The bench uses the endpoint's AD output enable, not bus values, for its ownership checks.

Limits:

- The CIC check covers only IPL3 (`0x40`–`0xFFF`), which is all the console checks for a libdragon ROM. Corrupting a byte after IPL3 is not detected; the test records this on purpose. Use the SHA-256 in the manifest for image integrity.
- The co-simulation replays the bootstrap's bus traffic by hand. It does not execute the MIPS code.
- No emulator run and no hardware run have been done. Controller behaviour, video output, frame pacing, and whether the IPL3 and the whole program boot on both consoles are all untested.

## Resource finding: the ROM window does not fit the current plan

| Compression | ROM size | ROM_ADDR_BITS needed | DP16KD |
|---|---|---|---|
| libdragon default LZ4 (level 1) | 147,456 bytes | 17 | 128 |
| aPLib or Shrinkler (levels 2 and 3; both measured) | 114,688 bytes | 16 | 64 (1K×16 each) |

The endpoint's current default of 12 bits (8 KiB, 4 DP16KD) holds only the header and IPL3. The ECP5-85F has 208 EBR, and the console plus bridge already uses 139. A 64-block ROM would leave about 5. This is arithmetic, not a synthesis run. Of the 114,688 bytes, 39,007 are uncompressed backtrace symbols (`.sym`), which libdragon's `n64.mk` always appends. The compressed ELF is 64,664 bytes.

Options, not yet decided:

1. Drop `.sym` with a custom `.z64` rule and trim libdragon modules.
2. Serve the window from the configuration SPI flash or a small PSRAM. The libdragon IPL3 reads the ROM only while booting, so latency matters much less than for a game.
3. Keep BRAM and accept the EBR cost.

2026-09-29: the menu shows the region and its source (main screen) and the ROM-header probe result (status screen) from REGION_INFO/REGION_SOURCE; the status-screen rows no longer overlap. Rebuilt: 114,688 bytes, SHA-256 `64d2b2a334117546a0610f3bdcafecb0809441a011f79f9d5dae5f49a72904b5`, CIC-6102 OK, co-simulation PASS.

## Still open

1. **Run it:** first in an emulator (ares, optional), then on an original N64 and on an M64 with the endpoint and CIC on real hardware. Measure boot time and PI timing.
2. **ROM storage decision** (above), and set `ROM_ADDR_BITS` in the top level to match. The endpoint default is still 12.
3. **STATUS wiring:** adopt or replace the provisional layout in the top level and record it in the endpoint note.
4. **Fault clear:** the power sequencer has a `fault_clear` input but no mailbox bit reaches it. A proposed `CONTROL` bit 1 (pulse) would need an RTL change, and then a menu item.
5. **Configurable mapping (SN64-06-03):** add runtime editing and persistence; there is no save storage yet. The table is data-driven, so the editor is UI work.
6. **Telemetry (SN64-08-13):** voltage/current/temperature registers do not exist in the mailbox yet.
7. **SNES serializer:** `joy1_buttons` to `JOY1_DI`/`JOY2_DI` is not in the RTL. It must follow the polarity above (1 = pressed in the image).
8. **Controller-2 menu input** and GameCube-style pads on the M64 are untested. libdragon reports them through the same `joypad` API.

## Console video path (2026-09-29): the game on the console's own screen

When a cartridge runs, the boot program no longer draws a status page: it switches the display to 256 × 240 (16-bit), sets PI domain-2 timing to LAT 0x40 / PWD 5 / PGS 7 / RLS 1 for the frame window at `0x0800_0000`, and every frame copies the SNES picture in four 56-line DMAs, each only after `FRAME_STATUS.lines_done` says those lines are finished (or the SNES has moved on to the next frame), so a line is never read while it is being written. The 224 lines sit centred in the 240-line screen; the borders are cleared once per buffer. Audio: `audio_init(32000, 4)`; each frame the new samples since the last read pointer are fetched from the ring at `0x0801_E000` (wrapping at 1024 pairs) into the N64's audio buffers, padded with silence if the ring is empty. The menu hotkey (Z+L+R for 1 s) switches back to the 320 × 240 menu. Rebuilt: 131,072 bytes, exactly the 128 KiB window at `ROM_ADDR_BITS = 16`; the board top now uses a 256 KiB flash window (`ROM_ADDR_BITS = 17`) for headroom. SHA-256 `92868c03f98ba7b5e5e8173d7d09b4a97128712b45c68f22e18346a7c100c36e`, CIC-6102 OK. **Not run on a console; the VI 256-wide framebuffer scaling and the PI domain-2 timing on real hardware are the first things to check on a prototype.**

## Cartridge check in the menu (2026-10-01)

For the owner's idea of catching a cartridge that is in back to front ([reversed-cartridge-detection.md](reversed-cartridge-detection.md)). The check itself is in the FPGA; the menu chooses its mode, shows its result, and says so on the screen.

- New items: "Check cartridge (no power)" asks for the check alone and shows the result; "Cartridge check:" steps through report only, enforce and off. The menu starts in **report only** (`SN64_CHECK_MODE_DEFAULT`) until the check's thresholds have been confirmed on real cartridges.
- The mode travels in `CONTROL` bits 5:4 with every frame's write. The result comes back in `CART_CHECK`, read with `FAULT` as the 32-bit pair at `0x08`.
- New alert screen. A latched fault or a finished check ends the request and shows the reason; the fault word is copied first, because dropping the request clears the latch. The reversed-cartridge text is "WHOA. WRONG WAY ROUND. / That cartridge is in backwards. / We don't do that around here. / Nothing was powered, so no harm done. Take it out, turn the label to the front, and try again." A rail that does not rise at all is reported as a short. In report-only mode a failed check followed by a power fault says that the check had warned.
- The game display is entered only once the sequencer reports RUNNING with the SNES clock on. Until then a text screen shows "Checking the cartridge..." or "Starting the cartridge...". Before this change a start that ended in a power fault left the program waiting in the frame copy for lines that never came.
- The decision which screen a result gives is in `src/sn64_cartcheck.c`, pure C. Host test `tests/test_cartcheck.c` (in `make test`): 74 checks, including that every screen line fits 38 columns. `make test-negative` builds it with a wrong short/backwards level and requires it to fail.

Rebuilt: 131,072 bytes (unchanged size), CIC-6102 check OK, word image fits `ROM_ADDR_BITS = 16`. Not run on a console or an emulator, like the rest of the menu.
