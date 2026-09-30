"""Independent static checks for the SN64 FPGA sheet, pin map and board LPF.

Exports a KiCad XML netlist and ERC report from a project whose root has the
FPGA sheet attached (after integration: hardware/sn64 itself; before it: the
validation copy made by add_fpga_sheet.py --validation-copy), then checks it
against tables written here from the Lattice ECP5U-85 pinout CSV (rev 1.0,
CABGA381 column), the Lattice checklist/sysCONFIG rules, the W25Q128JV pin
table, the SN74CB3Q3384A pin table and the board-top ports. It does not import
the authoring script. --lattice-csv re-derives the ball tables from the Lattice
file itself and compares them, and every U401 pin name, too.

  python verify_fpga_sheet.py --project build/fpga-sheet/proj --kicad-cli <kicad-cli> \
      [--board-top build/fpga-sheet/rtl/sn64_board_top.sv] [--lattice-csv <ECP5U-85 pinout.csv>]
      [--datasheets <dir>] [--negative-test] [--out hardware/sn64/validation/fpga-check.json]

Exit 0 and "PASS" only if every check passes; --negative-test exits 0 only
if every injected fault is detected by the check(s) named for it.
"""
import argparse
import csv
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

REPO = Path(__file__).resolve().parents[3]

# ------------------------------------------------------------------ Lattice tables
# ECP5U-85 pinout CSV rev 1.0 ("Revised Nov. 2, 2015"), CABGA381 column.
GND_BALLS = ('B14 B7 C19 D4 F13 F14 F7 F8 G10 G11 G12 G13 G14 G15 G17 G4 G6 G7 G8 G9 H19 J10 J11 J12 J14 J2 J7 J9 '
             'K10 K11 K12 K14 K15 K6 K7 K9 L10 L11 L12 L9 M10 M11 M12 M14 M16 M2 M7 M9 N14 N15 N6 N7 P11 P12 P13 '
             'P14 P7 P8 R19 T10 T11 T12 T13 T14 T15 T6 T7 T8 T9 U10 U11 U12 U13 U14 U15 U6 U7 U8 U9 V10 V11 V12 '
             'V13 V14 V15 V16 V17 V18 V19 V20 V5 V6 V7 V8 V9 W12 W15 W16 W19 W20 W6 W7 Y11 Y12 Y14 Y15 Y16 Y17 '
             'Y19 Y5 Y6 Y7 Y8').split()
VCC_BALLS = 'H10 H11 H12 H13 H8 H9 J13 J8 K13 K8 L13 L8 M13 M8 N10 N11 N12 N13 N8 N9'.split()
VCCAUX_BALLS = 'F15 F6 P15 P6'.split()
VCCIO_BALLS = {'0': 'F10 F9', '1': 'F11 F12', '2': 'H14 H15 J15', '3': 'L14 L15 M15', '6': 'L6 L7 M6',
               '7': 'H6 H7 J6', '8': 'P10 P9'}
RESERVED_BALLS = 'W10 W11 W13 W14 W17 W18 W4 W5 W8 W9'.split()
CONFIG_BALLS = {'CCLK': 'U3', 'CFG_0': 'U4', 'CFG_1': 'T4', 'CFG_2': 'R4', 'DONE': 'Y3', 'INITN': 'V3',
                'PROGRAMN': 'W3', 'TCK': 'T5', 'TDI': 'R5', 'TDO': 'V4', 'TMS': 'U5'}
BANK_IO = {
    '0': 'A10 A11 A6 A7 A8 A9 B10 B11 B6 B8 B9 C10 C11 C6 C7 C8 C9 D10 D6 D7 D8 D9 E10 E6 E7 E8 E9',
    '1': 'A12 A13 A14 A15 A16 A17 A18 A19 B12 B13 B15 B16 B17 B18 B19 B20 C12 C13 C14 C15 C16 C17 D11 D12 D13 '
         'D14 D15 D16 E11 E12 E13 E14 E15',
    '2': 'C18 C20 D17 D18 D19 D20 E16 E17 E18 E19 E20 F16 F17 F18 F19 F20 G16 G18 G19 G20 H16 H17 H18 H20 J16 '
         'J17 J18 J19 J20 K16 K17 K18 K19 K20',
    '3': 'L16 L17 L18 L19 L20 M17 M18 M19 M20 N16 N17 N18 N19 N20 P16 P17 P18 P19 P20 R16 R17 R18 R20 T16 T17 '
         'T18 T19 T20 U16 U17 U18 U19 U20',
    '6': 'F1 G1 G2 H1 H2 J1 J3 J4 J5 K1 K2 K3 K4 K5 L1 L2 L3 L4 L5 M1 M3 M4 M5 N1 N2 N3 N4 N5 P1 P2 P3 P4 P5',
    '7': 'A2 A3 A4 A5 B1 B2 B3 B4 B5 C1 C2 C3 C4 C5 D1 D2 D3 D5 E1 E2 E3 E4 E5 F2 F3 F4 F5 G3 G5 H3 H4 H5',
    '8': 'R1 R2 R3 T1 T2 T3 U1 U2 V1 V2 W1 W2 Y2',
}
PCLKT = {'A10': 'PCLKT0_1', 'B11': 'PCLKT0_0', 'D11': 'PCLKT1_1', 'B12': 'PCLKT1_0', 'J19': 'PCLKT2_1',
         'J20': 'PCLKT2_0', 'L20': 'PCLKT3_1', 'L19': 'PCLKT3_0', 'G2': 'PCLKT6_1', 'H2': 'PCLKT6_0',
         'G3': 'PCLKT7_1', 'F2': 'PCLKT7_0'}
