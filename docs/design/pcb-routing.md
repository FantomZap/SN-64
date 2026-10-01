# Main board routing

Started 2026-09-29. This note records how the placed main board ([hardware/sn64/sn64.kicad_pcb](../../hardware/sn64/sn64.kicad_pcb)) is being routed, what each tool does and what the result is worth. **Nothing here is a reviewed layout**: the placement is the block-zone draft from [build_main_pcb.py](../../hardware/sn64/tools/build_main_pcb.py), the fan-out and planes are generated, and the traces come from an autorouter. It is the first complete copper picture, meant to expose problems (congestion, plane splits, power paths) before a human-quality pass.

## Plain-language summary

The FPGA is a 381-ball grid at 0.8 mm pitch. Its inner balls cannot be reached by traces on the top layer, so every used inner ball gets a short stub to a small plated hole (a "dog-bone via") that carries the signal to the inner layers. Two of the six copper layers are solid sheets: a ground sheet and a 3.3 V sheet with a 1.1 V island under the FPGA core. Every ground and power ball reaches its sheet through its own via, so those 157 connections need no traces. The remaining 122 signal balls, the 80-pin joint header, the N64 edge, the USB and power parts are then routed by Freerouting, a free autorouter that runs on this PC, using the track widths and clearances set for the board.

## Stack-up and rules

| Layer | Use |
|---|---|
| F.Cu | components, BGA ring-0 escapes, signals |
| In1.Cu | GND plane, whole board |
| In2.Cu | signals |
| In3.Cu | FPGA_3V3 plane, whole board; FPGA_1V1 island under the FPGA core (±2.8 mm × 5.6 mm) at higher priority |
| In4.Cu | signals |
| B.Cu | small passives, FPGA decoupling, signals |

Rules from `build_main_pcb.py` (PCBWay 6-layer capable): 0.1 mm clearance, 0.15 mm default track, 0.45/0.2 mm via, 0.25 mm hole clearance, 0.3 mm copper-to-edge, 1.2 mm thick. Netclasses added by `prepare_route.py` in `sn64.kicad_pro`:

| Class | Nets | Track | Via | Clearance |
|---|---|---|---|---|
| Default | everything else | 0.15 mm | 0.45 / 0.2 mm | 0.1 mm |
| power | GND, FPGA_1V1/2V5/3V3, FPGA_VCCAUX, 5V_PRE, INTERFACE_3V3, HOST_3V3, SNES_5V_CART, USB_VBUS, USB_3V3, HOST_12V, ADC_VCC_5V, the regulator switch nodes | 0.4 mm | 0.6 / 0.3 mm | 0.15 mm |
| usb | USB_DP, USB_DM | 0.2 mm | 0.45 / 0.2 mm | 0.1 mm |

Impedance is not controlled in this draft; the USB pair width is a placeholder until PCBWay's stack-up is chosen.

## BGA fan-out (generated)

`hardware/sn64/tools/prepare_route.py`, on U401 (Lattice caBGA-381, 20 × 20 at 0.8 mm):

- Every used ball in rings 1-9 (counted from the outside) gets a through via 0.4 mm diagonally outward from the ball, toward its quadrant's corner, plus a 0.15 mm F.Cu stub. In one quadrant all stubs point the same way, so every via sits in its own square between four balls and no two collide.
- Geometry check against the rules: ball pad 0.4 mm, via 0.45 mm at 0.566 mm centre distance: copper gap 0.14 mm (min 0.10), hole edge to ball 0.27 mm (min 0.25). Adjacent vias leave a 0.35 mm channel, exactly one 0.15 mm track with 0.1 mm clearance each side.
- Ring 0 (the outer ring) gets no via: those balls escape straight out on F.Cu.
- Result: **240 vias**. Of the 279 used balls, 115 are GND, 20 FPGA_1V1, 18 FPGA_3V3, 4 VCCAUX and 122 signals; all signals sit in rings 0-4, so the escape depth is shallow.

## Planes

