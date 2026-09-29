# SNES peripheral menu research

This note proposes additions to the SN 64 input and compatibility plan. It does not declare them implemented or silently add physical connectors to the PCB. The same adapter must continue to work on original N64 and M64.

## Current decisions

- Multitap: excluded at the user's request. Do not add multitap menu options, extra-player hardware, or implementation tasks.
- Super Scope and Justifier: undecided. Retain research only; do not assume lightgun support or its hardware is selected.
- SNES Mouse: virtual mouse control from an N64 controller is deferred to a later FPGA/firmware update. Plan for it in the input interface and capacity budget; do not implement or expose it in the initial menu.
- Standard controller mapping remains the default. The other advanced accessories below are research candidates, not selected features.

## Input mode research

| Mode | Purpose | Proposed SN 64 behavior |
|---|---|---|
| Standard controller | Normal SNES games | Default mode with configurable N64-to-SNES button mapping |
| SNES Mouse | Mario Paint and other mouse-aware games | Deferred update: convert an assigned N64 analog stick into relative movement and map two buttons; later expose movement settings and SNES port selection |
| Multitap | Multiplayer games using the SNES multitap protocol | Excluded by user decision |
| Super Scope | Games expecting Nintendo's lightgun interface | Undecided; possible virtual aiming mode remains research only |
| Konami Justifier | Games such as Lethal Enforcers | Undecided; possible distinct lightgun mode remains research only |

The [MiSTer SNES source](https://github.com/MiSTer-devel/SNES_MiSTer/blob/master/SNES.sv) exposes multitap, mouse, Super Scope/Justifier, and Miracle Piano options. The [openFPGA SNES documentation](https://github.com/agg23/openfpga-SNES/blob/master/README.md#controller-options) describes virtual mouse and lightgun inputs. These are implementation references; they do not prove compatibility in SN 64 or automatically transfer the host-side input infrastructure.

The [documented SNES Mouse protocol](https://snes.nesdev.org/wiki/Mouse) provides relative movement, two buttons, and software-visible sensitivity behavior. A virtual mouse mode must implement that device behavior rather than only remapping a gamepad's buttons.

The original retail Mario Paint uses a mouse in controller port 1 and has no standard-gamepad play mode. [Nintendo's original instruction booklet](https://manualzz.com/doc/26101036/nintendo-mario-paint-family-user-manual) specifies the mouse connection and click/drag controls. The proposed SN 64 mode would translate N64 stick movement and buttons into the mouse protocol the unmodified cartridge expects. Suggested bindings are stick for movement, A for left click, B for right click, and configurable movement speed. This is a proposed adapter feature, not a claim that the original game supported a gamepad.

## Menu organization

Use Standard Controller initially. Add the deferred SNES Mouse mode only with its completed and tested update. Keep multitap out of the menu and leave lightgun options undecided. Show settings only for selected and implemented device types. Keep user-selected profiles and an explicit override; do not assume a flashcart exposes a reliable active-game identity.

## Deferred mouse update provisions

The initial design should transport analog-stick axes and button states through the host-to-FPGA controller interface, reserve justified FPGA and image-storage capacity, and support coordinated updates of the FPGA configuration, N64 bootstrap, and menu. The future implementation may change the FPGA bitstream as well as conventional firmware because the SNES mouse's serial device behavior must be reproduced. The proposed input source is the existing N64 controller, so this mode does not require adding a physical mouse connector. Confirm resource margins during component selection and synthesis before relying on an update without a PCB revision.

## Hardware implications to decide before PCB layout

- A virtual mouse can consume the host controller data, but requires protocol and timing work inside SN 64. The same general approach could support virtual aiming if lightgun modes are selected later.
- A real USB mouse, USB controller, or modern lightgun requires an implemented USB host/input path. A service or power-only USB socket would not supply that capability.
- Original SNES controllers/accessories require suitable native sockets or a defined adapter interface, power protection, and protocol support.
- An original [Super Scope depends on CRT scanning and latches SNES beam-position counters](https://snes.nesdev.org/wiki/Super_Scope). Its physical optical behavior is separate from generating virtual lightgun input for HDMI gameplay.

## Additional candidates

| Accessory | Treatment to investigate |
|---|---|
| Miracle Piano | Advanced input mode with actual keyboard/MIDI input requirements |
| NTT Data Keypad | Advanced controller mode with extra key bindings or an on-screen keypad |
| Turbo File Twin | Peripheral storage mode with persistent data and backup/restore behavior |
| Super Game Boy and Super Game Boy 2 | Physical cartridge compatibility tests, including audio, timing, controls, shell support, and SGB2 link-port clearance |
| Sufami Turbo | Physical adapter compatibility tests, including two-slot operation, saves, and mechanical support |
| Satellaview / BS-X | Separate expansion feasibility study covering the base unit, cartridge/memory pack, and content/storage behavior |

[higan's developer documentation](https://higan.readthedocs.io/en/v105/guides/import/) distinguishes the cartridge and expansion cases. [ares' NTT keypad implementation](https://github.com/ares-emulator/ares/blob/master/ares/sfc/controller/ntt-data-keypad/ntt-data-keypad.cpp) and a [Turbo File Twin protocol library](https://gist.github.com/NovaSquirrel/286693b4df3d3a3b44dec2c70487d223) are useful research leads, with explicitly incomplete or unverified details to resolve. [bsnes-plus documentation](https://github.com/devinacker/bsnes-plus/blob/master/bsnes/ui-qt/data/documentation.html) distinguishes Satellaview expansion and broadcast support.

## Validation additions if these modes are selected

- Mouse: device identification, both buttons, relative movement boundaries, game-controlled sensitivity, and correct port behavior.
- Lightguns, only if later selected: device identification, beam-counter timing, calibration, screen edges, off-screen/reload handling, buttons, and applicable multi-gun behavior.
- Physical accessories: connector fit, power draw, electrical levels, latency, reset behavior, and safe connection workflow.
- Storage accessories: persistent contents, write protection, interrupted operations, and backup/restore integrity.

All selected modes need tests on both hosts. Keep evidence for virtual modes and original physical accessory operation separate so compatibility statements remain precise.
