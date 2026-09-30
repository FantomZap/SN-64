# Clock, HDMI and cartridge-audio schematic sheet

Draft 0.1-av, 2026-09-29. This is a schematic sheet, [`hardware/sn64/av-clock.kicad_sch`](../../hardware/sn64/av-clock.kicad_sch). It is **not yet attached to the root schematic**; attaching it is an integration edit, listed at the end. It passes a static netlist check and KiCad ERC on a validation copy of the project. **No PCB, signal-integrity simulation, HDMI compliance test, audio measurement or hardware test has been done.**

## Plain-language summary

This sheet holds four things:

- **Clock chip.** It makes the SNES master clock for both regions and the HDMI pixel clock.
- **Housekeeping oscillator.** 25 MHz, for the FPGA.
- **HDMI connector.** It comes with the small protection/level-shift chip that HDMI needs.
- **Audio input.** A stereo audio converter digitises the analog sound that some cartridges send back through the SNES socket, such as MSU-1 audio from an FXPAK Pro or sd2snes.

Every part number, pin and value is taken from a downloaded datasheet or a pinned open design. Values still to be tuned on the prototype are marked **provisional**.

## Files

| File | Role |
|---|---|
| `hardware/sn64/av-clock.kicad_sch` | The child sheet: 53 symbols, 25 hierarchical ports. |
| `hardware/sn64/tools/add_av_clock_sheet.py` | Authoring script, same house style as `add_cart_interface.py`: installed KiCad symbols embedded in the sheet, drawn symbols only where KiCad has none, provenance JSON, refuses to overwrite without `--force`. It never edits the real root; `--attach-root` attaches the sheet to a given root (used on the validation copy). |
| `hardware/sn64/libraries/SN64_AV.kicad_sym` | Drawn symbols for TI **TPD12S016PW** and TI **PCM1808PW**; neither is in the KiCad 10 library. |
| `hardware/sn64/libraries/av-provenance.json` | Source URL, revision and SHA-256 of every datasheet, pin tables and the facts used. |
| `hardware/sn64/tools/verify_av_clock_sheet.py` | Independent netlist and ERC check, plus `--negative-test`. |
| `hardware/sn64/validation/av-clock-check.json` | Result of the last passing check (run on the validation copy). |

## Clock block (implements [clock-plan.md](clock-plan.md), unchanged)

| Ref | Part | Source and check |
|---|---|---|
| U701 | **Si5351A-B-GTR**, MSOP-10, LCSC C504891 | KiCad `Oscillator:Si5351A-B-GT`. Its pins match Skyworks Si5351-B Rev 1.3, Table 20: 1 VDD, 2 XA, 3 XB, 4 SCL, 5 SDA, 6 CLK2, 7 VDDO, 8 GND, 9 CLK1, 10 CLK0. VDD and VDDO both come from `FPGA_3V3`; §7.2 requires VDDO to come up with or before VDD. |
| Y701 | 25 MHz crystal, **YXC X322525MMB4SI**, 3225, **CL 10 pF**, LCSC C70582 (34,212 in stock) | Datasheet (YSX321SL family): pins 1 and 3 are the crystal, 2 and 4 are GND; ESR ≤ 50 Ω (16–31 MHz); drive level up to 200 µW; C0 ≤ 3 pF. Si5351 Table 8 needs 25–27 MHz, CL 6–12 pF, ESR ≤ 150 Ω and a crystal rated for ≥ 100 µW. |
| — | **Load-capacitance cross-check** | `fpga/rtl/sn64_clock_init.sv` writes register 183 = `0xD2`. AN619 Rev 0.8 decodes that as bits 7:6 = `11` (internal CL = 10 pF) and bits 5:0 = `010010b`, the required reserved value. That matches the crystal's 10 pF. Si5351 §7.4: the internal load capacitance is used, so there are no external load capacitors. The verifier reads the register value from the RTL and fails if the two disagree. |
| R701, R702 | 4.7 kΩ pull-ups from `si_scl`/`si_sda` to `FPGA_3V3` | Si5351 Figure 5 (4.7 k shown), Table 20 (at least 1 kΩ, to VDD). I²C address 0x60, 400 kHz from `sn64_clock_init`. |
| R703–R705 | **0 Ω** series resistors: CLK0 → `si_clk0` (NTSC 21.4772727 MHz), CLK1 → `si_clk1` (PAL 21.28137 MHz), CLK2 → `si_clk2` (pixel 27.0197947 MHz) | Si5351 Table 5: the output impedance is 50 Ω at 3.3 V VDDO, default high drive. §7.6, Figure 16: a 50 Ω trace with an optional 0 Ω series resistor for EMI. The series termination is therefore the driver itself; the footprint is kept for tuning (**provisional**). |
| C701, C702 | 100 nF, one per supply pin | §7.1: 0.1–1.0 µF per supply pin, as close as possible, no vias. |
| X701, R706, C703 | 25 MHz 3.3 V CMOS oscillator **CJO05-250003320B30**, LCSC C712741 → 0 Ω → `osc_25` | JSCJ spec rev1.0: pin 1 enable (high or open = run; tied to `FPGA_3V3`), 2 GND, 3 output, 4 VDD. The KiCad `Oscillator:ASE-xxxMHz` symbol has the same pin order. **Footprint provisional:** the KiCad ASE footprint's pads (1.3 × 1.1 mm, gaps 0.8/0.55 mm) are close to, but not the same as, the suggested pads (1.3 × 1.2 mm, gaps 0.9/0.5 mm). The crystal footprint matches YXC's suggested layout exactly. |

