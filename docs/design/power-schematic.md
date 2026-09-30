# Power schematic sheet (draft 0.1-power)

Snapshot 2026-09-29. This implements the recorded [power architecture](power-architecture.md) as a native KiCad child sheet, [hardware/sn64/power.kicad_sch](../../hardware/sn64/power.kicad_sch). It is authored by [add_power_sheet.py](../../hardware/sn64/tools/add_power_sheet.py) and checked by [verify_power_sheet.py](../../hardware/sn64/tools/verify_power_sheet.py). **Schematic candidate only.** It has no PCB and no measured load, and nothing here has been powered. The sheet is **not yet attached to the root schematic**; the integration steps are listed at the end. Values that depend on unmeasured cartridge or FPGA current are marked **PROV** (provisional).

## Plain-language summary

The adapter can take power from the N64 cartridge slot (3.3 V) or from the side USB-C port (5 V). Two protected electronic fuses pick one source and never connect the two together. USB wins only when the USB-C source advertises at least 1.5 A. A 5 V buck-boost regulator makes a clean 5 V from whichever source is active. Three small regulators then make the FPGA's 1.1 V, 2.5 V and 3.3 V.

The cartridge gets its 5 V through a third electronic fuse that is **off unless the FPGA asks for it**. The 3.3 V translator rail has its own switch, also off by default. Six window monitors, a reset supervisor and a temperature switch report back to the FPGA. Every report is wired so that a missing supply reads as "not OK".

## Blocks, parts and availability

LCSC numbers and stock come from the pcbparts database query of 2026-09-29. Re-check them before ordering.

| Ref | Part | LCSC (stock) | Role |
|---|---|---|---|
| U301 | TUSB320IRWBR | C80170 (1628) | USB-C CC current-class detector: UFP, GPIO mode |
| U302 | TPS259470LRPWR | C3662793 (2797) | USB target-input eFuse, **priority** channel |
| U303 | TPS259470LRPWR | same | HOST_3V3 input eFuse, **auxiliary** channel |
| U304 | TPS63070RNMR | C109322 (25100) | System regulator: SYS_VIN to **5V_PRE** |
| U305–U307 | TLV62569DBVR | C141836 (246272) | FPGA_1V1 / FPGA_2V5 / FPGA_3V3 bucks (ULX3S topology) |
| U308 | TPS22918DBVR | C131941 (18885) | INTERFACE_3V3 load switch with QOD |
| U309 | TPS259470LRPWR | same | Cartridge eFuse to SNES_5V_CART, default off |
| U310–U315 | TPS3700DDCR | C33002 (8920) | Window monitors |
| U316 | TPS3808G01DBVR | C19653 (18100) | board_reset_n supervisor |
| U317 | TMP302ADRLR | C2877557 (39857) | Board overtemperature switch |
| Q301–Q308 | BSS138BK,215 | C282529 (52253) | Permission, interlock, enable and discharge FETs |
| L301 | APV PNR4020-1R5M | C54620133 (7449) | 1.5 µH for the TPS63070 (Isat 7.7 A) |
| L302–L304 | FNR4030S2R2MT | C167869 (67195) | 2.2 µH for the TLV62569 bucks (Isat 5.8 A) |

Generic resistors and capacitors carry values only; monitor and feedback dividers are E192 0.1 %. Five symbols are drawn from TI pin tables because KiCad 10 has none: TPS259470L, TPS63070, TPS3700, TPS22918 and TMP302. Their pins and sources are in [power-provenance.json](../../hardware/sn64/libraries/power-provenance.json). The other symbols are installed KiCad library symbols, used unmodified.

**Footprints (2026-09-29):** RPW0010A (eFuses), RNM0015A (TPS63070) and the PNR4020 inductor are drawn from the manufacturers' land-pattern drawings by `tools/make_power_footprints.py` (TI 4225183/A example board layout; TI SLVSC58B example board layout, with VOUT 7+8 and VIN 12+13 as joined U pads since each pair is one signal; APV PNR datasheet p.2: 1.20 × 3.50 pads, 1.80 gap). L302–L304 use KiCad's `Inductor_SMD:L_Changjiang_FNR4030S`, which matches the Changjiang FNR datasheet (a 1.9, b 1.1, c 3.7). All 419 main-board parts now carry a footprint that loads; none has been built or stencil-checked.

## Input selection (qualified, never paralleled)

This follows TI SLVSFC9C §8.2.5, Figure 8-14 ("Option 3"), with both channels using the TPS259470x.

