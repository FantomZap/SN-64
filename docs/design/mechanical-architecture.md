# Mechanical architecture: board arrangement, insertion depths and region-free opening

Status 2026-09-29: **proposal, before PCB layout.** Nothing here has been fit-tested. Dimensions carry their sources; anything without a source is listed as missing, not estimated.

## Requirements this has to meet (SN_64_Engineering_Specification_Rev_A.docx)

- "Universal top opening suitable for SNES and Super Famicom cartridge shells": no region tabs; the opening accepts the North American shell and the PAL/Super Famicom shell. (The electronic lockout, the CIC, is already handled by `sn64_snes_cic_lock`, which answers either region's key.)
- "High-cycle cartridge connector and mechanically keyed insertion": a cartridge cannot go in reversed.
- "Physical validation against the M64 cartridge bay and eject mechanism."
- Layout guidance: SNES translators close to the top connector, N64 interface close to the bottom edge, FPGA centrally between them.
- Mechanical abuse tests: insertion force, wobble, repeated cycles, accidental side loading.

## The orientation problem

The SN64 stands upright in the N64/M64 slot, and the SNES cartridge enters from the top, parallel to it. A standard SNES console socket is a vertical through-hole part: its contacts face away from the board it is soldered to, so on an upright board the cartridge would stick out sideways.

A single-board design would need a **right-angle** 62-contact card-edge socket at the SNES's **2.5 mm** pitch. None was found: the only right-angle 62-position edge slot in the LCSC/JLC catalogue (WingTAT ER62BGFBK, LCSC C5173349) is **2.54 mm** pitch, which accumulates 30 × 0.04 = 1.2 mm of error across a row and cannot mate reliably with a 2.5 mm cartridge edge. The Super Game Boy solves the same problem for Game Boy carts with a right-angle connector (reused by MouseBiteLabs' open [Super Game Boy Plus](https://github.com/MouseBiteLabs/Super-Game-Boy-Plus)), but no SNES equivalent is sourced.

## Proposal: two rigid boards

- **Main board (upright):** N64 edge (SummerCart64 geometry), FPGA, power, USB-C, HDMI, clocks, audio ADC.
- **Socket board (horizontal, on top):** a standard vertical SNES socket (candidate NES Repair Shop `snspt043`, see [socket-selection.md](socket-selection.md)), plus the 5 V/3.3 V translators the spec wants close to the socket.
- **Joint:** a board-to-board connector or right-angle headers carrying the translated 3.3 V bus (about 70 signals), cartridge 5 V and many grounds. The final choice follows the signal count once the translators' side is fixed.

Advantages: standard, replaceable socket; the cartridge load goes into a horizontal board that the shell can support directly, instead of into the N64 slot through the main board. Costs: a second board and a connector.

Alternatives kept open: rigid-flex (costly), or a right-angle 2.5 mm socket if a real one is found.

## Depths and clearances

| Interface | Known (source) | Missing |
|---|---|---|
| SN64 into N64/M64 | Edge contacts 2.5 mm pitch, 60.0 mm span; tongue shoulder to insertion tip 10.5 mm; PCB 1.2 mm ([dimensions.md](../dimensions.md), SummerCart64 `a1e7996d`). SummerCart64 shell envelope about 116.1 × 89.4 × 18.1 mm. | How far the shell enters each console; M64 bay, door and eject travel (ModRetro publishes cartridge and door CAD: [official files](https://support.modretro.com/en_us/articles/m64-open-source-files-ByrpukdUGg)). |
| SNES cartridge into SN64 | Socket pin pattern (Sanni footprint): 62 contacts, 2.5 mm pitch, 5.0 mm row spacing. | Socket body height, board seating, contact engagement depth, ears (needs a manufacturer drawing or a measured sample). Cartridge edge engagement length. |
| Cartridge shells | Super Famicom shell CAD (SNESDRONE, usagi_ CC-BY-3.0). | A North American SNES shell source, PAL shell confirmation, and the flashcart shells (Super EverDrive X5/X6, FXPAK Pro). |

"Safely inside" means: the edge fully engaged in the socket, the shell resting on the SN64's top rim (as on a console) so a tall cartridge cannot lever against the N64 slot, and keying that stops reversed insertion for every shell style.

## Next steps

1. Gather the missing dimensions above: downloadable CAD first (ModRetro M64, SNES shell models), then measurements of real parts where no drawing exists.
2. Fix the two-board split and the joint connector.
3. Only then draw the board outlines and start placement.
