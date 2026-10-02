# A real game through the simulated SN64

**Status (2026-10-02): simulation only. A real cartridge image boots, draws, plays sound and takes controller input through the SN64's logic, with the picture read out through the N64 cartridge port. 38 of 38 judged test programs pass. The same game also runs through a model of the board itself: [board-simulation.md](board-simulation.md). Nothing here has run on hardware.**

## Why

Until this day every test of the FPGA logic used a hand-written stand-in cartridge of a few dozen bytes. No real program had ever run through the design. The owner asked for a test with a game before any board is ordered: "I'm worried that I'll have PCBWay create this and it might be a paperweight."

## What the bench is

[tb_game.sv](../../fpga/tests/tb_game.sv) is the whole-system bench ([tb_system.sv](../../fpga/tests/tb_system.sv)) with two things changed.

- **A cartridge that holds a real image.** The image file is read into a ROM model. The model answers `/ROMSEL` and `/RD` the way a cartridge board is wired: LoROM without A15, HiROM with A0 to A21, battery RAM where that kind of board has it, and a key CIC if asked for. It drives D0 to D7 only while it is selected and `/RD` is low.
- **An N64 that does what the boot program does.** It identifies the SN64, writes a controller image and asks for the cartridge, as Play does. Then, for every picture, it writes the controller image and COMMIT and fetches the picture through the cartridge port in four parts, each when `FRAME_STATUS` says its lines are finished, at the fast timing the boot program sets, one address latch a line. What it fetched is written out as a picture. The sound is taken where it enters the frame window.

Everything between those two is the real logic: `sn64_top` with the SNES core, the cartridge bridge, the power sequencer, the CIC lock, the header probe, the frame window and the N64 endpoint.

[run_game.py](../../fpga/tools/run_game.py) builds the bench, reads the image's own header for the board kind, the battery RAM and the region, runs it, and turns the output into PNG pictures, a sheet and a WAV file. [run_game_suite.py](../../fpga/tools/run_game_suite.py) runs a folder of test programs several at a time and reads the PASS and FAIL words off the instruction tests' screens.

No image is in this repository. The runs below used the owner's own cartridge image and free test programs fetched for the purpose; both stay on the owner's PC under `build/`, and pictures of commercial games are not committed.

## What it found on its first run

**The cartridge bridge drove the data lines against the cartridge during DMA.**

- A game loads its graphics with DMA: the console reads a byte from the cartridge (`/RD` low) and writes it to the picture chip in the same cycle (`/PAWR` low). The byte on the bus is the cartridge's.
- The bridge drove D0 to D7 toward the cartridge whenever any write strobe was low. During such a copy the FPGA and the cartridge ROM both drove the bus, and the picture chip received the FPGA's own stale byte.
- The first test program came up black, with 507,585 clocks of two drivers on the bus in its first four pictures.
- This was the open item "DMA matrix" in [physical-cartridge-bridge.md](physical-cartridge-bridge.md): known to be unfinished, and now shown with a real program.

**Fix** ([sn64_cart_bridge.sv](../../fpga/rtl/sn64_cart_bridge.sv)): whoever answers the read owns the bus. `/RD` names an A-side source: the cartridge, unless WRAM answers. `/PARD` names a B-side source: a console device at `$2100` to `$2183`, or something on the cartridge side above that. A write strobe makes the FPGA drive only when the source is the console's. After the fix the same program draws its text and the bench counts no clock with two drivers.

On a board this fault would have meant garbled or black pictures in nearly every game and two outputs fighting on eight lines. It is in the FPGA's logic, so it could also have been corrected after a board was built, through the USB port.

## Results

| Image | What happened |
|---|---|
| Hello World test program, 32 KiB LoROM | Black before the fix. After it: the text is on the screen. |
| The owner's Super Mario World cartridge image, 512 KiB LoROM with 2 KiB battery RAM, NTSC key CIC | 660 pictures. Region decided as NTSC by the key CIC. The opening screen, the title screen, the file menu after a Start press, "1 player game" after another, the fade into the first scene with the mosaic effect, and the first scene with its status line and sprites. Title music in the sound output. No picture missed or fetched twice by the N64 side, no clock with two drivers on D0 to D7. |
| 65816 instruction test "ADC" | All eight rows of its last table say PASS. |
| The set of 49 free test programs | 38 judged, 38 pass; 11 looked at. See "The test set" below. |
| The same two images through the board's own wiring | [board-simulation.md](board-simulation.md) |
| Super Mario World again on 2026-10-02, after the USB logic was taken out of the FPGA | The same 660 pictures: all 33 that are written are identical file for file, and the sound is identical byte for byte. The counts are the same too: 18,347,598 ROM reads, 351,408 sound samples. |