- **Priority (USB).** U302 AUXOFF asserts only once its input is valid and inrush has finished (§7.3.10). Q304 then clamps the U303 EN/UVLO pin low, so the host path turns off.
- **Changeover.** Both eFuses have true reverse-current blocking (SLVSFC9C §7.3.7). When USB (5 V) arrives while the host (3.3 V) is feeding SYS_VIN, U303 blocks reverse current before AUXOFF turns it off. When USB is lost, U303 restarts through its dVdt ramp, so SYS_VIN droops. Equation 22 gives the droop, which depends on load and needs measurement.
- **Rationale.** USB is supplemental power, so when it is qualified it carries the load. This is the recorded "qualified source selection" and it adds no new policy.

**USB permission is default-off, in hardware.** U302 can enable only when **TUSB320 OUT1 is actively low**, meaning a 1.5 A or 3 A advertisement (SLLSEN9F Table 7-3: unattached HH, default HL, 1.5 A LH, 3 A LL), **and** USB_3V3 is present.

| State | TC_OUT1 | USB_PERMIT (Q301 drain) | USB_INHIBIT (Q302 drain) | Q303 | U302 |
|---|---|---|---|---|---|
| Unattached, or default USB current | H | L | pulled to VBUS | on | EN clamped, **off** |
| 1.5 A or 3 A advertised | L | H (USB_3V3) | L | off | EN = UVLO divider |
| USB_3V3 absent, or TUSB320 dead | floats H / pull-up gone | L | pulled to VBUS | on | **off** |

TUSB320 straps are taken from SLLSEN9F Table 5-1:

- PORT = GND (UFP).
- ADDR open (GPIO mode).
- EN_N = GND.
- VBUS_DET through 887 kΩ, the RVBUS typical (range 855–920 kΩ).
- VDD = USB_3V3. Power register PWR-L06 places this detector on USB_3V3. Its VDD maximum is 5 V, so it cannot run from VBUS.

In dead-battery mode the TUSB320 presents Rd of 5.1 kΩ ±20% (§7.4.3). A blank board with no USB_3V3 is therefore still seen as a sink, and the source turns VBUS on. That is why the USB sheet's R101/R102 must become DNP rather than stay in parallel, as the architecture doc says.

The USB current limit is set for the 1.5 A class and is also used for 3 A: ILIM = 3334/RILM (Equation 7). With RILM = 2.55 kΩ the nominal is **1.307 A PROV**. My interpolation between the Table 6.5 points is roughly 1.11–1.50 A; this is an estimate, not a datasheet point.

| eFuse divider (Eq. 1/2: V = 1.20 V × (R1+R2)/R2, R2 = 100 k 1 %) | R1 | Rising nom (worst) | Falling nom (worst) |
|---|---|---|---|
| U302 UVLO, USB_VBUS | 267k | 4.404 V (4.279–4.554) | 4.000 V (3.892–4.156) |
| U302 OVLO | 383k | 5.796 V (5.624–6.002) | 5.265 V |
| U303 UVLO, HOST_3V3 | 150k | 3.000 V (2.922–3.095) | 2.725 V (2.658–2.824) |
| U303 OVLO | 215k | 3.780 V (3.676–3.906) | 3.433 V |
| U309 UVLO, 5V_PRE | 287k | 4.644 V (4.511–4.804) | 4.218 V |
| U309 OVLO | 357k | 5.484 V (5.323–5.677) | 4.981 V (4.841–5.181) |

Worst-case bands use VUVLO(R)/VOV(R) of 1.183–1.223 V and VUVLO(F) of 1.076–1.116 V from SLVSFC9C Table 6.5, with 1 % resistors.

**U302 checks.** Its UVLO worst-case maximum is 4.554 V and its OVLO worst-case minimum is 5.62 V. These were compared against the commonly quoted Type-C vSafe5V range of 4.75–5.5 V. That range comes from the USB Type-C/PD specifications, which were **not downloaded for this task**. Confirm it against the specification before closing SN64-08-01.

**U303 checks.** The host OVLO minimum of 3.68 V is above 3.3 V +5 %. The host current limit uses the largest allowed RILM, 6.65 kΩ, which is the recommended maximum. That gives **0.501 A nominal (0.425–0.575 A, Table 6.5)**. This cannot be set below the M64 U33 limiter's 500 mA setting, so upstream protection of the host still relies on the host's own limiter. Host-only budget closure remains open, as recorded.

Other eFuse settings:

