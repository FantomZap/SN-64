# Cartridge analog audio into HDMI

Snapshot 2026-09-29. Some SNES cartridges put their own sound on socket pins 31/32: MSU-1 music on the FXPAK Pro, and a few coprocessor boards. This block adds that sound to the SNES core's sound on the HDMI output.

**Status: simulated and synthesised only.** It has run in Verilator and also in Icarus, which is four-state and therefore able to see unknown (X) values. Nothing has run on hardware. The ADC part number, its oscillator and the analog front end belong to the clock/A-V schematic sheet and are not chosen here.

## Plain-language summary

A small converter chip (the ADC) on the board turns the cartridge's left and right audio into numbers, 32,000 times a second. It runs on its own crystal and sends those numbers over three wires in the standard I2S format.

The FPGA listens on those wires with a fast clock, about 30 times faster than the ADC's bit clock. It picks out each 24-bit left/right pair. It adds the pair to the SNES core's own sound, and the result goes to HDMI as before.

The two sounds are made by different clocks, so one side always runs a tiny bit faster than the other. A short waiting line (8 samples) absorbs the difference. When the line runs completely full or completely empty, one cartridge sample is skipped or played twice. At the ±500 ppm offset tested here that happens about 16 times a second, and each one is a single sample.

If both sounds are loud at the same instant, the sum is clipped at full scale. It never wraps around into a loud click.

## Files

| File | Role |
|---|---|
| [fpga/rtl/sn64_i2s_rx.sv](../../fpga/rtl/sn64_i2s_rx.sv) | I2S slave receiver. BCK/LRCK/DOUT are oversampled by a fast clock (`clk_host`, 62.5 MHz). It detects edges, extracts the words and checks framing. |
| [fpga/rtl/sn64_audio_mix.sv](../../fpga/rtl/sn64_audio_mix.sv) | Toggle crossing into `clk_snes`, 8-frame elastic buffer with one-sample slips, and saturating mix into the DSP stream. |
| [fpga/rtl/sn64_top.sv](../../fpga/rtl/sn64_top.sv) | New ports `adc_bck`, `adc_lrck`, `adc_dout`. The receiver runs on `clk_host` and the mixer sits between the core's audio and `sn64_av_out`. |
| [fpga/tests/tb_audio_mix.sv](../../fpga/tests/tb_audio_mix.sv) | Self-checking bench: an asynchronous I2S master at a chosen ppm offset, and an SNES sample stream. It also holds the four fault builds. |
| [fpga/tests/tb_system.sv](../../fpga/tests/tb_system.sv) | Whole-system check: an I2S master on the new ports, with the mixed audio checked at the input of `sn64_av_out`. |

Both RTL files are original SN64 code, GPL-3.0-or-later. No suitable open I2S-slave-with-elastic-buffer block was found to reuse:

- SNESTang's HDMI audio path resamples through a FIFO. [av-output-implementation.md](av-output-implementation.md) records why that was rejected.
- The hdl-util/hdmi modules vendored for A/V only transmit.

## Signal path

```text
 ADC (I2S master, own oscillator)          clk_host 62.5 MHz                     clk_snes 21.48 / 21.28 MHz
 BCK 2.048 MHz, LRCK 32 kHz, DOUT  ──►  sn64_i2s_rx: 3+2-stage synchronisers, ──► sn64_audio_mix: toggle sync ──► FIFO (8) ──┐
                                        BCK-rise detect, 24-bit L/R, framing     (frame held 31 us)                            │
 SNES core DSP: audio_left/right, audio_ready (1 pulse per sample) ───────────────────────────────────────────► sat16(snes + cart)
                                                                                                                   │
                                                                                 sn64_av_out (audio port unchanged) ◄┘
```

## Board ADC (from the clock/HDMI/audio sheet)

- ADC: **PCM1808** in I2S master mode at 384 fs from its own 12.288 MHz oscillator, 24-bit I2S, BCK = 64 fs = 2.048 MHz ([av-clock-schematic.md](av-clock-schematic.md)).
- TI SLES177B section 6.6 master-mode timing: BCK high/low >= 65 ns; t(CKLR) and t(CKDO), BCK falling edge to LRCK/DOUT valid, -10 to +20 ns; t(LRDO) -10 to +20 ns; rise/fall <= 20 ns.
- Level: ADC full scale (0.6 x VCC = 3.0 Vp-p at VINx) corresponds to 6.0 Vp-p at the socket contact (network gain 0.500). An sd2snes-class source sits at about -20.6 dBFS. The console mixes cartridge audio and S-DSP with equal 10 k weights (OpenSFC R62/R55 vs R60/R61), so the digital mix gain needs the S-DSP's analog level: open.