# Top-bank A/B pairs used for LVCMOS33D (Differential column: True_OF_/Comp_OF_)
DIFF_PAIRS = {'A16': 'B16', 'A14': 'C14', 'A12': 'A13', 'A17': 'B18'}
FLASH_FN = {'R2': 'CSSPIN', 'W2': 'D0/MOSI', 'V2': 'D1/MISO', 'Y2': 'D2', 'W1': 'D3', 'U3': 'MCLK'}

# W25Q128JV rev F 3.3 (SOIC 208-mil): pin -> function
W25Q_PINS = {'1': '/CS', '2': 'IO1', '3': 'IO2', '4': 'GND', '5': 'IO0', '6': 'CLK', '7': 'IO3', '8': 'VCC'}
# SN74CB3Q3384A SCDS114E Figure 3-1: (A, B) channel pins, OE pins, VCC, GND
CB3Q_CH = [('3', '2'), ('4', '5'), ('7', '6'), ('8', '9'), ('11', '10'), ('14', '15'), ('17', '16'), ('18', '19'),
           ('21', '20'), ('22', '23')]
N64_EDGE = ['N64_AD%d' % i for i in range(16)] + ['N64_ALE_L', 'N64_ALE_H', 'N64_READ_N', 'N64_WRITE_N',
                                                  'N64_RESET_N', 'N64_NMI_N', 'N64_CIC_CLK', 'N64_CIC_DATA',
                                                  'N64_PIF_CLK', 'N64_JOYBUS', 'N64_INT_N']
RAIL_1V1, RAIL_2V5, RAIL_3V3 = 'FPGA_1V1', 'FPGA_2V5', 'FPGA_3V3'
FORBIDDEN = re.compile(r'(5V|VBUS|12V)')   # rail names (upper case); cart_5v_ok etc. are 3.3 V logic
CLOCK_PORTS = ['osc_25', 'si_clk0', 'si_clk1']
HDMI_PORTS = ['hdmi_tmds[0]', 'hdmi_tmds[1]', 'hdmi_tmds[2]', 'hdmi_tmds_clock', 'hdmi_hpd', 'hdmi_scl', 'hdmi_sda', 'si_clk2']


def short(name):
    return name.rsplit('/', 1)[-1]


def value_ohms(v):
    m = re.match(r'^\s*([\d.]+)\s*([kKmM]?)', v or '')
    if not m:
        return None
    return float(m.group(1)) * {'': 1, 'k': 1e3, 'K': 1e3, 'm': 1e6, 'M': 1e6}[m.group(2)]


def value_farads(v):
    m = re.match(r'^\s*([\d.]+)\s*([pnu])F', v or '')
    return float(m.group(1)) * {'p': 1e-12, 'n': 1e-9, 'u': 1e-6}[m.group(2)] if m else None


class Net:
    def __init__(self, xml_path):
        t = ET.parse(xml_path)
        self.comp = {}
        for c in t.iter('comp'):
            ls = c.find('libsource')
            self.comp[c.get('ref')] = {'value': c.findtext('value') or '', 'lib': (ls.get('lib') + ':' + ls.get('part')) if ls is not None else '',
                                       'footprint': c.findtext('footprint') or ''}
        self.pin_net, self.nets = {}, {}
        for n in t.iter('net'):
            name = n.get('name')
            nodes = [(x.get('ref'), x.get('pin')) for x in n.iter('node')]
            self.nets[name] = nodes
            for node in nodes:
                self.pin_net[node] = name

    def net(self, ref, pin):
        return self.pin_net.get((ref, pin))

    def refs_on(self, name, prefix=None):
        return [(r, p) for r, p in self.nets.get(name, []) if prefix is None or r.startswith(prefix)]

    def by_lib(self, part):
        return sorted(r for r, c in self.comp.items() if c['lib'].endswith(':' + part))

    def two_pin_between(self, a, b, prefix='R'):
        """Resistors (or other two-pin parts) with one pin on net a and the other on net b."""
        out = []
        for r, c in self.comp.items():
            if not r.startswith(prefix):
                continue
            n1, n2 = self.net(r, '1'), self.net(r, '2')
            if {n1, n2} == {a, b} or (a == b and n1 == n2 == a):
                out.append(r)
        return out

    def other_end(self, ref, net):
        n1, n2 = self.net(ref, '1'), self.net(ref, '2')
        return n2 if n1 == net else n1


