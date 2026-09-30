"""Synthesise and place-and-route the whole SN64 design (feasibility run).

--top board (default): fpga/rtl/sn64_board_top.sv, the real top level with the
ECP5 PLLs, the DCSC NTSC/PAL clock select, the bootstrap ROM in the
configuration flash and the CIC pads; constraints fpga/constraints/
sn64_board.lpf, the board pinout generated with the FPGA schematic sheet
(hardware/sn64/tools/add_fpga_sheet.py). The older feasibility pinout
fpga/constraints/sn64_board_trial.lpf stays selectable with --lpf (it matches
the pre-round-3 board-top ports only). --top wrap: the older
fpga/rtl/sn64_pnr_wrap.sv (ideal clocks on pins, bootstrap ROM in block RAM)
with fpga/constraints/sn64_trial.lpf. Either way this measures resources and
internal timing on the constrained pins, not board-level I/O timing. Requires the OSS CAD Suite environment (yosys with the
slang plugin, nextpnr-ecp5) on PATH and prepared core sources in build/
(run fpga/tools/evaluate.py or prepare_core.py first).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def rel(paths):
    return [str(p.relative_to(ROOT)).replace('\\', '/') for p in sorted(paths)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed', default='6', help='ECP5 speed grade (6 or 8)')
    ap.add_argument('--top', choices=['board', 'wrap'], default='board', help='design top level')
    ap.add_argument('--out', default=None, help='output directory (default build/route-<top>)')
    ap.add_argument('--lpf', default=None,
                    help='constraint file (default: fpga/constraints/sn64_board.lpf for --top board, '
                         'fpga/constraints/sn64_trial.lpf for --top wrap)')
    ap.add_argument('--top-file', default=None, help='top-level source to use instead of fpga/rtl/<top>.sv')
    args = ap.parse_args()
    out = ROOT / (args.out or f'build/route-{args.top}')
    out.mkdir(parents=True, exist_ok=True)
    serv = rel((ROOT / 'fpga/vendor/summercart64/fw/rtl/serv').glob('*.v'))
    hdmi = rel((ROOT / 'fpga/vendor/hdl-util-hdmi/src').glob('*.sv'))
    files = (['-f', 'build/core-sources.f', 'fpga/rtl/sn64_console_candidate.sv', 'fpga/rtl/sn64_cart_bridge.sv',
              'fpga/rtl/sn64_console_with_bridge.sv', 'fpga/vendor/summercart64/fw/rtl/memory/mem_bus.sv',
              'fpga/rtl/sn64_n64_reg_bus.sv', 'fpga/vendor/summercart64/fw/rtl/n64/n64_scb.sv',
              'fpga/vendor/summercart64/fw/rtl/n64/n64_pi_fifo.sv', 'fpga/vendor/summercart64/fw/rtl/n64/n64_pi.sv',
              'build/generated/summercart64/n64_cic.sv', 'fpga/rtl/sn64_n64_endpoint.sv'] + serv + hdmi +
             ['fpga/rtl/sn64_av_hdmi_tx.sv', 'fpga/rtl/sn64_av_serializer.sv', 'fpga/rtl/sn64_av_out.sv',
              'fpga/rtl/sn64_cdc.sv', 'fpga/rtl/sn64_clock_init.sv', 'fpga/rtl/sn64_power_sequencer.sv',
              'fpga/rtl/sn64_snes_cic_lock.sv', 'fpga/vendor/snestang-controller/src/controller_adapter.sv',
              'fpga/rtl/sn64_snes_joypad.sv', 'fpga/rtl/sn64_header_probe.sv',
              'fpga/vendor/summercart64/fw/rtl/memory/memory_flash.sv', 'fpga/rtl/sn64_bootrom_flash.sv',
              'fpga/rtl/sn64_i2s_rx.sv', 'fpga/rtl/sn64_audio_mix.sv', 'fpga/rtl/sn64_top.sv'])
    top = 'sn64_board_top' if args.top == 'board' else 'sn64_pnr_wrap'
    if args.top == 'board':
        files.append('fpga/rtl/sn64_cic_pad.sv')
    files.append(args.top_file or f'fpga/rtl/{top}.sv')
    lpf = args.lpf or ('fpga/constraints/sn64_board.lpf' if args.top == 'board' else 'fpga/constraints/sn64_trial.lpf')
    netlist = out / f'{top}.json'
    # The ECP5 primitive library goes through slang itself so primitive
    # parameters (EHXPLLL dividers, DCSMODE) are checked; its modules carry the
    # blackbox attribute. VERILATOR selects the SNES core's inferred-memory
    # branch; SN64_SYNTH selects the ECP5 primitives in the HDMI serializer.
    cells_bb = (Path(shutil.which('yosys')).resolve().parent.parent / 'share/yosys/ecp5/cells_bb.v').as_posix()
    script = ('plugin -i slang; scratchpad -set abc9.xaiger 1; '
              f'read_slang --top {top} -DVERILATOR -DSN64_SYNTH '
              '-Ibuild/generated/snestang/src -Ibuild/generated/snestang/src/spc700 '
              '-Ibuild/generated/snestang/src/65C816 ' + cells_bb + ' ' + ' '.join(files) +
              f'; synth_ecp5 -top {top} -json {netlist.as_posix()}; stat')
    synth_log = out / 'synth.log'
    with synth_log.open('w', encoding='utf-8') as fh:
        r = subprocess.run([shutil.which('yosys'), '-Q', '-T', '-p', script], cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
    if r.returncode:
        sys.exit(f'synthesis failed; see {synth_log}')
    cells = {}
    for line in synth_log.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^\s+(\d+)\s+(LUT4|TRELLIS_FF|DP16KD|MULT18X18D|ODDRX1F|EHXPLLL|DCSC|USRMCLK)\s*$', line)
        if m:
            cells[m.group(2)] = int(m.group(1))
    pnr_log = out / 'pnr.log'
    with pnr_log.open('w', encoding='utf-8') as fh:
        r = subprocess.run([shutil.which('nextpnr-ecp5'), '--85k', '--package', 'CABGA381', '--speed', args.speed,
                            '--json', str(netlist), '--lpf', lpf,
                            '--lpf-allow-unconstrained', '--timing-allow-fail',
                            '--report', str(out / 'pnr-report.json')], cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
    body = pnr_log.read_text(encoding='utf-8', errors='replace')
    fmax = {}
    for m in re.finditer(r"Max frequency for clock\s+'([^']+)':\s+([\d.]+) MHz \((PASS|FAIL) at ([\d.]+) MHz\)", body):
        fmax[m.group(1).split('$')[2] if m.group(1).count('$') >= 2 else m.group(1)] = {
            'achieved_mhz': float(m.group(2)), 'required_mhz': float(m.group(4)), 'result': m.group(3)}
    summary = {'top': top, 'speed_grade': args.speed, 'lpf': lpf, 'synthesis_cells': cells, 'nextpnr_exit': r.returncode,
               'max_frequency': fmax, 'logs': [str(synth_log), str(pnr_log)]}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    if r.returncode or any(v['result'] != 'PASS' for v in fmax.values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
