# USB-C programmer connector: source and mechanical evidence

Use **JAE DX07S016JA3R1500** as the connector baseline for the side-facing USB 2.0 programming port. This is the exact value on **J1** in the pinned SummerCart64 Rev 2.1a design. It is a top-mounted, right-angle receptacle whose cable enters parallel to the PCB. The final SN 64 connector position, board thickness and enclosure opening remain layout decisions; this note does not release an enclosure for manufacture.

## Sources and method

- SummerCart64 commit `a1e7996d2cbece686820a5c785029c68514f17b0`: [schematic][sc-sch] and [PCB][sc-pcb]. Exported the schematic with KiCad CLI 10.0.6 to XML and read J1's actual connections; read the footprint pads and board edge directly from the PCB.
- [Official JAE release][jae-release] identifies JA1/JA3 variants. JAE engineering drawing **SJ122205, revision 2, 18 December 2020**, was obtained as a [manufacturer-authored PDF on distributor Comet's server][jae-drawing]; both pages were visually checked. It is not hosted on JAE's own domain. The drawing title is `DX07S016JA3`; the full orderable suffix comes from the source BOM value/release family.
- [JAE brochure MB-0350-2][jae-brochure], also distributor-hosted, corroborates the family dimensions. Referenced handling document `JAHL-30413` was not obtained.

Local evidence lives in the original workspace, `%USERPROFILE%/Documents/Codex/SN 64 Project/.local/usb-research/`: `JAE-SJ122205-rev2-JA3.pdf`, rendered pages `JA3-1.png`/`JA3-2.png`, `sc64v2.xml`, and `sc64-usb-source.json`. These are scratch evidence, not packaged manufacturing deliverables.

The downloaded drawing is 360,983 bytes; SHA-256: `1472b5aeb53034e2ba96b989faafaebd5e9defc49b932e70ab029df6f92d6bbf`.

## JA3 part and JA1 footprint name

SummerCart64 assigns `DX07S016JA3R1500` to footprint **`Connector_USB:USB_C_Receptacle_JAE_DX07S016JA1R1500`**. The PCB also contains a JA3 model override. The name difference alone is not a reason to discard this reusable footprint: the native copper/drill geometry was checked against the **JA3** drawing, rather than assuming interchangeability from the names.

JAE distinguishes the shell hold-down leg lengths: JA1 **0.9 mm**, JA3 **1.2 mm**. JA3 specifies the latter as **1.2 ± 0.15 mm**. The published JA3 reference land pattern matches the inspected source footprint's following features:

| Feature | Native footprint geometry, mm | Check against JA3 drawing |
|---|---|---|
| Signal/power terminals | Twelve distinct SMT positions; four lands 0.52 × 1.0, eight 0.27 × 1.0 | Matches reference pattern |
| Locating holes | One round Ø0.6, one oval 0.85 × 0.6; centers 6.0 apart | Matches reference pattern |
| Rear shell anchors | Two plated slots, drill 0.6 × 1.6, copper 1.3 × 2.3 | Matches reference pattern |
| Front shell anchors | Two plated slots, drill 0.6 × 1.9, copper 1.3 × 2.6 | Matches reference pattern |
| Left/right shell spacing | 8.64 between anchor centers | Matches reference pattern |
| Bottom solder-assist lands | Two 1.0 × 2.0 lands, centers 2.8 apart | Matches reference pattern; retain for mechanical strength |

All four plated shell anchors are pad `S1`, connected to GND in SummerCart64. The two solder-assist lands are unnumbered in the source. Ground and VBUS contact pairs appear as coincident pad objects: **16 named USB contacts occupy 12 distinct terminal lands**. Including four shell anchors, two locating holes and two solder-assist lands, the native footprint has 24 pad objects. Preserve this distinction when copying it; do not spread coincident contact pairs into separate physical lands.

## Physical pad identity and source circuit

The manufacturer's physical PCB terminal numbering below runs left to right in its mounting-side land-pattern view. It is not the same as the USB front-view contact numbering.

| Physical terminal | USB contacts | SummerCart64 connection |
|---|---|---|
| 1 | A1 / B12 | GND |
| 2 | A4 / B9 | VBUS, source net `+5V` |
| 3 | A5, CC1 | R4, 5.1 kΩ to GND |
| 4 | B8, SBU2 | Explicitly unconnected |
| 5 | B7, D− | `USB_D-` |
| 6 | A6, D+ | `USB_D+` |
| 7 | B6, D+ | `USB_D+` |
| 8 | A7, D− | `USB_D-` |
| 9 | B5, CC2 | R5, 5.1 kΩ to GND |
| 10 | A8, SBU1 | Explicitly unconnected |
| 11 | B4 / A9 | VBUS, source net `+5V` |
| 12 | A12 / B1 | GND |

The source ties A6/B6 together and A7/B7 together; these run directly to FT232HL U3 pins 7/6 respectively. CC1 and CC2 each have their **own** pulldown. Independent 5.1 kΩ Rd termination is the sink arrangement described by [TI's Type-C connection documentation, section 10.3.15][cc-reference]. These resistors do not constitute USB Power Delivery negotiation or prove a usable current budget for the whole adapter.

USB VBUS in SummerCart64 feeds 4.7 µF/100 nF input decoupling and TC1264-3.3VDB U1, then a TPS2111A power mux alongside N64 3.3 V. A 5.1 kΩ/10 kΩ divider feeds `FTDI_C7`. This is evidence for a separately managed USB supply, not permission to short programmer VBUS to SN 64 cartridge/host rails or to copy that divider into a different controller without review.

**No external USB ESD protection appears in the inspected source connections:** D+/D− have only J1 and U3; CC lines have J1 and their resistors; the VBUS net has no TVS. Add protection deliberately in SN 64. [ST USBLC6-2SC6][esd] is a concrete USB 2.0 data/VBUS protection reference, with an upstream-port application diagram and placement guidance: put protection near the receptacle and keep discharge paths short. It is not an upstream SummerCart64 component or a completed selection for this board. CC/VBUS fault protection and the final controller's requirements remain part of the support-circuit review; do not describe a D+/D− array as protecting every connector contact.

## Connector envelope and side-port constraints

The JA3 drawing gives reference body dimensions **8.94 mm wide × 6.9 mm deep**, height **3.16 ± 0.15 mm**, and reference center height **1.58 mm**. Its front interior opening is **8.34 × 2.56 mm**, a connector dimension rather than an enclosure cutout.

Reference mounting uses a **1.2 mm PCB** and **0.5 mm front overhang**; the PCB edge is 5.05 mm forward of the locating-hole datum Y. The mating example gives plug projection **6.65 ± 0.1 mm**, engagement **4.7 ± 0.2 mm**, and nominal exposed projection **1.95 mm**. It does not specify a cable-overmold envelope or permitted panel setback. The drawing notes its shell is shorter than the USB-recommended 6.2 mm and requires checking assembled mating reliability. [JA3 drawing, sheets 1–2][jae-drawing]

This matches the source placement: J1 is at **(102.2, 92.5), −90°**, facing the left PCB edge. Its fabrication outline maps to front X = **98.6 mm**, while that board edge is X = **99.1 mm**, giving the same 0.5 mm overhang. SummerCart64's board thickness is 1.2 mm. Its footprint courtyard is **10.94 × 8.43 mm**; this is component placement space, **not** a plug or enclosure keepout.

For the next enclosure pass, place the selected connector model on the actual SN 64 board and reserve space for the complete mating plug, its overmold and cable bend. Derive the opening and wall setback from that assembly, printing tolerances and a fit coupon. The connector opening, courtyard, and nominal 1.95 mm exposed plug length cannot independently determine the shell cutout. Final side, elevation and distance from the cartridge bay are still unresolved here.

## Programmer clock: selected crystal and provisional capacitors

The programmer draft uses **Abracon ABM3B-12.000MHZ-10-1-U-T** in place of SummerCart64's powered 12 MHz oscillator. [FTDI's FT232H datasheet v2.2, section 6.3/page 48][ftdi] specifies a 12 MHz ±30 ppm fundamental, parallel-cut crystal. Its two 27 pF capacitors are an example; **18 pF crystal load capacitance is not an FTDI requirement**.

The [Abracon datasheet, revision U][abm3b], decodes this selected part as 12 MHz fundamental, **CL = 10 pF**, ±10 ppm initial tolerance (`1`), ±10 ppm temperature stability (`U`), and the **standard −10 to +60 °C temperature grade** because no temperature-option code is present. `T` denotes reel packaging. At 12 MHz, series ESR is at most 70 Ω; the maximum drive rating is 100 µW. The first-year aging limit is ±5 ppm. Do not substitute another CL or temperature grade under the same shortened family name.

Use `Crystal:Crystal_SMD_Abracon_ABM3B-4Pin_5.0x3.2mm`. Its 1.8 × 1.2 mm pads have 4.0 × 2.4 mm center spacing, matching [Abracon's package drawing][abm3b-package]. Pins 1/3 are the nonpolar crystal connections; 2/4 are ground. Connect 1/3 across FT232H XCSI/XCSO (pins 1/2 in the reused FT232HL symbol). The package is 5.0 × 3.2 mm, at most 1.1 mm high.

**Initial, unvalidated load: two 11 pF C0G capacitors**, one from each crystal node to ground. Using `CL = C1*C2/(C1+C2) + Cstray`, an **assumed effective 4.5 pF parasitic load** gives `11/2 + 4.5 = 10 pF`. That parasitic value is an engineering starting assumption, not a measured board value or FTDI guarantee; it includes effective pin/trace contribution and is not the crystal's shunt capacitance C0. Retain capacitor tuning access and verify startup, drive level and frequency on the assembled PCB across the intended conditions.

A conservative initial-tolerance + temperature + first-year-aging sum is **±25 ppm**, leaving only **5 ppm** of FTDI's ±30 ppm limit for load error and other effects. The provisional capacitors do not prove that remaining budget. This temperature grade also limits the selected part to −10…+60 °C. Removing a separately powered oscillator eliminates that component's continuous supply load, but does not by itself demonstrate whole-board USB suspend compliance; FTDI's datasheet does not explicitly establish crystal shutdown. The separate programmer regulator is retained because this review found no guaranteed VCCD external-current budget for powering the translator.

[sc-sch]: https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_sch
[sc-pcb]: https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_pcb
[jae-release]: https://www.jae.com/en/releases/detail/id=92529
[jae-drawing]: https://store.comet.bg/download-file.php?id=31838
[jae-brochure]: https://www.ttieurope.com/content/dam/tti-europe/manufacturers/jae/resources/MB-0350-2E_DX07_16-POS_RECEPTACLE.pdf
[cc-reference]: https://www.ti.com/lit/ds/symlink/tps25855-q1.pdf
[esd]: https://www.st.com/resource/en/datasheet/usblc6-2.pdf
[ftdi]: https://ftdichip.com/wp-content/uploads/2024/09/DS_FT232H.pdf
[abm3b]: https://abracon.com/Resonators/abm3b.pdf
[abm3b-package]: https://abracon.com/Support/PackageDrawing/Resonators/ABM3B.PDF
