"""Turn the routed design into the files that go into the board's flash, and say how long the FPGA
takes to load them.

  python fpga/tools/pack_bitstream.py [--config build/route-board/sn64_board_top.config]
        [--bootrom build/n64-bootstrap/sn64_bootstrap.z64] [--out build/bitstream]
        [--freq 38.8] [--spimode qspi] [--no-compress]

Needs `ecppack` of the OSS CAD Suite on PATH. `route_top.py --top board` calls this when the routing
has met its timing, so the build ends with files that can be loaded.

Why the options matter. An empty FPGA is deaf: until it has read its image from the flash it cannot
answer the console's first question to the cartridge (the CIC exchange), and a console that gets no
answer stops for good until it is switched off and on. How long the console waits after power-on is
not published (N64brew, PIF-NUS and CIC-NUS) and has to be measured on an N64 and an M64. Left at
its defaults the FPGA reads its image one bit at a time at 2.4 MHz, which takes seconds. Packed
(`--compress`) and read four bits at a time (`--spimode qspi`) at 38.8 MHz it takes well under a
tenth of a second. The flash on the board (W25Q128JVSIQ) leaves the factory with its four-line mode
switched on, and all four lines are wired.

Outputs in --out:
  sn64_board_top.bit   the FPGA image with the chosen options (flash address 0)
  sn64-flash.bin       the whole content of the flash in one file: the image, then the boot program
                       at FLASH_OFFSET (fpga/rtl/sn64_top.sv), for a programmer that writes whole chips
  summary.json         sizes, options, the load time worked out for each choice, the two load commands

Load time = bits of the image / (lines x clock). The FPGA's own clock is only accurate to about
15 %, so the times are given with that much added. Before the read starts the FPGA spends up to
33 ms on its own start-up after its supplies are up (Lattice FPGA-DS-02012, tICFG).
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FREQS = (2.4, 4.8, 9.7, 19.4, 38.8, 62.0)            # the clocks the ECP5 can read its flash with (MHz)
LINES = {'fast-read': 1, 'dual-spi': 2, 'qspi': 4}
T_ICFG_MS = 33.0                                     # Lattice FPGA-DS-02012: power-up to the start of configuration, at most
CLOCK_TOLERANCE = 0.15


def flash_offset():
    text = (ROOT / 'fpga/rtl/sn64_top.sv').read_text(encoding='utf-8')
    m = re.search(r"FLASH_OFFSET\s*=\s*24'h([0-9A-Fa-f_]+)", text)
    if not m:
        sys.exit('FLASH_OFFSET not found in fpga/rtl/sn64_top.sv')
    return int(m.group(1).replace('_', ''), 16)


def load_ms(size_bytes, lines, mhz):
    return size_bytes * 8 / (lines * mhz * 1e6) * 1e3


def pack(config, out, freq, spimode, compress):
    out.mkdir(parents=True, exist_ok=True)
    exe = shutil.which('ecppack')
    if not exe:
        sys.exit('ecppack is not on PATH (OSS CAD Suite)')
    bit = out / 'sn64_board_top.bit'
    cmd = [exe, '--input', str(config), '--bit', str(bit), '--freq', '%.1f' % freq, '--spimode', spimode]
    if compress:
        cmd.append('--compress')
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not bit.exists():
        sys.exit('ecppack failed:\n' + r.stdout + r.stderr)
    return bit, cmd


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', type=Path, default=ROOT / 'build/route-board/sn64_board_top.config')
    ap.add_argument('--bootrom', type=Path, default=ROOT / 'build/n64-bootstrap/sn64_bootstrap.z64')
    ap.add_argument('--out', type=Path, default=ROOT / 'build/bitstream')
    ap.add_argument('--freq', type=float, default=38.8, choices=FREQS)
    ap.add_argument('--spimode', default='qspi', choices=sorted(LINES))
    ap.add_argument('--no-compress', action='store_true')
    a = ap.parse_args()
    if not a.config.exists():
        sys.exit('%s not found: run fpga/tools/route_top.py --top board first' % a.config)
    bit, cmd = pack(a.config, a.out, a.freq, a.spimode, not a.no_compress)
    size = bit.stat().st_size
    offset = flash_offset()
    if size > offset:
        sys.exit('the image (%d bytes) runs into the boot program at 0x%06X' % (size, offset))
    summary = {'config': str(a.config.relative_to(ROOT)).replace('\\', '/') if a.config.is_relative_to(ROOT) else a.config.name,
               'config_sha256': hashlib.sha256(a.config.read_bytes()).hexdigest(),
               'options': {'compress': not a.no_compress, 'spimode': a.spimode, 'freq_mhz': a.freq},
               'bitstream': {'file': bit.name, 'bytes': size, 'sha256': hashlib.sha256(bit.read_bytes()).hexdigest()},
               'flash_offset_of_boot_program': '0x%06X' % offset,
               'load_time_ms': {'as_packed': round(load_ms(size, LINES[a.spimode], a.freq), 1),
                                'as_packed_slow_clock': round(load_ms(size, LINES[a.spimode], a.freq) * (1 + CLOCK_TOLERANCE), 1),
                                'fpga_start_up_before_it_at_most': T_ICFG_MS,
                                'same_image_other_settings': {'%s at %.1f MHz' % (mode, f): round(load_ms(size, n, f), 1)
                                                              for mode, n in sorted(LINES.items(), key=lambda kv: kv[1]) for f in (2.4, 38.8, 62.0)}},
               'note': 'worked out from the file size; nothing has been loaded into a board'}
    if a.bootrom.exists():
        rom = a.bootrom.read_bytes()
        image = bit.read_bytes() + b'\xff' * (offset - size) + rom
        whole = a.out / 'sn64-flash.bin'
        whole.write_bytes(image)
        summary['boot_program'] = {'file': a.bootrom.name, 'bytes': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}
        summary['whole_flash'] = {'file': whole.name, 'bytes': len(image), 'sha256': hashlib.sha256(image).hexdigest()}
        summary['load_commands'] = ['openFPGALoader -b ulx3s -f --verify %s' % bit.name,
                                    'openFPGALoader -b ulx3s -f --verify -o 0x%06X --file-type raw %s' % (offset, a.bootrom.name)]
    else:
        summary['boot_program'] = 'not found at %s: sn64-flash.bin was not written' % a.bootrom.name
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=1))
    return summary


if __name__ == '__main__':
    main()
