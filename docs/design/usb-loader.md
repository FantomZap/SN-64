# The USB loader chip

**Status (2026-10-02): drawn, placed and routed on the v2 board, and checked against the chip's data
sheet and the source of the PC program that drives it. Nothing here has run on hardware: no board
exists yet.**

Owner, 2026-10-02: "Add back just the usb loader chip and put the usb on the right side of the cart",
and of the USB logic inside the FPGA: "no i want it clean so remove it".

## Why it is there

On v2 the USB port was logic inside the FPGA. A blank FPGA has no logic, so a blank board had
nothing that could answer the PC, and could not be given its first load over USB
([board-verification.md](board-verification.md)). The owner's rule is that the side USB-C port loads
the board from blank, with no console.

The loader chip sits between the USB-C socket and the FPGA's JTAG port. Lattice builds that port
into the FPGA; it works with nothing loaded. The PC talks USB to the chip, and the chip moves four
wires.

```
PC  --USB-->  FT231X (U13)  --TCK, TMS, TDI, TDO-->  FPGA JTAG port  -->  configuration flash
```

The same way is used for every later update and for recovery from a bad image. The FPGA's own USB
device is gone from the logic (see "What went away").

## The chip and how the PC drives it

FTDI **FT231XS** (SSOP-20, order code FT231XS-R, LCSC C132160: 3,714 in stock on 2026-10-02), as
it comes from the factory. It is the loader chip of the open ULX3S board, and SN64 joins it to the
FPGA the same way, so the PC program needs no change and the chip needs no programming of its own.

| JTAG | Chip pin | Pin number | FPGA ball |
|---|---|---|---|
| TCK | DSR# | 7 | T5 |
| TMS | DCD# | 8 | U5 |
| TDI | RI# | 5 | R5 |
| TDO | CTS# | 9 | V4 |

Where each column comes from:

| What | Source |
|---|---|
| Which chip pin is which JTAG line | openFPGALoader `src/board.hpp`, commit `676e53ec73d2261c974d610b7cf0693117c8d2ef`: board entry `ulx3s`, cable `ft231X`, pins in the order TMS, TCK, TDI, TDO = DCD, DSR, RI, CTS |
| The same, on a working board | ULX3S `usb.sch`, commit `6a92cec6b177191c5b0f80e260013a1f8ec147dd` (emard/ulx3s) |
| Pin numbers of the chip | FTDI data sheet FT_000565 version 1.2, tables 3.5 and 3.6 (SSOP-20) |
| JTAG balls of the FPGA | Lattice pin-out table for the ECP5U-85, CABGA381 |
| The chip's USB identity | the same data sheet, table 8.1: 0403:6015, which is what the cable entry `ft231X` looks for |

The four pins are **inputs** of the chip in its ordinary state (they are the modem status lines of a
serial port). They become outputs only when the PC program switches the chip to bit-bang mode. So a
cable that is merely plugged in does nothing to the FPGA.

openFPGALoader v1.1.1, the version in this project's tool set, lists `ulx3s` with cable `ft231X`.

## The circuit

FTDI's bus-powered circuit (data sheet figure 6.1), which is also what the ULX3S has.

| Part | Value | Job |
|---|---|---|
| U13 | FT231XS-R | the loader chip |
| R19, R20 | 27 Ω | in series with D+ and D− (were 22 Ω to the FPGA) |
| C44, C45 | 47 pF | D+ and D− to ground, on the socket side of the resistors |
| C41 | 100 nF | on the chip's supply pin (VBUS) |
| C42, C43 | 100 nF | on the chip's own 3.3 V output and on its I/O supply pin |
| R41 | 4.7 kΩ | holds TCK low when nothing drives it (Lattice FPGA-TN-02039: the FPGA has no pull of its own on TCK) |

Already there and kept: the USB-C socket J101, the protection part U4, C301 on VBUS, the 5.1 kΩ
resistors on CC1 and CC2, the pull-ups on TMS, TDI and TDO, and the five JTAG pads.

Rules taken from the data sheet, each with a check in `verify_board_wiring.py`:

- **The chip is fed from the cable.** VCC is on VBUS. With no cable the chip has no supply at all.
- **VCCIO and RESET# are on the chip's own 3.3 V output**, not on the board's 3.3 V. On the board's
  supply the chip's pins would stay powered while its core is not, and could drive the JTAG lines
  while a game runs. A board wired that way is one of the deliberate mistakes the check must catch.
- **D+ and D− go to the chip and to nothing else.** No FPGA ball is on them.
- **The serial pins and the four CBUS pins are not used** and are left open. The chip's inputs have
  pulls of their own.

Left out of FTDI's figure: the ferrite bead in the supply and the 10 nF at the socket. The ULX3S has
neither.

## What went away

| | Before | Now |
|---|---|---|
| USB in the FPGA | a full-speed USB device and flash bridge (TinyFPGA core), two extra clocks | none |
| FPGA balls | 111 | 107 (C9, C12, C13, C14 are free) |
| Logic | 30,820 LUT4, 13,489 flip-flops | 28,955 LUT4, 12,966 flip-flops |
| Clocks in the FPGA | 6 (two for USB) | 4 |
| Flash reader | a copy of SummerCart64's controller with split pins, so two users could share the flash | SummerCart64's controller unmodified |
| Reboot line | the FPGA could pull its own PROGRAMN through the open-drain driver | gone: the PC program asks for the reload through JTAG. The gate is tied off and R201 is gone |
| Parts | R21 (D+ pull-up), R201 | removed |
| Status LED | blinked while a PC talked to the FPGA | lit while a game runs, nothing else |

