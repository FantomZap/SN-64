# Frame lock: one Super NES picture for every console picture

**Status (2026-10-01): written and simulated. Nothing here has run on a console, a television or an M64.** FPGA logic, the menu program's part and the tests are in the repository; the routed FPGA meets timing. Every number marked "assumed" below is waiting for a measurement on real hardware.

## The problem

A Super NES and a Nintendo 64 do not make pictures at the same rate.

| Machine | Pictures a second | Why |
|---|---|---|
| Super NES, 60 Hz | 60.0988 | 21,477,272.7 Hz master clock, 357,366 clocks a picture (262 lines of 1364, less the short line on every other picture) |
| Nintendo 64, 60 Hz, 240-line picture | 59.8261 | 48,681,818 Hz video clock, 263 lines of 3094 clocks |
| Super NES, 50 Hz | 50.0070 (50.0093 as the SN64 makes its clock) | 312 lines of 1364 |
| Nintendo 64, 50 Hz | 49.9201 | 49,656,530 Hz video clock, 313 lines of 3178 clocks plus the leap line |

Left alone, the game makes one picture more than the console can show about every 3.7 seconds (60 Hz) or every 11 seconds (50 Hz). That picture is dropped, which shows as a hitch in smooth scrolling. The sound has the same trouble on a smaller scale: the console's sound output runs at a whole division of its video clock and is never exactly 32,000 Hz.

The frame lengths are from [clock-plan.md](clock-plan.md) (measured on the core in simulation) and from the console's video registers as libdragon sets them (see Sources).

## What the owner decided (2026-10-01)

1. The logos and the menu run on the console's own, unchanged picture timing. The timing changes only when a game is put on the screen, and goes back when the game display is left.
2. A **compatibility mode** in the menu, for a console or display that does not take the changed timing. It is off after every start-up. Choosing it shows a confirmation screen that states how much slower the game then runs. It stays in until the owner has play-tested the normal mode on real hardware.

No console is modified. Everything is ordinary software writing registers the console's own programs write.

## How it works

Two things are needed to show exactly one game picture per console picture: the two rates have to be made nearly equal, and then held exactly equal.

**Making them nearly equal** is done one of two ways:

- **Normal mode.** While a game is shown, the console's picture timing is given the Super NES's shape: its line count (262 at 60 Hz, 312 at 50 Hz) and a line length chosen so the console ends up a few hundredths of a percent *slower* than the game.
- **Compatibility mode.** The console's timing is not touched. The whole difference is taken from the game.

**Holding them equal** is always done on the game's side. The FPGA can slow the Super NES's clock in very fine steps (PACE, below). Once per console picture the menu program reads how far the Super NES is into its picture (FRAME_PHASE) and adjusts the pace so that position stays put. The game follows the console; the console never follows the game.

The game can only be slowed, never sped up. That is why normal mode leaves the console slightly slower than the game: there must always be something to take away.

| Console and game | Mode | Console shows | Game slowed by | In 30 minutes |
|---|---|---|---|---|
| 60 Hz console, 60 Hz game | normal | 60.0739 Hz | 0.04 % | under 1 s |
| 60 Hz console, 60 Hz game | compatibility | 59.8261 Hz (its own) | 0.45 % | 8 s |
| 50 Hz console, 50 Hz game | normal | 49.9860 Hz | 0.05 % | under 1 s |
| 50 Hz console, 50 Hz game | compatibility | 49.9201 Hz (its own) | 0.18 % | 3 s |
| Brazilian 60 Hz console, 60 Hz game | normal | 60.0856 Hz | 0.02 % | under 1 s |
| Brazilian 60 Hz console, 60 Hz game | compatibility | 59.8371 Hz (its own) | 0.44 % | 8 s |

Normal mode is not exact: the game runs 0.04 % slow. That is one tenth of compatibility mode's slowdown. For scale, a crystal of ordinary tolerance (50 ppm) is itself off by up to 0.005 %. How to make it exact is under "Not built" below.

A 50 Hz game on a 60 Hz console, or the other way round, cannot be locked. Those run as before: pictures are repeated or dropped, the console's timing is not changed, and the game runs at full speed.

## The FPGA's part

### Slowing the game: `sn64_clock_pace`

[sn64_clock_pace.sv](../../fpga/rtl/sn64_clock_pace.sv) makes the Super NES master clock by halving a clock of twice the frequency. Now and then it holds one low phase for one more period of the doubled clock, so that one master period is 3 half-periods long instead of 2.

