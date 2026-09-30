# USB-C initial programming and recovery architecture

The first SN64 revision must have a **side-mounted USB-C data port for initial loading from a blank board and later updates**. This is an explicit user requirement. The implemented circuit draft uses an FT232HL hardware USB/MPSSE bridge, with an independently powered USB interface and default-disabled JTAG isolation. Its USB enumeration must not depend on the main FPGA image or MCU firmware. The main SNES FPGA, its configuration flash, and their final power and pin assignments remain unselected; this document does not claim a complete working programming path.

## Reuse decision and source pins

Reuse the USB support circuit from SummerCart64's complete native KiCad design at commit `a1e7996d2cbece686820a5c785029c68514f17b0`: [schematic](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_sch), [PCB](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_pcb). Its hardware uses CERN-OHL-S-2.0; preserve the upstream hardware notices and distinguish them from the repository's software license.

The source block contains U3 FT232HL, U4 93AA56 EEPROM, J1 DX07S016JA3R1500 USB-C, and X1 ECS-3225MV-120-CN 12 MHz oscillator. A fresh source netlist confirms R6=12 kΩ 1% at REF, R7=12 kΩ at /RESET, filtered VPHY/VPLL through L1/L2, and their C7/C8 100 nF bypass capacitors. Preserve and review the source decoupling, clock, USB routing and EEPROM interface while adapting the power domains and protection for SN64. Reuse of these support circuits does not authorize connecting the old FPGA-side USB nets unchanged.

SummerCart64's existing route is different: its [EEPROM template](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/fw/ftdi/ft232h_config.xml) selects **FT1248**, and U3's AD/AC bus signals connect to normal FPGA I/O. Its [initial build procedure](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/docs/06_build_guide.md) also requires an external 3.3 V USB-to-UART adapter. [primer.py](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/sw/tools/primer.py) talks to the STM32 bootloader, loads a temporary FPGA primer into MCU RAM, then programs the remaining images. **Do not copy that EEPROM template or initial-loading dependency into SN64.** SN64's proposed on-board bridge will drive the eventual FPGA's dedicated JTAG interface directly.

