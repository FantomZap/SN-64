# ROM-header region probe

Snapshot 2026-09-29. Region fallback for cartridges that have no key CIC or whose key does not pass. **Simulated and synthesised only; nothing here has run on hardware.** It is not yet wired into `sn64_top.sv`: the integration edits are listed below and were checked on a scratch copy of the top level only (see "Integration trial").

| File | What it is |
|---|---|
| [fpga/rtl/sn64_header_probe.sv](../../fpga/rtl/sn64_header_probe.sv) | `sn64_header_probe` (clk_25 state machine) and `sn64_header_probe_mux` (socket owner mux) |
| [fpga/tests/tb_header_probe.sv](../../fpga/tests/tb_header_probe.sv) | Self-checking bench: cartridge models, strobe timing, safety monitors, fault injection |

## Plain-language summary

A real SNES starts at one speed for NTSC and a slightly different one for PAL. SN64 must choose before the SNES clock starts, and the clock never changes afterwards ([clock plan](clock-plan.md)). The cartridge's key chip usually says which region it is. When there is no key chip, SN64 now reads the cartridge's name tag (the ROM header) instead. ROM chips answer without a clock, so the FPGA can put an address on the socket, pull the "ROM select" and "read" lines low, and read the byte back. It reads the 32-byte header twice, and trusts it only if both reads match, the built-in checksum pair agrees, and the map-mode and country bytes are known values. If anything looks wrong, it falls back to NTSC. It never drives the data lines, never writes, never touches the reset line, and lets go of the socket the instant its permission is withdrawn.

## Where it sits

```text
          clk_25 domain                              clk_snes domain (stopped during the probe)
 seq_state, rails, !snes_clk_run ──► hdr_permit       sn64_console_with_bridge ──► br_* outputs
                                        │                                                │
                          sn64_header_probe ──► hdr_* ─────► sn64_header_probe_mux ◄─────┘
                                        │                           │  (bridge_permit selects the bridge)
                   header_valid/pal ───►│ region decision           ▼
                                                              socket pads / translator /OE, DIR
```

The mux owns the pads. The bridge drives them only while `bridge_permit` is high. The probe drives the address/strobe octets only while its own permit is high and the bridge is not permitted. Otherwise every translator is released. `/RESET` does not go through the mux; it stays with the power sequencer, which holds it low for the whole probe window.

## Header format (sources)

- fullsnes, "SNES Cartridge ROM Header", <https://problemkaputt.de/fullsnes.htm>, downloaded 2026-09-29, 1,524,441 bytes, SHA-256 `3853b65a7331bf12eea431ff494a2948a1c78ef22f7e819db4b139fd5a79f6c6`. The header is "mapped to 00FFxxh in SNES memory"; in ROM images it sits at 007Fxxh (LoROM), 00FFxxh (HiROM) or 40FFxxh (ExHiROM).
- SNESdev wiki, "ROM header", <https://snes.nesdev.org/wiki/ROM_header>, read 2026-09-29 (the raw page is behind a bot check, so no hash). It gives the same field offsets, the `001smmmm` map-mode layout, map modes 0/1/2/3/5/A and the ExHiROM location. Its region table lists names but no video standard for $0D-$10, so the NTSC/PAL column below is taken from fullsnes.

| Address | Field | Used for |
|---|---|---|
| `$FFD5` | Map mode: bits 7-6 = 0, bit 5 = 1, bit 4 = speed, bits 3-0 = map mode (0 LoROM, 1 HiROM, 2 S-DD1, 3 SA-1, 5 ExHiROM, A SPC7110) | Validity |
| `$FFD9` | Country code, which implies NTSC or PAL | Region |
| `$FFDC-$FFDD` | Checksum complement, little-endian, = checksum XOR `$FFFF` | Validity |
| `$FFDE-$FFDF` | Checksum | Validity |

ExHiROM: CPU bank `$00` upper half shows ROM `$40xxxx`, where the ExHiROM header lives, so reading `$00:FFC0` covers all three maps. The optional second read at `$40:FFC0` is therefore not implemented. Only two JP games use ExHiROM, and neither has a real cartridge in the test plan yet.

### Country code to region (fullsnes, "Country (also implies PAL/NTSC) (FFD9h)")