- Nothing is gated and no pulse is ever shortened. The clock is a flip-flop's output. Its high phase is always the same length; its low phase is one or two units. Everything on that clock, and the clock pin of the cartridge, sees a slightly slower clock and nothing else.
- `PACE` is how many of every 1,048,576 master periods are stretched, spread evenly. One count is 0.477 ppm. The maximum, 65,535, is 3.03 % slower.
- A first idea, switching the clock off for single pulses with the FPGA's clock gate, was dropped. The gate's timing against its enable is not something the open tools analyse, and a pulse cut short on this clock would corrupt the game.

The board's two game PLLs now make the doubled clock:

| Region | PLL setting from 27 MHz | Doubled clock | Master clock | Against the real console |
|---|---|---|---|---|
| NTSC | / 2, x 5, x 7, / 11 | 42.954545 MHz | 21.477273 MHz | exact |
| PAL | / 5, x 2, x 67, / 17 | 42.564706 MHz | 21.282353 MHz | +46 ppm |

PAL was -27 ppm before. No setting of these dividers gives a doubled PAL clock closer than +46 ppm. Both are inside what the board's own oscillator may be off by (50 ppm).

### Three mailbox words

| Offset | Name | Direction | Meaning |
|---|---|---|---|
| 0x0C | FEATURES | read | bit 0: this build can pace the clock; bit 1: FRAME_PHASE exists. Older builds read 0 |
| 0x24 | FRAME_PHASE | read | bits 10:0: where the Super NES is in its picture, in quarter lines (341 master clocks) since the first visible line began; 0x7FF until the first picture. Bits 15:11: pictures started, counted modulo 32, stepping as the position returns to 0 |
| 0x26 | PACE | write, reads back | the pace; cleared by a console reset |

A 32-bit read at 0x24 gives both words of the lock at once. A 32-bit write there sets PACE; its upper half falls on the read-only FRAME_PHASE.

## The menu program's part

All of the arithmetic is in pure C modules that are tested on the PC. `main.c` only touches registers.

### The plan: `sn64_framelock.c`

When the game display starts, the program reads the console's three timing registers back (so it works from what the console really runs, not from a table), and works out:

- the Super NES-shaped timing for normal mode: lines = the game's, line length = the shortest whole number of video clocks that leaves the console at least 200 ppm slower than the game (**assumed margin**: the board's oscillator is +-50 ppm, a console's crystal is taken as no worse than +-100 ppm);
- the pace that makes game and console equal on paper (871 in normal mode on a 60 Hz console, 9,560 in compatibility mode);
- the sound output's divider and the resampler's step.

In normal mode it then writes the three registers during the vertical blanking, as libdragon's own mode change does. On a 60 Hz console that is 262 lines of 3093 video clocks in place of 263 lines of 3094. Leaving the game display puts libdragon's standard values back and sets PACE to 0.

### The loop

Once per console picture, right after the console's vertical interrupt:

1. Read FRAME_PHASE and the processor's tick counter; an interrupt handler has noted the tick of the vertical interrupt. From the two, work out where the Super NES was at the interrupt.
2. Compare with the target: 270 lines after the Super NES's picture began (**assumed**: 224 lines are drawn, the last quarter takes 29 lines to fetch, the rest is margin before the console swaps pictures).
3. Far off: slow the game as much as PACE allows until the target comes round (or let it catch up, if that is quicker). Near: a proportional and integral control on the error.

In the model the lock is reached within 111 pictures (about 2 seconds) from any starting position, and afterwards the position stays within 2 lines of the target with the clocks up to 150 ppm off and a jittery measurement.

If a console turns out quicker than the game even at full speed (its clock further off than the margin allows), the loop lets the game run at full speed and fall behind at the rate the clocks dictate. A picture is then shown twice now and then, and no more often than that. The service screen shows it as "console too quick".

### Order of work in one picture

1. Wait for the console's vertical interrupt (libdragon's picture swap).
2. Frame lock (above).
3. Sound: fetch what the game has made, fit it, hand a block to the console.
4. Fetch the first quarter of the picture as soon as the Super NES has drawn it.
5. Controllers: by now the console has read them since its interrupt; the Super NES reads the result at the end of this same picture.
6. Fetch the other three quarters, each as soon as it is drawn.
7. Hand the picture over; it is shown at the next vertical interrupt.

A fetch that sees no progress from the Super NES for 40 ms gives the picture up, so a game whose clock stops (a power fault) no longer hangs the program.

### Sound: `sn64_resample.c`, `sn64_audioout.c`

The old loop padded every block with silence and would have buzzed ([n64-bootstrap.md](n64-bootstrap.md), item 9 of "Still open"). It is replaced.