- **dVdt.** Both input eFuses use 1.5 nF. Equation 4 gives SR = 2000/C(pF) ≈ 1.33 V/ms. Nominal SYS_VIN capacitance is C312–C315, 64 µF, before derating. Equation 3 then gives an inrush of about 85 mA, scaling with IdVdt 0.81–3.82 µA to roughly 31–147 mA. The capacitor rating follows the higher rail (note 3 of the recommended conditions).
- **ITIMER.** 1.2 nF gives t = VITIMER × C / IITIMER ≈ 1.51 × 1.2 / 1.8 ≈ 1.0 ms of transient blanking (Equation 8). **PROV.**

## System regulator and FPGA rails

**Decision (accepted 2026-09-29).** The architecture lists a "system regulator", 5V_PRE (TPS63070 candidate) and the FPGA rails. This sheet realises the system regulator as U304 TPS63070, with SYS_VIN at 2.7–6 V and forced PWM for ±1 % FB accuracy. U304's regulated 5.00 V output **is** 5V_PRE, and 5V_PRE is also the input to the three FPGA bucks. The reasons:

- The TLV62569's recommended VIN is 2.5–5.5 V, and the USB OVLO band reaches 6.0 V.
- FPGA_3V3 cannot be regulated by a buck from a 3.0 V host input.

The cost is one extra conversion stage on the FPGA power. Running the bucks directly from SYS_VIN would need a buck-boost for FPGA_3V3 and a USB OVLO cut to ≤5.35 V, so the 5V_PRE feed is kept. This refines only the "SYS → FPGA regulators" arrow of the architecture; no recorded decision is changed.

| Rail | Regulator | Feedback (R1/R2, 0.1 %) | Nominal | Worst case with VFB tolerance | ECP5 requirement (FPGA-DS-02012-3.4 Table 3.2) |
|---|---|---|---|---|---|
| 5V_PRE | TPS63070, VFB 0.8 V ±1 % in PWM (SLVSC58B) | 232k / 44.2k | 4.999 V | 4.941–5.058 V | — |
| FPGA_1V1 | TLV62569, VFB 0.588–0.612 V (SLVSDG1C Eq. 2) | 100k / 120k | 1.100 V | 1.077–1.123 V | VCC 1.045–1.155 V |
| FPGA_2V5 | TLV62569 | 361k / 114k | 2.500 V | 2.446–2.554 V | VCCAUX 2.375–2.625 V |
| FPGA_3V3 | TLV62569 | 459k / 102k | 3.300 V | 3.229–3.372 V | VCCIO ≤3.465 V (LVCMOS33 row still to confirm) |

Component values:

- **TLV62569 stages.** Each uses 2.2 µH with 22 µF in and 2×22 µF out. This is the SLVSDG1C Table 4 "++" combination for 1.1 V, and the ULX3S rev 1.0.8 power sheet uses 22 µF parts. Each also has a 6.8 pF feed-forward capacitor, as recommended for an R2 of about 100 kΩ.
- **TPS63070.** 1.5 µH, VAUX 100 nF, 3×22 µF out and 2×10 µF + 2×22 µF on SYS_VIN.

**Sizing and ramp.**

- **Current.** Each TLV62569 is rated 2 A. The only cited LFE5U-85F numbers are static typicals from Table 3.8: ICC 212 mA, ICCAUX 26 mA, ICCIO 0.5 mA per bank. Dynamic current needs the Lattice Power Calculator. **PROV.**
- **Ramp.** tSS is 800 µs (TLV62569DBV), so the ramps are about 1.4 V/ms (1V1) to 4.1 V/ms (3V3). This is inside the ECP5 tRAMP limit of 0.01–10 V/ms (Table 3.3) if the ramp is monotonic.

**Sequencing (ECP5 §3.5).** In master-SPI mode, VCCIO8 must be above the flash VIH before VCC or VCCAUX reaches POR. Otherwise PROGRAMN or INITN must be held low. On this sheet:

- PG_5V enables all three bucks together, so their order is not guaranteed.
- The second option is used instead. U316 TPS3808G01 holds **board_reset_n** low until all FPGA rails are in window (MR = fpga_rails_ok) and FPGA_3V3 is above 3.033 V (SENSE 649k/100k; 2.92–3.15 V worst case). It then waits the CT-open delay of 12/20/28 ms (SBVS050N §6.5).
- The parallel FPGA sheet (`fpga.kicad_sch`) already holds **PROGRAMN** low through its U407 until **fpga_rails_ok**, which is this sheet's rail-window output. That meets §3.5 with no extra wiring; board_reset_n remains the user-logic reset.

