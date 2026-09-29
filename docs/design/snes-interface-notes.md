# SNES female cartridge interface: verified pin map

The [62-row map](../../hardware/sn64/interfaces/snes-pin-map.csv) uses the conventional SNES numbering: front cartridge contacts 1–31, rear contacts 32–62. All directions are from **SN 64 acting as the SNES console**, toward or from the inserted cartridge. The map contains every contact exactly once; no contact is universally unused.

## Evidence

1. Exported the native [OpenSFC SHVC-CPU-01 Rev A schematic](https://github.com/starlightk7/OpenSFC/tree/6574450b1a4594b2aae436cf23869b0fb5808ce8/Motherboards/SHVC-CPU-01/Rev%20A) at commit `6574450b1a4594b2aae436cf23869b0fb5808ce8` with KiCad CLI 10.0.6 to XML. Read P1's 62 pin names, actual connected net names and destination pins. This is the primary console-side wiring evidence.
2. Cross-checked the [sd2snes SNESCART_EXT symbol and J101 netlist](https://github.com/mrehkopf/sd2snes/blob/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/pcb/kicad/RevF/sd2snes.net) at commit `cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1`. Its stored design header refers to an older `RevE_krikzz2` generation despite residing in `RevF`; use it as corroboration of connector numbering, not proof of the final Rev F netlist's freshness.
3. Cross-checked every physical pad and pinfunction on J3 in the [Sanni SNES adapter PCB](https://github.com/sanni/cartreader/blob/060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d/hardware/snes_adapter/snes_adapter.kicad_pcb) and [female slot footprint](https://github.com/sanni/cartreader/blob/060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d/hardware/footprints/%21OSCR.pretty/SNES%20Slot.kicad_mod), commit `060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d`. Sanni's symbol electrical pin types are not authoritative console directions.
4. Checked dynamic CIC direction/reset behavior in [SuperCIC lock source](https://github.com/mrehkopf/sd2snes/blob/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/cic/supercic/supercic-lock.asm) and [key source](https://github.com/mrehkopf/sd2snes/blob/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/cic/supercic/supercic-key.asm), rather than inferring behavior from ambiguous D1/D2 labels.

Raw extraction and the derivation script were kept in the original workspace's `.local/interface-research/`; source downloads were not modified. Pin identities agree across all three design sources after normalizing documented aliases.

## Signals requiring special treatment

| Physical contact | Canonical signal | Meaning for the draft |
|---|---|---|
| 1 | SYSTEM_CLK | Actual cartridge clock output. It is separate from PHI2 and CIC_CLK. |
| 2 | EXPAND | Passive expansion link. OpenSFC connects P1.2 to expansion P6.24 and pull-up R97. Preserve defined bias and the ability to sense/release; do not tie it to a push-pull high output or label it NC. The SN 64 expansion-link implementation remains to be decided. |
| 18 | /IRQ | Cartridge/expansion interrupt input to the console CPU, shared with a pull-up (OpenSFC R92). Treat as active-low sensing with open-drain-compatible behavior; no push-pull-high output. An optional deliberate console assertion requires its own justified design. |
| 24 | CIC_DATA1 | Nominal cartridge key-to-console lock data; key CIC pin 1, console CIC pin 2. Preserve configurable I/O/release for supported CIC behavior. |
| 25 | CIC_SLAVE_RESET | Console-to-key CIC reset/trigger, distinct from system /RESET. SuperCIC lock raises then lowers this output to trigger the slave. Do not silently give it the system reset's polarity/name. |
| 26 | /RESET | System reset may also be asserted by cartridge hardware. Preserve input sensing and pull-low/release behavior; a permanently push-pull console output is unsuitable. |
| 31, 62 | AUDIO_L_IN, AUDIO_R_IN | Analog cartridge audio into the console mixing/input path. Sanni intentionally leaves these unconnected in its reader; SN 64 must retain both. They are not digital bus pins. |
| 32 | /WRAMSEL | Actual slot contact, alias `/WRAM`; OpenSFC connects to CPU U1.78. |
| 33 | REFRESH | Actual slot contact; OpenSFC connects to CPU U1.40. |
| 55 | CIC_DATA0 | Nominal console lock-to-cartridge key data; key CIC pin 2, console CIC pin 1. Preserve configurable I/O/release. This is OpenSFC's `CI.D2`, so do not infer physical pin numbers from the data suffix. |
| 56 | CIC_CLK | Dedicated console-to-cartridge CIC clock. Its clock-generation details remain an architecture decision. |
| 57 | PHI2 | Actual slot contact, alias `CPU_CLK`/`CPU_Clock`; OpenSFC connects to CPU U1.72. |

Both SuperCIC data lines change mode in its pair protocol. The CSV records `bidirectional_protocol` with nominal direction in the notes; this does not imply both ends may drive simultaneously. The selected CIC implementation must establish drive/release sequencing.

## Completeness, domains and aliases

- The outer contacts are 1–4, 28–35 and 59–62: 16 of the 62 contacts, not an additional connector. They include B-bus addresses/strobes, timing, expansion and audio. Some ordinary carts omit these pads, but the full socket cannot.
- `/PRD` = `/PARD` at pin 4; `/PWR` = `/PAWR` at pin 35; `/ROMSEL` = `/CART` at pin 49. `/PWR` is a peripheral write strobe, not a power rail.
- A16–A23 at pins 41–48 are also named BA0–BA7. These are aliases for eight of the existing 24 address lines, not eight more signals.
- All eight D0–D7 lines are bidirectional and serve both A/B accesses. Direction and OE must allow contention-free turnaround and undriven/open-bus behavior.
- Pins 27 and 58 share protected switched cartridge +5 V; pins 5 and 36 are ground. Other digital contacts belong to the cartridge's 5 V logic domain and require a reviewed interface to the FPGA domain; this label does not certify thresholds, output topology, tolerance or a translator choice.
- The specification's PHI2, REFRESH, /WRAMSEL and SYSTEM CLK **are all physical slot signals**. None should be removed as internal-only. Core-specific enable nets such as MiSTer `SYSCLKR_CE`/`SYSCLKF_CE` are implementation signals, not extra connector contacts.

## Remaining decisions

The pin identities are source-backed; final translator circuits, IRQ/reset electrical implementation, CIC behavior, clock specifications, pin timing and cartridge-power protection are not selected or validated by this map. Keep resets, CIC and analog audio separate in the schematic. Confirm footprint numbering/orientation and mating geometry against the exact purchased female socket before PCB release. The Sanni footprint is a concrete reference, not a guarantee that every replacement SNES connector shares its mounting pattern. This interface map does not establish cartridge or host compatibility.