## Sources

- **I2S format and timing.** Philips Semiconductors, "I2S bus specification", February 1986, revised 5 June 1996. The copy came from the Internet Archive capture of `nxp.com/acrobat_download/various/I2SBUS.pdf`, downloaded 2026-09-29, 61,326 bytes, SHA-256 `8b745bc8e8a3d8da17e982477411ddf20c627edd557a84c2e7a6c5647ed97bda`, saved as `build/r3-audio/refs/philips-i2s-bus-spec-1996.pdf` (untracked). The current NXP UM11732 link returned "page not available". Facts used:
  - two's complement, MSB first;
  - the MSB is sent one clock period after WS changes;
  - WS = 0 is left;
  - the receiver latches on the rising (leading) SCK edge;
  - the transmitter's delay is tdtr ≤ 0.8T and its hold is thtr ≥ 0;
  - master-mode SCK HIGH and LOW are each ≥ 0.35T (Table 1 and notes 2a, 3, 4).
- **Task inputs, not re-derived here.** fs = 32 kHz nominal, 24-bit Philips I2S, BCK = 64 fs, and the ADC as I2S master on its own oscillator come from the round's system contract. The ADC part is not yet selected, so its tDO, duty and word length must be checked against the table below once it is.
- **SNES DSP sample rate.** Taken from the pinned SNESTang core (`build/generated/snestang/src/dsp.v`, `CEGen.v`, `dsp.vh`, prepared by `fpga/tools/prepare_core.py`):
  - `CEGen` fires at `f_master × ACLK_FREQ / 2147730`, with `ACLK_FREQ = 411904`;
  - `SND_RDY` fires once per 32 steps × 4 substeps = 128 CE.

## Receiver: why the sampling point is safe

The I2S lines are not used as clocks. All three pass through identical flip-flop chains clocked by `clk_host`, which is 16 ns and always on. A BCK rising edge is detected at stage 2, the first sample that is high after one that is low. SD and WS are taken `DATA_LAG = 2` captures before the capture that first saw BCK high.

| Quantity (T = 1/(64 × 32 kHz) = 488.3 ns) | Value | Source |
|---|---:|---|
| SD/WS guaranteed valid before a rising edge (tdtr ≤ 0.8T, thtr ≥ 0) | last 0.2T = 97.7 ns | I2S spec, Table 1 |
| When the lagged capture was taken | 16 to 48 ns before the edge (includes one clock of metastability uncertainty) | design |
| Margin, early side | 97.7 − 48 = **49.7 ns** | |
| Margin, late side | **16 ns** (one full clock before the edge) | |
| SCK HIGH/LOW minimum (0.35T) versus the sampling period | 170.9 ns = 10.7 clocks, so no edge is missed | I2S spec, Table 1 |
| The same arithmetic at `clk_snes` (46.6 ns) | lag window 140 ns > 97.7 ns: **does not fit** | why `clk_host` is used |

A converter that changes data on the falling edge, as most do, has far more margin (about T/2 − tDO before the rising edge). The bench does not rely on that. After every rising edge its model changes SD/WS at a random time anywhere in the specification's window, [1 ns, 0.78T]. The fault build `SN64_FAULT_I2S_LATE_SAMPLE` takes SD/WS from the same capture as BCK, which is up to 16 ns after the edge, and the bench rejects it.

**Framing.** Every slot must be exactly 32 BCK periods (64 fs). The first rising edge after a WS change carries the previous slot's last bit; the next 24 edges carry the word. A frame (left, then right) is delivered only if the slots before and between the words had full length. `locked` needs 2 good frames and drops on any bad slot. `frame_errors` counts bad slots, saturating.

## Elastic buffer and slip policy

Each frame the receiver completes flips `frame_tog`, and the words are held for a whole frame (31 µs). The mixer synchronises the toggle with two flops, then writes the held words into an 8-entry FIFO in `clk_snes`.

- **Priming.** Reading starts when the FIFO is half full (4 frames). Cartridge latency is therefore about 125 µs, which is negligible.
- **One output per SNES sample.** Each `audio_ready` rising edge pops one frame and emits one mixed sample one clock later. The SNES stream is never delayed, dropped or repeated.
- **ADC faster.** If the FIFO is full and nothing is popped on that clock, the incoming frame is dropped (overflow slip).
- **ADC slower.** If the FIFO is empty at a pop, the previous frame is repeated (underflow slip).
- **Slip rate.** Slips occur once per 1/|Δf| samples. They do not come in bursts, because the synchroniser can only move a frame by one clock, so the next event order cannot change twice in a row.
- **Checks.** The bench checks that no two slips are adjacent and that the gap between slips is at least half the gap the rate predicts.
- **Reset and lock loss.** With `cart_enable` low, core reset, or the ADC not locked, the FIFO is flushed and the SNES samples pass through bit-exact.

