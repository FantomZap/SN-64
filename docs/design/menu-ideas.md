# Menu ideas

**Status (2026-10-01): a list to choose from. Nothing here is decided or built.** The owner asked what features and options the menu should get, and said the menu system could be repackaged. What exists today is in [n64-bootstrap.md](n64-bootstrap.md): a text menu with Start, Controller mapping (view only), Status / diagnostics and Power down, two splash screens before it, and a hidden service screen.

"Needs" says what each idea touches: **menu** is the N64 program only; **FPGA** needs logic and a simulation as well; **board** would need a hardware change, which is the owner's call.

## Picks: the ones worth doing first

| Idea | What the player gets | Needs |
|---|---|---|
| Quick start | Power on, logos, and the game starts by itself. Hold a button during the logos to get the menu instead | menu |
| Cartridge name on the home screen | "SUPER MARIO WORLD, USA" read from the cartridge before it starts, instead of "Start SNES cartridge" | FPGA (the header reader already runs; it has to hand the title over) and menu |
| Pause menu in the game | The hotkey opens a small overlay: Resume, Reset game, Controls, Quit to menu. Today it only jumps back to the menu | menu; Reset game uses the soft reset the FPGA already has |
| Controller mapping editor | Change any button, pick a preset, set the stick threshold. The spec asks for a configurable mapping; today it can only be looked at | menu |
| Settings that stay | Mapping and options survive power-off, on a Controller Pak if one is in the pad | menu |
| Region choice | Auto, NTSC or PAL. The FPGA has the switch; the menu has no item for it | menu |
| Picture options | Sharp or smooth, full screen or exact pixels, picture position for a CRT | menu |
| About screen | Versions, "SN64 by FantomZap", where the source is, credits for the projects it builds on | menu |

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
| Controller test | Live picture of what each pad sends. The mapping screen shows it as numbers today | menu |
| Hotkey choice | Which button combination opens the pause menu | menu |

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
- **Settings**: Picture, Sound, Controllers, System (region, quick start, logos, hotkey).
- **Tools**: Save backup, Tests, Diagnostics. The service screen stays hidden behind Diagnostics.
- **In the game**: the pause overlay instead of a jump to the full menu.
- **Moving around**: stick or D-pad, A to choose, B back, Start to play from anywhere, and holding a button to confirm anything that removes power.

What limits it:

| Limit | Today | Meaning |
|---|---|---|
| ROM space | 5.5 KB left of 128 KiB on the first board's window; the v2 board has a 256 KiB window | A font and graphics fit on v2. The 128 KiB build would have to stay text-only or be dropped |
| Settings storage | None on the board that the menu can write | Controller Pak first; writing the board's flash from the menu would need FPGA work |
| Not yet run on a console | The whole menu has only been compiled and tested on the PC | The first real run may change what is worth polishing |
