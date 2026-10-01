# Controller path: implementation and evidence

Implemented 2026-09-29. This is the first working version of the logic that turns the button images the N64 bootstrap writes into the mailbox into two standard SNES controllers, as seen by the SNES core. It passes a serial-protocol simulation and a whole-console simulation in which an original 65816 diagnostic reads the pads. **It has not run on hardware, it is not yet wired into a top level, and the N64 bootstrap that fills the mailbox does not exist yet.**

## Plain-language summary

A real SNES controller is two tiny shift registers. When the console raises a "latch" wire, the pad photographs its 12 buttons. Each pulse on the "clock" wire then pushes the next button out on the data wire, in a fixed order: B, Y, Select, Start, Up, Down, Left, Right, A, X, L, R. Four more bits (all 0) tell the console "this is a standard pad", and after that the wire reads 1 forever. The data wire is active-low: a pressed button pulls it low.

SN64 has no SNES controllers. The N64 bootstrap reads the N64 controllers, converts them to SNES buttons using a mapping table, and writes one 16-bit word per player into the mailbox. This block plays the part of the two pads: it takes those words and answers the core's latch and clock pulses exactly as the real shift registers would. It works for both ways games read controllers: the automatic read the console hardware does every frame, and the manual bit-by-bit reads some games do themselves.

## Files

| File | Role |
|---|---|
| [fpga/rtl/sn64_snes_joypad.sv](../../fpga/rtl/sn64_snes_joypad.sv) | Two emulated standard pads between the mailbox images and the core's `JOY*` ports |
| [fpga/vendor/snestang-controller/src/controller_adapter.sv](../../fpga/vendor/snestang-controller/src/controller_adapter.sv) | Upstream SNESTang shift-register adapter, unmodified (see provenance) |
| [fpga/vendor/snestang-controller/provenance.json](../../fpga/vendor/snestang-controller/provenance.json), `LICENSE` | Source URL, pinned commit, SHA-256, GPL-3.0 licence |
| [fpga/tests/tb_snes_joypad.sv](../../fpga/tests/tb_snes_joypad.sv) | `tb_snes_joypad` (serial protocol) and `tb_snes_joypad_core` (whole console, define `SN64_JOYPAD_CORE_TEST`) |

## What is reused

`controller_adapter.sv` from SNESTang at the same pinned commit as the core (`5f0ef193…`), fetched from GitHub on 2026-09-29. Its SHA-256 (`104cb3e9…1d13`) matches the copy in the full upstream archive already extracted under `build/`. It is GPL-3.0, the same licence family as SN64 HDL, and is used unmodified. SNESTang's own top level (`snestang_top.v`) uses it to connect DS2, USB and SNES-pad inputs to this same CPU implementation. SN64 has not tested that use on hardware. It is kept in its own vendor directory so the existing `fpga/vendor/snestang/provenance.json` stays untouched. No GPL-2.0-only code is used.

The SN64 wrapper changes three things around it:

| Behaviour | Upstream SNESTang top | SN64 wrapper | Why |
|---|---|---|---|
| ID nibble (bits 12–15) | whatever the caller passes (zero-extended 12-bit sources) | always `0000` (standard pad); mailbox bits 12–15 ignored | A bootstrap bug cannot make the pad claim to be a mouse or another device |
| Second data line `JOYn_DI[1]` | tied `0`, which the core inverts to a constant 1 | held idle high, so it reads 0 | Matches a console with no multitap. With upstream's tie, `$4016`/`$4017` bit 1 read 1 and `$421C`–`$421F` read `$FFFF`, which is the multitap-present signature. SN64-U-05 excludes multitap. |
| Empty port | not modelled | `pad_present[n]=0` holds both lines idle high, so every bit reads 0 with no trailing 1s | Lets a game see player 2 as unplugged when the N64 has no second controller |

## How the core reads controllers

This is from the pinned `cpu.v` and was confirmed in simulation.

| Path | Core behaviour | Pad requirement |
|---|---|---|
| Auto-read (`$4200` bit 0) | During VBlank, `AUTO_JOY_STRB` rises for 32 dots. Then 16 times: sample `~JOYn_DI[0]` into `JOYn_DATA` (shifting left), raise `AUTO_JOY_CLK` in the same step, and drop it 32 dots later. `$4212` bit 0 is busy meanwhile. `JOY3/4` take `~JOYn_DI[1]`. | Bit 0 (B) valid as soon as strobe falls; advance once per clock pulse |
| Result registers | `$4219` = `JOY1_DATA[15:8]` = B Y Sel St U D L R; `$4218` = A X L R 0 0 0 0; `$421B`/`$421A` the same for port 2 | Standard order and ID bits |
| Manual (`$4016`/`$4017`) | Writing `$4016` bit 0 drives `OLD_JOY_STRB`. Reading `$4016` returns `{MDR[7:2], ~DI[1], ~DI[0]}` and pulses `JOY1_CLK` for one CPU cycle, starting at the end of the read. `$4017` returns `{MDR[7:5], 111, ~DI[1], ~DI[0]}` and pulses `JOY2_CLK`. | The CPU latches the data before the pulse. The adapter shifts on the pulse's falling edge, one CPU cycle later. |
| Strobe | One `JOY_STRB` for both ports | Both pads latch together; each shifts only on its own clock |

