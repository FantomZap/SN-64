# Menu ideas

**Status (2026-10-01): a list to choose from. Nothing here is decided or built, except where a row says so** (the frame lock and the sound rate lock were built later the same day, with a compatibility mode row; then the owner set the main menu to four rows, Play, Controller mapping, Settings and Power off cartridge, asked for a controller mapping screen with pictures that light up, and moved the in-game shortcut to all four C buttons: all built the same day, see [n64-bootstrap.md](n64-bootstrap.md)). The owner asked what features and options the menu should get, and said the menu system could be repackaged. What exists today is in [n64-bootstrap.md](n64-bootstrap.md): a text menu with Play, Controller mapping, Settings (Compatibility mode, Status / diagnostics, Credits) and Power off cartridge, two splash screens before it, and a hidden service screen.

"Needs" says what each idea touches: **menu** is the N64 program only; **FPGA** needs logic and a simulation as well; **board** would need a hardware change, which is the owner's call.

## Picks: the ones worth doing first

| Idea | What the player gets | Needs |
|---|---|---|
| Quick start | Power on, logos, and the game starts by itself. Hold a button during the logos to get the menu instead | menu |
| Cartridge name on the home screen | "SUPER MARIO WORLD, USA" read from the cartridge before it starts, instead of "Play" | FPGA (the header reader already runs; it has to hand the title over) and menu |
| Pause menu in the game | The shortcut (all four C buttons since 2026-10-01) opens a small overlay: Resume, Reset game, Controls, Quit to menu. Today it only jumps back to the menu | menu; Reset game uses the soft reset the FPGA already has |
| Controller mapping editor | Change any button, pick a preset, set the stick threshold. The spec asks for a configurable mapping. **Built 2026-10-01:** any button can be changed and the defaults restored, on a screen with two controller pictures that light up. Presets and the stick threshold are not built, and nothing is kept after power-off | menu |
| Settings that stay | Mapping and options survive power-off, on a Controller Pak if one is in the pad | menu |
| Region choice | Auto, NTSC or PAL. The FPGA has the switch; the menu has no item for it | menu |
| Picture options | Sharp or smooth, full screen or exact pixels, picture position for a CRT | menu |
| About screen | Versions, "SN64 by FantomZap", where the source is, credits for the projects it builds on. **The credits part was built 2026-10-01** as a "Credits" row: `CREDITS.md` as a roll ([n64-bootstrap.md](n64-bootstrap.md)). Versions are still only on the status screens | menu |

## Playing

| Idea | Notes | Needs |
|---|---|---|
| Quick start | As above. Off by choice for people who want the menu first | menu |
| Reset game | Like the reset button on a Super NES; cartridge power stays on, so a flash cartridge keeps its game | menu |
| Pause menu | As above | menu |
| Safe to remove | After Power down: "You can take the cartridge out now" | menu |
| No cartridge | Tell "nothing in the socket" from "cartridge will not start". The cartridge check cannot tell an empty socket; the header reader and the lockout chip can | menu, maybe FPGA |
| Cartridge name and facts | Title, region, memory map, save size from the header | FPGA and menu |
| Start-up hotkeys | Hold Z at power-on for the menu, hold B to skip the logos, and so on | menu |

## Picture and sound

| Idea | Notes | Needs |
|---|---|---|
| Sharp or smooth | The console's own resample filter on or off | menu |
| Full screen or exact pixels | Stretch to 4:3, or integer scale with borders | menu |
| Picture position and size | Nudge left, right, up, down for a CRT; overscan on or off | menu |
| Scanlines | Darken every other line; mostly for the M64's HDMI picture | menu, or FPGA for a better one |
| High-resolution games | Switch to a 512-wide mode when a game uses one. The FPGA already reports it | menu |
| Volume and mute | Simple level for the game's sound | menu |
| Cartridge audio level | Level or mute for sound that comes from the cartridge itself, which the FXPAK Pro uses for MSU-1 music | FPGA and menu |
| Test picture and test tone | Colour bars, a grid, left and right beeps, for setting up a television | menu |