| Code | Country | Region used |
|---|---|---|
| `$00` | Japan / International | NTSC |
| `$01` | USA and Canada | NTSC |
| `$02` | Europe, Oceania, Asia | PAL |
| `$03` | Sweden/Scandinavia | PAL |
| `$04` | Finland | PAL |
| `$05` | Denmark | PAL |
| `$06` | France (SECAM, 50 Hz) | PAL |
| `$07` | Holland | PAL |
| `$08` | Spain | PAL |
| `$09` | Germany, Austria, Switzerland | PAL |
| `$0A` | Italy | PAL |
| `$0B` | China, Hong Kong | PAL |
| `$0C` | Indonesia | PAL |
| `$0D` | South Korea | NTSC |
| `$0E` | "Common (?)" | not trusted |
| `$0F` | Canada | NTSC |
| `$10` | Brazil (PAL-M, 60 Hz NTSC-like timing) | NTSC |
| `$11` | Australia | PAL |
| `$12-$14`, `$15+` | "Other variation (?)" / undefined | not trusted |

An untrusted code makes the header invalid, and the top falls back to NTSC.

## Validation

`header_valid` is 1 only if **all** hold:

1. **Stable bus**: the 32 bytes read the same on two full passes. This rejects a floating data bus (no cartridge, or a cartridge that is not answering).
2. **Checksum pair**: `complement XOR checksum == $FFFF`.
3. **Map mode**: bits 7-5 = `001`, and the mode is one of 0, 1, 2, 3, 5, A.
4. **Known country**: one of the codes in the table above that has a region.

`reject[3:0]` reports which checks failed, as `{unstable, checksum, map, country}`, and `header_country` and `header_map` report the raw bytes for telemetry. An abort (permit lost mid-probe) gives `done=1, aborted=1, header_valid=0`.

Known consequence: homebrew often carries `0000/0000` or `FFFF/0000` in the checksum fields (fullsnes). Such carts fail check 2 and run NTSC unless the menu forces PAL.

## Bus timing (clk_25, 40 ns per cycle, defaults)

| Step | Cycles | Time | Requirement |
|---|---|---|---|
| Translators enabled at idle levels before the first address | 4 | 160 ns | Translator enable time |
| Address valid before `/ROMSEL` falls | 2 | 80 ns | ≥ 50 ns setup |
| `/ROMSEL` low before `/RD` falls | 1 | 40 ns | `/RD` nested inside `/ROMSEL` |
| `/RD` low | 10 | 400 ns | ≥ 200 ns (slow mask ROM, fullsnes `FFD5h` bit 4: "Slow 200ns") plus translator delays |
| Data sampled (two-flop synchroniser, captured at the end of `/RD`) | | 320 ns after `/RD` fell, 440 ns after the address | Data stable long before sampling |
| `/RD` high before `/ROMSEL` rises | 1 | 40 ns | |
| Both strobes high, address held, before the next address | 3 | 120 ns | Full release; ROM output float time |

That is 17 cycles per byte and 64 reads (two passes), about 44 µs per cartridge power-up. With 64 reads the probe finishes long before the 300 ms region timeout.

## Safety rules and how they are enforced

| Rule | Mechanism | Checked by |
|---|---|---|
| D0-D7 never driven | The mux forces `data_dir = 0` (cartridge to FPGA) while the probe owns the pads; the probe's data enable is listen-only, from `/ROMSEL` fall to `/ROMSEL` rise | Bench monitor, every ns |
| Drive only with permission | Every enable and strobe is `permit AND register`, combinationally | "socket enabled without permit / with no owner" monitors |
| Release immediately when permit drops | Combinational gate; the state machine then aborts on the next clk_25 edge and never restarts in the same enable window | Permit dropped mid-`/RD` (not on a clock edge): released 1.0 ns later (monitor resolution), well inside the one-cycle (40 ns) limit |
| Never assert `/WR`, `/PWR` | The mux ties `/WR`, `/PWR`, `/PARD`, `/WRAMSEL` high, `PA=$FF`, and `REFRESH`, `PHI2`, `SYSTEM_CLK` low while the probe owns | Bench monitor |
| Never touch `/RESET` | No `/RESET` port. The top only permits the probe while the sequencer holds `/RESET` (`seq_reset_pull`) | Integration trial monitor (`tb_system` copy) |
| Bridge and probe never both own | The probe permit includes `!bus_permit` and `!snes_clk_run`; the mux gives the bridge priority | Bench mux check |
| Stale bridge data-octet state after the SNES clock stops | The mux passes bridge `data_oe_n`/`data_dir`/`ctl_oe_n` only while `bridge_permit` is high | Bench: stale `data_dir=1, data_oe_n=0` with the bridge not permitted is blocked |