The core inverts `JOYn_DI`, so the lines are active-low, like a real pad. After 16 bits the adapter shifts in 1s, which drive the line low, and the CPU reads logical 1.

## Mailbox bit layout (JOY1_BUTTONS `0x10`, JOY2_BUTTONS `0x12`)

Active-high (1 = pressed), in the order the pad shifts its bits out. It is the same layout SNESTang uses internally.

| Bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12–15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SNES | B | Y | Select | Start | Up | Down | Left | Right | A | X | L | R | reserved, write 0 (ignored) |

The mailbox resets to `0x0000` (no buttons), so before the bootstrap writes anything the games see two connected pads with nothing pressed.

## Default N64 → SNES mapping

**In force since 2026-10-01 (owner's decision):** every N64 button gives the Super NES button of the same name (A, B, L, R, Start, the D-pad) and Z gives Select. X and Y have no namesake, so the C buttons give the Super NES diamond in its own positions: C-Up X, C-Left Y, C-Down B, C-Right A. The stick also presses the D-pad beyond a threshold. A player can change any row on the boot menu's mapping screen; nothing is kept after power-off yet. Details: [n64-bootstrap.md](n64-bootstrap.md), last section.

The mapping runs in the N64 bootstrap, not the FPGA, so this change touched no logic.

### The first table (2026-09-29), replaced

Kept for the record, with its reasoning. It mapped by position; the owner chose mapping by name. The C buttons are the same in both tables, so the by-position layout of the four Super NES face buttons is still there on the C diamond.

| N64 button | SNES button | Mailbox bit | Rationale |
|---|---|---|---|
| D-pad Up / Down / Left / Right | Up / Down / Left / Right | 4 / 5 / 6 / 7 | Spec §6: D-pad direct |
| Start | Start | 3 | Spec §6 |
| Z | Select | 2 | Spec §6 |
| A | B | 0 | The large main button maps to the SNES main (lower) face button |
| B | Y | 1 | N64 B sits upper-left of N64 A, just as SNES Y sits upper-left of SNES B |
| C-Down | B | 0 | The C buttons form the SNES diamond by position: bottom = B |
| C-Left | Y | 1 | left = Y |
| C-Up | X | 9 | top = X |
| C-Right | A | 8 | right = A |
| L | L | 10 | Shoulder to shoulder |
| R | R | 11 | Shoulder to shoulder |
| Analog stick | not mapped | — | Reserved for the deferred virtual mouse (SN64-U-06); raw axes go to JOY1_STICK |

Why this table: the C-button cluster alone reproduces all four SNES face buttons in their SNES positions. The N64's two large buttons repeat the two most-used SNES action buttons (B and Y) in the same relative positions. Two N64 buttons that map to one SNES button are ORed. Matching by name (N64 A to SNES A) was rejected because it puts SNES A, a secondary button on the SNES, on the N64's primary button, and it inverts the B/Y geometry. To use the D-pad the player holds the left and right prongs. In that grip L, R, A, B and the C buttons are all reachable. Z is not, which is acceptable only because §6 fixes Z to Select, a button most games use only in menus.

Bootstrap rules that go with the table:

1. Write both JOY registers once per N64 controller poll.
2. The N64 D-pad cannot press opposite directions. If a "stick as D-pad" option is added later, it must suppress Up+Down and Left+Right.
3. Write bits 12–15 as 0.

For the bootstrap author, the raw N64 controller status bits are: byte 0 = A, B, Z, Start, D-Up, D-Down, D-Left, D-Right (bit 7 to bit 0); byte 1 = reset flag, reserved, L, R, C-Up, C-Down, C-Left, C-Right. This layout comes from public joybus documentation (n64brew) and has **not** been checked on hardware in this repo.

## Verification

Commands are run from the repo root with the OSS CAD Suite environment. Build directories are `build/joypad-sim`, `build/joypad-sim-fault`, `build/joypad-core`, `build/joypad-core-fault` and `build/joypad-synth`.

- **Serial protocol** (`tb_snes_joypad`). The bench drives strobe and clocks the way the core does and checks every sampled bit. It covers:
  - walking-one on each button for both ports, in opposite orders;
  - reserved mailbox bits set, with the ID staying `0000`;
  - 64 random images;
  - buttons changed after the latch and mid-read (the latched image is still returned, and the new one appears after the next latch);
  - port-1-only clocks not shifting port 2;
  - clocks while strobe is held high not advancing the register, with the data following B live;
  - one-clock-wide pulses;
  - an empty port 2;
  - the multitap line idle on every bit.

  Result: `PASS: SNES pad serial protocol, 82 cases, 3460 bit checks (order B..R, ID 0000, trailing 1s, both ports, latch hold, no multitap, empty port)`.
- **Serial fault injection** (`+define+SN64_FAULT_SWAP_BY`, which swaps B and Y). Must fail. Result: rejected with `walking-one: port 1 bit 0 read 0, expected 1 (bit order/ID/trailing 1s)`.
- **Whole console** (`+define+SN64_JOYPAD_CORE_TEST`, top `tb_snes_joypad_core`). The real core (the same source list as `tb_console_boot`) runs an original diagnostic from a modelled ROM. The diagnostic:
  1. enables auto-read through `$4200`;
  2. waits for VBlank, then for `$4212` busy to rise and fall;
  3. copies `$4218`–`$421C` to cartridge addresses `$70:0000`–`$70:0004`;
  4. strobes `$4016` by hand and reads each port 16 times (plus a 17th read), storing the results to `$70:0005`–`$70:000A`.

  The bench checks every byte the CPU writes on the cartridge bus. It also checks `$421C` = 0 (no multitap), bit 0 = 1 and bit 1 = 0 on the 17th reads, and the mailbox images changing between frames (frame 1 also sets the reserved bits). Result: `frame 0: JOY1=ba50 JOY2=6ca0` at 316,859 clocks, `frame 1: JOY1=4010 JOY2=8020` at 673,215 clocks, then `PASS: core auto-joypad ($4218-$421C) and manual ($4016/$4017) reads return mailbox images over 2 frames with a button change; 4 strobes, 673215 clocks`. The simulation took 0.6 s of wall time.
- **Whole-console fault injection** (same define plus `SN64_FAULT_SWAP_BY`). Must fail. Result: rejected with `frame 0: CPU wrote 7a to 700001, expected ba (auto-joypad)`, where the B and Y bits in `$4219` are swapped.
- **Synthesis of the module alone** (Yosys + slang, `synth_ecp5`): **32 LUT4, 34 TRELLIS_FF**. The CHECK pass found 0 problems. The log is at `build/joypad-synth/synth.log`, which is not tracked.

## Limits

- Simulation only, and two-state. There is no hardware and no real N64 controller, PIF or bootstrap. The expected values are the documented SNES pad protocol, cross-checked against the core's own `$4218`/`$4016` decoding; no commercial game was run.
- **Not integrated.** No top level yet connects `sn64_n64_endpoint.joy*_buttons` to this block and the block to `sn64_console_candidate`. The whole-console bench drives the button images directly.
- `pad_present` has no mailbox bit yet. It should be tied to `2'b11` until one is assigned.
- Two upstream details are not reachable by normal CPU code:
  - While strobe is high, a clock's falling edge shifts the adapter for one master clock before it reloads. The CPU cannot sample in that window.
  - Two `$4016` reads in consecutive CPU cycles give one merged clock pulse in the core, so the pad advances only once. Ordinary load instructions do not do this; DMA from `$4016` could. This behaviour is in the core, not in this block.
- The input latency and stale-input behaviour (SN64-06-02) are not measured. The pad returns whatever the mailbox holds at the last latch.
- Only NTSC timing was run in the whole-console bench.
- Standard pad only. Multitap is excluded by decision. The mouse is deferred. Super Scope/Justifier are undecided.

## Still open

1. **Integration:** instantiate the block in the SN64 top level between the endpoint and the core, and add the four runs above to `fpga/tools/evaluate.py`.
2. **Presence bit:** assign a mailbox bit for `pad_present`. One proposal is a `PAD_ABSENT` flag, active-high so the reset value means "present", in a new register or in reserved bit 15 of JOYn_BUTTONS. This means changing the endpoint register map.
3. **Stale-input policy:** if the bootstrap stops updating the mailbox (host crash), buttons stay held. Consider clearing both images after a timeout without a mailbox SEQ change, and record the chosen policy in SN64-06-02.
4. **Bootstrap:** the default table, remapping on the menu's mapping screen and the opposite-direction rule are built (2026-10-01, PC tests only). Still open: persistence, and measuring the poll-to-latch latency on N64 and M64 (SN64-06-03, SN64-13-09).
5. **Virtual mouse (deferred):** a mouse on a port needs a different serial device (signature `0001`, 32 bits, speed cycling, per the protocol page linked in [snes-peripherals](../research/snes-peripherals.md)). It would replace the adapter on that port and reuse JOY1_STICK.
