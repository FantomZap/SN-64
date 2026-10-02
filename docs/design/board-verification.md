# Is the v2 board right? What has been checked, and what has not

**Status (2026-10-02, after the pre-order review): the files for a price quote are ready; not ready to order. The wiring is traced and passes, and a real game runs through a model of the board. The pre-order review ([pre-order-review.md](pre-order-review.md)) found faults in the layout that no simulation here shows: ground copper between the edge fingers, a power section laid out like signal wiring, capacitors far from their chips, and three more rules of the makers' data sheets. All are corrected on the board. What is left needs a real socket, a real console or PCBWay's answer: the list at the end.**

The owner's question: can the board be ordered without it turning out a paperweight? This note keeps the answer in one place. It lists every kind of mistake that would ruin a board, what checks it, and how far that check has got. "Passed" below always means the named check on the PC, never a test on hardware.

## What can and cannot be put right after the board is made

| | After the board is made |
|---|---|
| The FPGA's logic | Can be corrected: it is loaded through the USB port, also when the board is blank. The faults found by the game runs were of this kind. |
| Which pin goes where, the parts, the copper, the connectors' shape and position | Cannot. These are what the checks below are for. |
| The FPGA's configuration pins, the flash, the supplies, the JTAG pads | Cannot, and nothing else can be corrected without them: they are the way in. |
| The USB port and its loader chip | Their wiring cannot. Since 2026-10-02 the port no longer depends on the FPGA's logic: see "The first load" below. |

## The checks

