# N64/M64 host endpoint: implementation and evidence

Implemented 2026-09-29. This is the logic that makes SN64 look like an N64 cartridge to the console: the boot ROM window the console reads its bootstrap program from, and the mailbox the bootstrap uses to pass controller input to the SNES side and read status back. It passes a host-model simulation. **It has not run on hardware.** The [host interface notes](n64-interface-notes.md) remain the pin-level reference.

## Plain-language summary

When an N64 or M64 powers on, it reads a program from the cartridge and runs it. For SN64 that program is a small **menu/bootstrap** (settings, controller mapping, diagnostics). This endpoint provides two things the bootstrap needs: a memory window it boots from, and a set of registers (the "mailbox") through which it sends button presses to the SNES core and reads back power and fault status. The bus-protocol part is copied unmodified from SummerCart64, an open-source N64 flash cartridge that already works on real consoles, so the riskiest piece is proven.

## Files

| File | Role |
|---|---|
| [fpga/vendor/summercart64/](../../fpga/vendor/summercart64/provenance.json) | Unmodified SummerCart64 PI controller, FIFO and bus interfaces, GPL-3.0, commit `a1e7996d2cbece686820a5c785029c68514f17b0` |
| [fpga/rtl/sn64_n64_endpoint.sv](../../fpga/rtl/sn64_n64_endpoint.sv) | SN64 wrapper: bootstrap ROM window, mailbox registers, static configuration of the vendored controller |
| [fpga/rtl/sn64_n64_reg_bus.sv](../../fpga/rtl/sn64_n64_reg_bus.sv) | Equivalent of the upstream register-bus interface without the expression modports Verilator rejects; the vendored original is kept but not compiled |
| [fpga/tests/tb_n64_endpoint.sv](../../fpga/tests/tb_n64_endpoint.sv) | Host model driving the PI protocol; run by `evaluate.py --mode sim` |

## What is reused and what is new

The vendored `n64_pi.sv` implements the N64 PI bus: input synchronisation, the ALE_H/ALE_L address latch, read/write strobe detection, 16-bit multiplexed AD bus direction control, read/write FIFOs and address decoding. SN64 configures it statically (through `n64_scb`) as a plain ROM cartridge with registers unlocked: no SRAM/FlashRAM/64DD emulation, no bootloader window, no ROM writes.

New SN64 logic:

- **Bootstrap ROM window** at N64 address `0x1000_0000`, the ordinary cartridge-ROM range the console boots from. Served from block RAM (`ROM_ADDR_BITS` parameter; 4 KiB words in the test) with a write port for loading the image. The window mirrors the small ROM; the final image size is a bootstrap decision.
- **Frame/audio window** at N64 address `0x0800_0000` (PI domain 2, so the boot program can give it fast timing without touching the flash ROM window): the vendored controller's 128 KiB "SRAM" region, which lands on mem_bus `0x03FE_0000`. Byte offsets `0x00000` = the SNES frame as 240 lines × 256 pixels of RGBA5551 (`line*512 + x*2`), `0x1E000` = the 32 kHz stereo audio ring (1024 pairs, `pair*4`). Written by [sn64_frame_window.sv](../../fpga/rtl/sn64_frame_window.sv) in the SNES clock domain; see [console-video-path.md](console-video-path.md). Mailbox words `0x1E FRAME_STATUS` {frame_count[7:0], lines_done[7:0]}, `0x20 AUDIO_WPTR`, `0x22 VIDEO_MODE` {pal, interlace, high_res, overscan} tell the reader what is ready.
- **Mailbox** at `0x1FFF_0000`, SummerCart64's register range, so its unlocked-register convention carries over to the bootstrap software:

| Offset | Name | Access | Contents |
|---|---|---|---|
| `0x00` | MAGIC | r | `0x534E` ("SN") |
| `0x02` | VERSION | r | `build_id` input |
| `0x04` | STATUS | r | bit 0 configured (Si5351 locked), 1 host+FPGA rails, 2 cartridge 5 V, 3 interface rail, 4 bus permit, 5 fault latched, 6 run request seen, 7 PAL, 11:8 power-sequencer state, 12 SNES clock running, 13 key CIC ok, 14 key CIC fail, 15 clock-chip error (wired in `sn64_top.sv`) |
| `0x08` | FAULT | r | `{fault_code, 8'h00}` from the power sequencer; a latched fault clears when CONTROL.run_request is dropped. Bit 8 (fault code `0x01`): cartridge check failed in enforce mode |
| `0x0A` | CART_CHECK | r | result of the last cartridge check ([reversed-cartridge-detection.md](reversed-cartridge-detection.md)): bit 15 done, 14 pass, 13:12 mode used, 8 this build has the check, 7:0 rail reading (9.67 mV per count). Kept after the request is dropped; cleared when the next request starts |
| `0x06` | SEQ | r | increments on every COMMIT |
| `0x10` | JOY1_BUTTONS | r/w | SNES button image for controller 1 |
| `0x12` | JOY2_BUTTONS | r/w | SNES button image for controller 2 |
| `0x14` | JOY1_STICK | r/w | `{y, x}` analog stick, retained for the deferred virtual mouse |
| `0x16` | CONTROL | r/w | bit 0 `run_request` (cartridge power and run); bit 1 soft reset ("reset SNES": holds /RESET, keeps cartridge power); bits 3:2 region mode (0 auto, 1 NTSC, 2 PAL; applied at the next cartridge power-up, never live); bits 5:4 cartridge check mode (0 enforce, 1 report only, 2 off, 3 check only; taken when a request starts; back to 0 on host reset) |
| `0x18` | COMMIT | w | any write increments SEQ after a complete controller update; reads 0 |
| `0x1A` | REGION_INFO | r | ROM-header probe result ([header-region-probe.md](header-region-probe.md)): bits 7:0 country byte (`$FFD9`), 11:8 reject `{unstable, checksum, map, country}`, 12 done, 13 valid, 14 PAL, 15 aborted. Snapshot taken on the clk_25 edge that starts the SNES clock, kept until the next cartridge start; live probe state before the first decision. Writes ignored |
| `0x1C` | REGION_SOURCE | r | bits 1:0 decision source (0 forced by CONTROL, 1 key CIC, 2 ROM header, 3 NTSC default, i.e. no passing key and no valid header, or the region timeout); 2 decided (the fields describe the last cartridge start); 3 region timeout had expired; 4 decided region is PAL; 15:5 zero. Writes ignored |

