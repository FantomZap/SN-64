# Console video path: the SNES picture and sound through the N64/M64's own output

Decision (owner, 2026-09-29): **this is the primary video and audio path.** FPGA side implemented and simulated the same evening (below); the boot program's display loop is written and builds ([n64-bootstrap.md](n64-bootstrap.md)); neither has run on a console. The SN64 hands every SNES frame and its audio to the console over the cartridge bus, and the SN64 boot program displays them through the console's normal output: the AV jack on an original N64, the HDMI on an M64. This is the "single-HDMI operation through the M64" of the spec, achieved with ordinary N64 software and no undocumented console interface. The board's own HDMI output (sn64_av_out) stays as the spec's validation output, secondary.

## How it works

1. **Frame capture (FPGA).** `sn64_frame_capture` (to write) takes the SNES core's pixel stream (the same RGB/HDE/VDE/video_x/video_y signals `sn64_av_out` uses) and writes each visible line into a frame buffer in block RAM: 256 × 224 pixels (or 239 in overscan mode) at 16 bits per pixel in the N64's native RGBA5551 order, so the console can display the buffer as-is. Hi-res 512-wide modes are stored at 256 width in the first version (every second half-dot dropped).
2. **Frame window (FPGA).** The endpoint exposes the buffer to the N64 at a fixed address inside a PI **domain 2** region (`0x0800_0000`, the region the console reserves for cartridge RAM), because domain 2 has its own timing registers: the boot menu programs it fast, while the flash boot-ROM window keeps its slow domain-1 timing ([bootrom-flash.md](bootrom-flash.md) forbids lowering DOM1 LAT). A status register reports the frame counter and the last completed line, so the reader never overtakes the writer.
3. **Audio window.** The core's 32 kHz stereo samples (after the cartridge-audio mixer) go into a small ring buffer read through the same window; the menu feeds them to the N64 audio interface.
4. **Display loop (N64 boot program, libdragon).** Every frame: wait for the frame counter to advance, DMA the completed lines into a 256 × 224 16-bit framebuffer in console RAM (in a few chunks, following the SNES line counter), DMA the audio samples, and let the VI display the framebuffer scaled to the TV; controllers keep going the other way through the mailbox. Latency: about one frame.

## Bandwidth and memory

- One frame: 256 × 224 × 2 = 114,688 bytes; at the SNES's 60.10 Hz that is **6.9 MB/s** for video. Audio adds 128 kB/s. Controllers and status are negligible.
- N64 PI bus: the standard ROM timing (`0x80371240`) gives 368 ns per 16-bit word, 5.4 MB/s, too slow. Domain 2 programmed to PWD 0x05 / RLS 0x01 gives (6 + 2) × 16 ns = 128 ns per word inside a page, about 15 MB/s theoretical; flash carts run comparable settings. The FPGA serves the window from block RAM through the vendored SummerCart64 PI controller, whose FIFO already streams at 240 ns per word from flash, so BRAM should keep up with the faster host timing. **To be measured in simulation with the real host timing before the design is frozen.**
- Block RAM: the frame buffer needs 114,688 bytes = 50 DP16KD (each 2,304 bytes). The routed design uses 143 of 208, so a single buffer fits (193/208). Double buffering does not, so the reader follows the writer line by line, one frame behind, and never reads a line the SNES is writing.
- Interlaced and 512-wide modes and PAL's 239-line overscan are handled by the same buffer; PAL frames are 50 Hz and need less bandwidth.

## What changes in the existing work

| Area | Change |
|---|---|
| `sn64_n64_endpoint` | Add the domain-2 frame/audio window with its own address decode and a status/frame-counter register; keep the ROM window and mailbox as they are. |
| `sn64_top` | Add `sn64_frame_capture` beside `sn64_av_out`; both consume the core's video; the audio mixer output feeds both. |
| Bootstrap ROM | Add the display loop (VI 256 × 224 16-bit, AI at 32 kHz, PI domain-2 timing), keeping the menu on a button. |
| Tests | Bench: capture a synthetic frame, read it back through a PI host model with domain-2 fast timing at full rate, check every pixel and the line-follow rule; whole-system run reads frames from the real core. Negative build: a pixel-order fault must be caught. |
| Board | No new parts; the HDMI section becomes optional. |
| Requirements | "Game visible and audible on the console's own output" becomes the primary A/V acceptance row; the on-board HDMI row becomes secondary. |

## Open points

- Exact sustainable PI rate from the endpoint's BRAM path at fast domain-2 timing (simulation, then hardware).
- VI scaling quality on the M64 (its HDMI scaler) and on an original N64 (composite/S-video); a 320 × 240 framebuffer with the SNES image centred is the fallback if 256-wide framebuffers misbehave on either.
- Hi-res (512-wide) and interlaced games: full-width transfer needs 13.8 MB/s; not in the first version.
- Whether to keep the board's own HDMI at all (owner decision pending).

## Implemented (FPGA side, 2026-09-29, simulation only)

- [sn64_frame_window.sv](../../fpga/rtl/sn64_frame_window.sv): 240 × 256 RGBA5551 frame buffer plus a 1024-pair audio ring in block RAM, written in the SNES clock domain, read through the endpoint's mem_bus; status words cross with `sn64_cdc_word`.
- [sn64_n64_endpoint.sv](../../fpga/rtl/sn64_n64_endpoint.sv): the vendored controller's SRAM window is enabled (N64 `0x0800_0000`, PI domain 2, 128 KiB) and split off the ROM path by mem_bus address; mailbox words `0x1E FRAME_STATUS`, `0x20 AUDIO_WPTR`, `0x22 VIDEO_MODE`.
- [tb_frame_window.sv](../../fpga/tests/tb_frame_window.sv): a synthetic SNES source and an N64 host model reading a whole frame at domain-2 timing while following `lines_done`. **PWD 5 / RLS 1 (128 ns per word, 15.6 MB/s inside bursts) reads all 224 × 256 pixels back exactly**; PWD 3 is where the data starts lagging by a word, so PWD 5 keeps margin. The audio ring reads back in order and the mailbox/ROM window are unaffected. Fault build `SN64_FAULT_FRAME_RB_SWAP` fails on every pixel, as required.
- `tb_system` (NTSC default, PAL header, PAL key, NTSC key) reads FRAME_STATUS/VIDEO_MODE and two pixels through the PI from the real core: frames complete, the PAL bit follows the region, the pixels carry the alpha bit. All 42 `evaluate.py --mode sim` results pass.
- Resources: +54 DP16KD for the frame buffer and audio ring (routing check pending in the work log).