## Cartridge 5 V (U309) and INTERFACE_3V3 (U308)

**Cartridge enable (default low).** EN/UVLO is clamped by Q306 while CART_INHIBIT is pulled to 5V_PRE. cart_5v_enable is an FPGA output that drives Q305; when high it pulls CART_INHIBIT low.

- **Pull-down.** cart_5v_enable has a 1 kΩ pull-down. The ECP5 active pull-up is at most 150 µA (FPGA-DS-02012 IPU), which gives at most 0.15 V. That is below the BSS138BK VGSth minimum of 0.48 V (Nexperia BSS138BK Rev. 1). A 100 kΩ pull-down would fail, and the negative test proves it.
- **Latched faults.** They clear only when EN is pulled below VSD, which the FPGA does by dropping cart_5v_enable (SLVSFC9C §7.3.9). This matches the sequencer's deliberate fault_clear.

**Cartridge eFuse settings.**

| Setting | Value | Source / math |
|---|---|---|
| ILIM | 3.32 kΩ → **1.004 A**, Table 6.5 range 0.850–1.150 A | **PROV.** Cartridge peaks are unmeasured. |
| dVdt | 680 pF → SR 2.94 V/ms, rise about 1.7 ms | Assumes an unmeasured 33 µF on the socket rail: the cart sheet's 10 µF plus locals plus 22 µF assumed for the cartridge. Inrush 97 mA (36–168 mA). **PROV.** |
| ITIMER | 1.2 nF → about 1.0 ms | **PROV.** |
| UVLO/OVLO | See the table above | The OVLO lower bound of 5.32 V is above the 5V_PRE maximum of 5.06 V, so there are no false trips. |

**Cartridge rail discharge.** Q307 with R328 (470 Ω, 0805) discharges SNES_5V_CART whenever the rail is inhibited: τ ≈ 470 × 33 µF ≈ 16 ms, **PROV**.

- The architecture asks for this discharge to be "inhibited if an externally energized output is detected". This sheet instead **bounds** it. An externally held 5.5 V rail draws only 11.7 mA, 64 mW, inside the 0805 rating.
- Detection-based inhibit is an open item.
- The discharge works only while 5V_PRE is present, because the gate pull-up comes from 5V_PRE.

**INTERFACE_3V3 (U308).**

- **Input and enable.** VIN is FPGA_3V3. ON is iface_rail_enable with a 1 kΩ pull-down (≤0.15 V against VIL,ON ≤0.5 V, SLVSD76C).
- **Rise time.** CT 470 pF: Equation 3 gives SR = 0.55 × 470 + 30 = 288.5 µs/V, a 3.3 V rise of about 0.95 ms. Inrush into the cart sheet's roughly 11 µF is about 38 mA.
- **Discharge.** QOD runs through R341 100 Ω, so RQOD = RPD (25 typ/35 max Ω at 3.3 V) + 100 Ω. That gives τ ≈ 1.5 ms and a peak of 26 mA.
- **Sequencing.** The FPGA sequencer enables this rail only after cart 5 V, which is recorded behaviour.

## Monitors and the FPGA contract

TPS3700 (SBVS187G): OUTA goes low when INA+ < VIT+ − Vhys, and OUTB goes low when INB− > VIT+.

- **Dividers.** R1 (rail→INA+), R2 (INA+→INB−), R3 (INB−→GND). UV falling = 0.3945 V × RT/(R2+R3). OV rising = 0.400 V × RT/R3 (Equations 1–4). The two outputs are wired together.
- **Worst-case bands.** These use VIT+ 396–404 mV, VIT− 387–400 mV and 0.1 % resistors.
- **Divider current.** At least 100× the ±25 nA input current (6–12 µA).