- GND on In1.Cu over the whole board, thermal reliefs on pads (0.3 mm spokes, 0.2 mm gap), vias solid.
- FPGA_3V3 on In3.Cu over the whole board; FPGA_1V1 island on In3.Cu around the 20 core balls (ring 7) only, so the ring-5/6 VCCIO balls' vias land on the 3.3 V copper around it. The 1.1 V decoupling under the FPGA reaches the island through short B.Cu tracks and vias placed by the router.
- GND pours on F.Cu and B.Cu are added after routing (`finish_route.py`).

## Tool flow

```powershell
& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware/sn64/tools/prepare_route.py   # netclasses, fan-out, planes, DSN export
# Freerouting 2.4.1 (local jar, %USERPROFILE%\Tools\freerouting), through its local API / MCP:
#   create_session -> enqueue_job -> upload build/route-pcb/sn64.dsn -> settings -> start_job -> download .ses
& 'C:\Program Files\KiCad\10.0\bin\python.exe' hardware/sn64/tools/finish_route.py    # import .ses, outer GND pours, refill, save
& 'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe' pcb drc --format json --output hardware/sn64/validation/pcb-drc.json --severity-error --exit-code-violations hardware/sn64/sn64.kicad_pcb
```

Notes on the tools, found on the way:

- KiCad 10.0.6's Python: after `board.Remove()` every further lookup (even a fresh `LoadBoard` in the same process) returns bare SWIG pointers, so `prepare_route.py` clears an earlier fan-out, saves and asks to be run again.
- Freerouting's GUI mode (`java -jar ... -de -do`) died with a NullPointerException in its shape search tree on this board; the headless API server (what the MCP starts) is used instead.
- The DSN export carries the zones as `plane` items, so Freerouting treats every GND/3.3 V/1.1 V via as connected and does not route those nets as traces.
- Freerouting does not read KiCad's hole-to-copper rule (0.25 mm here) from the DSN; it must be given as a job setting (`holeClearanceUm: 250`), together with the edge clearance (`copperToEdgeClearanceUm: 300`). A run without it routes tracks 0.1 mm from via copper, 0.225 mm from the hole, and KiCad then reports every one of them.
- On import, KiCad gives the plane-net vias the power class drill (0.3 mm) while the BGA dog-bones keep their 0.45 mm diameter; `finish_route.py` pins each via's drill to its diameter afterwards.
- Freerouting's routing pass is single-threaded, and one API server instance time-slices its jobs: three jobs in one instance ran on less than one core in total. Separate instances (one JVM each, `hardware/sn64/tools/fr_instance.ps1`, driven through the REST API with the identity headers the MCP uses) run in parallel.
- The first fan-out attempt put the through vias straight onto the FPGA decoupling capacitors on the back (58 shorts): the decoupling now sits in two bands outside the via field.

## Second router: KiCadRoutingTools (2026-09-30)

