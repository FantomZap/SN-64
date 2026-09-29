# Integrated top level and system simulation

Snapshot 2026-09-29. [fpga/rtl/sn64_top.sv](../../fpga/rtl/sn64_top.sv) connects every FPGA block that exists so far. [fpga/tests/tb_system.sv](../../fpga/tests/tb_system.sv) runs the whole power-on story in simulation. **Nothing here has run on hardware.** The board top level [sn64_board_top.sv](../../fpga/rtl/sn64_board_top.sv) (PLLs, the SNES clock select, flash boot ROM, CIC pads) exists; the final pinout waits for the FPGA sheet of the schematic.

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
4. The SNES CIC lock starts on its own clock, and the [ROM-header probe](header-region-probe.md) reads `$00:FFC0-$00:FFDF` while the cartridge is still held in /RESET. The region is decided in priority order: forced mode, a passing key's type, a valid ROM header, NTSC default (also after the 300 ms timeout).
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

Status 2026-09-29 (evening):

1. **Bootstrap ROM storage: resolved.** The ROM window is served from the FPGA configuration flash ([bootrom-flash.md](bootrom-flash.md), SummerCart64 `memory_flash.sv` unmodified, `ROM_FROM_FLASH=1` in the board top). This frees 64 DP16KD. Still open: the sysCONFIG setting that frees CSSPIN/D0-D3 after configuration, flash part selection (QE bit, tCLQV), the programmer offset, and the menu rule that PI DOM1 LAT stays at the header's 0x40.
2. **Board wrapper: written** ([sn64_board_top.sv](../../fpga/rtl/sn64_board_top.sv)). EHXPLLL 25 -> 62.5 MHz and pixel -> x5, one DCSC that both selects NTSC/PAL and starts/stops the SNES clock, flash boot ROM, CIC pads. Still open: the real pinout and I/O standards (needs the FPGA schematic sheet).
3. **A/V output:** merged (HDMI 720x480p with 32 kHz audio). PAL raster and cartridge analog audio still open.
4. **ROM header region fallback: implemented** ([header-region-probe.md](header-region-probe.md)), tested alone and in `tb_system` with an EU header (PAL) and without a header (NTSC).
5. **Place-and-route:** see below; the board top is routed with real clock primitives.
6. **CIC data pin circuit: resolved.** Schematic rev 0.3.1 gives each CIC data pin its own SN74LVC1T45 with a dedicated DIR pin and pull-downs ([cart-interface-schematic.md](cart-interface-schematic.md)). [sn64_cic_pad.sv](../../fpga/rtl/sn64_cic_pad.sv) sequences DIR against the pad drive; [tb_cic_pad.sv](../../fpga/tests/tb_cic_pad.sv) checks it against a translator model, and a fault build that switches both together is rejected.
7. **Header telemetry:** STATUS is full; the menu cannot yet see why a region was chosen (header valid, country, reject reason). Needs a new mailbox word.

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

## Board top place-and-route with real clock primitives (2026-09-29)

Reproduce with `python fpga/tools/route_top.py` (default `--top board`; writes `build/route-board/summary.json`). This routes [sn64_board_top.sv](../../fpga/rtl/sn64_board_top.sv): the clocks now come from pins through the real ECP5 primitives (two EHXPLLL, one DCSC), the bootstrap ROM is served from the configuration flash through USRMCLK, and the CIC data pads have their DIR sequencing. Constraints: [sn64_board_trial.lpf](../../fpga/constraints/sn64_board_trial.lpf) (clock frequencies on the four clock pins; ULX3S sites for the oscillator, HDMI and flash pins; everything else placed by the tool). nextpnr-ecp5, 85F, CABGA381, speed grade 6:

| Clock | Required | Achieved |
|---|---:|---:|
| SNES master (after the DCSC) | 21.48 MHz | 27.30 MHz |
| Host, from PLL (N64 endpoint, CIC, flash) | 62.5 MHz | 82.90 MHz |
| Housekeeping, 25 MHz oscillator | 25 MHz | 61.46 MHz |
| HDMI pixel (Si5351 CLK2) | 27.02 MHz | 62.50 MHz |
| HDMI TMDS bit clock, from PLL | 135.1 MHz | 320.20 MHz |

Resources: 34,773 TRELLIS_COMB (41 %), 13,342 FF (15 %), **143 of 208 DP16KD** (the bootstrap ROM no longer uses block RAM), 20 MULT18X18D, 2 of 4 EHXPLLL, 1 of 2 DCSC, 121 I/O. nextpnr derived the SNES clock constraint through the DCSC by itself and promoted all five clocks to the global network. Cross-domain paths are synchronised by design and are not timing-checked; the SNES domain's worst reported cross-domain path is 24.5 ns. This is a feasibility result on a trial pinout: the real pin assignment, I/O standards and board timing come with the FPGA schematic sheet.