**Finding (bridge, not changed here):** in [sn64_cart_bridge.sv](../../fpga/rtl/sn64_cart_bridge.sv), `data_oe_n` and `data_dir` come from `drive_q`/`listen_q`, which are cleared only on a `clk_snes` edge. `ctl_oe_n` is gated by permit combinationally, but the data octet is not. When the sequencer shuts down, `snes_clk_run` falls one clk_25 cycle after `bus_permit`, so the board clock gate may stop `clk_snes` before an edge clears a driving `drive_q`. That would leave D0-D7 driven toward a cartridge that is powering down. The mux gate above closes this at the top level. A direct fix in the bridge (`data_oe_n = !((drive_q || listen_q) && permit)`) is still recommended. Not reproduced in `tb_system`; this is a code-review finding.

## Region decision priority (in `sn64_top`)

**Forced mode > passing key CIC > valid ROM header > NTSC default.**

- Forced (menu NTSC/PAL): the probe is not enabled at all (`hdr_enable` requires auto mode). `sn64_clock_init` already gives the forced mode priority.
- Passing key: `cic_region_valid` decides at once, and the header result is ignored.
- Otherwise, the decision waits until the key has settled (failed, or the region timeout expired) **and** the probe is done (or the timeout expired). Then `det_pal = header_valid ? header_pal : 0`.
- `det_valid` is now asserted for the NTSC default too. Before this, an absent key left `sn64_clock_init` holding whatever region the previous cartridge had used, because it keeps `region_pal` when `detected_valid = 0`.

## Tests run (2026-09-29, this snapshot)

Commands, from the repo root, after the tool environment in `CLAUDE.local.md`:

```powershell
verilator_bin --binary --timing --build-jobs 4 -Wno-fatal --top-module tb_header_probe --Mdir C:/Users/RyanB/.claude/projects/SN64/build/hdrprobe-sim fpga/rtl/sn64_header_probe.sv fpga/tests/tb_header_probe.sv
build/hdrprobe-sim/Vtb_header_probe.exe
# fault builds (each must FAIL): add +define+SN64_FAULT_SKIP_CHECKSUM or +define+TB_SHORT_ACCESS
yosys -Q -T -p "plugin -i slang; read_slang --top sn64_header_probe fpga/rtl/sn64_header_probe.sv; scratchpad -set abc9.xaiger 1; synth_ecp5 -top sn64_header_probe -json build/hdrprobe-sn64_header_probe.json; stat; check -assert"
```

| Run | Result |
|---|---|
| Normal bench | **PASS**. Accepted LoROM US (valid, NTSC, `$01`), HiROM EU (valid, PAL, `$02`, with a LoROM-looking decoy at the wrong offset) and South Korea (`$0D`, NTSC). Rejected, with the expected `reject` bits: corrupted checksum pair (`0100`), unknown country `$0E` (`0001`), bad map mode (`0010`), absent cartridge pulled up (`0111`), pulled down (`0110`) and floating (unstable bit set). Also checked: 576 reads with minimum address→`/ROMSEL` 80 ns, `/RD` low 400 ns, `/ROMSEL` high gap 200 ns; no D-bus drive, no `/WR`/`/PWR`; permit drop released in 1.0 ns and gave an aborted, invalid result with no restart; permit without enable drives nothing; the result clears when enable drops; stale bridge state blocked; the bridge wins over the probe. |
| `+define+SN64_FAULT_SKIP_CHECKSUM` | **FAIL** as required: the corrupted checksum is accepted (`header_valid=1 expected 0`). Floating and absent buses are still rejected by the other checks. |
| `+define+TB_SHORT_ACCESS` (`/RD` 120 ns) | **FAIL** as required: every valid cartridge reads garbage bytes (the ROM model returns correct data only after 214 ns), and the timing check reports `/RD` low < 200 ns. |
| Yosys ECP5 synthesis | `sn64_header_probe`: 399 LUT4, 323 TRELLIS_FF (256 of them hold the header bytes), 61 PFUMX, 18 L6MUX21, 7 CCU2C. `sn64_header_probe_mux`: 45 LUT4. `check -assert`: 0 problems. |

