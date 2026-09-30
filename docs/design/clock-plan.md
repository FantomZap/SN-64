# Clock plan

Decision record, 2026-09-29. Selects the clock sources for the SNES master clock (both regions), the N64 CIC soft CPU and the HDMI output. Parts are candidates checked for stock at JLCPCB/LCSC on this date, not a frozen BOM; jitter and phase-noise effects still need measurement on the prototype.

## Requirements

| Clock | Frequency | Why it must be accurate |
|---|---|---|
| SNES master, NTSC | 21.4772727 MHz (6 × 3.579545) | Drives the CPU/PPU/APU timing, and reaches the cartridge on SYSTEM_CLK (pin 1). Enhancement chips such as Super FX clock from it. Real consoles use a ±50 ppm-class crystal. |
| SNES master, PAL | 21.28137 MHz | Same, for PAL timing (spec keeps PAL in scope). |
| CIC soft CPU and N64 endpoint | 62.5 MHz | SummerCart64's rate; the SERV core is too slow at 21.477 MHz (see [CIC notes](n64-cic-implementation.md)). |
| HDMI 480p | 27.0198 MHz pixel (NTSC master × 39/31), 135.1 MHz TMDS (5×) | The [A/V block](av-output-implementation.md) line-doubles each SNES line into exactly two HDMI lines, so the raster must be frequency-locked to the SNES frame (858 × 524 at 60.0988 Hz). |

## Why the FPGA PLL alone cannot make the SNES clocks

ECP5 PLL dividers are limited to 1–128 with a 400–800 MHz VCO. A search over all divider combinations from a 25 MHz reference gives at best 21.428571 MHz for NTSC (**−2,268 ppm**) and **+6,917 ppm** for PAL; from 12 MHz it is worse. Both are far outside crystal accuracy and would shift CPU speed, audio pitch and cartridge coprocessor clocks. The 62.5 MHz and 135 MHz clocks, by contrast, are exact from 25 MHz (FB 5/REF 2 and FB 27/REF 5).

## Selected architecture

```text
25 MHz oscillator ──┬──> ECP5 PLL A ── 62.5 MHz  (N64 endpoint, CIC soft CPU)
                    └──> FPGA housekeeping (I2C master, power sequencer, SNES CIC lock)
25 MHz crystal ────────> Si5351A
                            ├─ CLK0: 21.4772727 MHz (NTSC SNES master) ─┐
                            ├─ CLK1: 21.28137   MHz (PAL SNES master)  ─┴─> FPGA global clock input → SNES core, bridge, SYSTEM_CLK
                            └─ CLK2: 27.0197947 MHz (HDMI pixel = NTSC master × 39/31, same PLLA) ──> ECP5 PLL B ×5 → 135.1 MHz TMDS
```

- The Si5351A variant has a crystal input only (XA/XB), so it gets its own 25 MHz crystal (10 pF load, register 183) rather than the FPGA's oscillator; the Si5351C would accept an external clock but is poorly stocked.
- **Si5351A-B-GTR** (LCSC C504891, MSOP-10, 1.71–3.6 V, 3 outputs, I²C; 34,074 in stock at $1.19 on 2026-09-29; datasheet period jitter 70 ps) synthesises both SNES masters from the 25 MHz reference:
  - NTSC: PLLA = 25 MHz × (34 + 4/11) = 859.090909 MHz, output divider 40 (even integer) → **21.4772727 MHz exactly** (rational ratio 189/220).
  - PAL: PLLB = 25 MHz × (34 + b/c) with c ≤ 1,048,575 → 851.2548 MHz, divider 40 → 21.28137 MHz with sub-ppb synthesis error.
  - Accuracy therefore follows the 25 MHz reference (±20 ppm for the candidate below), comparable to an original console's crystal.
