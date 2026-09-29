# Clock plan

Decision record, 2026-09-29. Selects the clock sources for the SNES master clock (both regions), the N64 CIC soft CPU and the HDMI output. Parts are candidates checked for stock at JLCPCB/LCSC on this date, not a frozen BOM; jitter and phase-noise effects still need measurement on the prototype.

## Requirements

| Clock | Frequency | Why it must be accurate |
|---|---|---|
| SNES master, NTSC | 21.4772727 MHz (6 × 3.579545) | Drives the CPU/PPU/APU timing, and reaches the cartridge on SYSTEM_CLK (pin 1). Enhancement chips such as Super FX clock from it. Real consoles use a ±50 ppm-class crystal. |
| SNES master, PAL | 21.28137 MHz | Same, for PAL timing (spec keeps PAL in scope). |
| CIC soft CPU | 62.5 MHz | SummerCart64's rate; the SERV core is too slow at 21.477 MHz (see [CIC notes](n64-cic-implementation.md)). |
| HDMI 480p | 27 MHz pixel, 135 MHz TMDS (5×) | Standard 720×480p60 timing; see the A/V design note. |

## Why the FPGA PLL alone cannot make the SNES clocks

ECP5 PLL dividers are limited to 1–128 with a 400–800 MHz VCO. A search over all divider combinations from a 25 MHz reference gives at best 21.428571 MHz for NTSC (**−2,268 ppm**) and **+6,917 ppm** for PAL; from 12 MHz it is worse. Both are far outside crystal accuracy and would shift CPU speed, audio pitch and cartridge coprocessor clocks. The 62.5 MHz and 135 MHz clocks, by contrast, are exact from 25 MHz (FB 5/REF 2 and FB 27/REF 5).

## Selected architecture

```text
25 MHz oscillator ──┬──> ECP5 PLL A ── 62.5 MHz  (CIC soft CPU)
                    ├──> ECP5 PLL B ── 135 MHz / 27 MHz (HDMI TMDS / pixel)
                    ├──> FPGA housekeeping (I2C master, power sequencer, USB-side logic)
                    └──> Si5351A XTAL/CLKIN
                            ├─ CLK0: 21.4772727 MHz (NTSC SNES master) ─┐
                            └─ CLK1: 21.28137   MHz (PAL SNES master)  ─┴─> FPGA global clock input(s) → SNES core, bridge, SYSTEM_CLK
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
