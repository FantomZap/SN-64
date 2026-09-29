# SNES cartridge interface schematic: translation and protection

Drafted 2026-09-29. This is the first schematic of the circuitry between the 62-contact SNES socket (J2) and the FPGA. It passes an independent static netlist check and KiCad ERC with zero errors. **It has not been built, simulated for signal integrity or tested with a cartridge.** Values marked provisional are engineering starting points, not measured results.

## Plain-language summary

The cartridge runs at 5 V and the FPGA at 3.3 V, so every wire between them goes through a translator chip. Seven SN74LVC4245A octal translators carry the 52 console-driven and data signals. Their 5 V side (A) faces the socket and their 3.3 V side (B) faces the FPGA. Six of them only ever drive toward the cartridge: their direction pin is wired to ground. The seventh carries the eight data wires, and the FPGA chooses its direction for each read or write.

Each translator has an enable pin that must be pulled up to 5 V to switch it off. A 5 V pull-up must never reach an FPGA pin. Each enable is therefore controlled by a small 3.3 V open-drain buffer that can pull the line low but never drives it high. If the interface rail is off or the FPGA is not yet configured, every translator stays switched off. The cartridge is also held in reset until the FPGA deliberately releases it. Signals the cartridge drives, or that must be released, are read through a 5 V-tolerant 3.3 V buffer: /IRQ, /RESET, EXPAND and both CIC data lines. Audio goes straight through with no digital parts.

## Files

| File | Role |
|---|---|
| [hardware/sn64/cart-interface.kicad_sch](../../hardware/sn64/cart-interface.kicad_sch) | Child sheet "SNES cartridge interface" (A1, page 3) |
| [hardware/sn64/sn64.kicad_sch](../../hardware/sn64/sn64.kicad_sch) | Root: one added sheet symbol; its cartridge pins carry the existing J2 labels. Existing objects were not changed. |
| [hardware/sn64/libraries/SN64_CART.kicad_sym](../../hardware/sn64/libraries/SN64_CART.kicad_sym) | Two symbols drawn from TI pin tables: SN74LVC4245APW, SN74LVC244APW |
| [hardware/sn64/libraries/cart-provenance.json](../../hardware/sn64/libraries/cart-provenance.json) | Datasheet revisions, downloaded-copy SHA-256, pin tables, installed KiCad symbols/footprints used |
| [hardware/sn64/tools/add_cart_interface.py](../../hardware/sn64/tools/add_cart_interface.py) | Authoring script; refuses to overwrite without `--force` |
| [hardware/sn64/tools/verify_cart_interface.py](../../hardware/sn64/tools/verify_cart_interface.py) | Independent validator with a `--negative-test` fault-injection mode |
| [hardware/sn64/validation/cart-interface-check.json](../../hardware/sn64/validation/cart-interface-check.json) | Validator result, including a per-contact table for all 62 J2 contacts |

## What is reused

- **Topology** comes from [power-architecture.md](power-architecture.md) (translator section) and [translation-reuse-review.md](translation-reuse-review.md). The design uses A=5 V/B=3.3 V, reversed from sd2snes, with /OE pulled to the A supply through open-drain control. Console outputs are kept separate from D0–D7, and IRQ, reset, CIC and audio have dedicated handling. Following the sd2snes precedent, the draft keeps tunable series-resistor footprints but does not copy that design; sd2snes is GPL-2.0-only and none of its files are included.
- **Installed KiCad 10.0.6 libraries**, unmodified: `74xGxx:74LVC1G07`, `74xGxx:74LVC1G06`, `Device:R`, `Device:C`, `Device:R_Pack04`, `Transistor_FET:2N7002` (its `extends` chain flattened into the embedded copy), `Connector:TestPoint` and `power:PWR_FLAG`. The standard TSSOP-24/TSSOP-20/SOT-23(-5)/0603/0805/R-array footprints are referenced from their installed libraries rather than copied.
- **No KiCad symbol exists** for SN74LVC4245A or SN74LVC244A. Both were drawn from TI SCAS375K (May 2026, Table 4-1) and SCAS414AG (June 2026, Figure 4-2). The validator checks them against its own copy of those tables. SCAS375K Figure 4-1 labels pin 23 "NC,VCCB", while Table 4-1 says VCCB. It is tied to VCCB and bypassed, which is safe under either reading.
- **Signal names**: cartridge-side nets reuse the root J2 labels (`SNES_*`). FPGA-side hierarchical labels use the [bridge](../../fpga/rtl/sn64_cart_bridge.sv) port names: `cart_address[0..23]`, `cart_pa[0..7]`, `cart_data[0..7]`, `cart_rd_n`…`cart_phi2`, `cart_sysclk`, `ctl_oe_n`, `data_oe_n`, `data_dir`, `cart_irq_n`, `cart_reset_n_sense` and `cart_reset_pull_n`. Seven are **proposed** additions that the bridge does not have yet: `cic_oe_n`, `cic_clk`, `cic_slave_reset`, `cic_data0_out`, `cic_data0_sense`, `cic_data1_in` and `expand_sense`.

## Circuit

