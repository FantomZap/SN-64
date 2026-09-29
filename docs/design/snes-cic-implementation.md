# SNES CIC lock: implementation and evidence

Implemented 2026-09-29. This is the console-side lockout chip (the F411/F413 "lock") that talks to the key CIC inside a real SNES cartridge. Carts with SA-1 or S-DD1 chips check that a lock is talking to them, and the key's type tells SN64 whether the cartridge is NTSC (60 Hz) or PAL (50 Hz). The design passes a self-checking simulation against a behavioural key model and against reference streams from a published program. **It has not run on hardware, and its timing has not been compared with a real key CIC.**

## Plain-language summary

Every SNES cartridge contains a small security chip (the key), and every console contains a matching chip (the lock). After power-on the lock resets the key, sends it a 4-bit starting value, and then both chips swap one bit at a time, forever. Each chip computes locally what the other one should send; a wrong bit means a fake or missing cartridge. Both chips count the same clock, so each bit must arrive at a precise moment.

SN64 now has this lock inside the FPGA. It generates the lock's clock, resets the key, runs the exchange, and reports three things: whether the key answered correctly, whether the key is the NTSC or PAL type, and whether the console may leave reset.

By default SN64 behaves like SuperCIC, a well-known open replacement lock. The console runs even when the key does not answer, so homebrew and carts without a key still work, and the failure is only reported. A single input switches to the original strict behaviour, where the console runs only while the key keeps answering correctly.

## Files

| File | Role |
|---|---|
| [fpga/rtl/sn64_snes_cic_lock.sv](../../fpga/rtl/sn64_snes_cic_lock.sv) | The lock: CIC_CLK divider, key reset, seed transmission, bit exchange, table update, region detection, status and console-run output |
| [fpga/tests/tb_snes_cic_lock.sv](../../fpga/tests/tb_snes_cic_lock.sv) | Self-checking bench with a behavioural D411/D413 key model, reference-stream comparison, contention monitor and 11 scenarios |

No shared file was changed. Hooking the bench into `evaluate.py`, the README files and the work log is listed under "Still open".

## What is reused, and what is not

The user wants existing open work reused first. The candidates were checked on 2026-09-29.

