# SNES cartridge interface schematic: translation and protection

Drafted 2026-09-29; revised the same day to rev `0.3.1-cart` (per-pin CIC data translators, see [the review finding](#review-finding-cic-data-pins-need-per-pin-bidirectional-drive-must-fix-before-layout)). This is the first schematic of the circuitry between the 62-contact SNES socket (J2) and the FPGA. It passes an independent static netlist check and KiCad ERC with zero errors. **It has not been built, simulated for signal integrity or tested with a cartridge.** Values marked provisional are engineering starting points, not measured results.

## Plain-language summary

The cartridge runs at 5 V and the FPGA at 3.3 V, so every wire between them goes through a translator chip. Seven SN74LVC4245A octal translators carry 51 console-driven and data signals. Their 5 V side (A) faces the socket and their 3.3 V side (B) faces the FPGA. Six of them only ever drive toward the cartridge: their direction pin is wired to ground. The seventh carries the eight data wires, and the FPGA chooses its direction for each read or write.

Each translator has an enable pin that must be pulled up to 5 V to switch it off. A 5 V pull-up must never reach an FPGA pin. Each enable is therefore controlled by a small 3.3 V open-drain buffer that can pull the line low but never drives it high. If the interface rail is off or the FPGA is not yet configured, every translator stays switched off. The cartridge is also held in reset until the FPGA deliberately releases it. Signals the cartridge drives, or that must be released, are read through a 5 V-tolerant 3.3 V buffer: /IRQ, /RESET and EXPAND. Audio goes straight through with no digital parts.

The two CIC data wires are different: the security-chip conversation swaps which side talks on each wire from round to round. Each of them therefore has its own single-bit translator (SN74LVC1T45) whose direction the FPGA sets with a dedicated pin. By default (FPGA not configured) both only listen, and a pull-down resistor holds each wire low when nobody drives it, which is what the lock logic expects.

## Files

| File | Role |
|---|---|
| [hardware/sn64/cart-interface.kicad_sch](../../hardware/sn64/cart-interface.kicad_sch) | Child sheet "SNES cartridge interface" (A1, page 3) |
| [hardware/sn64/sn64.kicad_sch](../../hardware/sn64/sn64.kicad_sch) | Root: one added sheet symbol; its cartridge pins carry the existing J2 labels. Existing objects were not changed. |
| [hardware/sn64/libraries/SN64_CART.kicad_sym](../../hardware/sn64/libraries/SN64_CART.kicad_sym) | Two symbols drawn from TI pin tables: SN74LVC4245APW, SN74LVC244APW |
| [hardware/sn64/libraries/cart-provenance.json](../../hardware/sn64/libraries/cart-provenance.json) | Datasheet revisions, downloaded-copy SHA-256, pin tables, installed KiCad symbols/footprints used |
| [hardware/sn64/tools/add_cart_interface.py](../../hardware/sn64/tools/add_cart_interface.py) | Authoring script; refuses to overwrite without `--force`. With `--force` it regenerates the child sheet and replaces only its own sheet symbol (pins, size) and the pin labels/no-connects it placed in the root; a second run is byte-identical |
| [hardware/sn64/tools/verify_cart_interface.py](../../hardware/sn64/tools/verify_cart_interface.py) | Independent validator with a `--negative-test` fault-injection mode |
| [hardware/sn64/validation/cart-interface-check.json](../../hardware/sn64/validation/cart-interface-check.json) | Validator result, including a per-contact table for all 62 J2 contacts |

## What is reused

- **Topology** comes from [power-architecture.md](power-architecture.md) (translator section) and [translation-reuse-review.md](translation-reuse-review.md). The design uses A=5 V/B=3.3 V, reversed from sd2snes, with /OE pulled to the A supply through open-drain control. Console outputs are kept separate from D0–D7, and IRQ, reset, CIC and audio have dedicated handling. Following the sd2snes precedent, the draft keeps tunable series-resistor footprints but does not copy that design; sd2snes is GPL-2.0-only and none of its files are included.
- **Installed KiCad 10.0.6 libraries**, unmodified: `Logic_LevelTranslator:SN74LVC1T45DBV` (pin table checked against TI SCES515N Table 4-1: 1 VCCA, 2 GND, 3 A, 4 B, 5 DIR, 6 VCCB), `74xGxx:74LVC1G07`, `74xGxx:74LVC1G06`, `Device:R`, `Device:C`, `Device:R_Pack04`, `Transistor_FET:2N7002` (its `extends` chain flattened into the embedded copy), `Connector:TestPoint` and `power:PWR_FLAG`. The standard TSSOP-24/TSSOP-20/SOT-23(-5)/0603/0805/R-array footprints are referenced from their installed libraries rather than copied.
- **No KiCad symbol exists** for SN74LVC4245A or SN74LVC244A. Both were drawn from TI SCAS375K (May 2026, Table 4-1) and SCAS414AG (June 2026, Figure 4-2). The validator checks them against its own copy of those tables. SCAS375K Figure 4-1 labels pin 23 "NC,VCCB", while Table 4-1 says VCCB. It is tied to VCCB and bypassed, which is safe under either reading.
- **Signal names**: cartridge-side nets reuse the root J2 labels (`SNES_*`). FPGA-side hierarchical labels use the [bridge](../../fpga/rtl/sn64_cart_bridge.sv) port names: `cart_address[0..23]`, `cart_pa[0..7]`, `cart_data[0..7]`, `cart_rd_n`…`cart_phi2`, `cart_sysclk`, `ctl_oe_n`, `data_oe_n`, `data_dir`, `cart_irq_n`, `cart_reset_n_sense` and `cart_reset_pull_n`. The CIC and expansion pins are not bridge ports: `cic_oe_n` (sn64_top `snes_cic_oe_n`), `cic_clk`, `cic_slave_reset`, `cic_data0`/`cic_data1` (bidirectional, A side of U215/U216), `cic_data0_dir`/`cic_data1_dir` (DIR of U215/U216) and `expand_sense`. The CIC names map to the [SNES CIC lock](../../fpga/rtl/sn64_snes_cic_lock.sv) ports `data0_o/oe/i` and `data1_o/oe/i` through the board wrapper (see [FPGA sequencing rule](#cic-data-pins-u215u216)).

## Circuit

| Block | Parts | Connection |
|---|---|---|
| Address A0–A23 | U201–U203 SN74LVC4245A | DIR=GND (B→A), /OE=`CTL_OE_N_5V` |
| PA0–PA7 | U204 | same |
| /RD /WR /PRD /PWR /ROMSEL /WRAMSEL REFRESH PHI2 | U205 | same |
| SYSTEM_CLK, CIC_CLK, CIC_SLAVE_RESET | U206 (5 channels spare: B inputs tied to GND, A outputs no-connect) | DIR=GND, own /OE=`CIC_OE_N_5V` (sn64_top `snes_cic_oe_n`, enabled from the sequencer IFACE state) |
| CIC_DATA0 (J2.55), CIC_DATA1 (J2.24) | U215, U216 SN74LVC1T45DBVR (LCSC C7843), one per pin | A = `cic_data0`/`cic_data1` (FPGA, VCCA = `INTERFACE_3V3`); B → R214/R215 33 Ω series → socket (VCCB = `SNES_5V_CART`); DIR = `cic_data0_dir`/`cic_data1_dir` straight from the FPGA (DIR is referenced to VCCA); see below |
| D0–D7 | U207 | DIR=`DATA_DIR_5V`, /OE=`DATA_OE_N_5V` |
| Damping | RN201–RN213, 4×33 Ω 0603 arrays at the translator A pins | provisional; tune after SI measurement |
| /OE control | U210/U211/U212 74LVC1G07 (3.3 V, open-drain, 5.5 V-tolerant output, Ioff); R201/R202 2.2 k, R203 1 k pull-ups to cartridge 5 V; R206–R208 10 k input pull-ups to 3.3 V | `ctl_oe_n`, `cic_oe_n`, `data_oe_n` keep the bridge polarity (0 = drive) |
| Data DIR | U213 74LVC1G06 (inverting open-drain), R204 1 k to 5 V, R209 10 k input pull-down | `data_dir`=1 → DIR low → B→A (FPGA drives); default listen |
| /RESET | Q201 2N7002 sink; gate `RESET_GATE_5V` pulled to 5 V by R205 100 k; U214 74LVC1G06 pulls the gate low when `cart_reset_pull_n`=1; R210 10 k input pull-down; R212 10 k /RESET pull-up | Cartridge stays in reset unless the interface rail is up **and** the FPGA releases it |
| Sense | U209 SN74LVC244A at 3.3 V (5.5 V-tolerant inputs, Ioff), both /OE tied low | /IRQ, /RESET, EXPAND (5 unused inputs tied to GND, outputs no-connect) |
| Bias | R211 /IRQ 10 k and R213 EXPAND 10 k pull-ups to 5 V | provisional values |
| CIC idle levels | R216/R217 10 k socket-side pull-downs on CIC_DATA0/1; R218/R219 100 k A-side pull-downs on `cic_data0/1`; R220/R221 10 k pull-downs on `cic_data0_dir/1_dir` | provisional values; the lock expects a released pin to read low |
| Audio | TP201/TP202 only | untouched analog pass-through |
| Decoupling | C201–C227: one 100 nF per supply pin (7 VCCA, 14 VCCB, receiver, five gates); C228–C231 one 100 nF per U215/U216 VCCA and VCCB pin; C232/C233 10 µF per rail | place at the pins |
| Rails | `SNES_5V_CART` (joined to J2 27/58 in the root), `INTERFACE_3V3` (pending) | both default-off, from the future power sheet; #FLG201/#FLG202 exist for ERC only |

Default states, derived from the circuit (not measured):

| Condition | Translator /OE | Data DIR | Cartridge /RESET | CIC_DATA0/1 (U215/U216) |
|---|---|---|---|---|
| 5 V on, `INTERFACE_3V3` off | released → high (isolated) | high (A→B) | held low | both ports high-Z (VCC isolation); socket pins held low by R216/R217 |
| `INTERFACE_3V3` on, 5 V off | released → high | — | held low | both ports high-Z (VCC isolation) |
| Both rails on, FPGA unconfigured | high (input pull-ups) | high | held low (input pull-down) | DIR low (R220/R221) → B→A, listen; socket pins low via R216/R217 |
| Running | bridge `*_oe_n` | bridge `data_dir` | released when `cart_reset_pull_n`=1 | per pin: `cic_dataN_dir`=1 drives the cartridge, 0 listens |

A passive pull-up makes the **disable edge** slow, and the bridge allows only one 46.56 ns released clock before turnaround. The data octet therefore uses 1 k pull-ups: with about 10 pF of load, τ≈10 ns, and 5 V reaches the 2.0 V threshold in about 0.5τ. The shared control /OE (five inputs) uses 2.2 k, because it switches only on permission changes. These are calculations, not measurements. Confirm them against the translator's t_dis and the real layout.

### CIC data pins (U215/U216)

[sn64_snes_cic_lock.sv](../../fpga/rtl/sn64_snes_cic_lock.sv) drives CIC_DATA0 during the seed and in rounds with dir=1, drives CIC_DATA1 in rounds with dir=0, releases both across every direction change and after a key mismatch, and reads a released pin as low. Each pin therefore gets its own [TI SN74LVC1T45](https://www.ti.com/lit/ds/symlink/sn74lvc1t45.pdf) (SCES515N, revised June 2024; downloaded copy SHA-256 `e6fbd840…0536e`, full hash and extracted facts in `libraries/cart-provenance.json`) and shares no enable or direction line with any other signal.

- **Orientation.** A = FPGA (VCCA = `INTERFACE_3V3`), B = cartridge (VCCB = `SNES_5V_CART`). The datasheet lists "DIR input circuit referenced to VCCA", so DIR is driven directly by a 3.3 V FPGA pin with no level shifting. Function table 7-1: DIR = H is "A data to B bus" (FPGA drives the cartridge), DIR = L is "B data to A bus" (FPGA listens).
- **Default.** R220/R221 (10 k) hold DIR low while the FPGA is unconfigured, so both pins listen. The 10 k value is chosen to dominate a configuration-time weak pull on the FPGA pin; confirm against the ECP5 sysIO data when the pinout is fixed.
- **Idle level.** R216/R217 (10 k, provisional) pull each socket pin low: the lock treats a released pin as 0. With about 20 pF of socket and trace load τ≈0.2 µs, well inside one lock instruction cycle (4 CIC clocks: about 1.1 µs at 3.58 MHz, 1.28 µs at sn64_top's 3.125 MHz); a 5 V CMOS driver sources 0.5 mA into it. This must be confirmed against a real key CIC's output drive and the original console board. R218/R219 (100 k) put the same pull-down condition on the A side, as SCES515N Table 8-2 note 1 asks ("SYSTEM-1 and SYSTEM-2 must use the same conditions"), and keep the A input defined if DIR is ever high while the FPGA pin floats.
- **Series resistor.** R214/R215 33 Ω 0603 between B and the socket, the same provisional damping as the octet arrays.
- **FPGA sequencing rule (obligation on the board wrapper).** The part has no OE pin; SCES515N §8.2.2 says the designer "should take precautions to avoid bus contention ... when changing directions". Before driving: set `cic_dataN_dir` high, then enable the FPGA output on `cic_dataN`. Before listening: disable the FPGA output on `cic_dataN` (input), then set `cic_dataN_dir` low. At VCCA = 3.3 V, VCCB = 5 V (SCES515N §5.8) DIR→A disable is at most 7.3 ns (tPHZ) / 5.7 ns (tPLZ) and DIR→B disable at most 6.8 / 4.9 ns, so one 40 ns `clk_25` cycle between the two steps is enough. Because the lock asserts `data0_oe` for both in one register today, the wrapper should derive `dir = oe | oe_q` and `pad_oe = oe & oe_q` (with `oe_q` = `oe` delayed one `clk_25`); see the integration note in this task's report. The lock already leaves both pins released across each direction change, so the cartridge-side turnaround is covered by the protocol gap.
- **Power-off behaviour (quoted, SCES515N).** Features: "VCC isolation feature - if either VCC input is at GND, both ports are in the high-impedance state" and "Ioff supports partial-power-down mode operation". §7.3.6: "The I/Os of both ports will enter a high-impedance state when either of the supplies are at GND, while the other supply is still connected to the device." §7.3.3: the I/Os "enter a high-impedance state when the device is powered down, inhibiting current backflow into the device". Ioff (§5.5) is ±1 µA at 25 °C and ±2 µA over −40 to 85 °C for VI/VO 0–5.5 V with the relevant supply at 0 V. So with either rail off, both pins are released and the socket pins sit at their pull-downs. §7.3.5 additionally states either rail may ramp in any order without output glitches. These are datasheet claims, not measurements on SN64 hardware.

## Verification (run 2026-09-29, KiCad 10.0.6)

Rev 0.3.1 re-run (per-pin CIC translators), all from the repository root with KiCad 10's python and kicad-cli:

- `verify_cart_interface.py`: `PASS: 20 cartridge-interface checks; 62/62 J2 contacts accounted; ERC {'warning:isolated_pin_label': 32, 'warning:pin_to_pin': 5}`. Three checks are new: `cic_data_pins_individually_direction_controlled` (each CIC pin reaches exactly one SN74LVC1T45 B pin through one 22–100 Ω series resistor and nothing else; VCCA = `INTERFACE_3V3`, VCCB = `SNES_5V_CART`; A on `cic_dataN` and DIR on its own `cic_dataN_dir` label, the only IC pin on that net; the two translators and DIR nets are distinct), `cic_data_pins_pulled_down_both_sides` (one 1–100 kΩ socket pull-down to GND, an A-side pull-down, a DIR pull-down, no pull-up) and `cic_data_pins_not_on_shared_octet_enable_or_receiver`. The 5 V graph search now also treats the 1T45 B/VCCB nets as 5 V and allows only 1T45 A/DIR pins on FPGA labels; the part-count, pin-identity (SCES515N Table 4-1) and decoupling checks include U215/U216.
- `verify_cart_interface.py --negative-test`: six mutations, each required to fail named checks; `"negative_test": "pass"` (exit 0). The four new ones: U215 DIR tied to cartridge 5 V → fails `cic_data_pins_individually_direction_controlled` (and pull-down/contact checks); R217 socket pull-down disconnected → fails `cic_data_pins_pulled_down_both_sides`; U216 DIR moved onto `cic_data0_dir` (shared direction) → fails `cic_data_pins_individually_direction_controlled`; U215 B wired to `cic_data0` (5 V on an FPGA label) → fails `no_5V_net_reaches_FPGA_label` and `cic_data_pins_individually_direction_controlled`. The two original mutations still fail as before.
- `kicad-cli sch erc`: **0 errors**, 37 warnings: 32 `isolated_pin_label` (pending N64 J1 labels) and 5 `pin_to_pin` (U206's five unused B inputs tied to GND, one more than before because CIC_DATA0 left U206).
- `verify_interfaces.py --source-root .`: pass, 30/30. `verify_usb_programmer.py`: pass, 64/64. `validation/sn64.xml` and `validation/erc.json` were regenerated first.
- The tracked `exports/sn64-interface-draft.pdf` was regenerated. The cartridge sheet's SVG export was rasterized (headless Edge) and the new CIC block, U206, the resistor row and the capacitor rows inspected: no label, reference or note overlaps (the decoupling note, which previously crossed three capacitor labels, was moved up).
- `add_cart_interface.py --force` was first run on a copy of the unmodified project: it reproduced all tracked outputs byte-for-byte, so no native edits were lost by regenerating. After the change a second `--force` run is byte-identical, and the root diff is limited to the sheet symbol (size and pins) and its FPGA-side no-connect markers.

Initial 0.3 run (superseded, kept for the record):

- `python hardware/sn64/tools/verify_cart_interface.py` (KiCad python): `PASS: 17 cartridge-interface checks; 62/62 J2 contacts accounted; ERC {'warning:isolated_pin_label': 32, 'warning:pin_to_pin': 4}`. The checks cover datasheet pin identities for all 7 translators, the receiver, the 5 gates and the NMOS. They also check A=5 V/B=3.3 V supplies and the per-contact handling for all 62 contacts. Fixed octets must have DIR=GND. Each /OE must be pulled to cartridge 5 V through open-drain control and default to disabled. The data DIR must use level-safe control. A graph search from all 62 FPGA-side nets through every resistor must find no 5 V net. The checks also cover the decoupling count, footprints, and sheet-pin/hierarchical-label agreement.
- `--negative-test` copies the project to a temporary directory and applies two faults:
  - U201's DIR strap is moved to 5 V. This fails `all_62_J2_contacts_accounted_with_required_handling` and `fixed_output_octets_DIR_strapped_B_to_A`.
  - R206's pull-up is moved to cartridge 5 V. This fails `every_OE_pulled_to_cart_5V_via_open_drain_default_disabled`, `no_5V_net_reaches_FPGA_label` and `5V_pullups_only_on_cartridge_side_nets`.
  - Result: `"negative_test": "pass"`, meaning both faults were detected.
- `kicad-cli sch erc`: **0 errors**, 36 warnings. The 32 `isolated_pin_label` warnings are the pending N64 J1 labels; the baseline had 90, including all the J2 labels that now connect to circuitry. The 4 `pin_to_pin` warnings are U206's unused B inputs tied to GND.
- `verify_usb_programmer.py`: pass, 64/64.
- `verify_interfaces.py --source-root .`: 29/30. The one failure is intended: `three_power_domains_separate` expects `/SNES_5V_CART` to contain only J2.27/J2.58, and the translator A-rail now shares it. The check needs a one-line fix to count only connector contacts on the three supply nets (see the open items). A temporary patched copy passed 30/30. The stored `validation/sn64.xml` was regenerated so the stored-netlist checks compare against the current schematic.
- PDF exported to `build/cart-interface-sch/sn64-cart-interface-draft.pdf`, not over the tracked export. All three pages were rasterized and inspected; label and reference overlaps were fixed.

## Limits

- Static connectivity only. No timing or SI simulation, no power-sequencing or hot-plug test, and no cartridge test.
- The FPGA-side sheet pins end at no-connect markers in the root until an FPGA sheet exists. `INTERFACE_3V3` has no source yet. The PWR_FLAGs only satisfy ERC; remove them when the power sheet drives the rails.
- The translator Ioff/isolation behavior is taken from TI §7.5 for a supply below 100 mV or floating. The [power architecture](power-architecture.md) lists the converse numeric qualification as still open.
- ERC and the validator cannot establish drive strength, ringing, ground bounce or the effect of the 33 Ω values.
- The CIC DIR/pad sequencing rule is an FPGA obligation that no netlist check can see. It must be implemented in the board wrapper and tested there (a bench that flags any clock where the pad drives while DIR is low, or DIR is low while the pad drives).
- The SN74LVC1T45 isolation and Ioff statements are quoted from SCES515N, not measured on SN64 hardware.

## Open items

1. The bridge needs `expand_sense`; `cic_oe_n` and the CIC signals come from `sn64_top` (`snes_cic_oe_n`, `snes_cic_*`). The board wrapper must map `data0/1_o/oe/i` onto `cic_data0/1` pads and `cic_data0/1_dir` with the DIR-first/release-first sequencing above.
2. ~~CIC_DATA0 shares U206's enable …~~ Resolved in rev 0.3.1: per-pin SN74LVC1T45 on each CIC data pin. SuperCIC pair mode (both data pins as console-side inputs or outputs) is now electrically possible on either pin.
3. Select low-capacitance ESD protection at the socket, with placement.
4. Final damping and pull values from layout and measurement. Confirm the OpenSFC R92/R97 values for the IRQ/EXPAND bias. Confirm the CIC_DATA0/1 10 k pull-down against a real key CIC's output drive and the original console board.
5. Confirm the /OE disable timing against the SN74LVC4245A t_dis/t_en at the real load.
6. ~~Apply the `verify_interfaces.py` supply-check patch~~ Done: the validator passes 30/30.


## Review finding: CIC data pins need per-pin bidirectional drive (must fix before layout)

Integration review (2026-09-29) against [sn64_snes_cic_lock.sv](../../fpga/rtl/sn64_snes_cic_lock.sv): the lock/key protocol swaps which side drives CIC_DATA0 (pin 55) and CIC_DATA1 (pin 24) between rounds (round 1: lock drives DATA1, key drives DATA0; key-stream element 7 bit 0 swaps them), and the lock expects a released pin to be defined by a pull-down. This sheet drives DATA0 through U206 (fixed FPGA-to-cartridge, shared enable) and only senses DATA1 through the 244. That would fight the key on DATA0 in rounds where the key drives it and cannot drive DATA1 at all. Replace with an individually enabled, per-pin bidirectional path for each of the two CIC data pins (drive with its own output enable, sense always, pull-down idle), move DATA0 off U206's shared enable, and re-run `verify_cart_interface.py` with the new contract. U206 then carries only console outputs (SYSTEM_CLK, CIC_CLK, CIC_SLAVE_RESET), enabled from the power sequencer's IFACE state so the CIC can run before the SNES clock starts (`cic_oe_n` in `sn64_top`).

**Resolution (rev 0.3.1-cart, 2026-09-29).** CIC_DATA0 and CIC_DATA1 each have their own SN74LVC1T45 (U215/U216) with a dedicated FPGA DIR pin, a 33 Ω series resistor, a 10 k socket-side pull-down, a 100 k A-side pull-down and a 10 k DIR pull-down (default listen). CIC_DATA0 was removed from U206 (which now carries only SYSTEM_CLK, CIC_CLK and CIC_SLAVE_RESET, five spare channels tied as before), and the CIC_DATA0/CIC_DATA1 sense paths and R214 100 k bias on U209 were removed; /IRQ, /RESET and EXPAND sensing is unchanged. `verify_cart_interface.py` enforces the new contract and its negative test covers DIR tied to 5 V, a missing pull-down, a shared DIR and 5 V on an FPGA label. See [CIC data pins (U215/U216)](#cic-data-pins-u215u216) and the verification section. The FPGA-side sequencing (board wrapper) is still open.
