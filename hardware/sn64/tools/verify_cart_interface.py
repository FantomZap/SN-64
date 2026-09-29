"""Independent static check of the SNES cartridge-interface child sheet.

Exports a fresh KiCad netlist and ERC report into a temporary directory and
checks them against tables kept HERE (TI datasheet pinouts and the SN64
signal/bridge-port map), not against the authoring script:

  * all 62 J2 contacts are accounted for, each with the handling its
    snes-pin-map.csv direction requires (driven through a fixed-direction
    translator, variable-direction data octet, sensed, open-drain, biased,
    analog pass-through, ground or cartridge supply);
  * every fixed octet's DIR is strapped to GND (B->A = FPGA->cartridge) and
    the data octet's DIR/OE come from level-safe open-drain control;
  * no 5 V net (cartridge rail, socket contact, translator A side or any net
    reachable from those through a resistor) reaches an FPGA-side label;
  * translator /OE defaults to released (disabled) with the interface rail off
    or the FPGA unconfigured, and /RESET defaults to asserted;
  * component pin identities match fixed datasheet tables; decoupling count;
  * KiCad ERC reports zero errors.

Usage (KiCad's python or any Python 3 with kicad-cli available):
  python verify_cart_interface.py [--project DIR] [--output JSON] [--kicad-cli EXE]
  python verify_cart_interface.py --negative-test   # mutates temp copies; each must FAIL

Writes validation/cart-interface-check.json (unless --output is given). This
is a static schematic check; it proves nothing about timing, SI, ESD or
behavior on hardware.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

SHEET = 'cart-interface.kicad_sch'
FPGA_PREFIX = '/SNES cartridge interface/'

# --- Fixed datasheet tables (independent copy) -------------------------------
# TI SCAS375K Table 4-1 (PW): pin -> name
LVC4245A = {'1': 'VCCA', '2': 'DIR', '11': 'GND', '12': 'GND', '13': 'GND', '22': 'OE', '23': 'VCCB', '24': 'VCCB',
            **{str(2 + i): f'A{i}' for i in range(1, 9)}, **{str(22 - i): f'B{i}' for i in range(1, 9)}}
# TI SCAS414AG Figure 4-2 (PW)
LVC244A = {'1': '1OE', '2': '1A1', '3': '2Y4', '4': '1A2', '5': '2Y3', '6': '1A3', '7': '2Y2', '8': '1A4', '9': '2Y1',
           '10': 'GND', '11': '2A1', '12': '1Y4', '13': '2A2', '14': '1Y3', '15': '2A3', '16': '1Y2', '17': '2A4',
           '18': '1Y1', '19': '2OE', '20': 'VCC'}
# TI SCES296AG / SCES295AB DBV: 1 NC, 2 A (input), 3 GND, 4 Y (open drain), 5 VCC
LVC1G_TYPES = {'2': 'input', '3': 'power_in', '4': 'open_collector', '5': 'power_in'}
NMOS_SOT23 = {'1': 'G', '2': 'S', '3': 'D'}
RPACK = [('1', '8'), ('2', '7'), ('3', '6'), ('4', '5')]

# SN64 bridge-port names for the FPGA side (fpga/rtl/sn64_cart_bridge.sv plus
# the proposed CIC/expansion ports documented in docs/design/cart-interface-schematic.md).
DRIVEN = {**{f'A{i}': f'cart_address{i}' for i in range(24)}, **{f'PA{i}': f'cart_pa{i}' for i in range(8)},
          '/RD': 'cart_rd_n', '/WR': 'cart_wr_n', '/PRD': 'cart_prd_n', '/PWR': 'cart_pwr_n',
          '/ROMSEL': 'cart_romsel_n', '/WRAMSEL': 'cart_wramsel_n', 'REFRESH': 'cart_refresh', 'PHI2': 'cart_phi2',
          'SYSTEM_CLK': 'cart_sysclk', 'CIC_CLK': 'cic_clk', 'CIC_SLAVE_RESET': 'cic_slave_reset',
          'CIC_DATA0': 'cic_data0_out'}
DATA = {f'D{i}': f'cart_data{i}' for i in range(8)}
SENSED = {'/IRQ': 'cart_irq_n', '/RESET': 'cart_reset_n_sense', 'EXPAND': 'expand_sense',
          'CIC_DATA1': 'cic_data1_in', 'CIC_DATA0': 'cic_data0_sense'}
CONTROL = ['ctl_oe_n', 'cic_oe_n', 'data_oe_n', 'data_dir', 'cart_reset_pull_n']
FPGA_LABELS = set(DRIVEN.values()) | set(DATA.values()) | set(SENSED.values()) | set(CONTROL)
RAIL5, RAIL3, GND = '/SNES_5V_CART', 'INTERFACE_3V3', '/GND'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def root_net(signal):
    if signal == 'GND':
        return GND
    if signal == '+5V_CART':
        return RAIL5
    return '/SNES_' + (signal[1:] + '_N' if signal.startswith('/') else signal)


def pin_name(node):
    # KiCad 10 writes pinfunction as <name>_<number>; overbars as ~{...}.
    name = node.get('pinfunction') or ''
    suffix = '_' + node.get('pin', '')
    if name.endswith(suffix):
        name = name[:-len(suffix)]
    return name.replace('~{', '').replace('}', '')


def run_checks(project: Path, cli: Path):
    checks, contacts = [], []

    def check(name, ok, detail=''):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})
        return ok

    with tempfile.TemporaryDirectory(prefix='sn64-cart-if-') as temp:
        net_path, erc_path = Path(temp) / 'net.xml', Path(temp) / 'erc.json'
        sch = project / 'sn64.kicad_sch'
        exp = subprocess.run([str(cli), 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', str(net_path), str(sch)],
                             capture_output=True, text=True)
        if not check('fresh_netlist_export', exp.returncode == 0 and net_path.exists(), (exp.stdout + exp.stderr).strip()[-400:]):
            return checks, contacts, {}
        erc = subprocess.run([str(cli), 'sch', 'erc', '--format', 'json', '--output', str(erc_path), str(sch)],
                             capture_output=True, text=True)
        xml = ET.parse(net_path)
        erc_ok = erc_path.exists()
        erc_data = json.loads(erc_path.read_text(encoding='utf-8')) if erc_ok else {'sheets': []}

    # ---- ERC ----------------------------------------------------------------
    summary = {}
    for sheet in erc_data.get('sheets', []):
        for v in sheet.get('violations', []):
            key = f"{v['severity']}:{v['type']}"
            summary[key] = summary.get(key, 0) + 1
    errors = {k: v for k, v in summary.items() if k.startswith('error:')}
    check('erc_zero_errors', erc_ok and not errors, {'report_written': erc_ok, 'violations_by_type': summary})

    # ---- netlist model ------------------------------------------------------
    comps = {}
    for c in xml.findall('./components/comp'):
        lib = c.find('libsource')
        comps[c.get('ref')] = {'value': c.findtext('value', ''), 'footprint': c.findtext('footprint', ''),
                               'part': lib.get('part') if lib is not None else '',
                               'sheet': c.find('sheetpath').get('names') if c.find('sheetpath') is not None else ''}
    net_of, nodes = {}, {}
    for net in xml.findall('./nets/net'):
        name = net.get('name')
        nodes[name] = []
        for n in net.findall('node'):
            key = (n.get('ref'), n.get('pin'))
            net_of[key] = name
            nodes[name].append({'ref': n.get('ref'), 'pin': n.get('pin'), 'name': pin_name(n),
                                'type': n.get('pintype', '').split('+')[0]})

    def base(name):
        return name.rsplit('/', 1)[-1] if name else name

    child = {r for r, c in comps.items() if 'SNES cartridge interface' in c['sheet']}
    by_part = lambda part: sorted(r for r in child if comps[r]['part'] == part)
    octets, receivers = by_part('SN74LVC4245APW'), by_part('SN74LVC244APW')
    od_buf, od_inv, nmos = by_part('74LVC1G07'), by_part('74LVC1G06'), by_part('2N7002')
    check('expected_part_counts', len(octets) == 7 and len(receivers) == 1 and len(od_buf) == 3 and len(od_inv) == 2 and len(nmos) == 1,
          {'SN74LVC4245A': octets, 'SN74LVC244A': receivers, '1G07': od_buf, '1G06': od_inv, 'NMOS': nmos})

    # Pin identities against the datasheet tables.
    bad = []
    for ref in octets:
        for pin, name in LVC4245A.items():
            actual = next((n['name'] for n in nodes.get(net_of.get((ref, pin)), []) if n['ref'] == ref and n['pin'] == pin), None)
            if actual != name:
                bad.append((ref, pin, name, actual))
    for ref in receivers:
        for pin, name in LVC244A.items():
            actual = next((n['name'] for n in nodes.get(net_of.get((ref, pin)), []) if n['ref'] == ref and n['pin'] == pin), None)
            if actual != name:
                bad.append((ref, pin, name, actual))
    for ref in od_buf + od_inv:
        for pin, typ in LVC1G_TYPES.items():
            actual = next((n['type'] for n in nodes.get(net_of.get((ref, pin)), []) if n['ref'] == ref and n['pin'] == pin), None)
            if actual != typ:
                bad.append((ref, pin, typ, actual))
    for ref in nmos:
        for pin, name in NMOS_SOT23.items():
            actual = next((n['name'] for n in nodes.get(net_of.get((ref, pin)), []) if n['ref'] == ref and n['pin'] == pin), None)
            if actual != name:
                bad.append((ref, pin, name, actual))
    check('pin_identities_match_datasheet_tables', not bad, bad[:20])

    def pin_net(ref, pin):
        return net_of.get((ref, str(pin)))

    def members(net):
        return nodes.get(net, [])

    def resistor_links(net):
        """(other_net, ref, value) for every resistor element with one end on net."""
        out = []
        for n in members(net):
            part = comps.get(n['ref'], {}).get('part')
            if part == 'R':
                other = '2' if n['pin'] == '1' else '1'
                out.append((pin_net(n['ref'], other), n['ref'], comps[n['ref']]['value']))
            elif part == 'R_Pack04':
                for a, b in RPACK:
                    if n['pin'] in (a, b):
                        out.append((pin_net(n['ref'], b if n['pin'] == a else a), n['ref'] + '.' + a + '-' + b, comps[n['ref']]['value']))
        return out

    def has_pull(net, rail):
        return any(o == rail for o, _, _ in resistor_links(net) if o)

    rail3 = next((n for n in nodes if base(n) == RAIL3), None)
    check('interface_rail_distinct_from_cart_rail', rail3 and rail3 != RAIL5 and RAIL5 in nodes,
          {'INTERFACE_3V3': rail3, 'cart_rail': RAIL5})

    # ---- translator groups ----------------------------------------------------
    info = {}
    for ref in octets:
        info[ref] = {'VCCA': pin_net(ref, 1), 'VCCB': {pin_net(ref, 23), pin_net(ref, 24)}, 'DIR': pin_net(ref, 2),
                     'OE': pin_net(ref, 22), 'GND': {pin_net(ref, p) for p in (11, 12, 13)}}
    check('translator_supplies_A5V_B3V3', all(i['VCCA'] == RAIL5 and i['VCCB'] == {rail3} and i['GND'] == {GND} for i in info.values()),
          {r: {'VCCA': i['VCCA'], 'VCCB': sorted(i['VCCB']), 'GND': sorted(i['GND'])} for r, i in info.items()})

    def od_driver(net, family):
        """Return the single open-drain driver of net from the given family, else None."""
        drivers = [n for n in members(net) if n['type'] in ('output', 'tri_state', 'bidirectional', 'open_collector', 'power_out', 'open_emitter')]
        if len(drivers) == 1 and drivers[0]['ref'] in family and drivers[0]['pin'] == '4':
            ref = drivers[0]['ref']
            if pin_net(ref, 5) == rail3 and pin_net(ref, 3) == GND:
                return ref
        return None

    oe_ok, oe_detail = True, {}
    for ref, i in info.items():
        drv = od_driver(i['OE'], od_buf)
        inp = pin_net(drv, 2) if drv else None
        ok = bool(drv) and has_pull(i['OE'], RAIL5) and base(inp) in FPGA_LABELS and has_pull(inp, rail3)
        oe_ok &= ok
        oe_detail[ref] = {'oe_net': i['OE'], 'driver': drv, 'fpga_control': base(inp) if inp else None,
                          'pullup_5V': has_pull(i['OE'], RAIL5), 'input_pullup_3V3_default_disabled': bool(inp) and has_pull(inp, rail3)}
    check('every_OE_pulled_to_cart_5V_via_open_drain_default_disabled', oe_ok, oe_detail)

    # ---- per-contact accounting --------------------------------------------------
    rows = list(csv.DictReader((project / 'interfaces/snes-pin-map.csv').open(encoding='utf-8-sig', newline='')))
    check('pin_map_has_62_contacts', sorted(int(r['pin']) for r in rows) == list(range(1, 63)), len(rows))
    fixed_dirs, data_octets = {}, set()

    def through_series(sock_net):
        links = [(o, r, v) for o, r, v in resistor_links(sock_net) if comps[r.split('.')[0]]['part'] == 'R_Pack04']
        if len(links) != 1:
            return None
        other, rref, value = links[0]
        a_pins = [n for n in members(other) if n['ref'] in octets and re.fullmatch(r'A[1-8]', n['name'])]
        extra = [n for n in members(other) if n['ref'] not in (rref.split('.')[0],) and n not in a_pins]
        if len(a_pins) != 1 or extra:
            return None
        return {'series': rref, 'value': value, 'octet': a_pins[0]['ref'], 'channel': int(a_pins[0]['name'][1:])}

    for row in rows:
        pin, sig, direction = row['pin'], row['signal'], row['direction']
        net = net_of.get(('J2', pin))
        rec = {'pin': int(pin), 'signal': sig, 'csv_direction': direction, 'socket_net': net}
        expected = root_net(sig)
        ok = net == expected
        why = [] if ok else [f'net {net} != {expected}']
        push_pull = [n for n in members(net) if n['type'] in ('output', 'tri_state', 'power_out')] if net else []
        if direction == 'out' or direction == 'bidirectional' or sig == 'CIC_DATA0':
            path = through_series(net) if net else None
            if not path:
                ok = False
                why.append('no single series-resistor path to exactly one SN74LVC4245A A pin')
            else:
                b_net = pin_net(path['octet'], 22 - path['channel'])
                want = DATA.get(sig) or DRIVEN.get(sig)
                rec.update(path, fpga_net=b_net)
                if base(b_net) != want:
                    ok = False
                    why.append(f'B-side net {b_net} != {want}')
                if not (22 <= float(re.match(r'[\d.]+', path['value']).group()) <= 100):
                    ok = False
                    why.append('series value outside 22-100 ohm')
                dnet = info[path['octet']]['DIR']
                if direction == 'bidirectional':
                    data_octets.add(path['octet'])
                    rec['direction_control'] = 'variable (FPGA data_dir via open-drain)'
                else:
                    fixed_dirs[path['octet']] = dnet
                    rec['direction_control'] = 'fixed B->A' if dnet == GND else f'WRONG: DIR on {dnet}'
                    if dnet != GND:
                        ok = False
                        why.append(f'fixed output octet {path["octet"]} DIR strapped to {dnet}, not GND (B->A)')
            if sig == 'CIC_DATA0':
                sensed = [n for n in members(net) if n['ref'] in receivers and re.fullmatch(r'[12]A[1-4]', n['name'])]
                if len(sensed) != 1 or base(pin_net(sensed[0]['ref'], {v: k for k, v in LVC244A.items()}[sensed[0]['name'].replace('A', 'Y')])) != SENSED[sig]:
                    ok = False
                    why.append('CIC_DATA0 release sense path missing')
            rec['handling'] = {'out': 'driven: fixed-direction translator', 'bidirectional': 'data octet: variable DIR + gated OE'}.get(direction, 'driven + sensed (release-capable group OE)')
        elif sig in SENSED:
            sensed = [n for n in members(net) if n['ref'] in receivers and re.fullmatch(r'[12]A[1-4]', n['name'])]
            y_net = None
            if len(sensed) == 1:
                y_name = sensed[0]['name'].replace('A', 'Y')
                y_pin = {v: k for k, v in LVC244A.items()}[y_name]
                y_net = pin_net(sensed[0]['ref'], y_pin)
            rec['fpga_net'] = y_net
            if base(y_net) != SENSED[sig]:
                ok = False
                why.append(f'receiver output {y_net} != {SENSED[sig]}')
            if push_pull:
                ok = False
                why.append(f'push-pull driver on sensed/released line: {push_pull}')
            if any(n['ref'] in octets for n in members(net)):
                ok = False
                why.append('translator attached to a sensed-only line')
            if sig in ('/IRQ', '/RESET', 'EXPAND') and not has_pull(net, RAIL5):
                ok = False
                why.append('missing pull-up/bias to cartridge 5 V')
            if sig == '/RESET':
                q = [n for n in members(net) if n['ref'] in nmos and n['name'] == 'D']
                gate = pin_net(q[0]['ref'], 1) if q else None
                inv = od_driver(gate, od_inv) if gate else None
                ctl = pin_net(inv, 2) if inv else None
                rec['reset_sink'] = {'nmos': q[0]['ref'] if q else None, 'gate': gate, 'gate_driver': inv, 'control': ctl}
                if not (q and pin_net(q[0]['ref'], 2) == GND and has_pull(gate, RAIL5) and inv and base(ctl) == 'cart_reset_pull_n'
                        and has_pull(ctl, GND)):
                    ok = False
                    why.append('reset open-drain sink / default-assert chain incomplete')
            rec['handling'] = {'/IRQ': 'sensed, 5 V pull-up, never driven', '/RESET': 'open-drain NMOS sink + sense, 5 V pull-up',
                               'EXPAND': 'bias (5 V pull-up) + sense', 'CIC_DATA1': 'sensed only (default high-Z)'}[sig]
        elif direction == 'analog_in':
            active = [n for n in members(net) if n['ref'] != 'J2' and comps.get(n['ref'], {}).get('part') != 'TestPoint']
            if active:
                ok = False
                why.append(f'analog audio touches active/digital parts: {active}')
            rec['handling'] = 'analog pass-through (test point only)'
        elif sig == 'GND':
            rec['handling'] = 'ground return'
        elif sig == '+5V_CART':
            vcca = sorted(n['ref'] for n in members(net) if n['name'] == 'VCCA')
            ok = ok and vcca == octets
            rec['handling'] = 'cartridge supply = translator A-side rail (default-off, from power sheet)'
            rec['translator_VCCA_on_rail'] = vcca
        else:
            ok = False
            why.append('unclassified contact')
        rec['passed'] = ok
        if why:
            rec['problems'] = why
        contacts.append(rec)
    check('all_62_J2_contacts_accounted_with_required_handling', all(c['passed'] for c in contacts) and len(contacts) == 62,
          {'passed': sum(c['passed'] for c in contacts), 'failed': [c for c in contacts if not c['passed']]})
    check('fixed_output_octets_DIR_strapped_B_to_A', fixed_dirs and all(v == GND for v in fixed_dirs.values())
          and not (set(fixed_dirs) & data_octets), fixed_dirs)

    d_ok, d_detail = len(data_octets) == 1, {'data_octets': sorted(data_octets)}
    if d_ok:
        ref = next(iter(data_octets))
        dnet = info[ref]['DIR']
        inv = od_driver(dnet, od_inv)
        ctl = pin_net(inv, 2) if inv else None
        d_ok = bool(inv) and has_pull(dnet, RAIL5) and base(ctl) == 'data_dir' and has_pull(ctl, GND)
        d_detail.update(dir_net=dnet, driver=inv, control=ctl,
                        default='data_dir pulled low -> 1G06 output released -> DIR high (A->B, listen)')
    check('data_octet_DIR_level_safe_inverting_open_drain', d_ok, d_detail)

    # ---- no 5 V net reaches an FPGA-side label ----------------------------------
    fpga_nets = {n for n in nodes if n.startswith(FPGA_PREFIX) and base(n) in FPGA_LABELS}
    check('all_FPGA_side_labels_present', {base(n) for n in fpga_nets} == FPGA_LABELS,
          sorted(FPGA_LABELS - {base(n) for n in fpga_nets}))
    five_v = {RAIL5} | {n for n in nodes if any(m['ref'] == 'J2' for m in members(n))} | \
             {pin_net(r, p) for r in octets for p in list(range(3, 11)) + [1, 2, 22]}
    five_v.discard(GND)   # fixed DIR straps sit on GND; ground is common, not a 5 V net
    leaks, seen, frontier = [], set(fpga_nets), list(fpga_nets)
    while frontier:
        net = frontier.pop()
        for m in members(net):
            if m['ref'] == 'J2' or (m['ref'] in octets and m['name'] in ('DIR', 'OE', 'VCCA') or (m['ref'] in octets and m['name'].startswith('A'))):
                leaks.append((net, m['ref'], m['pin']))
        for other, rref, _ in resistor_links(net):
            if other in (rail3, GND) or other is None:
                continue
            if other in five_v:
                leaks.append((net, rref, other))
            elif other not in seen:
                seen.add(other)
                frontier.append(other)
    allowed = []
    for net in fpga_nets:
        for m in members(net):
            part = comps.get(m['ref'], {}).get('part')
            fine = ((m['ref'] in octets and re.fullmatch(r'B[1-8]', m['name'])) or
                    (m['ref'] in receivers and re.fullmatch(r'[12]Y[1-4]', m['name'])) or
                    (m['ref'] in od_buf + od_inv and m['pin'] == '2') or part == 'R')
            if not fine:
                allowed.append((net, m['ref'], m['pin'], m['name']))
    check('no_5V_net_reaches_FPGA_label', not leaks and not allowed and seen == fpga_nets and rail3 not in five_v,
          {'fpga_nets_checked': len(fpga_nets), 'leaks': leaks, 'unexpected_members': allowed})
    pullups5 = sorted({base(n) for n in nodes if has_pull(n, RAIL5)} - {base(RAIL5)})
    check('5V_pullups_only_on_cartridge_side_nets', not ({p for p in pullups5} & FPGA_LABELS), pullups5)

    # ---- decoupling, footprints, sheet wiring --------------------------------------
    supply = {}
    for ref in octets + receivers + od_buf + od_inv:
        for n in [m for net in nodes for m in members(net) if m['ref'] == ref and m['type'] == 'power_in' and m['name'] != 'GND' and m['pin'] != '3']:
            supply[pin_net(ref, n['pin'])] = supply.get(pin_net(ref, n['pin']), 0) + 1
    caps = {}
    for ref in child:
        if comps[ref]['part'] == 'C' and comps[ref]['value'] == '100nF' and pin_net(ref, 2) == GND:
            caps[pin_net(ref, 1)] = caps.get(pin_net(ref, 1), 0) + 1
    check('one_100nF_per_supply_pin', all(caps.get(k, 0) >= v for k, v in supply.items()), {'supply_pins': supply, '100nF_caps': caps})
    missing_fp = sorted(r for r in child if not r.startswith('#') and not comps[r]['footprint'])
    check('every_part_has_footprint', not missing_fp, missing_fp)

    root_text = (project / 'sn64.kicad_sch').read_text(encoding='utf-8')
    child_text = (project / SHEET).read_text(encoding='utf-8')
    sheet_pins = set(re.findall(r'\(pin "([^"]+)" \w+ \(at', root_text.split(f'"{SHEET}"')[0].rsplit('(sheet ', 1)[-1] + root_text.split(f'"{SHEET}"')[1].split('(instances')[0])) if SHEET in root_text else set()
    hier = set(re.findall(r'\(hierarchical_label "([^"]+)"', child_text))
    check('sheet_pins_match_child_hierarchical_labels', sheet_pins and sheet_pins == hier,
          {'only_in_root': sorted(sheet_pins - hier), 'only_in_child': sorted(hier - sheet_pins)})
    return checks, contacts, {'erc': summary}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--output', type=Path)
    ap.add_argument('--kicad-cli', type=Path)
    ap.add_argument('--negative-test', action='store_true', help='mutate temporary copies; every mutation must fail')
    a = ap.parse_args()
    cli = a.kicad_cli or Path(sys.executable).with_name('kicad-cli.exe')
    if not cli.exists():
        cli = Path(shutil.which('kicad-cli') or r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe')
    project = a.project.resolve()

    if a.negative_test:
        # Each mutation edits one label in a temp copy of the project.
        mutations = [
            ('U201 DIR strapped to cartridge 5 V (A->B) instead of GND',
             '(label "GND" (at 38.1 116.84 180)', '(label "SNES_5V_CART" (at 38.1 116.84 180)'),
            ('R206 FPGA-side pull-up moved to cartridge 5 V (5 V reaches ctl_oe_n)',
             '(label "INTERFACE_3V3" (at 165.1 346.71 90)', '(label "SNES_5V_CART" (at 165.1 346.71 90)'),
        ]
        results = []
        for title, old, new in mutations:
            with tempfile.TemporaryDirectory(prefix='sn64-cart-neg-') as temp:
                copy = Path(temp) / 'sn64'
                shutil.copytree(project, copy, ignore=shutil.ignore_patterns('exports', 'validation'))
                (copy / 'interfaces').mkdir(exist_ok=True)
                text = (copy / SHEET).read_text(encoding='utf-8')
                applied = text.count(old) == 1
                (copy / SHEET).write_text(text.replace(old, new), encoding='utf-8', newline='\n')
                checks, _, _ = run_checks(copy, cli)
            failed = [c['check'] for c in checks if not c['passed']]
            results.append({'mutation': title, 'applied': applied, 'detected': bool(failed) and applied, 'failed_checks': failed})
            print(('FAIL (as required): ' if failed else 'NOT DETECTED: ') + title + ' -> ' + ', '.join(failed))
        ok = all(r['detected'] for r in results)
        print(json.dumps({'negative_test': 'pass' if ok else 'fail', 'results': results}, indent=2))
        return 0 if ok else 1

    checks, contacts, extra = run_checks(project, cli)
    failed = [c for c in checks if not c['passed']]
    result = {
        'status': 'pass' if not failed else 'fail',
        'scope': 'static schematic/netlist check of the SNES cartridge-side translation sheet only',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'checks_passed': len(checks) - len(failed), 'checks_failed': len(failed),
        'inputs': {p: sha256(project / p) for p in ['sn64.kicad_sch', SHEET, 'interfaces/snes-pin-map.csv',
                                                    'libraries/SN64_CART.kicad_sym'] if (project / p).exists()},
        'erc_violations_by_type': extra.get('erc', {}),
        'checks': checks, 'j2_contacts': contacts,
        'limitations': [
            'Static connectivity only: no timing, signal-integrity, ESD, power-sequencing or cartridge test was performed.',
            'Component values (33 R damping, 1k/2.2k/10k/100k pulls) are provisional engineering choices, not measured.',
            'FPGA-side pins end at no-connect markers in the root until the FPGA sheet exists; INTERFACE_3V3 has no source yet.',
            'CIC_DATA0 shares its enable with SYSTEM_CLK/CIC_CLK/CIC_SLAVE_RESET; SuperCIC pair-mode drive on CIC_DATA1 is not provided.',
            'Socket-side ESD protection is not yet selected.',
        ]}
    out = a.output or project / 'validation' / 'cart-interface-check.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'status': result['status'], 'checks_passed': result['checks_passed'],
                      'checks_failed': len(failed), 'failures': [c['check'] for c in failed]}, indent=2))
    if not failed:
        print(f"PASS: {result['checks_passed']} cartridge-interface checks; 62/62 J2 contacts accounted; ERC {extra.get('erc')}")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
