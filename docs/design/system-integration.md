# Integrated top level and system simulation

Snapshot 2026-09-29. [fpga/rtl/sn64_top.sv](../../fpga/rtl/sn64_top.sv) connects every FPGA block that exists so far. [fpga/tests/tb_system.sv](../../fpga/tests/tb_system.sv) runs the whole power-on story in simulation. **Nothing here has run on hardware.** The board top level [sn64_board_top.sv](../../fpga/rtl/sn64_board_top.sv) (PLLs, the SNES clock select, flash boot ROM, CIC pads) is pinned to [fpga/constraints/sn64_board.lpf](../../fpga/constraints/sn64_board.lpf), which is generated together with the FPGA schematic sheet ([fpga-schematic.md](fpga-schematic.md)). Since the round-3 integration the KiCad root holds all five child sheets (USB programmer, cartridge interface, FPGA, power, clock/HDMI/cartridge audio); see [Schematic integration](#schematic-integration-round-3-2026-09-29).

## Plain-language summary

This is the point where the separate pieces become one design. The system test powers everything up the way a real console would: the N64 boots our menu and asks for the cartridge, the cartridge gets power in the safe order, the clock chip is programmed, the region is decided, the SNES clock starts once, the reset lets go, and the SNES runs a program from a (simulated) cartridge that reads the buttons the N64 sent. It passes in about 5 seconds on the PC. Its first run found a real deadlock in the reset wiring, which is now fixed.

## Blocks and clock domains

| Domain | Clock | Blocks |
|---|---|---|
| Housekeeping | 25 MHz oscillator | [Si5351 start-up and region latch](clock-plan.md), [power sequencer](power-sequencer-implementation.md), [SNES CIC lock](snes-cic-implementation.md) (CIC_CLK = 25 MHz / 8 = 3.125 MHz) |
| Host | 62.5 MHz from an ECP5 PLL, always on | [N64 endpoint](n64-endpoint-implementation.md) (PI bus, mailbox, bootstrap ROM window) and the [N64 CIC](n64-cic-implementation.md) soft CPU, cartridge-audio I2S receiver ([cart audio](cart-audio-implementation.md)) |
| SNES | Si5351 NTSC or PAL master, started once per cartridge power-up | SNES core, [cartridge bridge](cartridge-bridge-implementation.md), [controller emulation](controller-path-implementation.md), cartridge-audio elastic buffer and mixer |
| HDMI pixel | Si5351 CLK2 (NTSC master x 39/31 = 27.0198 MHz, PAL master x 108/85 = 27.0399 MHz) and ECP5 PLL x5 | [HDMI and audio output](av-output-implementation.md) (720x480p VIC 2 or 720x576p50 VIC 17), held in reset until CLK2 is programmed for the latched region |

The N64 endpoint must run from an always-on clock: the N64 boots the menu before the SNES clock exists. Crossings use [sn64_cdc.sv](../../fpga/rtl/sn64_cdc.sv): two-flop synchronisers for levels and a toggle-handshake word transfer for the controller images, status and fault words and the mailbox CONTROL bits. The word transfer is tested for torn values across unrelated clocks ([tb_cdc.sv](../../fpga/tests/tb_cdc.sv)).

## Power-on sequence as implemented

1. Board reset releases; the Si5351 is programmed and both PLLs lock (`STATUS[0]`).
2. The N64 boots the bootstrap from the ROM window, checks MAGIC and writes CONTROL.run_request.
3. The power sequencer holds cartridge /RESET, enables 5 V, then the interface rail.
4. The SNES CIC lock starts on its own clock, and the [ROM-header probe](header-region-probe.md) reads `$00:FFC0-$00:FFDF` while the cartridge is still held in /RESET. The region is decided in priority order: forced mode, a passing key's type, a valid ROM header, NTSC default (also after the 300 ms timeout).
5. `snes_clk_run` starts the SNES master at that region's frequency. It never changes while it runs; see the [clock plan](clock-plan.md). It starts only after `sn64_clock_init` has retargeted Si5351 CLK2 (MS2 + register 18) for the latched region (`pixel_clock_ready`); the HDMI pixel domain is held in reset until then.
6. After 1 ms of running clock the sequencer releases /RESET and grants bus permission; the core leaves reset.

Socket /RESET is owned by the sequencer and the bus permission only. A soft reset (CONTROL bit 1) holds /RESET without removing cartridge power. Dropping run_request, a host reset or a fault shuts the cartridge down and stops the SNES clock.

## System simulation

`tb_system.sv` models an N64 host on the PI bus, a Si5351 I²C slave that records the registers the FPGA writes, cartridge rails that follow their enables, a ROM/SRAM cartridge that drives D0–D7 only while selected and /RD is low, a cartridge with or without a key CIC (the behavioural D411/D413 key model from tb_snes_cic_lock.sv, +pal_key/+ntsc_key), an optional ROM header (+pal_header/+ntsc_header) and an I2S cartridge-audio ADC. The SNES clock exists only while `snes_clk_run` is high and runs at the PAL or NTSC master period for the latched region; the HDMI pixel clock follows the CLK2 source programmed into the Si5351 model (PLLA 39/31 NTSC, PLLB 108/85 PAL). It checks, every clock, that the socket is never driven without permission, that the SNES clock never runs without cartridge power, that the region never changes while it runs, that /RESET is held until it runs, and that the Si5351 is never accessed while the SNES clock runs; at SNES clock start CLK2/MS2 must match the region. It then requires the SNES program to write its proof-of-life byte, read the controller image the N64 sent via auto-joypad (`$4218/$4219`), and the N64 to read STATUS showing RUN. Every run also checks that the audio at `sn64_av_out` equals sat16(DSP + ADC word) once the mixer is primed and that the N64 reads REGION_INFO/REGION_SOURCE matching the decision.

Result (round-3 integration run, 2026-09-29, `evaluate.py --mode sim`): **PASS** in all four positive runs.

| Run | Region / source | STATUS | REGION_INFO / SOURCE | Mixed audio samples | HDMI |
|---|---|---|---|---:|---|
| default (no key, no header) | NTSC default | `0x545F` | `0x1600` / `0x0007` | 2,108 | 858x524 VIC 2, lock reported only (re-phases every frame, -1,328 px) |
| +pal_header | PAL via ROM header | `0x54DF` | `0x7002` / `0x0016` | 2,466 | 864x624 VIC 17 frame-locked (lock errors 0 0 0 px after one start-up re-phase) |
| +pal_key +ntsc_header | PAL via key CIC | `0x34DF` | `0x3001` / `0x0015` | 2,466 | 864x624 VIC 17 frame-locked (0 0 0 px) |
| +ntsc_key +pal_header | NTSC via key CIC | `0x345F` | `0x7002` / `0x0005` | 2,108 | 858x524 VIC 2, lock reported only |

With +corrupt_key (one key bit flipped in round 1) the header decides and the run fails as required. The bench uses REGION_TIMEOUT_MS = 20 because the key's first round, including its table update, ends about 9.1 ms after the interface rail.

Finding fixed: the bridge pulled socket /RESET while the core was in reset, and the core reset followed the socket /RESET level, so neither could leave reset. Only the sequencer and bus permission now drive /RESET.

Limits: the PAL runs use a PAL-rate master and a pixel clock at exactly master x 108/85 in simulation time units, not the real frequencies; NTSC HDMI frame lock is reported, not checked (open decision 9); no N64 CIC exchange (covered by its own bench), behavioural rails, cartridge and ADC, representative PI timing.

## Whole-design synthesis

`sn64_top` with every block (SNES core, bridge, N64 endpoint and CIC, SNES CIC lock, controllers, power sequencer, clock start-up, CDC) synthesises for ECP5 with the pinned OSS CAD Suite in 45 s: **28,813 LUT4 (34 % of the 85F), 12,038 FF, 19 MULT18X18D and 205 of 208 DP16KD**; final netlist check reports 0 problems (log `build/sn64-top-synth.log`, untracked). The block-RAM figure includes the 64 blocks of the 64 K-word bootstrap ROM window and confirms that the ROM cannot stay in block RAM once A/V buffering is added. 
A first full place-and-route used [sn64_pnr_wrap.sv](../../fpga/rtl/sn64_pnr_wrap.sv), which keeps every board interface as a pin, ties off the simulation-only ROM load port and XOR-reduces the SNES video/audio outputs into pins so the PPU/APU logic is not optimised away. nextpnr-ecp5 (85F, CABGA381, speed 6, placer-chosen pins, 208 s) **met all three clocks**: SNES master 28.36 MHz achieved vs 21.48 MHz required (+32 %), host 87.11 MHz vs 62.5 MHz, housekeeping 61.97 MHz vs 25 MHz; 117 of 365 I/O sites, 141 of 208 DP16KD (the unwritten bootstrap ROM is removed in this run, consistent with moving it to flash), 19 multipliers. Cross-domain paths are synchronised by design and not timed; pins are not the final allocation, and the A/V block was not yet included.

## Open integration decisions

Status 2026-09-29 (round-3 integration):

1. **Bootstrap ROM storage: resolved.** The ROM window is served from the FPGA configuration flash ([bootrom-flash.md](bootrom-flash.md), SummerCart64 `memory_flash.sv` unmodified, `ROM_FROM_FLASH=1` in the board top). This frees 64 DP16KD. Flash part selected on the FPGA sheet: W25Q128JVSIQ (QE factory-fixed 1, EBh 2 mode + 4 dummy clocks, tCLQV 6 ns; [fpga-schematic.md](fpga-schematic.md)); the MASTER_SPI_PORT default is DISABLE, so CSSPIN/D0-D3 are GPIO in user mode (TN-02039 Table 7.1). Still open: the programmer offset, the menu rule that PI DOM1 LAT stays at the header's 0x40, and the USRMCLK/board round trip against the 30 ns budget (about 24 ns left after tCLQV).
2. **Board wrapper and real pinout: done** ([sn64_board_top.sv](../../fpga/rtl/sn64_board_top.sv), [sn64_board.lpf](../../fpga/constraints/sn64_board.lpf), [fpga-schematic.md](fpga-schematic.md)). The board top now has the pad adapters the schematic needs (cart_data one inout pad per bit, open-drain si_scl/si_sda, cart_reset_pull_n, expand_sense, reserved n64_si_dq/n64_int_n/hdmi_hpd/hdmi_scl/hdmi_sda, adc_*). Routed with the real LPF below. Still open: board-level I/O timing (cartridge setup/hold, N64 PI, flash), the -8BG381I alternate at speed 8.
3. **A/V output:** HDMI 720x480p (NTSC) and **PAL 720x576p50** (864x624, VIC 17, pixel = PAL master x 108/85 from PLLB) simulated, see [clock-plan.md "PAL HDMI"](clock-plan.md). **Cartridge analog audio implemented** ([cart-audio-implementation.md](cart-audio-implementation.md)). Board path drawn in [av-clock-schematic.md](av-clock-schematic.md) (PCM1808 I2S master, 32 kHz; TPD12S016 HDMI companion) and attached to the root. Open: NTSC frame lock (decision 9) and the DSP sample rate (decision 8).
4. **ROM header region fallback: implemented** ([header-region-probe.md](header-region-probe.md)), tested alone and in `tb_system` with an EU header (PAL) and without a header (NTSC).
5. **Place-and-route:** the board top routes on the real pinout; see below.
6. **CIC data pin circuit: resolved.** Schematic rev 0.3.1 gives each CIC data pin its own SN74LVC1T45 with a dedicated DIR pin and pull-downs ([cart-interface-schematic.md](cart-interface-schematic.md)). [sn64_cic_pad.sv](../../fpga/rtl/sn64_cic_pad.sv) sequences DIR against the pad drive; [tb_cic_pad.sv](../../fpga/tests/tb_cic_pad.sv) checks it against a translator model, and a fault build that switches both together is rejected.
7. **Header telemetry: done.** REGION_INFO (0x1A) and REGION_SOURCE (0x1C) in the mailbox, shown by the menu ([header-region-probe.md](header-region-probe.md#telemetry)).
8. **SNES DSP sample rate: resolved.** `prepare_core.py` restores the original 409600 with a region-correct CE divider (MiSTer behaviour): 32,000 Hz in both regions ([cart-audio-implementation.md](cart-audio-implementation.md)).
9. **NTSC HDMI frame lock: resolved.** Root cause was a SNESTang translation bug (long dots never taken, 1360-clock lines); the generated core now has hardware-length 1364-clock lines, NTSC MS2 = 31 + 14887/18733 locks one HDMI frame to the mean SNES frame, PAL MS2 = 31 + 31/54; `tb_system` checks frame lock in both regions ([clock-plan.md](clock-plan.md)).
10. **efuse_fault_n: resolved.** Pulled up to FPGA_3V3 like every other monitor output (the 5V_PRE divider would back-drive a non-hot-socket bank); `verify_fpga_sheet` 13/13.
11. **Cartridge enable pull-ups: resolved.** R206-R208 changed to 4.7k (ECP5 configuration-time pull-down up to 150 uA, DS-02012 Table 3.7).
12. **FPGA-sheet regulator input: accepted.** The FPGA bucks take 5V_PRE because a buck cannot make 3.3 V from the host's 3.3 V input ([power-schematic.md](power-schematic.md)).
13. **Console video path (primary A/V, owner decision 2026-09-29): to implement.** Frame and audio window for the N64 over the cartridge bus (PI domain 2, fast timing) plus the boot program's display loop; the board's own HDMI becomes the secondary validation output. Design and numbers in [console-video-path.md](console-video-path.md).

## Place-and-route with HDMI (2026-09-29)

Reproduce with `python fpga/tools/route_top.py` (OSS CAD Suite on PATH; writes `build/route-top/summary.json`). Synthesis loads the ECP5 cell library and defines `VERILATOR` (core memory branch) and `SN64_SYNTH` (real ODDRX1F in the HDMI serializer). The trial constraints [fpga/constraints/sn64_trial.lpf](../../fpga/constraints/sn64_trial.lpf) set all five clock frequencies and borrow the ULX3S HDMI pins (same 85F CABGA381 package) because DDR outputs need fixed PIOs; every other pin is placer-chosen.

| Clock | Required | Achieved (grade 6) |
|---|---:|---:|
| SNES master | 21.48 MHz | 28.54 MHz |
| Host (N64 endpoint, CIC) | 62.5 MHz | 84.25 MHz |
| Housekeeping | 25 MHz | 61.40 MHz |
| HDMI pixel | 27.02 MHz | 56.60 MHz |
| HDMI TMDS bit clock | 135.1 MHz | 317.36 MHz |

Resources: 29,224 LUT4 / 33,899 TRELLIS_COMB (40 %), 12,910 FF (15 %), 143 of 208 DP16KD, 20 MULT18X18D, 4 ODDRX1F, 122 I/O. The bootstrap ROM block RAM is not counted (its load port is tied off and it is being moved to flash). Cross-domain paths are synchronised by design and excluded; this is internal feasibility, not a board timing sign-off.

## Board top place-and-route with real clock primitives (2026-09-29)

Reproduce with `python fpga/tools/route_top.py` (default `--top board`; writes `build/route-board/summary.json`). This routes [sn64_board_top.sv](../../fpga/rtl/sn64_board_top.sv): the clocks now come from pins through the real ECP5 primitives (two EHXPLLL, one DCSC), the bootstrap ROM is served from the configuration flash through USRMCLK, and the CIC data pads have their DIR sequencing. Constraints: [sn64_board_trial.lpf](../../fpga/constraints/sn64_board_trial.lpf) (clock frequencies on the four clock pins; ULX3S sites for the oscillator, HDMI and flash pins; everything else placed by the tool). nextpnr-ecp5, 85F, CABGA381, speed grade 6:

| Clock | Required | Achieved |
|---|---:|---:|
| SNES master (after the DCSC) | 21.48 MHz | 27.30 MHz |
| Host, from PLL (N64 endpoint, CIC, flash) | 62.5 MHz | 82.90 MHz |
| Housekeeping, 25 MHz oscillator | 25 MHz | 61.46 MHz |
| HDMI pixel (Si5351 CLK2) | 27.02 MHz | 62.50 MHz |
| HDMI TMDS bit clock, from PLL | 135.1 MHz | 320.20 MHz |

Resources: 34,773 TRELLIS_COMB (41 %), 13,342 FF (15 %), **143 of 208 DP16KD** (the bootstrap ROM no longer uses block RAM), 20 MULT18X18D, 2 of 4 EHXPLLL, 1 of 2 DCSC, 121 I/O. nextpnr derived the SNES clock constraint through the DCSC by itself and promoted all five clocks to the global network. Cross-domain paths are synchronised by design and are not timing-checked; the SNES domain's worst reported cross-domain path is 24.5 ns. This is a feasibility result on a trial pinout: the real pin assignment, I/O standards and board timing come with the FPGA schematic sheet.

## Board top on the real pinout (round 3, 2026-09-29)

Reproduce with `python fpga/tools/route_top.py` (OSS CAD Suite on PATH). `--top board` now defaults to [fpga/constraints/sn64_board.lpf](../../fpga/constraints/sn64_board.lpf), the pinout generated with the FPGA schematic sheet; the older trial pinout stays selectable with `--lpf fpga/constraints/sn64_board_trial.lpf` (it only matches the pre-round-3 port names), and `--top-file` routes a candidate top without replacing the tracked one. The synthesis list gained `sn64_i2s_rx.sv` and `sn64_audio_mix.sv`. The board top includes the PAL HDMI and cartridge-audio edits of this round; `si_clk2` is constrained at the faster PAL pixel clock, 27.0399 MHz (the TMDS PLL dividers are unchanged, VCO 540.8 MHz in PAL).

nextpnr-ecp5, LFE5U-85F, CABGA381, speed grade 6, exit 0 (synthesis + route 4 min 44 s; logs in `build/r3-integ/route-board/`, untracked):

| Clock | Required | Achieved |
|---|---:|---:|
| SNES master (after the DCSC) | 21.48 MHz | 28.94 MHz |
| Host, from PLL (N64 endpoint, CIC, flash, I2S receiver) | 62.5 MHz | 86.26 MHz |
| Housekeeping, 25 MHz oscillator | 25 MHz | 53.12 MHz |
| HDMI pixel (Si5351 CLK2) | 27.04 MHz | 38.69 MHz |
| HDMI TMDS bit clock, from PLL | 135.21 MHz | 170.85 MHz |

Resources: 36,503 TRELLIS_COMB (43 %), 13,627 FF (16 %), 143 of 208 DP16KD, 20 MULT18X18D, 2 of 4 EHXPLLL, 1 of 2 DCSC, 1 USRMCLK, **121 of 365 I/O on the constrained balls**. Every clock passes after routing (the post-placement estimate for the TMDS clock, 127.8 MHz, was below target before routing). This is internal timing on the real pins; board-level I/O timing (cartridge setup/hold, N64 PI, flash round trip) is not analysed yet.

## Schematic integration (round 3, 2026-09-29)

The root [sn64.kicad_sch](../../hardware/sn64/sn64.kicad_sch) (rev `0.4-r3`, now A2) holds all five child sheets: USB-C programmer (page 2), SNES cartridge interface (3), FPGA (4), Power (5), clock/HDMI/cartridge audio (6). Every sheet pin carries a same-name root label, so the shared net-name contract is wired by name; no root no-connect remains on a sheet pin. The cartridge sheet's FPGA-side pins lost their no-connect markers; the USB sheet now exports USB_VBUS, USB_3V3, USB_CC1/CC2, jtag_tck/tms/tdi/tdo and TARGET_VREF (its local JTAG labels were renamed to the contract's lower case), and R101/R102 are DNP because the power sheet's TUSB320 (U301) presents Rd. The sheets were attached with the agents' own attach scripts, then the power and A/V blocks were moved right of the FPGA sheet (the agents' positions overlapped). The integration script is kept as untracked evidence in `build/r3-integ/tools/integrate_root.py`.

Integration fixes (each found by ERC or a validator on the integrated root):

- **Duplicate reference designators.** The FPGA and power sheets both used U301-U307, R301-R319, C301-C340, TP301-TP308 and #FLG301-#FLG304 (about 80 clashes). The FPGA sheet was renumbered to 4xx (its page number) in its generator, [add_fpga_sheet.py](../../hardware/sn64/tools/add_fpga_sheet.py), and regenerated; its verifier and [fpga-schematic.md](fpga-schematic.md) follow. Examples: ECP5 U401, PROGRAMN gate U407, TARGET_VREF link R414, N64 bus switches U402-U404.
- **Duplicate PWR_FLAGs** (5 ERC errors): FPGA_1V1/2V5/3V3 are flagged on the power sheet, 5V_PRE is driven by the TPS63070 power output, so #FLG401-#FLG403 (FPGA sheet) and #FLG701/#FLG702 (A/V sheet) were removed as those agents asked. #FLG404 (FPGA_VCCAUX after FB401) and #FLG703 (ADC_VCC_5V after FB701) stay. #FLG103 (TARGET_VREF) also stays, because TARGET_VREF is fed through the 0-ohm R414, a passive part.
- **Validators written for unattached sheets.** The cartridge, A/V, power and FPGA verifiers assumed FPGA-side nets had no other members. They now accept exactly one ECP5 ball on each contract net, root-named FPGA-side nets, the A/V sheet's passive input network on the socket audio lines, and an extra default-low pull-down on `fpga_rails_ok` only if the divided high level still meets VIH (R361 10k up, R415 100k down: 3.0 V). The FPGA 5 V-reachability walk no longer walks through GND, and the JTAG check now also rejects an opposite-direction pull, which the USB sheet's parallel bias resistors would otherwise have masked. Every negative test still detects all its faults.

Checks on the integrated real root (KiCad 10.0.6):

| Check | Result |
|---|---|
| ERC | **0 errors**; 10 warnings: 5 `isolated_pin_label` (reserved N64 edge labels: N64_AUDIO_L/R, N64_KEY1/KEY2_RESERVED, N64_VIDEO_SYNC_RESERVED), 5 `pin_to_pin` (cart U206 unused B4-B8 tied to the flagged GND, unchanged from before) |
| verify_interfaces.py | 30/30 |
| verify_usb_programmer.py | 69/69 (the CC check now requires DNP R101/R102; new: CC to TUSB320, VBUS to the power sheet, USB_3V3 powers U301, JTAG to the ECP5 dedicated balls, TARGET_VREF from FPGA_3V3 through R414); fault injection (R101 fitted, jtag_tck label broken) fails as required |
| verify_cart_interface.py | 20/20, 62/62 J2 contacts; negative test 6/6 |
| verify_fpga_sheet.py | **12/13**: fails only `no_5V_12V_or_VBUS_net_reaches_any_FPGA_ball` on `efuse_fault_n` (open decision 10); negative test 10/10 |
| verify_power_sheet.py | 23/23; negative test 11/11 |
| verify_av_clock_sheet.py | 30/30; negative test 12/12 |
| [verify_root_connectivity.py](../../hardware/sn64/tools/verify_root_connectivity.py) (new) | 4/4: hierarchical labels match sheet pins, every sheet pin labelled at the root, every pin has a partner, all 141 contract names (63 cartridge-sheet names + 78 others) are one net touching every sheet they must connect; negative test 4/4 |

The PDF export ([sn64-interface-draft.pdf](../../hardware/sn64/exports/sn64-interface-draft.pdf)) was regenerated; it was **not visually inspected** (no rasteriser on this machine). A geometric check found no overlapping sheet symbols and no root label running into a sheet body on the A2 page.

