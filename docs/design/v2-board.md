# SN64 v2 board: schematic write-up and rationale

**Status (2026-09-30): draft 0.1 on branch `v2`. One board. Schematic complete (ERC 0 errors), FPGA
logic simulated and routed with timing met, board routed to 211 of 218 nets with 7 nets left for
hand routing. Not fabrication-ready: see "Open items".**

v1 (`hardware/sn64/`) turned every line of the specification into its own chip: six window
comparators, a temperature switch, a USB-C controller, three eFuses, a clock synthesiser, two
packaged oscillators, an audio ADC, a USB bridge with its own crystal and EEPROM, three bus
switches, seven octal translators. 47 ICs, 149 resistors, 162 capacitors, 1,453 vias on the
first routed draft. v2 keeps every specification target and moves what the FPGA can do into the
FPGA, trims what remains outside it, and changes the two-board arrangement so the hard part of the
layout disappears.

| | v1 | v2 (main + riser) |
|---|---|---|
| ICs | 47 | 16 (FPGA, flash, 4 translators, hex driver, ADC, supervisor, USB ESD, mux, buck-boost, 2 bucks, LDO, cart switch) |
| Resistors | 136 + 13 arrays | 62 |
| Capacitors | 162 | 79 |
| Other (inductors, oscillators, crystals, MOSFETs, LEDs, beads) | 22 | 5 (3 inductors, 1 oscillator, 1 LED) |
| Placed parts | 380 | 176 |
| FPGA signal balls | 122 over rings 1-5 | 111, all on rings 1-3 |
| FPGA fan-out vias | 326 | 210 |
| Boards | 2 (main + socket board, 80-pin joint) | 1 |

## Arrangement (one board, owner decisions 2026-09-30)

One vertical board standing in the N64/M64 slot with the SNES cartridge upright on top of it, in
line: one continuous vertical item like a TriStar 64. The bottom is the SummerCart64 edge geometry
(tongue 10.5 mm below the shoulders, 1.2 mm thick, 101.8 mm wide with the shell notches, six
layers). The SNES socket (console-replacement family with ears: 62 contacts, 2.5 mm pitch, rows
7.0 mm apart, ear holes 95 mm apart) sits on the board's top edge with its tails on pads on both
faces, pins 1-31 on the front face. Its ears screw into the shell, which takes the insertion force,
and above the USB-C the shell bells out into a mushroom cap whose pocket holds the bottom of the
cartridge on all four sides. How the tails reach the pads is settled in the board footprint once a sample is measured. Shell
envelope: [v2-shell.md](v2-shell.md).

History: the board was first drawn with the socket through-hole on its face and the cartridge lying
flat over the console; the owner rejected that when he saw it in 3D. The committed routed board
still has J2 on the face at 56.5 mm. Moving it to the top edge, widening the outline for the USB-C
and moving the USB-C above the console line are the next board change (list in v2-shell.md).

Layout (committed board) is the horizontal v2 layout turned 180 degrees: FPGA banks 0/1 face the
N64 edge, the translator row sits between the FPGA and the socket, USB-C on the right edge, power
lower left.

## What moved into the FPGA (LFE5U-85F-8BG381I, the grade in stock)

| Function | v1 parts | v2 | Where |
|---|---|---|---|
| Clocks | Si5351A + 25 MHz crystal, 25 MHz and 12.288 MHz oscillators, I2C start-up machine | One 27 MHz oscillator; three PLLs (feedback from CLKOS): NTSC 21.477273 MHz exact (27/2 x 5 x 7 / 22), PAL 21.280788 MHz (-27 ppm against 21.28137: 27/7 x 4 x 40 / 29), 48 / 61.71 / 12 MHz for USB and the host side from one 432 MHz VCO | `fpga/rtl/sn64_board_top.sv` |
| USB programming and recovery | FT232H, 12 MHz crystal, EEPROM, 3.3 V LDO, 4-bit isolator, second ESD part | Full-speed USB device on two FPGA pins running the TinyFPGA bootloader protocol (`tinyprog` reads, erases, writes the flash and reboots the FPGA); 22 R series, 1.5 k pull-up switched by the FPGA; one ESD part | `fpga/rtl/sn64_usb_prog.sv`, vendor `fpga/vendor/tinyfpga-bootloader` (Apache-2.0) |
| Rail and temperature telemetry, USB-C detection | 6 x TPS3700, TPS3808, TMP302, TUSB320, 8 x BSS138, ~45 resistors | TLA2528 8-channel I2C ADC read by the FPGA, thresholds in logic; NTC for temperature; CC1/CC2 read directly (Rd resistors do the Type-C sink job); TPS3808 kept as the pre-configuration reset supervisor | `fpga/rtl/sn64_rail_monitor.sv` |
| Cartridge audio ADC | PCM1808 + 12.288 MHz oscillator + bead | First-order sigma-delta per channel: LVDS input pair as the comparator, 10 k / 1 nF integrator on a feedback pin, 2048-clock boxcar (~30 kHz, ~10 bits) | `fpga/rtl/sn64_sd_adc.sv` |
| Power sequencing and priority | MOSFET level shifters, eFuse enable logic | FPGA drives the cartridge switch enable; the input mux has its own priority logic | `sn64_power_sequencer.sv` (unchanged) |
| N64 bus isolation | 3 x SN74CB3Q3384A | Dropped: bank 0/1 are hot-socketing banks; the pins are inputs with weak pulls until configured. Under 1 mA leakage into a switched-off console in USB-only use is accepted (owner decision 2026-09-30) | |

