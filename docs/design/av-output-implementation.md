# Digital A/V output: implementation and evidence

Implemented 2026-09-29. This is the first version of the independent digital video and audio output required by SN64-07-01. It sends the SNES core's picture and sound out as HDMI with embedded 32 kHz audio: 720×480p for NTSC, and 720×576p50 for PAL (added the same day, see [PAL 576p50](#pal-576p50-2026-09-29)). It passes a simulation that decodes the serial TMDS output bit by bit. **It has not been shown on a display and has not run on hardware.**

## Plain-language summary

The SNES draws 60 pictures a second, one line at a time, on its own clock. That clock must stay exactly right because real cartridges run from it. HDMI also sends pictures a line at a time, but on its own faster pixel clock. The output block sits between the two.

Each SNES line is copied into a small four-line store as it is drawn. The HDMI side sends each stored line twice (line doubling), about one and a half SNES lines later, so 224 lines become 448 on a 480-line screen. The HDMI clock is made from the SNES clock at an exact ratio, so one SNES line lasts exactly two HDMI lines and one SNES frame exactly one HDMI frame. The two sides therefore never drift apart. Nothing is ever torn, dropped or repeated, and no full-frame memory is needed.

Once per frame the block checks that the HDMI side is still in step. If it is not (at start-up, after a change of picture height, or if the board clocks the HDMI side from a separate crystal), it corrects the HDMI timing during the blank lines below the picture. Sound samples are sent at the rate the core produces them, and the TV is told that rate, so no audio is dropped or repeated.

A PAL SNES draws 50 pictures a second with 312 lines each. For PAL the same block sends 720×576 at 50 Hz: each of the 312 SNES lines becomes two of the 624 HDMI lines. The clock chip is set, before the SNES clock starts, to a pixel clock made from the PAL master clock at an exact ratio, so PAL is locked in the same way.

## Files

| File | Role |
|---|---|
| [fpga/rtl/sn64_av_out.sv](../../fpga/rtl/sn64_av_out.sv) | Top level: SNES-side capture, 4-line ring buffer, frame-locked HDMI raster (NTSC 858×524 or PAL 864×624, chosen by `pal` during reset), audio clock-domain crossing, status |
| [fpga/rtl/sn64_av_hdmi_tx.sv](../../fpga/rtl/sn64_av_hdmi_tx.sv) | HDMI period scheduler (video, control, data islands) for an externally supplied raster, in either mode; instantiates the vendored packet and TMDS modules, plus a second vendored AVI InfoFrame for VIC 17 |
| [fpga/rtl/sn64_av_serializer.sv](../../fpga/rtl/sn64_av_serializer.sv) | 10:1 serializer on ECP5 `ODDRX1F` (three data lanes plus TMDS clock); behavioural DDR model under `VERILATOR` |
| [fpga/vendor/hdl-util-hdmi/](../../fpga/vendor/hdl-util-hdmi/provenance.json) | Vendored hdl-util/hdmi packet, ECC, InfoFrame, audio and TMDS encoder modules, with MIT and Apache-2.0 licence texts |
| [fpga/tests/tb_av_out.sv](../../fpga/tests/tb_av_out.sv) | SNES timing and pattern model (NTSC, or PAL with `SN64_TB_PAL`), serial TMDS deserializer and full HDMI decoder including AVI InfoFrame VIC/aspect/checksum, self-checking |

## What is reused

