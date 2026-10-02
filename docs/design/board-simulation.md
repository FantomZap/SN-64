# A game through the board's own wiring

**Status (2026-10-02): simulation only. The owner's game image boots and plays through a model of the v2 board that is generated from the board file itself: the real FPGA top level on its balls, a model of every part on its pads, the cartridge on the socket's pins and the N64 on the edge fingers. Nothing here has run on hardware.**

## Why

[game-simulation.md](game-simulation.md) runs a game through the FPGA's logic. The cartridge and the N64 are joined to the logic signal by signal there, so a wire on the board that goes to the wrong pin would never show. The owner's worry is the board: "I'm worried that I'll have PCBWay create this and it might be a paperweight."

This run puts the board between them.

| | Logic run ([tb_game.sv](../../fpga/tests/tb_game.sv)) | Board run ([tb_board_game.sv](../../fpga/tests/tb_board_game.sv)) |
|---|---|---|
| Logic under test | `sn64_top` | `sn64_board_top`, the top level that is loaded into the FPGA: PLLs, USB part, supply watcher, boot program in the flash |
| Clocks | made by the bench | one 27 MHz oscillator model; everything else from the logic's own PLL settings |
| Cartridge | joined to the logic's signals | on the socket's 62 pins by number |
| N64 | joined to the logic's signals | on the edge's 50 fingers by number |
| Between them | nothing | the board: every net as the board file has it, the level shifters, the open-drain driver, the flash, the cartridge switch, the supply converter, the pull resistors |
| Start-up | shortened times | the board's real times: 0.45 s from Play to a running game |

## How it is built

[make_board_sim.py](../../hardware/sn64-v2/tools/make_board_sim.py) reads four things and writes the board as a netlist for the simulator.

| It reads | For |
|---|---|
| `build/board-sim/board-nets.json`: every pad's net, written from `sn64-v2.kicad_pcb` by [export_board_nets.py](../../hardware/sn64-v2/tools/export_board_nets.py) | which pad is on which net |
| `fpga/constraints/sn64_board.lpf` | which port of the logic is on which ball, and the pull each pad is given |
| `fpga/rtl/sn64_board_top.sv` | the ports and their directions |
| Lattice's pin-out table | which ball is the partner of each comparator input |

What becomes what:

| On the board | In the simulation |
|---|---|
| A net | a net. Ground and the fixed supplies are constants. The switched cartridge 5 V follows the model of the cartridge switch |
| The FPGA | `sn64_board_top`, each port on the net of its ball |
| SN74ALVC164245, SN74LVC07A, W25Q128, oscillator, TPS3808, TPS2553, TLA2528 | a model of the part with the pin numbers of its maker's data sheet ([board_models.sv](../../fpga/tests/board_models.sv)). The board supplies only which net is on which pad |
| A resistor to a supply | a pull. To the switched 5 V: a pull that follows it |
| A resistor up to 100 ohm between two signals | the two nets are one |
| The dividers on the converter's inputs | worked out from the resistor values on each pin's net and given to the converter model as volts on that pin |
| The cartridge sound network | worked out from its resistors and capacitor: which comparator pin has the feedback, its time constant, the reference level |
| The converter's address pin | the address that wiring gives by the data sheet's table. A wiring the table does not list: the model answers at no address |
| The FPGA's PLLs, clock select and flash clock cell | stand-ins that give the frequencies the logic's own settings ask for ([ecp5_sim_stubs.sv](../../fpga/tests/ecp5_sim_stubs.sv)) |
| Left out | capacitors on supplies, inductors, the converters that make the supplies, the ESD part, the USB socket. No USB cable is plugged in |

The bench then plugs a cartridge into the socket and an N64 onto the edge, using the two connector tables that were drawn from other people's working boards (`hardware/sn64/interfaces/snes-pin-map.csv`, `n64-pin-map.csv`). The cartridge model lives only while it has its 5 V, and its battery RAM takes a write only while `/RESET` is high, as a real cartridge's guard does.

## What a run does

Times from the Super Mario World run, in milliseconds after power-on.

| Time | What happens | Through which parts of the board |
|---|---|---|
| 0.2 | The supervisor lets go of the reset | TPS3808, its pull-up |
| 0.4 | The N64 side reads the SN64's identity | 16 address and data fingers, ALE, read, write |
| 0.43 | The N64 side reads the first and last 32 words of the boot program | the flash on the configuration balls, its clock through the FPGA's own clock pin |
| 0.45 | Play is asked for | |
| 3.9 | The supply converter has answered and every supply reads good. The cartridge check starts | I2C lines, the converter's eight inputs and their dividers |
| 384 | The test current has charged the cartridge rail to 0.69 V: no cartridge in back to front | the converter's pin as an output, the 20 k divider resistor, the rail's capacitors |
| 385 | The cartridge switch closes; 5 V on the socket | TPS2553, its enable and fault lines |
| 389 | The supply reading confirms 5 V. The octets are switched on with the cartridge held in reset | level shifter enables |
| 389 to 456 | The key chip in the cartridge is run and answers; the cartridge's header is read | open-drain driver and pull-ups on the two CIC lines, the level shifters both ways |
| 456 | `/RESET` is let go. The game starts | |
| 456 on | The N64 side fetches every picture through the edge and writes the controller | |

## What it checks on every clock