## HDMI block

**TMDS network: reused from ULX3S, as the [FPGA board selection](fpga-board-selection.md) pins it.** In [`gpdi.sch`](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/gpdi.sch) at commit `6a92cec` (SHA-256 `2ff8d987…4b0f5b1164d`), each FPGA TMDS pin drives its connector pin through a **22 nF series capacitor** (C38–C45, 0603). There is **no series resistor**. The ULX3S sheet carries the note "SINGLE ENDED - NOT DIFFERENTIAL", and the SN64 trial LPF drives these pins as `LVCMOS33D`. The task brief described a "series-resistor network"; the pinned source has capacitors only, and this sheet copies the source: C704–C711 are 22 nF.

| Lane | FPGA labels | Series C | Connector pins (J701) | TPD12S016 ESD pins (U702) |
|---|---|---|---|---|
| D2 | `hdmi_d2_p` / `hdmi_d2_n` | C704 / C705 | 1 / 3 | 23 / 22 |
| D1 | `hdmi_d1_p` / `hdmi_d1_n` | C706 / C707 | 4 / 6 | 21 / 20 |
| D0 | `hdmi_d0_p` / `hdmi_d0_n` | C708 / C709 | 7 / 9 | 18 / 17 |
| Clock | `hdmi_ck_p` / `hdmi_ck_n` | C710 / C711 | 10 / 12 | 16 / 15 |

- **U702 TPD12S016PWR** (TSSOP-24, LCSC C201665, 3,497 in stock) is the ESD and level-shift companion. It sits on the connector side of the capacitors (TI SLLSE96F; pin table in the provenance file). It provides:
  - TMDS ESD, rated 6 V absolute on D/CLK and ±8 kV IEC contact.
  - DDC and CEC level shifting: A side referenced to VCCA = `FPGA_3V3`, B side to its own `5V_OUT`.
  - The HPD buffer: `HPD_A` is referenced to VCCA, so `hdmi_hpd` is a 3.3 V signal.
  - The HDMI **+5V pin (18)**, from its **55 mA current-limited load switch**, with VCC5V = `5V_PRE`. The connector's +5V is not connected to `5V_PRE` directly; the verifier checks this.
