# N64 / M64 lower cartridge interface — reference-verified draft

This is a 50-contact interface reference for SN64 acting as a **cartridge endpoint**. `in` means host to SN64; `out` means SN64 to host. It is not a completed circuit, a proven electrical design, or a manufacturing release. The same physical edge is intended for original N64 and M64; the M64 PDFs corroborate the contact identities but do not prove interchangeable timing, firmware behavior, or available power.

The machine-readable [pin map](../../hardware/sn64/interfaces/n64-pin-map.csv) retains every contact, including unused and unresolved ones. `/` denotes an active-low signal. Canonical signal names omit the host prefix; the CSV notes preserve exact source aliases. All SN64 electrical behavior remains unverified in hardware.

## Evidence and orientation

- SummerCart64 [schematic](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_sch) and [PCB](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_pcb), commit `a1e7996d2cbece686820a5c785029c68514f17b0`. KiCad 10 exported a fresh XML netlist from the local schematic; connector `J_N1` supplies the electrical map. The PCB pad-net map independently agrees for all 50 contacts after normalizing KiCad no-connect net names.
- Official M64 [cartridge schematic](https://cdn.shopify.com/s/files/1/0829/2034/1806/files/M64_CART_SCH.pdf?v=1786637332), physical PDF page 1, connector `J1`, and [mainboard schematic](https://cdn.shopify.com/s/files/1/0829/2034/1806/files/M64_MLB_SCH.pdf?v=1786637413), physical page 5, connector `J11`, corroborate pin numbers and aliases. Page references here are **physical PDF pages**, since title-block page totals are inconsistent. Source listing: [M64 open-source files](https://support.modretro.com/en_us/articles/m64-open-source-files-ByrpukdUGg).
- SummerCart64 [top-level HDL](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/fw/rtl/top.sv), [PI controller](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/fw/rtl/n64/n64_pi.sv), [SI controller](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/fw/rtl/n64/n64_si.sv), [CIC controller](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/fw/rtl/n64/n64_cic.sv), [IRQ control](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/fw/rtl/n64/n64_top.sv), and [pin constraints](https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/fw/project/lcmxo2/sc64.lpf) resolve actual endpoint behavior where schematic symbol directions are misleading. All cited SummerCart64 files use the same pinned commit.

In the source PCB, pads 1–25 are on `B.Cu`; pads 26–50 are on `F.Cu`. Pads 1/26 are at X=180 mm and pads 25/50 at X=120 mm, with 2.5 mm pitch; copper pads are 1.5 × 7.0 mm. These are the source PCB coordinate conventions, **not** a new front-view definition. Preserve this side/number association when creating a new footprint and verify the finished connector orientation against the host and shell. Hole/edge/bevel details require the separate mechanical reference; this signal document does not approve a footprint.

## Contact groups and behavior

| Contacts | Role at the SN64 endpoint | Draft handling |
|---|---|---|
| 1, 2, 6, 22, 23, 25, 26, 27, 31, 47, 48, 50 | Ground | Preserve all 12 returns. |
| 9, 17, 34, 42 | Host 3.3 V power | Power inputs, kept distinct from local rails until power-path selection. |
| 13, 38 | Nominal 12 V power | SummerCart64 leaves both unconnected. M64 labels `V_12P0_CART`; retain isolated until host availability and the need/current are verified. |
| 3–5, 7, 11–12, 15–16, 28–30, 32, 36–37, 40–41 | AD[15:0] | Bidirectional multiplexed PI bus. Host drives addresses and write data; SN64 drives selected read data only. |
| 8, 10, 33, 35 | /WRITE, /READ, ALE_L, ALE_H | Host inputs to SN64. Do not derive latch polarity/timing solely from a net name. |
| 20, 45 | /RESET, /NMI | Host inputs to SN64; active low. Do not tie these to the SNES-side reset output. |
| 18, 43 | CIC_DATA, CIC_CLK | CIC clock is input. CIC data is bidirectional low-or-release in the reference implementation; preserve authentication ownership and release. |
| 19, 21 | PIF_CLK, JOYBUS | Serial clock input and bidirectional low-or-release data. M64 calls them `CIC_11` and `EEPROM_DAT` at its connector symbol; the actual nets are `n64_PIF_CLK`/`n64_JOYBUS`. These are distinct from CIC_CLK/CIC_DATA. |
| 44 | /INT | Cartridge interrupt output to host with output enable; see implementation detail below. |
| 14, 39 | KEY1_RESERVED, KEY2_RESERVED | SummerCart64 no-connect; M64 FPGA-connected. Keep separate and isolated; their names do not establish a usable private interface. |
| 46 | VIDEO_SYNC_RESERVED | Unresolved legacy CSYNC/video-sync role. SummerCart64 assigns this pad high-Z continuously; no active SN64 drive selected. |
| 24, 49 | AUDIO_L, AUDIO_R | Nominal cartridge-to-host audio contacts, unused in SummerCart64. Preserve their identity and isolation. Analog levels, M64 routing behavior, and usefulness for SN64 require separate proof. |

**No contact is a 5 V supply.** The SNES cartridge's 5 V rail must come from a separately designed power stage or another explicitly selected source. Neither a nominal 12 V label nor M64's internal 5 V rail establishes an available SN64 power budget.

The SummerCart64 LPF sets all implemented N64 logic pads to `LVCMOS33`. It uses pull-ups for CIC clock/data, IRQ, /READ, /WRITE, ALE_H, and SI data; pull-downs for /RESET, /NMI, ALE_L, and SI clock; and no pulls on AD or VIDEO_SYNC. These are reference implementation settings, not permission to copy bias resistors or I/O standards to an arbitrary FPGA without its datasheet and host loading analysis.

Pin 44 is a concrete schematic-direction trap: the connector symbol's direction alone is not authoritative. `n64_top.sv` drives `n64_irq` from the cartridge. `irq_dq` is the complement of the asserted-interrupt state while output enable passes through a two-cycle shift register. Thus the line is low during a sustained interrupt and eventually high-Z while inactive, but it can briefly drive high during deassertion. Do **not** describe this exact implementation as strictly open-drain. CIC data and SI data, by contrast, explicitly use `0` or `Z` assignments. The SN64 IRQ implementation and safe inactive-state bias remain design decisions.

SummerCart64 connects reset/CIC to both its MCU and FPGA: `/RESET` → U6 PA0/pin7 and U8/pin31; `CIC_CLK` → U6 PA1/pin8 and U8/pin34; `CIC_DATA` → U6 PA2/pin9 and U8/pin35. A reuse design must preserve intentional firmware/FPGA ownership; it cannot let both devices drive CIC simultaneously.

## Power and protection circuits worth reusing as references

**SummerCart64 power selection, schematic U1/U2.** U1 `TC1264-3.3VDB` takes the board's `+5V` on pin1 and supplies a regulated 3.3 V node on pin3. U2 `TPS2111A` takes that node on IN1/pin8 and the N64 `N64_3V3` contacts on IN2/pin6; OUT/pin7 supplies the internal `+3V3` rail. C6 is 100 nF from the N64 input rail to ground. U2 VSNS/pin3 has R1=1 kΩ to the U1 output and R2=330 Ω to ground; ILM/pin4 has R3=470 Ω to ground. D1/pin2 is grounded; D0/pin1 is explicitly no-connect. This is a useful dual-source power-path starting point. Reconfirm operating mode, reverse-current behavior, limits, inrush, thermal performance, and fault behavior from the selected part's datasheet before reuse. The local `+5V` input in this circuit is not supplied by the N64 edge.

**SummerCart64 signal connection.** The checked N64 logic nets go directly to U8 `LCMXO2-7000HC` (reset/CIC also connect to U6). This reference does not place a general bus buffer or series protection device between the connector and FPGA. Direct wiring here is not evidence that a different SN64 FPGA tolerates an unpowered host, host-first startup, overshoot, or hot insertion. Separate isolation/ESD choices and safe output-enable sequencing are still needed.

**M64 host-side cartridge power, mainboard physical page 28.** U32 `TPS2553DRVR` is the cartridge 3.3 V power-switch/current-limit reference. The sheet gives R190=41.2 kΩ at ILIM and explicitly annotates **“500mA Ilimit”**; R192=10 mΩ provides a monitored series path with TP66/TP64. The host control/fault nets are `MCU_V_CART_EN` and `MCU_CART_PWR_FAULT`; R188=100 kΩ and C268=10 µF are adjacent to this circuit. This annotation concerns the published M64 design. It is not an allocation for SN64, a measured guaranteed current, or a rating for an original N64. Budget operating current, startup/inrush, margin, and both hosts before selecting an SN64 FPGA or SNES cartridge load.

**M64 12 V, mainboard physical page 29.** U25 `TLV61046A`, L5=10 µH, and `MCU_V12P0_CART_EN` implement the reference cartridge 12 V generation from the M64's internal `V_5P0_SYS`. This establishes the source topology in this M64 revision, not a usable current entitlement on pins13/38. The M64 cartridge power sheet (physical page4) also contains U7 `AP22800HB-7` and its own local power distribution, which is a sequencing/reference candidate rather than an approved drop-in SN64 stage.

## Remaining decisions before connecting a real host

1. Select FPGA/MCU I/O domains and isolation that remain safe for host-first, adapter-first, reset, loss of either rail, and programming power. Establish no-backfeed behavior with component datasheets and measurements.
2. Derive the combined FPGA, memory, conversion-loss, SNES cartridge, and peripheral budget on both hosts. Validate startup and worst-case loading; do not borrow the M64 sheet's 500 mA annotation as an SN64 allowance.
3. Implement and verify PI address/data turnaround, read output enable, host reset/NMI behavior, CIC ownership/region behavior, and serial reply timing. Confirm the exact IRQ electrical mode and deassertion behavior chosen for SN64.
4. Resolve KEY1/KEY2, CSYNC, and audio only if the selected architecture needs them. Until then retain individual contacts with explicit reserved/high-Z handling, not ordinary driven FPGA outputs. M64 digital routing does not prove an original-N64-compatible audio/video path or the single-HDMI target.
5. Verify footprint numbering, insertion orientation, contact setback/bevel, connector wear/fit, and mechanical clearance against the physical hosts before fabrication.

## Verification record

The source extraction checks all 50 numbered contacts against both SummerCart64 schematic netlist and PCB pad/net records, checks 12 ground contacts and four 3.3 V contacts, and cross-checks FPGA pad numbers against the pinned LPF for every implemented logic net. M64 connector aliases and power annotations were checked against official PDF text. No timing simulation, electrical measurements, assembled prototype, or manufacturing validation has been performed for SN64.

Sources remain third-party material. SummerCart64's PCB hardware has its own `hw/pcb/LICENSE` (CERN-OHL-S-2.0), separate from the top-level GPL-3.0 software license. The extracted edge footprint retains the hardware license and attribution in [the hardware notices](../../hardware/sn64/THIRD_PARTY.md). Preserve the applicable notices as further implementation is copied. The M64 download page's “open source” label and PDF copyright notices alone are not an explicit reusable CAD/hardware license grant; this document assigns no new license to those files.
