# Clock and cartridge-audio schematic sheet

**Draft 0.2-av (2026-09-29): the HDMI output is gone.** J701, U702 TPD12S016, the 22 nF TMDS coupling, TP701, R705 and the Si5351 CLK2 pixel clock were removed: the SNES picture and sound go to the console over the cartridge bus ([console-video-path.md](console-video-path.md)), so the board has no video output of its own. Si5351 pin 6 (CLK2) is left open and the RTL keeps the output powered down and disabled. The 0.1-av description of the HDMI block is in git history (commit `a2dcad3`). Everything below describes the sheet as it is now unless marked otherwise.

Draft 0.1-av, 2026-09-29. This is a schematic sheet, [`hardware/sn64/av-clock.kicad_sch`](../../hardware/sn64/av-clock.kicad_sch). It is **not yet attached to the root schematic**; attaching it is an integration edit, listed at the end. It passes a static netlist check and KiCad ERC on a validation copy of the project. **No PCB, signal-integrity simulation, audio measurement or hardware test has been done.**

## Plain-language summary

This sheet holds three things:

- **Clock chip.** It makes the SNES master clock for both regions.
- **Housekeeping oscillator.** 25 MHz, for the FPGA.
- **Audio input.** A stereo audio converter digitises the analog sound that some cartridges send back through the SNES socket, such as MSU-1 audio from an FXPAK Pro or sd2snes.

Every part number, pin and value is taken from a downloaded datasheet or a pinned open design. Values still to be tuned on the prototype are marked **provisional**.

## Files

| File | Role |
|---|---|
| `hardware/sn64/av-clock.kicad_sch` | The child sheet: 36 symbols, 13 hierarchical ports (0.2-av). |
| `hardware/sn64/tools/add_av_clock_sheet.py` | Authoring script, same house style as `add_cart_interface.py`: installed KiCad symbols embedded in the sheet, drawn symbols only where KiCad has none, provenance JSON, refuses to overwrite without `--force`. It never edits the real root; `--attach-root` attaches the sheet to a given root (used on the validation copy). |
| `hardware/sn64/libraries/SN64_AV.kicad_sym` | Drawn symbol for TI **PCM1808PW**, which is not in the KiCad 10 library. |
| `hardware/sn64/libraries/av-provenance.json` | Source URL, revision and SHA-256 of every datasheet, pin tables and the facts used. |
| `hardware/sn64/tools/verify_av_clock_sheet.py` | Independent netlist and ERC check, plus `--negative-test`. |
| `hardware/sn64/validation/av-clock-check.json` | Result of the last passing check (run on the validation copy). |

## Clock block (implements [clock-plan.md](clock-plan.md), unchanged)

| Ref | Part | Source and check |
|---|---|---|
| U701 | **Si5351A-B-GTR**, MSOP-10, LCSC C504891 | KiCad `Oscillator:Si5351A-B-GT`. Its pins match Skyworks Si5351-B Rev 1.3, Table 20: 1 VDD, 2 XA, 3 XB, 4 SCL, 5 SDA, 6 CLK2, 7 VDDO, 8 GND, 9 CLK1, 10 CLK0. Pin 6 (CLK2) is left open: `sn64_clock_init` keeps CLK2 powered down and its output disabled (register 3 = 0xFC), and the verifier checks both. VDD and VDDO both come from `FPGA_3V3`; §7.2 requires VDDO to come up with or before VDD. |
| Y701 | 25 MHz crystal, **YXC X322525MMB4SI**, 3225, **CL 10 pF**, LCSC C70582 (34,212 in stock) | Datasheet (YSX321SL family): pins 1 and 3 are the crystal, 2 and 4 are GND; ESR ≤ 50 Ω (16–31 MHz); drive level up to 200 µW; C0 ≤ 3 pF. Si5351 Table 8 needs 25–27 MHz, CL 6–12 pF, ESR ≤ 150 Ω and a crystal rated for ≥ 100 µW. |
| — | **Load-capacitance cross-check** | `fpga/rtl/sn64_clock_init.sv` writes register 183 = `0xD2`. AN619 Rev 0.8 decodes that as bits 7:6 = `11` (internal CL = 10 pF) and bits 5:0 = `010010b`, the required reserved value. That matches the crystal's 10 pF. Si5351 §7.4: the internal load capacitance is used, so there are no external load capacitors. The verifier reads the register value from the RTL and fails if the two disagree. |
| R701, R702 | 4.7 kΩ pull-ups from `si_scl`/`si_sda` to `FPGA_3V3` | Si5351 Figure 5 (4.7 k shown), Table 20 (at least 1 kΩ, to VDD). I²C address 0x60, 400 kHz from `sn64_clock_init`. |
| R703, R704 | **0 Ω** series resistors: CLK0 → `si_clk0` (NTSC 21.4772727 MHz), CLK1 → `si_clk1` (PAL 21.28137 MHz) | Si5351 Table 5: the output impedance is 50 Ω at 3.3 V VDDO, default high drive. §7.6, Figure 16: a 50 Ω trace with an optional 0 Ω series resistor for EMI. The series termination is therefore the driver itself; the footprint is kept for tuning (**provisional**). |
| C701, C702 | 100 nF, one per supply pin | §7.1: 0.1–1.0 µF per supply pin, as close as possible, no vias. |
| X701, R706, C703 | 25 MHz 3.3 V CMOS oscillator **CJO05-250003320B30**, LCSC C712741 → 0 Ω → `osc_25` | JSCJ spec rev1.0: pin 1 enable (high or open = run; tied to `FPGA_3V3`), 2 GND, 3 output, 4 VDD. The KiCad `Oscillator:ASE-xxxMHz` symbol has the same pin order. **Footprint provisional:** the KiCad ASE footprint's pads (1.3 × 1.1 mm, gaps 0.8/0.55 mm) are close to, but not the same as, the suggested pads (1.3 × 1.2 mm, gaps 0.9/0.5 mm). The crystal footprint matches YXC's suggested layout exactly. |