Controller input reached the game: the Start and A presses in the run came from the N64 side's controller image through the mailbox and the SNES controller port logic.

### Speed

About 1.4 seconds of computing for one game picture on the owner's PC, one run on one processor core. The Super Mario World run took 15 minutes for 11 seconds of game. Several runs can go at once.

### What the sound showed

With a program that makes no sound, the output is not silence. It is a repeating pattern of five values between -64 and +64, about 54 dB below full scale, repeating every seven samples. It comes from the cartridge sound input: its converter in the FPGA settles into a small repeating pattern when nothing is connected, and the mixer adds that to every game. To be fixed in the logic by leaving the cartridge input out of the mix while it carries nothing. Not a fault that stops anything from working.

## The test set

Peter Lemon's public collection of SNES test programs ([github.com/PeterLemon/SNES](https://github.com/PeterLemon/SNES), commit `350b394e`): 23 tests of the 65816's instructions and 7 of the SPC700's, which print a table of PASS or FAIL; memory-mapping tests for LoROM and HiROM, slow and fast; picture tests (background modes, mode 7, HDMA, windows, mosaic); sound tests; a controller test; one small game. 49 files, 2.6 MB, fetched with the owner's yes on 2026-10-01 and kept out of the repository.

Each program ran alone through the logic for 150 to 420 pictures. The set was run on 2026-10-01 and again on 2026-10-02 with the final logic: the same results, and every program's last picture the same pixel for pixel.

| Group | Programs | How it is judged | Result |
|---|---|---|---|
| 65816 instruction tests | 23 | the words PASS and FAIL are read off the last picture, pixel for pixel in the tests' own font: at least one PASS and no FAIL | **23 pass** |
| SPC700 instruction tests | 7 | the same | **7 pass** |
| Memory map: LoROM and HiROM, slow and fast, and work RAM | 5 | the same; these print PASSED | **5 pass** |
| Sound programs | 2 | the sound that reaches the N64 side is well above the idle pattern | **2 pass** (peaks 13,252 and 4,196 of 32,767) |
| Controller test | 1 | run with a button held from picture 60: the picture must change with it | **pass** |
| Picture programs: 2, 4 and 8 bit backgrounds, mode 7 rotation, two HDMA effects, mosaic, colour rings, windows | 9 | looked at | all nine show what the program draws |
| Hello World, and one small free game | 2 | looked at | text on the screen; the game reaches its first screen |

No picture was missed or fetched twice by the N64 side in any run, and no run had two drivers on the data lines.

The "MSC" instruction test ends on STP, which stops the processor until a reset; its last row stays empty, as its own screen says. The two sound programs and the controller program show a black picture by design.

What the set does not cover: enhancement chips, the more unusual picture modes, timing-sensitive games. It is a floor, not a guarantee.

## How to run it

```powershell
. '<oss-cad-suite>/environment.ps1'
$env:PATH = '<w64devkit>/bin;' + $env:PATH
python fpga/tools/run_game.py --build-dir C:/sn64-build/game --rom <image.sfc> --key ntsc --frames 600 --shot 30 --pad <script>
python fpga/tools/run_game_suite.py --build-dir C:/sn64-build/game --roms <folder of test programs> --jobs 10
```

A controller script is a text file with lines `<first picture> <last picture> <mask in hex>`. The mask is the mailbox's controller image: bit 0 B, then Y, Select, Start, Up, Down, Left, Right, A, X, L, R. `360 366 0008` holds Start from picture 360 to 366.

The core must be prepared first (`fpga/tools/evaluate.py` has run once, and `fpga/tools/build_cic.py`).

## What this does and does not show

- **It shows** that the logic, as written, runs real programs through the whole chain: cartridge bus, SNES core, picture and sound into the frame window, the N64 side reading them out in time, controller input going the other way.
- **It does not show** that the board is right. The bench connects the logic's ports straight to the models. Whether each port reaches the right pin through the level shifters is checked separately ([board-verification.md](board-verification.md)).
- **It has no voltages and no real timing.** Level shifters, the socket, trace lengths and a real cartridge's speed are not in it. The timing check of the routed FPGA covers the inside of the chip only.
- **The N64 is a model** that repeats the boot program's bus traffic. The boot program itself runs in the ares emulator ([n64-bootstrap.md](n64-bootstrap.md)), but the two have not been joined: no emulator has an SN64 behind its cartridge port.
- **The power-on timers are shortened** in the bench, as in tb_system.sv, and the cartridge check before 5 V is not built in at this level.
- **One game and a set of test programs are not every game.** Special chips in cartridges are not modelled at all.
