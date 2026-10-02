"""Run a real cartridge image through the whole SN64 logic in simulation and save what the
N64 would show and play (fpga/tests/tb_game.sv), or with --board through the v2 board as its
board file wires it (fpga/tests/tb_board_game.sv).

  python fpga/tools/run_game.py --build-dir <dir without spaces> --rom <image> [--frames N]
         [--shot K] [--pad <file>] [--key ntsc|pal|none] [--hirom|--lorom] [--sram-kb N]
         [--out <dir>] [--threads N] [--rebuild]
         [--board [--cartridge 0|1|2] [--bootrom <z64>] [--b-off-a 0|1] [--start-ms N]]

--board needs the board's connection list turned into a simulation first:
  <KiCad's python> hardware/sn64-v2/tools/export_board_nets.py
  python hardware/sn64-v2/tools/make_board_sim.py
and evaluate.py run once (it makes the generated copies of the core and of the N64 key chip).
It uses its own build directory: <build-dir>-board.

The image must be without a copier header. The board kind (LoROM or HiROM), the size of the
battery RAM and the region are read from the image's own header unless given. Outputs in --out
(default build/game-sim/<image name>): one PNG for every picture the bench wrote, a sheet of
them, the sound as a WAV file, the bench's log, and a summary in JSON.

Needs Verilator, a C++ compiler and make on PATH, and the prepared core (fpga/tools/evaluate.py
has run once, and fpga/tools/build_cic.py). No image is part of this repository: use your own
cartridge's image or a free test program, and keep it and the pictures of commercial games out
of the repository.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The sources of the whole-system bench (evaluate.py: sys_sources), with tb_game.sv as the top.
N64_COMMON = ['fpga/vendor/summercart64/fw/rtl/memory/mem_bus.sv', 'fpga/rtl/sn64_n64_reg_bus.sv',
              'fpga/vendor/summercart64/fw/rtl/n64/n64_scb.sv', 'fpga/vendor/summercart64/fw/rtl/n64/n64_pi_fifo.sv',
              'fpga/vendor/summercart64/fw/rtl/n64/n64_pi.sv', 'build/generated/summercart64/n64_cic.sv',
              'fpga/rtl/sn64_cdc.sv', 'fpga/rtl/sn64_frame_window.sv', 'fpga/rtl/sn64_n64_endpoint.sv'] + [
              'fpga/vendor/summercart64/fw/rtl/serv/serv_%s.v' % n for n in (
                  'alu', 'bufreg', 'bufreg2', 'ctrl', 'decode', 'immdec', 'mem_if', 'rf_if', 'rf_ram', 'rf_ram_if',
                  'rf_top', 'state', 'top')]
SOURCES = ['-Ibuild/generated/snestang/src', '-Ibuild/generated/snestang/src/spc700', '-Ibuild/generated/snestang/src/65C816',
           '-Ifpga/tests', '-f', 'build/core-sources.f',
           'fpga/rtl/sn64_console_candidate.sv', 'fpga/rtl/sn64_cart_bridge.sv', 'fpga/rtl/sn64_console_with_bridge.sv'] + N64_COMMON + [
           'fpga/rtl/sn64_power_sequencer.sv', 'fpga/rtl/sn64_snes_cic_lock.sv',
           'fpga/vendor/snestang-controller/src/controller_adapter.sv', 'fpga/rtl/sn64_snes_joypad.sv',
           'fpga/rtl/sn64_header_probe.sv', 'fpga/rtl/sn64_sd_adc.sv', 'fpga/rtl/sn64_audio_mix.sv',
           'fpga/rtl/sn64_clock_pace.sv', 'fpga/rtl/sn64_top.sv', 'fpga/tests/tb_game.sv']
# The board bench: the same logic under the board's real top level, the stand-ins for the FPGA's
# own cells, the part models and the board's connection list.
BOARD_ONLY = ['-I{board}', 'fpga/vendor/summercart64/fw/rtl/memory/memory_flash.sv', 'fpga/rtl/sn64_bootrom_flash.sv',
              'fpga/rtl/sn64_rail_monitor.sv', 'fpga/rtl/sn64_board_top.sv',
              'fpga/tests/ecp5_sim_stubs.sv', 'fpga/tests/tb_bootrom_flash.sv', 'fpga/tests/board_models.sv',
              '{board}/sn64_board_netlist.sv', 'fpga/tests/tb_board_game.sv']


def header(data, base):
    """The internal header at `base` (0x7FC0 LoROM, 0xFFC0 HiROM) and how much it looks like one."""
    if len(data) < base + 0x40:
        return None, -1
    h = data[base:base + 0x40]
    score = 0
    comp, chk = h[0x1C] | h[0x1D] << 8, h[0x1E] | h[0x1F] << 8
    if (comp ^ chk) == 0xFFFF:
        score += 4
    if (h[0x15] & 0x0F) == (1 if base == 0xFFC0 else 0):
        score += 2
    if all(32 <= c < 127 for c in h[:21]):
        score += 1
    reset = h[0x3C] | h[0x3D] << 8
    if reset >= 0x8000:
        score += 1
    return h, score


def describe(data):
    lo, slo = header(data, 0x7FC0)
    hi, shi = header(data, 0xFFC0)
    hirom = shi > slo
    h = hi if hirom else lo
    ram = h[0x18]
    return {'hirom': hirom, 'title': bytes(h[:21]).decode('ascii', 'replace').rstrip(),
            'map': h[0x15], 'kind': h[0x16], 'sram_kb': (1 << ram) if 0 < ram <= 7 and h[0x16] in (1, 2, 5) else 0,
            'country': h[0x19], 'pal': 2 <= h[0x19] <= 12 and h[0x19] != 13,
            'checksum_ok': ((h[0x1C] | h[0x1D] << 8) ^ (h[0x1E] | h[0x1F] << 8)) == 0xFFFF,
            'header_score': max(slo, shi)}


def to_png(words, path, scale=2):
    from PIL import Image
    im = Image.new('RGB', (256, 224))
    im.putdata([(((w >> 11) & 31) * 255 // 31, ((w >> 6) & 31) * 255 // 31, ((w >> 1) & 31) * 255 // 31) for w in words])
    if scale != 1:
        im = im.resize((256 * scale, 224 * scale), Image.NEAREST)
    im.save(path)
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--build-dir', type=Path, required=True, help='Verilator object directory, no spaces')
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--frames', type=int, default=60)
    ap.add_argument('--shot', type=int, default=30)
    ap.add_argument('--pad', type=Path, help='controller script: lines "<from> <to> <hex mask>"')
    ap.add_argument('--key', choices=['ntsc', 'pal', 'none'], default=None, help='key CIC in the cartridge (default: none)')
    ap.add_argument('--hirom', action='store_true')
    ap.add_argument('--lorom', action='store_true')
    ap.add_argument('--sram-kb', type=int, default=None)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--threads', type=int, default=1)
    ap.add_argument('--rebuild', action='store_true')
    ap.add_argument('--board', action='store_true', help='through the v2 board as its board file wires it')
    ap.add_argument('--cartridge', type=int, choices=[0, 1, 2], default=1,
                    help='--board: 0 nothing in the socket, 1 a cartridge, 2 a cartridge back to front')
    ap.add_argument('--bootrom', type=Path, help='--board: the boot program image for the flash')
    ap.add_argument('--b-off-a', type=int, choices=[0, 1],
                    help='--board: level an always-on level shifter byte puts out while the cartridge has no 5 V')
    ap.add_argument('--start-ms', type=int, default=3000, help='--board: give up if the game has not started after this long')
    ap.add_argument('--stop-ms', type=int, help='--board: end the run at this time (to measure the speed)')
    ap.add_argument('--board-dir', default='build/board-sim',
                    help='--board: where make_board_sim.py wrote the netlist (another one for a deliberate wiring mistake)')
    args = ap.parse_args()
    obj = args.build_dir.resolve()
    if args.board:
        obj = obj.with_name(obj.name + '-board')
    top = 'tb_board_game' if args.board else 'tb_game'
    if ' ' in str(obj):
        ap.error('the build directory must not contain spaces')
    os.chdir(ROOT)
    data = args.rom.read_bytes()
    if len(data) % 1024 == 512:
        ap.error('this image has a 512-byte copier header; remove it first')
    info = describe(data)
    hirom = True if args.hirom else False if args.lorom else info['hirom']
    sram_kb = info['sram_kb'] if args.sram_kb is None else args.sram_kb
    out = (args.out or ROOT / 'build/game-sim' / args.rom.stem.replace(' ', '_')).resolve()
    out.mkdir(parents=True, exist_ok=True)
    # The bench takes its paths as plusargs: none may contain a space.
    # Each run has its own files in the build directory, so several can run at once.
    tag = ''.join(c if c.isalnum() else '_' for c in out.name)
    obj.mkdir(parents=True, exist_ok=True)
    work_rom = obj / ('rom-%s.bin' % tag)
    shutil.copyfile(args.rom, work_rom)
    prefix = obj / ('run-%s' % tag)
    for old in obj.glob('run-%s-*.hex' % tag):
        old.unlink()

    env = os.environ.copy()
    verilator = shutil.which('verilator_bin') or shutil.which('verilator')
    if not verilator:
        sys.exit('Verilator is not on PATH; see fpga/README.md')
    if os.name == 'nt':
        env.setdefault('VERILATOR_ROOT', str(Path(verilator).resolve().parents[1] / 'share/verilator'))
    exe = obj / ('V%s.exe' % top if os.name == 'nt' else 'V' + top)
    stamp = obj / 'build-stamp.json'
    watched = sorted(f.relative_to(ROOT).as_posix() for f in (ROOT / 'fpga/rtl').glob('*.sv')) + [
        'fpga/tests/tb_game.sv', 'fpga/tests/snes_key_cic_model.svh']
    sources = SOURCES
    if args.board:
        board_dir = Path(args.board_dir).as_posix().rstrip('/')
        if not (ROOT / board_dir / 'sn64_board_netlist.sv').exists():
            sys.exit('--board: run export_board_nets.py and make_board_sim.py first')
        board_only = [f.replace('{board}', board_dir) for f in BOARD_ONLY]
        sources = SOURCES[:-1] + board_only
        watched = watched[:-2] + [f for f in board_only if f.startswith(('fpga/tests/', board_dir + '/'))] + [
            'fpga/tests/snes_key_cic_model.svh', board_dir + '/board_pins.svh']
    want = {'threads': args.threads, 'sources': {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in watched}}
    if args.rebuild or not exe.exists() or not stamp.exists() or json.loads(stamp.read_text()) != want:
        cmd = [verilator, '--binary', '--timing', '--build-jobs', '16', '-O3', '--x-assign', 'fast', '--x-initial', 'fast',
               '-CFLAGS', '-O2', '-Wno-fatal', '-Wno-lint', '-Wno-style', '-Wno-TIMESCALEMOD',
               '--top-module', top, '--Mdir', str(obj).replace('\\', '/')]
        if args.threads > 1:
            cmd += ['--threads', str(args.threads)]
        t0 = time.time()
        with (out / 'build.log').open('w', encoding='utf-8') as log:
            r = subprocess.run(cmd + sources, env=env, stdout=log, stderr=subprocess.STDOUT)
        if r.returncode:
            sys.exit('build failed; see %s' % (out / 'build.log'))
        stamp.write_text(json.dumps(want))
        print('built in %.0f s' % (time.time() - t0), flush=True)

    run = [str(exe), '+rom=' + str(work_rom).replace('\\', '/'), '+out=' + str(prefix).replace('\\', '/'),
           '+frames=%d' % args.frames, '+shot=%d' % args.shot, '+sram_kb=%d' % sram_kb]
    if hirom:
        run.append('+hirom')
    if args.key in ('ntsc', 'pal'):
        run.append('+%s_key' % args.key)
    if args.board:
        run += ['+cartridge=%d' % args.cartridge, '+start_ms=%d' % args.start_ms]
        if args.b_off_a is not None:
            run.append('+b_off_a=%d' % args.b_off_a)
        if args.stop_ms:
            run.append('+stop_ms=%d' % args.stop_ms)
        if args.bootrom:
            boot = obj / ('boot-%s.z64' % tag)
            shutil.copyfile(args.bootrom, boot)
            run.append('+bootrom=' + boot.as_posix())
    if args.pad:
        pad = obj / ('pad-%s.txt' % tag)
        shutil.copyfile(args.pad, pad)
        run.append('+pad=' + str(pad).replace('\\', '/'))
    print('%s: "%s", %s, %d KiB of battery RAM, header country 0x%02X, checksum pair %s' % (
        args.rom.name, info['title'], 'HiROM' if hirom else 'LoROM', sram_kb, info['country'], 'ok' if info['checksum_ok'] else 'not valid'), flush=True)
    t0 = time.time()
    lines = []
    with (out / 'run.log').open('w', encoding='utf-8') as log:
        p = subprocess.Popen(run, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
        for line in p.stdout:
            log.write(line)
            log.flush()
            lines.append(line.rstrip())
            print(line.rstrip(), flush=True)
        p.wait()
    took = time.time() - t0
    done = next((ln for ln in lines if ln.startswith(('DONE:', 'REFUSED:'))), None)

    # Pictures and sound, whatever the run got to.
    shots = []
    for f in sorted(obj.glob('run-%s-f*.hex' % tag)):
        words = [int(t, 16) for t in f.read_text().split() if not t.startswith('//')]
        if len(words) != 256 * 224:
            continue
        name = 'picture-' + f.stem.rsplit('-', 1)[1]
        shots.append((name, to_png(words, out / (name + '.png'))))
    if shots:
        from PIL import Image, ImageDraw
        cols = min(4, len(shots))
        rows = (len(shots) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * 522 + 10, rows * 478 + 10), (32, 32, 36))
        d = ImageDraw.Draw(sheet)
        for i, (name, im) in enumerate(shots):
            x, y = 10 + (i % cols) * 522, 10 + (i // cols) * 478
            sheet.paste(im, (x, y + 20))
            d.text((x, y + 4), name.replace('picture-f', 'picture '), fill=(220, 220, 220))
        sheet.save(out / 'sheet.png')
    audio = obj / ('run-%s-audio.hex' % tag)
    samples = 0
    if audio.exists():
        words = [int(t, 16) for t in audio.read_text().split() if not t.startswith('//')]
        words = words[:len(words) // 2 * 2]
        samples = len(words) // 2
        with wave.open(str(out / 'sound.wav'), 'wb') as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(32040)
            w.writeframes(struct.pack('<%dh' % len(words), *[v - 65536 if v >= 32768 else v for v in words]))
    summary = {'image': args.rom.name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'header': info,
               'board': 'HiROM' if hirom else 'LoROM', 'sram_kb': sram_kb, 'key': args.key or 'none', 'frames_asked': args.frames,
               'pictures_written': [n for n, _ in shots], 'sound_samples': samples, 'exit_code': p.returncode,
               'seconds': round(took, 1), 'done_line': done, 'fatal': [ln for ln in lines if 'Fatal' in ln or 'fatal' in ln][:5],
               'through': 'the v2 board (tb_board_game.sv)' if args.board else 'the logic (tb_game.sv)',
               'board_line': next((ln for ln in lines if ln.startswith('BOARD:')), None)}
    (out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print('%s in %.0f s; %d pictures, %d sound samples; outputs in %s' % ('finished' if done else 'DID NOT FINISH', took, len(shots), samples, out))
    return 0 if done and p.returncode == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