def parse_lpf(path):
    loc, iob, freq, other = {}, {}, [], []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        m = re.match(r'LOCATE COMP "([^"]+)" SITE "([^"]+)";$', line)
        if m:
            if m.group(1) in loc:
                other.append('duplicate LOCATE ' + m.group(1))
            loc[m.group(1)] = m.group(2)
            continue
        m = re.match(r'IOBUF PORT "([^"]+)"((?: \w+=\w+)*);$', line)
        if m:
            iob[m.group(1)] = dict(kv.split('=') for kv in m.group(2).split())
            continue
        m = re.match(r'FREQUENCY (PORT|NET) "([^"]+)" ([\d.]+) MHZ;$', line)
        if m:
            freq.append((m.group(1), m.group(2), float(m.group(3))))
            continue
        other.append(line)
    return loc, iob, freq, other


def board_ports(path):
    """Expanded port bits of the sn64_board_top module header."""
    text = Path(path).read_text(encoding='utf-8')
    head = text[text.index('module sn64_board_top'):text.index(');')]
    head = re.sub(r'//[^\n]*', '', head)
    ports = []
    for m in re.finditer(r'\b(input|output|inout)\s+wire\s*(\[(\d+):(\d+)\])?\s*([^;]*?)(?=,\s*(?:input|output|inout)\b|\s*$)',
                         head.split('(', 1)[1], re.S):
        names = [n.strip() for n in m.group(5).split(',') if n.strip()]
        for n in names:
            if m.group(2):
                hi, lo = int(m.group(3)), int(m.group(4))
                ports += [(f'{n}[{i}]', m.group(1)) for i in range(lo, hi + 1)]
            else:
                ports.append((n, m.group(1)))
    return ports


def lattice_from_csv(path):
    rows = {}
    for row in csv.reader(open(path, encoding='utf-8', errors='replace')):
        if len(row) > 9 and row[9] not in ('-', '', 'CABGA381') and not row[0].startswith('#'):
            rows[row[9]] = {'func': row[1], 'bank': row[2], 'dual': row[3], 'diff': row[4]}
    return rows