### Rates, and a finding about the pinned core

| SNES clock | Core DSP sample rate with the pinned `ACLK_FREQ = 411904` | Offset vs a 32,000 Hz ADC | One cartridge-sample slip every |
|---|---:|---:|---:|
| NTSC 21.477272 MHz | 32,179.96 Hz | +5,624 ppm | 5.6 ms (repeats) |
| PAL 21.28137 MHz | 31,886.43 Hz | −3,549 ppm | 8.8 ms (drops) |

The SNESTang default makes the DSP 0.56 % fast. `dsp.vh` keeps the original 409600 commented out. SNESTang also derives the CE from an NTSC constant in both regions. A 32 kHz ADC therefore slips about 180 times a second on NTSC, not the few times a second that crystal tolerances alone would cause.

`tb_system` sees this directly on the real core. Its run slips the cartridge stream 2 to 3 times in about 1,000 samples (repeats), as the table predicts.

- **Scope of the finding.** The mixer handles it correctly: it is tested at the SNESTang rate (`+snes_rate=32180`). It is still an audible-quality question for MSU-1 music.
- **Not changed here.** The DSP rate is a core-configuration decision. It also affects `sn64_av_out`, whose HDMI channel status says 32 kHz. See the open items.

## Mix, gain and headroom

`out = sat16(snes + cart_scaled)`, where `cart_scaled = (adc × CART_GAIN_Q12) >>> 20`, an arithmetic shift, i.e. floor.

- **Gain.** `CART_GAIN_Q12` is unsigned Q4.12; 4096 = 1.0, the default. At 1.0 an ADC full-scale word maps to 16-bit full scale (`adc[23:8]`) and no multiplier is synthesised. Any other value costs a MULT18X18D pair per channel.
- **Headroom.** The core's DSP output is already clamped to 16 bits (`CLAMP16` in `dsp.v`). The sum can reach twice full scale, so there is **0 dB of headroom** for coincident full-scale peaks. The output saturates at +32767 / −32768 and never wraps. The bench exercises this on more than 150 samples per run (more than 1,400 in the long runs), and the `SN64_FAULT_AUDIO_WRAP` build is rejected.
- **Why not −6 dB on both.** That would make clipping impossible but would lower every game by 6 dB and drop one bit of DSP resolution for the rare cartridge that has its own audio.
- **PROVISIONAL.** The gain of 1.0 is a placeholder. The correct value depends on the analog front end (cartridge line level versus ADC full scale, clock/A-V sheet) and on the level of cartridge audio relative to the DSP on a real console. Neither has been sourced or measured. Measure both on the prototype before fixing it.

## Verification

Commands, from the repo root with the tool environment in `CLAUDE.local.md`. `evaluate.py --mode sim` runs all of these.

```powershell
verilator_bin --binary --timing --build-jobs 4 -Wno-fatal --top-module tb_audio_mix --Mdir C:/Users/RyanB/.claude/projects/SN64/build/r3-audio/mix fpga/rtl/sn64_cdc.sv fpga/rtl/sn64_i2s_rx.sv fpga/rtl/sn64_audio_mix.sv fpga/tests/tb_audio_mix.sv
build/r3-audio/mix/Vtb_audio_mix.exe +adc_ppm=500
build/r3-audio/mix/Vtb_audio_mix.exe +adc_ppm=-500 +duty=35
build/r3-audio/mix/Vtb_audio_mix.exe +adc_ppm=0 +snes_rate=32180
# fault builds: add +define+SN64_FAULT_AUDIO_SWAP_LR | SN64_FAULT_AUDIO_NO_SIGNEXT | SN64_FAULT_AUDIO_WRAP | SN64_FAULT_I2S_LATE_SAMPLE (each must FAIL)
iverilog -g2012 -o build/r3-audio/iv/tb_audio_mix.vvp -s tb_audio_mix fpga/rtl/sn64_cdc.sv fpga/rtl/sn64_i2s_rx.sv fpga/rtl/sn64_audio_mix.sv fpga/tests/tb_audio_mix.sv
vvp -n build/r3-audio/iv/tb_audio_mix.vvp +adc_ppm=0 +snes_rate=32180
```