| Block | Parts | Connection |
|---|---|---|
| Address A0–A23 | U201–U203 SN74LVC4245A | DIR=GND (B→A), /OE=`CTL_OE_N_5V` |
| PA0–PA7 | U204 | same |
| /RD /WR /PRD /PWR /ROMSEL /WRAMSEL REFRESH PHI2 | U205 | same |
| SYSTEM_CLK, CIC_CLK, CIC_SLAVE_RESET, CIC_DATA0 | U206 (4 channels spare: B inputs tied to GND, A outputs no-connect) | DIR=GND, own /OE=`CIC_OE_N_5V` |
| D0–D7 | U207 | DIR=`DATA_DIR_5V`, /OE=`DATA_OE_N_5V` |
| Damping | RN201–RN213, 4×33 Ω 0603 arrays at the translator A pins | provisional; tune after SI measurement |
| /OE control | U210/U211/U212 74LVC1G07 (3.3 V, open-drain, 5.5 V-tolerant output, Ioff); R201/R202 2.2 k, R203 1 k pull-ups to cartridge 5 V; R206–R208 10 k input pull-ups to 3.3 V | `ctl_oe_n`, `cic_oe_n`, `data_oe_n` keep the bridge polarity (0 = drive) |
| Data DIR | U213 74LVC1G06 (inverting open-drain), R204 1 k to 5 V, R209 10 k input pull-down | `data_dir`=1 → DIR low → B→A (FPGA drives); default listen |
| /RESET | Q201 2N7002 sink; gate `RESET_GATE_5V` pulled to 5 V by R205 100 k; U214 74LVC1G06 pulls the gate low when `cart_reset_pull_n`=1; R210 10 k input pull-down; R212 10 k /RESET pull-up | Cartridge stays in reset unless the interface rail is up **and** the FPGA releases it |
| Sense | U209 SN74LVC244A at 3.3 V (5.5 V-tolerant inputs, Ioff), both /OE tied low | /IRQ, /RESET, EXPAND, CIC_DATA1, CIC_DATA0 |
| Bias | R211 /IRQ 10 k and R213 EXPAND 10 k pull-ups to 5 V; R214 100 k CIC_DATA1 pull-down | provisional values |
| Audio | TP201/TP202 only | untouched analog pass-through |
| Decoupling | C201–C227: one 100 nF per supply pin (7 VCCA, 14 VCCB, receiver, five gates); C228/C229 10 µF per rail | place at the pins |
| Rails | `SNES_5V_CART` (joined to J2 27/58 in the root), `INTERFACE_3V3` (pending) | both default-off, from the future power sheet; #FLG201/#FLG202 exist for ERC only |

Default states, derived from the circuit (not measured):

| Condition | Translator /OE | Data DIR | Cartridge /RESET |
|---|---|---|---|
| 5 V on, `INTERFACE_3V3` off | released → high (isolated) | high (A→B) | held low |
| Both rails on, FPGA unconfigured | high (input pull-ups) | high | held low (input pull-down) |
| Running | bridge `*_oe_n` | bridge `data_dir` | released when `cart_reset_pull_n`=1 |

A passive pull-up makes the **disable edge** slow, and the bridge allows only one 46.56 ns released clock before turnaround. The data octet therefore uses 1 k pull-ups: with about 10 pF of load, τ≈10 ns, and 5 V reaches the 2.0 V threshold in about 0.5τ. The shared control /OE (five inputs) uses 2.2 k, because it switches only on permission changes. These are calculations, not measurements. Confirm them against the translator's t_dis and the real layout.

## Verification (run 2026-09-29, KiCad 10.0.6)

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

## Open items

1. The bridge needs `cic_oe_n`, the CIC ports and `expand_sense`. Until a CIC controller exists, drive `cic_oe_n` = `ctl_oe_n`.
2. CIC_DATA0 shares U206's enable with SYSTEM_CLK, CIC_CLK and CIC_SLAVE_RESET, so it cannot be released alone. SuperCIC pair mode, in which both data pins may need console drive, is not supported on CIC_DATA1. Resolve this with the CIC design, possibly with a dedicated single-bit driver.
3. Select low-capacitance ESD protection at the socket, with placement.
4. Final damping and pull values from layout and measurement. Confirm the OpenSFC R92/R97 values for the IRQ/EXPAND bias.
5. Confirm the /OE disable timing against the SN74LVC4245A t_dis/t_en at the real load.
6. Apply the `verify_interfaces.py` supply-check patch (in this task's report) so the existing validator returns to 30/30.


## Review finding: CIC data pins need per-pin bidirectional drive (must fix before layout)

Integration review (2026-09-29) against [sn64_snes_cic_lock.sv](../../fpga/rtl/sn64_snes_cic_lock.sv): the lock/key protocol swaps which side drives CIC_DATA0 (pin 55) and CIC_DATA1 (pin 24) between rounds (round 1: lock drives DATA1, key drives DATA0; key-stream element 7 bit 0 swaps them), and the lock expects a released pin to be defined by a pull-down. This sheet drives DATA0 through U206 (fixed FPGA-to-cartridge, shared enable) and only senses DATA1 through the 244. That would fight the key on DATA0 in rounds where the key drives it and cannot drive DATA1 at all. Replace with an individually enabled, per-pin bidirectional path for each of the two CIC data pins (drive with its own output enable, sense always, pull-down idle), move DATA0 off U206's shared enable, and re-run `verify_cart_interface.py` with the new contract. U206 then carries only console outputs (SYSTEM_CLK, CIC_CLK, CIC_SLAVE_RESET), enabled from the power sequencer's IFACE state so the CIC can run before the SNES clock starts (`cic_oe_n` in `sn64_top`).