## HDMI block (removed in 0.2-av)

The 0.1-av sheet carried a type-A HDMI connector (J701), a TPD12S016 companion (U702), ULX3S-style 22 nF TMDS coupling (C704-C711) and the FPGA labels `hdmi_*`. All of it was removed on 2026-09-29; see [console-video-path.md](console-video-path.md) for the path that replaces it.

## Cartridge audio block

**Path:** socket contacts 31 `AUDIO_L_IN` and 62 `AUDIO_R_IN` → `SNES_AUDIO_L_IN`/`SNES_AUDIO_R_IN`. These are already root labels; the cartridge sheet passes them through untranslated, with test points. They feed an input network and then U703 **PCM1808PWR** (TSSOP-14, LCSC C55513, 28,147 in stock).

**ADC mode.** Straps follow TI SLES177B §8.2.2.1 (10 kΩ to VDD or GND):

- MD1 = H (R708 to `FPGA_3V3`) and MD0 = L (R709) select **master mode, 384 fs** (Table 2).
- FMT = L (R710) selects **I²S, 24-bit** (Table 3).

**ADC clock.** X702 is a 12.288 MHz 3.3 V oscillator, **CJO05-122883320B30** (LCSC C712747, 2,986 in stock; same pinout as X701). It drives SCKI through R707 (0 Ω, provisional). That gives **fs = 12.288 MHz / 384 = 32.000 kHz**, the 32 kHz row of Table 1. In master mode, BCK = 64 fs = 2.048 MHz (§7.3.5.1.1). BCK, LRCK and DOUT go to `adc_bck`, `adc_lrck` and `adc_dout` at VDD = `FPGA_3V3` levels.

**Supplies.**

- Analog VCC = `5V_PRE` through FB701 (Sunlord GZ1608D601TF, 600 Ω at 100 MHz, 200 mA, LCSC C1002) with 10 µF + 100 nF.
- Digital VDD = `FPGA_3V3` with 10 µF + 100 nF.
- VREF gets 10 µF + 100 nF (Figure 26 notes 2 and 3).
- AGND and DGND join GND at the device.

### Input level and impedance

**Evidence.**

- **Console load.** OpenSFC SHVC-CPU-01 Rev A at commit `6574450` (local netlist `.local/interface-research/opensfc.xml`). Each cartridge audio contact (P1.31 `SL.IN`, P1.62 `SR.IN`) is loaded by **200 Ω to GND** (R96/R95). It is also AC-coupled through 1 µF into a **10 kΩ** summing resistor (R62/R55) of an LM358 inverting mixer: 24 kΩ feedback, +9 V supply. The S-DSP path enters the same summing node through 10 kΩ. The console input is therefore 200 Ω ∥ 10 kΩ = **196 Ω** at audio frequencies.
- **A real cartridge source.** sd2snes Rev F at commit `cf7e21d` (the FXPAK Pro predecessor; local netlist):
  - A CS4344 DAC powered by `+3.3VDAC` drives 3.3 µF, then 10 kΩ to AGND, then **470 Ω** in series, with 10 nF at the contact.
  - The CS4344 full-scale output is 0.60/0.65/0.70 × VA Vp-p, with 100 Ω output impedance (Cirrus DS613F2). That is 2.15 Vp-p typical.
  - Into the 196 Ω console load this gives about **0.56 Vp-p** at the contact.
- **Missing data.** No manufacturer level is published for FXPAK Pro, Super EverDrive X5/X6, the Super Game Boy or other cartridges.
- **Worst case (derived).** The cartridge's only supply is +5 V. A cartridge source therefore cannot present more than **5.0 Vp-p** steady-state, whether DC-coupled from 0–5 V or AC-coupled. This also exceeds what the console's own mixer can pass before its LM358 output clips.