SNESTang ([design notes](../../references/downloads/snestang/design.md), archive `5f0ef193…`) drives HDMI with `src/snes2hdmi.v` plus a copy of [hdl-util/hdmi](https://github.com/hdl-util/hdmi) by Sameer Puri in `src/hdmi2/`. A diff against hdl-util at `83b1c9543a91b776671a44e68e130f81cae437b7` shows:

- Six files are byte-identical upstream: `tmds_channel.sv`, `packet_assembler.sv`, `audio_sample_packet.sv`, `audio_info_frame.sv`, `auxiliary_video_information_info_frame.sv` and `source_product_description_info_frame.sv`.
- `packet_picker.sv` and `audio_clock_regeneration_packet.sv` carry a SNESTang change: `clk_audio` is edge-detected inside the pixel clock domain rather than used as a clock. SN64 needs exactly that, so these two come from SNESTang.
- `serializer.sv` differs only by a Gowin define; `hdmi.sv` is identical.

Licences: hdl-util is MIT OR Apache-2.0. Both texts are retained, and both licences are compatible with GPL-3.0-or-later. The SNESTang change falls under SNESTang's GPL-3.0 repository licence. Provenance with per-file SHA-256 is in `fpga/vendor/hdl-util-hdmi/provenance.json`. SN64 made two tool-compatibility edits, each marked in the file and recorded there:

- `$rtoi`/`$itor` instead of `int'()` on reals, so Verilator 5.053 can constant-fold the ACR counter width.
- A single non-blocking update of the IEC 60958 frame counter, because yosys-slang rejects mixed blocking and non-blocking assignment.

Not reused:

- **`hdmi.sv`.** Its raster counters are internal and its frame is fixed at 525 lines. SN64 needs an externally locked 524-line raster, so `sn64_av_hdmi_tx.sv` re-implements the scheduler with the same period arithmetic, with attribution.
- **`serializer.sv`.** It has no ECP5 path.
- **SNESTang's `snes2hdmi.v`.** It scales ×3 to 720p through a 16/32-line buffer. It keeps the two sides in step with `pause_snes_for_frame_sync`, which stops the SNES mid-line, and it runs the SNES clock slightly fast to match 74.25 MHz. Both violate SN64's fixed-master-clock rule: real cartridges see the master clock and the CPU cycle timing. Its audio path resamples to a pixel-derived 32 kHz through a FIFO, so it drops or repeats samples whenever the rates differ.

## Buffering decision: line buffer with frame lock

EBR budget: the core uses 139 of 208 DP16KD, leaving 69. One DP16KD holds 1,024 × 18 bits.

| Option | EBR | Tearing / frame cadence | Verdict |
|---|---|---|---|
| Single frame buffer, 256 × 239 × 15 bit | 60 | Tears. The two frame rates differ by 0.16–0.26 % (60.0988 Hz SNES vs 59.94/60.00 Hz 480p), so the tear line sweeps the picture about every 4–10 s | Uses 87 % of what is left and still tears |
| Double buffer, 256 × 239 | 120 | Tear-free, but drops a frame every ~4–10 s (visible stutter in scrolling) | Does not fit |
| Any frame buffer at 512 wide (hi-res) | ×2 of the above | — | Does not fit |
| **4-line ring, 512 half-dots × 15 bit, raster locked to the SNES frame** | **2** | No tearing, no dropped or repeated frames, ~1.5 SNES lines (≈95 µs) latency | **Chosen** |

The lock depends on the HDMI raster having exactly the SNES frame period. The ratio is fixed by clocking, and a per-frame correction guards it (see below). This is the same principle as a line-locked scan doubler.

## Output format and clocking

- **Mode (NTSC; PAL is in [PAL 576p50](#pal-576p50-2026-09-29)).** CEA-861 VIC 2 (720×480p, 4:3) timing with **V total 524 instead of 525**, so the frame is exactly two HDMI lines per SNES line (262 × 2). Horizontal: 720 active, 16 front porch, 62 sync, 60 back porch, 858 total. Vertical: 480 active, 9 front porch, 6 sync, 29 back porch. Syncs are negative. The AVI InfoFrame declares VIC 2 with IT content and full-range RGB.
- **Pixel clock = master × 39/31 = 27.0198 MHz.** That is +0.073 % from 27.000 MHz, inside HDMI's ±0.5 % pixel-clock tolerance. At this ratio 1364 master clocks = 2 × 858 pixels exactly, and the frame rate is 60.0988 Hz.
- **Why 720×480 rather than 640×480.** 858/682 = 39/31 needs only the prime 31 in a PLL reference divider. 640×480 (800 total) needs 400/341 = 400/(11·31) and so three cascaded PLLs.
- **PLL chain.** Checked with `ecppll` from the pinned OSS CAD Suite; it enforces PFD ≥ 3.125 MHz and VCO 400–800 MHz. The master clock is only an input and is never modified.
  - PLL 1: 21.4772727 MHz, REF 1 / FB 5 / OP 6, VCO 644.3 MHz → 107.386 MHz.
  - PLL 2: 107.386 MHz, REF 31 (PFD 3.464 MHz) / FB 39 / OP 4, VCO 540.4 MHz → **135.099 MHz (5× TMDS)**, and CLKOS ÷20 → **27.0198 MHz pixel**.

  The LFE5U-85F has four PLLs; together with the 62.5 MHz CIC PLL this uses three. The 3.46 MHz PFD sits near the minimum, so jitter must be measured.
- **Conflict with the [clock plan](clock-plan.md).** That plan makes 27/135 MHz with ECP5 PLL B from the 25 MHz oscillator, while the Si5351 has its own crystal. The two domains are then asynchronous (27 MHz / 21.477 MHz = 44/35 nominal, plus crystal ppm). The design still works that way: `SN64_TB_ASYNC_27M` below re-phases every frame and passes all pixel and cadence checks. The cost is one shortened back-porch line per frame (about 339 pixels short), which is non-uniform timing that some sinks may not accept. Recommendation: derive the HDMI clocks from the SNES master as above. See "Shared-file changes" in the hand-off.

### Frame lock (`sn64_av_out.sv`)

1. **SNES side.** On each VDE rise it starts counting HDE rises. At the HDE rise of SNES line 250 it toggles an event. It also latches the visible-line count (224 or 239) at each VDE fall.
2. **Pixel side.** It synchronises the toggle (2 flip-flops plus edge detect) and compares its raster position with the expected one. The expected row is `v_off + 495` (511 for 224-line frames, 496 for 239), which is the back porch after vsync, so a correction never crosses vsync.
3. **Correction.** If the error exceeds `LOCK_TOL` (2 px), the raster is re-phased. This happens only when both the old and the new column are inside the horizontal active span of a blanking line, never inside a data island, preamble or guard band. `rephase_count` counts corrections; `locked` means the last error was under `LOCK_WINDOW` (1024 px).
4. **Placement.** The picture is 512 wide at x = 104..615. Vertically it starts at `v_off = 240 − visible_lines`, so 224-line frames occupy 16..463 and 239-line frames occupy 1..478 (PAL: `v_off = 288 − visible_lines`, see below). `v_off` comes from the previous frame's line count, because the core does not export its overscan bit (`V224_MODE` is unconnected in `sn64_console_candidate.sv`). The first frame after an overscan change is therefore placed with the old offset, and a 224→239 change re-phases by 15 lines once. A visible-line count outside 212..240 is treated as 224. The earlier bound, 200..240, allowed lock targets beyond the last raster line for 200–211-line frames; the core only produces 224 or 239.
5. **Start-up.** The first event after reset re-phases the raster from wherever it was running. That can be in an active line, so up to one active line of the first HDMI frame may be cut short, before any sink could have locked. The bench counts and reports this ("warm-up runs cut by the start-up lock") instead of failing. The PAL run shows one such line in HDMI frame 0; every later correction happens in the back porch.

### Hi-res (512-wide) handling

The core outputs `X_OUT = {dot, DOT_CLK}` and `RGB_OUT` = sub-screen pixel while `DOT_CLK` is high and main-screen pixel while it is low (`ppu.v` lines 2325–2331). The capture always stores all 512 half-dots per line:

- In lo-res both halves are equal, so the HDMI side reading one half-dot per pixel gives an exact 2× horizontal scale.
- In hi-res (modes 5/6, pseudo-hires) each half-dot appears once at 1:1.

No mode switch is needed, and mixed lines in one frame are handled; the testbench alternates them every 8 lines.

Aspect ratio: 512 px in a 4:3 720-wide frame is narrower than a CRT's 8:7 pixel aspect. The CRT-equivalent width is about 644 px (2.52 px per dot). A 2.5× option is an open item.

### Audio

- **SNES side.** Each `audio_ready` rising edge latches L/R and toggles a flag.
- **Pixel side.** It synchronises the flag, copies the stable holding register, and issues a one-clock `clk_audio` strobe to the vendored `packet_picker`. Four samples go per Audio Sample Packet, with IEC 60958 channel status 32 kHz and 16-bit.
- **Rate.** Samples go out at exactly the rate the core produces them, with no resampling FIFO. The ACR packet uses N = 4096, and CTS is measured by hdl-util's counter as pixel clocks per 32 samples, so the sink regenerates the true rate. Expected CTS is 27019.8 with the 39/31 clocks and 27000 with an asynchronous 27 MHz clock.
- **Not covered here.** Cartridge analog audio (pins 31/32) is a separate input path.

### Serializer

`sn64_av_serializer` registers the three 10-bit words at the pixel clock. It detects the pixel edge in the 5× domain (related clocks from one PLL), loads a shift register once every five 5× clocks, and drives two bits per clock through `ODDRX1F`, LSB first. The clock lane sends `0000011111`. In Verilator the primitive is replaced by a behavioural model: D0 while SCLK is high, D1 while low, registered on the rising edge. It is functional only; the real primitive's bit order and output timing must be confirmed at bring-up. Differential I/O (ECP5 LVDS or emulated LVDS, AC coupling or level shifting, ESD, the HDMI 5 V/HPD/DDC lines) belongs to the board top level and is not designed here.

## Verification

Build with the pinned Verilator from the repository root (sources: `fpga/vendor/hdl-util-hdmi/src/*.sv fpga/rtl/sn64_av_hdmi_tx.sv fpga/rtl/sn64_av_serializer.sv fpga/rtl/sn64_av_out.sv fpga/tests/tb_av_out.sv`, top `tb_av_out`, flags `--binary --timing -Wno-fatal -Wno-lint -Wno-style -Wno-TIMESCALEMOD`). Each run simulates 9 SNES frames and takes about 16 s.

**Stimulus.** The SNES model produces 1364 master clocks × 262 lines, 4-clock dots, HDE on dots 19–274, VDE on lines 1–224 for frames 0–3 and 1–239 from frame 4 (one overscan change). The pattern encodes half-dot, line and frame number, with hi-res content on every other 8-line group. Audio samples run at 32000/21477273 per master clock with L = n and R = n XOR 0x5A5A.

**Decoder.** The testbench samples the DUT's serial lanes mid-bit on both edges of the 5× clock and aligns words on the rising edge of the TMDS clock lane. It then decodes control tokens, video guard bands, 8b/10b video, data-island guard bands and TERC4. It rebuilds each 32-clock packet and checks the BCH ECC of the header and all four subpackets.

**Checks, from HDMI frame 1 onward** (frame 0 contains the initial lock):

- Every pixel of 720×480, including borders, against the pattern.
- Picture start line equal to `240 − visible lines`.
- SNES frame numbers consecutive: no drop, repeat or tear.
- Hsync 62 clocks; line period 858; vsync 6 × 858 clocks; 524 lines per frame, except frames with a counted re-phase.
- Exactly 480 video runs of 720.
- Data islands a multiple of 32 clocks; AVI and audio InfoFrames present every frame.
- ACR N = 4096 and CTS in range.
- Every audio sample recovered in sequence with correct L/R pairing.
- Steady-state lock error within ±2 px.

Results (real output, 2026-09-29):

| Build | Define | Result |
|---|---|---|
| `build/verilator-av-out` | — (pixel = master × 39/31) | `PASS: av-out (pixel = master*39/31) 7 frames, 2430720 pixels exact, 720x480 in 858x524, hsync 62, vsync 6 lines, 4792 audio samples in order, ACR CTS 27019..27021, 0 ECC errors, 2 re-phases` (the 2 re-phases are the start-up lock and the 224→239 change; 7 steady-state events all at 0 error) |
| `build/verilator-av-out-async` | `SN64_TB_ASYNC_27M` (27.000 MHz, ratio 44/35) | `PASS: av-out (async 27.000 MHz) 7 frames, 2430720 pixels exact, … ACR CTS 26999..27001, 0 ECC errors, 9 re-phases` (lock error −329 px per frame, corrected in the back porch each frame; frames are 523 lines) |
| `build/verilator-av-out-pixfault` | `SN64_AV_FAULT_PIXEL` (flips one bit of pixel 300,200) | `FAIL: av-out 4 errors`, exit code 1, e.g. `pixel (300,200) got 845239 expected 8c5239` |
| `build/verilator-av-out-syncfault` | `SN64_AV_FAULT_SYNC` (hsync one clock short on line 100) | `FAIL: av-out 8 errors`, exit code 1, e.g. `hsync width 61` |

Rerun after the PAL change (2026-09-29, `build/pal-hdmi/av-*`, same flags). The four builds above give the same results; their PASS lines now also report `VIC 2 aspect 0`. The bench now decodes every AVI InfoFrame (checksum, version/length, VIC, picture aspect). Two builds are new:

| Build | Define | Result |
|---|---|---|
| `build/pal-hdmi/av-pal` | `SN64_TB_PAL` (SNES 1360 × 312, pixel = master × 108/85) | `PASS: av-out (PAL, pixel = master*108/85) 6 frames, 2567520 pixels exact, 720x576 in 864x624, hsync 64, vsync 5 lines, VIC 17 aspect 1, 5688 audio samples in order, ACR CTS 27288..27290, 0 ECC errors, 2 re-phases` (7 steady-state lock events all at 0 error; one warm-up line cut by the start-up lock) |
| `build/pal-hdmi/av-pal-lines-fault` | `SN64_TB_PAL` + `SN64_AV_FAULT_PAL_LINES` (raster 625 lines, the CEA count) | `FAIL: av-out 1 errors`, exit code 1: `frame lock not steady (last lock_error -864, 9 re-phases, 7 of 7 steady events out of tolerance)` |

Limits of this evidence:

- The video source is a model of the core's output timing, not the real PPU. The alignment of `X_OUT` and `Y_OUT` with `HDE` in the real core is assumed from reading `ppu.v`, not simulated.
- The DDR primitive is modelled.
- The pixel→5× transfer is related-clock logic that no timing run has analysed (see Synthesis).
- No HDMI sink was tested. Acceptance of the 524-line, 60.1 Hz variant of 480p is common practice for line doublers but is not verified for any specific display.

## Synthesis

`sn64_av_out` alone, pinned OSS CAD Suite, `read_verilog -lib +/ecp5/cells_bb.v; read_slang …; synth_ecp5` (log `build/av-out-synth.log`, not tracked):

**1,437 LUT4, 972 TRELLIS_FF, 2 DP16KD, 1 MULT18X18D, 4 ODDRX1F** (plus 291 CCU2C, 179 PFUMX, 19 L6MUX21). The MULT18X18D is the constant multiply `sync_y × 858`; it could be replaced with shifts and adds if multipliers run short. With the core this is 141 of 208 DP16KD, leaving 67.

With both raster modes (2026-09-29): **1,475 LUT4, 982 TRELLIS_FF, 2 DP16KD, 1 MULT18X18D, 4 ODDRX1F** (plus 309 CCU2C, 174 PFUMX, 17 L6MUX21). The flow was `plugin -i slang; scratchpad -set abc9.xaiger 1; read_slang -DSN64_SYNTH …; synth_ecp5`, the same as `route_top.py`, with the log in `build/pal-hdmi/synth-av-out.log`. PAL therefore costs about 38 LUT4 and 10 flip-flops. The multiplier is now `sync_y × h_total` with `h_total` 858 or 864. `sn64_clock_init` alone is 327 LUT4 and 157 FF (344 LUT4 with `PAL_LINE_MCLK = 1364`).

A trial `nextpnr-ecp5 --85k --package CABGA381` placed the block alone, with placeholder serial pins (ULX3S GPDI sites in `build/av-out/av-out-fmax.lpf`, not the SN64 pinout) and other I/O unconstrained. It reported:

- clk_pixel 64.17 MHz (needs 27.02)
- clk_pixel_x5 298.06 MHz (needs 135.10)
- clk_snes 161.89 MHz (needs 21.48)

The clocks entered as independent ports, so cross-domain paths, including pixel→5× words, were not analysed. This is not a board timing result.

## Still open

1. **Clocking decision.** Adopt the master-derived PLL chain (and update the clock plan), or accept per-frame re-phasing with an independent 27 MHz. Measure PLL-cascade jitter and TMDS eye on hardware either way.
2. **Integration.** Instantiate `sn64_av_out` with the real core (`sn64_console_candidate` outputs `rgb/hde/vde/video_x/video_y/audio_*`). Run a core-driven frame through the decoder with a PPU test program to confirm the `X_OUT` and `HDE` alignment and the audio rate.
3. **PAL.** Implemented in simulation: 864×624 raster, VIC 17, pixel = PAL master × 108/85 from PLLB, CLK2 retargeted before the SNES clock starts ([PAL 576p50](#pal-576p50-2026-09-29), [clock plan](clock-plan.md#pal-hdmi-576p50-pixel-clock-2026-09-29)). Still open: display acceptance of 624 lines at 50.154 Hz, and the PAL interlace field (313 lines) is not handled beyond re-phasing.
4. **Interlace.** 263/262-line fields re-phase by two lines on alternate fields, and odd fields are not offset (plain bob). A field-offset option is open.
5. **Horizontal aspect.** Optional 2.5× (640 px) or CRT-exact 2.52× scaling instead of 2× (512 px).
6. **Board path.** HDMI connector, TMDS I/O standard and coupling, HPD/DDC/EDID, CEC, 5 V supply and ESD; SN64-17-04 transmitter selection.
7. **Cartridge audio: done** ([cart-audio-implementation.md](cart-audio-implementation.md)). `sn64_av_out`'s audio port is now fed from `sn64_audio_mix` (a 1-clock `audio_ready` pulse one clk_snes after the core's SND_RDY, values stable); the port contract is unchanged. The pinned core's real audio rate is 32,179.96 Hz (NTSC) / 31,886.43 Hz (PAL), not 32 kHz, which matters for channel status and ACR.
8. **Display compatibility.** Test several TVs, monitors and capture devices for acceptance of 858×524 at 27.0198 MHz and, if the fallback is used, the per-frame short line.
9. **Core quirk (for the core owner). Corrected 2026-09-29 by measurement.**
   - In `fpga/vendor/snestang/src/ppu.v` lines 256–263, the long-dot condition `H_CNT == 323 && H_CNT == 327` can never be true, and the short-line branch selects the same 4-clock dot as the default.
   - The earlier reading here ("341 × 4 = 1364") was wrong. `DOT_NUM` is 340 (`ppu_defines.vh:3`), so every line is **340 × 4 = 1360** master clocks, in both regions.
   - A scratch bench on the real core measured 356,320 master clocks per NTSC frame and 424,320 per PAL frame, and every line 1360 ([clock plan](clock-plan.md#the-snes-pal-frame-in-the-core-measured)).
   - The NTSC 39/31 decision assumes 1364-clock lines. With the core as it is, the NTSC raster is 1,318.5 px early per frame. The whole-system trial shows −1,328 px per frame (including testbench rounding), one re-phase every frame and `av_locked` = 0.
   - The PAL ratio (108/85) was derived from the measured 1360. The clock plan lists the two ways to make NTSC consistent; the decision is the owner's.


## Integration note (2026-09-29)

Integrated into [sn64_top.sv](../../fpga/rtl/sn64_top.sv): the SNES core's RGB, HDE/VDE, `video_x`/`video_y` and audio feed `sn64_av_out`; the top level's outputs are now the three TMDS lanes, the TMDS clock and `av_locked`. Clocking decision: the pixel clock comes from the Si5351's CLK2 on the same PLL as the NTSC master (exactly master × 39/31), not a chained ECP5 PLL pair; see the [clock plan](clock-plan.md). The whole-system simulation passes with this block included.

## PAL 576p50 (2026-09-29)

**Status:** simulated only. Unit bench, fault build, and a whole-system trial with the integration edits applied to scratch copies of the top level. Not run on a display or on hardware.

### Mode selection

`sn64_av_out` has a new input `pal` and a new status output `mode_pal`. Each domain synchronises `pal` and takes it only while it is in reset:

- the pixel domain, for the raster;
- the SNES domain, for the lock-event line.

The top level holds the pixel domain in reset until the Si5351 CLK2 is programmed for the region (`pixel_clock_ready` from [sn64_clock_init](../../fpga/rtl/sn64_clock_init.sv)) and feeds `pal` from `pixel_region_pal`, so the raster always matches the pixel clock. `sn64_av_hdmi_tx` has the same `pal` input; both rasters are constants selected by one mux each.

### PAL raster

CEA-861 VIC 17 timing with 624 lines instead of 625 (sources and derivation in the [clock plan](clock-plan.md#pal-hdmi-576p50-pixel-clock-2026-09-29)):

- **Horizontal:** 720 active, 12 front porch, 64 sync, 68 back porch, 864 total.
- **Vertical:** 576 active, 5 front porch, 5 sync, 38 back porch, 624 total.
- **Sync polarity:** negative.
- **Pixel clock:** PAL master × 108/85 = 27.0398584 MHz, so 2 × 864 pixels are exactly one 1360-clock SNES line and the HDMI frame is the SNES frame (50.154058 Hz).

### Placement and lock

- **Placement:** the picture stays 512 wide at x = 104..615. Vertically `v_off = 288 − visible lines`, so 224-line frames occupy lines 64..511 and 239-line frames occupy 49..526.
- **Lock event:** the HDE rise of SNES line 276 (`PAL_SYNC_LINE`). The expected raster line is `2 × 275 − 3 + v_off`: 611 for 224 lines and 596 for 239. Both are in the vertical back porch (lines 586..623, after vsync on 581..585). A correction therefore never crosses vsync or touches active video. `LEAD_LINES` (3), `SYNC_X` (100), `LOCK_TOL` and the 4-line ring are unchanged, because the geometry of two HDMI lines per SNES line is the same.
- **Counter widths:** the raster position counter is 20 bits (864 × 624 = 539,136 > 2^19). `v_off` is 7 bits and the "no event" timeout is 21 bits.

### InfoFrames and audio

- **AVI InfoFrame:** VIC 17 with picture aspect 4:3 (M1M0 = 01) and IT content. `packet_picker` stays vendored and unmodified. In PAL mode its AVI packet (type 0x82) is replaced by a second instance of the vendored `auxiliary_video_information_info_frame` with those parameters. The NTSC AVI InfoFrame is unchanged (VIC 2, aspect "no data"; VIC 2 itself is the 4:3 format).
- **Audio:** N = 4096 as before. CTS is measured, so it follows the PAL pixel clock (27,288.8 with the bench's audio model). The data-island slots are identical in both modes (3 packets per line, same horizontal active width).

### Evidence

- **Unit bench:** `SN64_TB_PAL` passes. `SN64_TB_PAL` + `SN64_AV_FAULT_PAL_LINES` fails (see Verification). The four NTSC builds are unchanged.
- **Whole-system trial** (`build/pal-hdmi/system-final`, integration edits applied to copies of the current `sn64_top.sv` / `tb_system.sv`). The trial bench models the Si5351 register image, derives the pixel clock from CLK2's programmed source (PAL: master/pixel = 108/85 exactly), runs the SNES clock at the region's frequency, and fails if the Si5351 is accessed while the SNES clock runs or if the SNES clock starts before CLK2 matches the region.

  | Run | HDMI line |
  |---|---|
  | default (NTSC) | `raster 858x524 VIC 2, 4 lock events, lock errors 61313 -1327 -1328 -1328 px, 3 re-phases, locked 0` |
  | `+pal_header` | `raster 864x624 VIC 17 frame-locked, 4 lock events, lock errors -23864 0 0 0 px, 1 re-phases, locked 1, Si5351 writes 59` |
  | `+pal_key +ntsc_header` | `raster 864x624 VIC 17 frame-locked, … lock errors -23864 0 0 0 px, 1 re-phases, locked 1` |
  | `+ntsc_key +pal_header` | `raster 858x524 VIC 2, … lock errors -188782 -1328 -1328 -1327 px, 3 re-phases, locked 0` |

  - All four end in `PASS: system power-on: …` with STATUS 545f / 54df / 34df / 345f.
  - The `+corrupt_key` negative run still fails with `region 0, expected 1`.
  - A trial top without the `pixel_clock_ready` gate on `snes_clk_run` fails `+pal_header` with `SNES clock started before the pixel clock was programmed for the region`.
  - The NTSC lock errors are the measured core-line-length finding (clock plan). They are reported by the trial bench, not failed on.

### Limits

- The unit bench's SNES model is a timing model of the core's output, not the PPU.
- No display has seen the 624-line, 50.154 Hz raster.
- PAL interlace (313-line fields) is not handled beyond per-frame re-phasing.
- The DDR primitive is modelled.