`REGION_INFO` and `REGION_SOURCE` are produced in the clk_25 domain by `sn64_top` and cross to the host clock as one 32-bit `sn64_cdc_word`, so both halves always come from the same snapshot. The bootstrap reads them as the 32-bit pairs `0x18 = {COMMIT (reads 0), REGION_INFO}` and `0x1C = {REGION_SOURCE, 0x1E reserved}`. Offsets `0x00`-`0x18` are unchanged.

`run_request` is cleared by hardware whenever the host asserts reset: the bootstrap must re-request cartridge power after every console reset, in line with the default-off principle in the [power architecture](power-architecture.md). `run_request` is an input to the hardware permission chain, not the permission itself; the hardware veto still applies.

## Verification

`tb_n64_endpoint.sv` models the console side of the PI bus: `{ALE_H, ALE_L}` sequence `11 → 01 → 00` (HIGH, LOW, VALID) with each state held ≥ 300 ns, then `/READ` or `/WRITE` pulses of ~400 ns on the multiplexed AD lines. It checks that the endpoint never drives AD while the host drives or more than a few clocks after `/READ` rises, and verifies:

1. burst ROM reads from `0x1000_0000` return the loaded words, and an offset read returns the right word;
2. mailbox reads return MAGIC, VERSION and STATUS;
3. mailbox writes reach `joy1_buttons`, `joy2_buttons`, the stick, `run_request` and increment SEQ, and read back;
4. host reset clears `run_request`;
5. (2026-09-29) `REGION_INFO`/`REGION_SOURCE` read back at `0x1A`/`0x1C` (also as the bootstrap's pairs at `0x18` and `0x1C`), follow their inputs, ignore writes, and the COMMIT pair write `{0x18, 0x1A}` increments SEQ exactly once.
6. (2026-10-01) the cartridge check mode in `CONTROL` bits 5:4 reaches `cart_check_mode`, reads back, and returns to 0 on host reset; `CART_CHECK` reads at `0x0A` as the low half of the bootstrap's pair at `0x08`. With these the bench passes in 5,145 master clocks.

Result: **PASS, 4,953 master clocks** (4,595 before the REGION registers were added). Fault build `+define+SN64_FAULT_REGION_SWAP` (the two words swapped in the decode) **fails as required**: `REGION_INFO/REGION_SOURCE read wrong: 0000 0016 7e02 0000`. Both are part of `evaluate.py --mode sim`. The whole path (header probe and key CIC in clk_25 → `sn64_cdc_word` → mailbox → N64 read) is checked by `tb_system` in four runs; see [system-integration.md](system-integration.md). Two host-model errors were found and fixed while writing the bench (ALE states held too briefly for the controller's three-stage synchroniser, and ALE_H/ALE_L dropped in the wrong order); both were in the test, not the design, and are recorded here because the same mistakes would matter in a bootstrap or fixture.

Limits: the host model's timing is representative, not measured N64 or M64 timing. Two-state simulation cannot show electrical contention on AD; the bench uses the controller's output enable. No CIC, SI/joybus, /INT or DMA-boundary behaviour is exercised.

## Synthesis

`sn64_n64_endpoint` synthesizes for ECP5 with the pinned OSS CAD Suite at **499 LUT4, 266 FF, 4 DP16KD** (4 KiB-word bootstrap ROM; log `build/n64-synth.log`, not tracked). Negligible against the console core's budget.

## Still open

1. **CIC lockout.** SummerCart64's CIC runs on a soft RISC-V core with a firmware image; adopting it means vendoring the core (`serv`) and building the image. Without a valid CIC response an original N64 will not boot the cartridge. This is the next endpoint task.
2. **SI/joybus.** Not needed while the bootstrap reads controllers through the console's own PIF and forwards them through the mailbox; revisit only if EEPROM emulation or direct joybus access becomes necessary.
3. **/INT** to the host and the exact IRQ electrical mode (see the [host interface notes](n64-interface-notes.md)).
4. **Bootstrap program:** first version implemented, see [n64-bootstrap.md](n64-bootstrap.md). The N64 CPU accesses these registers only as 32-bit pairs (0x00, 0x04, 0x08, 0x10, 0x14, 0x18, 0x1C); a write to 0x18 also writes 0x1A (REGION_INFO, read-only), which is ignored, so SEQ increments once per COMMIT. The menu shows the region and its source on the main screen and the header probe result on the status screen. The image needs a 64 K-word window (`ROM_ADDR_BITS = 16`); where that ROM lives (block RAM, configuration flash or external RAM) is an open decision in the [integration notes](system-integration.md).
5. Board-level: 3.3 V I/O bank allocation, host-first/adapter-first power sequencing, and measured PI timing on both consoles.