Files removed: `fpga/rtl/sn64_usb_prog.sv`, `fpga/vendor/tinyfpga-bootloader/`,
`fpga/tools/prepare_usb_core.py`, `fpga/tools/prepare_flash_pads.py`.

## On the board

- The socket J101 is on the board's −X edge, which is the player's right, 32.5 mm above the
  shoulders. The protection part U4 and C301 are beside it on the same face.
- The loader chip and its parts are on the other face, behind the socket.
- The open-drain driver U205 moved 5 mm toward the middle to give the socket's pads room.
- A keep-out under the socket's metal body: no track and no via there on the component side. The
  first routing run had put a JTAG line under it.
- `hardware/sn64-v2/tools/apply_usb_loader_v2.py` carries the change into the routed board. It
  removes only the copper of the nets that changed, and KiCadRoutingTools routes those 19 nets with
  everything else locked ([pcb-routing.md](pcb-routing.md)).

| Path | Length | Note |
|---|---|---|
| USB supply, socket to the input switch | 55 mm (was 104 mm) | 0.4 mm wide; 0.8 mm of it is 0.2 mm wide at a via |
| D+ and D−, socket to the resistors | 3 mm each | |
| Resistors to the chip | 8 and 10 mm | |
| TCK, chip to FPGA | 109 mm | |
| TDI | 119 mm | |
| TDO | 125 mm | |
| TMS | about 85 mm of copper in all | |

The JTAG lines are long because the chip is at the edge and the FPGA's JTAG balls face the other
way. The PC program caps this chip at 3 MHz, and the chip's outputs are slow and weak by default
(4 mA, slow slew), so the length is not expected to matter. It is still long for a JTAG clock: if
loading proves unreliable on a real board, the first thing to try is a lower `--freq`.

## How a blank board is loaded

Not yet done on a board. The commands follow the program's own help text.

1. Plug a USB-C cable from the PC into the SN64. No console is needed: the cable also powers the
   board.
2. Ask the FPGA who it is. This proves the chip, the four wires and the FPGA:

   ```bash
   openFPGALoader -b ulx3s --detect
   ```

3. Write the FPGA image to the flash:

   ```bash
   openFPGALoader -b ulx3s -f --verify sn64_board_top.bit
   ```

4. Write the boot program behind it, at 4 MiB (`FLASH_OFFSET` in `fpga/rtl/sn64_bootrom_flash.sv`):

   ```bash
   openFPGALoader -b ulx3s -f --verify -o 0x400000 --file-type raw sn64_bootstrap.z64
   ```

The program then tells the FPGA to load itself from the flash.

On Windows the program reaches the chip through a generic USB driver, so the chip's driver has to be
changed once with a tool such as Zadig. This is how the program is normally used on Windows; it has
not been tried here.

While a load runs the FPGA is empty, so a console that is on at the time loses the cartridge. Load
with the console off, or switch it off and on afterwards.

## What was checked, and what was not

| Check | Result |
|---|---|
| Schematic rule check | 0 errors |
| Board wiring check | 22 of 22. It follows D+, D− and the four JTAG lines pin by pin, with the pin numbers typed from the data sheet and from the PC program's source |
| Deliberate mistakes | 25 of 25 caught. Five are new: TCK and TMS swapped at the chip, TDI and TDO swapped, the chip's I/O supply on the board's 3.3 V, TCK pulled up, an unused open-drain gate left on PROGRAMN |
| Board rule check | no error, no open connection. After the loader-chip change three open connections and five thermal-relief errors were left, all older than it; they were closed the same day ([pcb-routing.md](pcb-routing.md)) |
| Logic test suite | passes without the USB logic |
| Timing | every clock passes |
| Board-level run | a game boots and plays through the new board ([board-simulation.md](board-simulation.md)) |

Not checked, because no simulation here can:

- **That a real PC loads a real board.** Neither the chip nor the FPGA's JTAG port is in the
  simulation. The first board is the test.
- The USB signals themselves.
- **What the chip's pins do while it has no supply.** In a console, with no cable, three of the four
  JTAG lines are pulled up to 3.3 V and the chip on them is unpowered. The data sheet says the pins
  tolerate 5 V but gives no figure for a chip without supply. The pull-ups limit whatever flows to
  0.7 mA a line, and a JTAG line that sags does nothing while TCK stands still. To measure on the
  first board.
- The protection part U4: its maker's sheet could not be fetched and its pins are as v1 had them.

## Open

- VBUS has 15.8 µF on it by the numbers on the parts (C301, C302, C304, C41). USB allows a device
  10 µF at plug-in. Capacitors of this kind lose a good part of their value at 5 V, and PCs are
  tolerant, but it should be settled before an order. This is older than the loader chip.
- The chip tells the PC it draws at most 90 mA (its factory setting). A board fed only from USB
  draws more. PCs do not usually act on that number. It can be changed in the chip with FTDI's tool.
- The five JTAG pads stay as a second way in.
