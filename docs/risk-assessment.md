# SN64 risk assessment

Quick assessment, 2026-09-29, based on the current design documents. Levels are engineering judgment, not measurements. All specification targets remain in scope; this document orders work by risk and does not remove anything.

| # | Risk | Level | Response |
|---|---|---|---|
| 1 | **Power.** The N64/M64 slot has no 5 V contact and limited current: the M64 limiter is set near 500 mA at 3.3 V, about 1.65 W. The FPGA, a SNES cartridge (especially Super FX, SA-1 or FXPAK Pro) and video output plausibly need more. | High | Close the power budget first. Expect the mandatory side USB-C port to be needed for power during play, particularly on original N64. Cartridge power stays off until hardware checks pass. |
| 2 | **Video path.** The N64 cartridge slot cannot carry SNES video to the console, so the TV connects to the adapter. One-cable HDMI through M64 depends on an interface ModRetro has not documented and may never exist. | High (expectation) | Adapter provides its own digital A/V output. M64 single-HDMI stays a tracked target with an external dependency. |
| 3 | **Real-cartridge timing.** The FPGA must reproduce SNES bus timing closely enough for real cartridges. Enhancement chips and FXPAK Pro are sensitive. SNESTang was built around loaded ROM images, not a physical slot. | High | Feasibility is proven commercially: Analogue Super Nt runs real cartridges on an FPGA SNES. Build the bridge in simulation with contention/timing checks, then prove it on inexpensive development hardware before the custom board. |
| 4 | **Board complexity.** ECP5 BG381 is a 0.8 mm-pitch BGA. It needs a 4–6 layer board, careful fan-out and power integrity, and X-ray-inspected assembly. PCB layout is the weakest area for automated design. | High | Reuse a proven open ECP5 layout (ULX3S, observing its logo condition), or evaluate an off-the-shelf ECP5 module on a simpler carrier board. Independent review before any order. |
| 5 | **N64 host side.** The adapter must pass the N64 CIC lockout and run an N64 program for the menu and controller transfer. | Medium | Reuse SummerCart64 (proven PI/CIC/SI endpoint) and the libdragon N64 SDK. |
| 6 | **Damaging hardware during bring-up.** | Medium | First power-ups use a current-limited supply with no console or cartridge. Early host tests use an inexpensive used N64 and an inexpensive cartridge, not the M64 or valuable games. |
| 7 | **Physical fit.** A tall assembly levers on the host slot. M64 door/eject clearance and varied cartridge shells must fit. | Medium | Buy a socket sample (~US$10). Iterate with 3D-printed fit coupons before the full enclosure. |
| 8 | **Parts availability.** `LFE5U-85F-6BG381C` shows no stock until 2027; `-8BG381I` was in stock (60 units). | Medium | Design for an orderable part. Recheck stock before committing the BOM. |
| 9 | **Cost and revisions.** First boards rarely work unchanged. Expect 2–3 board revisions and basic test equipment (multimeter; ideally an inexpensive logic analyzer). | Medium | Retire the largest risks cheaply before the full custom board. |
| 10 | **Scope.** The specification includes PAL, telemetry, factory test, recovery and M64 HDMI. The risk is never reaching a working unit. | Medium | Staged milestones: first a playable cartridge path, then host integration, then the remaining targets in order. |
| 11 | **M64 unknowns.** A newer console whose firmware can change, with MCU-controlled cartridge power and limited documentation. | Medium | Test on a real M64 early. Do not depend on undocumented behavior. |
| 12 | **Licensing.** GPL-3.0 core, CERN-OHL-S-2.0 SummerCart64 hardware, the ULX3S logo condition and Nintendo trademarks matter if the product is ever sold. | Low now | Already tracked per source. Review before any sale or public release. |

## Verification limits

Software checks — simulation, ERC/DRC, comparison against proven designs and independent review — catch most design errors before ordering. They cannot establish real-cartridge timing margins, actual power draw, thermal behavior, noise or host-console behavior. Those require physical tests, performed by the user with guided procedures. Verification therefore happens throughout the work, with the riskiest parts proven early, not only as a final check.

## Recommended de-risking milestone

Before the full custom board, prove the hardest path on inexpensive hardware: an ECP5 development board (for example ULX3S-85F, about US$275) plus a small, simple adapter board carrying the SNES socket and level translators. Target: a real SNES cartridge playing through the FPGA core with HDMI output, powered over USB, with no N64 involved. Success retires risks 3 and much of 1 and 4 before committing to the BGA board.
