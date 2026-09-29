# Independent USB programmer review

**PASS**: 64 checks passed; 0 failed.

Checked a fresh KiCad export against hand-authored manufacturer pin assignments, not the generated CSV or builder script. The checker covers separate CC resistors; DP/DM and ESD pairs; FT232HL supplies, crystal and EEPROM; AXC pin directions and default-disabled /OE; target-side service header; library pad sets; and host/USB rail separation.

Limits:

- This checks schematic connectivity against fixed pin tables; it does not prove physical routing, signal integrity, protection performance or USB compliance.
- Crystal startup, effective load capacitance and frequency accuracy require layout and prototype measurements. The 11 pF values are explicitly provisional.
- The USB supply powers the bridge only. The actual FPGA/flash power, pin allocation and persistent-loading algorithm remain unimplemented.
- A fitted EEPROM must preserve the safe ACBUS6 startup contract. Host loading must use the documented --status-pin 14 option.
- Target-off leakage, USB/target power sequencing, abnormal process termination/reset, inrush, thermal margin, suspend current and cold-boot persistence require bench tests.
- ESD array pin connectivity is checked; this is not a short-to-VBUS/USB-PD protection claim. USB and target supplies have no direct schematic connection to host power.

Reproduce using KiCad 10 Python: `python hardware/sn64/tools/verify_usb_programmer.py`.

See [usb-check.json](usb-check.json) for input hashes, manufacturer source links and detailed results. No hardware measurements were performed.