- **25 MHz oscillator**: e.g. CJO05-250003320B30 (LCSC C712741, 3.3 V CMOS, ±20 ppm, 3225, 17,002 in stock). ULX3S uses a 25 MHz reference for the same reason.
- **The SNES master clock starts once, at power-on, at the chosen frequency, and never changes while it runs.** No live NTSC/PAL switching, and no switching when a flashcart launches a game: a frequency change mid-launch could confuse a Super EverDrive or FXPAK Pro (crash or return to its menu). Physical damage is not expected (same logic levels; the two masters differ by about 0.9 %, the same difference as between PAL and NTSC consoles, which flashcarts support), but the functional risk is not worth taking.
- **Region auto-detection happens before the SNES clock starts**, with the cartridge powered and held in reset, as on a real console at power-on: (1) the cartridge's key CIC type (F411 = NTSC, F413 = PAL) from the SNES CIC lock, which runs from its own CIC clock; (2) the ROM header country byte at CPU `$00:FFD9` (the header maps there for both LoROM and HiROM), read through the bridge, which needs no SNES master clock because cartridge ROMs are asynchronous; (3) a user override in the N64 menu (Auto / NTSC / PAL), applied at the next cartridge power-up. For flashcarts the result is the flashcart's own menu region; per-game region then relies on the manual setting.
- **Region selection** is a register setting: the FPGA programs the Si5351 over I²C at power-on (both outputs are generated; nothing is reprogrammed later), then starts the SNES clock domain from CLK0 or CLK1 once the region is decided.
- Alternative kept on file: a dedicated 21.47727 MHz crystal (e.g. SST C5289705, ±20 ppm, 2,669 in stock) with the FPGA as oscillator is not recommended (FPGA pins are not crystal drivers), and no 21.28137 MHz part was found in stock, so a crystal-based design would need two oscillators and would lose PAL sourcing.

## Consequences and checks

- The FPGA must configure the Si5351 before the SNES side can run: add a small I²C master and a register table (both frequencies precomputed) to the FPGA image; the SNES clock domain stays in reset until the Si5351 reports lock (read `SYS_INIT`/`LOL` status) and the output is enabled.
- Blank-board programming and the N64 endpoint do not depend on the Si5351 (they run from the 25 MHz reference and the host clocks).
- Keep the Si5351 output traces short, series-terminated (footprints per spec §5), and route the SNES master to an ECP5 primary clock input.
- To measure on the prototype: frequency accuracy and jitter at SYSTEM_CLK, behaviour with Super FX / SA-1 carts, and audio pitch on both regions.

## Implementation

[fpga/rtl/sn64_clock_init.sv](../../fpga/rtl/sn64_clock_init.sv) programs the Si5351 over I²C at 400 kHz from the 25 MHz housekeeping clock: all outputs off, the PLLA/PLLB/MS0/MS1 values above, crystal load, PLL reset, CLK0/CLK1 enabled, then it polls register 0 until SYS_INIT and both loss-of-lock bits clear before asserting `clocks_ready`. A missing ACK or a lock timeout latches `i2c_error`. The region output follows the forced mode or the detection result only while `snes_clock_stopped` is high.

[fpga/tests/tb_clock_init.sv](../../fpga/tests/tb_clock_init.sv) uses a behavioural Si5351 I²C slave. It verifies every programmed register against the values in this document, that lock was polled, and that the region cannot change while the SNES clock runs but does change at the next power-up window. With `+wrong_addr` the slave never acknowledges and the run must end in `i2c_error`; both runs are in `evaluate.py --mode sim`. Real Si5351 timing, crystal start-up and output jitter remain hardware checks.

### SNES clock select and start/stop inside the FPGA (2026-09-29)

[fpga/rtl/sn64_board_top.sv](../../fpga/rtl/sn64_board_top.sv) feeds Si5351 CLK0 (NTSC) and CLK1 (PAL) into one ECP5 **DCSC** with `DCSMODE="NEG"` and `MODESEL=0` (glitchless). Lattice FPGA-TN-02200 1.3, Table 10.2: SEL[1:0] = 01 selects CLK0, 10 selects CLK1, and 00/11 hold the output low in NEG mode. Figure 10.1: a change waits for the old clock's falling edge and switches at the new clock's falling edge, so no runt pulse reaches the SNES domain. The same primitive therefore both picks the region clock and starts/stops it; no separate DCCA gate is used. The guide also states that both inputs must be oscillating for a glitchless switch; the Si5351 runs CLK0 and CLK1 continuously once programmed, and `snes_clk_run` only rises after `clocks_ready`.