## Controllers

| Idea | Notes | Needs |
|---|---|---|
| Mapping editor and presets | As above | menu |
| Turbo | Auto-fire per button | menu |
| Swap players | Controller 1 and 2 trade places | menu |
| Port 2 device | Pad or mouse. The stick as a Super NES mouse is already on the list for a later update | FPGA and menu |
| Controller test | Live picture of what each pad sends. **Built 2026-10-01 for controller 1:** the mapping screen's two pictures light up. Controllers 2 to 4 are not shown | menu |
| Hotkey choice | Which button combination opens the pause menu. Today it is fixed: all four C buttons (owner, 2026-10-01) | menu |

## Saves

| Idea | Notes | Needs |
|---|---|---|
| Back up a cartridge's save | Copy the cartridge's battery save to a Controller Pak, and put it back. Worth a lot for cartridges whose batteries are dying. The spec lists save integrity | FPGA (read and write the cartridge's save memory while the game is stopped) and menu |
| Save battery warning | Flag a cartridge whose save memory reads empty or changes between two reads | FPGA and menu |
| Settings that stay | As above. A Controller Pak is the place that needs no new hardware | menu |

## Service

| Idea | Notes | Needs |
|---|---|---|
| Plain-language diagnostics | "Cartridge power: 5.02 V, good" instead of hexadecimal words; temperature; which supply is feeding the board | menu; the rail readings need to reach the mailbox, which is FPGA |
| Fault messages | Each power fault gets a sentence and what to do, as the reversed-cartridge screen has | menu |
| Self test | One screen that runs the checks in turn: rails, lockout chip, cartridge check, controllers. Also the base for the factory test the spec asks for | menu, some FPGA |
| Service screen | Exists: the cartridge check's test tools. Other test tools would go here | menu |
| Update mode | "Restart into USB update": the FPGA can already restart itself on command | FPGA and menu |

## Repackaging the menu

The menu is plain text in the console's built-in 8-pixel font. A repackaged one could look like part of the product:

- **Look**: black background as on the splash screens, the SN64 logo small at the top, the four button colours for highlights, a real font in two sizes, panels with rounded corners like the logo's ring.
- **Home screen**: one large Start with the cartridge's name under it, and three or four entries below: Settings, Tools, About.
- **Settings**: Picture, Sound, Controllers, System (region, quick start, logos, hotkey). A Settings sub-menu exists since 2026-10-01 with Compatibility mode, Status / diagnostics and Credits.
- **Tools**: Save backup, Tests, Diagnostics. The service screen stays hidden behind Diagnostics.
- **In the game**: the pause overlay instead of a jump to the full menu.
- **Moving around**: stick or D-pad, A to choose, B back, Start to play from anywhere, and holding a button to confirm anything that removes power.

What limits it:

| Limit | Today | Meaning |
|---|---|---|
| ROM space | The program is 147,456 bytes since 2026-10-01 and no longer fits a 128 KiB window; the v2 board's window is 256 KiB, with about 116 KB free since the controller pictures | A font and graphics fit on v2 |
| Settings storage | None on the board that the menu can write | Controller Pak first; writing the board's flash from the menu would need FPGA work |
| Not yet run on a console | The whole menu has only been compiled and tested on the PC | The first real run may change what is worth polishing |

## What the chosen hardware allows (2026-10-01)

The owner asked which quality functions the hardware already on the v2 board can carry. Numbers are from the routed design (`fpga/reports/v2-board-route.json`, `build/route-board/pnr.log`) and the design notes; nothing here has run on a board.

| Part of the hardware | What is left | What it allows |
|---|---|---|
| FPGA logic (LFE5U-85F) | 41 % used, 59 % free | Cheat codes on the cartridge bus, turbo, the stick as a Super NES mouse, reading and writing a cartridge's save memory, a cartridge checksum test |
| FPGA block memory | 203 of 208 blocks used; 5 free, about 11 KB | Nothing large. No second frame buffer, no save states, no rewind |
| FPGA multipliers, PLLs | 19 of 156 multipliers, 3 of 4 PLLs | Room for filters in logic; one more clock if a function needs it |
| Flash, 16 MB | bitstream and fallback image in the first 4 MB, menu after it; about 12 MB unused | A graphical menu with fonts and pictures, more languages, a game-name list. The menu cannot write it (only USB can), so it is no place for settings without new logic |
| The console itself (N64 or M64 processor, video and sound chips) | all of it during a game; the game runs in the FPGA | Scaling, sharp or smooth, scanlines, picture position, the pause overlay, matching the console's video and sound timing to the Super NES |
| Telemetry ADC | 8 of 8 channels used: 3.3 V from the console, USB 5 V, 5 V system, cartridge 5 V, 1.1 V core, temperature, both USB-C CC lines | Live voltages and temperature in plain words, which supply feeds the board, how much current the USB-C source offers, clear fault messages. There is no current measurement |
| Cartridge bus through the FPGA | full access while the game is stopped | Game name and region from the header, reversed-cartridge check (done), empty-socket detection, save backup and restore, checksum test of the cartridge's contacts |
| USB-C | programs and recovers the flash | Updates without tools; "restart into update" from the menu with one new mailbox bit |
| Clocks | exact NTSC master clock, PAL within 46 ppm; since 2026-10-01 the master can be slowed in 0.5 ppm steps | Each region at its real speed, and the frame lock |
| Controller ports | four pads; Controller Pak, 32 KB | Remapping, turbo, two players, a place to keep settings and save backups |

### Quality functions worth the most

| Function | What it fixes | Needs |
|---|---|---|
| Frame lock | The Super NES makes 60.10 pictures a second, a Nintendo 64 shows 59.83 or 59.94. Unmatched, one picture is dropped about every 4 to 6 seconds, which shows as a hitch in scrolling. **Built 2026-10-01, simulated only** ([frame-lock.md](frame-lock.md)): the console's timing takes the Super NES's shape while a game is shown and the game's clock is held to it; a compatibility mode in the menu leaves the console's timing alone and slows the game by 0.45 % | FPGA and menu; to be tried on a television and on the M64's HDMI output |
| Sound rate lock | The console's sound output is never exactly the game's 32,000 Hz. **Built 2026-10-01, simulated only**: the output's divider is chosen per mode and a cubic resampler takes up the rest | menu |
| Fallback image | A failed update cannot leave the board dead: the FPGA starts the fallback image and USB still works. The flash has the room and the board note already plans it | FPGA build and flash layout |
| Save backup | Copies a cartridge's battery save to a Controller Pak and back | FPGA and menu |
| Health screen | Voltages, temperature, supply and cartridge check in plain words | FPGA (readings into the mailbox) and menu |
| Cartridge contact test | Reads the cartridge's own checksum before starting: "clean the contacts" instead of a crash | FPGA and menu |

### What it cannot do

- **Save states and rewind.** The block memory is full, and the chips inside a real cartridge cannot be snapshotted anyway.
- **512-wide and interlaced pictures at full width.** The one frame buffer is 256 wide. Those modes show at half width in the first version; full width would need memory that is not there or a line-by-line transfer near the cartridge bus's speed limit.
- **Cartridge current.** Only voltages and the switch's trip flag are measured.
- **Settings in the board's own flash**, without new logic for the menu to write it.
- **Anything on a spare FPGA pin.** The spare pins are not brought out on the board.
- **Cartridge sound better than about 10 bits.** That is what the built-in converter for the cartridge's analogue sound pins gives.

### Found while checking: the sound loop as written will crackle

`game_audio()` in the boot program handed the console whole buffers of 1,280 samples (libdragon makes 25 buffers a second at 32 kHz), but the FPGA's sound ring holds 1,024, so every buffer was topped up with at least 257 samples of silence, and the ring overflowed. That is a buzz at 25 Hz, not an occasional click. **Reworked the same day** with the frame lock ([frame-lock.md](frame-lock.md)): the program now drives the console's sound output itself, one block per picture, through a resampler. Not heard on a console yet.
