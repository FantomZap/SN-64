# Integrated top level and system simulation

Snapshot 2026-09-29. [fpga/rtl/sn64_top.sv](../../fpga/rtl/sn64_top.sv) connects every FPGA block that exists so far. [fpga/tests/tb_system.sv](../../fpga/tests/tb_system.sv) runs the whole power-on story in simulation. **Nothing here has run on hardware**, and the board wrapper (PLLs, the SNES clock select/gate primitive, pad constraints) is not written yet.

## Plain-language summary

This is the point where the separate pieces become one design. The system test powers everything up the way a real console would: the N64 boots our menu and asks for the cartridge, the cartridge gets power in the safe order, the clock chip is programmed, the region is decided, the SNES clock starts once, the reset lets go, and the SNES runs a program from a (simulated) cartridge that reads the buttons the N64 sent. It passes in about 5 seconds on the PC. Its first run found a real deadlock in the reset wiring, which is now fixed.

## Blocks and clock domains

| Domain | Clock | Blocks |
|---|---|---|
| Housekeeping | 25 MHz oscillator | [Si5351 start-up and region latch](clock-plan.md), [power sequencer](power-sequencer-implementation.md), [SNES CIC lock](snes-cic-implementation.md) (CIC_CLK = 25 MHz / 8 = 3.125 MHz) |
| Host | 62.5 MHz from an ECP5 PLL, always on | [N64 endpoint](n64-endpoint-implementation.md) (PI bus, mailbox, bootstrap ROM window) and the [N64 CIC](n64-cic-implementation.md) soft CPU |
| SNES | Si5351 NTSC or PAL master, started once per cartridge power-up | SNES core, [cartridge bridge](cartridge-bridge-implementation.md), [controller emulation](controller-path-implementation.md) |

The N64 endpoint must run from an always-on clock: the N64 boots the menu before the SNES clock exists. Crossings use [sn64_cdc.sv](../../fpga/rtl/sn64_cdc.sv): two-flop synchronisers for levels and a toggle-handshake word transfer for the controller images, status and fault words and the mailbox CONTROL bits. The word transfer is tested for torn values across unrelated clocks ([tb_cdc.sv](../../fpga/tests/tb_cdc.sv)).

## Power-on sequence as implemented

1. Board reset releases; the Si5351 is programmed and both PLLs lock (`STATUS[0]`).
2. The N64 boots the bootstrap from the ROM window, checks MAGIC and writes CONTROL.run_request.
3. The power sequencer holds cartridge /RESET, enables 5 V, then the interface rail.
4. The SNES CIC lock starts on its own clock. The region is decided by the forced mode, a passing key's type, a failing/absent key (NTSC default) or a 300 ms timeout.
5. `snes_clk_run` starts the SNES master at that region's frequency. It never changes while it runs; see the [clock plan](clock-plan.md).
6. After 1 ms of running clock the sequencer releases /RESET and grants bus permission; the core leaves reset.

Socket /RESET is owned by the sequencer and the bus permission only. A soft reset (CONTROL bit 1) holds /RESET without removing cartridge power. Dropping run_request, a host reset or a fault shuts the cartridge down and stops the SNES clock.

## System simulation

`tb_system.sv` models an N64 host on the PI bus, a Si5351 I²C slave, cartridge rails that follow their enables, a ROM/SRAM cartridge that drives D0–D7 only while selected and /RD is low, and a cartridge without a key CIC. The SNES clock exists only while `snes_clk_run` is high. It checks, every clock, that the socket is never driven without permission, that the SNES clock never runs without cartridge power, that the region never changes while it runs, and that /RESET is held until it runs. It then requires the SNES program to write its proof-of-life byte, read the controller image the N64 sent via auto-joypad (`$4218/$4219`), and the N64 to read STATUS showing RUN.

Result: **PASS**, STATUS `0x545F` (configured, rails, bus permit, run requested, NTSC, RUN, SNES clock running, key CIC failed as expected for a cartridge without one). It is part of `evaluate.py --mode sim`.

Finding fixed: the bridge pulled socket /RESET while the core was in reset, and the core reset followed the socket /RESET level, so neither could leave reset. Only the sequencer and bus permission now drive /RESET.

Limits: no key CIC and no PAL run in this test (both are covered by the [SNES CIC unit bench](snes-cic-implementation.md)), no A/V, no N64 CIC exchange (covered by its own bench), behavioural rails and cartridge, representative PI timing.