SEL is `{run & pal, run & !pal}` registered on the 25 MHz clock, so both bits change on one edge. Because `region_pal` is frozen while the SNES clock runs, the only transitions are 00 -> 01 or 00 -> 10 at start and back to 00 at stop; a direct NTSC <-> PAL switch never happens. Source: the guide PDF, SHA-256 `69843f2d6bf92bc19ea1f383b3c7fb0fcb9f1a2077efbce6d238c1c3f2496069` (kept under `build/datasheets/`, untracked).

The host clock (25 -> 62.5 MHz: CLKI_DIV 2, CLKFB_DIV 5, CLKOP_DIV 10, VCO 625 MHz) and the TMDS bit clock (27.0198 -> 135.099 MHz: CLKI_DIV 1, CLKFB_DIV 5, CLKOP_DIV 4, VCO 540.4 MHz) come from two EHXPLLL instances with parameters produced by `ecppll`. Both ratios are exact. The TMDS PLL locks only after the Si5351 is programmed; its LOCK holds the HDMI domain in reset (`hdmi_clock_ok`) and does not affect the rest of the design.

## HDMI pixel clock (decision 2026-09-29)

The [A/V block](av-output-implementation.md) needs its pixel clock frequency-locked to the SNES frame (each SNES line becomes exactly two HDMI lines, with a 4-line buffer instead of a frame buffer). Its author proposed two chained ECP5 PLLs from the SNES master (PFD 3.46 MHz, close to the 3.125 MHz minimum). Instead, the Si5351's otherwise unused CLK2 generates the pixel clock from the **same PLLA** as the NTSC master with a fractional output divider of 31 + 31/39: 859.0909 MHz / 31.7948718 = **27.0197947 MHz = master × 39/31 exactly**. Both outputs therefore share one oscillator and one PLL, so the raster cannot drift against the SNES frame, and the ECP5 only needs one PLL (×5, PFD 27 MHz) for the TMDS bit clock. Fractional multisynth outputs have somewhat more jitter than integer ones (Si5351A datasheet); measure the TMDS eye on the prototype. PAL HDMI uses its own ratio from PLLB; see [PAL HDMI](#pal-hdmi-576p50-pixel-clock-2026-09-29) below. The independent-27 MHz fallback also passes the A/V bench with one re-phase per frame.

`sn64_clock_init` programs MS2 (registers 58–65: P1 = 3557, P2 = 29, P3 = 39), CLK2 control 0x0F and enables outputs 0–2; its bench verifies every register.

## PAL HDMI (576p50) pixel clock (2026-09-29)

Status: implemented and simulated (unit benches and a whole-system trial). **Not run on hardware or shown on a display.** The NTSC decision above is unchanged.

### What must hold

The [A/V block](av-output-implementation.md) has no frame buffer. Each SNES line becomes exactly two HDMI lines, and one SNES frame must last exactly one HDMI frame. So the pixel clock must be an exact rational multiple of the running SNES master: `f_pixel / f_master = 2 × H_TOTAL / (master clocks per SNES line)`. For PAL the master is Si5351 CLK1 (PLLB ÷ 40), so the pixel clock must come from PLLB.

### The SNES PAL frame in the core (measured)

Source: the prepared core `build/generated/snestang/src` (generated from `fpga/vendor/snestang`, pinned SNESTang).