## What stays outside, and why

- **Cartridge translators.** The FPGA is not 5 V tolerant and cannot drive 5 V CMOS inputs. Four
  SN74ALVC164245 (the sd2snes part; A = 3.3 V, B = 5 V, Ioff for the unpowered cartridge side):
  U201 A0-15, U202 A16-23 + RD/WR/PRD/PWR/ROMSEL/WRAMSEL/REFRESH/PHI2, U203 PA0-7 + SYSTEM_CLK /
  CIC_CLK / CIC_SLAVE_RESET (its own enable), U204 D0-7 bidirectional + the five inputs
  (CIC_DATA0/1, IRQ, RESET sense, EXPAND) as a permanently enabled B-to-A byte.
- **SN74LVC07A hex open-drain driver** at 3.3 V with 5 V pull-ups for the lines the FPGA only ever
  pulls low: PROGRAMN (reboot after a USB update), SNES_CIC_DATA0/1, SNES_RESET_N.
- **Power**: TPS2121 mux (USB has priority above 4.0 V, host 3.3 V otherwise, 2.5 A limit),
  TPS63070 buck-boost to 5 V (v1 values), TLV62569 bucks for 3.3 V and 1.1 V (v1 values), AP2112K
  LDO for 2.5 V (about 20 mW traded for an inductor and three parts), TPS2553 cartridge switch
  with a fault flag and ~1 A limit, TPS3808 supervisor on FPGA_3V3.
- **Flash** W25Q128 (bitstream + golden image + boot program), 27 MHz oscillator, 30 decoupling
  capacitors (Lattice checklist counts, not one per ball), status LED, JTAG pads.

## Deviations from the plan given to the owner

- Rail telemetry uses one I2C ADC chip rather than sigma-delta channels in the FPGA: eleven
  channels that way would have been 44 passives and 22 FPGA pins against one chip and ten
  resistors. The audio channels do use the sigma-delta method.
- The series resistor arrays on the cartridge bus (13 in v1, marked "tune") are omitted; fit on the
  prototype only if ringing is measured.

## Files

| | |
|---|---|
| Generator | `hardware/sn64-v2/tools/build_v2_schematic.py` (every part, value, source and net; `--force` regenerates all sheets) |
| Pin plan | `hardware/sn64-v2/tools/pin_plan.py` -> `interfaces/fpga-pin-map.csv`, `fpga/constraints/sn64_board.lpf` |
| Sheets | `sn64-v2.kicad_sch` (root), `fpga.kicad_sch`, `cart.kicad_sch`, `power.kicad_sch` |
| Libraries | `libraries/SN64_V2.kicad_sym` (TPS2121, TLA2528, TPS2553 drawn from the TI pin tables), v1 libraries reused unchanged; `libraries/v2-provenance.json` |
| Boards | `build_v2_pcb.py` (placement), `prepare_route_v2.py` (fan-out, planes), `apply_netclasses_v2.py`, `finish_route_v2.py`, `add_plane_vias_v2.py`; router KiCadRoutingTools (see `docs/design/pcb-routing.md`) |
| Checks | `validation/erc.json` (0 errors, 8 warnings: unused translator inputs tied to ground), `validation/*.xml` netlists, DRC reports under `build/` |
| FPGA | `fpga/tools/evaluate.py --mode sim` (all benches pass, new `tb_sd_adc`); `fpga/tools/route_top.py --top board --speed 8` routes with every clock passing timing (`fpga/reports/v2-board-route.json`: 30.7k LUT4, 203/208 block RAMs, 111 I/O) |

## Provisional values (to confirm at review or bring-up)

TPS2553 RILIM 24.9 k (~1.0 A); TPS2121 CSS 1 nF; decoupling counts; sigma-delta RC 10 k / 1 nF;
NTC part and its threshold; TLA2528 register map and I2C address (SBAS925, manual mode); TLA2528
footprint exposed-pad size; USB pull-up switched only after PLL lock.

## Open items

- Routing: 211 of 218 signal nets (KiCadRoutingTools passes plus scripted gap closing); 7 nets left for hand routing in KiCad (`validation/pcb-open-connections.json`: N64_AD6 and N64_JOYBUS to the fingers, USB_PU and USB_DP_F across to the USB corner, FLASH_D2, a SNES_5V_CART segment, the TLA2528 DVDD pin). DRC: 0 errors apart from 6 single-spoke thermal reliefs and the USB-C shield pad on the edge (intended). 3,612 tracks, 997 vias (v1 draft: 7,065 and 1,453 with a fifth of the work left).
- Shell: envelope model only (`docs/design/v2-shell.md`, `mechanical/sn64-v2-shell/`): upright tower, socket ears screwed to brackets in the shell. The board changes it asks for (socket on the top edge, outline widened for the USB-C, USB-C above the console line) are listed there and not made yet.
- PCBWay: annular ring (6 mil) and spacing (5 mil) against the 0.125 / 0.1 mm rules, as in v1.
- Four-layer trial: with 210 fan-out vias and signals on the outer rings a four-layer stack may
  route; not tried yet.
- USB flash access blocks the boot-ROM window while a transfer runs: update from the boot menu or
  with the console off.
