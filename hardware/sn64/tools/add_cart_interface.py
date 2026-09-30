"""Author the SNES cartridge-side translation/protection child sheet.

One-time draft authoring utility, in the style of add_usb_programmer.py. It
writes cart-interface.kicad_sch, the project-local SN64_CART symbol library,
its sym-lib-table entry and cart-provenance.json, then appends ONE
hierarchical sheet symbol to sn64.kicad_sch whose cartridge-side pins carry the
existing J2 net labels. It never rewrites existing root objects.

It refuses to replace an existing child sheet unless --force is given; after
native KiCad editing starts, edit the KiCad files instead of regenerating.
With --force and an existing sheet symbol in the root, ONLY that sheet
symbol (its pins/size) and the labels/no-connect markers this script placed
on its pins are replaced; every other root object is left untouched.

Rev 0.3.1 (2026-09-29): CIC_DATA0 (J2.55) and CIC_DATA1 (J2.24) each get
their own SN74LVC1T45 (A = INTERFACE_3V3 / FPGA, B = cartridge 5 V, DIR from
its own FPGA pin, DIR high = A->B = drive the cartridge) with a series
resistor and a cartridge-side pull-down; they leave U206 and U209.

  python add_cart_interface.py --kicad-share "C:/Program Files/KiCad/10.0/share/kicad"
       [--datasheets <dir with sn74lvc4245a.pdf sn74lvc244a.pdf ...>] [--force]

Pure Python 3 (no pcbnew needed). Standard symbols are copied from the
installed KiCad library; the two octal parts without a KiCad symbol are drawn
here from the TI datasheet pin tables recorded in PIN TABLES below.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import uuid

ROOT = Path(__file__).resolve().parents[1]
NS = uuid.UUID('5d0f7c52-1c1e-4d8a-9a57-3c3c8b1f6a40')
SHEET_FILE = 'cart-interface.kicad_sch'
SHEET_NAME = 'SNES cartridge interface'
LIB = 'SN64_CART'


def uid(s):
    return str(uuid.uuid5(NS, s))


def q(s):
    return json.dumps(str(s), ensure_ascii=False)


class Quoted(str):
    pass


def parse_text(text):
    stack = []
    result = []
    for token in re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', text):
        if token == '(':
            item = []
            (stack[-1] if stack else result).append(item)
            stack.append(item)
        elif token == ')':
            stack.pop()
        else:
            stack[-1].append(Quoted(json.loads(token)) if token.startswith('"') else token)
    assert len(result) == 1 and not stack
    return result[0]


def parse(path):
    return parse_text(path.read_text(encoding='utf-8-sig'))


def dump(n):
    if isinstance(n, list):
        return '(' + ' '.join(dump(v) for v in n) + ')'
    return q(n) if isinstance(n, Quoted) else str(n)


def items(n, k):
    return [v for v in n if isinstance(v, list) and v and v[0] == k]


def get(n, k):
    return next(iter(items(n, k)), None)


def save(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + '\n', encoding='utf-8', newline='\n')


def g(v):
    return f'{round(v, 4):g}'


def prop(k, v, x, y, hide=False, justify=None, angle=0):
    j = f' (justify {justify})' if justify else ''
    return (f'(property {q(k)} {q(v)} (at {g(x)} {g(y)} {angle}) (effects (font (size 1.27 1.27)){j}'
            f'{" (hide yes)" if hide else ""}))')


def txt(s, x, y, size=1.27):
    return (f'(text {q(s)} (at {g(x)} {g(y)} 0) (effects (font (size {size} {size})) (justify left top)) '
            f'(uuid {q(uid("text:" + s[:60]))}))')


# ---------------------------------------------------------------------------
# PIN TABLES (TI datasheets, PW TSSOP packages). Checked independently by
# tools/verify_cart_interface.py against its own copy of these tables.
#   SN74LVC4245A, SCAS375K (May 2026), Figure 4-1 / Table 4-1
#   SN74LVC244A,  SCAS414AG (June 2026), Figure 4-2
# ---------------------------------------------------------------------------
LVC4245A_PINS = (
    [('1', 'VCCA', 'power_in', -7.62, 17.78, 270), ('2', 'DIR', 'input', -17.78, -15.24, 0),
     ('22', '~{OE}', 'input', -17.78, -17.78, 0),
     ('23', 'VCCB', 'power_in', 5.08, 17.78, 270), ('24', 'VCCB', 'power_in', 7.62, 17.78, 270),
     ('11', 'GND', 'power_in', -2.54, -25.4, 90), ('12', 'GND', 'power_in', 0, -25.4, 90),
     ('13', 'GND', 'power_in', 2.54, -25.4, 90)]
    + [(str(2 + i), f'A{i}', 'bidirectional', -17.78, 10.16 - 2.54 * i, 0) for i in range(1, 9)]
    + [(str(22 - i), f'B{i}', 'bidirectional', 17.78, 10.16 - 2.54 * i, 180) for i in range(1, 9)])
LVC244A_PINS = [
    ('20', 'VCC', 'power_in', 0, 17.78, 270), ('10', 'GND', 'power_in', 0, -25.4, 90),
    ('1', '~{1OE}', 'input', -17.78, -15.24, 0), ('19', '~{2OE}', 'input', -17.78, -17.78, 0),
    ('2', '1A1', 'input', -17.78, 10.16, 0), ('18', '1Y1', 'tri_state', 17.78, 10.16, 180),
    ('4', '1A2', 'input', -17.78, 7.62, 0), ('16', '1Y2', 'tri_state', 17.78, 7.62, 180),
    ('6', '1A3', 'input', -17.78, 5.08, 0), ('14', '1Y3', 'tri_state', 17.78, 5.08, 180),
    ('8', '1A4', 'input', -17.78, 2.54, 0), ('12', '1Y4', 'tri_state', 17.78, 2.54, 180),
    ('11', '2A1', 'input', -17.78, 0, 0), ('9', '2Y1', 'tri_state', 17.78, 0, 180),
    ('13', '2A2', 'input', -17.78, -2.54, 0), ('7', '2Y2', 'tri_state', 17.78, -2.54, 180),
    ('15', '2A3', 'input', -17.78, -5.08, 0), ('5', '2Y3', 'tri_state', 17.78, -5.08, 180),
    ('17', '2A4', 'input', -17.78, -7.62, 0), ('3', '2Y4', 'tri_state', 17.78, -7.62, 180)]


def own_symbol(name, value, pins, descr, datasheet, footprint):
    lines = [f'(symbol {q(LIB + ":" + name)} (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)',
             prop('Reference', 'U', 0, -29.21), prop('Value', value, 0, -31.75),
             prop('Footprint', footprint, 0, -34.29, True), prop('Datasheet', datasheet, 0, -36.83, True),
             prop('Description', descr, 0, -39.37, True),
             f'(symbol {q(name + "_0_1")} (rectangle (start -12.7 12.7) (end 12.7 -20.32) '
             f'(stroke (width 0.254) (type default)) (fill (type background))))',
             f'(symbol {q(name + "_1_1")}']
    for number, label, typ, x, y, angle in pins:
        lines.append(f'(pin {typ} line (at {g(x)} {g(y)} {angle}) (length 5.08) (name {q(label)} '
                     f'(effects (font (size 1.27 1.27)))) (number {q(number)} (effects (font (size 1.016 1.016)))))')
    return parse_text('\n'.join(lines) + ') (embedded_fonts no))')


# ---------------------------------------------------------------------------
# Circuit definition
# ---------------------------------------------------------------------------
# (octet ref, [(socket signal net, FPGA label), ...], /OE net, DIR net)
ADDR = [f'SNES_A{i}' for i in range(24)]
OCTETS = [
    ('U201', [(ADDR[i], f'cart_address{i}') for i in range(0, 8)], 'CTL_OE_N_5V', 'GND'),
    ('U202', [(ADDR[i], f'cart_address{i}') for i in range(8, 16)], 'CTL_OE_N_5V', 'GND'),
    ('U203', [(ADDR[i], f'cart_address{i}') for i in range(16, 24)], 'CTL_OE_N_5V', 'GND'),
    ('U204', [(f'SNES_PA{i}', f'cart_pa{i}') for i in range(8)], 'CTL_OE_N_5V', 'GND'),
    ('U205', [('SNES_RD_N', 'cart_rd_n'), ('SNES_WR_N', 'cart_wr_n'), ('SNES_PRD_N', 'cart_prd_n'),
              ('SNES_PWR_N', 'cart_pwr_n'), ('SNES_ROMSEL_N', 'cart_romsel_n'),
              ('SNES_WRAMSEL_N', 'cart_wramsel_n'), ('SNES_REFRESH', 'cart_refresh'),
              ('SNES_PHI2', 'cart_phi2')], 'CTL_OE_N_5V', 'GND'),
    ('U206', [('SNES_SYSTEM_CLK', 'cart_sysclk'), ('SNES_CIC_CLK', 'cic_clk'),
              ('SNES_CIC_SLAVE_RESET', 'cic_slave_reset')],
     'CIC_OE_N_5V', 'GND'),
    ('U207', [(f'SNES_D{i}', f'cart_data{i}') for i in range(8)], 'DATA_OE_N_5V', 'DATA_DIR_5V'),
]
RAIL5 = 'SNES_5V_CART'
RAIL3 = 'INTERFACE_3V3'

# Root sheet-pin interface. Cartridge side first (labels to existing J2 nets),
# then pending pins (FPGA side and the two default-off rails).
CART_PORTS = [('SNES_A[0..23]', 'passive'), ('SNES_PA[0..7]', 'passive'), ('SNES_D[0..7]', 'passive')] + [
    (n, 'passive') for n in ['SNES_RD_N', 'SNES_WR_N', 'SNES_PRD_N', 'SNES_PWR_N', 'SNES_ROMSEL_N',
                             'SNES_WRAMSEL_N', 'SNES_REFRESH', 'SNES_PHI2', 'SNES_SYSTEM_CLK', 'SNES_CIC_CLK',
                             'SNES_CIC_SLAVE_RESET', 'SNES_CIC_DATA0', 'SNES_CIC_DATA1', 'SNES_IRQ_N',
                             'SNES_RESET_N', 'SNES_EXPAND', 'SNES_AUDIO_L_IN', 'SNES_AUDIO_R_IN', 'GND']] + [
    (RAIL5, 'input')]
PENDING_PORTS = [('cart_address[0..23]', 'input'), ('cart_pa[0..7]', 'input'), ('cart_data[0..7]', 'bidirectional')] + [
    (n, 'input') for n in ['cart_rd_n', 'cart_wr_n', 'cart_prd_n', 'cart_pwr_n', 'cart_romsel_n', 'cart_wramsel_n',
                           'cart_refresh', 'cart_phi2', 'cart_sysclk', 'cic_clk', 'cic_slave_reset',
                           'cic_data0_dir', 'cic_data1_dir',
                           'ctl_oe_n', 'cic_oe_n', 'data_oe_n', 'data_dir', 'cart_reset_pull_n']] + [
    (n, 'output') for n in ['cart_irq_n', 'cart_reset_n_sense', 'expand_sense']] + [
    (n, 'bidirectional') for n in ['cic_data0', 'cic_data1']] + [(RAIL3, 'input')]

# Per-pin CIC data translators (TI SN74LVC1T45, SCES515N June 2024, DBV):
# pin 1 VCCA, 2 GND, 3 A, 4 B, 5 DIR (referenced to VCCA), 6 VCCB.
# (ref, J2 socket net, FPGA A-side label, FPGA DIR label, series R, cart pull-down R,
#  A-side pull-down R, DIR pull-down R)
CIC_XLAT = [
    ('U215', 'SNES_CIC_DATA0', 'cic_data0', 'cic_data0_dir', 'R214', 'R216', 'R218', 'R220'),
    ('U216', 'SNES_CIC_DATA1', 'cic_data1', 'cic_data1_dir', 'R215', 'R217', 'R219', 'R221'),
]
CIC_SERIES = '33'          # provisional source-series damping, same as the octet arrays
CIC_CART_PULLDOWN = '10k'  # idle level the lock expects on a released pin (value to confirm)
CIC_A_PULLDOWN = '100k'    # same idle condition on the A side (SCES515N Table 8-2 note 1)
CIC_DIR_PULLDOWN = '10k'   # DIR default low = B->A = listen while the FPGA is unconfigured


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--kicad-share', type=Path, required=True)
    ap.add_argument('--datasheets', type=Path, help='directory holding the downloaded TI PDFs (hashes recorded)')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    dest = ROOT / SHEET_FILE
    if dest.exists() and not a.force:
        ap.error('Child sheet exists; use KiCad to edit, or --force to replace the initial draft')

    root_text = (ROOT / 'sn64.kicad_sch').read_text(encoding='utf-8')
    root = parse_text(root_text)
    root_uuid = str(get(root, 'uuid')[1])
    sheet_uuid = uid('sheet')
    page_uuid = uid('page')
    libs, parts, fps = {}, [], set()

    def load(lib_id):
        if lib_id in libs:
            return libs[lib_id]
        lib, name = lib_id.split(':')
        db = parse(a.kicad_share / 'symbols' / f'{lib}.kicad_sym')
        byname = {str(s[1]): s for s in items(db, 'symbol')}

        def resolve(n):
            node = copy.deepcopy(byname[n])
            ext = get(node, 'extends')
            if not ext:
                return node
            base = resolve(str(ext[1]))
            old = str(base[1])
            base[1] = Quoted(n)
            for unit in items(base, 'symbol'):
                unit[1] = Quoted(str(unit[1]).replace(old + '_', n + '_', 1))
            for p in items(node, 'property'):
                base[:] = [v for v in base if not (isinstance(v, list) and v[:2] == p[:2])]
                base.append(p)
            return base
        s = resolve(name)
        s[1] = Quoted(lib_id)
        libs[lib_id] = s
        return s

    libs[LIB + ':SN74LVC4245APW'] = own_symbol(
        'SN74LVC4245APW', 'SN74LVC4245APWR', LVC4245A_PINS,
        'Octal 5V(A)/3.3V(B) translating bus transceiver, control inputs referenced to VCCA',
        'https://www.ti.com/lit/ds/symlink/sn74lvc4245a.pdf', 'Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm')
    libs[LIB + ':SN74LVC244APW'] = own_symbol(
        'SN74LVC244APW', 'SN74LVC244APWR', LVC244A_PINS,
        'Octal buffer, 5.5V-tolerant inputs, Ioff', 'https://www.ti.com/lit/ds/symlink/sn74lvc244a.pdf',
        'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm')

    def place(ref, lib_id, value, x, y, nets, fp='', dnp=False, fields=None):
        sym = load(lib_id)
        pins = [p for u in items(sym, 'symbol') for p in items(u, 'pin')]
        assert {str(get(p, 'number')[1]) for p in pins} == set(nets), (ref, sorted(nets))
        small = lib_id in ('Device:R', 'Device:C', 'Connector:TestPoint', 'power:PWR_FLAG')
        if small:
            rx, ry, vx, vy, just = x + 2.54, y - 1.27, x + 2.54, y + 1.27, 'left'
        elif lib_id == 'Device:R_Pack04':
            rx, ry, vx, vy, just = x + 5.08, y - 1.27, x + 5.08, y + 1.27, 'left'
        else:
            # Up and to the left, clear of the vertical supply-pin labels.
            tops = [y - float(get(p, 'at')[2]) for p in pins]
            rx, ry, vx, vy, just = x - 30.48, min(tops) - 10.16, x - 30.48, min(tops) - 7.62, 'left'
        hidden = ref.startswith('#')
        out = [f'(symbol (lib_id {q(lib_id)}) (at {g(x)} {g(y)} 0) (unit 1) (exclude_from_sim no) (in_bom {"no" if hidden else "yes"}) '
               f'(on_board {"no" if hidden else "yes"}) (dnp {"yes" if dnp else "no"}) (uuid {q(uid(ref))})',
               prop('Reference', ref, rx, ry, hidden, just), prop('Value', value, vx, vy, hidden, just),
               prop('Footprint', fp, x, y, True), prop('Datasheet', (fields or {}).get('Datasheet', ''), x, y, True)]
        for k, v in (fields or {}).items():
            if k != 'Datasheet':
                out.append(prop(k, v, x, y, True))
        for pin in pins:
            out.append(f'(pin {q(get(pin, "number")[1])} (uuid {q(uid(ref + ":" + str(get(pin, "number")[1])))}))')
        out.append(f'(instances (project "sn64" (path {q("/" + root_uuid + "/" + sheet_uuid)} (reference {q(ref)}) (unit 1)))))')
        parts.extend(out)
        seen = set()
        for pin in pins:
            number = str(get(pin, 'number')[1])
            net = nets[number]
            at = get(pin, 'at')
            px, py, angle = x + float(at[1]), y - float(at[2]), int(float(at[3]))
            role = ref + ':' + number
            if (px, py, net) in seen:
                continue
            seen.add((px, py, net))
            if net is None:
                parts.append(f'(no_connect (at {g(px)} {g(py)}) (uuid {q(uid("nc:" + role))}))')
                continue
            dx = -5.08 * round(math.cos(math.radians(angle)))
            dy = 5.08 * round(math.sin(math.radians(angle)))
            ex, ey = px + dx, py + dy
            parts.append(f'(wire (pts (xy {g(px)} {g(py)}) (xy {g(ex)} {g(ey)})) (stroke (width 0) (type default)) '
                         f'(uuid {q(uid("w:" + role))}))')
            if dx < 0:
                la, lj = 180, 'right'
            elif dx > 0:
                la, lj = 0, 'left'
            elif dy > 0:
                la, lj = 270, 'right'
            else:
                la, lj = 90, 'left'
            parts.append(f'(label {q(net)} (at {g(ex)} {g(ey)} {la}) (effects (font (size 1.016 1.016)) (justify {lj} bottom)) '
                         f'(uuid {q(uid("l:" + role))}))')
        if fp:
            fps.add(fp)

    R0603 = 'Resistor_SMD:R_0603_1608Metric'
    C0603 = 'Capacitor_SMD:C_0603_1608Metric'
    RARR = 'Resistor_SMD:R_Array_Convex_4x0603'
    TI = {'4245': 'https://www.ti.com/lit/ds/symlink/sn74lvc4245a.pdf',
          '244': 'https://www.ti.com/lit/ds/symlink/sn74lvc244a.pdf',
          '1g07': 'https://www.ti.com/lit/ds/symlink/sn74lvc1g07.pdf',
          '1g06': 'https://www.ti.com/lit/ds/symlink/sn74lvc1g06.pdf'}

    # --- Translators: A = 5 V cartridge side, B = 3.3 V FPGA side ----------
    rn_index = 201
    caps = []
    for i, (ref, chans, oe, dirnet) in enumerate(OCTETS):
        x = 60.96 + i * 109.22
        nets = {'1': RAIL5, '23': RAIL3, '24': RAIL3, '11': 'GND', '12': 'GND', '13': 'GND', '2': dirnet, '22': oe}
        for ch in range(1, 9):
            if ch <= len(chans):
                sig, label = chans[ch - 1]
                nets[str(2 + ch)] = 'XA_' + sig[5:]
                nets[str(22 - ch)] = label
            else:
                nets[str(2 + ch)] = None      # unused A output (DIR fixed B->A): no-connect
                nets[str(22 - ch)] = 'GND'    # unused B input: held at GND per datasheet note
        place(ref, LIB + ':SN74LVC4245APW', 'SN74LVC4245APWR', x, 101.6, nets,
              'Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm', fields={'Datasheet': TI['4245']})
        caps += [(RAIL5, ref + ' VCCA pin 1'), (RAIL3, ref + ' VCCB pin 23'), (RAIL3, ref + ' VCCB pin 24')]
        # Source-series damping arrays, translator A pin -> socket contact.
        for k in range(0, len(chans), 4):
            group = chans[k:k + 4]
            rnets = {}
            for j in range(4):
                if j < len(group):
                    rnets[str(1 + j)] = 'XA_' + group[j][0][5:]
                    rnets[str(8 - j)] = group[j][0]
                else:
                    rnets[str(1 + j)] = None
                    rnets[str(8 - j)] = None
            place(f'RN{rn_index}', 'Device:R_Pack04', '33 (4x0603, tune)', x - 15.24 + 30.48 * (k // 4), 177.8, rnets, RARR)
            rn_index += 1

    # --- Fixed receiver for sensed/released cartridge signals ----------------
    rx = {'20': RAIL3, '10': 'GND', '1': 'GND', '19': 'GND',
          '2': 'SNES_IRQ_N', '18': 'cart_irq_n', '4': 'SNES_RESET_N', '16': 'cart_reset_n_sense',
          '6': 'SNES_EXPAND', '14': 'expand_sense', '8': 'GND', '12': None,
          '11': 'GND', '9': None,
          '13': 'GND', '7': None, '15': 'GND', '5': None, '17': 'GND', '3': None}
    place('U209', LIB + ':SN74LVC244APW', 'SN74LVC244APWR', 76.2, 271.78, rx,
          'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm', fields={'Datasheet': TI['244']})
    caps.append((RAIL3, 'U209 VCC'))

    # --- Level-safe control: 3.3 V open-drain buffers into 5 V-pulled nets ----
    gates = [('U210', '74xGxx:74LVC1G07', 'SN74LVC1G07DBVR', 'ctl_oe_n', 'CTL_OE_N_5V', TI['1g07']),
             ('U211', '74xGxx:74LVC1G07', 'SN74LVC1G07DBVR', 'cic_oe_n', 'CIC_OE_N_5V', TI['1g07']),
             ('U212', '74xGxx:74LVC1G07', 'SN74LVC1G07DBVR', 'data_oe_n', 'DATA_OE_N_5V', TI['1g07']),
             ('U213', '74xGxx:74LVC1G06', 'SN74LVC1G06DBVR', 'data_dir', 'DATA_DIR_5V', TI['1g06']),
             ('U214', '74xGxx:74LVC1G06', 'SN74LVC1G06DBVR', 'cart_reset_pull_n', 'RESET_GATE_5V', TI['1g06'])]
    for k, (ref, lib_id, value, a_net, y_net, ds) in enumerate(gates):
        nets = {'2': a_net, '3': 'GND', '4': y_net, '5': RAIL3}
        if lib_id.endswith('1G07'):
            nets['1'] = None
        place(ref, lib_id, value, 190.5 + 76.2 * k, 271.78, nets, 'Package_TO_SOT_SMD:SOT-23-5', fields={'Datasheet': ds})
        caps.append((RAIL3, ref + ' VCC'))
    place('Q201', 'Transistor_FET:2N7002', '2N7002', 584.2, 271.78, {'1': 'RESET_GATE_5V', '2': 'GND', '3': 'SNES_RESET_N'},
          'Package_TO_SOT_SMD:SOT-23')

    resistors = [
        ('R201', '2.2k', RAIL5, 'CTL_OE_N_5V'), ('R202', '2.2k', RAIL5, 'CIC_OE_N_5V'),
        ('R203', '1k', RAIL5, 'DATA_OE_N_5V'), ('R204', '1k', RAIL5, 'DATA_DIR_5V'),
        ('R205', '100k', RAIL5, 'RESET_GATE_5V'),
        ('R206', '4.7k', RAIL3, 'ctl_oe_n'), ('R207', '4.7k', RAIL3, 'cic_oe_n'), ('R208', '4.7k', RAIL3, 'data_oe_n'),
        ('R209', '10k', 'data_dir', 'GND'), ('R210', '10k', 'cart_reset_pull_n', 'GND'),
        ('R211', '10k', RAIL5, 'SNES_IRQ_N'), ('R212', '10k', RAIL5, 'SNES_RESET_N'),
        ('R213', '10k', RAIL5, 'SNES_EXPAND')]
    for i, (ref, value, n1, n2) in enumerate(resistors):
        place(ref, 'Device:R', value, 38.1 + 25.4 * i, 355.6, {'1': n1, '2': n2}, R0603)

    # --- CIC data pins: one SN74LVC1T45 per pin, individually direction-controlled
    # A = FPGA (VCCA = INTERFACE_3V3), B = cartridge (VCCB = SNES_5V_CART).
    # DIR (referenced to VCCA) comes straight from its own FPGA pin: H = A->B
    # (drive the cartridge), L = B->A (listen; default through the DIR pull-down).
    for k, (ref, sock, a_net, dir_net, r_ser, r_pd, r_apd, r_dpd) in enumerate(CIC_XLAT):
        x = 640.08 + 96.52 * k
        xb = 'XB_' + sock[5:]
        place(ref, 'Logic_LevelTranslator:SN74LVC1T45DBV', 'SN74LVC1T45DBVR', x, 256.54,
              {'1': RAIL3, '2': 'GND', '3': a_net, '4': xb, '5': dir_net, '6': RAIL5},
              'Package_TO_SOT_SMD:SOT-23-6',
              fields={'Datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc1t45.pdf', 'LCSC': 'C7843'})
        caps += [(RAIL3, ref + ' VCCA pin 1'), (RAIL5, ref + ' VCCB pin 6')]
        for j, (rref, value, n1, n2) in enumerate([(r_ser, CIC_SERIES, xb, sock), (r_pd, CIC_CART_PULLDOWN, sock, 'GND'),
                                                    (r_apd, CIC_A_PULLDOWN, a_net, 'GND'),
                                                    (r_dpd, CIC_DIR_PULLDOWN, dir_net, 'GND')]):
            place(rref, 'Device:R', value, x + 30.48 + 10.16 * j, 256.54, {'1': n1, '2': n2}, R0603)

    caps += [(RAIL5, 'bulk'), (RAIL3, 'bulk')]
    for i, (net, _why) in enumerate(caps):
        ref = f'C{201 + i}'
        bulk = _why == 'bulk'
        place(ref, 'Device:C', '10uF 10V' if bulk else '100nF', 38.1 + 25.4 * (i % 20), 431.8 + 50.8 * (i // 20),
              {'1': net, '2': 'GND'}, 'Capacitor_SMD:C_0805_2012Metric' if bulk else C0603)

    place('TP201', 'Connector:TestPoint', 'AUDIO_L', 431.8, 355.6, {'1': 'SNES_AUDIO_L_IN'}, 'TestPoint:TestPoint_Pad_D1.0mm')
    place('TP202', 'Connector:TestPoint', 'AUDIO_R', 457.2, 355.6, {'1': 'SNES_AUDIO_R_IN'}, 'TestPoint:TestPoint_Pad_D1.0mm')
    # Default-off rails arrive from the future power sheet; the flags mark them
    # as externally supplied for ERC only. Remove when that sheet drives them.
    place('#FLG201', 'power:PWR_FLAG', 'PWR_FLAG', 482.6, 355.6, {'1': RAIL5})
    place('#FLG202', 'power:PWR_FLAG', 'PWR_FLAG', 508.0, 355.6, {'1': RAIL3})

    # --- Hierarchical ports: hier label -- wire/bus -- same-name local label --
    def port(name, shape, x, y):
        bus = '[' in name
        parts.append(f'(hierarchical_label {q(name)} (shape {shape}) (at {g(x)} {g(y)} 180) '
                     f'(effects (font (size 1.27 1.27)) (justify right)) (uuid {q(uid("hl:" + name))}))')
        kind = 'bus' if bus else 'wire'
        parts.append(f'({kind} (pts (xy {g(x)} {g(y)}) (xy {g(x + 7.62)} {g(y)})) (stroke (width 0) (type default)) '
                     f'(uuid {q(uid("pw:" + name))}))')
        parts.append(f'(label {q(name)} (at {g(x + 7.62)} {g(y)} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) '
                     f'(uuid {q(uid("pl:" + name))}))')
    for i, (name, shape) in enumerate(CART_PORTS):
        port(name, shape, 571.5, 327.66 + 5.08 * i)
    for i, (name, shape) in enumerate(PENDING_PORTS):
        port(name, shape, 718.82, 327.66 + 5.08 * i)

    notes = [
        txt('SNES CARTRIDGE-SIDE TRANSLATION AND PROTECTION', 20.32, 17.78, 2.54),
        txt('SN74LVC4245A: A port = 5 V cartridge (VCCA = SNES_5V_CART), B port = 3.3 V FPGA (VCCB = INTERFACE_3V3). '
            'DIR/OE are referenced to VCCA (TI SCAS375K). DIR=L: B->A (FPGA drives socket); DIR=H: A->B; OE=H: isolation.',
            20.32, 25.4),
        txt('U201-U206: console outputs, DIR strapped to GND (fixed FPGA->cartridge). U201-U205 share CTL_OE_N_5V (bridge ctl_oe_n); '
            'U206 (SYSTEM_CLK + CIC_CLK + CIC_SLAVE_RESET only) has its own CIC_OE_N_5V (sn64_top snes_cic_oe_n, enabled from the sequencer IFACE state).\n'
            'U207: D0-D7, DIR and OE both FPGA-controlled (bridge data_dir / data_oe_n). Unused B inputs tied to GND; unused A outputs no-connect.',
            20.32, 33.02),
        txt('CARTRIDGE OUTPUT DAMPING: 33 R arrays at the translator A pins (source-series). Values are provisional; tune after SI measurement.',
            20.32, 142.24, 1.524),
        txt('SENSE + RELEASE PATHS', 20.32, 210.82, 1.778),
        txt('U209 SN74LVC244A at 3.3 V: 5.5 V-tolerant inputs with Ioff; receives /IRQ, /RESET, EXPAND (CIC data pins use U215/U216).\n'
            'U210-U212 74LVC1G07 / U213 74LVC1G06: 3.3 V open-drain outputs (5.5 V tolerant, Ioff) pulled to SNES_5V_CART.\n'
            'No 5 V pull-up reaches an FPGA pin. Interface rail off or FPGA unconfigured => every translator /OE released high (isolated).\n'
            '/RESET: Q201 open-drain sink. RESET_GATE_5V pulled to 5 V: cartridge held in reset unless INTERFACE_3V3 is up AND the FPGA drives cart_reset_pull_n=1.',
            20.32, 215.9),
        txt('/OE and DIR edge timing: the bridge releases the data octet one 46.56 ns clock before turnaround. R203/R204 = 1k keep the passive rising edge short\n'
            '(about 10 pF load: tau ~10 ns); R201/R202 2.2k drive five/one /OE inputs where only permit-loss timing matters. Verify on hardware.',
            20.32, 312.42),
        txt('PULL/BIAS: /IRQ, /RESET, EXPAND 10k to cartridge 5 V (OpenSFC keeps pull-ups on IRQ/EXPAND); CIC_DATA0/1 10k pull-downs (R216/R217). Values provisional.',
            20.32, 325.12),
        txt('CIC DATA PINS - PER-PIN DIRECTION CONTROL (J2.55 CIC_DATA0 via U215, J2.24 CIC_DATA1 via U216)', 609.6, 203.2, 1.778),
        txt('SN74LVC1T45 (TI SCES515N): A = FPGA side (VCCA = INTERFACE_3V3), B = cartridge side (VCCB = SNES_5V_CART). No shared enable.\n'
            'DIR is referenced to VCCA and driven directly by its own FPGA pin cic_dataN_dir: H = A->B (FPGA drives the cartridge), L = B->A (listen).\n'
            'FPGA rule (no OE pin, SCES515N 8.2.2): set DIR high BEFORE driving cic_dataN; switch cic_dataN to input BEFORE setting DIR low.\n'
            'Idle: R216/R217 10k cartridge-side pull-down (lock expects released = low); R218/R219 100k A-side pull-down (same condition both sides);\n'
            'R220/R221 10k DIR pull-down (FPGA unconfigured = listen); R214/R215 33R series. Ioff + VCC isolation: either rail at GND => both ports high-Z.',
            609.6, 208.28),
        txt('DECOUPLING: one 100 nF per supply pin (place at the pin) plus one 10 uF bulk per rail.', 20.32, 401.32),
        txt('AUDIO: AUDIO_L_IN / AUDIO_R_IN pass untouched (no digital translation); test points only.', 406.4, 340.36),
        txt('HIERARCHICAL PORTS - CARTRIDGE SIDE (root J2 net labels)', 543.56, 317.5, 1.524),
        txt('PENDING PORTS - FPGA SIDE (bridge port names) + DEFAULT-OFF RAILS FROM FUTURE POWER SHEET', 690.88, 317.5, 1.524),
        txt('DRAFT 0.3.1-cart: schematic circuit candidate only. No PCB, SI simulation, power sequencing test, ESD part or cartridge test has been performed.\n'
            'SNES_5V_CART and INTERFACE_3V3 are hierarchical inputs from the power sheet; #FLG201/#FLG202 are kept because the power-sheet switch outputs are passive pins (ERC only).\n'
            'Open: socket ESD array selection, final damping/pull values (CIC pull-down value to confirm against a real key CIC).\n'
            'Sources: TI SCAS375K (SN74LVC4245A), SCAS414AG (SN74LVC244A), SCES296AG (SN74LVC1G07), SCES295AB (SN74LVC1G06), SCES515N (SN74LVC1T45).\n'
            'See docs/design/cart-interface-schematic.md.',
            20.32, 525.78)]
    contents = (f'(kicad_sch (version 20250114) (generator "sn64_cart_interface_authoring") (uuid {q(page_uuid)}) (paper "A1") '
                f'(title_block (title "SN 64 - SNES cartridge interface") (date "2026-09-29") (rev "0.3.1-cart") (company "SN 64") '
                f'(comment 1 "DESIGN DRAFT - NOT FOR MANUFACTURE"))\n(lib_symbols\n'
                + '\n'.join(dump(s) for s in libs.values()) + ')\n' + '\n'.join(parts + notes)
                + f'\n(sheet_instances (path {q("/" + root_uuid + "/" + sheet_uuid)} (page "3"))) (embedded_fonts no))')
    save(dest, contents)

    # Project-local library with only the two drawn symbols.
    own = [copy.deepcopy(s) for k, s in libs.items() if k.startswith(LIB + ':')]
    for s in own:
        s[1] = Quoted(str(s[1]).split(':', 1)[1])
    save(ROOT / 'libraries' / f'{LIB}.kicad_sym',
         '(kicad_symbol_lib (version 20250114) (generator "sn64_cart_interface_authoring")\n'
         + '\n'.join(dump(s) for s in own) + ')')
    table = parse(ROOT / 'sym-lib-table')
    table[:] = [e for e in table if not (isinstance(e, list) and e and e[0] == 'lib' and get(e, 'name')[1] == LIB)]
    table.append(['lib', ['name', Quoted(LIB)], ['type', Quoted('KiCad')], ['uri', Quoted('${KIPRJMOD}/libraries/' + LIB + '.kicad_sym')],
                  ['options', Quoted('')], ['descr', Quoted('SNES cartridge interface draft; see libraries/cart-provenance.json')]])
    save(ROOT / 'sym-lib-table', dump(table))

    datasheets = {}
    for name, rev in [('sn74lvc4245a', 'SCAS375K, revised May 2026'), ('sn74lvc244a', 'SCAS414AG, revised June 2026'),
                      ('sn74lvc1g07', 'SCES296AG, revised October 2025'), ('sn74lvc1g06', 'SCES295AB, revised October 2025'),
                      ('sn74lvc1t45', 'SCES515N, revised June 2024')]:
        rec = {'url': f'https://www.ti.com/lit/ds/symlink/{name}.pdf', 'revision': rev}
        if a.datasheets and (a.datasheets / f'{name}.pdf').exists():
            rec['sha256_of_downloaded_copy'] = hashlib.sha256((a.datasheets / f'{name}.pdf').read_bytes()).hexdigest()
        datasheets[name] = rec
    std = sorted({k for k in libs if not k.startswith(LIB + ':')})
    provenance = {
        'schema_version': 1, 'recorded_date': '2026-09-29',
        'scope': 'SNES cartridge-interface child-sheet symbols; schematic draft only, not a manufacturing or functional-validation release.',
        'tool_version': 'KiCad 10.0.6',
        'drawn_symbols': {
            'SN74LVC4245APW': {'library': f'libraries/{LIB}.kicad_sym', 'source': datasheets['sn74lvc4245a'],
                               'source_section': 'Figure 4-1 (DB/DW/PW top view) and Table 4-1 Pin Functions',
                               'pins': {p[0]: p[1] for p in LVC4245A_PINS},
                               'note': 'Pin 23 is shown as NC,VCCB in Figure 4-1 and VCCB in Table 4-1; drawn as VCCB and tied to VCCB (safe for both).',
                               'footprint': 'Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm (installed KiCad library)'},
            'SN74LVC244APW': {'library': f'libraries/{LIB}.kicad_sym', 'source': datasheets['sn74lvc244a'],
                              'source_section': 'Figure 4-2 (DB/DGV/DW/N/NS/DGS/PW packages)',
                              'pins': {p[0]: p[1] for p in LVC244A_PINS},
                              'footprint': 'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm (installed KiCad library)'}},
        'installed_kicad_symbols_used_unmodified': std,
        'installed_kicad_footprints_referenced': sorted(fps),
        'other_datasheets_checked': {k: v for k, v in datasheets.items() if k in ('sn74lvc1g07', 'sn74lvc1g06', 'sn74lvc1t45')},
        'cic_data_translator': {
            'part': 'SN74LVC1T45DBVR (LCSC C7843), installed KiCad symbol Logic_LevelTranslator:SN74LVC1T45DBV, '
                    'footprint Package_TO_SOT_SMD:SOT-23-6',
            'source': datasheets['sn74lvc1t45'],
            'pins_dbv_table_4_1': {'1': 'VCCA', '2': 'GND', '3': 'A', '4': 'B', '5': 'DIR', '6': 'VCCB'},
            'function_table_7_1': {'DIR=L': 'B data to A bus', 'DIR=H': 'A data to B bus'},
            'quoted_features': [
                'VCC isolation feature - if either VCC input is at GND, both ports are in the high-impedance state',
                'DIR input circuit referenced to VCCA',
                'Ioff supports partial-power-down mode operation'],
            'quoted_7_3_3': 'The inputs and outputs for this device enter a high-impedance state when the device is powered down, '
                            'inhibiting current backflow into the device.',
            'quoted_7_3_6': 'The I/Os of both ports will enter a high-impedance state when either of the supplies are at GND, '
                            'while the other supply is still connected to the device.',
            'quoted_8_2_2': 'Because the SN74LVC1T45 does not have an output-enable (OE) pin, the system designer should take '
                            'precautions to avoid bus contention between SYSTEM-1 and SYSTEM-2 when changing directions.',
            'ioff_limit_5_5': 'A port (VCCA = 0 V) and B port (VCCB = 0 V), VI or VO = 0 to 5.5 V: +/-1 uA at 25 C, +/-2 uA at -40 to 85 C',
            'dir_timing_5_8_vcca_3v3_vccb_5v_max_ns': {'tPHZ DIR->A': 7.3, 'tPLZ DIR->A': 5.7, 'tPHZ DIR->B': 6.8,
                                                       'tPLZ DIR->B': 4.9,
                                                       'tPZH DIR->A': 10.3, 'tPZL DIR->A': 11.3,
                                                       'tPZH DIR->B': 10.1, 'tPZL DIR->B': 11.3},
            'text_extraction': 'pdftotext (poppler, w64 Git) of the downloaded copy; table cells re-read in -raw mode.'},
        'licenses': 'KiCad library content: CC-BY-SA-4.0 with the KiCad library exception (see KiCad library LICENSE). '
                    'Drawn symbols: SN64 project content; pin data are facts from the cited TI datasheets.'}
    save(ROOT / 'libraries' / 'cart-provenance.json', json.dumps(provenance, indent=2))

    # Append the sheet symbol to the root; J2 net labels sit on the cartridge pins.
    original = (ROOT / 'sn64.kicad_sch').read_text(encoding='utf-8')
    if sheet_uuid in original:
        # --force update: remove ONLY the sheet symbol this script appended and
        # the labels/no-connects it placed on that symbol's pins, then append
        # the regenerated symbol. Anything else in the root is kept verbatim.
        lines = original.rstrip().split('\n')
        idx = [i for i, line in enumerate(lines) if line.startswith('(sheet ') and q(sheet_uuid) in line]
        if len(idx) != 1:
            raise SystemExit('Root sheet symbol is no longer in the authored one-line form (edited in KiCad?); '
                             'update its pins in KiCad instead of regenerating.')
        old_names = re.findall(r'\(pin "([^"]+)" \w+ \(at', lines[idx[0]])
        ours = {q(uid('root-label:' + n)) for n in old_names} | {q(uid('root-nc:' + n)) for n in old_names}
        drop = set(idx)
        if idx[0] > 0 and lines[idx[0] - 1] == '':
            drop.add(idx[0] - 1)      # blank separator written by the original append
        for i, line in enumerate(lines):
            if re.match(r'\((label|no_connect) ', line) and any(f'(uuid {u})' in line for u in ours):
                drop.add(i)
        original = '\n'.join(line for i, line in enumerate(lines) if i not in drop) + '\n'
    if sheet_uuid not in original:
        sx, sy, w = 375.92, 38.1, 25.4
        pins, labels = [], []
        for i, (name, shape) in enumerate(CART_PORTS):
            py = 43.18 + 5.08 * i
            pins.append(f'(pin {q(name)} {shape} (at {g(sx)} {g(py)} 180) (effects (font (size 1.27 1.27)) (justify left)) '
                        f'(uuid {q(uid("root-pin:" + name))}))')
            labels.append(f'(label {q(name)} (at {g(sx)} {g(py)} 180) (effects (font (size 1.016 1.016)) (justify right bottom)) '
                          f'(uuid {q(uid("root-label:" + name))}))')
        base = 43.18 + 5.08 * len(CART_PORTS)
        for i, (name, shape) in enumerate(PENDING_PORTS):
            py = base + 2.54 * i
            pins.append(f'(pin {q(name)} {shape} (at {g(sx)} {g(py)} 180) (effects (font (size 1.27 1.27)) (justify left)) '
                        f'(uuid {q(uid("root-pin:" + name))}))')
            # Pending FPGA-side pins: no root net exists yet (no FPGA sheet). A
            # no-connect marker records that deliberately; remove it when the
            # FPGA/power sheets connect these pins. The child keeps the names.
            labels.append(f'(no_connect (at {g(sx)} {g(py)}) (uuid {q(uid("root-nc:" + name))}))')
        h = round(base + 2.54 * len(PENDING_PORTS) + 2.54 - sy, 2)
        block = (f'(sheet (at {g(sx)} {g(sy)}) (size {g(w)} {g(h)}) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0)) '
                 f'(uuid {q(sheet_uuid)}) '
                 + prop('Sheetname', SHEET_NAME, sx, sy - 1.27, justify='left bottom')
                 + prop('Sheetfile', SHEET_FILE, sx, sy + h + 1.27, justify='left top')
                 + ' ' + ' '.join(pins)
                 + f' (instances (project "sn64" (path {q("/" + root_uuid)} (page "3")))))\n' + '\n'.join(labels))
        original = original.rstrip()[:-1] + '\n' + block + '\n)'
        save(ROOT / 'sn64.kicad_sch', original.rstrip())
    n_pins = sum(1 for p in parts if p.startswith('(pin '))
    print('Authored cartridge interface sheet:', len([p for p in parts if p.startswith('(symbol (lib_id')]), 'symbols;',
          n_pins, 'pins;', len(fps), 'footprints')


if __name__ == '__main__':
    main()