- `ppu_defines.vh:3` `DOT_NUM = 340`; `ppu_defines.vh:5` `LINE_NUM_PAL = 312`.
- `ppu.v:777-786`: in PAL, non-interlaced, `LAST_LINE = LINE_NUM_PAL - 1 = 311` and `LAST_DOT = DOT_NUM - 1 = 339`. `ppu.v:817-825`: `H_CNT` runs 0..339 and `V_CNT` 0..311, so there are **340 dots × 312 lines**.
- `ppu.v:257-264`: `DOT_CYCLES` is always 4. The long-dot branch `H_CNT == 323 && H_CNT == 327` can never be true, and the short-line branch is NTSC-only and also selects 4. So a line is **340 × 4 = 1360 master clocks** and a PAL frame is **424,320 master clocks**.

A scratch bench confirms this on the real core, not only by reading (`build/pal-hdmi/scratch/tb_core_timing.sv`, `sn64_console_candidate` with `pal = 0/1`; untracked):

```text
pal=0 frame 3: 356320 master clocks per frame, HDE rises 262, HDE rises with VDE 224, line min/max 1360/1360
pal=1 frame 3: 424320 master clocks per frame, HDE rises 312, HDE rises with VDE 224, line min/max 1360/1360
```

Real hardware has 1364-clock lines (two 6-clock dots per line). The core's lines are 4 clocks shorter. The earlier reading in the A/V document ("341 × 4 = 1364") was wrong: `DOT_NUM` is 340. See the NTSC finding below.

### Raster

CEA-861 VIC 17 (720×576p50, 4:3) timing, from two independent copies of the CEA table:

- hdl-util/hdmi `src/hdmi.sv` lines 152-162 and 207 (commit `83b1c9543a91b776671a44e68e130f81cae437b7`, file SHA-256 `82a8a7fb4c37a7d3a9b23338613e3eea91e06b94dedc7d13c8869b04a9d36788`, kept under `build/av-out/upstream/`).
- Linux `drivers/gpu/drm/drm_edid.c` tag v6.10 lines 837-841 (SHA-256 `1d80fc988a0147509a6b44bf8f38c4891c4814b0b177901aef5710e1b298c143`, under `build/pal-hdmi/datasheets/`).

Both give 27.000 MHz; H: 720 active, 12 front porch, 64 sync, 68 back porch, 864 total; V: 576 active, 5 front porch, 5 sync, 39 back porch, 625 total; negative syncs; picture aspect 4:3.

SN64 keeps every horizontal value, the active area, both sync widths and both front porches. It uses **624 lines instead of 625** (vertical back porch 38 instead of 39), so the frame is exactly 2 × 312 SNES lines. This is the same kind of deviation as the NTSC decision's 524 lines instead of 525. The AVI InfoFrame declares VIC 17 with picture aspect 4:3.

### Ratio and frequency

- `f_pixel / f_master = 2 × 864 / 1360 = 108 / 85`.
- `f_pixel = 21.2813700 MHz × 108/85 =` **27.0398584 MHz**. That is +0.148 % from 27.000 MHz; the NTSC decision is +0.073 %. The A/V document records the HDMI pixel-clock tolerance used for the NTSC decision as ±0.5 %.
- HDMI frame: 27.0398584 MHz / (864 × 624) = **50.154058 Hz**, identical to the core's PAL frame (21.28137 MHz / 424,320). A real PAL console runs at 50.006979 Hz (1364 × 312).
- TMDS ×5: 135.1993 MHz. The existing ECP5 TMDS PLL (CLKI_DIV 1, CLKFB_DIV 5, CLKOP_DIV 4) then runs its VCO at 540.8 MHz (540.4 MHz in NTSC), within the 400–800 MHz range quoted above. Its divider settings do not change.
- HDMI audio: N = 4096 as before; CTS is measured by the vendored counter. With the core's audio rate fixed to the master (a 32000/21477273 per-clock model in the bench), CTS is 27288.8.

### Si5351 programming (AN619 equations)

MultiSynth 2 from PLLB: `D = PLLB / f_pixel = 40 × 85/108 = 850/27 = 31 + 13/27`. This is inside the fractional range 8 + 1/1,048,575 to 2048 (AN619 §4.1.2, p. 5).

