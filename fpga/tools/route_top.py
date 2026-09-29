"""Synthesise and place-and-route the whole SN64 design (feasibility run).

Uses fpga/rtl/sn64_pnr_wrap.sv (every board interface as a pin, SNES A/V
consumed by the HDMI block) and fpga/constraints/sn64_trial.lpf (clock
frequencies and trial HDMI pins borrowed from ULX3S). Pins other than HDMI are
left to the placer: this measures resources and internal timing, not the
final board pinout. Requires the OSS CAD Suite environment (yosys with the
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
    ap.add_argument('--out', default='build/route-top', help='output directory')
    args = ap.parse_args()
    out = ROOT / args.out
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
              'fpga/rtl/sn64_snes_joypad.sv', 'fpga/rtl/sn64_top.sv', 'fpga/rtl/sn64_pnr_wrap.sv'])
    netlist = out / 'sn64-wrap.json'
    # VERILATOR selects the SNES core's inferred-memory branch; SN64_SYNTH selects
    # the ECP5 ODDRX1F primitive in the HDMI serializer.
    script = ('plugin -i slang; scratchpad -set abc9.xaiger 1; read_verilog -lib +/ecp5/cells_bb.v; '
              'read_slang --extern-modules --top sn64_pnr_wrap -DVERILATOR -DSN64_SYNTH '
              '-Ibuild/generated/snestang/src -Ibuild/generated/snestang/src/spc700 '
              '-Ibuild/generated/snestang/src/65C816 ' + ' '.join(files) +
              f'; synth_ecp5 -top sn64_pnr_wrap -json {netlist.as_posix()}; stat')
    synth_log = out / 'synth.log'
    with synth_log.open('w', encoding='utf-8') as fh:
        r = subprocess.run([shutil.which('yosys'), '-Q', '-T', '-p', script], cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
    if r.returncode:
        sys.exit(f'synthesis failed; see {synth_log}')
    cells = {}
    for line in synth_log.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^\s+(\d+)\s+(LUT4|TRELLIS_FF|DP16KD|MULT18X18D|ODDRX1F)\s*$', line)
        if m:
            cells[m.group(2)] = int(m.group(1))
    pnr_log = out / 'pnr.log'
    with pnr_log.open('w', encoding='utf-8') as fh:
        r = subprocess.run([shutil.which('nextpnr-ecp5'), '--85k', '--package', 'CABGA381', '--speed', args.speed,
                            '--json', str(netlist), '--lpf', 'fpga/constraints/sn64_trial.lpf',
                            '--lpf-allow-unconstrained', '--timing-allow-fail',
                            '--report', str(out / 'pnr-report.json')], cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
    body = pnr_log.read_text(encoding='utf-8', errors='replace')
    fmax = {}
    for m in re.finditer(r"Max frequency for clock\s+'([^']+)':\s+([\d.]+) MHz \((PASS|FAIL) at ([\d.]+) MHz\)", body):
        fmax[m.group(1).split('$')[2] if m.group(1).count('$') >= 2 else m.group(1)] = {
            'achieved_mhz': float(m.group(2)), 'required_mhz': float(m.group(4)), 'result': m.group(3)}
    summary = {'speed_grade': args.speed, 'synthesis_cells': cells, 'nextpnr_exit': r.returncode,
               'max_frequency': fmax, 'logs': [str(synth_log), str(pnr_log)]}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    if r.returncode or any(v['result'] != 'PASS' for v in fmax.values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
