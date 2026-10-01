# SN64 v2 board: schematic write-up and rationale

**Status (2026-10-01): draft 0.1 on branch `v2`. One board. Schematic complete (ERC 0 errors), FPGA
logic simulated and routed with timing met, board refitted to the upright tower shell with the
socket on its top edge and shortened by 10 mm on 2026-10-01 (213 of 218 signal nets fully connected).
Not fabrication-ready: see "Open items".**

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
faces, pins 1-31 on B.Cu (the face toward the front of the console, like the N64 edge's pins 1-25). Its ears screw into the shell, which takes the insertion force,
and above the USB-C the shell bells out into a mushroom cap whose pocket holds the bottom of the
cartridge on all four sides. How the tails reach the pads is settled in the board footprint once a sample is measured. Shell
envelope: [v2-shell.md](v2-shell.md).

History: the board was first drawn with the socket through-hole on its face and the cartridge lying
flat over the console; the owner rejected that when he saw it in 3D. The same day the routed board
was refitted to the tower shell (`tools/refit_tower_v2.py`, details in v2-shell.md): socket on the
top edge, outline widened for the USB-C, USB-C moved above the console line; only the socket and
USB nets were routed again. On 2026-10-01 the owner measured the console (its top is 17.7 mm above
the shoulders) and approved a shorter shell, and the board was refitted again the same way: top edge
from 70 to 60 mm, USB-C from 50 to 32.5 mm. The board is now 111 mm wide and 70.5 mm from the
tongue tip to the top edge.

Layout is the horizontal v2 layout turned 180 degrees: FPGA banks 0/1 face the N64 edge, the
translator row sits between the FPGA and the socket edge, USB-C on the right edge 32.5 mm above the
shoulders (the player's left), power lower left.

## What moved into the FPGA (LFE5U-85F-8BG381I, the grade in stock)

| Function | v1 parts | v2 | Where |
|---|---|---|---|
| Clocks | Si5351A + 25 MHz crystal, 25 MHz and 12.288 MHz oscillators, I2C start-up machine | One 27 MHz oscillator; three PLLs (feedback from CLKOS). Since 2026-10-01 the two game PLLs make twice the SNES master and `sn64_clock_pace` halves it, so the game can be slowed in 0.5 ppm steps for the frame lock ([frame-lock.md](frame-lock.md)): NTSC 42.954545 MHz (27/2 x 5 x 7 / 11), master 21.477273 MHz exact; PAL 42.564706 MHz (27/5 x 2 x 67 / 17), master 21.282353 MHz (+46 ppm against 21.28137; it was -27 ppm with the undoubled setting). 48 / 61.71 / 12 MHz for USB and the host side from one 432 MHz VCO | `fpga/rtl/sn64_board_top.sv` |
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
| Libraries | `libraries/SN64_V2.kicad_sym` (TPS2121, TLA2528, TPS2553 drawn from the TI pin tables), `libraries/SN64_V2.pretty` (straddle socket footprint from `tools/make_socket_footprint.py`), `libraries/3d/` (socket model from `tools/socket_3d_model.py`), v1 libraries reused unchanged; `libraries/v2-provenance.json` |
| Boards | `build_v2_pcb.py` (placement), `prepare_route_v2.py` (fan-out, planes), `apply_netclasses_v2.py`, `finish_route_v2.py`, `add_plane_vias_v2.py`, `refit_tower_v2.py` (tower refit), `report_board_v2.py` (DRC summary); router KiCadRoutingTools (see `docs/design/pcb-routing.md`) |
| Checks | `validation/erc.json` (0 errors, 8 warnings: unused translator inputs tied to ground), `validation/*.xml` netlists, DRC reports under `build/` |
| FPGA | `fpga/tools/evaluate.py --mode sim` (all benches pass, new `tb_sd_adc`); `fpga/tools/route_top.py --top board --speed 8` routes with every clock passing timing (`fpga/reports/v2-board-route.json`, rerun 2026-10-01 with the cartridge check: 30.2k LUT4, 203/208 block RAMs, 111 I/O) |

## Provisional values (to confirm at review or bring-up)

TPS2553 RILIM 24.9 k (1.04 A nominal, 0.96 to 1.12 A by the SLVS841F equations; the choice of limit is provisional); TPS2121 CSS 1 nF; decoupling counts; sigma-delta RC 10 k / 1 nF;
NTC part and its threshold; TLA2528 register map and I2C address (SBAS961A, manual mode); TLA2528
footprint exposed-pad size; USB pull-up switched only after PLL lock.

## Open items

- Routing after the refit to the shorter shell: 3,603 tracks, 1,066 vias, 213 of 218 signal nets fully connected, 6 unconnected items (FLASH_D2, FPGA_3V3, N64_AD6, N64_JOYBUS, USB_DP_F, USB_PU); DRC errors: 6 starved_thermal. Remaining items are listed in `validation/pcb-open-connections.json` for hand routing in KiCad.
- Shell: envelope model only (`docs/design/v2-shell.md`, `mechanical/sn64-v2-shell/`): upright tower, socket ears screwed to brackets in the shell. The board was refitted to it on 2026-09-30 (socket on the top edge, outline widened for the USB-C, USB-C above the console's top) and to the 10 mm shorter shell on 2026-10-01 (top edge at 60 mm, USB-C at 32.5 mm).
- Mounting holes (2026-10-01): H1, H2, H5 and H6 are 4.0 mm (KiCad `MountingHole_4mm`, set by `tools/set_mounting_holes_v2.py`) because the shell's screw posts pass through the board there; H3 and H4 stay 2.5 mm for the shell's two registration pins, which sit at different heights so the board cannot go in back to front. No copper is within 4.5 mm of the four larger holes; the checks are unchanged (6 starved thermals, 6 open items).
- Cartridge check (2026-10-01): before the cartridge's 5 V is switched on, the FPGA uses the telemetry ADC's channel 3 as an output so that R30 feeds 0.165 mA into the rail, and reads the rail back; a cartridge that is in back to front holds it at about half a volt ([reversed-cartridge-detection.md](reversed-cartridge-detection.md)). No part, pin or trace was added. Simulated only. To do on a real board: measure real cartridges both ways round in check-only mode and set the threshold; if the gap is thin, lower R30 and R31 together for more test current.
- PCBWay: annular ring (6 mil) and spacing (5 mil) against the 0.125 / 0.1 mm rules, as in v1.
- Four-layer trial: with 210 fan-out vias and signals on the outer rings a four-layer stack may
  route; not tried yet.
- USB flash access blocks the boot-ROM window while a transfer runs: update from the boot menu or
  with the console off.