- P1 = 128·31 + ⌊128·13/27⌋ − 512 = 3968 + 61 − 512 = **3517**.
- P2 = 128·13 − 27·⌊128·13/27⌋ = 1664 − 1647 = **17**.
- P3 = **27**.
- Registers 58–65 (layout AN619 pp. 39–41): `00 1B 00 0D BD 00 00 11`, with R2 = 1 and DIVBY4 = 00.
- CLK2 control, register 18 (AN619 p. 21): **0x2F**. This is 0x0F with MS2_SRC (bit 5) = PLLB: powered up, fractional mode, MultiSynth 2 as the source, 8 mA.

The NTSC values stay as programmed at start-up: `00 27 00 0D E5 00 00 1D` and 0x0F.

The tables are generated by the same equations. `tb_clock_init` also decodes the register image independently and checks `f_pixel/f_master` as an exact integer identity.

A core with hardware-length (1364-clock) lines would need 432/341 instead. That is MS2 = 31 + 31/54 (P1 3529, P2 26, P3 54; registers `00 36 00 0D C9 00 00 1A`), giving 26.9605626 MHz (−0.146 %) and 50.006979 Hz. `sn64_clock_init` has it behind `PAL_LINE_MCLK = 1364`. The default is 1360, the measured core. Any other value is an elaboration error.

### When CLK2 is retargeted

The region is only known after start-up (key CIC, ROM header or menu), so the start-up table keeps programming the NTSC MS2. After that, [sn64_clock_init.sv](../../fpga/rtl/sn64_clock_init.sv) rewrites MS2 and CLK2 control whenever the latched `region_pal` differs from the region CLK2 is programmed for:

- **Only while the SNES clock is stopped.** The region latch itself only changes then. Each of the nine writes (58–65, then 18) first checks `snes_clock_stopped`. If the clock has started, the sequence stops, CLK2 is marked unprogrammed, and the sequence is redone at the next stopped window.
- **No other register is written after start-up.** PLLA/PLLB (26–41), MS0/MS1, CLK0/CLK1 control, output enable (3) and PLL reset (177) keep their start-up values, so CLK0/CLK1 are never touched. CLK2 is not powered down during the rewrite, so the pixel domain keeps its clock while the reset below reaches it.
- **No PLL reset.** AN619 register 177 (p. 60) resets the PLL itself ("Writing a 1 to this bit will reset PLLA/PLLB"). The datasheet's programming flow (Figure 10, p. 21) applies it once after a complete new configuration. MultiSynth 2 is an output divider after the PLL (AN619 §4.1.2, and register 18 bit 5 only selects which PLL feeds it). Neither document asks for a PLL reset after an output-divider change, and the datasheet lists "glitchless frequency changes" as a feature (p. 1). The feedback dividers do not change, so neither PLL is disturbed. A PLL reset would restart PLLA or PLLB, which run CLK0 and CLK1; the DCSC needs both to keep running. Whether CLK0/CLK1 are really undisturbed during an MS2 rewrite is a prototype measurement (scope on both outputs), not something the documents state.
- **Intermediate frequencies.** The rewrite passes through a few other frequencies. With MS2 already at the PAL value but still on PLLA, CLK2 is 27.289 MHz, and 26.773 MHz in the reverse case. During that time the pixel domain is in reset.
- **`pixel_clock_ready`** is high only when CLK2 matches `region_pal` and, while the SNES clock is stopped, no region change is pending. It drops on the same clock that a new region is latched. `pixel_region_pal` says which raster CLK2 is programmed for.
- **Top level (integration edit).** `snes_clk_run` may only rise with `pixel_clock_ready`. `rst_pixel_n` uses `pixel_clock_ready` instead of `clocks_ready`. `sn64_av_out.pal` takes `pixel_region_pal`, and the block samples it only while its domain is in reset.

Source documents (untracked, `build/pal-hdmi/datasheets/`):

- Skyworks AN619 Rev 0.8 (2021-09-23), SHA-256 `0135b3a37195189e38cbd58ca504460814c691eeb1fdbe275806cfcd4783f36b`.
- Si5351A/B/C-B datasheet Rev 1.3 (2021-08-27), SHA-256 `f3bc5285fccafa3fcd06e9a7fa6abb67fb43e8c23f6147b14caecc9a4851101f`.

