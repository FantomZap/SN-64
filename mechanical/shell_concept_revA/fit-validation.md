# Shell fit-validation plan

Status: **not validated**. This is the evidence checklist for converting the concept into a release candidate.

## Reference measurements to capture

- Original N64 cartridge envelope, edge-card thickness/bevel, contact span, insertion depth, retention and eject path.
- ModRetro M64 cartridge bay envelope and eject motion, independently of the original N64 measurement.
- Selected female SNES/Super Famicom connector: body, contact centerline, insertion force, latch/key geometry, and board footprint.
- Maximum envelope of original SNES/SFC cartridges, Super EverDrive X5/X6, and FXPAK Pro, including shell overhangs and labels.
- Selected USB-C receptacle: panel cutout, shell standoff, plug clearance, and cable bend radius.
- Populated PCB outline, mounting-hole coordinates, PCB thickness, tallest parts, service/JTAG access, and heat sources.

## Prototype sequence

1. Print the top connector throat and bottom N64 tongue as separate gauges.
2. Check a real female SNES connector and cartridge pair; verify full insertion without contact scraping or shell interference.
3. Check the N64 tongue in an original console and M64 bay with no electronics installed. Confirm full seating and eject travel; do not force a prototype into a console.
4. Print the complete shell in a low-cost material, install a dummy PCB at the recorded datum, and check the USB-C cable, screw access, ventilation, and cartridge side loading.
5. Fit the populated PCB and dummy connector bodies. Check that the shell supplies structural support to the top connector and that a tall cartridge cannot lever against the lower host connector.
6. Repeat insertion/removal and side-load checks, then record temperatures in the closed shell under the worst-case FPGA/cartridge load.

## Release gates

- [ ] All `CONCEPT` dimensions replaced by measured or vendor-controlled values.
- [ ] Native PCB STEP and approved connector models imported with a common origin.
- [ ] Original N64 and M64 fit and eject motion recorded separately.
- [ ] SNES/SFC, EverDrive X5/X6, and FXPAK Pro physical fit recorded separately.
- [ ] USB-C receptacle, cable, and ESD/service access reviewed with the electrical design.
- [ ] Boss pull-out strength and repeated insertion loads checked.
- [ ] Thermal and ventilation test completed in the assembled shell.
- [ ] STEP/STL exports generated from the reviewed model with revision and units in filenames.

The OpenSCAD model is useful for layout and discussion only. CAD agreement does not establish electrical compatibility or cartridge safety.
