# FPGA schematic sheet and board pinout

Drafted 2026-09-29, schematic rev `0.4-fpga`. This is the first real pin assignment of the ECP5 on the SN64 board. It also adds the FPGA power, configuration, flash, JTAG and N64-host isolation circuits. The sheet passes its own static checks (13/13), a 10-fault negative test and KiCad ERC (0 errors) on a validation copy of the project. The board top level routes with these pins and meets all five clocks in nextpnr. **Nothing here is built or measured.**

**Round-3 integration (2026-09-29):** the sheet is now attached to the real root (page 4) and every pending pin is wired by name to the power, clock/A-V and USB sheets ([system-integration.md](system-integration.md#schematic-integration-round-3-2026-09-29)). Changes made there: (1) every reference designator moved from 3xx to 4xx (the power sheet already used U301-U307, R301-R319, C301-C340, TP301-TP308 and #FLG301-#FLG304); this document uses the new numbers. (2) #FLG401-#FLG403 were removed because the power sheet originates FPGA_1V1/2V5/3V3; #FLG404 stays. (3) `si_clk2` is constrained at 27.0399 MHz (PAL pixel clock, the faster region). On the integrated root the verifier passes 12/13: `no_5V_12V_or_VBUS_net_reaches_any_FPGA_ball` fails on `efuse_fault_n` (ball K4), which the power sheet derives from a 5V_PRE divider; that is an open owner decision. The "Integration still to do" list below is historical except where noted there.

## Plain-language summary

The FPGA chip has 381 balls on its underside. Every one is now decided:

- The 113 ground, 20 core-power, 4 auxiliary-power and 18 I/O-power balls go to their supplies, with the decoupling capacitors Lattice's checklist asks for.
- The 10 "reserved" balls stay unconnected, as Lattice requires.
- The configuration pins make the FPGA load itself from the flash chip at power-up.
- The 121 signals the FPGA design uses each have a ball, on the side of the chip facing the part they talk to:
  - the N64 bus on the top-left bank,
  - HDMI on the top-right bank,
  - the SNES cartridge on the two right-hand banks,
  - clocks, power control and the audio ADC on the left,
  - the flash on the bottom (configuration) bank.

Every I/O bank runs at 3.3 V. That keeps the choice simple and matches every chip the FPGA talks to.

The flash is a Winbond W25Q128JVSIQ. It is a basic part at JLCPCB, and it leaves the factory already in the four-wire read mode the N64 menu reader uses.

The N64 bus passes through three electronic switches. They connect the FPGA to the console only while the console's own 3.3 V is present. When the adapter runs from USB alone, the switches are open, so the FPGA cannot push current into a switched-off console.

## Files

| File | Role |
|---|---|
| [hardware/sn64/fpga.kicad_sch](../../hardware/sn64/fpga.kicad_sch) | Child sheet "FPGA" (A0, intended page 4): U401 LFE5U-85F (9 units), U402-U404 N64 bus switches, U405 flash, U406 host detector, U407 PROGRAMN hold, 59 capacitors, FB401, 19 resistors, D401, 8 test points |
| [hardware/sn64/tools/add_fpga_sheet.py](../../hardware/sn64/tools/add_fpga_sheet.py) | Authoring script with the single pin table. It writes the sheet, the pin-map CSV and the LPF. It refuses to overwrite without `--force`; a `--force` rerun is byte-identical (checked). `--validation-copy DIR` copies `hardware/sn64` to `DIR` (under `build/`) and attaches the sheet there. `--attach-real-root` applies that same attachment to `hardware/sn64/sn64.kicad_sch`; it is for the integration step and was **not** run. Without that flag the script never edits the real root. |
| [hardware/sn64/tools/verify_fpga_sheet.py](../../hardware/sn64/tools/verify_fpga_sheet.py) | Independent checker with its own Lattice tables and a `--negative-test` fault-injection mode |
| [hardware/sn64/validation/fpga-check.json](../../hardware/sn64/validation/fpga-check.json) | Checker result (positive run and negative test) |
| [hardware/sn64/interfaces/fpga-pin-map.csv](../../hardware/sn64/interfaces/fpga-pin-map.csv) | port, ball, bank, IO_TYPE, LPF attributes, FPGA net, sheet label, group, notes. Also lists the LVCMOS33D complement balls and the dedicated config/JTAG balls. |
| [fpga/constraints/sn64_board.lpf](../../fpga/constraints/sn64_board.lpf) | Board constraints: LOCATE and IOBUF for all 121 ports, four `FREQUENCY PORT` lines, `FREQUENCY NET "clk_snes"`, and `SYSCONFIG CONFIG_IOVOLTAGE=3.3 COMPRESS_CONFIG=ON` |

No project-local symbol was needed. Every part uses an installed KiCad 10.0.6 symbol, embedded unmodified:

- `FPGA_Lattice:LFE5U-85F-6BG381x`
- `74xx:SN74CB3Q3384APW`
- `Memory_Flash:W25Q128JVS`
- `74xGxx:74LVC1G14`
- `74xGxx:74LVC1G07`
- `Device:*`
- `Connector:TestPoint`
- `power:PWR_FLAG`

So `SN64_FPGA.kicad_sym` and `fpga-provenance.json` were not created. The source hashes are recorded below.

## Sources

Downloaded to `build/fpga-sheet/datasheets/` (untracked) on 2026-09-29:

| Source | Revision | SHA-256 |
|---|---|---|
| Lattice ECP5U-85 pinout CSV, [document 50487](https://www.latticesemi.com/view_document?document_id=50487) | Rev 1.0, "Revised Nov. 2, 2015" | `c97b21eca6f07893c6e4643a74221436c889c2580238537e9f679a7731ca45a3` |
| Lattice ECP5/ECP5-5G data sheet, [FPGA-DS-02012](https://www.latticesemi.com/view_document?document_id=50461) | 3.4, Sept 2025 | `26570f8bb2b800123120829cacd75d818d7a985d573797610521b5bda2e293c3` |
| Lattice hardware checklist, [FPGA-TN-02038](https://www.latticesemi.com/view_document?document_id=50482) | 2.1, Sept 2025 | `7b32b411d44a9b585972ea43583c9000fdb596f5322e4c9c5f3182591c44feae` |
| Lattice sysCONFIG guide, [FPGA-TN-02039](https://www.latticesemi.com/view_document?document_id=50462) | 2.5, Jan 2026 | `6931b2a1733b3530dfe6f8b661f56f6744b0c08b0fa731193dec6fa9d00a341b` |
| Lattice sysI/O guide, [FPGA-TN-02032](https://www.latticesemi.com/view_document?document_id=50464) | 1.4, Jan 2023 | `47830ffc0c7a879c8458431a1861c82a7656d0015092826337a317a6b08ee5cc` |
| Lattice sysCLOCK guide FPGA-TN-02200 | 1.3 | `69843f2d6bf92bc19ea1f383b3c7fb0fcb9f1a2077efbce6d238c1c3f2496069` (already recorded in [clock-plan.md](clock-plan.md)) |
| Winbond [W25Q128JV](https://www.winbond.com/resource-files/w25q128jv%20revf%2003272018%20plus.pdf) | Rev F, 2018-03-27 | `809f066e62bcde10b12c2202daf05f4776929ad7dc5f9d3b5131cdcc84502bc1` |
| ISSI [IS25LP128F](https://www.issi.com/WW/pdf/25LP-WP128F.pdf) (comparison only) | Rev A10 | `40e97f5edba8db626da6ba7de83385d7d00bbbcb37616d14c6ed427aff0d3496` |
| TI [SN74CB3Q3384A](https://www.ti.com/lit/ds/symlink/sn74cb3q3384a.pdf) | SCDS114E, Sept 2026 | `f5deefac358fd9c042a8bd61b14d4859563ee1d45ca84243589945dabe650575` |
| TI [SN74LVC1G14](https://www.ti.com/lit/ds/symlink/sn74lvc1g14.pdf) | SCES218AA, Oct 2025 | `d64e41f0a267e8c5f73873058561642c57e093a2b7ecb4715d7ab62f0ef31a4f` |
| TI [SN74LVC1G07](https://www.ti.com/lit/ds/symlink/sn74lvc1g07.pdf) | SCES296AG, Oct 2025 | `5c68b82a5110b337457ca918b149432c6b9c605be7849e76116f108ddbd7abee` |

Reuse references:

- **ULX3S.** Commit `6a92cec6b177191c5b0f80e260013a1f8ec147dd`, `flash.sch` SHA-256 `a31d5899…250889d`, the staged copy under `.local/archive/…/fpga-board-research/`. Reused for the flash pull network: CS 4.7 k, IO2/IO3 10 k, SCK about 1 k (ULX3S uses 1.1 k "for BOM simplification"). Also reused for the HDMI ball pairs. The ULX3S uses 15 k on PROGRAMN/INITN/DONE; SN64 follows the Lattice checklist's 4.7 k instead. The license condition is in [fpga-board-selection.md](fpga-board-selection.md). Only circuit facts and ball numbers were used; no ULX3S file was copied.
- **SummerCart64.** Commit `a1e7996d`, `hw/pcb/sc64v2.kicad_sch` and `fw/project/lcmxo2/sc64.lpf`. Reused for the N64 pad settings and the no-series-resistor finding.

The KiCad symbol was checked ball by ball against the Lattice CSV: all 381 pin numbers and names agree. Its description field says "1.2V", but that is the ECP5-5G core voltage; LFE5U runs at 1.1 V (DS-02012 Table 3.2, TN-02038 Table 16.1 item 1.1). The symbol was not edited.

## Device and power

The Value field is `LFE5U-85F-6BG381C`, per the task. A field records the stocked alternate, `LFE5U-85F-8BG381I`. It has the same CABGA381 ball map in the same pinout CSV, but timing must be re-run for grade 8.

| Balls (Lattice CSV) | Net | Decoupling (TN-02038 Table 3.1: "10 µF x 3 + 100 nF per pin", "120 Ω FB + 10 µF + 100 nF per pin", "10 µF + 100 nF per pin") |
|---|---|---|
| VCC ×20 | `FPGA_1V1` | 20 × 100 nF 0402 X7R + 3 × 10 µF 0603 X5R |
| VCCAUX ×4 | `FPGA_VCCAUX`, from `FPGA_2V5` through FB401 BLM18PG121SN1D (120 Ω at 100 MHz, 50 mΩ, LCSC C14709, basic) | 4 × 100 nF + 1 × 10 µF |
| VCCIO0/1/2/3/6/7/8 (2+2+3+3+3+3+2) | `FPGA_3V3` | 100 nF per ball + 10 µF per bank |
| GND ×113 | `GND` | — |
| RESERVED ×10 (W4, W5, W8–W11, W13, W14, W17, W18) | not connected | — |

**Unused and SERDES-related balls.**

- DS-02012 §4.1 says RESERVED "is reserved and should not be connected to anything on the board".
- On LFE5U, the LFE5UM's SERDES positions are listed as either GND or RESERVED in the LFE5U CSV. TN-02038 §14 says these power pins on ECP5U devices "are required to be connected to GND when migrating to LFE5UM is not considered". SN64 does not plan a SERDES part, so they follow the CSV.
- Unused user I/O are left open. TN-02039 §4.5: "GPIO not defined in the user design remains output tristate and the input has a weak pull-down enabled."
- The unused bank-8 dual-purpose pins (D4–D7, SN, CS1N, DOUT, WRITEN) are left open. TN-02038 Table 6.3 note 1: "Leave unused configuration ports open."

**Bank plan.** All VCCIO are 3.3 V. The standard for each bank's signals:

- the cartridge translators' B side (SN74LVC4245A VCCB = `INTERFACE_3V3`),
- the N64 PI (3.3 V host),
- HDMI LVCMOS33D (the ULX3S arrangement),
- bank 8 flash (TN-02038 §7: "The flash voltage should match the VCCIO8 voltage"),
- JTAG (DS-02012: "VCCIO8 is used for configuration and JTAG").

TN-02038 §3.6 also says "Connect unused VCCIO pins to a power rail. Do not leave them open." Every bank is used anyway.

| Bank | Side (DS-02012 §2.14) | Used for |
|---|---|---|
| 0 | top, hot-socket capable | N64 PI AD0–15, ALE, /RD, /WR, /RESET, /NMI, CIC, SI clock/data, /INT (27 of 27 balls) |
| 1 | top | HDMI 4 × LVCMOS33D pairs (ULX3S balls A16/B16, A14/C14, A12/A13, A17/B18), HPD, DDC |
| 2 | right | cart_address[0..23], cart_pa[0..7] |
| 3 | right | cart_data, strobes, SYSTEM_CLK, CIC, OE/DIR controls, sense inputs |
| 6 | left | osc_25, si_clk0, ADC I2S, power-control inputs/outputs |
| 7 | left | si_clk1, si_clk2, Si5351 I2C, status LED |
| 8 | bottom, configuration | flash CS/D0–D3 (MCLK is the dedicated CCLK ball U3) |

**Power-up order.** DS-02012 §3.5: "it is required to ramp VCCIO8 above VIH of the external SPI Flash, before at least one of the other two supplies (VCC and/or VCCAUX) is ramped to VPORUP voltage level. If the system cannot meet this… then the system must keep either PROGRAMN or INITN pin LOW during power up".

The sheet does not rely on the power sheet's ramp order. U407 (SN74LVC1G07, open drain, powered from `FPGA_3V3`) holds PROGRAMN low until `fpga_rails_ok` is high. R415 (100 k) keeps its input low while undriven. While `FPGA_3V3` is absent, the PROGRAMN pull-up has no supply, so PROGRAMN stays low anyway.

TN-02038 §4 separately says "VCCIO supplies should be powered up before or together with the VCC and VCCAUX supplies". That is a power-sheet obligation, listed below.

## Configuration and flash

| Item | Circuit | Source |
|---|---|---|
| Mode | CFG[2:0] = 010 (Master SPI): CFG0 U4 and CFG2 R4 tied to GND, CFG1 T4 through R401 4.7 k to VCCIO8 | TN-02038 Table 6.3 ("MSPI … 010") and Table 6.2 ("1 k to 10 k pull-up to VCCIO8, 0 = GND") |
| PROGRAMN W3, INITN V3, DONE Y3 | 4.7 k to VCCIO8 each (R402–R404), test points TP401–TP403 | TN-02038 Table 6.2 |
| MCLK U3 | R405 33 Ω series at the FPGA; R406 1 k pull-up on the flash side; TP407 | Table 6.2 ("510 to 1 k pull-up … serial resistor placing near TX side", note "22 to 80 Ω") |
| CSSPIN R2 | R407 4.7 k pull-up, placed at the flash | Table 6.2 ("4.7 k to 10 k"; "Strong pull-up resistor is put close to the SPI flash") |
| D0 W2, D1 V2, D2 Y2, D3 W1 | D0→DI/IO0 (pin 5), D1→DO/IO1 (pin 2), D2→IO2 (pin 3, R408 10 k up), D3→IO3 (pin 7, R409 10 k up) | [bootrom-flash.md](bootrom-flash.md) "Fit pull-ups on D2/D3"; W25Q128JV rev F §3.3 pin table |
| User access after DONE | CS/D0–D3 are ordinary GPIO in user mode because `MASTER_SPI_PORT` defaults to DISABLE (TN-02039 Table 7.1). MCLK is reached only through USRMCLK. | TN-02039 §4.7.10 and §4.9 |
| I/O voltage | `SYSCONFIG CONFIG_IOVOLTAGE=3.3` in the LPF; the default is 2.5 (TN-02039 Table 7.1). nextpnr accepted the line; the bitstream effect was not inspected. | — |

**Flash selection: W25Q128JVSIQ (LCSC C97521, JLC basic part, 54,669 in stock on 2026-09-29), not IS25LP128F.**

| Contract item ([bootrom-flash.md](bootrom-flash.md)) | W25Q128JVSIQ (rev F) | IS25LP128F-JBLE (rev A10) |
|---|---|---|
| EBh: 2 mode + 4 dummy clocks | Fig. 24a: "M7-0 Dummy Dummy", §8.2.11 "four Dummy clocks are required … prior to the data output". Mode byte 0xFF sent by `memory_flash` matches "M7-M0 should be set to Fxh". | Default EBh dummy cycles 6, "AXh has to be counted as a part of dummy cycles" (Table 6.11 note): also 6 in total |
| QE | §7.1.4: QE = 1 is "factory fixed default for part numbers with ordering options 'IQ' & 'JQ'". No production QE step. | "The default value of … QE … were set to '0' at factory": needs a QE programming step |
| tCLQV | 6 ns max (AC table; the adjacent 7 ns is tSHQZ, output disable) | not extracted |
| tSHSL (read deselect) | tSHSL2 10 ns; `memory_flash` gives 32–48 ns | — |
| Supply, package | 2.7–3.6 V, SOIC-8 208 mil | 2.3–3.6 V, SOIC-8 208 mil |
| JLC stock | basic, 54,669 | extended, 88, $7.15 |

**Round-trip budget** (contract: SCK out + tCLQV + trace below about 30 ns). With tCLQV = 6 ns, 24 ns remain for the USRMCLK path, the 33 Ω series resistor and the traces. The USRMCLK output delay is still unmeasured; [bootrom-flash.md](bootrom-flash.md) lists it as a hardware check.

Both the programmer path (openFPGALoader through ECP5 JTAG) and the N64 read path use this one flash. The 0x400000 image offset is unchanged.

## JTAG

- Balls: TCK T5, TDI R5, TDO V4, TMS U5. These are dedicated; the CSV lists them as bank "40", powered by VCCIO8.
- Hierarchical labels `jtag_tck`, `jtag_tdi`, `jtag_tdo`, `jtag_tms`.
- Pulls per TN-02038 Table 6.1: R410–R412 4.7 k up on TDI/TMS/TDO, R413 4.7 k down on TCK.
- `TARGET_VREF` comes from the VCCIO8 rail (`FPGA_3V3`) through R414 (0 Ω link). It is the B-side supply of the USB sheet's SN74AXC4T774, per [usb-programming-architecture.md](usb-programming-architecture.md).
- The USB sheet already has 10 k idle pulls in the same directions (R112 TCK down, R113/R114 TDI/TMS up). The two sets parallel and do not conflict (TCK 3.2 k down in total).

## Clock inputs

TN-02200 §8.3: "A dedicated PCLK clock pin must always be used to route an external clock source to FPGA logic and I/O". It also says "The ECP5… allows a PLL reference clock… to come from an external Primary Clock (PCLK) pin and route through the Primary clock network to drive… the input of a PLL".

TN-02038 §10 note: "For single-ended I/Os, use only PCLKT pins as primary CLK pads."

`osc_25` and `si_clk2` each drive logic directly (the housekeeping and pixel domains) as well as a PLL. `si_clk0` and `si_clk1` feed the DCSC. All four therefore sit on PCLKT balls:

| Port | Ball | Function | Feeds |
|---|---|---|---|
| osc_25 | G2 | PCLKT6_1 | housekeeping logic; host PLL CLKI through the primary clock network |
| si_clk0 | H2 | PCLKT6_0 | DCSC CLK0 (NTSC) |
| si_clk1 | G3 | PCLKT7_1 | DCSC CLK1 (PAL) |
| si_clk2 | F2 | PCLKT7_0 | pixel logic; TMDS PLL CLKI through the primary clock network |

The complement balls F1, G1, F3 and E2 are left unused to keep neighbours quiet.

**Which PLL each input reaches.** The dedicated GPLL input pins (A4/A5 ULC, A6/B6 ULC, C18/D17 URC, A19/B20 URC, P3/P4 LLC, U16/T17 LRC) each reach only their corner PLL (TN-02200 §7.1). They cannot also feed logic through a PCLK path. A PCLK input reaches any PLL through the primary network. In the routed run nextpnr placed `pll_tmds` at EHXPLL_UL and `pll_host` at EHXPLL_LL, fed from G2 and F2 over the global network.

TN-02200 §18.3.1 calls the dedicated pin "the recommended source for the PLL" because of its low-skew path. Using PCLK is the documented alternative. PLL input jitter through the primary network is a prototype measurement.

## HDMI

These are the ULX3S GPDI balls in bank 1, all top-bank PIO A/B pairs:

| Channel | True (A) | Complement (B) |
|---|---|---|
| hdmi_tmds[0] | A16 | B16 |
| hdmi_tmds[1] | A14 | C14 |
| hdmi_tmds[2] | A12 | A13 |
| hdmi_tmds_clock | A17 | B18 |

LVCMOS33D is an emulated differential output available "in pairs around all banks" (TN-02038 §12; TN-02032 Table 3.2). The LPF locates the true ball and nextpnr drives the complement. The sheet labels are `hdmi_d0_p`/`hdmi_d0_n` … `hdmi_ck_p`/`hdmi_ck_n`.

`hdmi_hpd` (E13), `hdmi_scl` (D15) and `hdmi_sda` (E15) are 3.3 V balls. The A/V sheet must deliver HPD and DDC at 3.3 V-safe levels; HDMI's own DDC and HPD are 5 V.

## N64 edge interface and host isolation

**Reference.** A fresh KiCad 10 netlist of SummerCart64 `sc64v2.kicad_sch` (commit `a1e7996d`) shows every N64 logic net as a two-node net from `J_N1` straight to the LCMXO2 (U8). CIC_CLK, CIC_DATA and /RESET have a third node on the STM32. For example, `N64_AD0: J_N1.28 – U8.60`. There are **no series resistors**, so SN64 adds none.

The FPGA pull settings copy `sc64.lpf`:

- PULLMODE=UP on CIC clock/data, /INT, /READ, /WRITE, ALE_H and SI data,
- DOWN on /RESET, /NMI, ALE_L and SI clock,
- NONE on AD[15:0].

JOYBUS (`n64_si_dq`, A6) and /INT (`n64_int_n`, B6) get balls and pulls now, although no RTL uses them yet. Without a port they would sit at the unused-pin weak pull-down (TN-02039 §4.5, 30–150 µA per TN-02038 Table 9.1) on two lines the console pulls up.

**Isolation requirement.** [power-architecture.md](power-architecture.md): "Host interface pins must remain isolated during USB-only operation." Two datasheet facts decide the circuit:

- TN-02038 §2: "All other VCCIOX are not monitored during power-up, but need to be at valid and stable level before the device is configured and entered into User Mode." A bank powered from the host's 3.3 V would therefore be unpowered during every USB-only configuration. That rules out a host-powered bank.
- DS-02012 §3.6: "The left and right banks generally do not support hot-socketing… the device pins present a low-impedance path to ground if the GPIO input voltage exceeds the VCCIO rail voltage." Top and bottom banks are specified at IDK_HS ≤ ±1 mA for 0 ≤ VIN ≤ VIH(max) (Table 3.5). So the N64 goes on top bank 0.

**Chosen circuit.** U402–U404 are SN74CB3Q3384APWR 10-bit FET bus switches (LCSC C469874, 4,945 in stock). Port A goes to the N64 edge nets and port B to the FPGA bank-0 balls. VCC is `FPGA_3V3`. 27 signals use 27 of the 30 channels; 3 are open.

TI SCDS114E quotes:

- "When OE is high, the associated 5-bit bus switch is OFF, and a high-impedance state exists between the A and B ports."
- "This device is fully specified for partial-power-down applications using Ioff. The Ioff circuitry prevents damaging current backflow through the device when it is powered down. The device has isolation during power off."
- Ioff is 1 µA maximum at VCC = 0, VO = 0 to 5.5 V.
- It "supports rail-to-rail switching on the data input/output (I/O) ports", unlike NMOS-only CBT parts that stop near VCC − Vt.
- tpd is 0.15 ns maximum, and ron is 3–9 Ω depending on VCC and VI.

**OE control.** OE = NOT(HOST_3V3 present).

- U406 is an SN74LVC1G14 Schmitt inverter (LCSC C7835), powered from `FPGA_3V3`. Its input is `HOST_3V3` through a divider: R416 10 k series and R417 33 k to GND.
- SCES218AA: VT+ is 1.5–1.87 V and VT− is 0.84–1.14 V at VCC = 3 V. The switches therefore close once `HOST_3V3` passes about 1.95–2.44 V and open below about 1.09–1.49 V. These values are provisional.
- The input has Ioff: "Ioff supports partial-power-down mode operation". It tolerates 3.3 V while `FPGA_3V3` is off.
- R418 10 k ties OE to VCC. SCDS114E: "To ensure the high-impedance state during power up or power down, OE must be tied to VCC through a pullup resistor".

| Condition | Result |
|---|---|
| USB only: FPGA powered, console off | U406 input low, OE high: switches open. The FPGA cannot back-power the console, and its pulls do not reach the edge. |
| Console on, FPGA rails still off | Switch VCC = 0: isolation during power off (Ioff) |
| Both on, FPGA not yet configured | Switches closed. The console sees tri-stated FPGA pins with weak pull-downs. |
| Both on, configured | Normal operation, less than 0.15 ns added delay |

`host_3v3_ok` was **not** used for OE. [sn64_power_sequencer.sv](../../fpga/rtl/sn64_power_sequencer.sv) documents it as "host/USB-derived system rails valid", so it can be high in USB-only operation.

## Cartridge side

- 63 balls in banks 2 and 3 use the cartridge sheet's lower-case labels unchanged: 24 address, 8 PA, 8 data, 8 strobes, SYSTEM_CLK, 6 CIC, 5 OE/DIR/reset controls, 3 sense inputs.
- The cartridge sheet's translators and receivers keep every 5 V node off FPGA balls. The checker repeats that search from the FPGA side (next section).
- `cart_data[7:0]` is bidirectional with PULLMODE=DOWN. The FPGA drives it only while `data_dir` = 1 (board-top edit below).
- `cic_data0`/`cic_data1` have PULLMODE=DOWN, matching the cartridge sheet's 100 k A-side pull-downs.

## Verification (run 2026-09-29, KiCad 10.0.6, OSS CAD Suite 20260928)

Run from the repository root with KiCad's Python:

1. `add_fpga_sheet.py --kicad-share … --validation-copy build/fpga-sheet/proj`. This attaches the sheet to a copy of the root: 92 sheet pins, 55 connected to existing root labels, 26 cartridge-sheet no-connect markers replaced by labels. The rest are pending sheets and get no-connect markers.
2. `verify_fpga_sheet.py --project build/fpga-sheet/proj --board-top build/fpga-sheet/rtl/sn64_board_top.sv --lattice-csv <ECP5U-85 CSV> --datasheets build/fpga-sheet/datasheets`: **`PASS: 13/13 FPGA-sheet checks`**.
3. `verify_fpga_sheet.py … --negative-test`: **`PASS: negative test, 10/10 faults detected`**.
4. `kicad-cli sch erc` on the copy: **0 errors**.
5. Idempotence: a second `add_fpga_sheet.py --force` reproduced the three outputs byte for byte. Without `--force` it refuses.

**The 13 checks in step 2:**

- one LFE5U-85F on the CABGA381 footprint
- every power ball on its rail (VCCAUX through exactly one ferrite bead from `FPGA_2V5`; all VCCIO on `FPGA_3V3`; RESERVED unconnected)
- decoupling counts per TN-02038 Table 3.1
- MSPI straps and PROGRAMN/INITN/DONE pull-ups, plus the PROGRAMN hold from `fpga_rails_ok`
- flash on the bank-8 sysCONFIG balls, with the MCLK series resistor and the CS/SCK/IO2/IO3 pull-ups in range
- JTAG labels and pulls, and TARGET_VREF linked to VCCIO8
- every board-top port bit's ball agrees across LPF, CSV and netlist, including:
  - bank,
  - IO_TYPE,
  - LVCMOS33D complement nets,
  - clock ports on PCLKT balls,
  - the five FREQUENCY lines,
  - no dedicated ball in the LPF
- no 5V/12V/VBUS rail reachable from any FPGA ball through resistors, beads or switch channels
- the 27 N64 edge nets reach the FPGA only through one host-gated switch channel each
- every cartridge-side ball reaches a cartridge-sheet IC pin, not just a same-named label
- all 381 balls accounted for, with unused I/O open
- the embedded tables match the Lattice CSV (381 rows, SHA-256 above)
- ERC 0 errors

**ERC warnings on the copy:**

- 11 `similar_labels`. They come from contract names that differ only in case: `jtag_*` against the USB sheet's local `JTAG_*`. The FPGA-side N64 nets were renamed `fpga_n64_*` so they do not collide with `N64_*`.
- 5 `isolated_pin_label`: the N64 KEY1/KEY2, VIDEO_SYNC and AUDIO_L/R edge labels, which stay unused.
- 5 `pin_to_pin`: the cartridge sheet's existing U206 spare inputs.

**Negative test: 10 faults, each caught by the named check:**

- bank-6 VCCIO moved to `FPGA_1V1`
- CFG0 strapped high
- flash IO2 pull-up removed
- TCK pull-down moved to 3.3 V
- `SNES_5V_CART` on ball T18
- N64 AD0 wired straight to the FPGA
- two LPF sites swapped
- `osc_25` moved to a non-clock ball in the CSV
- `si_clk2` moved off its PCLKT ball in the LPF
- the `cart_address0` ball label renamed, so it no longer reaches U201

**Against the unmodified `fpga/rtl/sn64_board_top.sv`, the checker fails the port-agreement check.** It lists exactly the ports the board-top edit changes (`si_*_oe`/`si_sda_in`, `cart_data_out`/`in`, `cart_reset_pull`, and the new ports). This is expected until that edit is applied.

**Place and route with the real pinout.**

- Setup: a copy of `route_top.py` with `--lpf`/`--top-file` options (`build/fpga-sheet/route_top_lpf.py`; patch in the integration notes). It routed the proposed board top (`build/fpga-sheet/rtl/sn64_board_top.sv`, the unified diff in `build/fpga-sheet/rtl/sn64_board_top.patch`) with `fpga/constraints/sn64_board.lpf`.
- nextpnr-ecp5: 85k, CABGA381, speed 6. Exit 0, 1 warning (the `clk_snes` user constraint overrides the equal derived one), 0 errors.
- Resources: 121/365 TRELLIS_IO, 36,458 TRELLIS_COMB (43 %), 13,623 FF, 143/208 DP16KD, 2 EHXPLLL, 1 DCSC.
- Sources: the repository snapshot at about 19:05. It included `sn64_i2s_rx.sv` and `sn64_audio_mix.sv`, which another task had just added to `sn64_top` (the `adc_*` ports).

| Clock | Required | Achieved |
|---|---:|---:|
| SNES master (`clk_snes`, after the DCSC) | 21.48 MHz | 28.79 MHz |
| Host (`clk_host`, PLL) | 62.5 MHz | 83.35 MHz |
| Housekeeping (`osc_25`) | 25.00 MHz | 54.22 MHz |
| HDMI pixel (`si_clk2`) | 27.02 MHz | 58.28 MHz |
| TMDS bit clock (`clk_pixel_x5`) | 135.12 MHz | 158.20 MHz |

Cross-domain paths are synchronised by design and are not timed. There is no I/O timing (setup/hold to the cartridge, PI or flash) in this run. **This is internal timing on the real pin placement, not a board timing sign-off.**

## Findings for other sheets

1. **Cartridge sheet R206–R208 (10 k pull-ups on `ctl_oe_n`, `cic_oe_n`, `data_oe_n` to `INTERFACE_3V3`) are too weak against the ECP5's configuration-time pull-down.**
   - TN-02039 §4.5: "The GPIO of the device at power-up defaults to tristated outputs with active weak input pull-downs." The weak pull-down current is 30–150 µA (TN-02038 Table 9.1).
   - At 150 µA, 10 k leaves 3.3 − 1.5 = 1.8 V. That is below the SN74LVC1G07's VIH of 2.0 V at 3.0–3.6 V, so during a reconfiguration with the interface rail still up, the translator enables are undefined.
   - 4.7 k gives at least 2.6 V. A 3.3 V pin driving low then sinks 0.7 mA.
   - The pull-downs R209/R210/R220/R221 act in the same direction as the FPGA default and are fine.
2. **USB sheet.** Its JTAG pulls agree in direction with the ones here. The USB sheet may DNP R112–R114 or keep them in parallel. #FLG103 on `TARGET_VREF` can be removed once R414 feeds it.
3. **Power sheet obligations** (from DS-02012 §3.3–3.5 and TN-02038 §4):
   - monotonic ramps of 0.01–10 V/ms,
   - VCCIO (`FPGA_3V3`) up before or with `FPGA_1V1`/`FPGA_2V5`,
   - `fpga_rails_ok` valid only when all three FPGA rails are in range,
   - its own default-off pull-downs on the `cart_5v_enable`/`iface_rail_enable` inputs. The FPGA pins only weakly pull down while unconfigured.
   - Regulators accurate to within 3 % (TN-02038 §2.2).
4. **A/V sheet obligations:** `hdmi_hpd`, `hdmi_scl` and `hdmi_sda` must reach the FPGA as 3.3 V signals (level shifter or clamp), and `hdmi_d*_p/n` need the A/V sheet's series/termination network.

## Integration still to do

The exact edits are in the task report (integration_edits). In summary:

- attach the sheet to the root,
- add the `SN64_FPGA` lines only if a project library is ever added (not needed now),
- apply the board-top patch and the `route_top.py` `--lpf` option,
- change R206–R208 to 4.7 k,
- remove the cartridge sheet's FPGA-side root no-connect markers,
- export JTAG and `TARGET_VREF` from the USB sheet,
- remove #FLG401–#FLG403 when the power sheet drives the rails; #FLG404 stays, because `FPGA_VCCAUX` is fed only through FB401.

## Limits and open items

- Schematic only. There is no PCB, BGA escape plan, SI, PDN or thermal analysis, and no power estimate (TN-02038 §5 asks for Diamond's power calculator).
- 3.3 V on every bank makes no use of the lower-voltage banks. SSTL/HSUL need VREF balls; none are used.
- The sheet was not rendered and visually inspected; the PDF was exported, but no rasterizer was available. Symbol placement is script-generated on A0 with label-per-pin connections, and overlaps have not been checked by eye.
- These are datasheet claims, not measurements on SN64 hardware:
  - the switch threshold divider R416/R417 and pull values,
  - USRMCLK delay and flash round trip,
  - PLL input jitter through the primary network,
  - hot-socket leakage.
- `CONFIG_IOVOLTAGE`/`COMPRESS_CONFIG` were accepted by nextpnr. Their effect on the bitstream and the MCLK frequency setting were not inspected.
- The `LFE5U-85F-8BG381I` alternate needs its own route at speed grade 8.