**Network per channel** (L: R711–R713, C722, C723; R: R714–R716, C724, C725):

| Element | Value | Why |
|---|---|---|
| R_load, contact to GND | 200 Ω | Presents the console's load, so each cartridge's level at the contact equals its level on a real console, whatever its source impedance. **Provisional:** the OpenSFC value should be confirmed on a real SHVC-CPU-01. |
| R_top / R_bot | 4.7 kΩ / 5.1 kΩ | Gain = (5.1 k ∥ 60 k) / (4.7 k + 5.1 k ∥ 60 k) = **0.500**. The 60 kΩ is the PCM1808 input impedance, typical value (§6.5). |
| C_aa, divider node to GND | 1 nF C0G | Thevenin resistance 4.7 k ∥ 5.1 k ∥ 60 k = 2.35 kΩ gives **fc = 67.7 kHz**: −0.24 dB at 16 kHz, about −30 dB at the 2.048 MHz modulator rate. The PCM1808 adds its own anti-alias filter (−3 dB at 1.3 MHz). Its decimation filter (stop band −65 dB) handles content near fs. |
| C_c, to VINx | 1 µF, X7R 25 V | Figure 26: 1 µF with the 60 kΩ input gives a 2.6 Hz high-pass, which also blocks any cartridge DC. TI shows an electrolytic; X7R is **provisional**. The DC across it is about 2.5 V (VREF = 0.5 VCC). |

**Resulting numbers** (computed by the verifier from the netlist values):

| Quantity | Value |
|---|---|
| ADC full scale | 0.6 × VCC Vp-p (§6.5): 3.00 Vp-p at 5.00 V, **2.85 Vp-p at 4.75 V**, the bottom of the provisional 5 V window in [power-architecture.md](power-architecture.md) |
| 5.0 Vp-p worst case at the ADC | **2.5 Vp-p**, with 1.14 dB headroom at 4.75 V |
| Full scale referred to the contact | 6.0 Vp-p at VCC = 5.00 V |
| sd2snes/FXPAK-class level | 0.56 Vp-p at the contact → 0.28 Vp-p at the ADC = **−20.6 dBFS**. PCM1808 dynamic range is 99 dB typical (95 dB minimum, 48 kHz, A-weighted), so about 78 dB remains below that level. |
| Input impedance at the contact | 200 Ω ∥ 9.4 kΩ = **195.8 Ω** (console 196.1 Ω). The verifier requires ±10 %. |
| Protection | A 5 V DC step at the contact moves VINx by at most 2.5 V around VREF, which stays inside the absolute-maximum range of −0.3 V to VCC + 0.3 V. |

### FPGA consequences (not implemented here)

- **Two unlocked 32 kHz clocks.**
  - The ADC's 32 kHz comes from its own ±20 ppm oscillator.
  - The SNES S-DSP's 32 kHz comes from the SNES master, which is ±20 ppm from the Si5351 crystal.
  - The two rates can differ by up to about 40 ppm, about 1.3 samples per second. The FPGA needs a small rate adapter before mixing into the stream the console reads (implemented: `sn64_audio_mix`, [cart-audio-implementation.md](cart-audio-implementation.md)).
- **Mix ratio.** On a console, the cartridge audio and the S-DSP output are summed with equal 10 kΩ weights. The FPGA needs the S-DSP's analog level at that summing node, which is not yet sourced, to reproduce the console's mix exactly. This is an open calibration item.

### SNES audio to the N64 edge (`N64_AUDIO_L/R`): not added

- No requirement asks for it: the SNES sound reaches the console digitally through the frame window ([console-video-path.md](console-video-path.md)). `SN64-07-03` forbids inventing an undocumented M64 interface.
- [n64-interface-notes.md](n64-interface-notes.md) and `n64-pin-map.csv` record contacts 24 and 49 as `analog_out_unverified`: "actual support/levels require separate validation; no direct digital FPGA drive in draft".
- SummerCart64 leaves them unconnected.
- The contacts stay reserved and isolated on the root, and nothing on this sheet drives them. If a later requirement adds the path, it needs a DAC and a buffer with a level sourced from the N64/M64 audio input, which is not in the evidence.

## Shared net-name contract (hierarchical ports)

| Group | Labels |
|---|---|
| Root labels | `GND`, `SNES_AUDIO_L_IN`, `SNES_AUDIO_R_IN` |
| Rails from the power sheet | `FPGA_3V3` (Si5351 VDD/VDDO, both oscillators, PCM1808 VDD, pull-ups/straps), `5V_PRE` (PCM1808 VCC through FB701) |
| To/from the FPGA sheet | `osc_25`, `si_clk0`, `si_clk1`, `si_scl`, `si_sda`, `adc_bck`, `adc_lrck`, `adc_dout` |