### Evidence (real output, 2026-09-29)

**`tb_clock_init`** (`build/pal-hdmi/clock-init`) passes:

```text
  PAL : PLLB 851.2548 MHz, master 21.281370 MHz, MS2 = 108800/3456, pixel 27.0398584 MHz (= master x 108/85), 1728.000 pixels per 1360-clock SNES line
PASS: Si5351 image (PLLA/PLLB/MS0/MS1/MS2/control) written and verified, lock polled (5 status reads), region latched only while SNES clock stopped; CLK2 retargeted NTSC->PAL->NTSC->PAL (MS2+reg18 only, 30 post-start-up writes, 0 while the SNES clock ran, 1 PLL reset), interrupted sequence stopped and redone (80 writes, 702020 clocks)
```

The bench checks:

- the start-up image, and that `pixel_clock_ready` is low from the moment PAL is latched until CLK2 is reprogrammed;
- the PAL and NTSC MS2/CLK2 images, both as bytes and as decoded ratios;
- that only registers 18 and 58–65 are written after start-up, and there is exactly one PLL reset;
- that there is no I²C START while the SNES clock runs, and `pixel_clock_ready` stays high while it runs;
- that a (misbehaving) clock start in the middle of the sequence stops it after the current byte and it is redone later.

The fault build `SN64_FAULT_CLK_IGNORE_STOP` keeps writing after the SNES clock starts. It fails as required, with `ERROR: Si5351 written while the SNES clock runs`, `6 I2C transactions started while the SNES clock ran` and `FAIL: clock-init 4 errors` (exit 1). `+wrong_addr` still ends in `i2c_error`.

**Whole-system trial.** This used the integration edits applied to copies of the current `sn64_top.sv` / `tb_system.sv`. The trial `tb_system` models the Si5351 register image, derives the pixel clock from the programmed CLK2 source and runs the SNES clock at the region's frequency. All four evaluate.py plusarg sets pass, and the corrupt-key negative run still fails as intended. PAL runs show `HDMI: raster 864x624 VIC 17 frame-locked, 4 lock events, lock errors -23864 0 0 0 px, 1 re-phases, locked 1, Si5351 writes 59`. The details are in the [A/V document](av-output-implementation.md#pal-576p50-2026-09-29).

### Finding: NTSC with the core's 1360-clock lines

The NTSC decision's 39/31 equals 2 × 858 / **1364**. The core's NTSC lines are 1360 clocks (measured above), so its NTSC frame is 356,320 master clocks, while the 858 × 524 raster at master × 39/31 lasts 357,368. In the whole-system trial the NTSC raster is therefore **1,328 px early at every lock event**:

- 1,318.5 px of that comes from the line length; the other 9.3 px comes from the testbench's rounded clock periods.
- The raster re-phases every frame (about 1.5 HDMI lines in the back porch).
- `av_locked` stays 0, because the error exceeds `LOCK_WINDOW`.

The unit bench does not show this, because its SNES model uses 1364-clock lines.

This record does not change the NTSC decision. The owner has two options:

1. Program NTSC MS2 = 40 × 340/429 = 31 + 301/429 (P1 3545, P2 347, P3 429; registers `01 AD 00 0D D9 00 01 5B`). That gives 27.0992647 MHz (+0.368 %) and locks to the current core at 60.275238 Hz.
2. Give the core hardware-length lines (fix the long-dot condition through `prepare_core.py`, which also changes CPU/PPU timing towards real hardware). The 39/31 decision is then exact, and PAL switches to `PAL_LINE_MCLK = 1364`.

### Still to check on hardware

- CLK0/CLK1 continuity during an MS2 rewrite.
- ECP5 TMDS PLL behaviour on the CLK2 frequency step (its LOCK also holds the HDMI domain in reset).
- TMDS eye at 135.2 MHz.
- Display and capture acceptance of 864 × 624 at 50.154 Hz.