| Monitor | Rail | R1 / R2 / R3 | UV falling nom (worst) | OV rising nom (worst) | Notes |
|---|---|---|---|---|---|
| U310 → host_3v3_ok | SYS_VIN | 442k / 37.4k / 33.6k | 2.850 (2.791–2.895) | 6.107 (6.035–6.180) | Selected system input valid. The sequencer's "host/USB system rails". |
| U311 | FPGA_1V1 | 115k / 3.74k / 64.2k | 1.062 (1.041–1.078) | 1.140 (1.127–1.153) | **Marginal:** the UV band overlaps the regulator minimum (1.077) by 1 mV and ECP5 1.045 by 4 mV. |
| U312 | FPGA_2V5 | 287k / 3.16k / 53.0k | 2.411 (2.361–2.448) | 2.590 (2.560–2.620) | **Marginal:** the UV band overlaps the regulator minimum (2.446) by 2 mV and is 14 mV below the ECP5 minimum. |
| U313 | FPGA_3V3 | 277k / 2.37k / 37.0k | 3.170 (3.104–3.220) | 3.420 (3.380–3.461) | The 3.465 V maximum holds. |
| U314 → cart_5v_ok | **SNES_5V_CART (socket side)** | 530k / 3.79k / 44.2k | 4.751 (4.653–4.826) | 5.231 (5.169–5.293) | Provisional 4.75–5.25 V window from the architecture. |
| U315 → iface_rail_ok | INTERFACE_3V3 (switch output) | 232k / 5.05k / 30.1k | 2.998 (2.936–3.045) | 3.550 (3.508–3.592) | SN74LVC4245A B-side ≤3.6 V. |

U311–U313 wire-AND into **fpga_rails_ok**.

| Contract signal | Dir (sheet) | Polarity / level | Fail-safe behaviour |
|---|---|---|---|
| host_3v3_ok, fpga_rails_ok, cart_5v_ok, iface_rail_ok | output | 1 = in window. Open-drain, 10 kΩ to FPGA_3V3. | The monitors are powered from FPGA_3V3, the same rail as the pull-up. Below UVLO, OUTA is driven low (SBVS187G note 3), and loss of the rail removes the pull-up. The TPS3700 needs VDD > 1.8 V for 450 µs before its outputs are valid; board_reset_n (≥12 ms) covers this. |
| efuse_fault_n | output | 0 = fault. FLT open drain, R329 10k pull-up to FPGA_3V3 like the other monitor outputs (FLT rated -0.3 to 6.5 V, leakage ±1 µA, SLVSFC9C). | Changed 2026-09-29 from a 12.1k/20k 5V_PRE divider: that would back-drive left-bank ball K4 while FPGA_3V3 ramps (ECP5 DS-02012 3.4 section 3.6, left/right banks are not hot-socket capable). A missing 5V_PRE is caught by cart_5v_ok and the sequencer's rail timeout. FLT also asserts on reverse current (Table 7-3). |
| overtemp | output | 1 = hot. TMP302A OUT (open drain, active low) → Q308 → 10 kΩ pull-up. | A hot sensor, a dead sensor (its pull-up to its own VS) or an open Q308 all read 1. The trip is TRIPSET1 = TRIPSET0 = VS, 65 °C, with HYSTSET = VS for 10 °C hysteresis (SBOS488E Tables 1–2). **PROV** pending a thermal budget. |
| board_reset_n | output | 0 = reset. TPS3808 open drain, 10 kΩ to FPGA_3V3. | RESET is valid for VDD ≥ 0.8 V. |
| cart_5v_enable, iface_rail_enable | input | 1 = enable. 1 kΩ pull-downs. | An unconfigured FPGA reads OFF. |

Temperature *telemetry* (SN64-08-13) is not provided by this sheet, which offers only a threshold.

## Verification (run 2026-09-29)

The sheet was validated on a **copy**, `build/power-sheet/proj`, prepared as follows:

1. `add_power_sheet.py --attach-only` attached the sheet to the copied root.
2. `build/power-sheet/integrate_copy.py` applied the USB and cart integration edits listed below.

| Check | Result |
|---|---|
| `verify_power_sheet.py --project build/power-sheet/proj` | **PASS, 23/23.** Covers pin maps, source isolation, the priority interlock, the USB permission chain, TUSB320 straps, the cart and interface default-off paths, discharge bounds, socket-side monitors, contract labels and directions, 3.3 V-safe and fail-safe pulls, and threshold arithmetic against the tables above. |
| `--negative-test` | **PASS, 11/11 mutations detected.** Host or USB shorted to SYS_VIN; enables pulled up; cart pull-down too weak; monitor moved to the supply side; divider values changed; contract label renamed; monitor pull-up to 5 V; USB permission bypassed. |
| KiCad ERC on the integrated copy | **0 errors.** 32 `isolated_pin_label` and 5 `pin_to_pin` warnings, identical to the committed baseline in `validation/erc.json`. |
| Existing validators on the integrated copy, after refreshing its `validation/sn64.xml` | verify_interfaces 30/30, verify_usb_programmer 64/64, verify_cart_interface 20/20. |