The cartridge models are behavioural: a mask ROM with one lumped 214 ns access delay (200 ns plus two 7 ns translator hops, an assumption, not a measured value), ideal translators, and no analog levels. The absent-cartridge "floating" model is random data, not a physical model of the SN74LVC4245A with an open A side.

## Integration trial

The integration edits were applied to scratch copies of `sn64_top.sv` (as of 2026-09-29 18:08, which already includes the HDMI output) and `tb_system.sv`, not to the repo files. They were built with the full `evaluate.py` system source list plus `fpga/rtl/sn64_header_probe.sv` (build dir `build/hdrprobe-integ-system`; the diffs are in `build/hdrprobe-integ-system-patches/`). The `tb_system` copy adds: probe ownership accepted by the "no socket drive without permission" invariant; a new invariant that while the probe owns the socket there is no `/WR`/`/PWR`, no D-bus drive, no running SNES clock and `/RESET` is held; an optional EU header at `$00:FFC0` (`+pal_header`); and a check that the region at clock start matches the header (PAL) or the NTSC default.

| `tb_system` run | Result |
|---|---|
| Default cartridge (no header at `$00:FFC0`, the bus reads `$00`) | **PASS**, STATUS `0x545F` (same as the baseline). Probe `done=1 valid=0 reject=0110`, so the NTSC default was used. |
| `+pal_header` (EU `$02`, valid checksum pair) | **PASS**, STATUS `0x54DF` (PAL bit set). Probe `done=1 valid=1 pal=1 country=02`. The SNES program ran and the region did not change while the clock ran. |

This trial does not replace running `evaluate.py --mode sim` after the real merge.

## Limits and open items

1. **Hardware**: nothing measured. Check real mask-ROM, MAD-1 decoder and translator timing, and the floating-bus behaviour with no cartridge, on the prototype.
2. **Cartridges that do not answer in reset or without a clock**: the probe runs with `/RESET` held and no SYSTEM_CLK. Coprocessor boards whose ROM is reached through the coprocessor (for example SA-1), and flashcarts that are still booting (FXPAK Pro / Super EverDrive load their FPGA from SD), may return garbage or their menu header. Validation fails closed (NTSC), or reports the flashcart menu's own region, as the clock plan already expects. A late retry (re-probe shortly before the region timeout) is not implemented.
3. **Telemetry**: STATUS is full (16 bits). `hdr_valid`, `hdr_country`, `hdr_reject` and `hdr_aborted` need a new mailbox word before the menu can show why a region was chosen.
4. **`tb_system`** must accept probe ownership in its "socket enabled without permission" invariant (edit listed in the integration notes).
5. **Constraints**: the mux mixes clk_25-domain and clk_snes-domain signals onto the same pads. They are never active together, so the cross-domain paths into the mux are false paths for timing. `SYSTEM_CLK` gains one LUT level through the mux (review with the board wrapper's clock-output choice).
6. **Glitches on `cart_5v_ok`/`iface_rail_ok`** drop the probe permit combinationally, which aborts the probe (invalid, so NTSC). The sequencer faults on a real rail loss in IFACE anyway.
7. The 256-flop header store could shrink to the six used bytes plus a signature for the stability check if LUT/FF budget becomes tight.

## Reuse

No existing hardware header reader was found to reuse. The pinned SNESTang and SNES_MiSTer sources receive ROM images from a loader. SNES_MiSTer (`SNES.sv` at `c61bfd4`, "ROM DETECT") takes `rom_region` from a word the HPS loader sends and applies `PAL <= (!status[15:14]) ? rom_region : status[15]`, meaning the menu's Auto/NTSC/PAL setting with the ROM's region in Auto. SN64 follows the same precedence. The pinned sd2snes files are only its CIC and PCB. The probe logic is original SN64 code (GPL-3.0-or-later), written from the published header format above.
