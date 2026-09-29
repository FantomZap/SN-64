"""Reject changed upstream CAD before the extractor can publish pinned datums.

Run with KiCad Python: python mechanical/test_source_provenance.py --source-root PATH
The test copies the extractor and two reference files into a temporary sandbox.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
paths = ['references/downloads/sanni/hardware/footprints/!OSCR.pretty/SNES Slot.kicad_mod',
         'references/downloads/summercart64/hw/pcb/sc64v2.kicad_pcb']
with tempfile.TemporaryDirectory(prefix='sn64-provenance-') as tmp:
    sandbox = Path(tmp)
    (sandbox / 'mechanical').mkdir()
    for rel in paths + ['references/source-manifest.json']:
        dest = sandbox / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile((root if rel.endswith('source-manifest.json') else args.source_root) / rel, dest)
    script = sandbox / 'mechanical/extract_source_datums.py'
    shutil.copyfile(root / 'mechanical/extract_source_datums.py', script)
    command = [sys.executable, str(script), '--source-root', str(sandbox)]
    good = subprocess.run(command, capture_output=True, text=True)
    assert good.returncode == 0, good.stderr
    output = sandbox / 'mechanical/source-datums.json'
    expected = output.read_bytes()
    for rel in paths:
        path = sandbox / rel
        original = path.read_bytes()
        # Valid KiCad data with changed bytes must not inherit the pinned identity.
        path.write_bytes(original + b'\n')
        bad = subprocess.run(command, capture_output=True, text=True)
        assert bad.returncode != 0 and 'Upstream file changed' in bad.stderr, \
            f'Extractor accepted modified source as pinned: {rel}'
        assert output.read_bytes() == expected, 'Rejected input changed published datums'
        path.write_bytes(original)
    print('PASS: authentic inputs accepted; both altered CAD inputs rejected before output changes')
