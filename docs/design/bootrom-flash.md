# Bootstrap ROM window from the configuration flash

Implemented 2026-09-29 as a build option of the N64 endpoint (`ROM_FROM_FLASH = 1`). It answers [open integration decision 1](system-integration.md#open-integration-decisions): the 64 K-word bootstrap ROM window needed 64 of the ECP5's 208 DP16KD block RAMs, and whole-design synthesis reached 205 of 208. **Simulation and synthesis only. Nothing here has run on a console, an ECP5 or a real flash chip.** The default build is still block RAM (`ROM_FROM_FLASH = 0`); `sn64_top` does not select the flash option yet (see [integration](#integration-still-to-do)).

## Plain-language summary

The N64 menu program (114,688 bytes) no longer has to be copied into the FPGA's scarce on-chip memory. It sits in the same flash chip that already holds the FPGA's configuration, just after the configuration data. When the N64 reads its cartridge ROM, the FPGA reads the flash four bits at a time and hands the words over. The flash reader is SummerCart64's own (it boots its menu the same way), copied unchanged. In simulation it delivers a word every 240 ns. A standard N64 cartridge read takes 368 ns per word, so it keeps up with 1.5× margin. The first word after a new address takes about 1 µs to arrive. The console's standard settings wait about 1.3 µs before it needs that word. This frees 64 block RAMs and costs about 220 logic cells.

## Files

| File | Role |
|---|---|
| [fpga/rtl/sn64_bootrom_flash.sv](../../fpga/rtl/sn64_bootrom_flash.sv) | `sn64_bootrom_flash`: mem_bus memory. It translates addresses into the flash, blocks writes and instantiates SummerCart64 `memory_flash`. `sn64_flash_mclk`: the SCK output abstraction (`USRMCLK` on ECP5, or a plain pin for simulation). |
| [fpga/rtl/sn64_n64_endpoint.sv](../../fpga/rtl/sn64_n64_endpoint.sv) | New parameters `ROM_FROM_FLASH`, `FLASH_OFFSET`, `FLASH_USE_USRMCLK` and ports `flash_sck`, `flash_cs_n`, `flash_dq[3:0]`. The BRAM branch is unchanged: CS stays high and DQ is released. |
| [fpga/vendor/summercart64/fw/rtl/memory/memory_flash.sv](../../fpga/vendor/summercart64/fw/rtl/memory/memory_flash.sv) | Vendored unmodified (commit `a1e7996d`, SHA-256 `ad8238fc…dfff`, 16,764 bytes; [provenance](../../fpga/vendor/summercart64/provenance.json)). Defines `flash_scb`, `flash_qspi` and `memory_flash`. |
| [fpga/tests/tb_bootrom_flash.sv](../../fpga/tests/tb_bootrom_flash.sv) | Endpoint at 62.5 MHz with a behavioural QSPI flash model and an N64 PI host model using real DOM1 timing. Includes fault injection. |

Licences: SummerCart64 RTL is GPL-3.0 (repository LICENSE, vendored); SN64 HDL is GPL-3.0-or-later. `memory_flash.sv` was checked byte-identical to the upstream tree at `temp/architecture-research/SummerCart64/Polprzewodnikowy-SummerCart64-a1e7996/`. All 28 vendored SummerCart64 files were re-verified against `provenance.json`: 0 mismatches.

## How it works

```
N64 PI --> n64_pi (vendored) --mem_bus--> sn64_bootrom_flash --mem_bus--> memory_flash (vendored) --QSPI--> flash
                                          address = FLASH_OFFSET + (addr mod 2^WINDOW_BITS)
                                          writes: acked here, never forwarded
```

- **Address.** Flash byte address = `FLASH_OFFSET + (mem_bus address mod 2^WINDOW_BITS)`. The endpoint passes `WINDOW_BITS = ROM_ADDR_BITS + 1` (17 = 128 KiB for the 64 K-word window). The window mirrors exactly like the BRAM window. It covers `0x1000_0000` and also the `0x1FFC`/`0x1FFE` windows that `cfg_unlock` maps to memory. `FLASH_OFFSET` must be window-aligned; an elaboration `$error` enforces it. With flash storage the window can grow beyond 128 KiB (up to 24 bits); `n64_pi` only increments the low 17 address bits inside a burst, which is fine because a PI page is at most 128 KiB.
- **Byte order.** The word at byte address *a* is `{flash[a], flash[a+1]}`, the big-endian order of a `.z64` ROM file. The flash holds the bootstrap ROM file unchanged; the `sn64_bootstrap_words.mem` conversion is only needed for the BRAM build.
- **Reads.** SummerCart64 `memory_flash` issues Quad I/O Fast Read `EBh`: command on IO0, 24-bit address on 4 lines, mode byte `0xFF` (no continuous-read mode), then 2 more quad bytes, for 6 clocks after the address in total. Data follows on 4 lines. SCK = clk/2 = 31.25 MHz. CS stays low between sequential requests, so a burst streams without re-addressing. A non-sequential request (new PI address, page change or window wrap) ends the read (CS high) and re-issues `EBh`.
- **Writes** (possible at `0x1FFE_0000` while `cfg_unlock` is set) are acknowledged in one clock and discarded, the same as the BRAM window. They never reach the flash controller, so the N64 cannot program or erase the configuration flash. `flash_scb.erase_pending` is tied low.

## Flash layout (proposal, parameter `FLASH_OFFSET`)

| Flash offset | Content |
|---|---|
| `0x000000` | ECP5 bitstream (LFE5U-85: about 2.2 MB uncompressed; confirm from an `ecppack` output, not measured here) |
| `0x400000` | N64 bootstrap ROM image (`.z64` bytes; 128 KiB window today) |
| above | free: recovery or multiboot image, future virtual-mouse or firmware data |

The 4 MiB offset leaves room for an uncompressed bitstream plus growth. It needs at least a 64 Mbit (8 MiB) part; 128 Mbit is the likely choice. The programming path in the [USB programming architecture](usb-programming-architecture.md) must write the image at this offset. openFPGALoader has a flash offset option; confirm its exact flag and the quad-enable option on the chosen part.

## ECP5 configuration pins and USRMCLK

Guidance to check against Lattice FPGA-TN-02039 (ECP5 and ECP5-5G sysCONFIG usage guide) before the board wrapper is written. Items marked (verify) were not checked against the document in this session.

- **SCK.** After configuration the MCLK/CCLK pin is a dedicated configuration pin. User logic reaches it only through the `USRMCLK` primitive: `USRMCLKI` is the clock and `USRMCLKTS` is the tristate, 0 = drive. `sn64_flash_mclk` (`USE_USRMCLK = 1`) instantiates it. The ECP5 flash build synthesises with one `USRMCLK` cell (below).
- **CS#, D0–D3.** CSSPIN, MOSI/D0, MISO/D1, D2 and D3 are dual-purpose sysCONFIG pins in bank 8. After configuration they can be user I/O, provided the master SPI port is not kept persistent (sysCONFIG option; verify the exact Diamond/nextpnr setting). The ULX3S uses the same package and reference designs drive its flash this way (CSSPIN R2, MCLK U3, D0 W2, D1 V2, D2 Y2, D3 W1 from the ULX3S constraint file; verify against the LFE5U-85F BG381 pinout).
- **Delay.** `USRMCLK` passes through the configuration block and adds output delay that the timing tools do not constrain the usual way (verify the figure). The design samples a full SCK period after launch; see the sample window below.
- **Before the first read** (verify): confirm the state in which the configuration engine leaves the flash. It must not be in deep power-down, and a Release Power-down (`ABh`) may be needed. Also confirm that MCLK is released to `USRMCLK` right after DONE.
- **Quad enable.** `EBh` requires the flash's non-volatile QE bit set. Otherwise IO2/IO3 act as WP#/HOLD#, and a floating HOLD# stalls the flash. Set QE once in production (programmer), or choose a part shipped with QE = 1. Fit pull-ups on D2/D3 either way. The chosen part's `EBh` dummy-cycle count must be 6 (2 mode + 4 dummy, as on Winbond W25Q-class parts), because `memory_flash` sends exactly that.
- **CS# high time.** Between reads CS# stays high for 2–3 clocks (32–48 ns). The model enforces tSHSL ≥ 10 ns (typical read deselect time; verify for the chosen part).

## N64 PI timing

The PI runs from the 62.5 MHz RCP clock (16 ns per PI cycle). Domain-1 timing registers count cycles as value + 1. These come from the n64brew "Peripheral Interface" and "ROM header" descriptions and were not measured on a console:

| Setting | LAT (address → first /RD) | PWD (/RD low) | RLS (/RD high) | Page | Per word |
|---|---|---|---|---|---|
| Boot default before the header is read (IPL2) | 0xFF → 4096 ns | 0xFF → 4096 ns | 3 → 64 ns | — | ~4.2 µs |
| ROM header word `0x80371240` (loaded by IPL2; IPL3 and libdragon programs keep it unless they reprogram DOM1; verify) | 0x40 → 1040 ns | 0x12 → 304 ns | 3 → 64 ns | PGS 7 → 512 B | 368 ns (5.4 MB/s) |
| tb_n64_endpoint.sv host model | 500 ns after ALE_L | 420 ns (sample at 400) | 400 ns | — | 820 ns |

`n64_pi` latches the low address half, flushes its 4-word read FIFO and starts the memory request when **ALE_H falls** (HIGH → LOW), before ALE_L falls. The time between those two edges also counts toward the first-word budget. A PI DMA re-issues the address every 512-byte page. Each page therefore restarts the flash read, because the FIFO prefetch has already moved the stream past the page end.

## Results (Verilator 5.053, OSS CAD Suite 20260928)

Bench defaults: flash-path delays `t_sck` = 6 ns (FPGA SCK register → flash) and `t_clqv` = 9 ns (SCK fall → data at the FPGA), 300 ns ALE steps.

```
PASS: bootrom flash window: 1411 words in 15 bursts match the image (P0 2, P1 1089, P2 64, P3 256), mailbox ok, writes blocked, no DQ contention (35464 clocks)
STATS: ALE step 300 ns; first-word latency max 928 ns from address latch (ALE_H fall), 704 ns from ALE_L fall
STATS: streaming ack interval 240..240 ns/word; in-burst restart (window wrap) 928 ns; P3 strobes 256 ns/word
STATS: min FIFO lead first/later words (ns): P0 7504/-  P1 620/452  P2 748/1328  P3 532/548
STATS: FIFO-empty reads: first word 0, later words 0; flash EBh commands 16
```

The bursts cover:

- the header word at the slow boot default;
- a 2 KiB IPL3-style DMA from `0x1000_1000` in four 512-byte pages;
- bursts at `0x1000_0040`, an unaligned `0x1000_7FF2`, `0x1001_FFF8` crossing the window end (wraps to word 0 and restarts the flash) and `0x1003_0010` above the window (mirrored);
- a mailbox MAGIC read;
- two writes to `0x1FFE_0000` (the model fails on any command other than `EBh`) and a read back of that window;
- a mid-stream restart at a new offset;
- the endpoint bench's strobes (P2) and one fast page (P3).

There are 16 `EBh` commands: 15 ROM reads plus `n64_pi`'s speculative read prefetch after the write burst's ALE.

**Throughput.** One word every 240 ns (15 clocks) while streaming, about 8.3 MB/s. The host needs at least 16 PI cycles per word ((PWD+1)+(RLS+1)):

| Host strobes per word | Result |
|---|---|
| 820 ns (endpoint bench) | 3.4× margin |
| 368 ns (header `0x80371240`) | 1.53× margin |
| 256 ns (P3, 16 cycles) | Passes, with the FIFO still leading the host sample by ≥ 548 ns |
| 224 ns (`+p3_pwd=12 +p3_rls=2`, 14 cycles) | Underruns from read 25 and fails at word 31 (limit run) |

**First word.** The first word is acknowledged 928 ns after the controller's address latch, about 1.0 µs after ALE_H falls at the pin. With the header timing the host samples 1040 + 304 − 20 ns after ALE_L. The first word sat in the FIFO for at least 620 ns before being needed with 300 ns ALE steps, and 384 ns with 64 ns steps (`+ale_step=64`, PASS). Floor: LAT + PWD must stay above about 1.05 µs plus host setup. With PWD 304 ns and the bench's 20 ns early sample, that means LAT ≥ about 0x30 (768 ns). **The bootstrap and menu must keep the standard header `0x80371240` and must not lower DOM1 LAT.** A window-wrap restart inside a burst costs 928 ns and is absorbed by the 4-word FIFO at header timing: 212 ns lead with 64 ns ALE steps, one FIFO-empty read that still returned correct data.

**tb_n64_endpoint's first strobe** (500 ns after ALE_L, sample at 900 ns) passes only because its ALE steps are 300 ns. With 64 ns steps it fails (`+ale_step=64 +p2_lat=500`: word 0 wrong). It is earlier than a real console's first strobe (1040 ns), so the BRAM bench is unchanged, but that host model must not be reused for the flash build without real LAT.

**Sample window.** `memory_flash` samples the pin one full SCK period (32 ns) after the edge that launched the data. With `t_sck` = 6 ns the bench passes up to `t_clqv` = 24 ns and fails at 26 ns, so the round trip (SCK out + flash tCLQV + trace back) must stay below about 30 ns minus the input register setup. Also passes at `t_sck` 15 + `t_clqv` 14 ns. A W25Q-class tCLQV of 6–7 ns leaves about 15 ns for USRMCLK plus trace delays (verify the USRMCLK delay).

**Fault injection** (all exit 1):

```
+fault=1  FAIL P1 read 0x1000112c (word 150 of burst at 0x10001000): got 08a3 expected 085c     (one corrupted flash byte)
+fault=2  FAIL P0 read 0x10000000 (word 0 of burst at 0x10000000): got ffff expected 6047       (image 2 bytes off the offset)
+fault=3  FAIL P0 read 0x10000000 (word 0 of burst at 0x10000000): got 9047 expected 6047       (tCLQV 40 ns)
```

**Regression with the modified endpoint (BRAM default, unchanged source lists):**

| Bench | Result |
|---|---|
| `tb_n64_endpoint` | PASS, 4595 clocks (unchanged) |
| `tb_n64_cic` | PASS; `+corrupt_expect` fails as required |
| `tb_bootstrap_rom_window` (`-GAW=16`) | PASS, 68015 clocks; `+corrupt_load` fails as required |
| `tb_system` | PASS, STATUS=545f |

## Synthesis (Yosys + slang, `synth_ecp5`, endpoint alone, `ROM_ADDR_BITS = 16`)

| Build | LUT4 | TRELLIS_FF | DP16KD | USRMCLK |
|---|---|---|---|---|
| Block RAM (`ROM_FROM_FLASH = 0`) | 811 | 596 | 66 | 0 |
| Flash (`ROM_FROM_FLASH = 1`, `FLASH_USE_USRMCLK = 1`) | 1032 | 657 | 2 | 1 |

Block RAM drops by 64. The remaining 2 DP16KD are present in both builds (the rest of the endpoint, CIC path included). The flash build costs 221 LUT4 and 61 FF. No place-and-route or timing analysis was run. Logs: `build/bootrom-flash-synth-{bram,flash}.log` (untracked). The flash build must read the ECP5 cell library before slang so it knows `USRMCLK`:

```
yosys -Q -T -p "read_verilog -lib +/ecp5/cells_bb.v; plugin -i slang; read_slang --top sn64_n64_endpoint -G ROM_ADDR_BITS=16 -G ROM_FROM_FLASH=1 -G FLASH_USE_USRMCLK=1 <endpoint sources> fpga/vendor/summercart64/fw/rtl/memory/memory_flash.sv fpga/rtl/sn64_bootrom_flash.sv; scratchpad -set abc9.xaiger 1; synth_ecp5 -top sn64_n64_endpoint -json build/bootrom-flash-flash-ecp5.json; stat"
```

## Reproduce

From the repo root, with the tool environment from `CLAUDE.local.md`:

```
verilator_bin --binary --timing --build-jobs 4 -Wno-fatal --top-module tb_bootrom_flash --Mdir <build-dir> \
  fpga/vendor/summercart64/fw/rtl/memory/mem_bus.sv fpga/rtl/sn64_n64_reg_bus.sv fpga/vendor/summercart64/fw/rtl/n64/n64_scb.sv \
  fpga/vendor/summercart64/fw/rtl/n64/n64_pi_fifo.sv fpga/vendor/summercart64/fw/rtl/n64/n64_pi.sv build/generated/summercart64/n64_cic.sv \
  fpga/rtl/sn64_n64_endpoint.sv fpga/vendor/summercart64/fw/rtl/serv/*.v \
  fpga/vendor/summercart64/fw/rtl/memory/memory_flash.sv fpga/rtl/sn64_bootrom_flash.sv fpga/tests/tb_bootrom_flash.sv
<build-dir>/Vtb_bootrom_flash.exe                 # PASS
<build-dir>/Vtb_bootrom_flash.exe +fault=1        # must fail (also +fault=2, +fault=3)
```

## Integration still to do

1. `sn64_top`: pass `ROM_FROM_FLASH`/`FLASH_OFFSET` through and add the `flash_cs_n` and `flash_dq[3:0]` top-level ports. `flash_sck` stays unused with `USRMCLK`. Then switch the default to flash once the board wrapper exists.
2. `evaluate.py`: build and run `tb_bootrom_flash` plus the three fault runs. Whole-design synthesis with the flash option needs `read_verilog -lib +/ecp5/cells_bb.v` before `read_slang` and the two new source files.
3. Board wrapper and constraints: bank-8 pins, I/O standard, QE-bit production step, `ABh` wake-up if needed, confirm TN02039 items above.
4. Hardware checks: measure the real PI DOM1 waveform (ALE_H→ALE_L interval, LAT start point), the USRMCLK output delay and the flash round trip on the prototype.
5. Optional speed-ups if the first-word margin proves too small on hardware: continuous-read mode (skips the 8-clock command) or a faster SCK. Both need an SN64-owned controller instead of the unmodified `memory_flash`.