- The program drives the console's sound output directly, one block per picture. libdragon's own queue works in 40 ms blocks; this keeps the sound about one picture and 12 ms behind the game, close to the picture's own delay.
- The output's divider is chosen so the console plays almost exactly what the game makes in a picture (1522 in normal mode on a 60 Hz console, 1528 in compatibility mode).
- What is left of the difference, and whatever the two clocks are off by, is taken up by a four-point cubic resampler whose step is a hair off 1.0. The step is nudged, by at most 0.5 %, so that the sound waiting in the console's output stays near 12 ms (**assumed** target).
- The console's sound output has two places: the block that plays and one behind it. Blocks are kept to about one picture each, and nothing is added while the playing block would by itself last past the next picture. A first version sent everything it had; the model showed that one late picture then left a long block playing with the next one stuck behind it, and the output ran dry a picture later.
- A block never ends on an 8 KiB address boundary: the console's sound DMA then plays the wrong memory (documented hardware fault). The pairs held back go out with the next block.

In compatibility mode the game's sound is lower in pitch by the same 0.45 %, which is under a tenth of a semitone.

### The menu

![Mock-up of the compatibility mode screens](img/compat-screens.png)

The picture is drawn by `firmware/bootstrap/tools/mock_screens.py`; the confirmation's text and figures come from the code under test. It is not a capture.

- One new row on the main menu, "Compatibility mode: off". Choosing it shows the confirmation with the slowdown for this console (0.45 % on a 60 Hz console, 0.18 % on a 50 Hz one). A turns it on, B cancels. Choosing it again turns it off without asking.
- While it is on, the main menu says so in red.
- It is forgotten when the console is reset or switched off. The menu has nowhere to keep settings yet ([menu-ideas.md](menu-ideas.md)).
- If the picture is lost when a game starts: hold Z+L+R for a second (the menu hotkey, which works blind) or reset the console, then turn compatibility mode on.
- On an FPGA build without the pace the row answers "Not in this SN64 build".
- Service screen (Status / diagnostics, then Z): the lock's state, how much the game is being slowed, the position error and how many pictures were lost, as they were when a game was last shown. C-up switches on a one-line readout above the game picture for bring-up.

## Why the game follows the console

The other way round, the console following the game, would leave the game at exact speed. It needs the console's picture length adjusted by a few video clocks every picture. The console has a register for that (the leap line, which 50 Hz consoles use to hit their colour standard), but the N64brew documentation says values that *shorten* the line cause "a variety of undesired side effects" in the sync signal. Lengthening is clean. So an exact mode is possible in principle with a shorter line and a leap that only ever lengthens, but it means rewriting a video register every picture, which is one more thing an M64 or an upscaler might not take.

Slowing the game instead means the console's registers are written once when the game starts and never again. That is the least a display has to put up with, and it is the same mechanism compatibility mode needs anyway.

## Not built

- **Exact speed.** Steering the console with the leap line, as above. Worth doing only if the 0.04 % matters to someone and the consoles measured take it.
- **A narrower margin.** If measured consoles sit within 60 ppm of the board, the line can be one clock shorter (3092 on a 60 Hz console) and the slowdown falls from 0.04 % to 0.01 %.
- **Interlaced games.** A Super NES in interlaced mode makes 59.98 pictures a second, slower than normal mode's console. The loop then coasts and a picture is shown twice about every 11 seconds. Compatibility mode locks it. Few games use the mode.
- **Keeping the setting.** Needs somewhere to store it.
- **Racing the beam.** With the lock holding the two pictures a fixed distance apart, the picture could be fetched just ahead of the console's own scan instead of a picture early. That would cut the delay from about 18 ms (estimated, not measured) to a few.

## Assumed, until measured

| Assumption | Value | Where |
|---|---|---|
| Margin of the Super NES-shaped timing below the game's rate | 200 ppm | `SN64_LOCK_MARGIN_PPM` |
| A console's video clock is within | +-100 ppm of nominal | the margin above |
| Position of the Super NES at the console's vertical interrupt | 270 lines into its picture | `SN64_LOCK_TARGET_LINE` |
| Sound waiting in the console's output before a block is added | 12 ms (384 pairs) | `SN64_AOUT_TARGET_PAIRS` |
| The console's timing registers read back what was written | yes | N64brew lists them as read/write |
| A television, an upscaler and an M64 accept 262 lines of 3093 clocks | unknown | the reason compatibility mode exists |
| An M64's processor tick counter and video clock behave as a Nintendo 64's | unknown | the loop measures the tick rate itself, so a different rate does no harm |

## Evidence

Simulated or computed on the PC. Not hardware.

