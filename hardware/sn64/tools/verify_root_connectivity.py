"""Root-sheet connectivity check for the SN64 KiCad hierarchy (round-3 integration).

Independent of the sheet authoring scripts. It reads the schematic text and a
fresh KiCad netlist export and checks:

  1. every child-sheet hierarchical label has a pin of the same name on its
     sheet symbol in the root, and every sheet pin has a hierarchical label;
  2. every sheet pin carries a same-name root label at the pin (a no-connect
     marker, or nothing, is reported as "pending");
  3. every sheet-pin name has a partner: another sheet pin, or a root label
     somewhere else of the same name (the N64/SNES connector labels). Pins
     without a partner are listed;
  4. every name of the shared net-name contract (docs/design/system-integration.md)
     is ONE net in the fresh netlist and touches every sheet it must connect
     ("both ends"): e.g. osc_25 reaches the A/V sheet oscillator and an ECP5 ball.

Writes validation/root-connectivity-check.json (unless --no-write). Exit 0 and
"PASS" only if every check passes. --negative-test mutates temporary copies of
the project (one fault per copy) and exits 0 only if every fault is detected.

  python hardware/sn64/tools/verify_root_connectivity.py [--project hardware/sn64] [--kicad-cli <exe>]
  python hardware/sn64/tools/verify_root_connectivity.py --negative-test

This is a static connectivity check, not an electrical or timing check.
"""
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
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve()
PROJECT = HERE.parents[1]
KICAD_CLI = r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'

ROOT = '/'
USB, CART, FPGA, POWER, AV = ('/USB-C programmer/', '/SNES cartridge interface/', '/FPGA/', '/Power/',
                              '/AV clock and cartridge audio/')

# Shared net-name contract -> sheets whose components the net must touch.
# N64_AUDIO_L/R and HOST_12V are deliberately left on the edge connector only
# (docs/design/av-clock-schematic.md: no requirement routes audio to the N64;
# HOST_12V unused), so their expected set is the root connector alone.
N64_TO_FPGA = ([f'N64_AD{i}' for i in range(16)] +
               ['N64_ALE_H', 'N64_ALE_L', 'N64_READ_N', 'N64_WRITE_N', 'N64_RESET_N', 'N64_NMI_N',
                'N64_CIC_CLK', 'N64_CIC_DATA', 'N64_PIF_CLK', 'N64_INT_N', 'N64_JOYBUS'])
CONTRACT = {
    'GND': {ROOT, USB, CART, FPGA, POWER, AV},
    'HOST_3V3': {ROOT, FPGA, POWER},
    'HOST_12V': {ROOT},
    'USB_VBUS': {USB, POWER},
    'USB_3V3': {USB, POWER},
    'USB_CC1': {USB, POWER},
    'USB_CC2': {USB, POWER},
    'FPGA_1V1': {POWER, FPGA},
    'FPGA_2V5': {POWER, FPGA},
    'FPGA_3V3': {POWER, FPGA, AV},
    'INTERFACE_3V3': {POWER, CART},
    'SNES_5V_CART': {ROOT, POWER, CART},
    '5V_PRE': {POWER, AV},
    'SNES_AUDIO_L_IN': {ROOT, AV},
    'SNES_AUDIO_R_IN': {ROOT, AV},
    'N64_AUDIO_L': {ROOT},
    'N64_AUDIO_R': {ROOT},
    'TARGET_VREF': {USB, FPGA},
    **{n: {USB, FPGA} for n in ['jtag_tck', 'jtag_tms', 'jtag_tdi', 'jtag_tdo']},
    **{n: {POWER, FPGA} for n in ['cart_5v_enable', 'iface_rail_enable', 'host_3v3_ok', 'fpga_rails_ok',
                                  'cart_5v_ok', 'iface_rail_ok', 'efuse_fault_n', 'overtemp', 'board_reset_n']},
    **{n: {AV, FPGA} for n in ['osc_25', 'si_clk0', 'si_clk1', 'si_scl', 'si_sda',
                               'adc_bck', 'adc_lrck', 'adc_dout']},
    **{n: {ROOT, FPGA} for n in N64_TO_FPGA},
}
PIN_RE = re.compile(r'\(pin "([^"]+)" (\w+) \(at ([-\d.]+) ([-\d.]+)')
HL_RE = re.compile(r'\(hierarchical_label "([^"]+)" \(shape (\w+)\)')


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def expand(name):
    """cart_address[0..23] -> cart_address0 .. cart_address23 (KiCad bus member names)."""
    m = re.fullmatch(r'(.+)\[(\d+)\.\.(\d+)\]', name)
    if not m:
        return [name]
    a, b = int(m.group(2)), int(m.group(3))
    return [f'{m.group(1)}{i}' for i in range(min(a, b), max(a, b) + 1)]


