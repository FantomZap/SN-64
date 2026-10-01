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
from prepare_flash_pads import generate as prepare_flash_pads


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
        run('simulation-build', [verilator, '--binary', '--timing', '--build-jobs', '16',
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
        run('wram-build', [verilator, '--binary', '--timing', '--build-jobs', '16',
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
        run('bridge-build', [verilator, '--binary', '--timing', '--build-jobs', '16',
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
        run('bridge-fault-build', [verilator, '--binary', '--timing', '--build-jobs', '16',
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
                      'fpga/rtl/sn64_cdc.sv', 'fpga/rtl/sn64_frame_window.sv', 'fpga/rtl/sn64_n64_endpoint.sv'] + serv
        n64_sources = n64_common + ['fpga/tests/tb_n64_endpoint.sv']
        n64_obj = obj / 'n64-endpoint'
        run('n64-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '--top-module', 'tb_n64_endpoint', '--Mdir', str(n64_obj).replace('\\', '/')] + n64_sources)
        n64_exe = n64_obj / ('Vtb_n64_endpoint.exe' if os.name == 'nt' else 'Vtb_n64_endpoint')
        n64_body = run('n64-endpoint', [str(n64_exe)])
        n64_pass = next((line for line in n64_body.splitlines() if line.startswith('PASS:')), None)
        if n64_pass is None:
            raise RuntimeError('N64 endpoint test exited without its acceptance marker')
        report['simulation']['n64_endpoint'] = n64_pass
        # Fault injection: REGION_INFO and REGION_SOURCE swapped in the register decode must be caught.
        n64_fault_obj = obj / 'n64-endpoint-region-swap'
        run('n64-region-swap-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '+define+SN64_FAULT_REGION_SWAP', '--top-module', 'tb_n64_endpoint',
            '--Mdir', str(n64_fault_obj).replace('\\', '/')] + n64_sources)
        run('n64-endpoint-region-swap', [str(n64_fault_obj / ('Vtb_n64_endpoint.exe' if os.name == 'nt' else 'Vtb_n64_endpoint'))],
            'REGION_INFO/REGION_SOURCE read wrong')
        report['simulation']['injected_n64_endpoint_fault'] = 'Rejected: swapped REGION_INFO/REGION_SOURCE decode is detected'
        # Console video path: frame/audio window read by an N64 host model at fast domain-2 timing,
        # plus a fault build (R/B swapped) that must fail.
        fw_src = n64_common + ['fpga/tests/tb_frame_window.sv']
        fw_obj = obj / 'frame-window'
        run('frame-window-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '--top-module', 'tb_frame_window', '--Mdir', str(fw_obj).replace('\\', '/')] + fw_src)
        fw_exe = fw_obj / ('Vtb_frame_window.exe' if os.name == 'nt' else 'Vtb_frame_window')
        fw_body = run('frame-window', [str(fw_exe), '+pwd=5', '+rls=1'])
        fw_pass = next((line for line in fw_body.splitlines() if line.startswith('PASS:')), None)
        if fw_pass is None:
            raise RuntimeError('Frame window test exited without its acceptance marker')
        report['simulation']['frame_window'] = fw_pass
        fwf_obj = obj / 'frame-window-fault'
        run('frame-window-fault-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '+define+SN64_FAULT_FRAME_RB_SWAP', '--top-module', 'tb_frame_window', '--Mdir', str(fwf_obj).replace('\\', '/')] + fw_src)
        run('frame-window-rb-swap', [str(fwf_obj / ('Vtb_frame_window.exe' if os.name == 'nt' else 'Vtb_frame_window')), '+pwd=5', '+rls=1'],
            'FAIL: tb_frame_window')
        report['simulation']['injected_frame_window_fault'] = 'Rejected: swapped red/blue in the RGBA5551 conversion is detected on every pixel'
        prepare_flash_pads()
        # Bootstrap ROM window from the configuration flash: SummerCart64 memory_flash (unmodified) + QSPI flash model.
        flash_sources = n64_common + ['build/generated/summercart64/memory_flash_dq.sv',
                                      'fpga/rtl/sn64_bootrom_flash.sv', 'fpga/tests/tb_bootrom_flash.sv']
        flash_obj = obj / 'bootrom-flash'
        run('bootrom-flash-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '--top-module', 'tb_bootrom_flash', '--Mdir', str(flash_obj).replace('\\', '/')] + flash_sources)
        flash_exe = flash_obj / ('Vtb_bootrom_flash.exe' if os.name == 'nt' else 'Vtb_bootrom_flash')
        flash_body = run('bootrom-flash', [str(flash_exe)])
        flash_pass = next((line for line in flash_body.splitlines() if line.startswith('PASS:')), None)
        if flash_pass is None:
            raise RuntimeError('Bootrom flash test exited without its acceptance marker')
        report['simulation']['bootrom_flash'] = flash_pass
        run('bootrom-flash-corrupt-byte', [str(flash_exe), '+fault=1'], 'got 08a3 expected 085c')
        run('bootrom-flash-wrong-offset', [str(flash_exe), '+fault=2'], 'got ffff expected 6047')
        run('bootrom-flash-late-data', [str(flash_exe), '+fault=3'], 'got 9047 expected 6047')
        report['simulation']['injected_bootrom_flash_faults'] = ('Rejected: a corrupted flash byte, the image 2 bytes off '
                                                                 'FLASH_OFFSET and flash data 40 ns late are all detected')
        # CIC lockout handshake against a console-side model; needs the built firmware image.
        if (ROOT / 'build/cic/cic-build.json').exists():
            cic_obj = obj / 'n64-cic'
            run('cic-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
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
        run('power-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '--top-module', 'tb_power_sequencer', '--Mdir', str(pwr_obj).replace('\\', '/'),
            'fpga/rtl/sn64_power_sequencer.sv', 'fpga/tests/tb_power_sequencer.sv'])
        pwr_exe = pwr_obj / ('Vtb_power_sequencer.exe' if os.name == 'nt' else 'Vtb_power_sequencer')
        pwr_body = run('power-sequencer', [str(pwr_exe)])
        pwr_pass = next((line for line in pwr_body.splitlines() if line.startswith('PASS:')), None)
        if pwr_pass is None:
            raise RuntimeError('Power sequencer test exited without its acceptance marker')
        report['simulation']['power_sequencer'] = pwr_pass
        # Cartridge check before 5 V (reversed-cartridge detection): rail monitor and sequencer against a
        # TLA2528 model and an electrical model of the cartridge rail (docs/design/reversed-cartridge-detection.md)
        chk_src = ['fpga/rtl/sn64_rail_monitor.sv', 'fpga/rtl/sn64_power_sequencer.sv', 'fpga/tests/tb_cart_check.sv']
        chk_name = 'Vtb_cart_check.exe' if os.name == 'nt' else 'Vtb_cart_check'
        chk_obj = obj / 'cart-check'
        run('cart-check-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '--top-module', 'tb_cart_check', '--Mdir', str(chk_obj).replace('\\', '/')] + chk_src)
        chk_body = run('cart-check', [str(chk_obj / chk_name)])
        chk_pass = next((line for line in chk_body.splitlines() if line.startswith('PASS:')), None)
        if chk_pass is None:
            raise RuntimeError('Cartridge check test exited without its acceptance marker')
        report['simulation']['cart_check'] = chk_pass
        # Fault injection: /RESET kept pulled during the check loads the test current (its pull-up hangs
        # from the cartridge rail), and a sequencer that does not enforce a failed check powers a reversed cartridge.
        run('cart-check-reset-kept-pulled', [str(chk_obj / chk_name), '+keep_reset'], 'empty socket failed the check')
        chkf_obj = obj / 'cart-check-not-enforced'
        run('cart-check-not-enforced-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '+define+SN64_FAULT_CHECK_IGNORED', '--top-module', 'tb_cart_check',
            '--Mdir', str(chkf_obj).replace('\\', '/')] + chk_src)
        run('cart-check-not-enforced', [str(chkf_obj / chk_name)], '5 V switched on into a cartridge the check must protect')
        report['simulation']['injected_cart_check_faults'] = ('Rejected: /RESET kept pulled during the check; '
                                                              'a sequencer that does not enforce a failed check')
        # Sigma-delta cartridge-audio ADC (v2: replaces the PCM1808 and the Si5351 start-up test)
        adc_obj = obj / 'sd-adc'
        run('sd-adc-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '--top-module', 'tb_sd_adc', '--Mdir', str(adc_obj).replace('\\', '/'),
            'fpga/rtl/sn64_sd_adc.sv', 'fpga/tests/tb_sd_adc.sv'])
        adc_exe = adc_obj / ('Vtb_sd_adc.exe' if os.name == 'nt' else 'Vtb_sd_adc')
        adc_body = run('sd-adc', [str(adc_exe)])
        adc_pass = next((line for line in adc_body.splitlines() if line.startswith('PASS:')), None)
        if adc_pass is None:
            raise RuntimeError('Sigma-delta ADC test exited without its acceptance marker')
        report['simulation']['sd_adc'] = adc_pass
        # Clock-domain crossing word transfer
        cdc_obj = obj / 'cdc'
        run('cdc-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
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
                           'fpga/rtl/sn64_cdc.sv', 'fpga/rtl/sn64_power_sequencer.sv',
                           'fpga/rtl/sn64_snes_cic_lock.sv', 'fpga/vendor/snestang-controller/src/controller_adapter.sv',
                           'fpga/rtl/sn64_snes_joypad.sv',
                           'fpga/rtl/sn64_header_probe.sv', 'fpga/rtl/sn64_sd_adc.sv', 'fpga/rtl/sn64_audio_mix.sv',
                           'fpga/rtl/sn64_top.sv', 'fpga/tests/tb_system.sv']
            sys_obj = obj / 'system'
            run('system-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
                '-Wno-lint', '-Wno-style', '-Wno-TIMESCALEMOD',
                '--top-module', 'tb_system', '--Mdir', str(sys_obj).replace('\\', '/')] + sys_sources)
            sys_body = run('system', [str(sys_obj / ('Vtb_system.exe' if os.name == 'nt' else 'Vtb_system'))])
            sys_pass = next((line for line in sys_body.splitlines() if line.startswith('PASS:')), None)
            if sys_pass is None:
                raise RuntimeError('System test exited without its acceptance marker')
            report['simulation']['system'] = sys_pass
            # Same system with a PAL (Europe) ROM header and no key CIC: region must come up PAL.
            sys_pal_body = run('system-pal-header', [str(sys_obj / ('Vtb_system.exe' if os.name == 'nt' else 'Vtb_system')), '+pal_header'])
            sys_pal_pass = next((line for line in sys_pal_body.splitlines() if line.startswith('PASS:')), None)
            if sys_pal_pass is None or 'STATUS=54df' not in sys_pal_pass:   # STATUS bit 7 = region PAL
                raise RuntimeError('System PAL-header test did not start in PAL')
            report['simulation']['system_pal_header'] = sys_pal_pass
            # Key CIC in the cartridge: a passing key decides the region and wins over a contradicting ROM header.
            sys_exe = str(sys_obj / ('Vtb_system.exe' if os.name == 'nt' else 'Vtb_system'))
            for key_label, key_args, key_expect in (
                    ('system-pal-key', ['+pal_key', '+ntsc_header'], ('PAL via key CIC', 'STATUS=34df')),
                    ('system-ntsc-key', ['+ntsc_key', '+pal_header'], ('NTSC via key CIC', 'STATUS=345f'))):
                key_body = run(key_label, [sys_exe] + key_args)
                key_pass = next((line for line in key_body.splitlines() if line.startswith('PASS:')), None)
                if key_pass is None or any(x not in key_pass for x in key_expect):
                    raise RuntimeError(f'{key_label}: the key CIC did not decide the region as expected')
                report['simulation'][key_label.replace('-', '_')] = key_pass
            # Negative: a key that fails the exchange must not decide the region (the NTSC header does).
            run('system-pal-key-corrupted', [sys_exe, '+pal_key', '+ntsc_header', '+corrupt_key'],
                'region 0, expected 1 (key CIC > ROM header')
            report['simulation']['injected_system_key_fault'] = ('Rejected: with one corrupted key bit the region falls '
                                                                 'back to the NTSC header and the key-wins check fails')
        # Cartridge audio: I2S receiver (62.5 MHz oversampling) + elastic buffer + saturating mix, against an
        # asynchronous I2S master at +/-500 ppm and at the pinned SNESTang DSP rate; four fault builds must fail.
        aud_src = ['fpga/rtl/sn64_cdc.sv', 'fpga/rtl/sn64_i2s_rx.sv', 'fpga/rtl/sn64_audio_mix.sv', 'fpga/tests/tb_audio_mix.sv']
        aud_exe_name = 'Vtb_audio_mix.exe' if os.name == 'nt' else 'Vtb_audio_mix'
        for tag, define in (('', None), ('-swap-lr', 'SN64_FAULT_AUDIO_SWAP_LR'), ('-no-signext', 'SN64_FAULT_AUDIO_NO_SIGNEXT'),
                            ('-wrap', 'SN64_FAULT_AUDIO_WRAP'), ('-late-sample', 'SN64_FAULT_I2S_LATE_SAMPLE')):
            a_obj = obj / ('audio-mix' + tag)
            run('audio-mix' + tag + '-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal']
                + (['+define+' + define] if define else []) + ['--top-module', 'tb_audio_mix',
                '--Mdir', str(a_obj).replace('\\', '/')] + aud_src)
            if define:
                run('audio-mix' + tag, [str(a_obj / aud_exe_name), '+adc_ppm=0', '+snes_rate=32180'], 'FAIL: tb_audio_mix')
                continue
            for a_label, a_args in (('audio-mix-adc-plus500ppm', ['+adc_ppm=500']),
                                    ('audio-mix-adc-minus500ppm-duty35', ['+adc_ppm=-500', '+duty=35']),
                                    ('audio-mix-snestang-rate', ['+adc_ppm=0', '+snes_rate=32180'])):
                a_body = run(a_label, [str(a_obj / aud_exe_name)] + a_args)
                a_pass = next((line for line in a_body.splitlines() if line.startswith('PASS:')), None)
                if a_pass is None:
                    raise RuntimeError(f'{a_label} exited without its acceptance marker')
                report['simulation'][a_label.replace('-', '_')] = a_pass
        report['simulation']['injected_audio_faults'] = ('Rejected: swapped L/R, missing sign extension, wrap-around instead '
                                                         'of saturation and I2S data sampled after the BCK edge are all detected')
        # Same bench under a four-state simulator (Icarus, from the same OSS CAD Suite) so its no-X check means something.
        iverilog, vvp = shutil.which('iverilog'), shutil.which('vvp')
        if iverilog and vvp:
            iv_out = obj / 'audio-mix-iverilog.vvp'
            run('audio-mix-iverilog-build', [iverilog, '-g2012', '-o', str(iv_out), '-s', 'tb_audio_mix'] + aud_src)
            iv_body = run('audio-mix-iverilog-4state', [vvp, '-n', str(iv_out), '+adc_ppm=0', '+snes_rate=32180'])
            iv_pass = next((line for line in iv_body.splitlines() if line.startswith('PASS:')), None)
            if iv_pass is None:
                raise RuntimeError('audio-mix-iverilog-4state exited without its acceptance marker')
            report['simulation']['audio_mix_iverilog_4state'] = iv_pass
        else:
            report['simulation']['audio_mix_iverilog_4state'] = 'SKIPPED: iverilog/vvp not on PATH'
        # Controller path: mailbox button images -> emulated standard SNES pads, alone and on the core.
        pad_sources = ['fpga/vendor/snestang-controller/src/controller_adapter.sv',
                       'fpga/rtl/sn64_snes_joypad.sv', 'fpga/tests/tb_snes_joypad.sv']
        pad_obj = obj / 'snes-joypad'
        run('joypad-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '--top-module', 'tb_snes_joypad', '--Mdir', str(pad_obj).replace('\\', '/')] + pad_sources)
        pad_body = run('snes-joypad', [str(pad_obj / ('Vtb_snes_joypad.exe' if os.name == 'nt' else 'Vtb_snes_joypad'))])
        pad_pass = next((line for line in pad_body.splitlines() if line.startswith('PASS:')), None)
        if pad_pass is None:
            raise RuntimeError('Joypad protocol test exited without its acceptance marker')
        report['simulation']['snes_joypad'] = pad_pass
        pad_fault_obj = obj / 'snes-joypad-fault'
        run('joypad-fault-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '+define+SN64_FAULT_SWAP_BY', '--top-module', 'tb_snes_joypad',
            '--Mdir', str(pad_fault_obj).replace('\\', '/')] + pad_sources)
        run('snes-joypad-swap', [str(pad_fault_obj / ('Vtb_snes_joypad.exe' if os.name == 'nt' else 'Vtb_snes_joypad'))],
            'bit order/ID/trailing 1s')
        report['simulation']['injected_joypad_fault'] = 'Rejected: B/Y swap detected by the serial protocol check'
        core_pad_obj = obj / 'snes-joypad-core'
        run('joypad-core-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
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
        run('snes-cic-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '--top-module', 'tb_snes_cic_lock', '--Mdir', str(scic_obj).replace('\\', '/')] + scic_src)
        scic_body = run('snes-cic', [str(scic_obj / ('Vtb_snes_cic_lock.exe' if os.name == 'nt' else 'Vtb_snes_cic_lock'))])
        scic_pass = next((line for line in scic_body.splitlines() if line.startswith('PASS:')), None)
        if scic_pass is None:
            raise RuntimeError('SNES CIC lock test exited without its acceptance marker')
        report['simulation']['snes_cic'] = scic_pass
        for tag, define in (('no-compare', 'SN64_FAULT_CIC_NO_COMPARE'), ('mangle', 'SN64_FAULT_CIC_MANGLE')):
            f_obj = obj / ('snes-cic-' + tag)
            run('snes-cic-' + tag + '-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
                '+define+' + define, '--top-module', 'tb_snes_cic_lock', '--Mdir', str(f_obj).replace('\\', '/')] + scic_src)
            run('snes-cic-' + tag, [str(f_obj / ('Vtb_snes_cic_lock.exe' if os.name == 'nt' else 'Vtb_snes_cic_lock'))],
                'FAIL: SNES CIC lock')
        report['simulation']['injected_snes_cic_fault'] = 'Rejected: disabled compare and altered table update are both detected'
        # ROM-header region probe, plus two fault builds that must fail
        hdr_src = ['fpga/rtl/sn64_header_probe.sv', 'fpga/tests/tb_header_probe.sv']
        hdr_obj = obj / 'header-probe'
        run('header-probe-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
            '--top-module', 'tb_header_probe', '--Mdir', str(hdr_obj).replace('\\', '/')] + hdr_src)
        hdr_body = run('header-probe', [str(hdr_obj / ('Vtb_header_probe.exe' if os.name == 'nt' else 'Vtb_header_probe'))])
        hdr_pass = next((line for line in hdr_body.splitlines() if line.startswith('PASS:')), None)
        if hdr_pass is None:
            raise RuntimeError('Header probe test exited without its acceptance marker')
        report['simulation']['header_probe'] = hdr_pass
        for tag, define in (('skip-checksum', 'SN64_FAULT_SKIP_CHECKSUM'), ('short-access', 'TB_SHORT_ACCESS')):
            f_obj = obj / ('header-probe-' + tag)
            run('header-probe-' + tag + '-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal',
                '+define+' + define, '--top-module', 'tb_header_probe', '--Mdir', str(f_obj).replace('\\', '/')] + hdr_src)
            run('header-probe-' + tag, [str(f_obj / ('Vtb_header_probe.exe' if os.name == 'nt' else 'Vtb_header_probe'))],
                'FAIL: tb_header_probe')
        report['simulation']['injected_header_fault'] = ('Rejected: skipped checksum validation and a too-short read strobe '
                                                         'are both detected')
        # SNES CIC pad direction sequencing (SN74LVC1T45 per pin), plus a fault build that must fail
        cpad_src = ['fpga/rtl/sn64_cic_pad.sv', 'fpga/tests/tb_cic_pad.sv']
        for tag, defines, expect in (('', [], None), ('-order', ['+define+SN64_FAULT_CIC_PAD_ORDER'], 'FAIL: tb_cic_pad')):
            c_obj = obj / ('cic-pad' + tag)
            run('cic-pad' + tag + '-build', [verilator, '--binary', '--timing', '--build-jobs', '16', '-Wno-fatal'] + defines +
                ['--top-module', 'tb_cic_pad', '--Mdir', str(c_obj).replace('\\', '/')] + cpad_src)
            c_body = run('cic-pad' + tag, [str(c_obj / ('Vtb_cic_pad.exe' if os.name == 'nt' else 'Vtb_cic_pad'))], expect)
            if not tag:
                c_pass = next((line for line in c_body.splitlines() if line.startswith('PASS:')), None)
                if c_pass is None:
                    raise RuntimeError('CIC pad test exited without its acceptance marker')
                report['simulation']['cic_pad'] = c_pass
        report['simulation']['injected_cic_pad_fault'] = 'Rejected: pad drive and DIR switching together is detected as contention'
        report['simulation']['limit'] = ('tb_system runs use simulation-time master clocks (NTSC and PAL rates), not the real '
                                         'Si5351 outputs; the console video path is checked against a PI host model, not a '
                                         'console; PPU/APU not qualified; bridge bus model is behavioural (no analog levels or '
                                         'translator delays); the cartridge check runs against an assumed electrical model of the rail and of '
                                         'a cartridge (tb_cart_check), not against measured cartridges')

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
