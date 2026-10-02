# Pre-order review of the v2 board (2026-10-02)

**Outcome: the files for a price quote are ready and nothing has been sent to PCBWay. The review found faults that no simulation here could have shown. All that can be put right on the PC are put right on the board. What is left needs a real socket, a real console or PCBWay's answer.**

The owner asked on 2026-10-02: "do everything except sending the files to pcbway because i need a quote from them first. you also need to ensure the usbc that we will use fits the hole you made, or rather vice versa".

Everything below is a check on the PC. Nothing has been built or measured.

## What is ready

| | Where |
|---|---|
| What to type into PCBWay's forms, with four questions for their engineer | [quote-sheet.md](../../hardware/sn64-v2/production/quote-sheet.md) |
| Gerber and drill files, test netlist, notes for the board maker | [production/fabrication](../../hardware/sn64-v2/production/fabrication) |
| Parts list, placement file, assembly drawings, schematic as a PDF | [production/assembly](../../hardware/sn64-v2/production/assembly) |
| The two zip files for uploading | made beside them by `make_production_v2.py`; not kept in the repository |
| The files that go into the board's flash | `build/bitstream/` on the owner's PC, made by [pack_bitstream.py](../../fpga/tools/pack_bitstream.py) |

The board for the quote: 111 x 70.5 mm, 6 layers, 1.2 mm, 194 parts of which the assembler places 187 (50 on the top face, 137 on the bottom), 49 different part numbers.

## What the review found and what was done

| Found | How | Done |
|---|---|---|
| **Ground copper between the N64 edge fingers and across the tip.** The solder mask is open over the whole row, so this copper would have been bare gold 0.2 mm from every finger and 0.3 mm from the bevelled edge. A console contact sitting a little to one side could have joined a finger to ground. SummerCart64's own board has no fill there | looking at where copper comes near the board's edge, for the fabrication notes | A rule area keeps fills out of the finger zone. The ground plane on the inner layer now reaches the via at the top of every ground finger; before, one pair of ground fingers reached ground only through the copper between the fingers ([apply_finger_clearance_v2.py](../../hardware/sn64-v2/tools/apply_finger_clearance_v2.py), picture [fingers-before-after.png](../../hardware/sn64-v2/exports/fingers-before-after.png)) |
| **The power section was laid out like signal wiring.** The 1.1 V converter had no capacitor within 6.9 mm of its input pin. The 5 V converter's output capacitors were 7 to 10 mm away behind one via. The coil currents ran through 0.15 mm tracks. The console's 3.3 V entered the input selector through one via in a pad | following each supply through the copper ([power_paths_v2.py](../../hardware/sn64-v2/tools/power_paths_v2.py)) and measuring each chip's distance to its capacitors | The corner is laid out again, one group for each converter with its capacitors and coil beside it and wide tracks between them, as the makers' layout sections ask ([make_power_plan.py](../../hardware/sn64-v2/tools/make_power_plan.py), [apply_power_layout_v2.py](../../hardware/sn64-v2/tools/apply_power_layout_v2.py), picture [power-corner-before-after.png](../../hardware/sn64-v2/exports/power-corner-before-after.png)) |
| **The small capacitors sat in clumps**, not at the chips they belong to. One level shifter's nearest was 36 mm away, the oscillator's 12 mm | the same measurement | Each capacitor is at the pin it serves: 40 capacitors, 3.5 mm at most with four named exceptions, most of them directly under the pin on the other face ([capacitor-distances.json](../../hardware/sn64-v2/validation/capacitor-distances.json)). The wiring check now measures this |
| **The 5 V converter's enable pin was tied straight to its supply.** TI SLVSC58B, section 11.1: "a 10k resistor must be used in series" | reading the data sheet's layout and application sections, not only its pin table | R321, 10 k |
| **The 5 V converter had no small capacitor at its pins.** The same section asks for one of size 0603 at the input pins and one at the output pins, with the larger ones behind | the same | C324 and C325, 10 µF 0603, 0.4 mm from the pins |
| **Each level shifter had one capacitor for each supply; it has two pins on each** | the same measurement | C213 to C220: one 100 nF for every supply pin |
| **The measuring chip had 100 nF for both supply pins.** TI SBAS961A asks for 1 µF on each, and at least 220 nF when both come from one supply. One of the two is also the chip's reference | reading its layout section | C35 is 1 µF at the analog pin, C46 is 1 µF at the digital pin. The supervisor chip beside it moved 10 mm to make the room |
| The measuring chip's footprint had the wrong exposed pad (0.8 mm, the part has 1.68 mm), with two signal vias under the real pad | each own or unusual footprint against its maker's drawing | Footprint changed, the two lines laid again ([apply_review_fixes_v2.py](../../hardware/sn64-v2/tools/apply_review_fixes_v2.py)) |
| 15.8 µF directly on the USB supply; USB allows a device 10 µF at plug-in | adding up the part values | 8.0 µF. The input selector's soft-start capacitor is 10 nF, about 0.3 A of inrush into the 42 µF behind it (TI SLVSEA3F figure 7-6) |
| The status lamp was a green one, which needs about 3 V; on 3.3 V through 1 k it would stay dark | choosing a part number for it | A yellow-green one with about 2 V across it |
| The small parts had no maker's part numbers | PCBWay's parts list needs one on every line | One on every bought part ([build_v2_schematic.py](../../hardware/sn64-v2/tools/build_v2_schematic.py), `SMALL_PARTS`) |
| 14 leftovers of the first routing, 225 silkscreen warnings, 218 differences between the board's part records and the schematic | KiCad's rule check | All gone ([trim_leftovers_v2.py](../../hardware/sn64-v2/tools/trim_leftovers_v2.py), [tidy_silk_v2.py](../../hardware/sn64-v2/tools/tidy_silk_v2.py), [sync_board_fields_v2.py](../../hardware/sn64-v2/tools/sync_board_fields_v2.py)) |
| No file to load into the FPGA had ever been made | looking for it | [pack_bitstream.py](../../fpga/tools/pack_bitstream.py), called by `route_top.py` when the timing is met |