## Whole-design synthesis

`sn64_top` with every block (SNES core, bridge, N64 endpoint and CIC, SNES CIC lock, controllers, power sequencer, clock start-up, CDC) synthesises for ECP5 with the pinned OSS CAD Suite in 45 s: **28,813 LUT4 (34 % of the 85F), 12,038 FF, 19 MULT18X18D and 205 of 208 DP16KD**; final netlist check reports 0 problems (log `build/sn64-top-synth.log`, untracked). The block-RAM figure includes the 64 blocks of the 64 K-word bootstrap ROM window and confirms that the ROM cannot stay in block RAM once A/V buffering is added. 
A first full place-and-route used [sn64_pnr_wrap.sv](../../fpga/rtl/sn64_pnr_wrap.sv), which keeps every board interface as a pin, ties off the simulation-only ROM load port and XOR-reduces the SNES video/audio outputs into pins so the PPU/APU logic is not optimised away. nextpnr-ecp5 (85F, CABGA381, speed 6, placer-chosen pins, 208 s) **met all three clocks**: SNES master 28.36 MHz achieved vs 21.48 MHz required (+32 %), host 87.11 MHz vs 62.5 MHz, housekeeping 61.97 MHz vs 25 MHz; 117 of 365 I/O sites, 141 of 208 DP16KD (the unwritten bootstrap ROM is removed in this run, consistent with moving it to flash), 19 multipliers. Cross-domain paths are synchronised by design and not timed; pins are not the final allocation, and the A/V block was not yet included.

## Open integration decisions

1. **Bootstrap ROM storage.** The first menu ROM is 114,688 bytes and needs a 64 K-word window: 64 DP16KD blocks. Whole-design synthesis confirms 205 of 208 blocks used with it, so it must move out of block RAM. Options: serve it from the FPGA configuration flash through SummerCart64's flash path (it already serves its bootloader from flash), or from external RAM if the A/V design needs one anyway. `ROM_ADDR_BITS` stays configurable until this is decided.
2. **Board wrapper:** ECP5 PLLs for 62.5 MHz and the HDMI clocks, a glitch-free SNES clock select/gate (DCS) driven by `snes_clk_run`/`region_pal`, I/O standards and pin constraints.
3. **A/V output** integration once its block is merged.
4. **ROM header region fallback** (`$00:FFD9`) needs a pre-boot bus master in front of the bridge; today an absent key means NTSC unless the menu forces PAL.
5. Whole-design place-and-route for timing.
6. **CIC data pin circuit** (must fix before layout): the [cartridge interface sheet](cart-interface-schematic.md) treats CIC_DATA0 as output-only and CIC_DATA1 as input-only, but the lock protocol drives each pin in some rounds and receives on it in others. Each needs its own enabled bidirectional path with a pull-down.


## Place-and-route with HDMI (2026-09-29)

Reproduce with `python fpga/tools/route_top.py` (OSS CAD Suite on PATH; writes `build/route-top/summary.json`). Synthesis loads the ECP5 cell library and defines `VERILATOR` (core memory branch) and `SN64_SYNTH` (real ODDRX1F in the HDMI serializer). The trial constraints [fpga/constraints/sn64_trial.lpf](../../fpga/constraints/sn64_trial.lpf) set all five clock frequencies and borrow the ULX3S HDMI pins (same 85F CABGA381 package) because DDR outputs need fixed PIOs; every other pin is placer-chosen.

| Clock | Required | Achieved (grade 6) |
|---|---:|---:|
| SNES master | 21.48 MHz | 28.54 MHz |
| Host (N64 endpoint, CIC) | 62.5 MHz | 84.25 MHz |
| Housekeeping | 25 MHz | 61.40 MHz |
| HDMI pixel | 27.02 MHz | 56.60 MHz |
| HDMI TMDS bit clock | 135.1 MHz | 317.36 MHz |

Resources: 29,224 LUT4 / 33,899 TRELLIS_COMB (40 %), 12,910 FF (15 %), 143 of 208 DP16KD, 20 MULT18X18D, 4 ODDRX1F, 122 I/O. The bootstrap ROM block RAM is not counted (its load port is tied off and it is being moved to flash). Cross-domain paths are synchronised by design and excluded; this is internal feasibility, not a board timing sign-off.
