"""Check the connector draft against maps and original reference footprints.

Run with KiCad's Python (pcbnew must be importable):
  python verify_interfaces.py --source-root <original-project-with-downloads>

Only writes validation/interface-check.json and validation/interface-review.md.
A fresh netlist is exported into a temporary directory and removed afterwards.
This validates reference consistency, not electrical safety or manufacture.
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

import pcbnew


def sexpr(path):
    tokens = re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', path.read_text(encoding='utf-8-sig'))
    stack, roots = [], []
    for token in tokens:
        if token == '(':
            item = []
            (stack[-1] if stack else roots).append(item)
            stack.append(item)
        elif token == ')':
            if not stack:
                raise ValueError(f'Unbalanced expression in {path}')
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if stack or len(roots) != 1:
        raise ValueError(f'Unbalanced/multiple expressions in {path}')
    return roots[0]


def children(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def child(node, key):
    found = children(node, key)
    return found[0] if found else None


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vector(v):
    return [v.x, v.y]


def pad_record(pad):
    return {
        'position_iu': vector(pad.GetFPRelativePosition()),
        'size_iu': vector(pad.GetSize()),
        'drill_iu': vector(pad.GetDrillSize()),
        'layers': list(pad.GetLayerSet().Seq()),
        'shape': pad.GetShape(), 'attribute': pad.GetAttribute(),
        'angle_deg': pad.GetOrientationDegrees(),
        'roundrect_ratio': pad.GetRoundRectRadiusRatio(),
        'solder_mask_margin_iu': pad.GetLocalSolderMaskMargin(),
    }


def pad_records(footprint):
    pads = list(footprint.Pads())
    result = {p.GetNumber(): pad_record(p) for p in pads}
    if len(result) != len(pads):
        raise ValueError('Duplicate footprint pad numbers')
    return result


def graph_record(node):
    # Ignore identifier/serialization ordering; geometry uses footprint-local coords.
    ignore = {'uuid', 'tstamp'}
    def normalize(x):
        if not isinstance(x, list):
            try:
                return float(x)
            except ValueError:
                return x
        # KiCad 10 serializes legacy (fill solid) polygons as (fill yes).
        if x in [['fill', 'solid'], ['fill', 'yes']]:
            return ['fill', 'yes']
        return [normalize(c) for c in x if not (isinstance(c, list) and c and c[0] in ignore)]
    return json.dumps(normalize(node), sort_keys=True)


def expected_net(ref, signal):
    if signal == 'GND':
        return '/GND'
    if ref == 'J1' and signal == '3V3':
        return '/HOST_3V3'
    if ref == 'J1' and signal == '12V':
        return '/HOST_12V'
    if ref == 'J2' and signal == '+5V_CART':
        return '/SNES_5V_CART'
    suffix = signal[1:] + '_N' if signal.startswith('/') else signal
    return '/' + ('N64_' if ref == 'J1' else 'SNES_') + suffix


def net_signature(xml):
    return sorted((n.get('name'), sorted((p.get('ref'), p.get('pin'), p.get('pinfunction'), p.get('pintype'))
                                       for p in n.findall('node'))) for n in xml.findall('./nets/net'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--kicad-cli', type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    source_root = args.source_root.resolve()
    validation = project / 'validation'
    checks, warnings = [], []

    def check(name, ok, detail):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})

    paths = {
        'schematic': project / 'sn64.kicad_sch',
        'symbol_library': project / 'libraries/SN64.kicad_sym',
        'n64_footprint': project / 'libraries/SN64.pretty/N64_Edge_SC64_Reference.kicad_mod',
        'snes_footprint': project / 'libraries/SN64.pretty/SNES Slot.kicad_mod',
        'n64_source_board': source_root / 'references/downloads/summercart64/hw/pcb/sc64v2.kicad_pcb',
        'snes_source_footprint': source_root / 'references/downloads/sanni/hardware/footprints/!OSCR.pretty/SNES Slot.kicad_mod',
        'n64_map': project / 'interfaces/n64-pin-map.csv',
        'snes_map': project / 'interfaces/snes-pin-map.csv',
    }
    try:
        cli = args.kicad_cli or Path(sys.executable).with_name('kicad-cli.exe')
        if not cli.exists():
            cli = Path(shutil.which('kicad-cli') or '')
        with tempfile.TemporaryDirectory(prefix='sn64-interface-review-') as temp:
            fresh = Path(temp) / 'netlist.xml'
            export = subprocess.run([str(cli), 'sch', 'export', 'netlist', '--format', 'kicadxml',
                                     '--output', str(fresh), str(paths['schematic'])], capture_output=True, text=True)
            check('fresh_kicad_netlist_export', export.returncode == 0 and fresh.exists(),
                  {'exit_code': export.returncode, 'output': (export.stdout + export.stderr).strip()})
            if export.returncode != 0 or not fresh.exists():
                raise RuntimeError('Fresh KiCad netlist export failed')
            xml = ET.parse(fresh)
        stored = ET.parse(validation / 'sn64.xml')
        check('stored_netlist_matches_fresh_export', net_signature(xml) == net_signature(stored),
              'Compared electrical connectivity, pin functions and pin types, ignoring timestamps.')

        maps = {ref: {r['pin']: r for r in csv.DictReader(paths[key].open(encoding='utf-8-sig', newline=''))}
                for ref, key in [('J1', 'n64_map'), ('J2', 'snes_map')]}
        nets = xml.findall('./nets/net')
        actual, duplicates = {}, []
        for net in nets:
            for node in net.findall('node'):
                if node.get('ref') not in maps:
                    continue  # USB and future sheets have their own validators.
                key = (node.get('ref'), node.get('pin'))
                if key in actual:
                    duplicates.append(key)
                actual[key] = (net.get('name'), node.get('pinfunction'), node.get('pintype'))
        expected_keys = {(ref, pin) for ref, rows in maps.items() for pin in rows}
        # Two-board split (tools/split_socket_board.py): J2 on this board is the socket-board joint.
        # Its pins 1-62 are the socket contacts; 63-66 carry the cartridge 5 V and 67-80 GND.
        joint_extra = {('J2', str(n)): ('/SNES_5V_CART' if n <= 66 else '/GND') for n in range(63, 81)}
        joint_actual = {k: v[0] for k, v in actual.items() if k in joint_extra}
        contacts = {k: v for k, v in actual.items() if k not in joint_extra}
        check('all_112_contacts_once', len(contacts) == 112 and set(contacts) == expected_keys and not duplicates,
              {'exported_contacts': len(contacts), 'duplicates': duplicates,
               'missing': sorted(expected_keys - set(contacts)), 'extra': sorted(set(contacts) - expected_keys)})
        check('J2_joint_pins_63_66_5V_67_80_GND', joint_actual == joint_extra,
              {k: v for k, v in joint_actual.items() if joint_extra.get(k) != v} or 'all 18 joint pins as expected')
        mismatches = []
        for ref, rows in maps.items():
            count = 50 if ref == 'J1' else 62
            check(ref + '_complete_map', set(rows) == {str(i) for i in range(1, count + 1)}, count)
            for pin, row in rows.items():
                expected = (expected_net(ref, row['signal']), row['signal'] + '_' + pin, 'passive')
                if actual.get((ref, pin)) != expected:
                    mismatches.append({'ref': ref, 'pin': pin, 'expected': expected, 'actual': actual.get((ref, pin))})
        check('all_112_pin_net_assignments', not mismatches, {'matched': 112 - len(mismatches), 'mismatches': mismatches})

        shared = [n.get('name') for n in nets
                  if {'J1', 'J2'} <= {p.get('ref') for p in n.findall('node')}]
        check('only_ground_crosses_host_snes_domains', shared == ['/GND'], shared)
        # Connector pins only: translator, pull-up and decoupling nodes on the
        # cartridge 5 V rail (cart-interface sheet) are expected and checked by
        # verify_cart_interface.py.
        supplies = {n.get('name'): sorted((p.get('ref'), int(p.get('pin'))) for p in n.findall('node')
                                          if p.get('ref') in maps)
                    for n in nets if n.get('name') in ['/HOST_3V3', '/HOST_12V', '/SNES_5V_CART']}
        check('three_power_domains_separate', supplies == {
            '/HOST_3V3': [('J1', 9), ('J1', 17), ('J1', 34), ('J1', 42)],
            '/HOST_12V': [('J1', 13), ('J1', 38)],
            '/SNES_5V_CART': [('J2', 27), ('J2', 58), ('J2', 63), ('J2', 64), ('J2', 65), ('J2', 66)]}, supplies)
        root_components = [c.get('ref') for c in xml.findall('./components/comp')
                           if c.find('sheetpath').get('names') == '/']
        check('root_cartridge_sheet_has_two_connectors', set(root_components) == {'J1', 'J2'},
              root_components)
        reserved = {str(p) for p in [14, 24, 39, 46, 49]}
        isolated = all(len(n.findall('node')) == 1 for n in nets
                       if any(p.get('ref') == 'J1' and p.get('pin') in reserved for p in n.findall('node')))
        check('reserved_signal_contacts_have_no_driver', isolated,
              'J1.14,24,39,46,49 are individual single-contact labeled nets; host 12 V has only its two edge contacts.')

        library = sexpr(paths['symbol_library'])
        schematic = sexpr(paths['schematic'])
        symbols = {s[1]: s for s in children(library, 'symbol')}
        embedded = {s[1].split(':', 1)[-1]: ['symbol', s[1].split(':', 1)[-1], *s[2:]]
                    for s in children(child(schematic, 'lib_symbols'), 'symbol')}
        check('embedded_symbols_match_reusable_library', embedded == symbols, sorted(symbols))
        # J2 on the main board is the joint symbol: the socket's 62 pins plus 18 joint pins.
        assignments = {'J1': ('N64_Cartridge_Edge_50', 'SN64:N64_Edge_SC64_Reference'),
                       'J2': ('SN64_Socket_Joint_2x40', 'Connector_PinHeader_2.00mm:PinHeader_2x40_P2.00mm_Horizontal')}
        for ref, (symbol_name, footprint_name) in assignments.items():
            symbol = symbols[symbol_name]
            pins = [p for unit in children(symbol, 'symbol') for p in children(unit, 'pin')]
            values = [(child(p, 'number')[1], child(p, 'name')[1], p[1]) for p in pins]
            expected = [(pin, row['signal'], 'passive') for pin, row in maps[ref].items()]
            if ref == 'J2':
                expected += [(str(n), 'SNES_5V_CART' if n <= 66 else 'GND', 'passive') for n in range(63, 81)]
            check(ref + '_library_pin_names_numbers_types', sorted(values) == sorted(expected), len(values))
            component = next(c for c in xml.findall('./components/comp') if c.get('ref') == ref)
            check(ref + '_footprint_binding', component.findtext('footprint') == footprint_name,
                  component.findtext('footprint'))
            for table_name, expected_uri in [('sym-lib-table', '${KIPRJMOD}/libraries/SN64.kicad_sym'),
                                             ('fp-lib-table', '${KIPRJMOD}/libraries/SN64.pretty')]:
                table = sexpr(project / table_name)
                entries = [e for e in children(table, 'lib') if child(e, 'name')[1] == 'SN64']
                check(table_name + '_' + ref, len(entries) == 1 and child(entries[0], 'uri')[1] == expected_uri,
                      expected_uri)

        source_board = pcbnew.LoadBoard(str(paths['n64_source_board']))
        original = next(f for f in source_board.GetFootprints() if f.GetReference() == 'J_N1')
        copied = pcbnew.FootprintLoad(str(paths['n64_footprint'].parent), paths['n64_footprint'].stem)
        a, b = pad_records(original), pad_records(copied)
        bad_pads = [pin for pin in set(a) | set(b) if a.get(pin) != b.get(pin)]
        check('n64_all_50_pad_geometries_match_source', not bad_pads and len(a) == len(b) == 50,
              {'source_origin_iu': vector(original.GetPosition()), 'mismatched_pads': sorted(bad_pads),
               'checked': ['relative XY', 'width/height', 'drill', 'copper/mask layers', 'shape', 'pad attribute',
                           'rotation', 'roundrect ratio', 'local solder-mask margin']})
        check('n64_source_side_and_numbering_preserved',
              all(b[str(i)]['layers'] == [pcbnew.B_Cu if i <= 25 else pcbnew.F_Cu] for i in range(1, 51)),
              'Pins 1–25 B.Cu; 26–50 F.Cu; 50 independent pad numbers.')
        check('n64_library_has_no_old_nets', all(p.GetNetCode() == 0 and not p.GetNetname() for p in copied.Pads()),
              'All 50 imported pad net assignments are empty.')
        board_ast = sexpr(paths['n64_source_board'])
        fp_ast = next(f for f in children(board_ast, 'footprint')
                      if any(p[1:3] == ['Reference', 'J_N1'] for p in children(f, 'property')))
        copied_ast = sexpr(paths['n64_footprint'])
        for layer in ['F.Mask', 'B.Mask', 'Edge.Cuts']:
            def layer_shapes(fp):
                return sorted(graph_record(g) for g in fp if isinstance(g, list) and g and g[0] in ['fp_line', 'fp_arc', 'fp_poly', 'fp_rect']
                              and child(g, 'layer') and child(g, 'layer')[1] == layer)
            source_shapes, draft_shapes = layer_shapes(fp_ast), layer_shapes(copied_ast)
            check('n64_' + layer + '_geometry_preserved', source_shapes == draft_shapes,
                  {'source_shape_count': len(source_shapes), 'draft_shape_count': len(draft_shapes)})
        check('snes_footprint_byte_identical_to_source',
              paths['snes_footprint'].read_bytes() == paths['snes_source_footprint'].read_bytes(),
              {'sha256': sha256(paths['snes_footprint'])})
        snes = pcbnew.FootprintLoad(str(paths['snes_footprint'].parent), paths['snes_footprint'].stem)
        snes_pads = pad_records(snes)
        check('snes_pad_numbers_1_to_62', set(snes_pads) == {str(i) for i in range(1, 63)}, len(snes_pads))
        check('snes_no_inherited_net_assignment', all(p.GetNetCode() == 0 and not p.GetNetname() for p in snes.Pads()),
              'All 62 socket pads are unassigned library pads.')
        check('snes_through_hole_geometry', all(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in snes.Pads()),
              'Reference socket uses 62 plated through-hole pads; exact pattern preserved by byte-identity.')
        provenance = json.loads((project / 'libraries/provenance.json').read_text(encoding='utf-8'))
        check('source_hashes_match_provenance',
              sha256(paths['n64_source_board']) == provenance['n64_footprint']['source_board_sha256']
              and sha256(paths['snes_source_footprint']) == provenance['snes_footprint']['sha256'],
              'SummerCart64 PCB and Sanni socket source hashes match the recorded pinned sources.')

        warnings.extend([
            'Reference agreement is not a validated SNES socket purchase/fit; no final socket manufacturer part number is selected.',
            'The N64 footprint includes six source Edge.Cuts segments forming an open connector profile; complete the board perimeter without duplicating them.',
            'All connector pins are deliberately passive; ERC cannot establish endpoint direction, power safety, translation or drive-enable correctness.',
            'Only the connector scaffold is checked: no FPGA assignment, power circuitry, timing behavior, complete PCB, host fit or manufacturing release is validated.',
        ])
    except Exception as exc:
        check('validator_execution', False, f'{type(exc).__name__}: {exc}')

    failed = [c for c in checks if not c['passed']]
    result = {
        'status': 'pass' if not failed else 'fail', 'scope': 'connector reference consistency only',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'kicad_python_version': pcbnew.Version(),
        'checks_passed': len(checks) - len(failed), 'checks_failed': len(failed),
        'inputs': {key: {'path': str(path), 'sha256': sha256(path)} for key, path in paths.items() if path.exists()},
        'checks': checks, 'limitations': warnings,
    }
    validation.mkdir(parents=True, exist_ok=True)
    (validation / 'interface-check.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    lines = ['# Independent interface review', '',
             f"Result: **{result['status'].upper()}** — {result['checks_passed']} checks passed; {len(failed)} failed.", '',
             'The validator independently exports the current schematic with KiCad and checks all 112 pin-to-net assignments against both CSV maps. It compares the N64 footprint with J_N1 loaded directly from the original SummerCart64 PCB, including copper sides, pad geometry, mask polygons and connector edge profile. The SNES footprint must be byte-identical to the original Sanni footprint.', '',
             'Only GND may join the two connectors. HOST_3V3, HOST_12V and SNES_5V_CART must remain separate. Both reusable symbols must match the schematic copies and preserve all pin numbers and names.', '']
    if failed:
        lines += ['Failures:', ''] + [f"- {c['check']}: {c['detail']}" for c in failed] + ['']
    lines += ['Limits:', ''] + ['- ' + w for w in warnings] + ['',
              'Reproduce with KiCad 10 Python: `python hardware/sn64/tools/verify_interfaces.py --source-root <original-project-with-reference-downloads>`.', '',
              'See [machine-readable checks](interface-check.json) for input SHA-256 hashes and per-check evidence. The stored netlist is compared to a fresh export; the PDF was not visually reviewed by this validator.', '']
    (validation / 'interface-review.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    print(json.dumps({'status': result['status'], 'checks_passed': result['checks_passed'], 'checks_failed': len(failed), 'failures': failed}, indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
