# SN 64 cartridge shell — concept Rev A

This folder is a new, isolated mechanical concept and does not modify the existing SN 64 planning documents. It is a **parametric starting point**, not a manufacturing-ready or fit-validated enclosure.

## What is included

- `sn64_shell.scad` — editable OpenSCAD model for an upper/lower shell concept.
- `sn64_shell_dimensions.csv` — the controlling dimensions and their status.
- `fit-validation.md` — measurements and tests required before freezing the shell.

## Mechanical intent

The shell is arranged around the architecture in the repository specification:

- **Top:** a protected, female SNES/Super Famicom cartridge interface with a guided cartridge throat.
- **Bottom:** a PCB tongue and clearance envelope for the male N64 cartridge edge; the shell itself does not pretend to reproduce the N64 electrical contacts.
- **Side:** a USB-C service/update opening with a recessed panel and connector keep-out.
- **Inside:** a central PCB cavity, four PCB mounting bosses, a protected cartridge-power/translator region near the top connector, and room for FPGA/regulators near the center.

The model deliberately leaves connector bodies, latches, eject geometry, PCB thickness, and host-specific N64/M64 bay dimensions as replaceable keep-outs. Those dimensions must come from native component drawings and physical fit checks before a STEP/STL release.

## Use

Open `sn64_shell.scad` in OpenSCAD. Set `view_mode` to:

- `0` assembled shell concept;
- `1` exploded upper/lower shell;
- `2` shell cutaway with PCB and connector keep-outs.

The model is in millimetres. Export only after selecting actual connector and PCB dimensions in the parameter block. The current values are intentionally tagged `CONCEPT` in the CSV and are not claims of compatibility.

## Important electrical/mechanical boundary

The bottom interface is shown as a **N64 PCB-edge keep-out**, not as a loose male connector. The final board edge/contact geometry, plating, bevel, insertion depth, card thickness, retention features, and M64 eject clearance must be derived from a verified N64 cartridge reference and checked on both an original N64 and M64. Likewise, the top connector must be a real high-cycle female SNES connector with its own approved footprint and insertion-force data.

The side USB-C opening is a service/update access provision. It does not select a USB protocol, power role, ESD network, or charging behavior; those remain PCB design decisions.

## Recommended next step

Import the final populated PCB STEP model into the same mechanical master, replace the three connector keep-outs with vendor models, then print only the interface/fit samples first. Do not release a complete enclosure until cartridge seating, connector insertion force, host bay clearance, USB-C cable clearance, thermal margin, and screw boss strength are recorded.
