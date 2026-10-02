# Physical cartridge bridge: implementation and evidence

Implemented 2026-09-29. This is the first working version of the logic that connects the SNES console core to the real 62-contact cartridge socket. It passes a contention-checking bus simulation. **It has not run on hardware.** The [bridge contract](physical-cartridge-bridge.md) remains the specification; this note records what is implemented against it and what is still open.

## Plain-language summary

A SNES cartridge and the console share one set of eight data wires. Only one side may drive them at a time; if both do, chips can be damaged. The bridge is the referee. Every 46.56 ns (one master clock) it decides whether the FPGA drives the data wires (console write, or WRAM answering a read), listens to them (cartridge answering a read), or lets go. Whenever ownership changes it lets go for one full clock first, which is longer than the level translator needs to switch off. All other console outputs (address, strobes, clocks) are driven only while a hardware permission signal is high; otherwise every socket driver is off and the cartridge is held in reset.

## Files

| File | Role |
|---|---|
| [fpga/rtl/sn64_cart_bridge.sv](../../fpga/rtl/sn64_cart_bridge.sv) | The bridge: ownership state machine, registered socket outputs, translator controls |
| [fpga/rtl/sn64_console_with_bridge.sv](../../fpga/rtl/sn64_console_with_bridge.sv) | Console candidate plus bridge; the socket-facing top level |
| [fpga/tests/tb_cart_bridge.sv](../../fpga/tests/tb_cart_bridge.sv) | Physical-bus testbench with a cartridge model that drives only when selected, and a contention monitor |
| [fpga/tools/evaluate.py](../../fpga/tools/evaluate.py) | Runs the bridge test and a fault-injected build in `--mode sim` |

## How the core's bus maps to the socket

Cross-reference of the pinned SNESTang core against SNES hardware behaviour. Core references are to the vendored files; hardware behaviour follows the console-side wiring in the [interface notes](snes-interface-notes.md) and the [bus evidence audit](bus-electrical-evidence.md).

| Socket signal group | Real console behaviour | Core source | Bridge treatment |
|---|---|---|---|
| A0–A23 | Driven continuously by the 5A22; changes at cycle start | `RAW_CA` (CPU/DMA/HDMA-selected address before WRAM mirror rewrite; `cpu.v` `INT_A`) | Registered, driven while permitted |
| PA0–PA7, /PRD, /PWR | Driven continuously; strobes low during the B-bus access | `PA`, `PARD_N`, `PAWR_N` (`cpu.v` lines 405–420) | Registered, driven while permitted |
| /RD, /WR | Low during the access half of the CPU cycle; DMA has its own strobes | `CPURD_N`, `CPUWR_N` (`cpu.v` lines 423–434; `CPU_RD/CPU_WR` set on `INT_CLKR_CE`, cleared on `INT_CLKF_CE`) | Registered, driven while permitted |
| /ROMSEL, /WRAMSEL, REFRESH | Decode and refresh outputs | `ROMSEL_N`, `RAMSEL_N`, `SNES_REFRESH` | Registered, driven while permitted |
| PHI2 | CPU clock, 6/8/12 master clocks per cycle | `INT_CLK` via generated `SYSCLK` export | Registered, driven while permitted |
| SYSTEM_CLK | 21.477 MHz master clock | `clk` | `clk & permit` (placeholder; final output uses a clock buffer, not logic) |
| D0–D7 | Shared; console drives during writes and when internal RAM answers; cartridge drives during external reads; otherwise open | `DO` (write byte / MDR) and the wrapper's WRAM source-valid | Ownership state machine below |
| /IRQ | Cartridge pulls low; console senses | `IRQ_N` | Sensed; passed to core only while permitted |
| /RESET | Open-drain, either side may pull low | not in core | `cart_reset_pull_n` low whenever not permitted or core in reset |
| CIC, EXPAND, audio | Separate designs | none | **Not implemented** in this bridge |

The core latches read data on its falling-edge enable at the end of the cycle (`P65C816.v`, `CE` = `INT_CLKF_CE`), as the real 65C816 does. The CPU strobe therefore spans from the second master clock of the cycle to its end, and cartridge data must be valid by the final clock. The bridge's one-clock turnaround at the strobe's leading edge leaves the remaining 4–10 clocks (186–465 ns) for the cartridge to respond, which covers 120 ns FastROM and 200 ns SlowROM parts with margin, before translator and PCB delays are included.

## Data-bus ownership rules

Implemented in `sn64_cart_bridge.sv`. `permit` = `bus_permit && reset_n`, where `bus_permit` is intended to be the hardware veto AND run request from the [power architecture](power-architecture.md).