- Every FPGA-facing net is driven by a device referenced to `FPGA_3V3`.
- No 5 V net reaches any of them through a resistor or ferrite.
- Reference designators use the 700 series.

**Load estimates for the power budget** (datasheet maxima unless noted):

- On `FPGA_3V3`:
  - Si5351 IDD 24 mA typical / 38 mA maximum, plus IDDO 2.2 mA typical / 5.6 mA maximum per output.
  - Two oscillators, 10 mA maximum each.
  - PCM1808 IDD 5.9 mA typical / 8 mA maximum at 48 kHz.
- On `5V_PRE`:
  - PCM1808 ICC 8.6 mA typical / 11 mA maximum.

## Verification (real output, 2026-09-29, draft 0.2-av on the integrated root)

**ERC** on `hardware/sn64`: **0 errors**; the warning set is the project baseline (5 `isolated_pin_label` on reserved N64 labels, 5 `pin_to_pin` on the cartridge sheet). This sheet has zero violations of its own.

```
& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware/sn64/tools/verify_av_clock_sheet.py --project hardware/sn64
PASS: 27 AV/clock checks; ERC {'warning:isolated_pin_label': 5, 'warning:pin_to_pin': 5}

& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware/sn64/tools/verify_av_clock_sheet.py --project hardware/sn64 --negative-test
10 mutations, 10 detected (each mutated copy fails the listed checks); exit 0
```

**The negative test.** Each mutation must fail. The ten mutations are:

1. The crystal is lifted off XB.
2. An 8 pF crystal is fitted against register 183's 10 pF.
3. The `si_scl` pull-up is removed.
4. The `si_sda` pull-up goes to `5V_PRE`.
5. MD1 is strapped low (slave mode).
6. FMT is strapped high (left-justified).
7. Si5351 CLK2 is wired to a clock label (the pixel-clock output brought back).
8. Audio L/R are swapped at the ADC.
9. The divider's bottom resistor is open (gain 0.93).
10. A contract label is renamed.

**Limits.** This is static connectivity and arithmetic against datasheet tables only. It does not show:

- Si5351 jitter or accuracy at `SYSTEM_CLK`.
- Audio noise, crosstalk or the real cartridge levels.

## Sources (downloaded to `build/av-clock/datasheets/`, untracked; hashes also in `av-provenance.json`)

| Document | SHA-256 |
|---|---|
| Skyworks Si5351-B Rev 1.3 | `f3bc5285fccafa3fcd06e9a7fa6abb67fb43e8c23f6147b14caecc9a4851101f` |
| Skyworks AN619 Rev 0.8 | `0135b3a37195189e38cbd58ca504460814c691eeb1fdbe275806cfcd4783f36b` |
| TI PCM1808 SLES177B | `4ac1a7ec0c05ee972ba52ad8ebbd7cc661ce1c4dff59cf33429b684ca0595547` |
| Cirrus CS4344 DS613F2 | `e4cf72f7136c4c9f47be4683f7a0a36d702b673d446ba8b4d5c74dc37d062c16` |
| JSCJ CJO05-250003320B30 spec rev1.0 | `e0ed8f76b1afbb40081a66ac7ff67f8bac255912119d6042b4b563505e5df44e` |
| JSCJ CJO05-122883320B30 spec rev1.1 | `3e2cacb39cce36ff764f848c02785eaa0e46d6cd3f9fcfbb3cd8ab8c3c9c441a` |
| YXC X322525MMB4SI (YSX321SL) | `7bc18549e407d8e381075b0f5fc696e48cf0fa060aeee67971925f43cfdfbb8b` |

## Open items

1. **X701/X702 footprints.** Use the JSCJ suggested pads, or confirm that the ASE pads are acceptable.
2. **Console load.** Confirm the 200 Ω on a real SHVC-CPU-01. Measure FXPAK Pro, X5/X6 and Super Game Boy output levels into 196 Ω.
3. **FPGA work.** Mix calibration against the S-DSP level (the I²S receiver and the 32 kHz rate adapter are implemented).
4. **Power-sheet checks.** `FPGA_3V3` and `5V_PRE` sequencing (Si5351 §7.2 is satisfied by construction, since VDD and VDDO share one rail). PCM1808 behaviour when VCC is up and VDD is down.

## Integration edits (not applied by this task)

See the task report for the exact list. In short:

- Attach the sheet to the root (`--attach-root hardware/sn64/sn64.kicad_sch`).
- Add `SN64_AV` to `sym-lib-table`.
- Done (round-3 integration): pending pins connected at the root; `#FLG701`/`#FLG702` removed.
- Add power-budget rows.
- Add README, work-log and system-integration entries.