Run on the unintegrated `hardware/sn64`, the verifier reports `power_sheet_attached` failed. That is expected until the integration is applied. [power-check.json](../../hardware/sn64/validation/power-check.json) records the copy run and the negative test. **Static only:** no ripple, thermal, inrush, timing or hardware measurement exists.

## Open items

- **Footprints.** RPW0010A, RNM0015A and the inductor land patterns come from the vendor mechanical drawings, followed by a pad-set check like the USB validator's.
- **Tolerance margins.** The FPGA_1V1 and FPGA_2V5 UV bands are marginal. Options: a tighter-accuracy supervisor, measured trimming of the thresholds, or acceptance after the measurement.
- **Provisional cartridge settings.** ILIM, dVdt, ITIMER and discharge all wait on measured cartridge currents and capacitance (X5, X6, FXPAK Pro, SA-1/SuperFX).
- **Missing measurements.** Dynamic FPGA power (Lattice Power Calculator), the TPS63070 boost-mode capacity from a 3.0 V host input, and the host-only budget.
- **Discharge inhibit.** Detection-based inhibit on an externally energized cartridge rail (currently bounded to 11.7 mA).
- **Telemetry.** Optional fault telemetry: USB/host eFuse FLT and AUXOFF, and the ILM analog current monitors (Equation 9), for SN64-08-13. Test points TP301–TP310 exist now.
- **Measurements still required.** VBUS attach, detach, suspend and brownout behaviour; switchover droop (Equations 21/22); the M64 accessory-port qualification recorded in the architecture.

## Sources (downloaded to `build/power-sheet/datasheets`, SHA-256)

| Document | SHA-256 |
|---|---|
| TI TPS25947 SLVSFC9C (May 2026) | 8f96de389903091650d4f462dcfad3210071c3ae7093623a7978f34baf8a65b4 |
| TI TUSB320 SLLSEN9F (March 2022) | 1306e448c3f3b169f3b90854710033b9a1aede1d04ba35088f3d2e3ed260d2c4 |
| TI TPS3700 SBVS187G (February 2019) | 3bb7daed20b154bf22ded78e23269c6437eb587400b89bce0f543813df94ebf0 |
| TI TPS63070 SLVSC58B (March 2019) | a88ef66f3493156ff6e7da0849de0e0e1068647f2553d08c1844d4a90c5c65ef |
| TI TLV62569 SLVSDG1C (October 2017) | 1ba6f55dfe678d06d563acd6632f1f950a497d812270806021097b55cd81d3c4 |
| TI TPS22918 SLVSD76C (July 2017) | 1b28eb58003d28b18bf919a15734056f296a499bebee2bd493a1e4358c4dfb1c |
| TI TPS3808 SBVS050N (August 2026) | 74d889c0f68af88032f1633c26381817cc03e10d9fd3b4c177a044ad3ed86eed |
| TI TMP302 SBOS488E (December 2018) | 5413acb9f08d49360a8f2f60474895ea84890e4a9bb20e06cbc03af96bfe275b |
| Nexperia BSS138BK Rev. 1 (2011) | 7ee99c2ff94d07a981fa018ea9c1b86302d179fbff5a466d29e21bebd6eba617 |
| Lattice ECP5 family datasheet FPGA-DS-02012-3.4 | 26570f8bb2b800123120829cacd75d818d7a985d573797610521b5bda2e293c3 |
| ULX3S power.sch @ 6a92cec (MIT; topology reference only, nothing copied) | 0a7ea4d8aa82dd30be2c21654e6e38d335413440c477129f8a6e45eb70c23b43 |

## Integration steps (not applied by this task)

1. Add the root sheet symbol and the SN64_POWER sym-lib-table entry, either with `add_power_sheet.py --attach-only` or by hand.
2. Connect the root labels HOST_3V3, GND, SNES_5V_CART, INTERFACE_3V3, USB_VBUS, USB_3V3, USB_CC1 and USB_CC2.
3. On the USB sheet, make R101/R102 DNP and export USB_VBUS, USB_3V3, USB_CC1 and USB_CC2.
4. Label the cart sheet's INTERFACE_3V3 pin.
5. Connect the FPGA contract pins, and 5V_PRE to the A/V sheet's HDMI +5V, once those sheets exist.
6. Keep the FPGA sheet's PROGRAMN hold from fpga_rails_ok. No extra wiring is needed.
7. Update verify_usb_programmer.py to match.
8. Refresh `validation/sn64.xml`.

The exact edits are in the task hand-off.