def run_checks(proj, kicad_cli, board_top, lpf_path, csv_path, lattice_csv=None, workdir=None):
    workdir = Path(workdir or tempfile.mkdtemp(prefix='sn64-fpga-verify-'))
    xml_path, erc_path = workdir / 'netlist.xml', workdir / 'erc.json'
    root = Path(proj) / 'sn64.kicad_sch'
    subprocess.run([kicad_cli, 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', str(xml_path), str(root)],
                   check=True, capture_output=True)
    subprocess.run([kicad_cli, 'sch', 'erc', '--format', 'json', '--severity-all', '-o', str(erc_path), str(root)],
                   check=False, capture_output=True)
    N = Net(xml_path)
    checks = {}

    def check(name, ok, detail):
        checks[name] = {'pass': bool(ok), 'detail': detail}

    fpga = [r for r, c in N.comp.items() if c['lib'].startswith('FPGA_Lattice:LFE5U-85F')]
    check('single_LFE5U_85F_CABGA381', len(fpga) == 1 and 'caBGA-381' in N.comp[fpga[0]]['footprint'],
          {'refs': fpga, 'footprint': N.comp[fpga[0]]['footprint'] if fpga else None})
    U = fpga[0] if fpga else 'U401'
    ball = lambda b: N.net(U, b)

    # ---- power balls
    bad = []
    for b in GND_BALLS:
        if short(ball(b) or '') != 'GND':
            bad.append((b, 'GND', ball(b)))
    for b in VCC_BALLS:
        if short(ball(b) or '') != RAIL_1V1:
            bad.append((b, RAIL_1V1, ball(b)))
    aux_nets = {ball(b) for b in VCCAUX_BALLS}
    aux = next(iter(aux_nets)) if len(aux_nets) == 1 else None
    fb = [r for r in N.comp if r.startswith('FB') and aux in (N.net(r, '1'), N.net(r, '2'))]
    aux_ok = aux is not None and len(fb) == 1 and short(N.other_end(fb[0], aux) or '') == RAIL_2V5 and \
        not any(p[0] == U for p in N.nets.get(N.other_end(fb[0], aux), []))
    if not aux_ok:
        bad.append(('VCCAUX', 'FPGA_2V5 via one ferrite bead', sorted(str(n) for n in aux_nets), fb))
    for bank, balls in VCCIO_BALLS.items():
        for b in balls.split():
            if short(ball(b) or '') != RAIL_3V3:
                bad.append((b, f'VCCIO{bank}={RAIL_3V3}', ball(b)))
    for b in RESERVED_BALLS:
        n = ball(b)
        if n and len(N.nets[n]) > 1:
            bad.append((b, 'RESERVED unconnected', n))
    check('every_power_ball_on_its_rail', not bad,
          {'violations': bad, 'gnd': len(GND_BALLS), 'vcc': len(VCC_BALLS), 'vccaux': len(VCCAUX_BALLS),
           'vccio': sum(len(v.split()) for v in VCCIO_BALLS.values()), 'reserved_unconnected': len(RESERVED_BALLS),
           'bank_plan': {f'VCCIO{k}': RAIL_3V3 for k in VCCIO_BALLS}})

    # ---- decoupling (FPGA-TN-02038-2.1 Table 3.1)
    def caps_on(net):
        out = []
        for r, c in N.comp.items():
            if r.startswith('C') and {short(N.net(r, '1') or ''), short(N.net(r, '2') or '')} == {short(net or ''), 'GND'}:
                out.append(value_farads(c['value']))
        return out
    dec = {}
    for label, net, need_small, need_bulk in [('VCC', next((ball(b) for b in VCC_BALLS), None), 20, 3),
                                              ('VCCAUX', aux, 4, 1),
                                              ('VCCIO', ball('P9'), 18, 7)]:
        cs = caps_on(net)
        small = sum(1 for v in cs if v and abs(v - 100e-9) < 1e-12)
        bulk = sum(1 for v in cs if v and v >= 10e-6 - 1e-12)
        dec[label] = {'net': net, '100nF': small, '>=10uF': bulk, 'required': [need_small, need_bulk]}
    check('decoupling_per_TN02038_table_3_1', all(d['100nF'] >= d['required'][0] and d['>=10uF'] >= d['required'][1]
                                                   for d in dec.values()), dec)

    vccio8 = ball('P9')

    def pulled(net, to, lo, hi):
        rs = [r for r in N.two_pin_between(net, to)
              if value_ohms(N.comp[r]['value']) is not None and lo <= value_ohms(N.comp[r]['value']) <= hi]
        return rs

    # ---- configuration straps and pins
    cfg = {}
    for pin in ('CFG_0', 'CFG_2'):
        n = ball(CONFIG_BALLS[pin])
        low = short(n or '') == 'GND' or bool(pulled(n, next(k for k in N.nets if short(k) == 'GND'), 0, 500))
        cfg[pin] = {'net': n, 'low': low}
    n = ball(CONFIG_BALLS['CFG_1'])
    cfg['CFG_1'] = {'net': n, 'pullup_1k_10k_to_VCCIO8': pulled(n, vccio8, 1e3, 10e3)}
    for pin in ('PROGRAMN', 'INITN', 'DONE'):
        n = ball(CONFIG_BALLS[pin])
        cfg[pin] = {'net': n, 'pullup_1k_10k_to_VCCIO8': pulled(n, vccio8, 1e3, 10e3), 'testpoint':
                    [r for r, p in N.nets.get(n, []) if r.startswith('TP')]}
    prog = ball(CONFIG_BALLS['PROGRAMN'])
    hold = [(r, p) for r, p in N.nets.get(prog, []) if N.comp[r]['lib'].endswith('74LVC1G07') and p == '4']
    hold_in = N.net(hold[0][0], '2') if hold else None
    cfg['PROGRAMN_hold'] = {'open_drain': hold, 'input': hold_in}
    ok = (cfg['CFG_0']['low'] and cfg['CFG_2']['low'] and cfg['CFG_1']['pullup_1k_10k_to_VCCIO8'] and
          all(cfg[p]['pullup_1k_10k_to_VCCIO8'] for p in ('PROGRAMN', 'INITN', 'DONE')) and
          len(hold) == 1 and short(hold_in or '') == 'fpga_rails_ok')
    check('config_straps_master_spi_010_and_pullups', ok, cfg)

    # ---- flash
    fl = N.by_lib('W25Q128JVS')
    fdet = {'refs': fl}
    fok = len(fl) == 1
    if fok:
        F = fl[0]
        fn = {k: N.net(F, k) for k in W25Q_PINS}
        fdet['pins'] = fn
        fok &= fn['1'] == ball('R2') and fn['5'] == ball('W2') and fn['2'] == ball('V2')
        fok &= fn['3'] == ball('Y2') and fn['7'] == ball('W1')
        fok &= short(fn['4'] or '') == 'GND' and fn['8'] == vccio8
        ser = [r for r in N.comp if r.startswith('R') and {N.net(r, '1'), N.net(r, '2')} == {ball('U3'), fn['6']}]
        fdet['mclk_series'] = [(r, N.comp[r]['value']) for r in ser]
        fok &= len(ser) == 1 and 22 <= value_ohms(N.comp[ser[0]]['value']) <= 80
        fdet['sck_pullup'] = pulled(fn['6'], vccio8, 510, 1.1e3)
        fdet['cs_pullup'] = pulled(fn['1'], vccio8, 4.7e3, 10e3)
        fdet['io2_pullup'] = pulled(fn['3'], vccio8, 1e3, 100e3)
        fdet['io3_pullup'] = pulled(fn['7'], vccio8, 1e3, 100e3)
        fok &= all(fdet[k] for k in ('sck_pullup', 'cs_pullup', 'io2_pullup', 'io3_pullup'))
        fdet['value'] = N.comp[F]['value']
        fok &= N.comp[F]['value'].startswith('W25Q128JV') and N.comp[F]['value'].endswith('IQ')
    check('config_flash_wired_to_bank8_sysconfig_balls', fok, fdet)

    # ---- JTAG
    jt = {}
    for pin, label, pull in [('TCK', 'jtag_tck', 'down'), ('TDI', 'jtag_tdi', 'up'), ('TDO', 'jtag_tdo', 'up'),
                             ('TMS', 'jtag_tms', 'up')]:
        n = ball(CONFIG_BALLS[pin])
        gnd = next(k for k in N.nets if short(k) == 'GND')
        pr = pulled(n, vccio8 if pull == 'up' else gnd, 1e3, 10e3)
        # Since the round-3 integration the USB sheet's JTAG bias resistors (R112-R114) share these nets,
        # so also require that nothing pulls the opposite way (a parallel same-direction pull alone
        # must not mask a reversed one).
        opp_rails = [gnd] if pull == 'up' else [vccio8] + [k for k in N.nets if short(k) == 'TARGET_VREF']
        opp = [r for t in opp_rails for r in N.two_pin_between(n, t)]
        jt[pin] = {'net': n, 'label_ok': short(n or '') == label, 'pull_' + pull: pr if not opp else [],
                   'opposite_pull': opp}
    tv = [k for k in N.nets if short(k) == 'TARGET_VREF']
    link = [r for r in N.comp if r.startswith('R') and any({N.net(r, '1'), N.net(r, '2')} == {t, vccio8} for t in tv)
            and value_ohms(N.comp[r]['value']) is not None and value_ohms(N.comp[r]['value']) <= 1]
    jt['TARGET_VREF'] = {'net': tv, 'link_to_VCCIO8_rail': link}
    check('jtag_balls_labels_pulls_and_target_vref', all(v.get('label_ok') and (v.get('pull_up') or v.get('pull_down'))
                                                          for k, v in jt.items() if k != 'TARGET_VREF') and len(link) == 1, jt)

    # ---- ports / LPF / CSV / netlist agreement
    loc, iob, freq, other = parse_lpf(lpf_path)
    rows = list(csv.DictReader(open(csv_path, encoding='utf-8')))
    crow = {r['port']: r for r in rows if not r['port'].startswith('(')}
    ports = board_ports(board_top)
    bank_of = {b: k for k, v in BANK_IO.items() for b in v.split()}
    pm = []
    for port, direction in ports:
        r = crow.get(port)
        site = loc.get(port)
        if r is None or site is None:
            pm.append((port, 'missing', r and r['ball'], site))
            continue
        net = ball(site)
        if site != r['ball']:
            pm.append((port, 'lpf/csv ball differ', site, r['ball']))
        if iob.get(port, {}).get('IO_TYPE') != r['IO_TYPE']:
            pm.append((port, 'IO_TYPE differs', iob.get(port), r['IO_TYPE']))
        if bank_of.get(site) != r['bank']:
            pm.append((port, 'bank', site, bank_of.get(site), r['bank']))
        if short(net or '') != r['fpga_net']:
            pm.append((port, 'netlist net', site, net, r['fpga_net']))
        if r['IO_TYPE'] == 'LVCMOS33D':
            comp = DIFF_PAIRS.get(site)
            want = r['fpga_net'][:-2] + '_n'
            if comp is None or short(ball(comp) or '') != want:
                pm.append((port, 'LVCMOS33D complement', site, comp, ball(comp) if comp else None, want))
    extra = sorted(set(loc) - {p for p, _ in ports})
    balls = [loc[p] for p in loc]
    dup = sorted({b for b in balls if balls.count(b) > 1})
    wanted_freq = {('PORT', 'osc_25', 25.0), ('PORT', 'si_clk0', 21.477272), ('PORT', 'si_clk1', 21.28137),
                   ('NET', 'clk_snes', 21.477272)}
    clk = {p: (loc.get(p), PCLKT.get(loc.get(p))) for p in CLOCK_PORTS}
    hdmi_left = sorted(p for p in HDMI_PORTS if p in loc or p in {q for q, _ in ports})
    check('no_hdmi_ports_in_lpf_or_board_top', not hdmi_left,
          hdmi_left or 'no HDMI/TMDS/DDC/si_clk2 ports (rev 0.5-fpga: video goes to the console over the cartridge bus)')
    config_used = sorted(b for b in balls if b in CONFIG_BALLS.values())
    flash_ok = all(loc.get(p) == b for p, b in [('flash_cs_n', 'R2'), ('flash_dq[0]', 'W2'), ('flash_dq[1]', 'V2'),
                                                 ('flash_dq[2]', 'Y2'), ('flash_dq[3]', 'W1')])
    ok = (not pm and not extra and not dup and wanted_freq <= set(freq) and all(v[1] for v in clk.values())
          and not config_used and flash_ok and not [o for o in other if not o.startswith('SYSCONFIG')])
    check('every_board_top_port_ball_matches_lpf_csv_netlist', ok,
          {'ports': len(ports), 'mismatches': pm, 'lpf_locates_without_port': extra, 'duplicate_balls': dup,
           'frequency': sorted(freq), 'clock_pins_on_PCLKT': clk, 'dedicated_balls_in_lpf': config_used,
           'flash_bank8_sites': flash_ok, 'unparsed_lpf_lines': other})

    # ---- no 5 V anywhere near an FPGA ball (graph search through two-pin passives and closed FET channels)
    adj = {}

    def link(a, b):
        if a and b:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    for r, c in N.comp.items():
        if r[:1] in ('R', 'L') or r.startswith('FB'):
            link(N.net(r, '1'), N.net(r, '2'))
    for r in N.by_lib('SN74CB3Q3384APW'):
        for a, b in CB3Q_CH:
            link(N.net(r, a), N.net(r, b))
    rails = {short(k) for k in N.nets if short(k) in ('GND', RAIL_1V1, RAIL_2V5, RAIL_3V3, 'HOST_3V3', 'TARGET_VREF')}
    hits = []
    for pin in [p for (r, p) in N.pin_net if r == U]:
        start = ball(pin)
        if not start:
            continue
        seen, todo = {start}, [start]
        while todo:
            n = todo.pop()
            if FORBIDDEN.search(short(n)):
                hits.append((pin, start, n))
                break
            if short(n) == 'GND' or (short(n) in rails and n != start):
                # stop at supplies (a pull-up to a 3.3 V rail is not a path onward). GND always stops,
                # even at a GND ball: once the power sheet is attached, every divider/pull-down to GND
                # would otherwise "connect" the GND balls to 5V_PRE (round-3 integration fix). The FPGA
                # rails are still walked from their own balls, so a resistor from 5 V into them is caught.
                continue
            for m in adj.get(n, ()):
                if m not in seen:
                    seen.add(m)
                    todo.append(m)
    check('no_5V_12V_or_VBUS_net_reaches_any_FPGA_ball', not hits, {'hits': hits})

    # ---- N64 host isolation
    sw = N.by_lib('SN74CB3Q3384APW')
    iso = {'switches': sw}
    iok = len(sw) >= 3
    oe_nets = {N.net(r, p) for r in sw for p in ('1', '13')}
    iso['oe_nets'] = sorted(str(n) for n in oe_nets)
    iok &= len(oe_nets) == 1
    oe = next(iter(oe_nets)) if oe_nets else None
    drv = [(r, p) for r, p in N.nets.get(oe, []) if N.comp[r]['lib'].endswith('74LVC1G14') and p == '4']
    iso['oe_driver'] = drv
    iok &= len(drv) == 1
    iso['oe_pullup_to_switch_vcc'] = pulled(oe, vccio8, 1e3, 100e3)
    iok &= bool(iso['oe_pullup_to_switch_vcc']) and all(N.net(r, '24') == vccio8 for r in sw)
    if drv:
        det = N.net(drv[0][0], '2')
        host = [k for k in N.nets if short(k) == 'HOST_3V3']
        iso['detector_input'] = det
        iso['detector_from_HOST_3V3'] = bool(host) and bool(N.two_pin_between(det, host[0]))
        iso['detector_pulldown'] = bool(N.two_pin_between(det, next(k for k in N.nets if short(k) == 'GND')))
        iok &= iso['detector_from_HOST_3V3'] and iso['detector_pulldown'] and N.net(drv[0][0], '5') == vccio8
    chan = []
    for edge in N64_EDGE:
        nets = [k for k in N.nets if short(k) == edge]
        if len(nets) != 1:
            chan.append((edge, 'net missing'))
            continue
        nodes = N.nets[nets[0]]
        a = [(r, p) for r, p in nodes if r in sw and p in {x for x, _ in CB3Q_CH}]
        direct = [(r, p) for r, p in nodes if r == U]
        other = [(r, p) for r, p in nodes if r not in sw and not r.startswith('J') and not r.startswith('TP')]
        if len(a) != 1 or direct or other:
            chan.append((edge, 'edge net', nodes))
            continue
        r, p = a[0]
        b = dict(CB3Q_CH)[p]
        bnet = N.net(r, b)
        fp = [(rr, pp) for rr, pp in N.nets.get(bnet, []) if rr == U]
        if len(fp) != 1:
            chan.append((edge, 'switch B side must reach exactly one FPGA ball', bnet, fp))
            continue
        row = next((x for x in rows if x['sheet_label'] == edge), None)
        if row is None or row['ball'] != fp[0][1] or bank_of.get(fp[0][1]) not in ('0', '1', '8'):
            chan.append((edge, 'ball/bank', fp[0][1], row and row['ball']))
    iso['channel_faults'] = chan
    iok &= not chan
    check('n64_edge_reaches_fpga_only_through_host_gated_bus_switches', iok, iso)

    # ---- cartridge-side balls reach the cartridge sheet (translator/receiver/gate/1T45 pin, not just a label)
    cart_fault = []
    for r in rows:
        if r['group'] != 'cart':
            continue
        nodes = N.nets.get(ball(r['ball']), [])
        ics = [(rr, pp) for rr, pp in nodes if rr != U and rr.startswith('U')]
        if not ics:
            cart_fault.append((r['port'], r['ball'], ball(r['ball'])))
    check('cartridge_balls_reach_cartridge_sheet_ICs', not cart_fault and any(r['group'] == 'cart' for r in rows),
          {'unconnected': cart_fault, 'cart_rows': sum(1 for r in rows if r['group'] == 'cart')})

    # ---- every ball accounted
    assigned = {r['ball'] for r in rows}
    unused_driven = []
    for io_ball in bank_of:
        n = ball(io_ball)
        connected = n and len(N.nets[n]) > 1
        if io_ball not in assigned and connected:
            unused_driven.append((io_ball, n))
    all_balls = set(GND_BALLS) | set(VCC_BALLS) | set(VCCAUX_BALLS) | set(RESERVED_BALLS) | set(CONFIG_BALLS.values()) | \
        {b for v in VCCIO_BALLS.values() for b in v.split()} | set(bank_of)
    sym_balls = {p for (r, p) in N.pin_net if r == U}
    check('all_381_balls_accounted_unused_io_open', len(all_balls) == 381 and sym_balls == all_balls and not unused_driven,
          {'tables': len(all_balls), 'symbol_pins': len(sym_balls), 'unused_io_connected': unused_driven,
           'user_io_assigned': len(assigned & set(bank_of)), 'user_io_total': len(bank_of)})

    # ---- optional: Lattice CSV
    if lattice_csv:
        L = lattice_from_csv(lattice_csv)
        diffs = []
        for b, r in L.items():
            f = r['func']
            exp = ('GND' if b in GND_BALLS else 'VCC' if b in VCC_BALLS else 'VCCAUX' if b in VCCAUX_BALLS else
                   'RESERVED' if b in RESERVED_BALLS else None)
            if exp and f != exp:
                diffs.append((b, f, exp))
            if f.startswith('VCCIO') and b not in VCCIO_BALLS.get(f[5:], '').split():
                diffs.append((b, f, 'VCCIO table'))
            if f.startswith('P') and f != 'PROGRAMN' and r['bank'] != bank_of.get(b):
                diffs.append((b, f, r['bank'], bank_of.get(b)))
            if b in PCLKT and PCLKT[b] != r['dual']:
                diffs.append((b, r['dual'], PCLKT[b]))
        for t, c in DIFF_PAIRS.items():
            if L[t]['diff'] != 'True_OF_' + L[c]['func']:
                diffs.append((t, c, L[t]['diff']))
        for b, fn in FLASH_FN.items():
            if fn not in L[b]['dual'] and fn != 'MCLK':
                diffs.append((b, fn, L[b]['dual']))
        check('embedded_tables_match_lattice_pinout_csv',
              not diffs and len(L) == 381, {'rows': len(L), 'diffs': diffs,
                                            'sha256': hashlib.sha256(Path(lattice_csv).read_bytes()).hexdigest()})

    # ---- ERC
    erc = json.loads(erc_path.read_text(encoding='utf-8'))
    counts = {}
    for s in erc.get('sheets', []):
        for v in s.get('violations', []):
            k = v['severity'] + ':' + v['type']
            counts[k] = counts.get(k, 0) + 1
    check('erc_zero_errors', not any(k.startswith('error') for k in counts), counts)
    return checks


MUTATIONS = [
    # (name, file, kind, target, replacement, checks that must fail)
    ('bank 6 VCCIO (L6/L7/M6) moved to FPGA_1V1', 'sch', 'label', 'U401:L6', 'FPGA_1V1', ['every_power_ball_on_its_rail']),
    ('CFG0 strapped high (U4 on the CFG1 pull-up net)', 'sch', 'label', 'U401:U4', 'fpga_cfg1',
     ['config_straps_master_spi_010_and_pullups']),
    ('flash IO2 pull-up removed (R408 pin 2 re-netted)', 'sch', 'label', 'R408:2', 'spare_net',
     ['config_flash_wired_to_bank8_sysconfig_balls']),
    ('TCK pull-down moved to FPGA_3V3 (R413)', 'sch', 'label', 'R413:2', 'FPGA_3V3',
     ['jtag_balls_labels_pulls_and_target_vref']),
    ('cartridge 5 V on an FPGA ball (T18)', 'sch', 'label', 'U401:T18', 'SNES_5V_CART',
     ['no_5V_12V_or_VBUS_net_reaches_any_FPGA_ball', 'every_board_top_port_ball_matches_lpf_csv_netlist']),
    ('N64 AD0 wired straight to the FPGA (switch bypassed)', 'sch', 'label', 'U401:E6', 'N64_AD0',
     ['n64_edge_reaches_fpga_only_through_host_gated_bus_switches']),
    ('LPF: n64_ad[0] and n64_ad[1] balls swapped', 'lpf', 'swap', 'n64_ad[0]', 'n64_ad[1]',
     ['every_board_top_port_ball_matches_lpf_csv_netlist']),
    ('CSV: osc_25 moved to a non-clock ball', 'csv', 'ball', 'osc_25', 'F1',
     ['every_board_top_port_ball_matches_lpf_csv_netlist']),
    ('LPF: si_clk1 moved off its PCLKT ball', 'lpf', 'site', 'si_clk1', 'F3',
     ['every_board_top_port_ball_matches_lpf_csv_netlist']),
    ('cart_address0 ball label renamed (no longer reaches U201)', 'sch', 'label', 'U401:C18', 'cart_addr0_typo',
     ['cartridge_balls_reach_cartridge_sheet_ICs', 'every_board_top_port_ball_matches_lpf_csv_netlist']),
]
AUTHOR_NS = uuid.UUID('8f0c8a0e-5b1e-4c55-9a8e-0f64a5e0c301')   # add_fpga_sheet.py UUIDv5 namespace (fault-injection locator only)


def mutate(kind, path, target, repl):
    text = Path(path).read_text(encoding='utf-8')
    if kind == 'label':
        u = json.dumps(str(uuid.uuid5(AUTHOR_NS, 'l:' + target)))
        lines = text.split('\n')
        hit = [i for i, line in enumerate(lines) if line.startswith('(label ') and f'(uuid {u})' in line]
        assert len(hit) == 1, ('label not found', target)
        lines[hit[0]] = re.sub(r'^\(label "[^"]*"', f'(label "{repl}"', lines[hit[0]])
        text = '\n'.join(lines)
    elif kind == 'swap':
        a = re.search(r'LOCATE COMP "%s" SITE "(\w+)";' % re.escape(target), text).group(1)
        b = re.search(r'LOCATE COMP "%s" SITE "(\w+)";' % re.escape(repl), text).group(1)
        text = text.replace(f'LOCATE COMP "{target}" SITE "{a}";', 'X1').replace(f'LOCATE COMP "{repl}" SITE "{b}";', 'X2')
        text = text.replace('X1', f'LOCATE COMP "{target}" SITE "{b}";').replace('X2', f'LOCATE COMP "{repl}" SITE "{a}";')
    elif kind == 'site':
        text = re.sub(r'LOCATE COMP "%s" SITE "\w+";' % re.escape(target), f'LOCATE COMP "{target}" SITE "{repl}";', text)
    elif kind == 'ball':
        text = re.sub(r'^(%s,)\w+,' % re.escape(target), r'\g<1>' + repl + ',', text, flags=re.M)
    Path(path).write_text(text, encoding='utf-8', newline='\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project', type=Path, default=REPO / 'hardware/sn64')
    ap.add_argument('--kicad-cli', default=r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe')
    ap.add_argument('--board-top', type=Path, default=REPO / 'fpga/rtl/sn64_board_top.sv')
    ap.add_argument('--lpf', type=Path, default=REPO / 'fpga/constraints/sn64_board.lpf')
    ap.add_argument('--csv', type=Path, default=REPO / 'hardware/sn64/interfaces/fpga-pin-map.csv')
    ap.add_argument('--lattice-csv', type=Path)
    ap.add_argument('--datasheets', type=Path, help='directory of downloaded source PDFs/CSV (SHA-256 recorded)')
    ap.add_argument('--negative-test', action='store_true')
    ap.add_argument('--out', type=Path, default=REPO / 'hardware/sn64/validation/fpga-check.json')
    a = ap.parse_args()
    if not (a.project / 'fpga.kicad_sch').exists() or 'fpga.kicad_sch' not in (a.project / 'sn64.kicad_sch').read_text(encoding='utf-8'):
        sys.exit(f'{a.project}: root does not contain the FPGA sheet; use the validation copy '
                 '(add_fpga_sheet.py --validation-copy) until the integration edit is applied')
    if a.negative_test:
        results = {}
        for name, where, kind, target, repl, must in MUTATIONS:
            tmp = Path(tempfile.mkdtemp(prefix='sn64-fpga-neg-'))
            proj = tmp / 'proj'
            shutil.copytree(a.project, proj)
            lpf, csvp = tmp / 'board.lpf', tmp / 'pins.csv'
            shutil.copy(a.lpf, lpf)
            shutil.copy(a.csv, csvp)
            mutate(kind, {'sch': proj / 'fpga.kicad_sch', 'lpf': lpf, 'csv': csvp}[where], target, repl)
            ch = run_checks(proj, a.kicad_cli, a.board_top, lpf, csvp, None, tmp)
            failed = sorted(k for k, v in ch.items() if not v['pass'])
            detected = all(m in failed for m in must)
            results[name] = {'required_failures': must, 'failed_checks': failed, 'detected': detected}
            print(('DETECTED ' if detected else 'MISSED   ') + name + ' -> ' + ', '.join(failed))
            shutil.rmtree(tmp, ignore_errors=True)
        ok = all(r['detected'] for r in results.values())
        report = json.loads(a.out.read_text(encoding='utf-8')) if a.out.exists() else {}
        report['negative_test'] = {'result': 'pass' if ok else 'FAIL', 'mutations': results}
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
        print(('PASS' if ok else 'FAIL') + f': negative test, {sum(r["detected"] for r in results.values())}/{len(results)} faults detected')
        sys.exit(0 if ok else 1)

    work = Path(tempfile.mkdtemp(prefix='sn64-fpga-verify-'))
    checks = run_checks(a.project, a.kicad_cli, a.board_top, a.lpf, a.csv, a.lattice_csv, work)
    ok = all(c['pass'] for c in checks.values())
    report = {'schema_version': 1, 'tool': 'hardware/sn64/tools/verify_fpga_sheet.py',
              'scope': 'static netlist/LPF/CSV consistency of the FPGA sheet; not electrical, timing or hardware validation',
              'inputs': {k: str(v) for k, v in {'project': a.project, 'board_top': a.board_top, 'lpf': a.lpf,
                                                 'csv': a.csv, 'lattice_csv': a.lattice_csv}.items()},
              'result': 'pass' if ok else 'FAIL', 'checks': checks}
    if a.datasheets:
        report['source_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(a.datasheets.iterdir()) if p.suffix.lower() in ('.pdf', '.csv')}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    for k, v in checks.items():
        print(('pass ' if v['pass'] else 'FAIL ') + k)
    print(('PASS' if ok else 'FAIL') + f': {sum(c["pass"] for c in checks.values())}/{len(checks)} FPGA-sheet checks')
    shutil.rmtree(work, ignore_errors=True)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
