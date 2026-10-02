"""Run a set of free SNES test programs through the simulated SN64 (run_game.py), several at once,
and say for each what came out.

  python fpga/tools/run_game_suite.py --build-dir <dir without spaces> --roms <folder> [--jobs N]
         [--only <text>] [--out <dir>]

--roms is a folder with the .sfc files of Peter Lemon's public collection
(https://github.com/PeterLemon/SNES), named as their paths with "__" for "/"
(CPUTest__CPU__ADC__CPUADC.sfc ...). They are not part of this repository.

What is judged, and how:
  * CPU and SPC700 instruction tests print a table with PASS or FAIL in its last column and stop
    at the first FAIL. The last picture is read: every row of the table must carry the word PASS
    (compared pixel for pixel with that word in the tests' own font).
  * Every run: the bench's own checks (no bus contention on D0-D7, the cartridge still running at
    the end), no picture missed or fetched twice by the N64 side, and a picture that is not blank.
  * Sound tests: the sound is not silent beyond the idle pattern of the cartridge-audio input.
Pictures of the other programs are for a person to look at: sheet.png.
"""
import argparse
import collections
import json
import os
import re
import struct
import subprocess
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The word PASS in the tests' 8 x 8 font: four cells, one row of pixels per entry (bit 31 = left).
PASS_WORD = [0x7c183c3c, 0x663c6262, 0x7e247c7c, 0x7c7e3e3e, 0x60664646, 0x60663c3c, 0x00000000, 0x00000000]
TABLE_X, TABLE_Y, TABLE_ROWS = 200, 63, 8      # the last column of the table: first row at this pixel, a row every 8
FRAMES = {'CPUTest__CPU': 180, 'CPUTest__SPC700': 300, 'BANK': 150, 'SPC700': 300, 'Games': 420, 'INPUT': 150}


def frames_for(name):
    for prefix, n in FRAMES.items():
        if name.startswith(prefix):
            return n
    return 150


def read_table(words):
    """(rows that say PASS, rows that say something else, rows of the table) on a test's last picture."""
    bg = collections.Counter(words).most_common(1)[0][0]
    ink = [[words[y * 256 + x] != bg for x in range(256)] for y in range(224)]
    passed = other = rows = 0
    for r in range(TABLE_ROWS):
        y0 = TABLE_Y + 8 * r
        if not any(ink[y0 + dy][x] for dy in range(8) for x in range(8, 64)):       # no mode named in this row
            continue
        rows += 1
        cell = [sum(1 << (31 - i) for i in range(32) if ink[y0 + dy][TABLE_X + i]) for dy in range(8)]
        if cell == PASS_WORD:
            passed += 1
        elif any(cell):
            other += 1
    return passed, other, rows


def run_one(rom, args, out):
    name = rom.stem
    dest = out / name
    cmd = [sys.executable, str(ROOT / 'fpga/tools/run_game.py'), '--build-dir', str(args.build_dir), '--rom', str(rom),
           '--frames', str(frames_for(name)), '--shot', str(frames_for(name)), '--out', str(dest)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
    res = {'name': name, 'exit': r.returncode, 'seconds': round(time.time() - t0), 'frames': frames_for(name)}
    log = (dest / 'run.log').read_text(encoding='utf-8', errors='replace') if (dest / 'run.log').exists() else r.stdout
    done = re.search(r'^DONE: .*$', log, re.M)
    res['done'] = bool(done)
    m = re.search(r'\((\d+) words, (\d+) missed, (\d+) fetched twice\)', log)
    res['missed'], res['twice'] = (int(m.group(2)), int(m.group(3))) if m else (None, None)
    res['fatal'] = (re.findall(r'^.*Fatal.*$', log, re.M) or [''])[0][:160]
    hexes = sorted(Path(args.build_dir).glob('run-%s-f*.hex' % ''.join(c if c.isalnum() else '_' for c in name)))
    if hexes:
        words = [int(t, 16) for t in hexes[-1].read_text().split() if not t.startswith('//')]
        if len(words) == 256 * 224:
            res['lit'] = sum(1 for w in words if w >> 1)
            if name.startswith('CPUTest__'):
                res['pass_rows'], res['other_rows'], res['rows'] = read_table(words)
    wav = dest / 'sound.wav'
    if wav.exists():
        with wave.open(str(wav), 'rb') as w:
            n = w.getnframes()
            d = struct.unpack('<%dh' % (2 * n), w.readframes(n)) if n else ()
        res['sound_peak'] = max((abs(v) for v in d), default=0)
    if name.startswith('CPUTest__'):
        ok = res['done'] and res.get('rows', 0) > 0 and res.get('pass_rows') == res.get('rows') and res.get('other_rows') == 0
        res['verdict'] = 'PASS' if ok else 'FAIL'
    elif not res['done'] or res['missed'] or res['twice'] or not res.get('lit'):
        res['verdict'] = 'FAIL'
    else:
        res['verdict'] = 'ran'              # for a person to look at
    print('%-58s %-4s %4d s  %s' % (name, res['verdict'], res['seconds'],
                                     'table %s/%s' % (res.get('pass_rows'), res.get('rows')) if 'rows' in res else
                                     'lit %s, sound peak %s' % (res.get('lit'), res.get('sound_peak'))), flush=True)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--build-dir', type=Path, required=True)
    ap.add_argument('--roms', type=Path, required=True)
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--only', default='')
    ap.add_argument('--out', type=Path, default=ROOT / 'build/game-sim/suite')
    args = ap.parse_args()
    os.chdir(ROOT)
    roms = sorted(p for p in args.roms.glob('*.sfc') if args.only in p.name)
    if not roms:
        sys.exit('no .sfc files in %s' % args.roms)
    args.out.mkdir(parents=True, exist_ok=True)
    # Build once before the workers start (the first run_game call builds; the others only run).
    first = run_one(roms[0], args, args.out)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = [first] + list(pool.map(lambda r: run_one(r, args, args.out), roms[1:]))
    (args.out / 'suite.json').write_text(json.dumps(results, indent=1), encoding='utf-8')
    from PIL import Image, ImageDraw
    cols = 7
    cells = []
    for res in results:
        pics = sorted((args.out / res['name']).glob('picture-f*.png'))
        if pics:
            cells.append((res, Image.open(pics[-1]).resize((256, 224))))
    if cells:
        rows = (len(cells) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * 264 + 8, rows * 250 + 8), (32, 32, 36))
        d = ImageDraw.Draw(sheet)
        for i, (res, im) in enumerate(cells):
            x, y = 8 + (i % cols) * 264, 8 + (i // cols) * 250
            sheet.paste(im, (x, y + 16))
            d.text((x, y + 2), ('%s  %s' % (res['verdict'], res['name'].split('__')[-1]))[:40],
                   fill=(120, 230, 120) if res['verdict'] != 'FAIL' else (255, 110, 100))
        sheet.save(args.out / 'sheet.png')
    tests = [r for r in results if r['name'].startswith('CPUTest__')]
    bad = [r['name'] for r in results if r['verdict'] == 'FAIL']
    print('%d programs: %d instruction tests of which %d PASS; %d others ran; %d FAIL %s' % (
        len(results), len(tests), sum(r['verdict'] == 'PASS' for r in tests),
        sum(r['verdict'] == 'ran' for r in results), len(bad), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
