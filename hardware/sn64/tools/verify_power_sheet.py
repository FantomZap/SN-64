"""Independent static review of the SN64 power sheet using a fresh KiCad netlist.

Run with KiCad 10 Python (plain Python 3 also works; pcbnew is not needed):
  python hardware/sn64/tools/verify_power_sheet.py --project <project dir with power sheet attached>
  python hardware/sn64/tools/verify_power_sheet.py --project <dir> --negative-test

The expected pin maps and documented thresholds below are hand-authored from the
datasheets and docs/design/power-schematic.md, not imported from add_power_sheet.py.
Normal mode writes hardware/sn64/validation/power-check.json. --negative-test copies the
project to a temporary directory, applies schematic mutations that must each be caught,
and records the result in the same JSON. This checks static connectivity and divider
arithmetic only; it is not an electrical, thermal, timing or load test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
VALIDATION = HERE.parent / 'validation'
KICAD_CLI = Path('C:/Program Files/KiCad/10.0/bin/kicad-cli.exe')

# ----------------------------------------------------------------------------
# Hand-authored expectations (datasheet pin numbers -> intended SN64 nets).
# None = deliberately unconnected (no-connect marker).
# ----------------------------------------------------------------------------
IC_PINS = {
    # TUSB320I RWB X2QFN-12, TI SLLSEN9F Figure 5-1
    'U301': {'1': 'USB_CC1', '2': 'USB_CC2', '3': 'GND', '4': 'VBUS_DET', '5': None, '6': None, '7': 'TC_OUT1',
             '8': 'TC_OUT2', '9': None, '10': 'GND', '11': 'GND', '12': 'USB_3V3'},
    # TPS259470L RPW: 1 EN/UVLO 2 OVLO 3 AUXOFF 4 FLT 5 IN 6 OUT 7 DVDT 8 GND 9 ILM 10 ITIMER (SLVSFC9C Table 5-1)
    'U302': {'1': 'USB_EN', '2': 'USB_OVLO', '3': 'USB_AUXOFF', '4': 'USB_FLT_N', '5': 'USB_VBUS', '6': 'SYS_VIN',
             '7': 'DVDT_U302', '8': 'GND', '9': 'ILM_U302', '10': 'ITIMER_U302'},
    'U303': {'1': 'HOST_EN', '2': 'HOST_OVLO', '3': 'HOST_AUXOFF', '4': 'HOST_FLT_N', '5': 'HOST_3V3', '6': 'SYS_VIN',
             '7': 'DVDT_U303', '8': 'GND', '9': 'ILM_U303', '10': 'ITIMER_U303'},
    'U309': {'1': 'CART_EN', '2': 'CART_OVLO', '3': 'CART_AUXOFF', '4': 'efuse_fault_n', '5': '5V_PRE',
             '6': 'SNES_5V_CART', '7': 'DVDT_U309', '8': 'GND', '9': 'ILM_U309', '10': 'ITIMER_U309'},
    # TPS63070 RNM: PS/SYNC 1, PG 2, VAUX 3, GND 4, FB 5, FB2 6, VOUT 7/8, L2 9, PGND 10, L1 11, VIN 12/13, EN 14, VSEL 15
    'U304': {'1': 'GND', '2': 'PG_5V', '3': 'VAUX_5V', '4': 'GND', '5': 'FB_5V', '6': None, '7': '5V_PRE', '8': '5V_PRE',
             '9': 'L2_5V', '10': 'GND', '11': 'L1_5V', '12': 'SYS_VIN', '13': 'SYS_VIN', '14': 'SYS_VIN', '15': 'GND'},
    # TLV62569 DBV: EN 1, GND 2, SW 3, VIN 4, FB 5 (SLVSDG1C Pin Functions)
    'U305': {'1': 'PG_5V', '2': 'GND', '3': 'SW_1V1', '4': '5V_PRE', '5': 'FB_1V1'},
    'U306': {'1': 'PG_5V', '2': 'GND', '3': 'SW_2V5', '4': '5V_PRE', '5': 'FB_2V5'},
    'U307': {'1': 'PG_5V', '2': 'GND', '3': 'SW_3V3', '4': '5V_PRE', '5': 'FB_3V3'},
    # TPS22918 DBV: VIN 1, GND 2, ON 3, CT 4, QOD 5, VOUT 6 (SLVSD76C)
    'U308': {'1': 'FPGA_3V3', '2': 'GND', '3': 'iface_rail_enable', '4': 'CT_IFACE', '5': 'QOD_IFACE', '6': 'INTERFACE_3V3'},
    # TPS3808 DBV: RESET 1, GND 2, MR 3, CT 4, SENSE 5, VDD 6 (SBVS050N Figure 5-1)
    'U316': {'1': 'board_reset_n', '2': 'GND', '3': 'fpga_rails_ok', '4': None, '5': 'SENSE_3V3', '6': 'FPGA_3V3'},
    # TMP302 DRL: TRIPSET0 1, GND 2, OUT 3, HYSTSET 4, VS 5, TRIPSET1 6 (SBOS488E)
    'U317': {'1': 'FPGA_3V3', '2': 'GND', '3': 'OT_N', '4': 'FPGA_3V3', '5': 'FPGA_3V3', '6': 'FPGA_3V3'},
    # BSS138BK SOT-23: 1 G, 2 S, 3 D
    'Q301': {'1': 'TC_OUT1', '2': 'GND', '3': 'USB_PERMIT'},
    'Q302': {'1': 'USB_PERMIT', '2': 'GND', '3': 'USB_INHIBIT'},
    'Q303': {'1': 'USB_INHIBIT', '2': 'GND', '3': 'USB_EN'},
    'Q304': {'1': 'USB_AUXOFF', '2': 'GND', '3': 'HOST_EN'},
    'Q305': {'1': 'cart_5v_enable', '2': 'GND', '3': 'CART_INHIBIT'},
    'Q306': {'1': 'CART_INHIBIT', '2': 'GND', '3': 'CART_EN'},
    'Q307': {'1': 'CART_INHIBIT', '2': 'GND', '3': 'CART_DIS'},
    'Q308': {'1': 'OT_N', '2': 'GND', '3': 'overtemp'},
}
# TPS3700 DDC: OUTA 1, GND 2, INA+ 3, INB- 4, VDD 5, OUTB 6 (SBVS187G). (ref, rail, output)
MONITORS = {'U310': ('SYS_VIN', 'host_3v3_ok'), 'U311': ('FPGA_1V1', 'fpga_rails_ok'),
            'U312': ('FPGA_2V5', 'fpga_rails_ok'), 'U313': ('FPGA_3V3', 'fpga_rails_ok'),
            'U314': ('SNES_5V_CART', 'cart_5v_ok'), 'U315': ('INTERFACE_3V3', 'iface_rail_ok')}
VALUES = {'U301': 'TUSB320I', 'U302': 'TPS259470L', 'U303': 'TPS259470L', 'U309': 'TPS259470L', 'U304': 'TPS63070',
          'U305': 'TLV62569', 'U306': 'TLV62569', 'U307': 'TLV62569', 'U308': 'TPS22918', 'U316': 'TPS3808G01',
          'U317': 'TMP302A', **{m: 'TPS3700' for m in MONITORS}, **{f'Q30{i}': 'BSS138' for i in range(1, 9)}}

# Documented thresholds, copied from docs/design/power-schematic.md (volts / amps).
DOC_WINDOWS = {'U310': (2.850, 6.107), 'U311': (1.062, 1.140), 'U312': (2.411, 2.590), 'U313': (3.170, 3.420),
               'U314': (4.751, 5.231), 'U315': (2.998, 3.550)}       # (UV falling, OV rising)
DOC_EFUSE = {'U302': (4.404, 5.796, 1.307), 'U303': (3.000, 3.780, 0.501), 'U309': (4.644, 5.484, 1.004)}  # UVLO, OVLO rising, ILIM
DOC_REG = {'5V_PRE': ('FB_5V', 0.8, 4.999), 'FPGA_1V1': ('FB_1V1', 0.6, 1.100), 'FPGA_2V5': ('FB_2V5', 0.6, 2.500),
           'FPGA_3V3': ('FB_3V3', 0.6, 3.300)}
DOC_SENSE_3V3 = 3.033
REL_TOL = 0.003
# Datasheet constants
TPS3700_VIT_RISE, TPS3700_VIT_FALL = 0.400, 0.3945      # SBVS187G VIT+ typ, VIT+ - Vhys typ
TPS25947_VUVLO_R, TPS25947_RILM_K = 1.20, 3334.0        # SLVSFC9C Eq. 1/2 and Eq. 7
TPS3808_VIT = 0.405                                     # SBVS050N G01 adjustable
ECP5_IPU_MAX = 150e-6                                   # FPGA-DS-02012 IPU max (A)
BSS138BK_VGSTH_MIN = 0.48                               # Nexperia BSS138BK VGSth min, 25 C
TPS22918_VIL_MAX = 0.5                                  # SLVSD76C VIL,ON max
ECP5_VCCIO33_MAX = 3.465                                # FPGA-DS-02012 Table 3.2 VCCIO max
LVCMOS33_VIH = 2.0

CONTRACT = [('host_3v3_ok', 'output'), ('fpga_rails_ok', 'output'), ('cart_5v_ok', 'output'), ('iface_rail_ok', 'output'),
            ('efuse_fault_n', 'output'), ('overtemp', 'output'), ('board_reset_n', 'output'),
            ('cart_5v_enable', 'input'), ('iface_rail_enable', 'input'),
            ('GND', 'passive'), ('HOST_3V3', 'input'), ('USB_VBUS', 'input'), ('USB_3V3', 'input'),
            ('USB_CC1', 'bidirectional'), ('USB_CC2', 'bidirectional'), ('5V_PRE', 'output'), ('FPGA_1V1', 'output'),
            ('FPGA_2V5', 'output'), ('FPGA_3V3', 'output'), ('SNES_5V_CART', 'output'), ('INTERFACE_3V3', 'output')]
SOURCE_RAILS = ['HOST_3V3', 'USB_VBUS', 'USB_3V3', 'SYS_VIN', '5V_PRE', 'SNES_5V_CART', 'FPGA_1V1', 'FPGA_2V5',
                'FPGA_3V3', 'INTERFACE_3V3']


def num(value):
    m = re.match(r'\s*([0-9.]+)\s*([pnumkKM]?)', value)
    if not m:
        raise ValueError(value)
    scale = {'': 1, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'K': 1e3, 'M': 1e6}[m.group(2)]
    return float(m.group(1)) * scale


def export(project, out, kicad_cli):
    p = subprocess.run([str(kicad_cli), 'sch', 'export', 'netlist', '--format', 'kicadxml', '--output', str(out),
                        str(project / 'sn64.kicad_sch')], capture_output=True, text=True)
    return p.returncode == 0 and out.exists(), p.stdout + p.stderr


class Net:
    def __init__(self, xml):
        self.comps = {c.get('ref'): c for c in xml.findall('./components/comp')}
        self.value = {r: c.findtext('value', '') for r, c in self.comps.items()}
        self.pin_net, self.nets, self.dup = {}, {}, []
        for net in xml.findall('./nets/net'):
            name = net.get('name').rsplit('/', 1)[-1]
            members = set()
            for node in net.findall('node'):
                key = (node.get('ref'), node.get('pin'))
                if key in self.pin_net:
                    self.dup.append(key)
                self.pin_net[key] = (name, node.get('pintype', ''))
                members.add(key)
            self.nets.setdefault(name, set()).update(members)

    def net(self, ref, pin):
        return self.pin_net.get((ref, pin), (None, ''))[0]

    def resistors_between(self, a, b):
        out = []
        for r in self.comps:
            if not r.startswith('R'):
                continue
            n = {self.net(r, '1'), self.net(r, '2')}
            if n == {a, b}:
                out.append(r)
        return out

    def resistors_on(self, a):
        return [(r, (self.net(r, '2') if self.net(r, '1') == a else self.net(r, '1'))) for r in self.comps
                if r.startswith('R') and a in (self.net(r, '1'), self.net(r, '2'))]


def run_checks(project, kicad_cli):
    checks = []

    def check(name, ok, detail):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})
    with tempfile.TemporaryDirectory(prefix='sn64-power-') as tmp:
        out = Path(tmp) / 'fresh.xml'
        ok, log = export(project, out, kicad_cli)
        check('fresh_netlist_export', ok, log.strip()[-300:])
        if not ok:
            return checks
        n = Net(ET.parse(out))
    sheet = project / 'power.kicad_sch'
    check('power_sheet_attached', 'U302' in n.comps and 'power.kicad_sch' in (project / 'sn64.kicad_sch').read_text(encoding='utf-8'),
          'power sheet symbol present in root and its parts in the netlist')
    if 'U302' not in n.comps:
        return checks
    check('each_pin_in_one_net', not n.dup, n.dup[:10])
    check('power_parts_present', all(VALUES[r] in n.value.get(r, '') for r in VALUES),
          {r: n.value.get(r) for r in VALUES if VALUES[r] not in n.value.get(r, '')})

    # 1. IC and FET pin maps
    bad = {}
    for ref, pins in IC_PINS.items():
        for pin, want in pins.items():
            got = n.net(ref, pin)
            if want is None:
                if got is not None and len(n.nets.get(got, ())) > 1:
                    bad[f'{ref}.{pin}'] = f'expected no-connect, on {got}'
            elif got != want:
                bad[f'{ref}.{pin}'] = f'expected {want}, got {got}'
    for ref, (rail, outnet) in MONITORS.items():
        for pin, want in {'1': outnet, '2': 'GND', '3': 'MON_A_' + ref, '4': 'MON_B_' + ref, '5': 'FPGA_3V3', '6': outnet}.items():
            if n.net(ref, pin) != want:
                bad[f'{ref}.{pin}'] = f'expected {want}, got {n.net(ref, pin)}'
    check('ic_and_fet_pin_maps', not bad, bad)

    # 2. No source directly paralleled; only reverse-blocking eFuses join inputs to SYS_VIN
    rails = {r: r in n.nets for r in SOURCE_RAILS}
    check('rails_are_distinct_nets', all(rails.values()), rails)
    bridges = {}
    for a, b, allowed in [('HOST_3V3', 'SYS_VIN', {'U303'}), ('USB_VBUS', 'SYS_VIN', {'U302'}),
                          ('HOST_3V3', 'USB_VBUS', set()), ('USB_3V3', 'SYS_VIN', set()),
                          ('HOST_3V3', 'USB_3V3', set()), ('5V_PRE', 'SNES_5V_CART', {'U309', 'R328'}),
                          ('FPGA_3V3', 'INTERFACE_3V3', {'U308'})]:
        refs = {r for r, _ in n.nets.get(a, set())} & {r for r, _ in n.nets.get(b, set())}
        power_bridges = {r for r in refs if not r.startswith(('C', '#', 'TP'))}
        bridges[f'{a}~{b}'] = sorted(power_bridges)
        # R328 is the discharge resistor to CART_DIS, not a 5V_PRE bridge; tolerate only listed parts
        if not power_bridges <= allowed:
            bridges['VIOLATION ' + f'{a}~{b}'] = sorted(power_bridges - allowed)
    sys_feeders = sorted(k for k in n.nets.get('SYS_VIN', set())
                         if n.pin_net[k][1] in ('power_out', 'passive') and k[0].startswith('U'))
    no_parallel = not any(k.startswith('VIOLATION') for k in bridges) and sys_feeders == [('U302', '6'), ('U303', '6')] \
        and 'HOST_3V3' in n.nets and 'USB_VBUS' in n.nets
    check('no_source_directly_paralleled', no_parallel, {'bridges': bridges, 'SYS_VIN_feeders': sys_feeders})
    check('priority_mux_interlock', n.net('Q304', '1') == n.net('U302', '3') and n.net('Q304', '3') == n.net('U303', '1')
          and n.net('Q304', '2') == 'GND', 'U302 AUXOFF -> Q304 gate; Q304 drain clamps U303 EN/UVLO (SLVSFC9C Fig. 8-14)')

    # 3. USB input default-off permission chain
    perm = (n.net('U301', '7') == n.net('Q301', '1') and n.net('Q301', '3') == n.net('Q302', '1')
            and n.resistors_between('USB_3V3', n.net('Q301', '3')) and n.net('Q302', '3') == n.net('Q303', '1')
            and n.resistors_between('USB_VBUS', n.net('Q302', '3')) and n.net('Q303', '3') == n.net('U302', '1')
            and n.resistors_between('USB_3V3', n.net('U301', '7')))
    en_pullups = [o for r, o in n.resistors_on(n.net('U302', '1')) if o not in ('GND', 'USB_VBUS')]
    check('usb_input_default_off_permission', bool(perm) and not en_pullups,
          {'chain_ok': bool(perm), 'unexpected_EN_pullups': en_pullups,
           'logic': 'U302 EN only released when TUSB320 OUT1 low (>=1.5 A) and USB_3V3 present'})
    r_vbd = n.resistors_between('USB_VBUS', 'VBUS_DET')
    addr = n.net('U301', '5')
    straps = (len(r_vbd) == 1 and 855e3 <= num(n.value[r_vbd[0]]) <= 920e3 and n.net('U301', '3') == 'GND'
              and n.net('U301', '11') == 'GND' and (addr is None or len(n.nets.get(addr, ())) == 1)
              and n.net('U301', '12') == 'USB_3V3')
    check('tusb320_straps', straps,
          {'VBUS_DET_R': [n.value[r] for r in r_vbd], 'PORT(UFP=GND)': n.net('U301', '3'), 'EN_N': n.net('U301', '11'),
           'ADDR(open=GPIO)': addr, 'VDD': n.net('U301', '12'), 'source': 'TI SLLSEN9F Table 5-1, RVBUS 855/887/920 k'})

    # 4. Cartridge eFuse default low, discharge
    pd = [r for r in n.resistors_between('cart_5v_enable', 'GND')]
    pu = [o for r, o in n.resistors_on('cart_5v_enable') if o != 'GND']
    vpd = ECP5_IPU_MAX * num(n.value[pd[0]]) if pd else 99
    en_ok = (n.net('Q306', '3') == n.net('U309', '1') and n.net('Q306', '1') == n.net('Q305', '3')
             and n.resistors_between('5V_PRE', n.net('Q305', '3')) and n.net('Q305', '1') == 'cart_5v_enable')
    check('cart_efuse_enable_default_low', bool(en_ok) and bool(pd) and not pu and vpd < BSS138BK_VGSTH_MIN,
          {'pull_down': [n.value[r] for r in pd], 'other_pulls': pu, 'worst_gate_V_with_ECP5_IPU': round(vpd, 3),
           'BSS138BK_VGSth_min': BSS138BK_VGSTH_MIN})
    rdis = n.resistors_between('SNES_5V_CART', 'CART_DIS')
    pdis = (5.5 ** 2 / num(n.value[rdis[0]])) if rdis else 99
    check('cart_rail_discharge_bounded', n.net('Q307', '1') == n.net('Q305', '3') and len(rdis) == 1 and pdis <= 0.125,
          {'R': [n.value[r] for r in rdis], 'P_at_5V5_W': round(pdis, 3)})

    # 5. INTERFACE_3V3 switch default off, discharge path
    ipd = n.resistors_between('iface_rail_enable', 'GND')
    ipu = [o for r, o in n.resistors_on('iface_rail_enable') if o != 'GND']
    vi = ECP5_IPU_MAX * num(n.value[ipd[0]]) if ipd else 99
    check('iface_switch_default_off', bool(ipd) and not ipu and vi < TPS22918_VIL_MAX
          and len(n.resistors_between('QOD_IFACE', 'INTERFACE_3V3')) == 1,
          {'pull_down': [n.value[r] for r in ipd], 'other_pulls': ipu, 'worst_ON_V': round(vi, 3)})

    # 6. Monitors on the socket side of their switches
    top5 = n.resistors_between('SNES_5V_CART', 'MON_A_U314')
    topi = n.resistors_between('INTERFACE_3V3', 'MON_A_U315')
    check('monitors_on_socket_side', len(top5) == 1 and len(topi) == 1 and n.net('U309', '6') == 'SNES_5V_CART'
          and n.net('U308', '6') == 'INTERFACE_3V3' and not n.resistors_between('5V_PRE', 'MON_A_U314'),
          {'cart_top': top5, 'iface_top': topi})

    # 7. Contract labels and directions
    text = sheet.read_text(encoding='utf-8')
    hl = dict(re.findall(r'\(hierarchical_label "([^"]+)" \(shape (\w+)\)', text))
    wrong = {k: hl.get(k) for k, s in CONTRACT if hl.get(k) != s}
    check('contract_signals_present_with_direction', not wrong, wrong)
    pulls = {}
    for name, _ in CONTRACT[:7]:
        others = [o for r, o in n.resistors_on(name)]
        pulls[name] = others
    # Pull-ups only to FPGA_3V3. Since the round-3 integration another sheet may add a default-low
    # pull-down (fpga_rails_ok: R415 100k on the FPGA sheet); allowed only if the divided high level
    # of the open-drain output still meets LVCMOS33_VIH.
    levels = {}
    for k, v in pulls.items():
        if not (set(v) - {'FPGA_3V3'}):
            continue
        up = [num(n.value[r]) for r in n.resistors_between('FPGA_3V3', k)]
        down = [num(n.value[r]) for r in n.resistors_between(k, 'GND')]
        if len(up) == 1 and down and set(v) <= {'FPGA_3V3', 'GND'}:
            rd = 1 / sum(1 / x for x in down)
            levels[k] = round(3.3 * rd / (up[0] + rd), 3)
        else:
            levels[k] = None
    safe = all('FPGA_3V3' in v and set(v) <= {'FPGA_3V3', 'GND'} for k, v in pulls.items()) \
        and all(lv is not None and lv >= LVCMOS33_VIH for lv in levels.values())
    check('monitor_outputs_pulled_to_FPGA_3V3', safe, {'pulls': pulls, 'high_level_with_pulldown_at_3V3': levels})
    # fail-safe: every monitor's supply equals its pull-up rail
    same = all(n.net(m, '5') == 'FPGA_3V3' for m in MONITORS) and n.net('U316', '6') == 'FPGA_3V3' \
        and n.net('U317', '5') == 'FPGA_3V3' and n.resistors_between('FPGA_3V3', 'OT_N')
    check('monitor_supply_equals_pullup_rail', bool(same), 'TPS3700/TPS3808/TMP302 on FPGA_3V3; loss of it removes every pull-up')
    # efuse_fault_n: 5 V must never reach it (no divider from 5V_PRE; DS-02012 section 3.6 back-drive)
    flt_5v = n.resistors_between('5V_PRE', 'efuse_fault_n')
    flt_up = n.resistors_between('FPGA_3V3', 'efuse_fault_n')
    check('efuse_fault_n_pulled_to_FPGA_3V3_not_5V', bool(flt_up) and not flt_5v,
          {'to_FPGA_3V3': flt_up, 'to_5V_PRE': flt_5v})
    ot = n.net('Q308', '3') == 'overtemp' and n.resistors_between('FPGA_3V3', 'overtemp') and n.net('Q308', '1') == 'OT_N'
    check('overtemp_active_high_failsafe', bool(ot), 'TMP302 OUT low (hot) or unpowered -> Q308 off -> overtemp pulled high')
    check('board_reset_chain', n.net('U316', '3') == 'fpga_rails_ok' and n.net('U316', '1') == 'board_reset_n',
          'TPS3808 MR on the FPGA-rail window node; RESET -> board_reset_n (CT open, 12-28 ms)')
    check('regulator_enable_chain', n.net('U304', '14') == 'SYS_VIN' and all(n.net(u, '1') == n.net('U304', '2') for u in ('U305', 'U306', 'U307'))
          and n.resistors_between('5V_PRE', 'PG_5V'), 'TPS63070 PG enables the three TLV62569 bucks')

    # 8. Threshold arithmetic
    calc, bad = {}, {}
    for m, (rail, _) in MONITORS.items():
        a, b = 'MON_A_' + m, 'MON_B_' + m
        r1, r2, r3 = n.resistors_between(rail, a), n.resistors_between(a, b), n.resistors_between(b, 'GND')
        if not (len(r1) == len(r2) == len(r3) == 1):
            bad[m] = 'divider string not found'
            continue
        v1, v2, v3 = (num(n.value[x[0]]) for x in (r1, r2, r3))
        t = v1 + v2 + v3
        uv, ov = TPS3700_VIT_FALL * t / (v2 + v3), TPS3700_VIT_RISE * t / v3
        calc[m] = {'rail': rail, 'UV_fall': round(uv, 4), 'OV_rise': round(ov, 4), 'doc': DOC_WINDOWS[m]}
        if abs(uv / DOC_WINDOWS[m][0] - 1) > REL_TOL or abs(ov / DOC_WINDOWS[m][1] - 1) > REL_TOL:
            bad[m] = calc[m]
    for u, (vin, en, ovlo, ilm) in {'U302': ('USB_VBUS', 'USB_EN', 'USB_OVLO', 'ILM_U302'),
                                    'U303': ('HOST_3V3', 'HOST_EN', 'HOST_OVLO', 'ILM_U303'),
                                    'U309': ('5V_PRE', 'CART_EN', 'CART_OVLO', 'ILM_U309')}.items():
        try:
            ru = [num(n.value[n.resistors_between(vin, en)[0]]), num(n.value[n.resistors_between(en, 'GND')[0]])]
            ro = [num(n.value[n.resistors_between(vin, ovlo)[0]]), num(n.value[n.resistors_between(ovlo, 'GND')[0]])]
            ri = num(n.value[n.resistors_between(ilm, 'GND')[0]])
        except IndexError:
            bad[u] = 'UVLO/OVLO/ILM resistor missing'
            continue
        uvlo, ovl, ilim = TPS25947_VUVLO_R * sum(ru) / ru[1], TPS25947_VUVLO_R * sum(ro) / ro[1], TPS25947_RILM_K / ri
        calc[u] = {'UVLO_rise': round(uvlo, 4), 'OVLO_rise': round(ovl, 4), 'ILIM_A': round(ilim, 4), 'doc': DOC_EFUSE[u]}
        if any(abs(x / d - 1) > REL_TOL for x, d in zip((uvlo, ovl, ilim), DOC_EFUSE[u])):
            bad[u] = calc[u]
    for rail, (fbn, vref, doc) in DOC_REG.items():
        top, bot = n.resistors_between(rail, fbn), n.resistors_between(fbn, 'GND')
        if len(top) != 1 or len(bot) != 1:
            bad[rail] = 'feedback divider not found'
            continue
        v = vref * (1 + num(n.value[top[0]]) / num(n.value[bot[0]]))
        calc[rail] = {'Vout': round(v, 4), 'doc': doc}
        if abs(v / doc - 1) > REL_TOL:
            bad[rail] = calc[rail]
    st, sb = n.resistors_between('FPGA_3V3', 'SENSE_3V3'), n.resistors_between('SENSE_3V3', 'GND')
    if st and sb:
        vs = TPS3808_VIT * (1 + num(n.value[st[0]]) / num(n.value[sb[0]]))
        calc['U316_SENSE'] = {'falling': round(vs, 4), 'doc': DOC_SENSE_3V3}
        if abs(vs / DOC_SENSE_3V3 - 1) > REL_TOL:
            bad['U316'] = calc['U316_SENSE']
    check('divider_values_reproduce_documented_thresholds', not bad, {'mismatch': bad, 'computed': calc})

    # 9. HOST_12V untouched by the power sheet
    h12 = n.net('J1', '13')
    check('HOST_12V_unused', h12 is not None and not any(r.startswith(('U3', 'Q3', 'R3', 'C3')) for r, _ in n.nets.get(h12, ())),
          {'net': h12})
    return checks


def mutate(project, kind, arg):
    """Return mutated power.kicad_sch text for a copy of the project."""
    sys.path.insert(0, str(HERE))
    NS = uuid.UUID('7a3c1e4e-2f5b-4c61-9a0e-5b1d0f6c2d77')      # authoring namespace, used only to locate objects

    def uid(s):
        return str(uuid.uuid5(NS, s))
    t = (project / 'power.kicad_sch').read_text(encoding='utf-8')
    lines = t.split('\n')
    if kind == 'relabel':                    # (pin role, new net)
        role, new = arg
        u = uid('l:' + role)
        i = next(i for i, l in enumerate(lines) if f'(uuid "{u}")' in l)
        lines[i] = re.sub(r'^\(label "[^"]+"', f'(label "{new}"', lines[i])
    elif kind == 'add_label':                # (pin role, extra net name at the same point) -> short
        role, new = arg
        u = uid('l:' + role)
        i = next(i for i, l in enumerate(lines) if f'(uuid "{u}")' in l)
        extra = re.sub(r'^\(label "[^"]+"', f'(label "{new}"', lines[i]).replace(u, str(uuid.uuid4()))
        lines.insert(i + 1, extra)
    elif kind == 'value':                    # (ref, new value)
        ref, new = arg
        i = next(i for i, l in enumerate(lines) if f'(uuid "{uid(ref)}")' in l and l.startswith('(symbol (lib_id'))
        j = next(j for j in range(i, i + 8) if lines[j].startswith('(property "Value"'))
        lines[j] = re.sub(r'^\(property "Value" "[^"]*"', f'(property "Value" "{new}"', lines[j])
    elif kind == 'rename_port':              # (old, new)
        old, new = arg
        i = next(i for i, l in enumerate(lines) if l.startswith(f'(hierarchical_label "{old}"'))
        lines[i] = lines[i].replace(f'"{old}"', f'"{new}"', 1)
    return '\n'.join(lines)


MUTATIONS = [
    ('host_shorted_to_SYS_VIN', 'add_label', ('U302:6', 'HOST_3V3'), 'no_source_directly_paralleled'),
    ('usb_shorted_to_SYS_VIN', 'add_label', ('U303:6', 'USB_VBUS'), 'no_source_directly_paralleled'),
    ('cart_enable_pulled_up', 'relabel', ('R326:2', 'FPGA_3V3'), 'cart_efuse_enable_default_low'),
    ('cart_monitor_on_supply_side', 'relabel', ('R354:1', '5V_PRE'), 'monitors_on_socket_side'),
    ('iface_enable_pulled_up', 'relabel', ('R340:2', 'FPGA_3V3'), 'iface_switch_default_off'),
    ('cart_window_resistor_changed', 'value', ('R356', '40.2k 0.1%'), 'divider_values_reproduce_documented_thresholds'),
    ('usb_ovlo_resistor_changed', 'value', ('R309', '432k 1%'), 'divider_values_reproduce_documented_thresholds'),
    ('contract_signal_renamed', 'rename_port', ('efuse_fault_n', 'efuse_fault'), 'contract_signals_present_with_direction'),
    ('monitor_pullup_to_5V', 'relabel', ('R362:1', '5V_PRE'), 'monitor_outputs_pulled_to_FPGA_3V3'),
    ('usb_permission_bypassed', 'relabel', ('Q303:3', 'USB_EN_X'), 'usb_input_default_off_permission'),
    ('cart_pulldown_too_weak', 'value', ('R326', '100k'), 'cart_efuse_enable_default_low'),
    ('fault_pullup_to_5V', 'relabel', ('R329:1', '5V_PRE'), 'efuse_fault_n_pulled_to_FPGA_3V3_not_5V'),
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project', type=Path, default=HERE.parent)
    ap.add_argument('--kicad-cli', type=Path, default=KICAD_CLI)
    ap.add_argument('--negative-test', action='store_true')
    ap.add_argument('--no-write', action='store_true')
    a = ap.parse_args()
    project = a.project.resolve()
    out_json = VALIDATION / 'power-check.json'
    if a.negative_test:
        results = []
        for name, kind, arg, expect in MUTATIONS:
            with tempfile.TemporaryDirectory(prefix='sn64-power-mut-') as tmp:
                cp = Path(tmp) / 'proj'
                shutil.copytree(project, cp, ignore=shutil.ignore_patterns('exports', '*.xml', 'erc.json'))
                (cp / 'power.kicad_sch').write_text(mutate(project, kind, arg), encoding='utf-8', newline='\n')
                checks = run_checks(cp, a.kicad_cli)
            failed = [c['check'] for c in checks if not c['passed']]
            results.append({'mutation': name, 'expected_failing_check': expect, 'failed_checks': failed,
                            'detected': expect in failed})
            print(f"{'DETECTED' if expect in failed else 'MISSED  '} {name}: failed={failed}")
        ok = all(r['detected'] for r in results)
        summary = {'status': 'pass' if ok else 'fail', 'mutations': len(results),
                   'detected': sum(r['detected'] for r in results), 'results': results,
                   'generated_at_utc': datetime.now(timezone.utc).isoformat()}
        if not a.no_write and out_json.exists():
            data = json.loads(out_json.read_text(encoding='utf-8'))
            data['negative_test'] = summary
            out_json.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        print(('NEGATIVE TEST PASS' if ok else 'NEGATIVE TEST FAIL') + f": {summary['detected']}/{summary['mutations']} mutations detected")
        return 0 if ok else 1
    checks = run_checks(project, a.kicad_cli)
    failed = [c for c in checks if not c['passed']]
    inputs = {p: digest(project / p) for p in ['sn64.kicad_sch', 'power.kicad_sch', 'libraries/SN64_POWER.kicad_sym',
                                               'usb-programmer.kicad_sch', 'cart-interface.kicad_sch'] if (project / p).exists()}
    result = {'status': 'pass' if not failed else 'fail', 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'independent power-sheet static connectivity and divider arithmetic review',
              'project_checked': str(project), 'checks_passed': len(checks) - len(failed), 'checks_failed': len(failed),
              'inputs_sha256': inputs, 'checks': checks,
              'limitations': [
                  'Static schematic connectivity and nominal divider arithmetic only; no load, thermal, ripple, inrush, timing or fault-injection measurement.',
                  'Thresholds use typical reference voltages; worst-case tolerance bands are computed in docs/design/power-schematic.md.',
                  'Cartridge current limit, dVdt and ITIMER values are provisional until cartridge loads are measured.',
                  'Footprints for RPW/RNM packages and the inductors are pending; no PCB exists.']}
    if not a.no_write:
        if out_json.exists():
            old = json.loads(out_json.read_text(encoding='utf-8'))
            if 'negative_test' in old:
                result['negative_test_previous_run'] = old['negative_test']
        VALIDATION.mkdir(exist_ok=True)
        out_json.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'checks_passed': result['checks_passed'], 'checks_failed': len(failed),
                      'failures': [{'check': c['check'], 'detail': c['detail']} for c in failed]}, indent=2))
    print('PASS' if not failed else 'FAIL')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