An alternative is [Tigard's complete KiCad FT2232H design](https://github.com/tigard-tools/tigard/tree/e255a56893832f122e6f2f5be5826b3cba01d297), published under [CC-BY-SA 4.0](https://github.com/tigard-tools/tigard/blob/e255a56893832f122e6f2f5be5826b3cba01d297/LICENSE.txt). Its two channels and directional translation are useful references if simultaneous UART and JTAG later become necessary. FT232HL is preferred now because it reuses the already examined SummerCart64 circuit and satisfies the single programmer requirement without a new dual-channel bridge.

## Blank-board startup and EEPROM

[FTDI's FT232H datasheet v2.2](https://www.ftdichip.cn/Support/Documents/DataSheets/ICs/DS_FT232H.pdf), printed pp10, 41, 49–50, establishes:

- No or blank EEPROM: UART enumeration with VID `0403`, PID `6014`, and no USB serial number.
- Host software selects MPSSE after enumeration; MPSSE is not an EEPROM startup mode.
- Optional blank EEPROM can be programmed through USB using FT_PROG.
- ACBUS6 defaults to a pulled-up input and becomes GPIOH6 in MPSSE.
- Startup UART outputs are driven. ADBUS2 is initially RTS#, although JTAG uses it as the TDO input.

Therefore isolate both JTAG directions until the PC has configured MPSSE. Retain an optional EEPROM footprint for later SN64 identification and accurate descriptors, but make blank/no-EEPROM operation a required acceptance test. Any production EEPROM image must preserve ACBUS6's safe startup state. No FPGA bitstream or MCU firmware is needed to establish this USB bridge connection.

## Fixed isolation and pin contract

Use a **SN74AXC4T774PW** candidate with A-side supply `USB_3V3`, B-side supply `TARGET_VREF`, common ground, and local supply bypassing. The [TI datasheet, revision C](https://www.ti.com/lit/ds/symlink/sn74axc4t774.pdf) supports independent direction controls, 0.65–3.6 V rails, partial-power-down isolation, and high-impedance outputs if either rail is below 100 mV. Its controls are referenced to VCCA; /OE must be pulled up to VCCA for disabled startup. These features do not replace a check of the final target rail, leakage, ramp behavior and timing.

| FT232HL source | AXC4T774PW A-side | B-side target | Direction strap |
|---|---|---|---|
| ADBUS0, pin13 | A1, pin3 | B1, pin14 → TCK | DIR1, pin1 high |
| ADBUS1, pin14 | A2, pin4 | B2, pin13 → TDI | DIR2, pin2 high |
| ADBUS2, pin15 | A3, pin5 | B3, pin12 ← TDO | DIR3, pin7 low |
| ADBUS3, pin16 | A4, pin6 | B4, pin11 → TMS | DIR4, pin8 high |
| ACBUS6, pin30 | /OE, pin9 | Enables all four channels | 10 kΩ pull-up to USB_3V3; low enables |

Translator VCCA is pin16, VCCB pin15, and GND pin10. `TARGET_VREF` must track the actual powered target JTAG bank. It is a voltage reference/supply for the translator B side, not a command to power the FPGA from an FTDI I/O pin. Include any required target power-good qualification without allowing it to override the default-disabled /OE. Target reset/configuration pins need their own safely isolated controls if the selected FPGA requires them.

## Host software contract: ACBUS6 = status GPIO14

The inspected openFPGALoader commit is **`676e53ec73d2261c974d610b7cf0693117c8d2ef`**. Its [cable definition](https://github.com/trabucayre/openFPGALoader/blob/676e53ec73d2261c974d610b7cf0693117c8d2ef/src/cable.hpp) supports generic `ft232` at `0403:6014`. [CLI handling](https://github.com/trabucayre/openFPGALoader/blob/676e53ec73d2261c974d610b7cf0693117c8d2ef/src/main.cpp) and [MPSSE initialization/teardown](https://github.com/trabucayre/openFPGALoader/blob/676e53ec73d2261c974d610b7cf0693117c8d2ef/src/ftdipp_mpsse.cpp) provide `--status-pin 14`: GPIO14 is high-byte bit6, hence ACBUS6. Its active-low status behavior fits the translator /OE contract without modifying upstream code.

The later SN64 command wrapper must always include this option. Illustrative detection command, **not yet tested against SN64 hardware**:

```text
openFPGALoader -c ft232 --status-pin 14 --detect
```

At this source revision, initialization resets the mode, selects MPSSE, then sends:

1. `SET_BITS_LOW`: value `0x08`, direction `0x0B`, setting TCK/TDI outputs low, TMS output high, and TDO input.
2. `SET_BITS_HIGH`: value `0x08`, direction `0x4B`, driving ACBUS6 low **after** those data directions are configured.
3. Normal JTAG operations follow. Clean teardown raises GPIO14 before resetting MPSSE mode.

Generic `ft232` **without** `--status-pin 14` leaves ACBUS6 as an input, so the pull-up keeps the translator disabled. The default cable definition also drives ACBUS0/1 low and ACBUS3 high; reserve those pins unless software configuration is changed deliberately. Do not use ACBUS7 for this enable: its reset bias differs, and it can have a USB power-sense role.

A separately maintained custom cable profile could instead explicitly assign GPIOH6, but would need its own safe teardown. Pin and test the host-tool release used for production. Process termination, reconnect, USB reset/suspend, failed initialization, and abnormal target rail ramps still require bench verification; source-code ordering is not measured timing proof.

## USB power and persistent configuration

The FT232H default descriptor is bus-powered, 500 mA; this is not measured consumption or automatic permission to power the whole adapter. VCCIO is 2.97–3.63 V. The datasheet distinguishes internal-regulator current (52 mA typical with 3.3 V input) and PHY current (30 mA typical, 60 mA maximum); do not turn these separate table entries into an unverified total. Its 3.3 V VREGIN arrangement is qualified for revision C. See printed pp42–47 of the FTDI datasheet and qualify the ordered silicon accordingly.

The root power design must keep USB bridge startup independent, satisfy USB pre-configuration/suspend/inrush requirements, and prevent USB backfeed into N64/M64. A Type-C receptacle alone does not establish extra current or USB-PD capability. Powering the eventual FPGA and flash during programming remains a separate load/sequencing decision. This programmer block cannot establish the complete SN64 power budget.

[openFPGALoader's programming guide](https://trabucayre.github.io/openFPGALoader/guide/first-steps.html) distinguishes volatile FPGA loading from persistent flash programming. JTAG access to a blank FPGA is only the first step. Persistent boot requires the exact FPGA configuration mechanism, supported flash part, pin routing, boot straps, image format and programming algorithm. Some targets use a temporary SRAM-loaded JTAG-to-SPI bridge; see the pinned [spiOverJtag implementations](https://github.com/trabucayre/openFPGALoader/tree/676e53ec73d2261c974d610b7cf0693117c8d2ef/spiOverJtag). Others use device-specific internal configuration flash. A compatible USB cable definition alone proves neither route.

The target acceptance test must program the persistent image through the side USB-C port, disconnect power completely, and demonstrate autonomous configuration on the next boot. If the selected target lacks a suitable JTAG-to-flash route, add an explicit direct-flash access/recovery design; do not silently replace the mandatory USB first-load capability with an external programmer.

## Implemented KiCad circuit, revision 0.2-usb

The native [USB child sheet](../../hardware/sn64/usb-programmer.kicad_sch) now implements the bridge and isolation circuit. It is connected to the cartridge sheet by common GND; no USB supply is tied to a host supply. The generated [net map](../../hardware/sn64/interfaces/usb-programmer-net-map.csv) is an audit aid. The independent validator uses separately authored pin tables rather than that generated map.

| References | Implemented purpose and remaining qualification |
|---|---|
| J101, R101/R102 | JAE DX07S016JA3R1500; R101/R102 5.1 kΩ 1% are now DNP because the TUSB320 (U301, power sheet) presents Rd; side placement and shell cutout remain open. JTAG reaches ECP5 balls T5/R5/V4/U5 and TARGET_VREF comes from FPGA_3V3 through R414 (FPGA sheet). |
| U101/U102 | USBLC6-2SC6 arrays on D+/D− and CC1/CC2 respectively; paired pins need flow-through placement/routing and short ground paths |
| U103, C101–C103 | AP2112K-3.3TRG1 regulator for programmer-only USB_3V3; 4.7 µF + 1 µF VBUS input and 4.7 µF output; exact capacitor MPNs/derating and power behavior pending |
| U104, L101/L102, R103/R104, C104–C111 | FT232HL revision C, filtered analog supplies, REF/reset and local bypassing; not the SummerCart64 FT1248 interface |
| Y101, C115/C116 | ABM3B-12.000MHZ-10-1-U-T passive crystal and provisional 11 pF load capacitors; source oscillator replaced; [clock/mechanical qualification](usb-connector-mechanics.md) remains open |
| U105, R105, C112/C113 | SN74AXC4T774PWR fixed JTAG directions and 10 kΩ default-disabled /OE pull-up; powered from USB_3V3 and target-supplied TARGET_VREF |
| R108–R114, J102 | 33 Ω JTAG series options, 10 kΩ target idle pulls, and six-contact service header; final target hookups and placement/timing remain open |
| U106, R106/R107, C114 | Optional 93AA56BT-I/OT EEPROM marked DNP; USB startup must work without it; populate only with the separately validated descriptor/GPIO image |

J102 pin order is **1 TARGET_VREF, 2 GND, 3 TCK, 4 TDI, 5 TDO, 6 TMS**. This is an SN64 service pinout, not a claim of compatibility with a standardized keyed debug connector. Only one programmer may drive the JTAG nets. Place the TDO series option near its target-side source when the target is integrated. Generic passives and the service-header body still need final manufacturer selections for an assembly BOM.

ERC power flags behind the regulator filters and on externally supplied TARGET_VREF express intended power origins; they do not implement a target supply. The FTDI EEPROM clock/chip-select pin types were corrected from the reused symbol to outputs according to the FTDI datasheet. Full reuse/modification records are in [THIRD_PARTY.md](../../hardware/sn64/THIRD_PARTY.md).

The current [independent USB review](../../hardware/sn64/validation/usb-review.md) passes 64 static checks, with no USB-sheet ERC violations. There is no PCB routing or fabricated prototype, so these checks establish connectivity and pin/footprint consistency only.

## Circuit blocks and validation still required

- Qualify and lay out the implemented receptacle, CC termination, ESD arrays and programmer-only power path, including real plug/enclosure clearance.
- Qualify the implemented FT232HL support circuit and crystal/load capacitors; define and test a safe optional EEPROM image.
- Validate the implemented four-channel isolation and ACBUS6 /OE contract, connect the actual target-voltage rail, and add any required target power-good/reset controls.
- Selected FPGA/configuration-storage hookup, boot straps and persistent programming support; this is pending part selection.
- A packaged PC loading/update procedure with driver setup, mandatory GPIO14 option, image identification and readback/verification where supported.
- Tests from erased EEPROM and erased target storage; target-off leakage; all power-up/down orders; abnormal USB/software interruptions; successful reprogramming and cold-boot persistence.

No external uploads or supplier communications were made for this research. Published PCBWay loading services may be used later, subject to its acceptance of the exact selected FPGA/flash and programming procedure. That service does not substitute for the first-revision USB-C loading path.
