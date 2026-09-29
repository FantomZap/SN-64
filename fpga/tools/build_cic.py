"""Build the vendored SummerCart64/UltraCIC_C CIC firmware for the SERV core.

Reproduces sw/cic/build.sh with the xPack riscv-none-elf-gcc toolchain and
writes build/cic/cic.mem (the $readmemh image) plus a generated copy of
n64_cic.sv whose firmware path points at that image. Vendored sources are
never modified. Pass --toolchain <bin dir> or set RISCV_TOOLCHAIN_BIN.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / 'fpga/vendor/summercart64'
SW = VENDOR / 'sw/cic'
OUT = ROOT / 'build/cic'
GEN = ROOT / 'build/generated/summercart64'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--toolchain', type=Path, default=Path(os.environ.get('RISCV_TOOLCHAIN_BIN', '')))
    args = ap.parse_args()
    prefix = str(args.toolchain / 'riscv-none-elf-') if str(args.toolchain) else 'riscv-none-elf-'
    OUT.mkdir(parents=True, exist_ok=True)
    GEN.mkdir(parents=True, exist_ok=True)
    elf, lst, binary, mem = OUT / 'cic.elf', OUT / 'cic.lst', OUT / 'cic.bin', OUT / 'cic.mem'
    cflags = ['-ffreestanding', '-nostartfiles', '-Os', '-march=rv32i', '-mabi=ilp32']
    run = lambda cmd: subprocess.run(cmd, cwd=SW, check=True)
    run([prefix + 'gcc'] + cflags + ['-T', 'cic.ld', '-o', str(elf), 'startup.S', 'cic.c'])
    run([prefix + 'size', '-B', '-d', str(elf)])
    with lst.open('w') as fh:
        subprocess.run([prefix + 'objdump', '-S', '-D', str(elf)], cwd=SW, check=True, stdout=fh)
    run([prefix + 'objcopy', '-O', 'binary', str(elf), str(binary)])
    subprocess.run([sys.executable, 'convert.py', str(binary), str(mem)], cwd=SW, check=True)
    # Generated RTL copy with a repository-relative firmware path (upstream uses a relative path to its own tree).
    src = (VENDOR / 'fw/rtl/n64/n64_cic.sv').read_text(encoding='utf-8')
    gen = src.replace('$readmemh("../../../sw/cic/build/cic.mem", ram);', '$readmemh("build/cic/cic.mem", ram);')
    assert gen != src, 'firmware path pattern not found in vendored n64_cic.sv'
    (GEN / 'n64_cic.sv').write_text(gen, encoding='utf-8', newline='\n')
    words = mem.read_text().split()
    manifest = {
        'firmware_words': len(words), 'firmware_bytes': len(words) * 4,
        'ram_words_available': 512,
        'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (elf, binary, mem)},
        'sources_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SW.iterdir()) if p.is_file()},
        'toolchain': subprocess.run([prefix + 'gcc', '--version'], capture_output=True, text=True).stdout.splitlines()[0],
        'cflags': cflags,
    }
    (OUT / 'cic-build.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    if len(words) > 512:
        raise SystemExit(f'firmware too large for the 512-word CIC RAM: {len(words)} words')
    print(f'CIC firmware: {len(words)} words of 512; image {mem}')


if __name__ == '__main__':
    main()
