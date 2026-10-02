# Is the v2 board right? What has been checked, and what has not

**Status (2026-10-01): not ready to order. The wiring is traced and passes; the layout is unfinished; the socket footprint has not met a real socket.**

The owner's question: can the board be ordered without it turning out a paperweight? This note keeps the answer in one place. It lists every kind of mistake that would ruin a board, what checks it, and how far that check has got. "Passed" below always means the named check on the PC, never a test on hardware.

## What can and cannot be put right after the board is made

| | After the board is made |
|---|---|
| The FPGA's logic | Can be corrected: it is loaded through the USB port. The fault found by the first game run was of this kind. |
| Which pin goes where, the parts, the copper, the connectors' shape and position | Cannot. These are what the checks below are for. |
| The USB port, the FPGA's configuration pins, the flash, the supplies | Cannot, and nothing else can be corrected without them: they are the way in. |

## The checks

| Mistake that would ruin a board | Check | State |
|---|---|---|
| A signal on the wrong FPGA ball, level-shifter pin, socket pin or edge finger | [verify_board_wiring.py](../../hardware/sn64-v2/tools/verify_board_wiring.py): traces every port from its ball through the level shifter to the connector pin, in the board file itself | **19 of 19 pass; 16 of 16 deliberate mistakes caught** |
| A level-shifter byte pointing the wrong way, or enabled when it must not be | same | pass |
| Board and schematic disagree | same: every pad's net compared with the schematic's list | pass (176 parts) |
| FPGA supply, ground, configuration, clock balls wrong | same, against Lattice's pin-out table | pass |
| Copper does not join what it should, or joins what it should not | KiCad's design-rule check | **6 connections still open, 6 thermal-relief errors** (`validation/pcb-open-connections.json`) |
| The logic does not run a game | [game-simulation.md](game-simulation.md) | a real game boots and plays; one fault found and corrected |
| The logic is too slow for the chip | route and timing check of the whole design on the board's pins | pass after the correction: every clock, SNES master 37.2 MHz against 21.5 needed |
| A part's pin numbers differ from its maker's sheet | pin tables typed once in the schematic generator and once in the wiring check | both from memory of the same sheets: **an independent reading of each sheet is still to do** |
| A footprint does not fit its part | KiCad library footprints for standard packages; own footprints for the socket, the N64 edge, the USB-C, the buck-boost and an inductor | **not re-checked for v2** |
| The cartridge socket's pads do not meet a real socket's tails | none possible on the PC | **open: no socket has been measured** |
| The socket or the N64 edge is mirrored or back to front | orientation reasoned from the SNESdev and N64brew pin-outs and SummerCart64's board (2026-09-30); the wiring check catches a mirrored net list but not a mirrored footprint | **to be confirmed a second time from the sources** |
| A supply gives the wrong voltage or cannot carry the load | divider values recomputed; budget from the console's 3.3 V | **review still to do** |
| The level shifters misbehave while the cartridge's 5 V is off | their B side is on the switched 5 V | **to be settled from the data sheet** |
| The board breaks PCBWay's rules | the board's own rules are 0.1 mm spacing, 0.125 mm ring; PCBWay's are to be confirmed with the quote | open |

## What the wiring check covers

It reads three things that are made independently of one another: the board file (which pad is on which net), the FPGA constraints (which port is on which ball), and the two connector tables that v1 drew from other people's working boards (OpenSFC, sd2snes and the Sanni reader for the SNES socket; SummerCart64 and ModRetro's schematics for the N64 edge). A port passes when its ball's net reaches the connector pin that carries that signal on a real console, through a level-shifter channel that points the right way and is switched by the right port.

- 43 outputs to the cartridge, D0 to D7 both ways, 5 inputs from it, 3 open-drain pulls and PROGRAMN.
- 27 signals on the N64 edge, its supply fingers and the unused 12 V fingers.
- The flash on the configuration balls, the mode pins, the clock, the reset supervisor, the USB pins and their resistors, the telemetry converter and the test-current divider of the cartridge check, the cartridge sound input.
- Every supply and ground ball of the FPGA.

`--negative` makes 16 deliberate mistakes one at a time, among them the socket's rows exchanged, the socket mirrored, a byte pointing the wrong way and two ports exchanged in the constraints. Each is caught.

It says nothing about voltages, timing, footprints or whether the logic works.

## Found on the way

- **The status LED is wired to light when its FPGA pin is low**, and the logic drives the pin high while a game runs. The LED would be on when idle and off in a game. A matter of the logic, to be corrected there.
- **The cartridge's control lines have no pull resistors on the 5 V side.** While the cartridge has power and the level shifters are released, `/RD`, `/WR` and the address lines float. The logic holds `/RESET` low in those moments, which protects battery RAM on boards that gate it with `/RESET`. To be looked at with the power-off behaviour of the level shifters.