Confirmed without a change:

| Checked | Result |
|---|---|
| Footprints of the unusual parts against their makers' drawings | 5 V converter (TI 4222000/B), input selector (TI 4224010/A), both coils, the oscillator, the USB-C socket (JAE SJ122205 rev 2), the FPGA's 381 balls against Lattice's table: all agree. The N64 edge's 50 pads are identical to SummerCart64's board in place, size and face |
| Which way round the N64 edge is, from a second source | ModRetro's own drawing of the M64 main board (`M64_MLB_SCH.pdf`, page 31) shows the cartridge connector from above with pins 1 to 25 in the row towards the front and pin 1 at the player's left. Our board agrees |
| USB protection part (U4) | ST USBLC6-2, Doc ID 11265 Rev 5: pins as wired |
| Oscillator (X1) | Interquip sheet SPXO 3225 163-B: pins and land pattern as wired |
| Hole spacing against PCBWay's stated 11 mil | smallest wall-to-wall distance 0.281 mm, at the USB-C socket's own holes |

## The USB-C opening

The receptacle is JAE DX07S016JA3R1500. The opening is now derived from three sources instead of assumed.

| | Value | Source |
|---|---|---|
| Receptacle face | 8.94 x 3.16 mm, round ends, 0.5 mm beyond the board's edge | JAE drawing SJ122205 rev 2 |
| Largest plug overmold | 12.35 x 6.5 mm | USB-IF Type-C compliance document rev 1.2, figure B-1 |
| Mated overmold stops | 1.95 mm in front of the receptacle's face | the same two drawings |
| Recess in the shell | 14.54 x 8.0 mm, 2.0 mm corners, 1.0 mm deep | SummerCart64's own port for the same receptacle |
| Opening through the rim | 9.94 x 4.16 mm, round ends | the receptacle's face plus 0.5 mm all round |
| Result | the largest plug the standard allows goes in with 0.75 mm to spare, also 0.3 mm off centre both ways | fit check in CAD; picture [usb-port-fit.png](../../mechanical/sn64-v2-shell/usb-port-fit.png) |

The old 13 x 7 recess would not have taken the largest overmold at its corners.

## What only hardware or PCBWay can settle

### 1. How long the console waits for the cartridge

An empty FPGA cannot answer the console's first question to the cartridge (the CIC exchange). A console that gets no answer stops until it is switched off and on. No published figure was found for how soon after power-on the console asks.

| The FPGA's image, 1,313,752 bytes | Time to load |
|---|---|
| As the tools made it by default (one data line, 2.4 MHz) | 4.4 s |
| As packed now (four data lines, 38.8 MHz, compressed) | 68 ms, 78 ms if the FPGA's clock runs 15 % slow |
| The FPGA's own start before that | 33 ms at most |

So the board is ready about a tenth of a second after its supplies are up. **To measure on an N64 and on an M64:** the time from power-on to the first clock on the CIC line. If a console asks sooner than that, the remedy is a small separate CIC chip. That would be an added part and so the owner's decision.

### 2. Power from the console

**Estimates. Nothing is measured.** The FPGA's share comes from Lattice's standby table plus a guess for the switching part. The cartridge currents are assumptions.

| Case | Cartridge takes at 5 V | From the console's 3.3 V |
|---|---|---|
| Menu, cartridge off | nothing | 0.22 to 0.28 A |
| Plain cartridge | 60 mA | 0.34 to 0.40 A |
| Cartridge with an extra chip | 150 mA | 0.49 to 0.55 A |
| Flash cartridge | 400 mA | 0.92 to 0.97 A |