def sheet_blocks(text):
    """(sheetname, sheetfile, [(pin, shape, x, y)]) for every sheet symbol in the root."""
    out = []
    for line in text.splitlines():
        if not line.startswith('(sheet (at '):
            continue
        name = re.search(r'"Sheetname" "([^"]+)"', line).group(1)
        sfile = re.search(r'"Sheetfile" "([^"]+)"', line).group(1)
        body = line.split('(instances', 1)[0]
        out.append((name, sfile, [(m.group(1), m.group(2), m.group(3), m.group(4)) for m in PIN_RE.finditer(body)]))
    return out


def run_checks(project, cli):
    checks = []

    def check(name, ok, detail):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})

    root_text = (project / 'sn64.kicad_sch').read_text(encoding='utf-8')
    blocks = sheet_blocks(root_text)
    labels = [(m.group(1), m.group(2), m.group(3)) for m in
              re.finditer(r'^\(label "([^"]+)" \(at ([-\d.]+) ([-\d.]+)', root_text, re.M)]
    ncs = {(m.group(1), m.group(2)) for m in re.finditer(r'^\(no_connect \(at ([-\d.]+) ([-\d.]+)\)', root_text, re.M)}
    label_at = {(x, y): n for n, x, y in labels}

    # 1. hierarchical labels <-> sheet pins
    mismatch = {}
    for name, sfile, pins in blocks:
        child = (project / sfile).read_text(encoding='utf-8')
        hl = {m.group(1) for m in HL_RE.finditer(child)}
        sp = {p for p, _, _, _ in pins}
        if hl != sp:
            mismatch[sfile] = {'label_without_pin': sorted(hl - sp), 'pin_without_label': sorted(sp - hl)}
    check('hierarchical_labels_match_sheet_pins', not mismatch,
          mismatch or {s: len(p) for _, s, p in blocks})

    # 2. every sheet pin labelled at the root (same name, same point)
    pending, wrong = [], []
    for name, sfile, pins in blocks:
        for p, _, x, y in pins:
            at = label_at.get((x, y))
            if at is None:
                pending.append(f'{sfile}:{p}' + (' (no-connect)' if (x, y) in ncs else ' (nothing)'))
            elif at != p:
                wrong.append(f'{sfile}:{p} labelled {at}')
    check('every_sheet_pin_labelled_at_root', not pending and not wrong, {'pending': pending, 'wrong_name': wrong})

    # 3. partner for every sheet-pin name
    owners = {}
    for name, sfile, pins in blocks:
        for p, _, x, y in pins:
            owners.setdefault(p, []).append((sfile, x, y))
    pin_points = {(x, y) for v in owners.values() for _, x, y in v}
    free_labels = {}
    for n, x, y in labels:
        if (x, y) not in pin_points:
            free_labels.setdefault(n, 0)
            free_labels[n] += 1
    def partnered(p, v):
        if len(v) >= 2 or free_labels.get(p):
            return True
        members = expand(p)       # a bus pin is partnered when every member is labelled elsewhere (e.g. on J2)
        return len(members) > 1 and all(free_labels.get(m) for m in members)
    lonely = sorted(f'{v[0][0]}:{p}' for p, v in owners.items() if not partnered(p, v))
    check('every_sheet_pin_has_a_partner', not lonely, {'no_partner': lonely})

    # 4. contract nets: one net each, touching every expected sheet
    with tempfile.TemporaryDirectory(prefix='sn64-root-conn-') as tmp:
        xml_path = Path(tmp) / 'net.xml'
        r = subprocess.run([str(cli), 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', str(xml_path),
                            str(project / 'sn64.kicad_sch')], capture_output=True, text=True)
        if r.returncode or not xml_path.exists():
            check('fresh_netlist_export', False, (r.stdout + r.stderr)[-400:])
            return checks
        xml = ET.parse(xml_path)
    sheet_of = {c.get('ref'): c.find('sheetpath').get('names') for c in xml.findall('./components/comp')}
    nets = {}
    for n in xml.findall('./nets/net'):
        nets[n.get('name')] = {sheet_of.get(nd.get('ref'), '?') for nd in n.findall('node')}
    cart_lower = sorted({x for m in HL_RE.finditer((project / 'cart-interface.kicad_sch').read_text(encoding='utf-8'))
                         for x in expand(m.group(1)) if m.group(1)[:1].islower()})
    contract = dict(CONTRACT)
    contract.update({n: {CART, FPGA} for n in cart_lower})
    result, bad = {}, {}
    for name, want in sorted(contract.items()):
        hits = [k for k in nets if k.rsplit('/', 1)[-1] == name and (k.count('/') == 1 or k.startswith('/'))]
        root_named = [k for k in hits if k == '/' + name]
        cand = root_named or hits
        if len(cand) != 1:
            bad[name] = {'nets': cand}
            continue
        got = nets[cand[0]]
        result[name] = sorted(got)
        if not want <= got:
            bad[name] = {'net': cand[0], 'missing_sheets': sorted(want - got), 'touches': sorted(got)}
    check('contract_nets_connected_on_both_ends', not bad,
          {'checked': len(contract), 'problems': bad, 'cartridge_contract_names': len(cart_lower)})
    return checks


