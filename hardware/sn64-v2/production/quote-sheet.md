# SN64 v2: what to enter for a PCBWay quote

Written by `hardware/sn64-v2/tools/make_production_v2.py` on 2026-10-02 from the board file. Every number below is read from the board.
**Nothing has been sent to PCBWay.** The files are for a price. Before an order the list at the end still applies.

## 1. The bare board (PCBWay's "PCB Instant Quote")

| Field | Enter | Where the value comes from |
|---|---|---|
| Board type | Single pieces | |
| Size | 111 x 70.5 mm | board outline |
| Quantity | 5 | their smallest lot |
| Layers | 6 | |
| Material | FR-4, TG 150 or higher | lead-free soldering on both faces |
| Thickness | 1.2 mm | the console's slot. SummerCart64 uses the same |
| Min track / spacing | 4/4 mil | the board's smallest track is 0.10 mm and its smallest gap 0.1 mm |
| Min hole size | 0.2 mm | 1118 vias: 802 x 0.45 mm pad on 0.20 mm hole, 310 x 0.50 mm pad on 0.20 mm hole, 6 x 0.60 mm pad on 0.30 mm hole |
| Solder mask | any colour | green is the cheapest and quickest |
| Silkscreen | white | |
| Edge connector | Yes | the 50 gold fingers |
| Bevelling | 45 degrees | SummerCart64's build guide |
| Surface finish | Immersion gold (ENIG) | the fingers and the 381-ball chip. SummerCart64 orders ENIG. Hard gold on the fingers lasts longer and costs much more |
| Via process | Tenting vias | set on the board |
| Finished copper | 1 oz outer, 0.5 oz inner | 0.1 mm tracks need the thin inner copper |
| Stack-up | their standard one, no impedance control | |

## 2. Four things to put in the remarks box

PCBWay's form has no field for these. Their engineer answers them with the quote.

1. **Via in pad.** 85 of the small holes sit in solder pads, 8 of them under the 381-ball chip. Left open they draw the solder away from the joint. Ask for them to be **filled with resin and plated over**, and for the price with and without. If the difference is large, the 85 holes can be moved instead. That is a routing job of about a day, not a new design.
2. **Annular ring.** 802 vias have a 0.45 mm pad on a 0.2 mm hole, which leaves a copper ring of 0.125 mm. PCBWay's page states 0.15 mm. Ask whether 0.125 mm is accepted as drawn. If not, those holes may be drilled 0.15 mm, which changes no copper.
3. **One small oval hole.** The USB-C socket's maker asks for an unplated oval hole of 0.85 x 0.6 mm. PCBWay's page states 0.8 mm as the narrowest unplated slot. It may be made as two overlapping 0.6 mm drill hits.
4. **Rails and marks for assembly.** The board has no fiducial marks of its own. Ask them to add tooling rails with fiducials.

The same four points are in `fabrication/fabrication-notes.txt` inside the zip, so the engineer sees them with the files.

## 3. Assembly (PCBWay's "Assembly" quote)

| Field | Enter |
|---|---|
| Service | Turnkey: they buy the parts |
| Assembly sides | Both |
| Unique parts | 49 |
| SMD parts | 187 (50 on the top face, 137 on the bottom face) |
| BGA / QFP parts | 1 BGA with 381 balls at 0.8 mm. Also 3 leadless chips and 6 parts with 0.5 mm lead pitch |
| Through-hole parts | 0. The USB-C socket is surface-mount with four legs in plated slots |
| Files | `assembly/sn64-v2-bom.csv` and `assembly/sn64-v2-positions.csv` |

Not fitted by PCBWay: the **SNES cartridge socket** (J2). It is soldered by hand after delivery. Say so in the remarks, so that they do not ask for the part.

## 4. What makes this board cost more than a simple one

Six layers. Gold fingers with a bevel. ENIG. Parts on both faces. A 381-ball chip, which is X-rayed after soldering. Filled vias, if point 1 stays. The FPGA is the dearest part.

## 5. Before an order, not before a quote

- The SNES socket's footprint waits for a measured sample of the socket. The price does not depend on it.
- The open points in [board-verification.md](../../../docs/design/board-verification.md) under "Still open".

Sources for PCBWay's limits and SummerCart64's order settings are listed in [board-verification.md](../../../docs/design/board-verification.md).