- **Enable pins.** `LS_OE` and `CT_HPD` are tied to VCCA, the "fully on" row of Table 1, so the chip is active whenever `FPGA_3V3` is up. The contract has no FPGA enable pin for it.
- **Pull-ups.** None are fitted on DDC, CEC or HPD; §7.3.15 says none are needed.
- **Bring-up caution.** The A-side input low level (VIL) is at most 0.082 × VCCA, about 0.27 V at 3.3 V. The FPGA's open-drain DDC master must pull the line fully to ground. Check this on hardware.
- **CEC.** There is no FPGA CEC label in the contract. `CEC_A` goes to test point TP701 and has an internal pull-up. The optional integration edit `hdmi_cec` is listed below.
- **Utility/HEC pin (14).** Not connected.
- **J701: Amphenol 10029449-111RLF** (LCSC C427307, 1,905 in stock). This is the part ULX3S v1.8.1+ uses, and its sheet carries the same LCSC number. Pin numbering is the standard type-A order: the KiCad `Connector:HDMI_A` symbol and the ULX3S connector wiring agree (1 D2+, 2 D2 shield … 17 GND, 18 +5V, 19 HPD). Shields, GND and the shell go to GND.
  - **Footprint provisional.** KiCad's `HDMI_A_Amphenol_10029449-x01xLF_Horizontal` names the -001/-101 variants. The drawing LCSC serves (10029449 rev Y) lists -001/-101/-002 and **not -111RLF**. Get Amphenol's -111RLF drawing before layout.
  - **Mechanical fit** of the side-mounted connector is not checked.

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
  - The two rates can differ by up to about 40 ppm, about 1.3 samples per second. The FPGA needs a small rate adapter before mixing into the HDMI stream (`sn64_av_out` sends at the core's rate).
- **Mix ratio.** On a console, the cartridge audio and the S-DSP output are summed with equal 10 kΩ weights. The FPGA needs the S-DSP's analog level at that summing node, which is not yet sourced, to reproduce the console's mix exactly. This is an open calibration item.

### SNES audio to the N64 edge (`N64_AUDIO_L/R`): not added

- No requirement asks for it. `SN64-07-01` requires an **independent** digital A/V output. `SN64-07-03` (M64 single HDMI) forbids inventing an undocumented M64 interface.
- [n64-interface-notes.md](n64-interface-notes.md) and `n64-pin-map.csv` record contacts 24 and 49 as `analog_out_unverified`: "actual support/levels require separate validation; no direct digital FPGA drive in draft".
- SummerCart64 leaves them unconnected.
- The contacts stay reserved and isolated on the root, and nothing on this sheet drives them. If a later requirement adds the path, it needs a DAC and a buffer with a level sourced from the N64/M64 audio input, which is not in the evidence.

## Shared net-name contract (hierarchical ports)

| Group | Labels |
|---|---|
| Root labels | `GND`, `SNES_AUDIO_L_IN`, `SNES_AUDIO_R_IN` |
| Rails from the power sheet | `FPGA_3V3` (Si5351 VDD/VDDO, both oscillators, TPD12S016 VCCA, PCM1808 VDD, pull-ups/straps), `5V_PRE` (TPD12S016 VCC5V → HDMI +5V; PCM1808 VCC through FB701) |
| To/from the FPGA sheet | `osc_25`, `si_clk0`, `si_clk1`, `si_clk2`, `si_scl`, `si_sda`, `hdmi_d0_p`, `hdmi_d0_n`, `hdmi_d1_p`, `hdmi_d1_n`, `hdmi_d2_p`, `hdmi_d2_n`, `hdmi_ck_p`, `hdmi_ck_n`, `hdmi_hpd`, `hdmi_scl`, `hdmi_sda`, `adc_bck`, `adc_lrck`, `adc_dout` |

- Every FPGA-facing net is driven by a device referenced to `FPGA_3V3`.
- No 5 V net reaches any of them through a resistor or ferrite. The TMDS lines reach the connector only through 22 nF capacitors.
- Reference designators use the 700 series.

**Load estimates for the power budget** (datasheet maxima unless noted):

- On `FPGA_3V3`:
  - Si5351 IDD 24 mA typical / 38 mA maximum, plus IDDO 2.2 mA typical / 5.6 mA maximum per output.
  - Two oscillators, 10 mA maximum each.
  - PCM1808 IDD 5.9 mA typical / 8 mA maximum at 48 kHz.
  - TPD12S016 ICCA about 13 µA typical.
- On `5V_PRE`:
  - HDMI +5V, up to the 55 mA limit.
  - TPD12S016 ICC5V about 200 µA typical.
  - PCM1808 ICC 8.6 mA typical / 11 mA maximum.

## Verification (real output, 2026-09-29)

Validation copy: `build/av-clock/proj`. It is a copy of `hardware/sn64` with this sheet attached to the copied root by `add_av_clock_sheet.py --attach-root`; `build/av-clock/regen.sh` rebuilds it.

**ERC** on the copy: **0 errors**. The warning set is identical to the unmodified project: 32 `isolated_pin_label` on the root and 5 `pin_to_pin` on the cartridge sheet, all pre-existing. This sheet has zero violations of its own.

```
& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware/sn64/tools/verify_av_clock_sheet.py --project build/av-clock/proj
PASS: 30 AV/clock checks; ERC {'warning:isolated_pin_label': 32, 'warning:pin_to_pin': 5}

& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware/sn64/tools/verify_av_clock_sheet.py --project build/av-clock/proj --negative-test
12 mutations, 12 detected (each mutated copy fails the listed checks); exit 0
```

**The negative test.** Each mutation must fail. The twelve mutations are:

1. The crystal is lifted off XB.
2. An 8 pF crystal is fitted against register 183's 10 pF.
3. The `si_scl` pull-up is removed.
4. The `si_sda` pull-up goes to `5V_PRE`.
5. MD1 is strapped low (slave mode).
6. FMT is strapped high (left-justified).
7. The `hdmi_d1_n` capacitor lands on D1+.
8. TPD12S016 VCCA goes on `5V_PRE`.
9. HDMI +5V comes straight from `5V_PRE`.
10. Audio L/R are swapped at the ADC.
11. The divider's bottom resistor is open (gain 0.93).
12. A contract label is renamed.

A directly faulted copy (`build/av-clock/proj-fault`, MD1 strapped to GND) makes the ordinary check return `status: fail`, `adc_straps_i2s_master_fs_32kHz`, exit 1.

**Limits.** This is static connectivity and arithmetic against datasheet tables only. It does not show:

- Si5351 jitter or accuracy at `SYSTEM_CLK`.
- The TMDS eye through 22 nF capacitors and TPD12S016 capacitance at 135 MHz × 10.
- Sink acceptance.
- DDC low-level margin.
- Audio noise, crosstalk or the real cartridge levels.

## Sources (downloaded to `build/av-clock/datasheets/`, untracked; hashes also in `av-provenance.json`)

| Document | SHA-256 |
|---|---|
| Skyworks Si5351-B Rev 1.3 | `f3bc5285fccafa3fcd06e9a7fa6abb67fb43e8c23f6147b14caecc9a4851101f` |
| Skyworks AN619 Rev 0.8 | `0135b3a37195189e38cbd58ca504460814c691eeb1fdbe275806cfcd4783f36b` |
| TI TPD12S016 SLLSE96F | `10d63c0775c5a8d9893982de205c02fd9611980ad08de889d7c5324c6afdfd58` |
| TI PCM1808 SLES177B | `4ac1a7ec0c05ee972ba52ad8ebbd7cc661ce1c4dff59cf33429b684ca0595547` |
| Cirrus CS4344 DS613F2 | `e4cf72f7136c4c9f47be4683f7a0a36d702b673d446ba8b4d5c74dc37d062c16` |
| JSCJ CJO05-250003320B30 spec rev1.0 | `e0ed8f76b1afbb40081a66ac7ff67f8bac255912119d6042b4b563505e5df44e` |
| JSCJ CJO05-122883320B30 spec rev1.1 | `3e2cacb39cce36ff764f848c02785eaa0e46d6cd3f9fcfbb3cd8ab8c3c9c441a` |
| YXC X322525MMB4SI (YSX321SL) | `7bc18549e407d8e381075b0f5fc696e48cf0fa060aeee67971925f43cfdfbb8b` |
| Amphenol FCI 10029449 rev Y | `a80c0a2657d1e8131e508dd46b350ff329bb561398fcdf69d11fa32f9cb6fcfe` |
| ULX3S `gpdi.sch` @6a92cec | `2ff8d987b7f167ec0c0f7396bb11f8040d79a0289ab2d4a73ebde4b0f5b1164d` |
| ULX3S `LICENSE.md` @6a92cec | `cdaaa3f0c2d1dbb538844077fd7a1d9d43c890d0745b20d8aa0717b583d6af9f`, the same as recorded in fpga-board-selection.md |

## Open items

1. **J701 footprint.** Get the -111RLF drawing, or select a -101RLF/-001RLF part that KiCad's footprint names. Check the side-opening mechanics.
2. **X701/X702 footprints.** Use the JSCJ suggested pads, or confirm that the ASE pads are acceptable.
3. **HDMI bring-up.**
   - Measure the TMDS eye with 22 nF coupling plus the TPD12S016.
   - Check the DDC low level from the FPGA (VIL ≤ 0.082 × VCCA).
   - Test sink acceptance.
4. **Console load.** Confirm the 200 Ω on a real SHVC-CPU-01. Measure FXPAK Pro, X5/X6 and Super Game Boy output levels into 196 Ω.
5. **FPGA work.**
   - An I²S receiver.
   - A 32 kHz rate adapter.
   - Mix calibration against the S-DSP level.
   - Place `si_clk0`/`si_clk1` on primary clock input pins and `si_clk2` where it can feed the TMDS PLL (FPGA sheet).
6. **Power-sheet checks.** `FPGA_3V3` and `5V_PRE` sequencing (Si5351 §7.2 is satisfied by construction, since VDD and VDDO share one rail). PCM1808 behaviour when VCC is up and VDD is down.
7. **Optional FPGA-controlled pins.** `hdmi_cec` (TPD12S016 CEC_A) and TPD12S016 `CT_HPD`/`LS_OE` could become FPGA pins, but each needs a contract change.

## Integration edits (not applied by this task)

See the task report for the exact list. In short:

- Attach the sheet to the root (`--attach-root hardware/sn64/sn64.kicad_sch`).
- Add `SN64_AV` to `sym-lib-table`.
- Done (round-3 integration): pending pins connected at the root; `#FLG701`/`#FLG702` removed.
- Add a `THIRD_PARTY.md` row for the ULX3S TMDS-coupling reuse.
- Add power-budget rows.
- Add README, work-log and system-integration entries.
