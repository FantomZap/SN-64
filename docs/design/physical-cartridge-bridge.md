# Physical SNES cartridge bridge: contract and verification plan

Design snapshot: 2026-09-29. This document specifies the next integration boundary for [the architecture](../architecture.md). **The current console candidate is not a physical cartridge bridge.** No output-enable implementation, socket-level timing result or cartridge compatibility is claimed. The complete [62-contact map](../../hardware/sn64/interfaces/snes-pin-map.csv), [signal notes](snes-interface-notes.md), [power architecture](power-architecture.md) and [requirements register](../requirements.md) remain binding.

## Existing exports and resolved core issues

The selected upstream is SNESTang `5f0ef193145f67bded7f73f2c477ac8da4d85f7e`. Its [SNES.v](https://github.com/nand2mario/snestang/blob/5f0ef193145f67bded7f73f2c477ac8da4d85f7e/src/SNES.v) connects CPU, WRAM, PPU and APU and exposes separate DI/DO signals for an emulated-cartridge interface. The [SCPU](https://github.com/nand2mario/snestang/blob/5f0ef193145f67bded7f73f2c477ac8da4d85f7e/src/cpu.v) selects CPU, DMA or HDMA address as `INT_A`; it then rewrites low WRAM mirrors in `CA`. That internal transformation must not change the physical socket address.

The generated-source patches in [prepare_core.py](../../fpga/tools/prepare_core.py) now export `RAW_CA = INT_A` separately through SNES, and [the candidate](../../fpga/rtl/sn64_console_candidate.sv) connects it to `cart_address`. Internal `CA` still supplies existing WRAM/decode logic. The diagnostic writes the low WRAM mirror and checks its raw address. This resolves the previously identified address-export issue without changing internal memory mapping.

The same preparation ties SCPU `TURBO` low. Upstream left this input open although it participates in CPU cycle-length selection. Normal CPU cycles can use 6, 8 or 12 master clocks; DMA/refresh/startup have separate rules. The previous open input was a synthesis don't-care despite a passing two-state simulation. PHI2 is now exported from existing SYSCLK and HIGH_RES is connected. These changes are recorded in the generated manifest and leave vendored source intact.

| Candidate signal | Present meaning | Bridge treatment still required |
|---|---|---|
| `cart_address[23:0]` | Raw CPU/DMA/HDMA-selected A address. | Socket timing, output isolation and captured address stability. |
| `cart_peripheral_address[7:0]` | B-bus address. | Independent A/B transaction decoding, including DMA overlap. |
| `cart_rd_n`, `cart_wr_n` | A-bus active-low read/write strobes. | Preserve waveform and distinguish internal/external data ownership. |
| `cart_prd_n`, `cart_pwr_n` | B-bus active-low strobes. | `/PWR` means peripheral write; it is not cartridge power control. |
| `cart_romsel_n`, `cart_wramsel_n`, `cart_refresh` | Core selects and refresh state. | Preserve physical contacts and prove their timing; `/ROMSEL` alone is not a universal external-access decoder. |
| `cart_phi2` | Core CPU clock waveform. | Establish frequency/duty/phase and output constraints at the socket. |
| `cart_data_in`, `cart_data_out` | Core cartridge input and upstream write/B-read data feed. | Add resolved internal-read data, ownership, driven-bit validity and turnaround policy. |
| `cart_irq_n` | Active-low CPU IRQ input. | Shared-line receiver, bias, power isolation and timing. |

SYSTEM_CLK, shared system reset sensing/assertion, CIC clock/data/slave reset, EXPAND, analog audio and all power controls still need explicit implementation. SYSCLK edge-enable pulses are internal scheduling signals, not additional socket contacts.

## Shared data bus and ownership

Upstream SNES assigns `DO = ~INT_PARD_N ? BUSB_DO : CPU_DO`. SCPU assigns its DO from `MDR`, which captures internal read results at the cycle's falling-edge enable. Thus `cart_data_out` does not expose the current WRAM or CPU-I/O read byte during the active read window. A translator around this signal alone would leave a physical cartridge observing stale data on those internal reads. Source evidence is the pinned [SNES bus mux](https://github.com/nand2mario/snestang/blob/5f0ef193145f67bded7f73f2c477ac8da4d85f7e/src/SNES.v) and [SCPU MDR/readback logic](https://github.com/nand2mario/snestang/blob/5f0ef193145f67bded7f73f2c477ac8da4d85f7e/src/cpu.v); exact socket behavior must also be compared with real console traces.

The proposed next core boundary should provide the selected internal read byte, a driven-bit mask or equivalent validity, console write data, raw A/B addresses, strobes and explicit ownership information. This is a design proposal, not implemented ports. Keep internal CPU input selection separate from the value visibly driven on socket D0-D7. Decode CPU registers, WRAM and B-bus peripherals with the same rules as their functional modules so the bridge cannot disagree about the selected responder.

| Transaction class | Required model and check |
|---|---|
| CPU write to external cartridge | Console drives the write byte with characterized setup/hold; cartridge receives. Test high/low data transitions and consecutive writes. |
| External cartridge read | Console releases D0-D7; cartridge response reaches core sampling within the available window. Include cartridge registers outside ordinary ROM-selected ranges. |
| Internal WRAM/CPU-register read | Export the internal responder's current data, including partial-bit/open-bus behavior where applicable. The slot must not observe stale MDR substituted for current read data. |
| Internal PPU/APU/WRAM B-bus read | Preserve peripheral selection/read side effects and make resolved read data available at the bridge boundary. |
| A-to-B DMA/HDMA | Model the A-side source and B-side destination concurrently. An external A-side source may drive the shared bus while the internal B-side peripheral consumes it. Avoid a second console driver. |
| B-to-A DMA/HDMA | Select the actual B-side source. Internal peripheral data must reach an external A-side destination; an external B-side responder must remain the physical driver when selected. |
| No responder or partially driven read | Preserve documented open-bus/retained-bit behavior. Do not fabricate `$EA`, `$00` or `$FF` as a universal hardware response. |

The table is a test classification, not a completed combinational direction equation. Neither `direction = !WR_N` nor `drive only during writes` covers the complete console data bus. The bridge must retain A/B timing relationships, ownership during DMA, read side effects and response latency without feeding its own output back as a false cartridge response.

The present diagnostic's asynchronous input model supplies bytes by address regardless of output enables and selects. It verifies the core's data path but cannot detect electrical contention, release delay or an incorrectly selected physical responder. Replace or supplement it with a bus-resolution model that records each participant's intended drive/value and fails on overlapping incompatible ownership. Use four-state simulation where available; with a two-state simulator, track ownership and valid bits explicitly so an undriven input cannot silently become zero.

## Timing, reset and remaining contacts

Derive an explicit clock and I/O timing budget from the selected oscillator/PLL, core sampling edges, FPGA output/input paths, translator propagation, PCB/cable loading and cartridge response. Add setup/hold and clock-output constraints for the actual package and bank allocation. An unconstrained core route is not the socket budget. Do not assume one generic input synchronizer is suitable for every data, clock, IRQ, reset and CIC signal; preserve deterministic bus latency while resolving asynchronous controls individually.

SYSTEM_CLK, PHI2 and CIC_CLK are distinct socket clocks. Validate NTSC and PAL frequencies and phase/duty requirements separately; changing the core PAL bit does not generate a different master clock. The pinned [DSP](https://github.com/nand2mario/snestang/blob/5f0ef193145f67bded7f73f2c477ac8da4d85f7e/src/dsp.v) fixes CE generation to an NTSC-derived input constant, and [dsp.vh](https://github.com/nand2mario/snestang/blob/5f0ef193145f67bded7f73f2c477ac8da4d85f7e/src/dsp.vh) selects `ACLK_FREQ=411904`. Characterize and resolve audio cadence for each regional clock and output transport rather than assuming nominal 32 kHz.

Treat `/RESET` as a sensed line with deliberate pull-low/release behavior, including cartridge-originated reset. Keep host reset, console system reset and CIC_SLAVE_RESET distinct. Use the console-side [SuperCIC lock](https://github.com/mrehkopf/sd2snes/blob/cf7e21d7a5978fcd74981d71c3cfbf6e982a4dd1/cic/supercic/supercic-lock.asm) as the behavioral reference, retaining its notices; its reset trigger and data direction changes require a dedicated design. The N64 CIC endpoint is a different interface.

Preserve EXPAND sensing/release/bias and all outer contacts. Route AUDIO_L_IN/AUDIO_R_IN into an analog conditioning/conversion and mixing path with measured levels/noise/headroom; never through digital bus translators. Qualify the exact socket and mating geometry using [socket selection](socket-selection.md), including X5/X6/FXPAK Pro and enhancement-cartridge cases.

## Fault gating and power sequencing

Implement and qualify the power document's proposed interface rails, default-off cartridge supply and hardware voltage/fault veto. Proposed permission is the conjunction of configured safe logic, valid required rails, valid cartridge supply, no latched fault, and an explicit run request. **A firmware request cannot override the hardware veto.** Actual components, polarity and response bounds must be fixed and verified before this becomes a circuit contract.

Address/control outputs and the D-bus driver must disable on configuration loss, reset/fault policy, or invalid rails even if the master clock stops. Disable the data translator before changing direction; wait the characterized release/settling interval before enabling the new owner. Keep shared lines released and cartridge power off during blank-board loading and recovery. Qualification must cover host-only, USB-only, simultaneous supplies, unplugging either source, brownout and an externally energized cartridge-side rail. No digital gate equation alone proves power-off isolation or prevents signal-pin back-power.

## Next verifiable work

These are pending tests/design deliverables, not completed results. Preserve source/build identity, expected limits, waveforms and failure evidence for each.

1. **Resolved read interface:** write two different WRAM bytes, read them through direct and mirrored addresses, and assert the socket model sees each current byte before the end-of-cycle sample. Intentionally substitute MDR to demonstrate failure. Add CPU I/O and PPU/APU/WRAM-port reads, including partially driven bits and side effects.
2. **Address/selection coverage:** check raw mirror addresses, LoROM/HiROM-style external ranges, cartridge register ranges, `/ROMSEL`, `/WRAMSEL`, refresh and all A/B strobes. Keep CPU, DMA and HDMA source selection explicit.
3. **Peripheral DMA matrix:** test A-to-B and B-to-A with internal and external responders, increment/decrement/fixed address modes, byte counts/bank boundaries and representative HDMA reloads. Assert both destination data and source/destination bus ownership.
4. **Turnaround model:** test read-to-write, write-to-read and back-to-back changing owners with nonzero responder/translator delays. Assert no simultaneous incompatible drive, adequate release interval, and valid data at sampling edges. Include absent cartridges/open bus rather than unconditional address-based test data.
5. **Clock/reset checks:** assert normal 6/8/12-master-clock CPU periods in applicable windows and distinct DMA/refresh behavior; test IRQ, cartridge reset, pause/restart, NTSC and actual PAL master clocks. Add video-frame and audio-sample cadence checks and meaningful PPU/APU memory traffic.
6. **Fault disable:** inject rail/fault/configuration loss during every bus phase and while the core clock is halted. Require outputs to disable within the predeclared hardware bound, supplies to enter their defined state, no automatic unsafe restart, and no spurious save write. Then verify the same cases on a protected fixture with measured leakage/current and scope captures.
7. **Physical qualification:** after isolated power/dummy-load tests, compare socket waveforms with reference-console behavior, then progress through diagnostic cartridges, ordinary ROM/SRAM, enhancement carts and physical X5/X6/FXPAK Pro on both hosts. Follow the acceptance register's bring-up order and save-integrity checks; passing a core simulation does not skip these gates.

The [core evaluation report](../../fpga/reports/evaluation.md) records the narrower implemented simulation and synthesis scope. Add bridge results there or in dedicated linked reports when they exist; leave unrun behavior explicitly open.
