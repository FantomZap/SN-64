"""Prepare an auditable SNESTang console build; never edits vendored sources.

The upstream VERILATOR branch supplies portable inferred PPU memories. Synthesis
cannot emit its debug print tasks, so generated copies replace those statements
with null statements. Generated SNES.v also exports the CPU PHI2 and video-mode
signals, preserves raw cartridge addresses, and ties the upstream open TURBO
input low for normal SNES CPU timing.
The vendored upstream source remains unchanged; every patch is recorded below.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]


def prepare():
    source = ROOT / 'fpga/vendor/snestang'
    target = ROOT / 'build/generated/snestang'
    manifest = json.loads((source / 'provenance.json').read_text())
    evidence = []
    for item in manifest['files']:
        rel = item['path']
        raw = (source / rel).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item['local_sha256'], rel
        text = raw.decode('utf-8')
        edits = 0
        patches = []
        if Path(rel).suffix in ('.v', '.sv', '.vh'):
            text, edits = re.subn(r'(?m)^(\s*)(?!//)(\$fdisplay\([^\n]*\);)',
                                 r'\1; // Simulation diagnostic omitted for synthesis.', text)
        if rel == 'src/SNES.v':
            # Expose existing CPU clock and connect the already-declared video
            # mode output; upstream leaves both instance outputs unconnected.
            assert 'output CPURD_N,' in text and '.SYSCLK(), .TURBO()' in text
            assert '.HIGH_RES(), .DOTCLK(DOTCLK)' in text
            text = text.replace('output CPURD_N,', 'output CPURD_N,\n    output PHI2,')
            text = text.replace('.SYSCLK(), .TURBO()', ".SYSCLK(PHI2), .TURBO(1'b0)")
            text = text.replace('.HIGH_RES(), .DOTCLK(DOTCLK)', '.HIGH_RES(HIGH_RES), .DOTCLK(DOTCLK)')
            assert 'output [23:0] CA,' in text and '.CA(INT_CA), .CPURD_N' in text
            text = text.replace('output [23:0] CA,', 'output [23:0] CA,\n    output [23:0] RAW_CA,')
            text = text.replace('.CA(INT_CA), .CPURD_N', '.CA(INT_CA), .RAW_CA(RAW_CA), .CPURD_N', 1)
            patches = ['export PHI2', 'connect HIGH_RES', 'tie TURBO low', 'export raw cartridge address separately from internal CA']
        if rel == 'src/cpu.v':
            assert 'output reg [23:0] CA,' in text and 'assign INT_A = ' in text
            text = text.replace('output reg [23:0] CA,', 'output [23:0] RAW_CA,\n    output reg [23:0] CA,')
            text = text.replace('assign INT_A = ', 'assign RAW_CA = INT_A;\n\nassign INT_A = ')
            patches = ['export CPU/DMA/HDMA selected address before WRAM mirror canonicalization']
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding='utf-8', newline='\n')
        evidence.append({'path': rel, 'debug_prints_omitted': edits,
                         'interface_patches': patches,
                         'sha256': hashlib.sha256(out.read_bytes()).hexdigest()})
    sources = (ROOT / 'fpga/core-sources.f').read_text().replace('fpga/vendor/snestang/', 'build/generated/snestang/')
    (ROOT / 'build/core-sources.f').write_text(sources, encoding='utf-8', newline='\n')
    (ROOT / 'build/core-preparation.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(f'Prepared {len(evidence)} pinned files; omitted {sum(x["debug_prints_omitted"] for x in evidence)} diagnostic statements.')


if __name__ == '__main__':
    prepare()