[drandyhaas/KiCadRoutingTools](https://github.com/drandyhaas/KiCadRoutingTools) (MIT, Rust A* core with a Python driver, reads and writes `.kicad_pcb` directly) is installed per user under `%USERPROFILE%\Tools\KiCadRoutingTools` (prebuilt core v0.22.1 fetched by its `build_router.py`) with a Python 3.14 environment in `%USERPROFILE%\Tools\krt-venv`. It attempts all 375 signal nets in about five minutes and spends the rest of a 30-60 minute run ripping up and retrying the hard ones, where Freerouting needed half an hour for its first pass alone. Both are single-threaded per net.

Command used (run 3, on the prepared board with plane vias; the project file must sit beside the board copy so the net classes are seen):

```powershell
%USERPROFILE%\Tools\krt-venv\Scripts\python.exe %USERPROFILE%\Tools\KiCadRoutingTools\py_router\route.py build/route-pcb/krt-in3.kicad_pcb build/route-pcb/krt-out3.kicad_pcb `
  --nets '*' '!/GND' '!/FPGA_3V3' '!/FPGA_1V1' --keep-input-copper --layers F.Cu In2.Cu B.Cu `
  --clearance 0.125 --track-width 0.15 --via-size 0.5 --via-drill 0.2 `
  --fab-overrides hardware/sn64/tools/fab-pcbway.txt --escalation fab --hole-to-hole-clearance 0.25 --board-edge-clearance 0.3 --no-bga-zones `
  --power-nets '/FPGA_2V5' '/5V_PRE' '/INTERFACE_3V3' '/HOST_3V3' '/SNES_5V_CART' '/USB_VBUS' '/USB_3V3' '/FPGA/FPGA_VCCAUX' '/HOST_12V' --power-nets-widths 0.4 0.4 0.4 0.4 0.4 0.4 0.4 0.4 0.4 `
  --ordering mps --json-out build/route-pcb/krt-out3.json
```

What its options mean here: the three plane nets are excluded (it skips zone-owning nets anyway); `--keep-input-copper` keeps the fan-out and plane vias; In4 is left out because it carries the 1.1 V island; 0.125 mm clearance keeps router tracks 0.25 mm from the 0.45 mm fan-out via holes and 0.5 mm router vias keep their own holes 0.25 mm from neighbours; `--fab-overrides` + `--escalation fab` pin it to the board's floors ([fab-pcbway.txt](../../hardware/sn64/tools/fab-pcbway.txt)), because by default it "escalates" to JLCPCB's advanced tier (0.25 mm vias, 0.0889 mm tracks) whenever a net will not fit, which run 1 did 4,280 times.

| Run | Settings | Signal nets connected | Multi-pin pads | Time | KiCad DRC on the output |
|---|---|---:|---:|---:|---|
| 1 | defaults (auto fab tier), 0.1 mm clearance, 0.45/0.2 vias, BGA exclusion zones on | 313 / 375 | 520 / 554 | 34 min | 199+ each of annular ring, hole clearance, drill size, track width, via diameter (narrowed features) |
| 2 | fab floors pinned, 0.125 mm clearance, 0.5/0.2 router vias, no BGA zones | 29 signal nets open, 3 power nets partly open | 510 / 558 | 62 min | only 94 hole-clearance items at 0.225-0.248 mm (the rule was 0.25; PCBWay's is 0.2) and the known edge items |
| 3 | as 2, on the board with 324 plane vias and the N64-finger keep-out placed first | 253 / 375 (about 110 signal nets open) | 477 / 538 | 57 min | 2 shorts, plus the known edge items |

Plane-net pads: `add_plane_vias.py` after run 2 found free spots for only 100 of 454 pads because the routed bottom layer was already full. Placing the vias **before** routing (run 3: 324 placed, 118 without a spot) cost far more than it gained: the stubs and vias beside every pad took the room the router needed and it connected 90 fewer signal nets. Conclusion for this board: route signals first, then connect the plane pads; the remaining plane pads get their vias from Freerouting (which places plane vias well) or by hand.

PCBWay capability check (capabilities page, 2026-09-30, standard 6-layer): hole to copper >= 8 mil (0.203 mm; the board rule is now 0.2), copper to edge 0.25 mm (board 0.3), via drill >= 0.15 mm, annular ring >= 6 mil (0.15 mm; **the board's 0.45/0.2 vias have 0.125**), trace/space >= 4/5 mil outer (**the board's 0.1 mm spacing is 4 mil**). The last two need either PCBWay's advanced process or wider rules; to be settled with the quote, before the final layout pass.

## State of the tracked board (2026-09-30, morning)

[hardware/sn64/sn64.kicad_pcb](../../hardware/sn64/sn64.kicad_pcb) is run 2's routing plus 157 plane vias from `add_plane_vias.py` (now layer-aware for the stubs) and GND pours on the outer layers. KiCad DRC ([validation/pcb-drc.json](../../hardware/sn64/validation/pcb-drc.json)): **no shorts, crossings, clearance or hole violations**; the reports are the 18 by-design USB-C edge pads plus one GND item at the edge, 79 starved thermal reliefs on the outer pours (cosmetic) and the N64 fingers' shared mask opening. Open connections ([validation/pcb-open-connections.json](../../hardware/sn64/validation/pcb-open-connections.json)):

| Open | Count | Where |
|---|---:|---|
| Signal and power nets not fully connected | 75 nets, 95 connections | mostly SNES_* and cart_* lines in the translator row, the CIC translators, a few N64 AD lines, SNES_5V_CART and INTERFACE_3V3 branches |
| Plane pads without a via | GND 132, FPGA_3V3 64, FPGA_1V1 23 | the 0.65 mm-pitch translator/regulator pins and decoupling in the dense regions |

Roughly 80 % of the signal connections and 55 % of the plane connections are routed with rule-clean geometry. The rest is hand work in KiCad, or another router pass after loosening the placement (the translator row is the congested area).

Two more things tried on the way, both rejected by their own tools: Freerouting given run 2's board as its starting point (to place the plane vias and finish the 75 nets) ripped up good KiCadRoutingTools traces while working and, 60 min in, had more signal nets open than it started with; KiCadRoutingTools' own plane step (`route_planes.py` + a route pass on the three plane nets, its "pour-launch" welds) ran 20 min and then reverted its output as worse than the input.

## Freerouting results

**Run 2 (FPGA at 0°, abandoned after 70 min at pass 3):** 327 of the routable nets connected; the leftovers were almost all the N64 bus between the FPGA and the bus switches (`fpga_n64_ad0..15`, `read_n`, `write_n`, `aleh`, `reset_n`, `nmi_n`, `cic_clk`, `int_n`, `si_dq`). Cause: with the package at 0° its bank 0 (the N64 bus) faces the top of the board while the bus switches sit at the bottom by the edge fingers, so those 27 signals had to cross the whole ball grid. The FPGA is now placed at 180° (bank 0 toward the switches, banks 2/3 toward the translator row) and the board rebuilt.

**Runs 3 (FPGA at 180°, hole clearance set, one job per instance, 2 h 20 min):** the main job reached 335 nets with wires at pass 8 and the low-via-cost variant 333 at pass 5 before both were stopped; imported and checked, the main snapshot left about 80 signal nets and 64 plane pads open with no rule violations beyond the known edge items. KiCadRoutingTools reached a better state in a third of the time, so Freerouting is the fallback from here.

## Adding routes to a routed board without disturbing it (v2 tower refit, 2026-09-30)

KiCadRoutingTools rips pre-existing nets that block a new route and does not always restore them:
on the v2 refit a first run broke 7 good nets, and a run with `KICAD_RIP_PREEXISTING=0` still broke
5 because the end-of-run reconciliation grants itself rip authority over "hinted blockers". What
works: **lock every existing track and via** (`PCB_TRACK.SetLocked(True)`, see
`hardware/sn64-v2/tools/refit_tower_v2.py place`), route, then unlock; the router never rips locked
copper. Also keep BGA escape copper in place when re-routing nets that start at the FPGA, and never
adopt the `.kicad_pro` the router writes beside its output (it lowers the copper-to-hole floor to
what it used); run DRC against the board's own project file.

The second v2 refit (shorter shell, 2026-10-01) used the same recipe on 64 nets, with the socket nets squeezed into 8 mm between the translator row and the socket pads. With the default `--ordering mps` the router finished 63 and left the corner pad's net (the cartridge master clock) boxed in by its six neighbours. `--ordering bus` routed all 64 on the same three layers (157 new vias); `--ordering inside_out` also routed all 64 (173 vias), and so did `mps` with In4.Cu added as a fourth layer (102 vias). The `bus` result is the one on the board. Each run takes under a minute, so trying the orderings costs nothing. Scratch DRC runs need the board's `.kicad_dru` copied beside the board as well as its `.kicad_pro`; without it the USB-C receptacle's edge rule is missing and a false edge-clearance error appears.
