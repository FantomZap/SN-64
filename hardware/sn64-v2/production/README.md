# SN64 v1 board (files named sn64-v2): manufacturing files

Made by `hardware/sn64-v2/tools/make_production_v2.py` on 2026-10-04. **For a quotation. Not released for manufacture, and nothing has been sent to a maker.**

- The SNES socket's footprint (J2) waits for a measured sample of the socket.
- No board has been built. What has and has not been checked is in [board-verification.md](../../../docs/design/board-verification.md).
- What to enter in PCBWay's forms: [quote-sheet.md](quote-sheet.md).

| | |
|---|---|
| Board | 111 x 70.5 mm, 6 copper layers, 1.2 mm, 4034 tracks, 1118 vias, 7914 mm of track |
| Parts | 187 placed by the assembler (50 top, 137 bottom), 49 different part numbers, 1123 surface-mount pads |
| KiCad's rule check | no error, no open connection, no difference from the schematic. 199 notes, all about the solder mask being open across the row of edge fingers, which is on purpose |
| Board file SHA-256 | `f3772975f0fafee3ca76cd3fb921d42bc9b4c6c78519a39c791a751b6c180cca` |
| Netlist SHA-256 | `6276e53528ba6e029613c16fdd0a94bbb332e3b5ce6e2f32d474de5d7584c80c` |

The top face in these files (F.Cu) is the back of the cartridge. The bottom face (B.Cu) is the label side, which faces the player.

## fabrication/

| File | What it is |
|---|---|
| `fabrication-notes.txt` | the notes for the board maker |
| `sn64-v2-B_Cu.gbl` | bottom copper (B.Cu), the label side of the cartridge |
| `sn64-v2-B_Mask.gbs` | solder mask, bottom |
| `sn64-v2-B_Paste.gbp` | solder paste, bottom |
| `sn64-v2-B_Silkscreen.gbo` | silkscreen, bottom |
| `sn64-v2-Edge_Cuts.gm1` | board outline |
| `sn64-v2-F_Cu.gtl` | top copper (F.Cu), the back face of the cartridge |
| `sn64-v2-F_Mask.gts` | solder mask, top |
| `sn64-v2-F_Paste.gtp` | solder paste, top |
| `sn64-v2-F_Silkscreen.gto` | silkscreen, top |
| `sn64-v2-In1_Cu.g1` | inner layer 1, ground plane |
| `sn64-v2-In2_Cu.g2` | inner layer 2, signals |
| `sn64-v2-In3_Cu.g3` | inner layer 3, 3.3 V plane |
| `sn64-v2-In4_Cu.g4` | inner layer 4, signals and the 1.1 V area |
| `sn64-v2-job.gbrjob` | job file that lists the Gerber files |
| `sn64-v2-NPTH-drl_map.pdf` | drawing of the unplated holes |
| `sn64-v2-NPTH.drl` | holes that are not plated |
| `sn64-v2-PTH-drl_map.pdf` | drawing of the plated holes |
| `sn64-v2-PTH.drl` | plated holes and vias |
| `sn64-v2.d356` | netlist for the electrical test of the bare board (IPC-D-356) |

## assembly/

| File | What it is |
|---|---|
| `sn64-v2-assembly-bottom.pdf` | drawing of the parts on the bottom face, mirrored as seen from that side |
| `sn64-v2-assembly-top.pdf` | drawing of the parts on the top face |
| `sn64-v2-bom.csv` | parts list: one line for each maker's part number |
| `sn64-v2-positions.csv` | where each part goes: centre, angle and face |
| `sn64-v2-schematic.pdf` | the schematic |

The two zip files beside this text hold the same two folders for uploading. They are made by the tool and are not kept in the repository.

To make everything again after a change to the board:

```
python hardware/sn64-v2/tools/make_production_v2.py
```

with KiCad's Python. The tool refuses a board whose rule check is not clean.
