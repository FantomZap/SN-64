"""Run a set of free SNES test programs through the simulated SN64 (run_game.py), several at once,
and say for each what came out.

  python fpga/tools/run_game_suite.py --build-dir <dir without spaces> --roms <folder> [--jobs N]
         [--only <text>] [--out <dir>] [--rejudge]

--roms is a folder with the .sfc files of Peter Lemon's public collection
(https://github.com/PeterLemon/SNES), named as their paths with "__" for "/"
(CPUTest__CPU__ADC__CPUADC.sfc ...). They are not part of this repository.
--rejudge runs nothing: it reads the pictures, logs and sound of an earlier run again.

What is judged, and how:
  * CPU and SPC700 instruction tests print PASS or FAIL beside each case and stop at the first
    FAIL. The last picture is read: the two words are looked for in every text cell, pixel for
    pixel in the tests' own font. A test passes with at least one PASS and no FAIL on its last
    screen. (The "MSC" test ends on STP, which stops the processor: its last row stays empty
    until a reset, as its screen says.) The bank tests print PASSED in the same font and are
    read the same way.
  * Every run: the bench's own checks (no bus contention on D0-D7, the cartridge still running at
    the end), no picture missed or fetched twice by the N64 side.
  * Sound programs (SPC700/...): they show nothing; they pass when the sound that reaches the N64
    side is well above the idle pattern of the cartridge-audio input.
  * The controller program shows nothing until a button is down: it is run with a button pressed
    from picture 60 on and passes when the picture changes with it.
  * Everything else must show a picture that is not blank, and is for a person to look at:
    sheet.png.
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
# The words PASS and FAIL in the tests' 8 x 8 font (the font table inside the test programs, read
# from CPUADC.sfc): four cells, one row of pixels per entry (bit 31 = left). A text row's first
# pixel row is 7 + 8 k: the picture starts one line into the first row of the tile map.
PASS_WORD = [0x7c183c3c, 0x663c6262, 0x7e247c7c, 0x7c7e3e3e, 0x60664646, 0x60663c3c, 0x00000000, 0x00000000]
FAIL_WORD = [0x7e187e60, 0x603c1860, 0x7c241860, 0x607e1860, 0x60667e7e, 0x60667e7e, 0x00000000, 0x00000000]
FRAMES = {'CPUTest__CPU': 180, 'CPUTest__SPC700': 300, 'BANK': 150, 'SPC700': 300, 'Games': 420, 'INPUT': 150}
IDLE_PEAK = 64                  # the idle pattern of the cartridge-audio input (docs/design/game-simulation.md)
# Controller scripts: "<from picture> <to picture> <mailbox image, hex>" (bit 0 is B).
PADS = {'INPUT__ControllerLatency__ControllerLatency': '60 150 0001\n'}


def frames_for(name):
    for prefix, n in FRAMES.items():
        if name.startswith(prefix):
            return n
    return 150


def tag_of(name):
    return ''.join(c if c.isalnum() else '_' for c in name)


def read_hex(path):
    words = [int(t, 16) for t in path.read_text().split() if not t.startswith('//')]
    return words if len(words) == 256 * 224 else None


def read_words(words):
    """(times the word PASS stands on the picture, times the word FAIL does)."""
    bg = collections.Counter(words).most_common(1)[0][0]
    ink = [[words[y * 256 + x] != bg for x in range(256)] for y in range(224)]
    passed = failed = 0
    for y0 in range(7, 224 - 7, 8):
        for x0 in range(0, 256 - 31, 8):
            cell = [sum(1 << (31 - i) for i in range(32) if ink[y0 + dy][x0 + i]) for dy in range(8)]
            passed += cell == PASS_WORD
            failed += cell == FAIL_WORD
    return passed, failed


def run_one(rom, args, out):
    name = rom.stem
    dest = out / name
    shot = 50 if name in PADS else frames_for(name)
    cmd = [sys.executable, str(ROOT / 'fpga/tools/run_game.py'), '--build-dir', str(args.build_dir), '--rom', str(rom),
           '--frames', str(frames_for(name)), '--shot', str(shot), '--out', str(dest)]
    if name in PADS:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / 'pad.txt').write_text(PADS[name])
        cmd += ['--pad', str(dest / 'pad.txt')]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
    res = judge(name, args, out, r.stdout)
    res['exit'], res['seconds'] = r.returncode, round(time.time() - t0)
    show(res)
    return res


def judge(name, args, out, stdout=''):
    dest = out / name
    res = {'name': name, 'frames': frames_for(name)}
    log = (dest / 'run.log').read_text(encoding='utf-8', errors='replace') if (dest / 'run.log').exists() else stdout
    res['done'] = bool(re.search(r'^DONE: .*$', log, re.M))
    m = re.search(r'\((\d+) words, (\d+) missed, (\d+) fetched twice\)', log)
    res['missed'], res['twice'] = (int(m.group(2)), int(m.group(3))) if m else (None, None)
    res['fatal'] = (re.findall(r'^.*Fatal.*$', log, re.M) or [''])[0][:160]
    pictures = [w for w in (read_hex(f) for f in sorted(Path(args.build_dir).glob('run-%s-f*.hex' % tag_of(name)))) if w]
    if pictures:
        res['lit'] = sum(1 for w in pictures[-1] if w >> 1)
        if name.startswith(('CPUTest__', 'BANK__')):
            res['pass_words'], res['fail_words'] = read_words(pictures[-1])
        if name in PADS:
            res['changed'] = sum(1 for a, b in zip(pictures[0], pictures[-1]) if a != b)
    wav = dest / 'sound.wav'
    if wav.exists():
        with wave.open(str(wav), 'rb') as w:
            n = w.getnframes()
            d = struct.unpack('<%dh' % (2 * n), w.readframes(n)) if n else ()
        res['sound_peak'] = max((abs(v) for v in d), default=0)
    basics = res['done'] and res['missed'] == 0 and res['twice'] == 0 and not res['fatal']
    if name.startswith(('CPUTest__', 'BANK__')):
        res['verdict'] = 'PASS' if basics and res.get('pass_words', 0) > 0 and res.get('fail_words') == 0 else 'FAIL'
        res['why'] = '%s PASS and %s FAIL on its last screen' % (res.get('pass_words'), res.get('fail_words'))
    elif name.startswith('SPC700__'):
        res['verdict'] = 'PASS' if basics and res.get('sound_peak', 0) > 8 * IDLE_PEAK else 'FAIL'
        res['why'] = 'sound peak %s of 32767' % res.get('sound_peak')
    elif name in PADS:
        res['verdict'] = 'PASS' if basics and res.get('changed', 0) > 0 else 'FAIL'
        res['why'] = '%s pixels change when the button goes down' % res.get('changed')
    else:
        res['verdict'] = 'ran' if basics and res.get('lit') else 'FAIL'
        res['why'] = '%s of 57344 pixels lit; for a person to look at' % res.get('lit')
    return res


def show(res):
    print('%-58s %-4s %5s s  %s' % (res['name'], res['verdict'], res.get('seconds', ''), res['why']), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--build-dir', type=Path, required=True)
    ap.add_argument('--roms', type=Path, required=True)
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--only', default='')
    ap.add_argument('--out', type=Path, default=ROOT / 'build/game-sim/suite')
    ap.add_argument('--rejudge', action='store_true', help='run nothing; judge the outputs of an earlier run again')
    args = ap.parse_args()
    os.chdir(ROOT)
    roms = sorted(p for p in args.roms.glob('*.sfc') if args.only in p.name)
    if not roms:
        sys.exit('no .sfc files in %s' % args.roms)
    args.out.mkdir(parents=True, exist_ok=True)
    before = {}
    if (args.out / 'suite.json').exists():
        before = {r['name']: r for r in json.loads((args.out / 'suite.json').read_text(encoding='utf-8'))}
    if args.rejudge:
        results = []
        for rom in roms:
            res = judge(rom.stem, args, args.out)
            for key in ('exit', 'seconds'):
                if key in before.get(rom.stem, {}):
                    res[key] = before[rom.stem][key]
            show(res)
            results.append(res)
    else:
        # Build once before the workers start (the first run_game call builds; the others only run).
        first = run_one(roms[0], args, args.out)
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = [first] + list(pool.map(lambda r: run_one(r, args, args.out), roms[1:]))
    if args.only:                       # a part of the set: keep what is known about the rest
        for r in results:
            before[r['name']] = r
        results = [before[k] for k in sorted(before)]
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
    tests = [r for r in results if r['name'].startswith(('CPUTest__', 'BANK__'))]
    bad = [r['name'] for r in results if r['verdict'] == 'FAIL']
    print('%d programs: %d instruction and bank tests of which %d PASS; %d others PASS; %d ran, for a person to look at; %d FAIL %s' % (
        len(results), len(tests), sum(r['verdict'] == 'PASS' for r in tests),
        sum(r['verdict'] == 'PASS' for r in results if r not in tests),
        sum(r['verdict'] == 'ran' for r in results), len(bad), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