| Mistake that would ruin a board | Check | State |
|---|---|---|
| A signal on the wrong FPGA ball, level-shifter pin, socket pin or edge finger | [verify_board_wiring.py](../../hardware/sn64-v2/tools/verify_board_wiring.py): traces every port from its ball through the level shifter to the connector pin, in the board file itself | **24 of 24 pass; 29 of 29 deliberate mistakes caught** |
| The same, with everything working together | [board-simulation.md](board-simulation.md): the owner's game through a model of the board made from the board file, cartridge and N64 plugged in by pin number | **a game boots and plays; two deliberately mis-wired boards are refused** |
| A level-shifter byte pointing the wrong way, or enabled when it must not be | both of the above | pass, after the correction of 2026-10-02 |
| Board and schematic disagree | wiring check: every pad's net compared with the schematic's list | pass (194 parts); KiCad's own comparison of board and schematic lists no difference |
| FPGA supply, ground, configuration, clock balls wrong | wiring check, against Lattice's pin-out table | pass |
| A part's pin numbers differ from its maker's sheet | each sheet read again, pin by pin, against the board | **done from the makers' sheets for 12 kinds of part and from the supplier's data for one; all agree** (table below). One small part not re-read |
| A part is wired against a rule of its sheet | the same reading | **two found on 2026-10-02 and corrected (below); three more found in the pre-order review the same day, in the layout and application sections of the sheets, and corrected** ([pre-order-review.md](pre-order-review.md)): a resistor in the 5 V converter's enable line, a small capacitor at its pins, 1 µF at each supply pin of the measuring chip |
| A converter's capacitors and coil are too far from it, or a chip's capacitor is not at its pin | wiring check: the distance from each of 40 capacitors to the pin it serves; [power_paths_v2.py](../../hardware/sn64-v2/tools/power_paths_v2.py): the narrowest track on each supply path | **pass since the re-layout of 2026-10-02**: 3.5 mm at most with four named exceptions; no supply path narrower than 0.25 mm |
| Bare copper where the console's connector slides | the edge fingers looked at layer by layer | **pass since 2026-10-02**: no fill in the finger zone, no inner copper under the fingers ([apply_finger_clearance_v2.py](../../hardware/sn64-v2/tools/apply_finger_clearance_v2.py) checks both before it saves) |
| Copper does not join what it should, or joins what it should not | KiCad's design-rule check | **pass: no error, no open connection, 218 of 218 signal nets complete, and no warning other than the 199 notes at the edge fingers** (`validation/pcb-open-connections.json`) |
| The logic does not run a game | [game-simulation.md](game-simulation.md) | a real game boots and plays; 38 of 38 judged test programs pass; three faults found and corrected |
| The logic is too slow for the chip | route and timing check of the whole design on the board's pins | pass with the final logic: every clock, SNES master 34.6 MHz against 21.5 needed |
| A footprint does not fit its part | KiCad library footprints for standard packages; own footprints for the socket, the N64 edge, the USB-C, the buck-boost and an inductor | **checked on 2026-10-02 against the makers' drawings: all agree but one.** The measuring chip's footprint had the wrong exposed pad and was changed ([pre-order-review.md](pre-order-review.md)) |
| The cartridge socket's pads do not meet a real socket's tails | none possible on the PC | **open: no socket has been measured** |
| The socket or the N64 edge is mirrored or back to front | orientation reasoned from the SNESdev and N64brew pin-outs and SummerCart64's board (2026-09-30); the wiring check and the board run catch a mirrored net list but not a mirrored footprint. Looked at again on 2026-10-02: the board file has socket pins 1 to 31 and edge pins 1 to 25 on the face towards the player, both with pin 1 at the player's left. The SNESdev page says in so many words that pins 01 to 31 are the row nearest the console's front, drawn from the console's right side, which puts pin 1 at the left: the socket agrees. The N64brew page gives the edge's pin table but not its orientation; the edge is SummerCart64's own footprint, the same way round in SummerCart64's own shell | **socket: confirmed from the source a second time. N64 edge: confirmed on 2026-10-02 from ModRetro's drawing of the M64 main board** (`M64_MLB_SCH.pdf`, page 31: pins 1 to 25 in the row towards the front, pin 1 at the player's left) |
| A supply gives the wrong voltage or cannot carry the load | divider values recomputed (5.0, 3.3, 1.1 V; reset threshold 3.03 V); budget from the console's 3.3 V | **estimated on 2026-10-02, not measured** ([pre-order-review.md](pre-order-review.md)): menu and plain cartridges are inside what an M64 gives; a flash cartridge on an M64 needs the USB cable |
| A blank board cannot be loaded | a loader chip between the USB-C socket and the FPGA's JTAG port ([usb-loader.md](usb-loader.md)); the wiring check follows it pin by pin, with the pin numbers from the chip's data sheet and from the source of the PC program | **wired and checked on the PC; not tried on a board** |
| The board breaks PCBWay's rules | the board against the limits on PCBWay's page | **three points to ask with the quote**: 85 vias in pads, 802 vias with a 0.125 mm ring, one narrow oval hole ([quote-sheet.md](../../hardware/sn64-v2/production/quote-sheet.md)). Everything else is inside their stated limits |

## What the makers' data sheets said

Read on 2026-10-02 from each maker's own sheet, pin by pin, against the pads of the board file. The sheets are kept on the owner's PC under `build/`, not in the repository.

| Part | Sheet | Pins agree with the board | What else it says that matters here |
|---|---|---|---|
| SN74ALVC164245 level shifter (U201 to U204) | TI SCAS416Q | yes, all 48 | A side is 2.5 or 3.3 V, B side 3.3 or 5 V; direction and enable pins belong to the A supply. Section 10: power the A side first, with `/OE` pulled up to it. Section 3: the inputs of both sides are always active and must not float. A B-side pin may be at most 0.5 V above the B supply |
| SN74LVC07A open-drain driver (U205) | TI SCAS595W | yes | |
| TPS2553 cartridge switch (U12) | TI SLVS841F | yes; enable is active high | |
| TLA2528 supply converter (U6) | TI SBAS961A | yes | Table 2: the I2C address is set by resistors on ADDR; with the pin open it is 0x10. 1 µF on AVDD and on DVDD, close to the pins; AVDD is also the reference |
| TPS3808G01 reset supervisor (U3) | TI SBVS050N | yes | timing pin open: fixed delay |
| TPS2121 input selector (U7) | TI SLVSEA3F | yes | sections 11 and 12: capacitors on IN1, IN2 and OUT as close as possible, short wide traces |
| TPS63070 5 V converter (U8) | TI SLVSC58B | yes | 11.1: capacitors and coil as close as possible; a 0603 capacitor at the input pins and one at the output pins; EN through 10 k when tied to the supply. 7.5: it starts only from 3.0 V and may draw about 1 A while starting. PS/SYNC low is forced PWM |
| TLV62569 3.3 V and 1.1 V converters (U9, U10) | TI SLVSDG1C | yes | enable must not float: it is driven by the 5 V converter's power-good with its pull-up. 10.1: capacitors and coil as close as possible. The supply pin's limit is 6 V |
| W25Q128JV flash (U2) | Winbond, revision F | yes | |
| 27 MHz oscillator (X1) | Interquip SPXO 3225 163-B | yes | land pattern as the board's; 10 mA |
| LFE5U-85F FPGA (U1) | Lattice pin-out table | yes (wiring check) | |
| AP2112K-2.5 regulator (U11) | Diodes DS39724 rev. 2-2 | yes | |
| FT231XS loader chip (U13) | FTDI FT_000565 version 1.2 (read from the supplier's copy; FTDI's site did not answer) | yes, all 20 | Figure 6.1: fed from the cable, with VCCIO and RESET# on its own 3.3 V output. The four pins used for JTAG are inputs until the PC switches the chip to bit-bang mode |
| USBLC6-2SC6 protection (U4) | ST Doc ID 11265 Rev 5 (the supplier's copy) | yes | |

### The two mistakes, and what was done

**1. One half of a level shifter was switched on all the time.**

- U204's second byte brings the cartridge's CIC data, `/IRQ` and `/RESET` back to the FPGA. Its enable pin was tied to ground.
- The B side of every level shifter is fed from the cartridge's switched 5 V. In the menu, with the cartridge off, that byte was enabled with one of its two supplies missing. The sheet's rule is to keep `/OE` high until both supplies are up. What the part does otherwise is not stated: an undefined level on its outputs and extra current are possible.
- **Now:** the enable is a line of its own, `SENSE_OE_N`, driven by the FPGA and pulled up by a new 100 k resistor (R214). The logic switches the byte on only while the cartridge has its 5 V. The line uses the FPGA ball and trace that carried the EXPAND sense, which the logic never read; EXPAND keeps its pull-up. The byte's four unused channels have both pins on ground, and the FPGA's pads on the data and sense lines have a pull, so that nothing floats while a byte is off.
- The other seven bytes already followed the rule: their enables are pulled up and driven by the FPGA.
- One thing is accepted as it is: five unused outputs of U203 are open. They are driven whenever their byte is on and have no supply while the cartridge is off; they float only for the few milliseconds between the 5 V coming up and the byte being switched on.

**2. The supply converter's address pin was tied to ground.**

- The logic talks to the converter at address 0x10. The sheet's table gives 0x10 for the address pin left open, and three other addresses for a resistor to ground. Straight to ground is not in the table.
- If the part took another address, the logic would get no answer, would report a converter error, and would never switch a cartridge on. It could have been put right in the logic afterwards, by trying the other addresses.
- **Now:** the pin is open, as the table has it.

Both changes were carried into the routed board by [apply_enable_fix_v2.py](../../hardware/sn64-v2/tools/apply_enable_fix_v2.py): 10 pads on new nets, 9.2 mm of new track on the bottom layer, one resistor, two ground bars across pads, the dead branch of the EXPAND trace removed. KiCad's design-rule check shows no new error and the same six open connections as before. The wiring check has a rule for each, and the board run refuses a board with either mistake put back.

## What the wiring check covers

It reads three things that are made independently of one another: the board file (which pad is on which net), the FPGA constraints (which port is on which ball), and the two connector tables that v1 drew from other people's working boards (OpenSFC, sd2snes and the Sanni reader for the SNES socket; SummerCart64 and ModRetro's schematics for the N64 edge). A port passes when its ball's net reaches the connector pin that carries that signal on a real console, through a level-shifter channel that points the right way and is switched by the right port.

- 43 outputs to the cartridge, D0 to D7 both ways, 4 inputs from it, 3 open-drain pulls; unused open-drain gates tied off, and none on PROGRAMN.
- Every level-shifter enable driven by the FPGA and pulled up; no pin that can float for long left open.
- 27 signals on the N64 edge, its supply fingers and the unused 12 V fingers.
- The flash on the configuration balls, the mode pins, the clock, the reset supervisor, the cartridge sound input.
- USB: D+ and D− through their resistors to the loader chip and to nothing else, the chip's supply pins as its data sheet draws them.
- JTAG: the loader chip's four pins on the FPGA's JTAG balls in the order the PC program drives them, the pulls on the four lines, and nothing else on them.
- The supply converter: address pin, I2C lines, supplies, and the cartridge supply on the input the cartridge check uses.
- Every supply and ground ball of the FPGA.

`--negative` makes 29 deliberate mistakes one at a time, among them the socket's rows exchanged, the socket mirrored, a byte pointing the wrong way, a byte enabled all the time, the converter's address pin on ground, two ports exchanged in the constraints, two JTAG lines swapped at the loader chip and the loader chip's I/O supply on the wrong rail. Each is caught.

It says nothing about voltages, timing, footprints or whether the logic works.

## The first load

**Settled on 2026-10-02.** Until then the USB port was part of the FPGA's logic. A board that comes from the factory with an empty flash has no logic, so its USB port did nothing, and the first load would have had to come another way. The board-level run brought this to light. The three ways that were put to the owner:

| Way | What it needs | |
|---|---|---|
| PCBWay programs the flash chip before it is soldered | their programming service, and a file from us | not chosen |
| The five JTAG pads on the board | a JTAG adapter and five wires or spring pins | kept as a second way in |
| A USB-to-JTAG chip on the board | a chip and its few parts | **chosen**: "Add back just the usb loader chip" |

The chip is an FTDI FT231X between the USB-C socket and the FPGA's JTAG port, wired like the open ULX3S board so that openFPGALoader drives it as it is ([usb-loader.md](usb-loader.md)). It loads a blank board, every later update, and a board whose image has gone bad. The FPGA's own USB logic was taken out at the owner's word ("i want it clean so remove it").

What is not known until a board exists: that a real PC loads a real board this way. Neither the chip nor the JTAG port is in any simulation here.

## Still open before an order

| What | Who |
|---|---|
| Measure a real cartridge socket against the footprint | the owner: a socket sample is needed |
| The price, and PCBWay's answer to three questions: vias in pads, the 0.125 mm ring, the narrow oval hole ([quote-sheet.md](../../hardware/sn64-v2/production/quote-sheet.md)) | the owner asks for the quote; nothing has been sent |
| How long a console waits before it first asks the cartridge. The FPGA is ready about 0.1 s after power-on ([pre-order-review.md](pre-order-review.md)) | the first board, on an N64 and an M64 |
| Starting from an M64's limited cartridge supply; power for a flash cartridge on an M64 | the first board |
| Load a board over USB for the first time: the loader chip has not met hardware | the first board |
| The converters follow their makers' layout rules; how quiet the supplies are is not simulated | the first board |
| Sound: the cartridge sound input adds a faint pattern to every game ([game-simulation.md](game-simulation.md)); a matter of the logic | Claude |

## Found on the way, and settled

- **A blank board could not be loaded over USB** (found by the board-level run, 2026-10-02). Settled the same day by the owner: a loader chip on the board, and the USB-C port on the player's right ([usb-loader.md](usb-loader.md)).

- **The status LED** lights when its FPGA pin is low; the logic drove it high in a game. Corrected in the logic on 2026-10-02; the board run checks that it is lit in a game.
- **The cartridge's control lines have no pull resistors on the 5 V side.** The logic now drives them at rest whenever the cartridge has its 5 V, and holds `/RESET` low for 1 ms before it lets them go at power-off ([board-simulation.md](board-simulation.md)). While the cartridge is off, neither it nor that side of the level shifters has a supply.