| Candidate | Licence | Decision |
|---|---|---|
| sd2snes SuperCIC lock/key (`references/downloads/fpga/sd2snes-cf7e21d7…/cic/supercic/`) | GPL-2.0-only | **Read, not copied.** GPL-2.0-only code cannot enter GPL-3.0-or-later SN64 HDL. It was used to understand behaviour: the pin direction per round, region detection from key nibble 2, and the pass-through policy. The instruction-cycle timing was also derived from it, because it is a proven drop-in lock. |
| [rgalland/snes_cic_fpga](https://github.com/rgalland/snes_cic_fpga) (commit `eeaab3b3`) | GPL-3.0 | **Not reused.** It is VHDL, and it re-implements the 4-bit CIC CPU running a 512-byte program image (`cic_rom.vhd`) whose provenance is not documented. That image is most likely a dump of the original chip's program, which the repository's GPL notice cannot license. |
| [raphnet/snes_cic](https://github.com/raphnet/snes_cic) | none stated | Not reused (no licence; it is a PIC key, not a lock). |
| [SHIMA-R7/sfc-cic-notes](https://github.com/SHIMA-R7/sfc-cic-notes) | GPL-2.0 | Not read or copied. |

The implementation is therefore original SN64 HDL, written from published algorithm descriptions:

- **Super Famicom Development Wiki, [CIC page](https://wiki.superfamicom.org/cic)**, fetched 2026-09-29. It gives:
  - the D411/D413 seed tables: key `b14f4b57fd61e98`; lock `_9a185f11e10dec` (D411) or `_6a185f11e10dec` (D413), where `_` is the stream-select nibble sent in bit order 3-0-1-2;
  - a C program for the table update ("mangle"), with the rule for where the next round starts and which way the lines point.
- **segher, ["The weird and wonderful CIC"](https://hackmii.com/2010/01/the-weird-and-wonderful-cic/)**, hackmii.com, January 2010. It gives the principle that each chip sends a bit and checks the other's bit against its own copy of the other stream, plus the CPU background.

The wiki's C program was compiled with w64devkit gcc, with its endless loop bounded and seed/region taken from the command line. That build lives in the session scratchpad and is not part of SN64. Its printed streams for seed 0/D411 and seed F/D413 are embedded as reference data in the bench. The RTL table update and the bench's key model were written separately: one as a synthesizable function, the other as a C-style task.

## Protocol as implemented

Pins are socket contacts from the [pin map](../../hardware/sn64/interfaces/snes-pin-map.csv). Times are **instruction cycles** of 4 CIC clocks, counted from the falling edge of CIC_SLAVE_RESET, as in the SuperCIC lock program.

| Step | Time (instructions) | Lines |
|---|---|---|
| Power-up wait with the key clocked, reset low | 49,605 (`T_PWRUP`) | — |
| Key reset pulse | 3 high, then low (starts the key) | CIC_SLAVE_RESET (25) |
| Seed: 4 bits, order 3-0-1-2, 15 cycles apart, 3 cycles high (widened, see below) | first at 630 | lock drives CIC_DATA0 (55); key drives CIC_DATA1 (24) low |
| Lock releases CIC_DATA0 | 686 | both released until round 1 |
| Round 1, slot 1 starts | 806 | dir=0: lock drives CIC_DATA1 (24), key drives CIC_DATA0 (55) |
| Each slot (elements `start`..15) | 93 per slot; own bit high from +10 to +16; key sampled at +12.5 | lock's pin by `dir` |
| After the last slot: 3 table updates of each stream | 145 + Σ(78 or 84 per update iteration) + 5 (7 if the restart element is 0) from the last slot's start | both data pins released |
| Next round | `start` = key-stream element 7 (1 if zero); `dir` = its bit 0 | dir=1: lock drives CIC_DATA0 (55) |

Other details:

- **Tables.** The lock sends `b14f4b57fd61e98`. It expects `<seed> <9|6> a185f11e10dec`.
- **Region detection** is SuperCIC's method. In round 1 the key's bit at element 2 is bit 0 of 9 (D/F411) or 6 (D/F413). The lock stores the matching nibble and reports PAL when the bit is 0. The region counts as valid only once the whole first round has matched.
- **Update timing is data-dependent.** One iteration of the table update takes 84 cycles when step 3 carries (its store is skipped) and 78 when it does not; these are SuperCIC's cycle counts for the original chip. The RTL computes both streams' updates in at most 96 master clocks and sets the length of the round's last slot from the accumulated cycle count.
- **SN64 additions**, which are not in the original lock and are all documented in the RTL:
  1. **Wider pulses.** The lock's own seed and round pulses are widened by 4 instruction cycles on each side (`T_WIDEN`). This gives a key that samples up to ±5 cycles early or late the right level. The original windows lie inside the widened ones.
  2. **Released pins.** The lock drives a data pin only while it needs to, and releases both pins across every direction change. The board therefore needs pull-downs on CIC_DATA0/1.
  3. **Release after failure.** After a mismatch the lock stops driving the data pins, so it cannot fight a key that is out of step. It keeps sequencing and reporting.

## CIC_CLK

- **Generated clock.** CIC_CLK is `clk / CLK_DIV`, registered, with a full-length first cycle.
  - The default `CLK_DIV = 6` on the 21.4772727 MHz NTSC master gives **3.579545 MHz** at exactly 50 % duty. Measured in simulation: 279.36 ns period, 139.68 ns high.
  - With `CLK_DIV = 7` it would be 3.068182 MHz at 4:3 duty.
- **The "3.072 MHz" figure is not confirmed.** The OpenSFC SHVC-CPU-01 Rev A netlist (commit `6574450b`) shows the console CIC clock coming from its own oscillator: X2 (value "4mhz"), a 74HCU04 (U9) with a 1 MΩ feedback resistor (R72), net `C.CLK` from U9 pin 2 to slot pin 56, and U9 pin 6 to the lock F411 (U8) pin 7. So at least that board revision runs its CIC at about 4 MHz. The frequency on later revisions (1CHIP) was not checked.
- **Why 3.58 MHz is acceptable.** Lock and key count the same clock, so the protocol does not depend on the absolute frequency. It only has to be within the key's working range. 3.58 MHz lies between the two figures and keeps an exact 50 % duty.
- **Conflict with the clock plan.** The [clock plan](clock-plan.md) wants region detection to finish **before** the SNES master clock starts, with the lock on "its own CIC clock". The module is clock-agnostic, and the integration should follow the plan:
  - clock the lock from the 25 MHz housekeeping reference with `CLK_DIV = 8`, giving **3.125 MHz** at 50 % duty;
  - it then runs before, and independently of, the Si5351 SNES clock, and keeps running for SA-1/S-DD1 carts.
  - Timing closure is not a concern: the module routes at 95 MHz (below).

## Status outputs and policy

| Output | Meaning |
|---|---|
| `key_ok` | Round 1 fully matched and no mismatch since |
| `key_fail` | Sticky: some received bit did not match, which includes no key at all |
| `region_valid`, `region_pal` | Region from the key when `key_ok`; otherwise `default_pal` (menu setting) with `region_valid=0` |
| `console_run` | `enforce=0` (default, SuperCIC-style): 1 after round 1, pass or fail. `enforce=1` (original behaviour): 1 only while `key_ok`, and drops at the first mismatch. |
| `rounds_done`, `phase` | Diagnostics |

The lock never stops while `enable` is high, because SA-1/S-DD1 keys expect the exchange to continue. When the key does not answer, the lock does not wait for it: every step is timed by the lock's own clock, so a missing key cannot hang it.

The original lock resets the console at about 1 Hz on failure. SN64 instead holds `console_run` low under `enforce=1`. The N64 menu should expose the policy and the default region as settings.

Integration notes:
- Gate the console core's reset with `console_run`.
- Gate `enable` with cartridge power-good and the bridge's `bus_permit`.
- Drive `seed` from a free-running counter (the real lock seeds from a timer; SuperCIC uses a constant F).
- Restart the handshake after a console reset by dropping `enable`.

## Verification

Commands (repository root, tool environment as in `CLAUDE.local.md`):

```powershell
verilator_bin --binary --timing --build-jobs 4 -Wno-fatal --top-module tb_snes_cic_lock --Mdir C:/Users/RyanB/.claude/projects/SN64/build/verilator-snes-cic fpga/rtl/sn64_snes_cic_lock.sv fpga/tests/tb_snes_cic_lock.sv
build/verilator-snes-cic/Vtb_snes_cic_lock.exe
# fault injection: same with +define+SN64_FAULT_CIC_NO_COMPARE (Mdir build/verilator-snes-cic-fault)
#                  and +define+SN64_FAULT_CIC_MANGLE (Mdir build/verilator-snes-cic-mangle)
```

**The key model.**
- It is clocked by the DUT's CIC_CLK and resets on the CIC_SLAVE_RESET pulse.
- It reads the seed on CIC_DATA0 and drives CIC_DATA1 low during the seed.
- It then drives its own stream on the pin the protocol assigns to the key. Its bit is high only for the original 6-cycle window.
- It samples the lock's bit and counts mismatches.
- It updates both streams with its own C-style implementation, computes the same inter-round delay, and records both physical lines at every sample point.

A pull-down resolves released lines. A monitor counts every master clock where lock and key drive the same pin.

**Result (2026-09-29): `PASS`**, 259 ms simulated, about 2 s wall time:

| # | Scenario | Result |
|---|---|---|
| 0 | CIC_CLK from `CLK_DIV=6` | 279.36 ns (3.5796 MHz), 139.68 ns high |
| 1 | D411 key, seed 0, `enforce=1`, 5 rounds | pass. `key_ok=1`, NTSC, console runs, 0 key-side mismatches, 0 contention clocks. DATA1/DATA0 streams and start elements of rounds 0–3 equal the wiki program's output (`110101111101010`/`010101111010100`, then start 6, 8, 1). |
| 2 | D413 key, seed F, 5 rounds | pass, PAL. Reference streams for rounds 0–3 match (starts 1, 11, 12, 15). |
| 3–4 | D413 seed 5; D411 seed A | pass, correct region |
| 5–6 | Key running 8 CIC clocks (2 instructions) late / early | pass |
| 7 | No key, pass-through | `key_fail=1`, `key_ok=0`, region not valid (default reported), console runs, rounds continue (3 completed) |
| 8 | No key, `enforce=1` | `key_fail=1`, console held in reset, rounds continue |
| 9 | One corrupted key bit (round 2, element 15), `enforce=1` | rounds 0–1 pass with console running; the bit is detected, `key_ok` drops and the console stops |
| 10 | Same corruption, pass-through | detected, console keeps running |
| 11 | Key 20 CIC clocks (5 instructions) late | detected as failure (outside the sample window) |

Negative controls (the bench must be able to fail). On failure the bench prints `FAIL:` and exits with code 1 through `$fatal`. On success it prints `PASS:` and exits with 0.
- **`SN64_FAULT_CIC_NO_COMPARE`** (the lock never flags a mismatch): **`FAIL: SNES CIC lock: 11 error(s)`**. Scenarios 7–11 fail ("failure not flagged", "corrupted key bit not detected", "desynchronised key not detected").
- **`SN64_FAULT_CIC_MANGLE`** (one constant in the RTL table update changed from 8 to 7): **`FAIL: SNES CIC lock: 43 error(s)`**. Every good-key scenario fails. The key model sees the lock's wrong bits, and the reference comparison reports, for example, `round 1 DATA1: 0000000000, reference 1010000100`.

**Limits.**
- **Timing is the main one.** The instruction-cycle timing (power-up, seed placement, 93-cycle slot, 145-cycle update overhead, 78/84 per iteration) comes from reading the SuperCIC lock program, which was itself tuned against real keys. The bench's key model uses the same numbers, so it proves internal consistency and tolerance to ±2 instructions, not agreement with a real D411/D413/F411 or an SA-1 key.
- There are no analog levels, 5 V translators, pull-ups/pull-downs, clock jitter or real key start-up behaviour.
- Pin direction per round and the seed/round line assignment follow SuperCIC's source. They were not cross-checked against a logic-analyser capture.
- The SuperCIC pair mode and the D4/$213F region override are not implemented.

## Synthesis

- **Yosys** (`read_slang`, `synth_ecp5`, abc9), module alone: **1,038 LUT4, 238 TRELLIS_FF, 144 CCU2C, 301 PFUMX, 163 L6MUX21**, 0 EBR. Log: `build/snes-cic-synth.log` (not tracked).
- **nextpnr-ecp5**, out of context (`--85k --package CABGA381 --speed 8 --freq 21.477`): **1,400 TRELLIS_COMB, 238 FF, 95.21 MHz Fmax** (PASS at 21.48 MHz). Log: `build/snes-cic-pnr.log`.
- About half the logic is the single-cycle table-update function with its variable start element. A multi-cycle version would be smaller if space gets tight.
- Not yet in the full-system build.

## Still open

1. **Calibrate the timing on hardware.** Capture an original F411 lock with a D411 key (and an SA-1 cart) on a logic analyser. Compare seed placement, slot period, sample point and the inter-round delay with the parameters here, and adjust them. This is the precondition for claiming any real-cart result.
2. **Pick the lock clock per the [clock plan](clock-plan.md)** (25 MHz reference, `CLK_DIV=8`, 3.125 MHz), and confirm the key and SA-1/S-DD1 run at that frequency.
3. **Board:**
   - pull-downs on CIC_DATA0/1;
   - series resistors on both data lines, against a fight with an out-of-step key;
   - 5 V level translation with per-pin direction control for pins 24, 25, 55, 56.
4. Wire the lock into the top level (`console_run` → core reset, `enable` from power-good/`bus_permit`, `seed` from a counter, policy and default region from the N64 menu registers), and expose status in the mailbox.
5. Add the bench to `fpga/tools/evaluate.py --mode sim`, with both fault builds as expected-fail runs.
6. Optional: SuperCIC-compatible pair mode and a D4 ($213F bit 4) override, if a use appears.
