# Independent interface review

Result: **PASS** — 30 checks passed; 0 failed.

The validator independently exports the current schematic with KiCad and checks all 112 pin-to-net assignments against both CSV maps. It compares the N64 footprint with J_N1 loaded directly from the original SummerCart64 PCB, including copper sides, pad geometry, mask polygons and connector edge profile. The SNES footprint must be byte-identical to the original Sanni footprint.

Only GND may join the two connectors. HOST_3V3, HOST_12V and SNES_5V_CART must remain separate. Both reusable symbols must match the schematic copies and preserve all pin numbers and names.

Limits:

- Reference agreement is not a validated SNES socket purchase/fit; no final socket manufacturer part number is selected.
- The N64 footprint includes six source Edge.Cuts segments forming an open connector profile; complete the board perimeter without duplicating them.
- All connector pins are deliberately passive; ERC cannot establish endpoint direction, power safety, translation or drive-enable correctness.
- Only the connector scaffold is checked: no FPGA assignment, power circuitry, timing behavior, complete PCB, host fit or manufacturing release is validated.

Reproduce with KiCad 10 Python: `python hardware/sn64/tools/verify_interfaces.py --source-root <original-project-with-reference-downloads>`.

See [machine-readable checks](interface-check.json) for input SHA-256 hashes and per-check evidence. The stored netlist is compared to a fresh export; the PDF was not visually reviewed by this validator.
