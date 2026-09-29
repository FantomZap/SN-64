"""Independent, topology-specific USB programmer review using a fresh KiCad netlist.

Run with KiCad 10 Python so pcbnew can check local footprint pin numbers:
  python hardware/sn64/tools/verify_usb_programmer.py

The assertions below are hand-authored from manufacturer pin tables and the
documented interface contract, not generated CSVs or the schematic builder.
Only writes validation/usb-check.json and validation/usb-review.md. This checks
static connectivity; it is not an electrical, timing, thermal or USB compliance test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import pcbnew


SOURCES = {
    'FT232H_v2_2': 'https://www.ftdichip.cn/Support/Documents/DataSheets/ICs/DS_FT232H.pdf',
    'SN74AXC4T774_revC': 'https://www.ti.com/lit/ds/symlink/sn74axc4t774.pdf',
    'AP2112': 'https://www.diodes.com/datasheet/download/AP2112.pdf',
    'USBLC6_2_rev7': 'https://www.st.com/resource/en/datasheet/usblc6-2.pdf',
    'ABM3B': 'https://abracon.com/Resonators/abm3b.pdf',
    'source_USB_connector_EEPROM': 'https://github.com/Polprzewodnikowy/SummerCart64/blob/a1e7996d2cbece686820a5c785029c68514f17b0/hw/pcb/sc64v2.kicad_sch',
    'programmer_GPIO_contract': 'https://github.com/trabucayre/openFPGALoader/blob/676e53ec73d2261c974d610b7cf0693117c8d2ef/src/ftdipp_mpsse.cpp',
}


def pins(words):
    return {tuple(p.split('.')) for p in words.split()}


# These are physical pins, not net-label expectations. Additional supply flags
# are ignored because they are virtual ERC annotations, not hardware devices.
GROUPS = {
    'USB_VBUS': pins('J101.A4 J101.A9 J101.B4 J101.B9 U101.5 U102.5 U103.1 U103.3 C101.1 C102.1'),
    'USB_DP': pins('J101.A6 J101.B6 U101.3 U101.4 U104.7'),
    'USB_DM': pins('J101.A7 J101.B7 U101.1 U101.6 U104.6'),
    'CC1': pins('J101.A5 R101.1 U102.1 U102.6'),
    'CC2': pins('J101.B5 R102.1 U102.3 U102.4'),
    'USB_3V3': pins('U103.5 U104.12 U104.24 U104.39 U104.40 U104.46 '
                    'U105.1 U105.2 U105.8 U105.16 U106.6 '
                    'C103.1 C106.1 C107.1 C108.1 C109.1 C112.1 C114.1 '
                    'L101.1 L102.1 R104.1 R105.1 R107.1'),
    'FT_VPHY': pins('U104.3 L101.2 C104.1'),
    'FT_VPLL': pins('U104.8 L102.2 C105.1'),
    'FT_VCCA_1V8': pins('U104.37 C110.1'),
    'FT_VCORE_1V8': pins('U104.38 C111.1'),
    'FT_REF': pins('U104.5 R103.1'),
    'FT_RESET': pins('U104.34 R104.2'),
    'XTAL_IN': pins('U104.1 Y101.1 C115.1'),
    'XTAL_OUT': pins('U104.2 Y101.3 C116.1'),
    'FT_TCK_to_A1': pins('U104.13 U105.3'),
    'FT_TDI_to_A2': pins('U104.14 U105.4'),
    'FT_TDO_from_A3': pins('U104.15 U105.5'),
    'FT_TMS_to_A4': pins('U104.16 U105.6'),
    'ACBUS6_OE_N': pins('U104.30 U105.9 R105.2'),
    'B1_TCK_series': pins('U105.14 R108.1'),
    'B2_TDI_series': pins('U105.13 R109.1'),
    'B3_TDO_series': pins('U105.12 R110.1'),
    'B4_TMS_series': pins('U105.11 R111.1'),
    'TARGET_TCK': pins('R108.2 R112.1 J102.3'),
    'TARGET_TDI': pins('R109.2 R113.2 J102.4'),
    'TARGET_TDO': pins('R110.2 J102.5'),
    'TARGET_TMS': pins('R111.2 R114.2 J102.6'),
    'TARGET_VREF': pins('U105.15 C113.1 J102.1 R113.1 R114.1'),
    'EE_CLK': pins('U104.44 U106.4'),
    'EE_CS': pins('U104.45 U106.5'),
    'EE_DATA': pins('U104.43 U106.3 R106.2'),
    'EE_DO': pins('U106.1 R106.1 R107.2'),
    'GROUND': pins('J101.A1 J101.A12 J101.B1 J101.B12 J101.S1 J102.2 '
                   'U101.2 U102.2 U103.2 U104.4 U104.9 U104.10 U104.11 '
                   'U104.22 U104.23 U104.35 U104.36 U104.41 U104.42 U104.47 U104.48 '
                   'U105.7 U105.10 U106.2 Y101.2 Y101.4 R101.2 R102.2 R103.2 R112.2')
              | {(f'C{i}', '2') for i in range(101, 117)},
}
NC = pins('J101.A8 J101.B8 U103.4 U104.17 U104.18 U104.19 U104.20 '
          'U104.21 U104.25 U104.26 U104.27 U104.28 U104.29 U104.31 U104.32 U104.33')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(xml):
    return sorted((n.get('name'), sorted(tuple(sorted(p.attrib.items())) for p in n.findall('node')))
                  for n in xml.findall('./nets/net'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kicad-cli', type=Path, default=Path(sys.executable).with_name('kicad-cli.exe'))
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    validation = project / 'validation'
    checks = []
    def check(name, ok, detail):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})
    try:
        with tempfile.TemporaryDirectory(prefix='sn64-usb-check-') as temp:
            out = Path(temp) / 'fresh.xml'
            process = subprocess.run([str(args.kicad_cli), 'sch', 'export', 'netlist', '--format', 'kicadxml',
                                      '--output', str(out), str(project / 'sn64.kicad_sch')],
                                     capture_output=True, text=True)
            check('fresh_netlist_export', process.returncode == 0 and out.exists(), process.stdout + process.stderr)
            if process.returncode or not out.exists():
                raise RuntimeError('Cannot examine current schematic without a fresh export')
            xml = ET.parse(out)
        check('stored_netlist_current', signature(xml) == signature(ET.parse(validation / 'sn64.xml')),
              'Electrical connectivity and pin types compared with a fresh temporary export.')
        components = {c.get('ref'): c for c in xml.findall('./components/comp')}
        expected_usb_refs = {r for group in GROUPS.values() for r, _ in group} | {r for r, _ in NC}
        check('all_expected_USB_parts_present', expected_usb_refs <= set(components), sorted(expected_usb_refs - set(components)))
        usb_refs = {r for r, c in components.items()
                    if c.find('sheetpath') is not None and 'USB-C programmer' in c.find('sheetpath').get('names', '')}
        check('no_unreviewed_USB_sheet_parts', usb_refs == expected_usb_refs,
              {'extra': sorted(usb_refs - expected_usb_refs), 'missing': sorted(expected_usb_refs - usb_refs)})
        nodes, by_net, duplicates = {}, {}, []
        for net in xml.findall('./nets/net'):
            by_net[net.get('name')] = set()
            for node in net.findall('node'):
                key = (node.get('ref'), node.get('pin'))
                if key in nodes:
                    duplicates.append(key)
                nodes[key] = (net.get('name'), node.attrib)
                by_net[net.get('name')].add(key)
        check('each_pin_in_one_net', not duplicates, duplicates)
        group_names = {}
        for name, expected in GROUPS.items():
            actual_nets = {nodes[p][0] for p in expected if p in nodes}
            missing = sorted(expected - set(nodes))
            actual_pins = set.union(*(by_net[n] for n in actual_nets)) if actual_nets else set()
            actual_usb = {p for p in actual_pins if p[0] in expected_usb_refs}
            ok = len(actual_nets) == 1 and not missing and actual_usb == expected
            check('topology_' + name, ok, {'actual_nets': sorted(actual_nets), 'missing_pins': missing,
                  'unexpected_USB_pins': sorted(actual_usb - expected), 'expected_pin_count': len(expected)})
            if len(actual_nets) == 1:
                group_names[name] = next(iter(actual_nets))
        check('intended_groups_remain_distinct', len(set(group_names.values())) == len(GROUPS),
              {'groups': len(GROUPS), 'distinct_nets': len(set(group_names.values()))})
        check('deliberate_NC_contacts', all(p in nodes and len(by_net[nodes[p][0]]) == 1 and
                                          'no_connect' in nodes[p][1].get('pintype', '') for p in NC), sorted(NC))
        mapped = set.union(*GROUPS.values()) | NC
        actual_usb = {p for p in nodes if p[0] in expected_usb_refs}
        check('all_USB_component_pins_accounted_for', mapped == actual_usb,
              {'mapped': len(mapped), 'actual': len(actual_usb), 'extra': sorted(actual_usb - mapped),
               'missing': sorted(mapped - actual_usb)})

        ground = nodes[('J101', 'A1')][0]
        check('USB_ground_joins_both_cartridge_interfaces',
              ground == nodes[('J1', '1')][0] == nodes[('J2', '5')][0],
              {'USB': ground, 'N64': nodes[('J1', '1')][0], 'SNES': nodes[('J2', '5')][0]})
        crossings = [n for n, ps in by_net.items() if any(r in expected_usb_refs for r, _ in ps)
                     and any(r in ['J1', 'J2'] for r, _ in ps)]
        check('only_ground_directly_crosses_USB_host_boundary', crossings == [ground], crossings)
        rails = {name: nodes[pin][0] for name, pin in {
            'USB_VBUS': ('J101', 'A4'), 'USB_3V3': ('U103', '5'), 'TARGET_VREF': ('U105', '15'),
            'HOST_3V3': ('J1', '9'), 'HOST_12V': ('J1', '13'), 'SNES_5V': ('J2', '27')}.items()}
        check('six_power_domains_distinct', len(set(rails.values())) == 6, rails)

        values = {r: c.findtext('value', '') for r, c in components.items()}
        check('independent_CC_5k1_resistors', values['R101'] == values['R102'] == '5.1k 1%',
              {r: values[r] for r in ['R101', 'R102']})
        check('OE_has_10k_pullup_to_USB_3V3', values['R105'] == '10k', values['R105'])
        check('REF_and_reset_resistors', values['R103'] == '12k 1%' and values['R104'] == '12k',
              {'REF': values['R103'], 'RESET': values['R104']})
        check('JTAG_series_and_target_bias_values', all(values[f'R{i}'] == '33' for i in range(108, 112))
              and all(values[f'R{i}'] == '10k' for i in range(112, 115)),
              {r: values[r] for r in [f'R{i}' for i in range(108, 115)]})
        check('FTDI_and_translator_bypassing', all(values[f'C{i}'] == '100nF' for i in range(104, 115)),
              '100 nF capacitors on filtered PHY/PLL, USB3V3, separate FTDI1V8 outputs, and translator supplies; physical placement untested.')
        check('crystal_and_load_cap_candidate', values['Y101'] == 'ABM3B-12.000MHZ-10-1-U-T'
              and values['C115'] == values['C116'] == '11pF C0G (tune)',
              '12 MHz crystal; both signal electrodes and grounded package pads verified. 11 pF loads require parasitic/startup measurement.')
        check('regulator_fixed_3V3_variant', values['U103'] == 'AP2112K-3.3TRG1', values['U103'])
        check('FT232H_revision_C_qualified', 'rev C' in values['U104'], values['U104'])
        check('EEPROM_really_DNP', any(p.get('name') == 'dnp' for p in components['U106'].findall('property')),
              'KiCad DNP property required in addition to the value text.')
        check('EEPROM_clock_select_are_FTDI_outputs', all(nodes[('U104', p)][1].get('pintype') == 'output' for p in ['44', '45']),
              {p: nodes[('U104', p)][1].get('pintype') for p in ['44', '45']})

        # Pin sets catch a wrong physical package or missing/renumbered pad,
        # without treating the symbol's own name as pinout evidence.
        expected_packages = {'U104': set(map(str, range(1, 49))), 'U105': set(map(str, range(1, 17))),
                             'U103': set(map(str, range(1, 6))), 'U101': set(map(str, range(1, 7))),
                             'U102': set(map(str, range(1, 7))), 'U106': set(map(str, range(1, 7))),
                             'Y101': {'1', '2', '3', '4'}, 'J102': set(map(str, range(1, 7))),
                             'J101': {p for r, p in mapped if r == 'J101'}}
        for ref, expected in expected_packages.items():
            library, name = components[ref].findtext('footprint').split(':', 1)
            fp = pcbnew.FootprintLoad(str(project / 'libraries' / (library + '.pretty')), name)
            actual = {p.GetNumber() for p in fp.Pads() if p.GetNumber()} if fp else set()
            check(ref + '_physical_pad_set', actual == expected, sorted(actual))
        check('service_header_target_side_only',
              nodes[('J102', '1')][0] == nodes[('U105', '15')][0]
              and nodes[('J102', '1')][0] != nodes[('U105', '16')][0],
              'J102 is VTREF,GND,TCK,TDI,TDO,TMS on the target side; it does not expose USB3V3 as target power.')
    except Exception as exc:
        check('validator_execution', False, f'{type(exc).__name__}: {exc}')

    failed = [c for c in checks if not c['passed']]
    limitations = [
        'This checks schematic connectivity against fixed pin tables; it does not prove physical routing, signal integrity, protection performance or USB compliance.',
        'Crystal startup, effective load capacitance and frequency accuracy require layout and prototype measurements. The 11 pF values are explicitly provisional.',
        'The USB supply powers the bridge only. The actual FPGA/flash power, pin allocation and persistent-loading algorithm remain unimplemented.',
        'A fitted EEPROM must preserve the safe ACBUS6 startup contract. Host loading must use the documented --status-pin 14 option.',
        'Target-off leakage, USB/target power sequencing, abnormal process termination/reset, inrush, thermal margin, suspend current and cold-boot persistence require bench tests.',
        'ESD array pin connectivity is checked; this is not a short-to-VBUS/USB-PD protection claim. USB and target supplies have no direct schematic connection to host power.',
    ]
    inputs = ['sn64.kicad_sch', 'usb-programmer.kicad_sch', 'libraries/SN64_USB.kicad_sym']
    result = {'status': 'pass' if not failed else 'fail', 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'independent USB programmer static connectivity review', 'kicad': pcbnew.Version(),
              'checks_passed': len(checks) - len(failed), 'checks_failed': len(failed),
              'inputs': {p: digest(project / p) for p in inputs if (project / p).exists()},
              'sources': SOURCES, 'checks': checks, 'limitations': limitations}
    validation.mkdir(exist_ok=True)
    (validation / 'usb-check.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    lines = ['# Independent USB programmer review', '',
             f"**{result['status'].upper()}**: {result['checks_passed']} checks passed; {len(failed)} failed.", '',
             'Checked a fresh KiCad export against hand-authored manufacturer pin assignments, not the generated CSV or builder script. The checker covers separate CC resistors; DP/DM and ESD pairs; FT232HL supplies, crystal and EEPROM; AXC pin directions and default-disabled /OE; target-side service header; library pad sets; and host/USB rail separation.', '']
    if failed:
        lines += ['Failures:', ''] + [f"- {c['check']}: {c['detail']}" for c in failed] + ['']
    lines += ['Limits:', ''] + ['- ' + x for x in limitations] + ['',
              'Reproduce using KiCad 10 Python: `python hardware/sn64/tools/verify_usb_programmer.py`.', '',
              'See [usb-check.json](usb-check.json) for input hashes, manufacturer source links and detailed results. No hardware measurements were performed.', '']
    (validation / 'usb-review.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'checks_passed': result['checks_passed'], 'checks_failed': len(failed), 'failures': failed}, indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
