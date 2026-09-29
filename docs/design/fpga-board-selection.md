# FPGA board selection and reusable reference circuits

Research snapshot: 2026-09-29. Status: candidate selection, with an initial synthesis result; no routed SN64 FPGA board, measured power budget, procurement commitment or hardware validation.

Keep **LFE5U-85F in BG381** as the current custom-board baseline. The original `LFE5U-85F-6BG381C` is poorly stocked; the faster industrial `LFE5U-85F-8BG381I` is a credible purchasing alternative after selecting its exact implementation target. Use a ULX3S-85F for early core experiments if a prototype is purchased. The cheaper 45F remains an explicit external-memory alternative, not an approved substitute.

## Memory and implementation evidence

The intended on-chip memories are WRAM 128 KiB, VRAM 64 KiB and ARAM 64 KiB: 256 KiB total. Lattice specifies 208 eighteen-kilobit EBRs for 85F and 108 for 45F. In a simple 2 KiB byte-wide mapping, these memories alone require at least 128 blocks. Port requirements, mapping and other core memories determine the actual total. The 45F's entire raw EBR capacity is below 256 KiB. See [Lattice ECP5 datasheet, table 1.1 and sysMEM description](https://www.latticesemi.com/view_document?document_id=50461).

The [recorded evaluation](../../fpga/reports/evaluation.md) successfully synthesized the console core and these three memories on 2026-09-29: **139 DP16KD, 26,669 LUT4, 10,775 TRELLIS_FF and 19 MULT18X18D**. It used the OSS 20260928 toolchain with Slang and the recorded `abc9.xaiger` compatibility setting. This is 66.8% of the 85F's EBR count, leaving 69 blocks before host interface, video/audio transport, menus, buffers and protection-control logic. A trial grade-6/CABGA381 route achieved 29.91 MHz against a 21.477273 MHz internal-clock constraint, with unconstrained trial I/O. This is not a complete board pin/bank or external-timing result, gameplay result or power budget.

Moving WRAM outside the FPGA would remove a theoretical minimum of 64 byte-wide EBRs. Subtracting that minimum from the observed total gives 75, below the 45F's 108. That arithmetic is a reason to investigate 45F, **not a prediction that it fits**: the memory controller, buffering, timing, I/O allocation and revised mapping need their own synthesis and route. External memory also adds PCB area, signals, power and validation work.

## Supplier snapshot

Prices are USD per unit at quantity one, excluding shipping and tax, observed on public direct supplier pages. Inventory and incoming dates are snapshots, not reserved supply. The three bare-device pages reported active status and a 43-week manufacturer standard lead time.