MUTATIONS = [
    ('root label osc_25 at the FPGA sheet pin replaced by a no-connect', 'root_nc', 'osc_25', 'fpga.kicad_sch',
     {'every_sheet_pin_labelled_at_root', 'contract_nets_connected_on_both_ends'}),
    ('A/V sheet hierarchical label adc_dout renamed', 'child_rename', ('av-clock.kicad_sch', 'adc_dout', 'adc_dout_x'), None,
     {'hierarchical_labels_match_sheet_pins'}),
    ('root label jtag_tck at the USB sheet pin renamed', 'root_rename', 'jtag_tck', 'usb-programmer.kicad_sch',
     {'every_sheet_pin_labelled_at_root', 'contract_nets_connected_on_both_ends'}),
    ('power sheet pin efuse_fault_n removed from the root sheet symbol', 'drop_pin', 'efuse_fault_n', 'power.kicad_sch',
     {'hierarchical_labels_match_sheet_pins', 'every_sheet_pin_has_a_partner', 'contract_nets_connected_on_both_ends'}),
]


def mutate(project, kind, arg, sfile):
    root = project / 'sn64.kicad_sch'
    text = root.read_text(encoding='utf-8')
    if kind == 'child_rename':
        f, old, new = arg
        p = project / f
        t = p.read_text(encoding='utf-8')
        assert t.count(f'(hierarchical_label "{old}" ') == 1
        p.write_text(t.replace(f'(hierarchical_label "{old}" ', f'(hierarchical_label "{new}" '), encoding='utf-8', newline='\n')
        return
    blk = next(b for b in sheet_blocks(text) if b[1] == sfile)
    x, y = next((x, y) for p, _, x, y in blk[2] if p == arg)
    pat = re.compile(r'^\(label "' + re.escape(arg) + r'" \(at ' + re.escape(x) + ' ' + re.escape(y) + r' [^\n]*$', re.M)
    m = pat.search(text)
    assert m, (arg, x, y)
    if kind == 'root_nc':
        text = text[:m.start()] + f'(no_connect (at {x} {y}) (uuid "00000000-0000-4000-8000-000000000001"))' + text[m.end():]
    elif kind == 'root_rename':
        text = text[:m.start()] + m.group(0).replace(f'(label "{arg}"', f'(label "{arg}_x"', 1) + text[m.end():]
    elif kind == 'drop_pin':
        text = text[:m.start()] + text[m.end():]
        text = re.sub(r'\(pin "' + re.escape(arg) + r'" \w+ \(at ' + re.escape(x) + ' ' + re.escape(y) + r' [^)]*\) '
                      r'\(effects \(font \(size [\d.]+ [\d.]+\)\) \(justify \w+\)\) \(uuid "[^"]+"\)\) ?', '', text, count=1)
    root.write_text(text, encoding='utf-8', newline='\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project', type=Path, default=PROJECT)
    ap.add_argument('--kicad-cli', type=Path, default=Path(KICAD_CLI))
    ap.add_argument('--negative-test', action='store_true')
    ap.add_argument('--no-write', action='store_true')
    a = ap.parse_args()
    project = a.project.resolve()
    if a.negative_test:
        results = []
        for desc, kind, arg, sfile, expect in MUTATIONS:
            with tempfile.TemporaryDirectory(prefix='sn64-root-neg-') as tmp:
                cp = Path(tmp) / 'sn64'
                shutil.copytree(project, cp, ignore=shutil.ignore_patterns('exports', 'validation', '*-backups'))
                mutate(cp, kind, arg, sfile)
                failed = {c['check'] for c in run_checks(cp, a.kicad_cli) if not c['passed']}
            ok = expect <= failed
            results.append({'mutation': desc, 'expected_failures': sorted(expect), 'failed': sorted(failed), 'detected': ok})
            print(('detected ' if ok else 'MISSED   ') + desc + f'  (failed: {sorted(failed)})')
        n_ok = sum(r['detected'] for r in results)
        print(('PASS' if n_ok == len(results) else 'FAIL') + f': negative test, {n_ok}/{len(results)} faults detected')
        if not a.no_write:
            out = project / 'validation' / 'root-connectivity-check.json'
            if out.exists():
                data = json.loads(out.read_text(encoding='utf-8'))
                data['negative_test'] = {'status': 'pass' if n_ok == len(results) else 'fail', 'results': results,
                                         'generated_at_utc': datetime.now(timezone.utc).isoformat()}
                out.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8', newline='\n')
        return 0 if n_ok == len(results) else 1
    checks = run_checks(project, a.kicad_cli)
    failed = [c for c in checks if not c['passed']]
    report = {'status': 'pass' if not failed else 'fail', 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'root hierarchy connectivity: hierarchical labels, sheet pins, root labels and the shared net-name contract',
              'tool': 'hardware/sn64/tools/verify_root_connectivity.py',
              'checks_passed': len(checks) - len(failed), 'checks_failed': len(failed),
              'inputs': {f: sha256(project / f) for f in ['sn64.kicad_sch', 'usb-programmer.kicad_sch', 'cart-interface.kicad_sch',
                                                          'fpga.kicad_sch', 'power.kicad_sch', 'av-clock.kicad_sch']
                         if (project / f).exists()},
              'checks': checks,
              'limitations': ['Static connectivity only: no electrical, level, timing or layout claim.',
                              'N64_AUDIO_L/R and HOST_12V are expected on the edge connector only (reserved / unused).']}
    if not a.no_write:
        (project / 'validation' / 'root-connectivity-check.json').write_text(json.dumps(report, indent=2) + '\n',
                                                                            encoding='utf-8', newline='\n')
    for c in checks:
        print(('pass ' if c['passed'] else 'FAIL ') + c['check'])
        if not c['passed']:
            print('     ' + json.dumps(c['detail'])[:1500])
    print(('PASS' if not failed else 'FAIL') + f': {len(checks) - len(failed)}/{len(checks)} root connectivity checks')
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