| Condition (core signals) | Owner | Translator |
|---|---|---|
| `!permit` | none | `/OE` high (released), cartridge in reset |
| Console write: `!CPUWR_N` or `!PAWR_N` | FPGA drives | `/OE` low, DIR = FPGA→cartridge |
| WRAM answering a read: `cart_wram_read_valid && (!CPURD_N or !PARD_N)` | FPGA drives the RAM byte | `/OE` low, DIR = FPGA→cartridge |
| External read or idle | cartridge may drive; FPGA listens | `/OE` low, DIR = cartridge→FPGA |
| Any change of owner | none for one clock | `/OE` high for one master clock |

Two timing details make this match a real 5A22 at the pins:

1. **Look-ahead.** Ownership is decided from the core's strobes, which are one clock ahead of the registered socket strobes. The turnaround therefore completes before the strobe edge reaches the cartridge: write data is stable when /WR falls, and the octet is already listening when /RD falls.
2. **Data hold.** The FPGA keeps driving for one clock after the socket-side write strobe rises, so a cartridge that latches on the rising edge sees stable data.

3. **DMA and HDMA (2026-10-01).** During a copy a read strobe on one side and a write strobe on the other are low together, and whoever answers the read owns D0-7. A copy from the cartridge to the picture chip (`/RD` and `/PAWR` low) is the cartridge's byte, so the octet listens. A copy from a console device to the cartridge (`/PARD` and `/WR` low) is the console's byte, so the octet drives. `/RD` names the cartridge as the source unless WRAM answers; `/PARD` names a console device at `$2100`-`$2183`, or something on the cartridge side above that. Until this day every write strobe made the octet drive: a copy out of the cartridge ROM had two drivers and the picture chip got the console's own stale byte. Found by the first run of a real program ([game-simulation.md](game-simulation.md)); the fault build `SN64_FAULT_DMA_DRIVE` puts the old behaviour back.

Internal CPU-register reads are **not** driven onto the socket, as the [evidence audit](bus-electrical-evidence.md) requires. While the octet is released the core sees `$FF`; this only happens during the turnaround clock, never as a substitute for a cartridge response inside a read window.

## Verification

`fpga/tools/evaluate.py --mode sim` now runs, in addition to the earlier diagnostics:

- **`cart-bridge`**: an original diagnostic program executes from a modelled cartridge (ROM at `$00:8000`, SRAM at `$70:0000`) that drives D0–D7 only while `/RD` is low and its address is selected. The program writes the cartridge SRAM, reads it back, writes and reads WRAM, reads a ROM byte, and performs a two-byte B→A DMA from WRAM to the cartridge. The bench checks every readback value in the cartridge's SRAM, and fails on: any clock where both the cartridge and the FPGA drive data; any console output while not permitted; any write strobe that ends without the FPGA driving valid data; any owner change without a released clock. Result: **PASS, 56 ownership changes, 1,411 master clocks, zero contention.**
- **`cart-bridge-no-guard`**: the same bench with `SN64_FAULT_NO_GUARD` defined, which removes the turnaround clock. It must fail. Result: rejected with `Listen->drive without release clock`.

Limits: this is a behavioural model. It has no analog levels, translator propagation delay, PCB loading or real cartridge timing variation, and it does not exercise HDMA, PPU/APU responders, CIC, /IRQ assertion or open-bus decay. Passing it does not establish cartridge compatibility; it establishes that the ownership logic is contention-free and cycle-aligned with the core.

## Synthesis

`sn64_console_with_bridge` synthesizes for ECP5 with the pinned OSS CAD Suite: **25,618 LUT4, 10,827 FF, 139 DP16KD, 19 MULT18X18D** (log: `build/bridge-synth.log`, not tracked). Compared with the console-only candidate (26,669 LUT4, 10,775 FF) the bridge adds 52 registers; the LUT count moved with ABC's mapping, not a design change. No place-and-route was rerun for this checkpoint.

## Still open (from the bridge contract)

1. CIC lock (SuperCIC-derived), EXPAND bias, cartridge reset sensing into the core, and analog audio: separate designs.
2. HDMA and PPU/APU responder cases in the bus model; B-bus reads that an external device answers. A-to-B copies from the cartridge are now exercised by real programs ([game-simulation.md](game-simulation.md)); B-to-A copies from a device on the cartridge side are decoded but not exercised.
3. Hardware fault gating: connect `bus_permit` to the rail monitor and eFuse fault outputs; the bridge currently exposes the input only.
4. Real timing: translator delays, socket loading, and measured setup/hold at the socket on a prototype.
5. Physical bring-up order from the [acceptance register](../requirements.md) §13 before any real cartridge.
