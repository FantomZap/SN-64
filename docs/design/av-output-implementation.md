# On-board HDMI output: retired

**Removed 2026-09-29 (owner decision).** The SN64 board has no video or audio output of its own. The SNES picture and sound go to the console over the cartridge bus and the boot program shows them on the console's own output: the M64's HDMI port, an original N64's AV jack. That path is described and evidenced in [console-video-path.md](console-video-path.md).

## What was removed

| Item | Where it was | Removed by |
|---|---|---|
| `sn64_av_out`, `sn64_av_hdmi_tx`, `sn64_av_serializer` (line-doubled 720x480p / 720x576p50 raster, 32 kHz HDMI audio, ECP5 ODDRX1F serializer) | `fpga/rtl/` | deleted |
| Vendored hdl-util/hdmi packet, InfoFrame, audio and TMDS encoder modules (MIT OR Apache-2.0) | `fpga/vendor/hdl-util-hdmi/` | deleted; no hdl-util code remains in the project |
| `tb_av_out` (TMDS-decoding bench) and the six `av-out*` runs of `evaluate.py` | `fpga/tests/`, `fpga/tools/evaluate.py` | deleted |
| Si5351 CLK2 pixel clock and the per-region MultiSynth-2 retarget (`pixel_clock_ready`, `Q_PIX`) | `fpga/rtl/sn64_clock_init.sv` | CLK2 stays powered down, output disabled (register 3 = 0xFC); nothing is written after start-up |
| ECP5 "tmds" PLL (x5), `si_clk2`, `hdmi_tmds[2:0]`, `hdmi_tmds_clock`, `hdmi_hpd/scl/sda` ports | `fpga/rtl/sn64_board_top.sv`, `sn64_top.sv`, `sn64_pnr_wrap.sv` | removed; one EHXPLLL remains (host 62.5 MHz) |
| Balls A16/B16, A14/C14, A12/A13, A17/B18 (TMDS), E13/D15/E15 (HPD/DDC), F2 (`si_clk2`) | FPGA sheet rev 0.4 / `sn64_board.lpf` | unassigned in rev 0.5-fpga; bank 1 is spare |
| J701 HDMI type-A (Amphenol 10029449-111RLF), U702 TPD12S016, C704-C714, TP701, R705 | A/V sheet draft 0.1-av | gone in draft 0.2-av; Si5351 pin 6 (CLK2) left open |
| `J701` fixed position and its edge-clearance rule | `hardware/sn64/tools/build_main_pcb.py` | removed; board rebuilt from the new netlist |
| HDMI +5 V and TPD12S016 loads (PWR-L37/L38) | `hardware/sn64/interfaces/power-budget.csv` | removed |

The full 0.1-av/round-3 description of the block (raster timing, frame lock, audio packets, the TMDS-decoding bench and its fault builds) is in git history at commit `a2dcad3` and earlier.

## What was learned and kept

- Two SNESTang core bugs were found while locking the HDMI raster to the SNES frame and are still fixed in `prepare_core.py`: the long-dot condition (`&&` instead of `||`, 1360-clock lines) and the DSP sample rate (0.56 % sharp). The console video path benefits from both.
- The cartridge-audio receiver and mixer ([cart-audio-implementation.md](cart-audio-implementation.md)) were written for this output and now feed the frame window's audio ring unchanged.
- The Si5351 start-up image (PLLA/PLLB, MS0/MS1, crystal load) is unchanged; only CLK2 and MS2 went away.