- **M64.** Its cartridge supply runs through a switch with a 41.2 k limit resistor (ModRetro's drawing, page 28, noted there as 500 mA). By the switch maker's formula it limits between 0.57 and 0.70 A. Plain cartridges are inside that. A flash cartridge is not: on the M64 it needs the USB cable from the console's accessory port, which the board prefers whenever it is plugged in.
- **Starting on the M64.** The 5 V converter may draw up to about 1 A for a fraction of a millisecond while it starts (TI SLVSC58B, 8.4.4). That is more than the M64's switch gives, so the supply will dip for a moment. It should recover, because the converter keeps what it has charged. This has to be watched on the first board.
- **Original N64.** No figure for what a cartridge may take was found. Its supply is not limited by a switch.
- **Copper.** The supply paths on the board, after the re-layout: [power-paths.json](../../hardware/sn64-v2/validation/power-paths.json). The console's 3.3 V has 70 mΩ from the fingers to the input selector, 35 mV at 0.5 A.

### 3. Three questions for PCBWay

They are on the quote sheet and in the fabrication notes.

| Question | Numbers |
|---|---|
| Vias in pads, to be filled with resin and plated over | 85, of them 8 under the FPGA. If the price is high, they can be moved instead |
| Annular ring of 0.125 mm where their page states 0.15 mm | 802 vias of 0.45 mm on a 0.2 mm hole. If refused: 0.15 mm holes, no copper change |
| An unplated oval hole of 0.85 x 0.6 mm at the USB-C socket where their page states 0.8 mm as the narrowest slot | one. It can be two overlapping drill hits |

### 4. The cartridge socket

Its footprint has still not met a real socket. The price does not depend on it. An order does.

## Checks on the board as it is now

| Check | Result |
|---|---|
| KiCad's rule check with the schematic comparison | no error, no open connection, no difference. 199 notes, all about the mask being open across the edge fingers, which is on purpose |
| Signal nets complete | 218 of 218 |
| Wiring check | 24 of 24. Two are new: the 5 V converter's and the measuring chip's rules, and every capacitor at its pin |
| Deliberate mistakes | 29 of 29 caught. Four are new |
| Board run of a test program through the new board | ends with DONE (`board-hello6`) |
| Every part of the board against both shell halves | 307 solids, none touches |
| Logic | unchanged. The simulation suite, the game runs and the timing stand as they were |

## How the board was changed

In place, by scripts, on copies first. The chain for the power section and the capacitors:

1. `make_power_plan.py` writes where each part goes and which supply tracks are drawn by hand.
2. `apply_power_layout_v2.py parts` adds the 12 new parts. `clear` takes up the copper of the power corner. `place` and `decouple` put the parts down. `fit` removes only what is in the way elsewhere. `copper` draws the supply tracks.
3. `add_plane_vias_v2.py`, then the router joins the remaining 32 nets (ordering `inside_out`; the other two orderings each left one net open).
4. `trim_leftovers_v2.py` in its guarded loop, `tidy_silk_v2.py`, `sync_board_fields_v2.py`, the rule check, the wiring check, `make_production_v2.py`.

The placement generator `build_v2_pcb.py` still describes the two-board arrangement of 2026-09-30 and no longer makes this board. The board file is the source now.

## What this review did not do

It did not simulate the supplies or the signals as voltages. The converters follow their makers' layout rules now; whether they are quiet enough is seen on a board. The game simulation checks wiring and logic.

## Sources

- [USB Type-C compliance document rev 1.2](https://www.usb.org/sites/default/files/USB_Type-C_Compliance_Document_rev_1_2.pdf)
- [PCBWay capabilities](https://www.pcbway.com/capabilities.html), read 2026-10-02
- [SummerCart64 build guide](https://raw.githubusercontent.com/Polprzewodnikowy/SummerCart64/a1e7996d2cbece686820a5c785029c68514f17b0/docs/06_build_guide.md)
- [N64brew: PIF-NUS](https://n64brew.dev/wiki/PIF-NUS) and [CIC-NUS](https://n64brew.dev/wiki/CIC-NUS)
- [TI TPS63070, SLVSC58B](https://www.ti.com/lit/ds/symlink/tps63070.pdf), [TLV62569, SLVSDG1C](https://www.ti.com/lit/ds/symlink/tlv62569.pdf), [TPS2121, SLVSEA3F](https://www.ti.com/lit/ds/symlink/tps2121.pdf), [TLA2528, SBAS961A](https://www.ti.com/lit/ds/symlink/tla2528.pdf), [TPS2553, SLVS841F](https://www.ti.com/lit/ds/symlink/tps2553.pdf)
- [TI SLYT118, USB inrush](https://www.ti.com/lit/an/slyt118/slyt118.pdf)
- [Interquip oscillator sheet](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2211111700_Interquip-1631-27005-BTBEYA_C3003262.pdf)
- [ST USBLC6-2 sheet, supplier's copy](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2410121836_STMicroelectronics-USBLC6-2SC6_C7519.pdf)
- JAE drawing SJ122205 rev 2 and ModRetro's M64 drawings: kept with the owner's references, not in the repository
