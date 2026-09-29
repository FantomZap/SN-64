"""Reproduce the console-only simulation and ECP5 resource experiment.

No bitstream is emitted. P&R deliberately has no board pin assignments; it
cannot qualify external bus timing, I/O banks, power or a finished PCB.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from prepare_core import prepare, ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sim-build-dir', type=Path, required=True,
                        help='Disposable Verilator object directory; must not contain spaces')
    parser.add_argument('--mode', choices=['sim', 'synth', 'pnr', 'all'], default='all')
    args = parser.parse_args()
    obj = args.sim_build_dir.resolve()
    if ' ' in str(obj):
        parser.error('Verilator/GNU Make requires a build directory without spaces')
    os.chdir(ROOT)
    prepare()
    logs = ROOT / 'build/evaluation'
    logs.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    verilator = shutil.which('verilator_bin') or shutil.which('verilator')
    if verilator and os.name == 'nt':
        env.setdefault('VERILATOR_ROOT', str(Path(verilator).resolve().parents[1] / 'share/verilator'))
    report = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Console candidate only; no board pin/timing qualification or hardware proof',
        'mode': args.mode,
        'commands': [],
        'inputs': {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p)
                   for p in sorted((ROOT / 'fpga').rglob('*'))
                   if p.is_file() and p.suffix in ('.py', '.sv', '.v', '.vh', '.f')},
        'preparation_sha256': sha(ROOT / 'build/core-preparation.json'),
    }

    def run(label, command, expected_failure=None):
        if not command[0]:
            raise RuntimeError(f'Missing tool for {label}; see fpga/README.md')
        log = logs / (label + '.log')
        print(label, flush=True)
        with log.open('w', encoding='utf-8') as output:
            result = subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT)
        body = log.read_text(encoding='utf-8', errors='replace')
        report['commands'].append({'label': label, 'argv': [str(x) for x in command],
                                   'exit_code': result.returncode, 'log_sha256': sha(log)})
        if expected_failure:
            if result.returncode == 0 or expected_failure not in body:
                raise RuntimeError(f'{label} did not reject the injected error as expected; {log}')
        elif result.returncode:
            raise RuntimeError(f'{label} failed ({result.returncode}); {log}')
        return body

    if args.mode in ('sim', 'all'):
        obj.mkdir(parents=True, exist_ok=True)
        run('verilator-version', [verilator, '--version'])
        run('simulation-build', [verilator, '--binary', '--timing', '--build-jobs', '4',
            '-Wno-fatal', '--top-module', 'tb_console_boot', '--Mdir', str(obj).replace('\\', '/'),
            '-Ibuild/generated/snestang/src', '-Ibuild/generated/snestang/src/spc700',
            '-Ibuild/generated/snestang/src/65C816', '-f', 'build/core-sources.f',
            'fpga/rtl/sn64_console_candidate.sv', 'fpga/tests/tb_console_boot.sv'])
        executable = obj / ('Vtb_console_boot.exe' if os.name == 'nt' else 'Vtb_console_boot')
        report['simulation'] = {}
        for name, options in [('ntsc-mode', []), ('pal-mode-bit', ['+pal'])]:
            body = run(name, [str(executable)] + options)
            passed = next((line for line in body.splitlines() if line.startswith('PASS:')), None)
            if passed is None:
                raise RuntimeError(f'{name} exited without its acceptance marker')
            report['simulation'][name] = passed
        run('corrupt-cartridge-read', [str(executable), '+corrupt_read'], 'cartridge low readback')
        report['simulation']['injected_bad_read'] = 'Rejected with expected cartridge low readback assertion'
        wram_obj = obj / 'wram-bus'
        run('wram-build', [verilator, '--binary', '--timing', '--build-jobs', '4',
            '-Wno-fatal', '--top-module', 'tb_wram_bus', '--Mdir', str(wram_obj).replace('\\', '/'),
            '-Ibuild/generated/snestang/src', '-Ibuild/generated/snestang/src/spc700',
            '-Ibuild/generated/snestang/src/65C816', '-f', 'build/core-sources.f',
            'fpga/rtl/sn64_console_candidate.sv', 'fpga/tests/tb_wram_bus.sv'])
        wram_exe = wram_obj / ('Vtb_wram_bus.exe' if os.name == 'nt' else 'Vtb_wram_bus')
        wram_body = run('wram-bus', [str(wram_exe)])
        wram_pass = next((line for line in wram_body.splitlines() if line.startswith('PASS:')), None)
        if wram_pass is None:
            raise RuntimeError('WRAM bus test exited without its acceptance marker')
        report['simulation']['wram_bus'] = wram_pass
        bridge_sources = ['fpga/rtl/sn64_console_candidate.sv', 'fpga/rtl/sn64_cart_bridge.sv',
                          'fpga/rtl/sn64_console_with_bridge.sv', 'fpga/tests/tb_cart_bridge.sv']
        bridge_obj = obj / 'cart-bridge'
        run('bridge-build', [verilator, '--binary', '--timing', '--build-jobs', '4',
            '-Wno-fatal', '--top-module', 'tb_cart_bridge', '--Mdir', str(bridge_obj).replace('\\', '/'),
            '-Ibuild/generated/snestang/src', '-Ibuild/generated/snestang/src/spc700',
            '-Ibuild/generated/snestang/src/65C816', '-f', 'build/core-sources.f'] + bridge_sources)
        bridge_exe = bridge_obj / ('Vtb_cart_bridge.exe' if os.name == 'nt' else 'Vtb_cart_bridge')
        bridge_body = run('cart-bridge', [str(bridge_exe)])
        bridge_pass = next((line for line in bridge_body.splitlines() if line.startswith('PASS:')), None)
        if bridge_pass is None:
            raise RuntimeError('Cartridge bridge test exited without its acceptance marker')
        report['simulation']['cart_bridge'] = bridge_pass
        # Fault injection: a bridge without the turnaround clock must be caught as contention.
        fault_obj = obj / 'cart-bridge-fault'
        run('bridge-fault-build', [verilator, '--binary', '--timing', '--build-jobs', '4',
            '-Wno-fatal', '+define+SN64_FAULT_NO_GUARD', '--top-module', 'tb_cart_bridge',
            '--Mdir', str(fault_obj).replace('\\', '/'),
            '-Ibuild/generated/snestang/src', '-Ibuild/generated/snestang/src/spc700',
            '-Ibuild/generated/snestang/src/65C816', '-f', 'build/core-sources.f'] + bridge_sources)
        fault_exe = fault_obj / ('Vtb_cart_bridge.exe' if os.name == 'nt' else 'Vtb_cart_bridge')
        run('cart-bridge-no-guard', [str(fault_exe)], 'without release clock')
        report['simulation']['injected_bridge_fault'] = 'Rejected: owner change without a released clock is detected'
        # N64/M64 host endpoint: vendored SummerCart64 PI controller plus the SN64 ROM/mailbox wrapper.
        serv = sorted(str(p.relative_to(ROOT)).replace('\\', '/')
                      for p in (ROOT / 'fpga/vendor/summercart64/fw/rtl/serv').glob('*.v'))
        n64_common = ['fpga/vendor/summercart64/fw/rtl/memory/mem_bus.sv', 'fpga/rtl/sn64_n64_reg_bus.sv',
                      'fpga/vendor/summercart64/fw/rtl/n64/n64_scb.sv', 'fpga/vendor/summercart64/fw/rtl/n64/n64_pi_fifo.sv',
                      'fpga/vendor/summercart64/fw/rtl/n64/n64_pi.sv', 'build/generated/summercart64/n64_cic.sv',
                      'fpga/rtl/sn64_n64_endpoint.sv'] + serv
        n64_sources = n64_common + ['fpga/tests/tb_n64_endpoint.sv']
        n64_obj = obj / 'n64-endpoint'
        run('n64-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
            '--top-module', 'tb_n64_endpoint', '--Mdir', str(n64_obj).replace('\\', '/')] + n64_sources)
        n64_exe = n64_obj / ('Vtb_n64_endpoint.exe' if os.name == 'nt' else 'Vtb_n64_endpoint')
        n64_body = run('n64-endpoint', [str(n64_exe)])
        n64_pass = next((line for line in n64_body.splitlines() if line.startswith('PASS:')), None)
        if n64_pass is None:
            raise RuntimeError('N64 endpoint test exited without its acceptance marker')
        report['simulation']['n64_endpoint'] = n64_pass
        # CIC lockout handshake against a console-side model; needs the built firmware image.
        if (ROOT / 'build/cic/cic-build.json').exists():
            cic_obj = obj / 'n64-cic'
            run('cic-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
                '--top-module', 'tb_n64_cic', '--Mdir', str(cic_obj).replace('\\', '/')] + n64_common + ['fpga/tests/tb_n64_cic.sv'])
            cic_exe = cic_obj / ('Vtb_n64_cic.exe' if os.name == 'nt' else 'Vtb_n64_cic')
            cic_body = run('n64-cic', [str(cic_exe)])
            cic_pass = next((line for line in cic_body.splitlines() if line.startswith('PASS:')), None)
            if cic_pass is None:
                raise RuntimeError('CIC test exited without its acceptance marker')
            report['simulation']['n64_cic'] = cic_pass
            run('n64-cic-corrupt-expectation', [str(cic_exe), '+corrupt_expect'], 'FAIL checksum nibble 3')
            report['simulation']['injected_cic_fault'] = 'Rejected: a single altered checksum nibble is detected'
            report['cic_firmware'] = json.loads((ROOT / 'build/cic/cic-build.json').read_text())
        else:
            report['simulation']['n64_cic'] = 'SKIPPED: build/cic/cic-build.json missing; run fpga/tools/build_cic.py first'
        # Power-control state machine
        pwr_obj = obj / 'power-sequencer'
        run('power-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
            '--top-module', 'tb_power_sequencer', '--Mdir', str(pwr_obj).replace('\\', '/'),
            'fpga/rtl/sn64_power_sequencer.sv', 'fpga/tests/tb_power_sequencer.sv'])
        pwr_exe = pwr_obj / ('Vtb_power_sequencer.exe' if os.name == 'nt' else 'Vtb_power_sequencer')
        pwr_body = run('power-sequencer', [str(pwr_exe)])
        pwr_pass = next((line for line in pwr_body.splitlines() if line.startswith('PASS:')), None)
        if pwr_pass is None:
            raise RuntimeError('Power sequencer test exited without its acceptance marker')
        report['simulation']['power_sequencer'] = pwr_pass
        # Si5351 start-up and region latch
        clk_obj = obj / 'clock-init'
        run('clock-init-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
            '--top-module', 'tb_clock_init', '--Mdir', str(clk_obj).replace('\\', '/'),
            'fpga/rtl/sn64_clock_init.sv', 'fpga/tests/tb_clock_init.sv'])
        clk_exe = clk_obj / ('Vtb_clock_init.exe' if os.name == 'nt' else 'Vtb_clock_init')
        clk_body = run('clock-init', [str(clk_exe)])
        clk_pass = next((line for line in clk_body.splitlines() if line.startswith('PASS:')), None)
        if clk_pass is None:
            raise RuntimeError('Clock init test exited without its acceptance marker')
        report['simulation']['clock_init'] = clk_pass
        run('clock-init-no-ack', [str(clk_exe), '+wrong_addr'], 'master reported i2c_error on NACK')
        report['simulation']['injected_clock_fault'] = 'Rejected: a non-responding Si5351 is reported as i2c_error'
        # Clock-domain crossing word transfer
        cdc_obj = obj / 'cdc'
        run('cdc-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
            '--top-module', 'tb_cdc', '--Mdir', str(cdc_obj).replace('\\', '/'), 'fpga/rtl/sn64_cdc.sv', 'fpga/tests/tb_cdc.sv'])
        cdc_body = run('cdc', [str(cdc_obj / ('Vtb_cdc.exe' if os.name == 'nt' else 'Vtb_cdc'))])
        cdc_pass = next((line for line in cdc_body.splitlines() if line.startswith('PASS:')), None)
        if cdc_pass is None:
            raise RuntimeError('CDC test exited without its acceptance marker')
        report['simulation']['cdc'] = cdc_pass
        # Whole-system power-on: N64 host, Si5351, rails, cartridge, SNES core, all blocks in sn64_top.
        if (ROOT / 'build/cic/cic-build.json').exists():
            sys_sources = ['-Ibuild/generated/snestang/src', '-Ibuild/generated/snestang/src/spc700',
                           '-Ibuild/generated/snestang/src/65C816', '-f', 'build/core-sources.f',
                           'fpga/rtl/sn64_console_candidate.sv', 'fpga/rtl/sn64_cart_bridge.sv',
                           'fpga/rtl/sn64_console_with_bridge.sv'] + n64_common + [
                           'fpga/rtl/sn64_cdc.sv', 'fpga/rtl/sn64_clock_init.sv', 'fpga/rtl/sn64_power_sequencer.sv',
                           'fpga/rtl/sn64_snes_cic_lock.sv', 'fpga/vendor/snestang-controller/src/controller_adapter.sv',
                           'fpga/rtl/sn64_snes_joypad.sv', 'fpga/rtl/sn64_top.sv', 'fpga/tests/tb_system.sv']
            sys_obj = obj / 'system'
            run('system-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
                '--top-module', 'tb_system', '--Mdir', str(sys_obj).replace('\\', '/')] + sys_sources)
            sys_body = run('system', [str(sys_obj / ('Vtb_system.exe' if os.name == 'nt' else 'Vtb_system'))])
            sys_pass = next((line for line in sys_body.splitlines() if line.startswith('PASS:')), None)
            if sys_pass is None:
                raise RuntimeError('System test exited without its acceptance marker')
            report['simulation']['system'] = sys_pass
        # Controller path: mailbox button images -> emulated standard SNES pads, alone and on the core.
        pad_sources = ['fpga/vendor/snestang-controller/src/controller_adapter.sv',
                       'fpga/rtl/sn64_snes_joypad.sv', 'fpga/tests/tb_snes_joypad.sv']
        pad_obj = obj / 'snes-joypad'
        run('joypad-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
            '--top-module', 'tb_snes_joypad', '--Mdir', str(pad_obj).replace('\\', '/')] + pad_sources)
        pad_body = run('snes-joypad', [str(pad_obj / ('Vtb_snes_joypad.exe' if os.name == 'nt' else 'Vtb_snes_joypad'))])
        pad_pass = next((line for line in pad_body.splitlines() if line.startswith('PASS:')), None)
        if pad_pass is None:
            raise RuntimeError('Joypad protocol test exited without its acceptance marker')
        report['simulation']['snes_joypad'] = pad_pass
        pad_fault_obj = obj / 'snes-joypad-fault'
        run('joypad-fault-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
            '+define+SN64_FAULT_SWAP_BY', '--top-module', 'tb_snes_joypad',
            '--Mdir', str(pad_fault_obj).replace('\\', '/')] + pad_sources)
        run('snes-joypad-swap', [str(pad_fault_obj / ('Vtb_snes_joypad.exe' if os.name == 'nt' else 'Vtb_snes_joypad'))],
            'bit order/ID/trailing 1s')
        report['simulation']['injected_joypad_fault'] = 'Rejected: B/Y swap detected by the serial protocol check'
        core_pad_obj = obj / 'snes-joypad-core'
        run('joypad-core-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
            '+define+SN64_JOYPAD_CORE_TEST', '--top-module', 'tb_snes_joypad_core',
            '--Mdir', str(core_pad_obj).replace('\\', '/'),
            '-Ibuild/generated/snestang/src', '-Ibuild/generated/snestang/src/spc700',
            '-Ibuild/generated/snestang/src/65C816', '-f', 'build/core-sources.f',
            'fpga/rtl/sn64_console_candidate.sv'] + pad_sources)
        core_pad_body = run('snes-joypad-core', [str(core_pad_obj / ('Vtb_snes_joypad_core.exe' if os.name == 'nt' else 'Vtb_snes_joypad_core'))])
        core_pad_pass = next((line for line in core_pad_body.splitlines() if line.startswith('PASS:')), None)
        if core_pad_pass is None:
            raise RuntimeError('Joypad core test exited without its acceptance marker')
        report['simulation']['snes_joypad_core'] = core_pad_pass
        # SNES CIC lock, plus two fault builds that must fail
        scic_src = ['fpga/rtl/sn64_snes_cic_lock.sv', 'fpga/tests/tb_snes_cic_lock.sv']
        scic_obj = obj / 'snes-cic'
        run('snes-cic-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
            '--top-module', 'tb_snes_cic_lock', '--Mdir', str(scic_obj).replace('\\', '/')] + scic_src)
        scic_body = run('snes-cic', [str(scic_obj / ('Vtb_snes_cic_lock.exe' if os.name == 'nt' else 'Vtb_snes_cic_lock'))])
        scic_pass = next((line for line in scic_body.splitlines() if line.startswith('PASS:')), None)
        if scic_pass is None:
            raise RuntimeError('SNES CIC lock test exited without its acceptance marker')
        report['simulation']['snes_cic'] = scic_pass
        for tag, define in (('no-compare', 'SN64_FAULT_CIC_NO_COMPARE'), ('mangle', 'SN64_FAULT_CIC_MANGLE')):
            f_obj = obj / ('snes-cic-' + tag)
            run('snes-cic-' + tag + '-build', [verilator, '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
                '+define+' + define, '--top-module', 'tb_snes_cic_lock', '--Mdir', str(f_obj).replace('\\', '/')] + scic_src)
            run('snes-cic-' + tag, [str(f_obj / ('Vtb_snes_cic_lock.exe' if os.name == 'nt' else 'Vtb_snes_cic_lock'))],
                'FAIL: SNES CIC lock')
        report['simulation']['injected_snes_cic_fault'] = 'Rejected: disabled compare and altered table update are both detected'
        report['simulation']['limit'] = ('Same master clock in all runs; PAL clocks/video and PPU/APU not qualified; '
                                         'bridge bus model is behavioural (no analog levels or translator delays)')

    if args.mode in ('synth', 'all'):
        run('yosys-version', [shutil.which('yosys'), '-V'])
        script = ('plugin -i slang; scratchpad -set abc9.xaiger 1; '
                  'read_slang --top sn64_console_candidate -DVERILATOR '
                  '-Ibuild/generated/snestang/src -Ibuild/generated/snestang/src/spc700 '
                  '-f build/core-sources.f fpga/rtl/sn64_console_candidate.sv; '
                  'synth_ecp5 -top sn64_console_candidate -json build/console-ecp5.json; stat')
        body = run('synthesis', [shutil.which('yosys'), '-Q', '-T', '-p', script])
        netlist = json.loads((ROOT / 'build/console-ecp5.json').read_text())
        top = netlist['modules']['sn64_console_candidate']
        turbo = top['netnames']['console.CPU.TURBO']['bits']
        if turbo != ['0']:
            raise RuntimeError(f'CPU timing control must be tied low, found {turbo}')
        report['synthesis'] = {
            'cells': dict(sorted(Counter(c['type'] for c in top['cells'].values()).items())),
            'normal_cpu_speed_control': turbo,
            'netlist_sha256': sha(ROOT / 'build/console-ecp5.json'),
            'warnings': [s for s in body.splitlines() if 'warning:' in s.lower()],
        }

    if args.mode in ('pnr', 'all'):
        run('nextpnr-version', [shutil.which('nextpnr-ecp5'), '--version'])
        run('placement-route', [shutil.which('nextpnr-ecp5'), '--85k', '--package', 'CABGA381',
            '--speed', '6', '--json', 'build/console-ecp5.json', '--freq', '21.477273',
            '--lpf-allow-unconstrained', '--report', 'build/console-ecp5-pnr.json'])
        pnr = json.loads((ROOT / 'build/console-ecp5-pnr.json').read_text())
        report['placement_route'] = {k: pnr[k] for k in ('fmax', 'utilization') if k in pnr}
        report['placement_route']['constraint_limit'] = 'Unconstrained trial I/O; internal fit experiment only'
        report['placement_route']['netlist_sha256'] = sha(ROOT / 'build/console-ecp5.json')

    output = logs / 'evaluation.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Completed requested experiment: {output}', flush=True)


if __name__ == '__main__':
    main()