| What | Result |
|---|---|
| `tb_clock_pace` | 5.3 million master periods; the shortest phase is exactly one unit; rates 1, 871, 9560, 30000, 65535 stretch exactly that many of 2^20 periods, evenly spread; rate 0 is a plain halving; stopping and restarting the doubled clock makes no short pulse |
| `tb_frame_window` | FRAME_PHASE reads 0x7FF before the first picture and follows the generator at 7 points through the visible lines, the blanking and the wrap |
| `tb_n64_endpoint` | FEATURES, PACE written through the pair at 0x24 and read back beside FRAME_PHASE, cleared by a console reset |
| `tb_system` (whole design, real core, NTSC and PAL) | FRAME_PHASE advances as time passes; PACE 0xFFFF written through the mailbox slows the Super NES clock by 3.03 % (13,359 clocks counted, 13,358.6 expected) and 0 restores it |
| Fault builds | rate ignored; position never restarted; FRAME_PHASE and PACE swapped: all three rejected |
| Whole FPGA suite | 88 runs pass, 24 of them fault runs that must fail |
| Routed design, speed grade 8 | Super NES clock 36.2 MHz against 21.5 needed, doubled clock 345 against 43, host 100 against 62; 13,488 flip-flops (140 more, as added), 44 % of the logic. The logic count rose from 41 %: the mapper's result for the big core module alone swings by 1,400 cells between runs with no change in it (seen in a module-by-module comparison of before and after), so the rise is not the 140 flip-flops' logic |
| `test_framelock` (120 checks) | timing and pace for every console and region; the control loop from every start position, clocks +-150 ppm, jittery measurement: locks within 111 pictures, stays within 2 lines, never loses a picture; a console 50 ppm too quick loses 7 pictures in 2,000 s where the clocks dictate 6 |
| `test_resample` (34 checks) | step 1.0 passes samples unchanged; pieces of any size give identical output; tones at 1, 4 and 8 kHz within 0.02 %, 0.9 % and 9.3 % of the ideal curve; integer arithmetic within 2 counts of floating point at full scale |
| `test_audioout` (36 checks) | against a model of the console's sound output: every pair played in order, left and right together, never dry, with clocks +-300 ppm, hand-over +-1 ms and one picture in twenty up to 10 ms late; no block ends on an 8 KiB boundary; recovers from a missed picture and from a stalled output |
| Fault builds of the three | wrong sign in the loop; lost carry in the resampler; lost hold-back pairs in the queue: all rejected |
| ROM and endpoint co-simulation | the lock's register traffic (FEATURES, the FRAME_PHASE and PACE pair) arrives as written |

The resampler's 9 % at 8 kHz is its treble loss between samples: a four-point curve is about 1 dB down at 8 kHz when the output falls midway between two input samples, and not at all when it falls on one. As the step is a hair off 1.0 that level drifts slowly up and down. Below 4 kHz it is under 0.1 dB. Not listened to yet; a longer filter is the remedy if it is heard.

The menu program is 147,456 bytes now and no longer fits a 128 KiB window (it was 357 bytes over with the frame lock, and is 2 KB over since the credits roll). `ROM_ADDR_BITS` is 17 in the build files, as on the v2 board, whose window is 256 KiB with about 129 KB to spare.

## To check on real hardware

| Check | N64 on a CRT | N64 on a flat TV or upscaler | M64 over HDMI |
|---|---|---|---|
| Normal mode: picture steady, right size, colour right | | | |
| Normal mode: service screen says "locked"; slowdown reads near 0.04 % | | | |
| Normal mode: smooth scrolling without a hitch for 5 minutes; "lost" stays 0 | | | |
| Sound: no buzz, clicks or dropouts | | | |
| Compatibility mode: the same four | | | |
| Slowdown reading with the lock held (it measures how far the two clocks really are apart) | | | |
| Return to the menu: picture comes back on the console's own timing | | | |

The slowdown reading is the useful number: it says whether the 200 ppm margin is too wide or too narrow for real consoles.

## Sources

- N64brew wiki, [Video Interface](https://n64brew.dev/wiki/Video_Interface): V_TOTAL, H_TOTAL, the leap pattern and H_TOTAL_LEAP, their units, that they are read/write, and the side effects of a shortened leap line. Read 2026-10-01.
- N64brew wiki, [Audio Interface](https://n64brew.dev/wiki/Audio_Interface): the sound registers, the two-block queue and the 8 KiB boundary fault. Read 2026-10-01.
- libdragon, commit `e356bf3f56f7afbf7e5246329562f145965cfdfc`: `src/vi.h` (the standard register values per video standard), `src/display.c` (the timing is written once at mode set), `src/audio.c` (the video clock frequencies, the bit-clock rule).
- Lattice ECP5 and ECP5-5G Family Data Sheet FPGA-DS-02012-3.4, SHA-256 `26570f8bb2b800123120829cacd75d818d7a985d573797610521b5bda2e293c3`: section 2.5.1, the clock gate sits before the clock select (why a gate was not used).
- [clock-plan.md](clock-plan.md): the Super NES frame lengths as measured on the core.
