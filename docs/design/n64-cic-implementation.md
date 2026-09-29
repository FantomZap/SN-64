# N64 CIC lockout: implementation and evidence

Implemented 2026-09-29. This is the lockout-chip emulation that lets an original N64 (and an M64 behaving as an N64) accept SN64 as a genuine cartridge. It reuses SummerCart64's implementation unmodified: a SERV RISC-V soft core running the UltraCIC_C firmware, both open source and proven on real consoles in SummerCart64. **It has not run on hardware from SN64.** See the [endpoint notes](n64-endpoint-implementation.md) for the surrounding host interface.

## Plain-language summary

Every N64 cartridge has a small security chip (the CIC). At power-on the console's own security chip talks to it over two wires; if the answers are wrong the console stays in reset and never boots. SN64 answers with a tiny software CPU inside the FPGA running a public re-implementation of the cartridge chip, exactly as SummerCart64 does. It presents itself as the standard NTSC cartridge chip (CIC-6102), or PAL (7101) when configured.

## Files

| File | Role |
|---|---|
| [fpga/vendor/summercart64/fw/rtl/serv/](../../fpga/vendor/summercart64/provenance.json) | SERV RISC-V core, ISC license (Olof Kindgren), unmodified |
| `fpga/vendor/summercart64/fw/rtl/n64/n64_cic.sv` | SummerCart64 CIC module (SERV + 512-word RAM + timer + DQ open-drain driver), unmodified |
| `fpga/vendor/summercart64/sw/cic/` | UltraCIC_C-derived firmware (MIT, Jan Goldacker / Mateusz Faderewski), linker script, startup and converter, unmodified |
| [fpga/tools/build_cic.py](../../fpga/tools/build_cic.py) | Builds the firmware with xPack `riscv-none-elf-gcc`, writes `build/cic/cic.mem` and a generated `n64_cic.sv` whose `$readmemh` path is repository-relative |
| [fpga/rtl/sn64_n64_endpoint.sv](../../fpga/rtl/sn64_n64_endpoint.sv) | Instantiates the CIC with cartridge type, region input, seed `0x3F` and checksum `0xA536C0F1D859` |
| [fpga/tests/tb_n64_cic.sv](../../fpga/tests/tb_n64_cic.sv) | Console-side model of the handshake with reference seed/checksum streams |

The generated RTL copy exists only because upstream's `$readmemh` path points into its own tree; no vendored line is edited.

## Protocol as implemented by the firmware

From `cic.c` (public algorithm): after console reset release the cartridge sends a 4-bit ID (`0 region 0 1`), then the 6-nibble encoded seed, waits one console bit, sends the 16-nibble encoded checksum, receives two nibbles for its RAM, then loops on 2-bit commands: compare (00), X105 challenge (10) and soft reset (11). Bits are exchanged on the console's CIC clock: the cartridge changes DQ after the clock falls and the console samples before it rises. The 500 ms timeout timer counts the PIF/SI clock, so it is independent of the FPGA clock.

The seed and checksum constants are the standard CIC-6102 values SummerCart64 uses by default; the bootstrap ROM image's checksum must match them (the N64 IPL verifies the ROM against the CIC checksum), which is a bootstrap-build task.

## Verification

`tb_n64_cic.sv` models the console: it clocks the CIC at 250 kHz, reads the ID nibble and compares it with `0001`, reads the 24-bit seed stream and the 64-bit checksum stream and compares them nibble by nibble with references computed independently in Python from the same public algorithm (`BD393D` and `04E2FAC5210FCE2F`), supplies the two RAM nibbles, issues the compare command and checks that the firmware reaches its compare step and keeps answering bits without locking the line. The test is part of `evaluate.py --mode sim` whenever `build/cic/cic-build.json` exists; otherwise it is reported as skipped rather than silently passing.

Result: **PASS** (ID, full seed and 64-bit checksum streams match; compare mode entered). A second run with `+corrupt_expect` alters one expected checksum nibble and must fail; it does.

### Findings from bring-up in simulation

- **The CIC soft CPU needs its own fast clock.** SERV is bit-serial; at the 21.477 MHz master clock the firmware could not answer bits in time. SummerCart64 runs it at 62.5 MHz, so the endpoint now takes a separate `cic_cpu_clk` (from the ECP5 PLL) with a synchronised reset; the CIC's inputs are already synchronised inside the vendored module.
- **Firmware speed at 62.5 MHz:** about 48 ms from reset release to the ID step, roughly 10-16 µs per bit, and long pauses while it computes the seed (2 encode rounds) and checksum (4 rounds). The real console (PIF) paces the exchange in software; the [n64brew CIC page](https://n64brew.dev/wiki/CIC-NUS) notes the CIC waits for each clock edge and that the minimum usable rate is not documented. The bench therefore clocks at 10 kHz and waits for the firmware to reach each phase, which is consistent with SummerCart64 working on real consoles but is **not** a measured PIF timing. Measuring the real PIF's bit period and inter-phase gaps on both N64 and M64 is a hardware check item.
- Three bench errors were found and fixed along the way (console model clocking before the firmware booted, sampling too early in the bit, and a 64-bit checksum read into a 32-bit variable). None was in the vendored design.

Limits: representative clock rate and timing, not a captured PIF trace; the X105 challenge and soft-reset paths are exercised only by the firmware's own logic, not by the bench; PAL region is configured but not separately tested.

## Still open

1. Build and verify the bootstrap ROM with a matching CIC checksum (libdragon handles this for 6102).
2. Confirm on an original N64 and an M64 that the console boots; the M64's handling of CIC is its own firmware's business and must be tested, not assumed.
3. Add the X105 and soft-reset console-side sequences to the bench.
