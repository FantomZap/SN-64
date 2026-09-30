"""Independent check of the two-board socket joint.

Exports both projects' netlists with kicad-cli and checks, pin by pin, that the main board's J2
(joint header) and the socket board's J2 (joint socket) carry the same net on every pin, that the
socket board's J1 (the real SNES socket) is wired 1:1 to joint pins 1-62, that joint pins 63-66 are
cartridge 5 V and 67-80 GND on both boards, and that the socket footprint reproduces the OpenSFC
CartSlot geometry (rows 7.0 mm apart, 2.5 mm pitch with 7.5 mm gaps after contacts 4 and 27, ears
95.0 mm apart). --negative-test applies mutations to a temporary copy of the socket project and
requires the named checks to fail.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAIN = HERE.parent
SOCKET = MAIN.parent / 'sn64-socket'
KICAD_CLI = r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'
EXPECT_EXTRA = {n: 'SNES_5V_CART' for n in range(63, 67)}
EXPECT_EXTRA.update({n: 'GND' for n in range(67, 81)})


def netlist(cli, sch, out):
    subprocess.run([cli, 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', str(out), str(sch)], check=True,
                   capture_output=True)
    root = ET.parse(out).getroot()
    pins = {}      # (ref, pin) -> net name
    fps = {}
    for c in root.find('components'):
        fps[c.get('ref')] = (c.findtext('footprint') or '')
    for net in root.find('nets'):
        name = net.get('name')
        for node in net:
            pins[(node.get('ref'), node.get('pin'))] = name.lstrip('/')   # local labels are reported as /NAME
    return pins, fps


def pad_x(index):
    x = -42.5
    for k in range(1, index):
        x += 7.5 if k in (4, 27) else 2.5
    return round(x, 3)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--kicad-cli', default=KICAD_CLI)
    ap.add_argument('--socket-project', type=Path, default=SOCKET)
    ap.add_argument('--negative-test', action='store_true')
    ap.add_argument('--out', type=Path, default=MAIN / 'validation/socket-joint-check.json')
    a = ap.parse_args()
    if a.negative_test:
        return negative(a)
    result = run(a.kicad_cli, a.socket_project)
    a.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    for c in result['checks']:
        print(('pass ' if c['ok'] else 'FAIL ') + c['name'])
    n_ok = sum(c['ok'] for c in result['checks'])
    print(f'{"PASS" if result["status"] == "pass" else "FAIL"}: {n_ok}/{len(result["checks"])} socket-joint checks')
    return 0 if result['status'] == 'pass' else 1


def run(cli, socket_project):
    with tempfile.TemporaryDirectory(prefix='sn64-joint-') as tmp:
        main_pins, main_fps = netlist(cli, MAIN / 'sn64.kicad_sch', Path(tmp) / 'main.xml')
        sock_pins, sock_fps = netlist(cli, socket_project / 'sn64-socket.kicad_sch', Path(tmp) / 'socket.xml')
    checks = []

    def check(name, ok, detail=None):
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail})

    j2_main = {int(p): n for (r, p), n in main_pins.items() if r == 'J2'}
    j2_sock = {int(p): n for (r, p), n in sock_pins.items() if r == 'J2'}
    j1_sock = {int(p): n for (r, p), n in sock_pins.items() if r == 'J1'}
    check('joint_has_80_pins_on_both_boards', len(j2_main) == 80 and len(j2_sock) == 80, {'main': len(j2_main), 'socket': len(j2_sock)})
    mism = {p: (j2_main.get(p), j2_sock.get(p)) for p in range(1, 81) if j2_main.get(p) != j2_sock.get(p)}
    check('joint_pins_carry_same_net_on_both_boards', not mism, mism)
    wrong = {p: j1_sock.get(p) for p in range(1, 63) if j1_sock.get(p) != j2_sock.get(p)}
    check('socket_contacts_wired_1_to_1_to_joint_pins_1_62', len(j1_sock) == 62 and not wrong, {'count': len(j1_sock), 'wrong': wrong})
    bad = {p: (j2_main.get(p), j2_sock.get(p)) for p, exp in EXPECT_EXTRA.items() if j2_main.get(p) != exp or j2_sock.get(p) != exp}
    check('joint_pins_63_66_5V_and_67_80_GND', not bad, bad)
    check('main_J2_is_the_right_angle_2x40_2mm_header', main_fps.get('J2') == 'Connector_PinHeader_2.00mm:PinHeader_2x40_P2.00mm_Horizontal', main_fps.get('J2'))
    check('socket_J2_is_the_vertical_2x40_2mm_socket', sock_fps.get('J2') == 'Connector_PinSocket_2.00mm:PinSocket_2x40_P2.00mm_Vertical', sock_fps.get('J2'))
    check('socket_J1_uses_console_replacement_footprint', sock_fps.get('J1') == 'SN64:SNES_Slot_Console_7mm', sock_fps.get('J1'))
    # capacitors on the cartridge 5 V
    caps = [r for (r, p), n in sock_pins.items() if r.startswith('C') and n == 'SNES_5V_CART']
    check('socket_board_decoupling_on_cartridge_5V', len(set(caps)) >= 2, sorted(set(caps)))
    # footprint geometry vs OpenSFC
    fp = (MAIN / 'libraries/SN64.pretty/SNES_Slot_Console_7mm.kicad_mod').read_text(encoding='utf-8')
    pads = {int(n): (float(x), float(y)) for n, x, y in re.findall(r'\(pad "(\d+)" thru_hole \w+ \(at ([-\d.]+) ([-\d.]+)\)', fp)}
    geo_bad = {}
    for n in range(1, 63):
        col = n if n <= 31 else n - 31
        exp = (pad_x(col), 3.5 if n <= 31 else -3.5)
        if pads.get(n) != exp:
            geo_bad[n] = (pads.get(n), exp)
    ears = re.findall(r'\(pad "" np_thru_hole circle \(at ([-\d.]+) 0\) \(size ([\d.]+) ([\d.]+)\) \(drill ([\d.]+)\)', fp)
    ear_ok = sorted(float(e[0]) for e in ears) == [-47.5, 47.5] and all(e[1] == '3.2' and e[3] == '3.2' for e in ears)
    check('socket_footprint_matches_OpenSFC_geometry', len(pads) == 62 and not geo_bad and ear_ok, {'pads': len(pads), 'bad': geo_bad, 'ears': ears})
    status = 'pass' if all(c['ok'] for c in checks) else 'fail'
    return {'status': status, 'checks': checks, 'scope': 'static netlist and footprint-geometry review of the two-board joint; nothing built or measured'}


MUTATIONS = [
    ('joint_pin_swapped', lambda t: t.replace('(label "SNES_A0"', '(label "SNES_A1"', 1), 'socket_contacts_wired_1_to_1_to_joint_pins_1_62'),
    ('ground_pin_relabelled_5V', lambda t: t.replace('(label "GND" (at 250.19 218.44 270)', '(label "SNES_5V_CART" (at 250.19 218.44 270)', 1), 'joint_pins_63_66_5V_and_67_80_GND'),
    ('socket_footprint_changed', lambda t: t.replace('SN64:SNES_Slot_Console_7mm', 'SN64:SNES Slot', 1), 'socket_J1_uses_console_replacement_footprint'),
]


def negative(a):
    results = []
    for name, mutate, expect in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix='sn64-joint-mut-') as tmp:
            proj = Path(tmp) / 'sn64-socket'
            shutil.copytree(a.socket_project, proj)
            sch = proj / 'sn64-socket.kicad_sch'
            text = sch.read_text(encoding='utf-8')
            mutated = mutate(text)
            assert mutated != text, name
            sch.write_text(mutated, encoding='utf-8', newline='\n')
            # the copied project must still find the shared libraries
            for f in ('sym-lib-table', 'fp-lib-table'):
                t = (proj / f).read_text(encoding='utf-8').replace('${KIPRJMOD}/../sn64/libraries', (MAIN / 'libraries').as_posix())
                (proj / f).write_text(t, encoding='utf-8', newline='\n')
            r = run(a.kicad_cli, proj)
            failed = [c['name'] for c in r['checks'] if not c['ok']]
            ok = expect in failed
            results.append({'mutation': name, 'expected_failure': expect, 'failed': failed, 'detected': ok})
            print(('DETECTED ' if ok else 'MISSED   ') + name + ': failed=' + str(failed))
    status = 'pass' if all(r['detected'] for r in results) else 'fail'
    out = MAIN / 'validation/socket-joint-negative.json'
    out.write_text(json.dumps({'negative_test': status, 'results': results}, indent=2) + '\n', encoding='utf-8')
    print(f'negative test: {status} ({sum(r["detected"] for r in results)}/{len(results)})')
    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