- Two drivers on the cartridge's data lines at the socket.
- The FPGA and a level shifter driving the same 3.3 V data line.
- The key chip driving a CIC line high while the board holds it low.
- A cartridge that has power and is out of reset while nothing drives its control pins.
- A level shifter byte that is enabled while its 5 V side has no supply (TI's rule for the part).
- The SNES clock running without cartridge power.

At the end it powers the cartridge off the way the menu does and checks the order: `/RESET` low, then the socket pins let go, then the 5 V gone, with no write to the battery RAM on the way down. The status LED must be lit while the game runs.

## Results

| Run | Board | Result |
|---|---|---|
| Hello World test program, 30 pictures | as it was on 2026-10-01 | The text is on the screen: 173 pixels lit, the same count as the logic run. |
| Super Mario World, 240 pictures, key CIC | as it was on 2026-10-01 | Region decided as NTSC by the key chip: 678 rounds of the exchange through the board's open-drain lines, no mismatch. The cartridge's header read through the board. The opening screen at picture 100 with 301 pixels lit, the same count as the logic run. No picture missed, none fetched twice, no two drivers on the data lines. |
| Hello World, 30 pictures | corrected board, corrected logic | Same picture. No loose pins, no byte enabled without its supply. Power-off: `/RESET` low after 2.4 µs, socket pins let go after 1.0 ms, 5 V below 4.5 V after 2.4 ms, no battery RAM write. LED lit in the game, dark after. |
| The cartridge plugged in back to front | corrected board, corrected logic | **Refused**: the cartridge check gives up after its 4.0 s limit with the rail at 0.46 V; fault 0x01; the 5 V is never switched on. |
| A board with the converter's address pin on ground | deliberate mistake | **Refused**: 40 ms after Play the status word still says the converter does not answer; the cartridge is never powered. |
| A board with the socket-to-FPGA byte enabled all the time | deliberate mistake | **Refused** at 1.0 ms: a level shifter byte is enabled while its 5 V side has no supply. |

Pictures of the owner's game are not in this repository.

## What it found

**In the logic. Both are corrected, and the logic's own test suite now has a check and a fault build for each.**

- **The status LED was dark in a game.** The LED sits between 3.3 V and its FPGA pin, so a low pin lights it. The logic drove the pin high for "on". `sn64_board_top.sv` now drives it low.
- **The cartridge's pins were loose for a moment at every start, and let go too early at power-off.**
  - At a start, `/RESET` was released two SNES clocks before the octets that drive `/RD`, `/WR` and the address were switched on. For about 90 ns the cartridge was out of reset with nothing driving its control pins.
  - At power-off, `/RESET` was pulled and the pins were let go in the same instant.
  - Now the pins are held at rest (every strobe inactive, no clock) whenever the cartridge has its 5 V and neither the bridge nor the header read is using them ([sn64_header_probe.sv](../../fpga/rtl/sn64_header_probe.sv), the socket owner part). At power-off `/RESET` is held low for 1 ms with the pins still driven before the 5 V is switched off ([sn64_power_sequencer.sv](../../fpga/rtl/sn64_power_sequencer.sv)).
  - Fault builds `SN64_FAULT_NO_IDLE_DRIVE` and `SN64_FAULT_NO_SHUTDOWN_HOLD` put the old behaviour back; the system bench refuses both.

**On the board, from the data sheets that the part models were written from.** These are in [board-verification.md](board-verification.md): the socket-to-FPGA byte of one level shifter was enabled permanently, and the supply converter's address pin was tied to ground. Both are corrected on the board, and both are now mistakes this run refuses.

## What it cannot show

- **Copper.** The netlist says which pad is on which net. Whether the copper really joins those pads, and nothing else, is KiCad's design-rule check. Six connections are still not routed ([board-verification.md](board-verification.md)).
- **Anything electrical.** The part models are ideal: no voltages, currents, delays or edges. A part that behaves outside its data sheet, a marginal level, a supply that sags: none of that is here.
- **Footprints.** A pad that is on the right net but in the wrong place for the part.
- **The real cartridge and the real console.** Both are models written from the same understanding as the logic.
- **USB.** No host model is plugged in. The USB pins idle as a real board's would.

## Speed

About 0.4 seconds of computing for a millisecond on the board: 3 minutes for the start-up, 7 seconds for each picture, one processor core for each run. The 240-picture run took 31 minutes.

## How to run it

Tool locations for this PC are in `CLAUDE.local.md`. Verilator, a C++ compiler and make must be on `PATH`; `evaluate.py` must have run once.

```bash
"C:/Program Files/KiCad/10.0/bin/python.exe" hardware/sn64-v2/tools/export_board_nets.py
python hardware/sn64-v2/tools/make_board_sim.py
python fpga/tools/run_game.py --board --build-dir <dir without spaces> --rom <image> --key ntsc --frames 240 --shot 20 --bootrom build/n64-bootstrap/sn64_bootstrap.z64
```

A deliberate wiring mistake, which the run must refuse:

```bash
python hardware/sn64-v2/tools/make_board_sim.py --mutate U6.11=GND --out build/board-sim-fault-addr
python fpga/tools/run_game.py --board --board-dir build/board-sim-fault-addr --build-dir <another dir> --rom <image> --frames 1 --start-ms 100
```

`--cartridge 2` plugs the cartridge in back to front: the run must end with `REFUSED`.