| Candidate | Public availability | Price | Use in SN64 |
|---|---:|---:|---|
| [LFE5U-85F-6BG381C, DigiKey](https://www.digikey.com/en/products/detail/lattice-semiconductor-corporation/LFE5U-85F-6BG381C/5395905) | 0; 90 expected 2027-02-15 | $74.75 | Original baseline; do not plan an immediate build around the incoming estimate. |
| [LFE5U-85F-8BG381I, DigiKey](https://www.digikey.com/en/products/detail/lattice-semiconductor-corporation/LFE5U-85F-8BG381I/5398971) | 60 in stock | $99.88 | Same family, density and package; faster industrial grade candidate. Rebuild for the selected grade and include its power/temperature assumptions. |
| [LFE5U-45F-6BG381C, DigiKey](https://www.digikey.com/en/products/detail/lattice-semiconductor-corporation/LFE5U-45F-6BG381C/5250564) | 46 in stock | $46.64 | $53.24 below the currently stocked 85F alternative before external-memory costs. Requires a new memory architecture. |
| [ULX3S-85F, Crowd Supply](https://www.crowdsupply.com/radiona/ulx3s) | In stock | $275 | Complete development board with LFE5U-85F-6BG381C; useful for core, flash and clock experiments. |

ULX3S supplies 32 MiB SDRAM, configuration flash, a 25 MHz reference and 56 external GPIOs. Those GPIOs should not be assumed sufficient for both complete parallel cartridge interfaces at once. Its development-board connectors and enclosure dimensions also do not establish SN64 cartridge compatibility. No board was ordered. [ULX3S hardware specification and offer](https://www.crowdsupply.com/radiona/ulx3s).

## Package and electrical constraints

For LFE5U-85F, BG381 is a 17 × 17 mm, 0.8 mm-pitch caBGA with 205 user I/Os. The 45F BG381 has 203; check migration tables and every ball before permitting either density on one layout. ECP5 core operation is 1.045–1.155 V and auxiliary operation 2.375–2.625 V. VCCIO is bank-specific; use the selected I/O standard's operating limits, not the generic 1.14–3.465 V envelope as a tolerance. Commercial junction range is 0–85 °C; industrial is −40–100 °C. These pins are not 5 V inputs. [Lattice datasheet, tables 1.1, 3.1–3.2](https://www.latticesemi.com/view_document?document_id=50461).

All supplies need monotonic ramps within 0.01–10 V/ms. POR monitors VCC, VCCAUX and VCCIO8 on startup, not every I/O bank. Master-SPI startup requires configuration-bank power sequencing or holding PROGRAMN/INITN low until flash logic levels are valid. Left/right banks have restricted hot-socket behavior. [Lattice datasheet, §§3.3–3.7](https://www.latticesemi.com/view_document?document_id=50461).

SN64 consequence: keep cartridge/host translators disabled whenever core or their relevant I/O rail is invalid. USB-only first loading must power the FPGA and configuration bank through hardware-controlled supplies even with erased flash. Do not rely on FPGA firmware to turn on its own mandatory programming rails. The existing USB bridge's regulator is not the full-board supply; use the source-selection and budget work in [power architecture](power-architecture.md). `LFE5UM5G` development boards use a different core voltage and SERDES circuitry and are not electrical drop-in references for this LFE5U design.

## Pinned ULX3S reuse reference

Inspected upstream hardware commit: **`6a92cec6b177191c5b0f80e260013a1f8ec147dd`** from [emard/ulx3s](https://github.com/emard/ulx3s/tree/6a92cec6b177191c5b0f80e260013a1f8ec147dd). Small exact source files are staged only in ignored `.local/fpga-board-research/ulx3s-6a92cec6b177191c5b0f80e260013a1f8ec147dd/`. This task did not import them into the SN64 circuit libraries.

| Exact source sheet | Reusable circuit evidence | Adaptation prerequisite |
|---|---|---|
| [power.sch](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/power.sch) | U1 power units and decoupling; U3–U5 TLV62569DBV buck stages for nominal 1.1, 2.5 and 3.3 V; inductor and feedback networks. | Recalculate current/transients, input headroom, capacitors, feedback tolerance and layout for SN64. Separate useful regulators from the RTC/power-latch and FTDI sleep-control functions. |
| [flash.sch](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/flash.sch) | U10 IS25LP128F-JBLE SPI flash; FPGA configuration signals, pull-ups and Master-SPI notes. | Verify exact flash voltage, availability, supported programming algorithm and capacity; retain PROGRAMN, INITN and DONE access. Confirm configuration-bank balls against the selected Lattice device. |
| [usb.sch](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/usb.sch) | FPGA clock/configuration connections and Y1 FNETHE025 25 MHz clock source; upstream FT231XQ/JTAG arrangement. | Preserve SN64's existing FT232HL/isolated-target programming architecture. Its GPIO enable contract differs from ULX3S. Y1 uses a generic legacy crystal symbol despite the clock-source part; validate the actual oscillator's pinout, enable and supply before copying it. |
| [ulx3s.sch](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/ulx3s.sch) and [cached symbols](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/ulx3s-cache.lib) | Legacy hierarchy and symbol definitions needed to interpret the sheets. | The FPGA library identifier contains `LFE5UM`, while the instance value/MPN says `LFE5U-85F-6BG381C`. Validate actual ball mapping, not the library identifier alone. |

TI specifies TLV62569 operation from 2.5–5.5 V and up to 2 A. This makes the ULX3S buck stages useful candidates on a valid approximately 5 V system source; it does not establish the total FPGA requirement or available input power. The DBV five-pin variant does not acquire a power-good pin merely because other family variants have one. A separate rail-valid/reset arrangement may be needed. [TI TLV62569 documentation](https://www.ti.com/product/TLV62569).

ULX3S's [manual](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/doc/MANUAL.md) documents openFPGALoader flash use. For SN64, persistent loading still requires the selected SPI flash and a supported JTAG-to-flash path, generally using a temporary FPGA loader. Loading volatile SRAM alone is not a persistent factory program. Do not use the ULX3S cable preset for SN64 without checking its pin/GPIO initialization against [the existing programmer contract](usb-programming-architecture.md).

The pinned [LICENSE.md](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/LICENSE.md) is **MIT-style with an additional logo condition**, not ordinary unmodified MIT. It requires notice retention and preservation of EMARD/RADIONA/FER top-silkscreen logos, including position, shape and size. Preserve the exact license and address this condition before importing/adapting upstream layout. No conclusion about exceptions for partial reuse is assumed here.

Local exact-source SHA-256 checksums:

| File | SHA-256 |
|---|---|
| LICENSE.md | `cdaaa3f0c2d1dbb538844077fd7a1d9d43c890d0745b20d8aa0717b583d6af9f` |
| power.sch | `0a7ea4d8aa82dd30be2c21654e6e38d335413440c477129f8a6e45eb70c23b43` |
| flash.sch | `a31d5899b7481a0b98a99fdf84b0020a76a861b4d1d6cef6753b15f41250889d` |
| usb.sch | `023e16f40ab93ff4f6a403062964d874624dc1f188a15bbda18b1df87e278ecd` |

## Gates before fixing the board BOM

1. Preserve the successful synthesis recipe and run place-and-route for the exact candidate grade/package, including realistic clock constraints and the remaining SN64 logic.
2. Allocate all interface, flash, clock, JTAG and control balls with bank voltages and configuration-time behavior checked against Lattice's pin data.
3. Produce a rail-by-rail power estimate, then validate regulator limits, startup, shutdown, USB-only loading and console/USB source transitions on hardware.
4. Confirm oscillator and flash orderable parts; prove blank-board JTAG access, persistent flash programming and recovery from a corrupt image.
5. Recheck supplier stock and manufacturing assembly capability after the above work. Keep 45F plus external WRAM as a separately synthesized cost-reduction option.
