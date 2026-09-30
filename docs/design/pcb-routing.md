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
# Freerouting 2.4.1 (local jar, C:\Users\RyanB\Tools\freerouting), through its local API / MCP:
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

## Results

_(filled in as runs complete)_