### What the bench checks

- **Integrity.** Every output equals `sat16(snes + adc[23:8])` for a single ADC frame *n*, the same *n* on L and R. That covers pairing, sign, truncation and gain.
- **Sequence.** *n* advances by exactly one per SNES sample except at a slip.
- **Slip direction and count.** Only drops when the ADC is faster and only repeats when it is slower, with at least two per run. The net count must agree with the rate offset to within half the buffer ±2, and the DUT's own counters must agree.
- **Second mixer.** A second mixer with gain 0.5 is checked on the same frames.
- **Other checks.** At least 10 saturating outputs, exactly one output per SNES sample, and `$isunknown` on every output.

### Results, 2026-09-29, this snapshot

| Run | Result |
|---|---|
| `+adc_ppm=500` | PASS: 14,785 outputs bit-exact, **3 drops, 0 repeats**, min gap 2,079 (rate implies 2,076), 1,454 saturated, 0 framing errors |
| `+adc_ppm=-500 +duty=35` (BCK high 35 %, the specification minimum) | PASS: 13,764 outputs, **0 drops, 5 repeats**, min gap 1,927 (1,930), 1,449 saturated |
| `+adc_ppm=0 +snes_rate=32180` (pinned SNESTang NTSC rate) | PASS: 1,503 outputs, 0 drops, **6 repeats**, one every 178 samples as predicted, 152 saturated |
| same run, Icarus `vvp` (four-state) | PASS with identical counts, no X on any output |
| `SN64_FAULT_AUDIO_SWAP_LR` | **FAIL as required**: output 6 `L=ce19 R=8eb6` matches no ADC frame |
| `SN64_FAULT_AUDIO_NO_SIGNEXT` | **FAIL as required**: negative cartridge words come out as `7fff` |
| `SN64_FAULT_AUDIO_WRAP` | **FAIL as required**: `snes 7d00 + cart` gives `da07` instead of `7fff` |
| `SN64_FAULT_I2S_LATE_SAMPLE` | **FAIL as required**: bit errors (for example `R=3b6b`, expected `3b5b`) when SD changes within 16 ns after the edge |
| `tb_system`, all four runs (default, `+pal_header`, `+pal_key +ntsc_header`, `+ntsc_key +pal_header`) | PASS: 997 to 1,098 samples at `sn64_av_out` equal `sat16(DSP + ADC word)` after 3 priming samples, 0 wrong, 0 framing errors, 2 to 3 underflow slips at the core's real rate |

### Synthesis

Yosys, OSS CAD Suite 20260928, `synth_ecp5`, `check -assert` gives 0 problems for both:

- **`sn64_i2s_rx`:** 58 LUT4, 147 FF, 25 CCU2C.
- **`sn64_audio_mix`:** 208 LUT4, 112 FF, 50 CCU2C, 8 TRELLIS_DPR16X4 (the FIFO; the 8 LSBs the gain-1.0 mix never uses are trimmed), and no multiplier.

Logs: `build/r3-audio/synth-*.log`, untracked. Not yet in a place-and-route run: `route_top.py` needs the two new files (integration edit).

## Limits and open items

1. **Hardware.** The ADC part, its oscillator, tDO and BCK duty, the analog front end, and the grounding against HDMI and FPGA noise all belong to the clock/A-V sheet. Check them against the sampling table above once chosen.
2. **SNES DSP rate (decision needed, not made here).** With the pinned `ACLK_FREQ = 411904`, cartridge audio slips every 5.6 ms (NTSC) or 8.8 ms (PAL). Options:
   - restore 409600, the original 32.000 kHz, in the generated core copy, and make the CE input constant region-correct;
   - or choose the ADC oscillator to match the core.

   `sn64_av_out`'s HDMI channel-status rate is affected by the same choice.
3. **Gain and headroom** are provisional (see above). Consider making `CART_GAIN` a menu setting through the mailbox if cartridges differ.
4. **Telemetry.** `adc_locked`, `frame_errors` and the slip counters exist in `sn64_top` but are not yet in the mailbox. They are useful for a diagnostics page.
5. **No glitch filter on BCK.** A noise spike longer than one 16 ns sample would be taken as an edge. The framing check then drops lock until two clean frames arrive. Revisit after board layout.
6. **Slip audibility.** A single-sample repeat or drop is inaudible on most material at the crystal-tolerance rate. At the SNESTang rate offset it may be audible on sustained tones. A fractional resampler would remove it, at the cost of logic and a multiplier.
