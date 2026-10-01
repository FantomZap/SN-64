"""Author the SN64 v2 schematic set (one board) from one script.

v2 (2026-09-30, docs/design/v2-board.md): the FPGA absorbs the USB device, the
clock generation, the cartridge audio ADC and the power sequencing; rail
telemetry is one I2C ADC; the N64 edge is on the board and its bus goes straight to the
FPGA; the cartridge translators are four 16-bit parts plus one open-drain hex
driver. Wiring is by global label so the sheets need no hierarchical pins.

  python build_v2_schematic.py [--force]

Outputs (hardware/sn64-v2): sn64-v2.kicad_sch (root), fpga.kicad_sch,
cart.kicad_sch, power.kicad_sch, libraries/SN64_V2.kicad_sym (drawn TI parts:
TPS2121RUX, TLA2528RTE, TPS2553DBV) + copies of the v1 libraries it reuses,
sym-lib-table, fp-lib-table, sn64-v2.kicad_pro, libraries/v2-provenance.json.
Pure Python (KiCad's python for the shared parser only).
"""
import argparse
import copy
import json
import math
import shutil
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
REPO = V2.parents[1]
V1 = REPO / 'hardware/sn64'
KICAD_SHARE = Path('C:/Program Files/KiCad/10.0/share/kicad')
sys.path.insert(0, str(V1 / 'tools'))
sys.path.insert(0, str(HERE))
from add_av_clock_sheet import parse, parse_text, dump, items, get, Quoted, q, g   # noqa: E402
import pin_plan                                                                     # noqa: E402

NS = uuid.UUID('5d2f1c8e-7a3b-4e90-b6c1-9f0d2a4e6b21')
PROJECT = 'sn64-v2'


def uid(s):
    return str(uuid.uuid5(NS, s))


def prop(k, v, x, y, hide=False, justify=None, angle=0):
    j = f' (justify {justify})' if justify else ''
    return (f'(property {q(k)} {q(v)} (at {g(x)} {g(y)} {angle}) (effects (font (size 1.27 1.27)){j}'
            f'{" (hide yes)" if hide else ""}))')


def text(s, x, y, size=1.27):
    return (f'(text {q(s)} (exclude_from_sim no) (at {g(x)} {g(y)} 0) (effects (font (size {size} {size})) (justify left top)) '
            f'(uuid {q(uid("text:" + s[:80]))}))')


def save(path, s):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s + '\n', encoding='utf-8', newline='\n')


# ---------------------------------------------------------------------------
# Drawn symbols (TI pin tables from LCSC/EasyEDA pinouts, cross-checked with the datasheets)
# (number, name, electrical type, side)   side: L, R, T, B
# ---------------------------------------------------------------------------
TPS2121_PINS = [('7', 'IN1', 'power_in', 'L'), ('2', 'IN2', 'power_in', 'L'), ('6', 'PR1', 'input', 'L'),
                ('3', 'CP2', 'input', 'L'), ('5', 'OV1', 'input', 'L'), ('4', 'OV2', 'input', 'L'),
                ('1', 'OUT', 'power_out', 'R'), ('8', 'OUT', 'passive', 'R'), ('9', 'ST', 'open_collector', 'R'),
                ('10', 'ILM', 'passive', 'R'), ('11', 'SS', 'passive', 'R'), ('12', 'GND', 'power_in', 'B')]
TLA2528_PINS = [('15', 'AIN0', 'input', 'L'), ('16', 'AIN1', 'input', 'L'), ('1', 'AIN2', 'input', 'L'),
                ('2', 'AIN3', 'input', 'L'), ('3', 'AIN4', 'input', 'L'), ('4', 'AIN5', 'input', 'L'),
                ('5', 'AIN6', 'input', 'L'), ('6', 'AIN7', 'input', 'L'),
                ('13', 'SCL', 'input', 'R'), ('14', 'SDA', 'bidirectional', 'R'), ('11', 'ADDR', 'input', 'R'),
                ('8', 'DECAP', 'passive', 'R'), ('12', 'NC', 'no_connect', 'R'),
                ('7', 'AVDD', 'power_in', 'T'), ('10', 'DVDD', 'power_in', 'T'),
                ('9', 'GND', 'power_in', 'B'), ('17', 'EP', 'power_in', 'B')]
TPS2553_PINS = [('1', 'IN', 'power_in', 'L'), ('3', 'EN', 'input', 'L'), ('5', 'ILIM', 'passive', 'L'),
                ('6', 'OUT', 'power_out', 'R'), ('4', '~{FAULT}', 'open_collector', 'R'), ('2', 'GND', 'power_in', 'B')]


def own_symbol(lib, name, value, pins, descr, datasheet, footprint):
    sides = {s: [p for p in pins if p[3] == s] for s in 'LRTB'}
    rows = max(len(sides['L']), len(sides['R']))
    cols = max(len(sides['T']), len(sides['B']), 2)
    hh = max(7.62, (rows + 1) * 1.27)
    hw = max(12.7, (cols + 1) * 2.54, 10.16)
    top, bottom = hh, -hh
    lines = [f'(symbol {q(name)} (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)',
             prop('Reference', 'U', 0, top + 3.81), prop('Value', value, 0, bottom - 3.81),
             prop('Footprint', footprint, 0, bottom - 6.35, True), prop('Datasheet', datasheet, 0, bottom - 8.89, True),
             prop('Description', descr, 0, bottom - 11.43, True),
             f'(symbol {q(name + "_0_1")} (rectangle (start {g(-hw)} {g(top)}) (end {g(hw)} {g(bottom)}) '
             f'(stroke (width 0.254) (type default)) (fill (type background))))',
             f'(symbol {q(name + "_1_1")}']

    def emit(number, label, typ, x, y, angle):
        lines.append(f'(pin {typ} line (at {g(x)} {g(y)} {angle}) (length 5.08) (name {q(label)} '
                     f'(effects (font (size 1.27 1.27)))) (number {q(number)} (effects (font (size 1.016 1.016)))))')
    for i, (n, lab, typ, _) in enumerate(sides['L']):
        emit(n, lab, typ, -hw - 5.08, top - 2.54 * (i + 1), 0)
    for i, (n, lab, typ, _) in enumerate(sides['R']):
        emit(n, lab, typ, hw + 5.08, top - 2.54 * (i + 1), 180)
    for i, (n, lab, typ, _) in enumerate(sides['T']):
        emit(n, lab, typ, -hw + 2.54 * (i + 1) + (hw - 2.54 * (len(sides['T']) + 1) / 2) - 1.27, top + 5.08, 270)
    for i, (n, lab, typ, _) in enumerate(sides['B']):
        emit(n, lab, typ, -hw + 2.54 * (i + 1) + (hw - 2.54 * (len(sides['B']) + 1) / 2) - 1.27, bottom - 5.08, 90)
    return parse_text('\n'.join(lines) + ') (embedded_fonts no))')


# ---------------------------------------------------------------------------
# Sheet builder
# ---------------------------------------------------------------------------
class Sheet:
    SMALL = ('Device:R', 'Device:C', 'Device:LED', 'Device:Thermistor_NTC', 'Connector:TestPoint', 'power:PWR_FLAG')

    def __init__(self, name, file, page, paper, root_uuid, own_libs, project=PROJECT, root_level=False):
        self.name, self.file, self.page, self.paper = name, file, page, paper
        self.root_uuid, self.project, self.root_level = root_uuid, project, root_level
        self.sheet_uuid = uid('sheet:' + file)
        self.page_uuid = root_uuid if root_level else uid('page:' + file)
        self.path = '/' + root_uuid if root_level else '/' + root_uuid + '/' + self.sheet_uuid
        self.own_libs = own_libs              # lib name -> parsed library node
        self.libs, self.parts, self.fps = {}, [], set()
        self.anchors = {}
        self.cursor = [20.0, 30.0]
        self.row_h = 0.0
        self.width = {'A0': 1189, 'A1': 841, 'A2': 594, 'A3': 420}[paper] - 20
        self.bom = []

    def claim(self, x, y, kind, name):
        key = (round(x, 3), round(y, 3))
        prev = self.anchors.get(key)
        assert prev is None or prev == (kind, name), f'{self.file}: anchor collision at {key}: {prev} vs {(kind, name)}'
        self.anchors[key] = (kind, name)

    def load(self, lib_id):
        if lib_id in self.libs:
            return self.libs[lib_id]
        lib, name = lib_id.split(':')
        db = self.own_libs[lib] if lib in self.own_libs else parse(KICAD_SHARE / 'symbols' / f'{lib}.kicad_sym')
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
        self.libs[lib_id] = s
        return s

    def unit_pins(self, sym, unit):
        out = []
        for u in items(sym, 'symbol'):
            n = str(u[1])
            try:
                un = int(n.rsplit('_', 2)[1])
            except ValueError:
                continue
            if un in (0, unit):
                out += items(u, 'pin')
        return out

    def next_cell(self, w, h):
        if self.cursor[0] + w > self.width:
            self.cursor[0] = 20.0
            self.cursor[1] += self.row_h
            self.row_h = 0.0
        x, y = self.cursor
        self.cursor[0] += w
        self.row_h = max(self.row_h, h)
        return x, y

    def newline(self, gap=10.0):
        self.cursor[0] = self.width + 1   # force a wrap
        self.next_cell(0, 0)
        self.cursor[1] += gap

    def place(self, ref, lib_id, value, nets, fp='', fields=None, unit=1, dnp=False):
        sym = self.load(lib_id)
        pins = self.unit_pins(sym, unit)
        nums = {str(get(p, 'number')[1]) for p in pins}
        assert nums == set(nets), (self.file, ref, sorted(nums ^ set(nets)))
        xs = [float(get(p, 'at')[1]) for p in pins]
        ys = [float(get(p, 'at')[2]) for p in pins]
        small = lib_id in self.SMALL
        if small:
            w, h = 16.0, 30.0
            ox, oy = 8.0, 12.0
        else:
            w = (max(xs) - min(xs)) + 2 * 30.0
            h = (max(ys) - min(ys)) + 26.0
            ox, oy = -min(xs) + 30.0, max(ys) + 14.0
        cx, cy = self.next_cell(w, h)
        x, y = cx + ox, cy + oy
        x, y = round(x / 1.27) * 1.27, round(y / 1.27) * 1.27
        if small:
            rx, ry, vx, vy, just = x + 2.54, y - 1.27, x + 2.54, y + 1.27, 'left'
        else:
            rx, ry, vx, vy, just = x + min(xs), y - max(ys) - 7.62, x + min(xs), y - max(ys) - 5.08, 'left'
        hidden = ref.startswith('#')
        key = ref + (f':u{unit}' if unit != 1 else '')
        out = [f'(symbol (lib_id {q(lib_id)}) (at {g(x)} {g(y)} 0) (unit {unit}) (exclude_from_sim no) (in_bom {"no" if hidden else "yes"}) '
               f'(on_board {"no" if hidden else "yes"}) (dnp {"yes" if dnp else "no"}) (uuid {q(uid("sym:" + key))})',
               prop('Reference', ref, rx, ry, hidden, just), prop('Value', value, vx, vy, hidden, just),
               prop('Footprint', fp, x, y, True), prop('Datasheet', (fields or {}).get('Datasheet', ''), x, y, True)]
        for k, v in (fields or {}).items():
            if k != 'Datasheet':
                out.append(prop(k, v, x, y, True))
        for pin in pins:
            out.append(f'(pin {q(get(pin, "number")[1])} (uuid {q(uid(key + ":" + str(get(pin, "number")[1])))}))')
        out.append(f'(instances (project {q(self.project)} (path {q(self.path)} (reference {q(ref)}) (unit {unit})))))')
        self.parts.extend(out)
        seen = set()
        for pin in pins:
            number = str(get(pin, 'number')[1])
            net = nets[number]
            at = get(pin, 'at')
            px, py, angle = x + float(at[1]), y - float(at[2]), int(float(at[3]))
            role = key + ':' + number
            if (px, py, net) in seen:
                continue
            seen.add((px, py, net))
            self.claim(px, py, 'pin', role)
            if net is None:
                self.parts.append(f'(no_connect (at {g(px)} {g(py)}) (uuid {q(uid("nc:" + role))}))')
                continue
            dx = -5.08 * round(math.cos(math.radians(angle)))
            dy = 5.08 * round(math.sin(math.radians(angle)))
            ex, ey = px + dx, py + dy
            self.claim(ex, ey, 'label', net + '@' + role)
            self.parts.append(f'(wire (pts (xy {g(px)} {g(py)}) (xy {g(ex)} {g(ey)})) (stroke (width 0) (type default)) '
                              f'(uuid {q(uid("w:" + role))}))')
            if dx < 0:
                la, lj = 180, 'right'
            elif dx > 0:
                la, lj = 0, 'left'
            elif dy > 0:
                la, lj = 270, 'right'
            else:
                la, lj = 90, 'left'
            self.parts.append(f'(global_label {q(net)} (shape passive) (at {g(ex)} {g(ey)} {la}) (fields_autoplaced yes) '
                              f'(effects (font (size 1.016 1.016)) (justify {lj})) (uuid {q(uid("gl:" + role))}) '
                              f'(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {g(ex)} {g(ey)} 0) (effects (font (size 1.27 1.27)) (hide yes))))')
        if fp:
            self.fps.add(fp)
        if not hidden and unit == 1:
            self.bom.append((ref, value, fp))

    def res(self, ref, value, n1, n2, fields=None):
        self.place(ref, 'Device:R', value, {'1': n1, '2': n2}, 'Resistor_SMD:R_0603_1608Metric', fields)

    def cap(self, ref, value, n1, n2, fp='Capacitor_SMD:C_0603_1608Metric', fields=None):
        self.place(ref, 'Device:C', value, {'1': n1, '2': n2}, fp, fields)

    def flag(self, net):
        self.nflag = getattr(self, 'nflag', 0) + 1
        self.place(f'#FLG{self.nflag}', 'power:PWR_FLAG', 'PWR_FLAG', {'1': net})

    def note(self, s, size=1.27):
        self.newline(4)
        cx, cy = self.next_cell(self.width - 20, 6 + 4 * s.count('\n'))
        self.parts.append(text(s, cx, cy, size))

    def render(self, title):
        libs = '\n'.join(dump(s) for s in self.libs.values())
        return (f'(kicad_sch (version 20250114) (generator "sn64_v2_authoring") (generator_version "10.0") (uuid {q(self.page_uuid)}) '
                f'(paper {q(self.paper)}) (title_block (title {q(title)}) (date "2026-09-30") (rev "v2 draft 0.1") '
                f'(comment 1 "DESIGN DRAFT - NOT FOR MANUFACTURE"))\n(lib_symbols\n{libs}\n)\n'
                + '\n'.join(self.parts)
                + f'\n(sheet_instances (path {q("/" if self.root_level else self.path)} (page {q(self.page)}))) (embedded_fonts no))')


def root_sheet(root_uuid, sheets, title, paper='A4'):
    out = [f'(kicad_sch (version 20250114) (generator "sn64_v2_authoring") (generator_version "10.0") (uuid {q(root_uuid)}) '
           f'(paper {q(paper)}) (title_block (title {q(title)}) (date "2026-09-30") (rev "v2 draft 0.1") '
           f'(comment 1 "DESIGN DRAFT - NOT FOR MANUFACTURE"))', '(lib_symbols)']
    for i, sh in enumerate(sheets):
        x, y, w, h = 30 + i * 60, 40, 45, 25
        out.append(f'(sheet (at {x} {y}) (size {w} {h}) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (fields_autoplaced yes) '
                   f'(stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid {q(sh.sheet_uuid)}) '
                   f'(property "Sheetname" {q(sh.name)} (at {x} {y - 0.7} 0) (effects (font (size 1.27 1.27)) (justify left bottom))) '
                   f'(property "Sheetfile" {q(sh.file)} (at {x} {y + h + 0.6} 0) (effects (font (size 1.27 1.27)) (justify left top))) '
                   f'(instances (project {q(PROJECT)} (path {q("/" + root_uuid)} (page {q(sh.page)})))))')
    out.append(text(title + '\nSheets are wired by global label; see docs/design/v2-board.md for the write-up.', 30, 90, 1.5))
    out.append('(sheet_instances (path "/" (page "1"))) (embedded_fonts no))')
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# Parts data
# ---------------------------------------------------------------------------
GND, V33, V25, V11, V5, VIN, VBUS, HOST, CART5 = 'GND', 'FPGA_3V3', 'FPGA_2V5', 'FPGA_1V1', '5V_SYS', 'SYS_VIN', 'USB_VBUS', 'HOST_3V3', 'SNES_5V_CART'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'
LCSC = {  # JLC/LCSC stock snapshot 2026-09-30 (pcbparts jlc_search / mouser)
    'LFE5U-85F-8BG381I': ('Mouser 842-LFE5U85F8BG381I', 141), 'W25Q128JVSIQ': ('C97521', None),
    '1631-27005-BTBEYA': ('C3003262', 7439), 'TPS3808G01DBVR': ('C19653', 18100), 'USBLC6-2SC6': ('C7519', None),
    'SN74ALVC164245DGGR': ('C7128', 14549), 'SN74LVC07APWR': ('C7809', 14747), 'TLA2528IRTER': ('C2866175', 4658),
    'TPS2121RUXR': ('C485916', 32370), 'TPS63070RNMR': ('C109322', 25100), 'TLV62569DBVR': ('C141836', 246272),
    'AP2112K-2.5TRG1': ('C51118', None), 'TPS2553DBVR': ('C55266', 59074), 'PNR4020-1R5M': ('C54620133', 7449),
    'FNR4030S2R2MT': ('C167869', 67195), 'DX07S016JA3R1500': ('C2939926', None)}
SOCKET = {1: 'SNES_SYSTEM_CLK', 2: 'SNES_EXPAND', 3: 'SNES_PA6', 4: 'SNES_PRD_N', 5: GND, 6: 'SNES_A11', 7: 'SNES_A10', 8: 'SNES_A9',
          9: 'SNES_A8', 10: 'SNES_A7', 11: 'SNES_A6', 12: 'SNES_A5', 13: 'SNES_A4', 14: 'SNES_A3', 15: 'SNES_A2', 16: 'SNES_A1',
          17: 'SNES_A0', 18: 'SNES_IRQ_N', 19: 'SNES_D0', 20: 'SNES_D1', 21: 'SNES_D2', 22: 'SNES_D3', 23: 'SNES_RD_N',
          24: 'SNES_CIC_DATA1', 25: 'SNES_CIC_SLAVE_RESET', 26: 'SNES_RESET_N', 27: CART5, 28: 'SNES_PA0', 29: 'SNES_PA2',
          30: 'SNES_PA4', 31: 'SNES_AUDIO_L_IN', 32: 'SNES_WRAMSEL_N', 33: 'SNES_REFRESH', 34: 'SNES_PA7', 35: 'SNES_PWR_N',
          36: GND, 37: 'SNES_A12', 38: 'SNES_A13', 39: 'SNES_A14', 40: 'SNES_A15', 41: 'SNES_A16', 42: 'SNES_A17', 43: 'SNES_A18',
          44: 'SNES_A19', 45: 'SNES_A20', 46: 'SNES_A21', 47: 'SNES_A22', 48: 'SNES_A23', 49: 'SNES_ROMSEL_N', 50: 'SNES_D4',
          51: 'SNES_D5', 52: 'SNES_D6', 53: 'SNES_D7', 54: 'SNES_WR_N', 55: 'SNES_CIC_DATA0', 56: 'SNES_CIC_CLK', 57: 'SNES_PHI2',
          58: CART5, 59: 'SNES_PA1', 60: 'SNES_PA3', 61: 'SNES_PA5', 62: 'SNES_AUDIO_R_IN'}
# N64 edge (SummerCart64 numbering, v1 J1) and the riser joint: header pins 1-27 carry the signals the
# FPGA uses, 28-31 HOST_3V3, 32-40 GND. 12 V, audio, video sync and the key pins stay on the riser only.
N64_EDGE = {1: GND, 2: GND, 3: 'N64_AD15', 4: 'N64_AD14', 5: 'N64_AD13', 6: GND, 7: 'N64_AD12', 8: 'N64_WRITE_N', 9: HOST,
            10: 'N64_READ_N', 11: 'N64_AD11', 12: 'N64_AD10', 13: 'HOST_12V', 14: 'N64_KEY1_RESERVED', 15: 'N64_AD9', 16: 'N64_AD8',
            17: HOST, 18: 'N64_CIC_DATA', 19: 'N64_PIF_CLK', 20: 'N64_RESET_N', 21: 'N64_JOYBUS', 22: GND, 23: GND, 24: 'N64_AUDIO_L',
            25: GND, 26: GND, 27: GND, 28: 'N64_AD0', 29: 'N64_AD1', 30: 'N64_AD2', 31: GND, 32: 'N64_AD3', 33: 'N64_ALE_L', 34: HOST,
            35: 'N64_ALE_H', 36: 'N64_AD4', 37: 'N64_AD5', 38: 'HOST_12V', 39: 'N64_KEY2_RESERVED', 40: 'N64_AD6', 41: 'N64_AD7',
            42: HOST, 43: 'N64_CIC_CLK', 44: 'N64_INT_N', 45: 'N64_NMI_N', 46: 'N64_VIDEO_SYNC_RESERVED', 47: GND, 48: GND,
            49: 'N64_AUDIO_R', 50: GND}
JOINT = ([f'N64_AD{i}' for i in range(16)] + ['N64_ALE_L', 'N64_ALE_H', 'N64_READ_N', 'N64_WRITE_N', 'N64_RESET_N', 'N64_NMI_N',
                                                'N64_INT_N', 'N64_CIC_CLK', 'N64_CIC_DATA', 'N64_PIF_CLK', 'N64_JOYBUS']
         + [HOST] * 4 + [GND] * 9)
assert len(JOINT) == 40
JOINT_NETS = {str(i + 1): n for i, n in enumerate(JOINT)}


def translator(sh, ref, a1, b1, a2, b2, dir1, oe1, dir2, oe2):
    nets = {'1': dir1, '24': dir2, '25': oe2, '48': oe1, '4': GND, '10': GND, '15': GND, '21': GND, '28': GND, '34': GND,
            '39': GND, '45': GND, '7': CART5, '18': CART5, '31': V33, '42': V33}
    for i, p in enumerate(['47', '46', '44', '43', '41', '40', '38', '37']):
        nets[p] = a1[i]
    for i, p in enumerate(['2', '3', '5', '6', '8', '9', '11', '12']):
        nets[p] = b1[i]
    for i, p in enumerate(['36', '35', '33', '32', '30', '29', '27', '26']):
        nets[p] = a2[i]
    for i, p in enumerate(['13', '14', '16', '17', '19', '20', '22', '23']):
        nets[p] = b2[i]
    sh.place(ref, '74xx:74ALVC164245', 'SN74ALVC164245DGGR', nets, 'Package_SO:TSSOP-48_6.1x12.5mm_P0.5mm',
             {'Datasheet': 'https://www.ti.com/lit/ds/symlink/sn74alvc164245.pdf', 'LCSC': LCSC['SN74ALVC164245DGGR'][0],
              'MPN': 'SN74ALVC164245DGGR', 'Note': 'A = 3.3 V FPGA side, B = 5 V cartridge side; Ioff partial-power-down (sd2snes U101-U103 reuse)'})


def build_fpga_sheet(sh, balls, rows):
    sh.note('SN64 v2 FPGA SHEET - LFE5U-85F CABGA381 (-8BG381I, Mouser stock), configuration flash, 27 MHz clock, USB device pins, '
            'telemetry ADC, reset supervisor.\nPin map: interfaces/fpga-pin-map.csv (tools/pin_plan.py): every signal on rings 1-3; '
            'constraints fpga/constraints/sn64_board.lpf.', 1.8)
    nets = pin_plan.fpga_nets(balls, rows)
    for b, d in balls.items():
        if d['fn'] in pin_plan.JTAG:
            nets[b] = pin_plan.JTAG[d['fn']]
    fields = {'Datasheet': 'https://www.latticesemi.com/view_document?document_id=50461', 'MPN': 'LFE5U-85F-8BG381I',
              'Source': LCSC['LFE5U-85F-8BG381I'][0], 'Note': 'ECP5-85 CABGA381, speed 8, industrial (the grade in stock)'}
    sym = sh.load('FPGA_Lattice:LFE5U-85F-8BG381x')
    for unit in range(1, 10):
        pins = sh.unit_pins(sym, unit)
        unets = {str(get(p, 'number')[1]): nets[str(get(p, 'number')[1])] for p in pins}
        sh.place('U1', 'FPGA_Lattice:LFE5U-85F-8BG381x', 'LFE5U-85F-8BG381I', unets,
                 'Package_BGA:Lattice_caBGA-381_17x17mm_Layout20x20_P0.8mm', fields, unit=unit)
    sh.newline()
    # Decoupling (provisional: Lattice ECP5 hardware checklist counts, not one per ball as in v1).
    n = 1
    for rail, count100, count10 in ((V11, 8, 2), (V25, 2, 1), (V33, 14, 3)):
        for _ in range(count100):
            sh.cap(f'C{n}', '100nF 16V X7R', rail, GND); n += 1
        for _ in range(count10):
            sh.cap(f'C{n}', '10uF 10V X5R', rail, GND, C0805); n += 1
    sh.newline()
    # Configuration flash (W25Q128JVS, v1 wiring: CS 4.7k up, WP/HOLD 10k up, MCLK 33R series + 1k up, CFG1 up)
    sh.place('U2', 'Memory_Flash:W25Q128JVS', 'W25Q128JVSIQ',
             {'1': 'FLASH_CS_N', '2': 'FLASH_D1', '3': 'FLASH_D2', '4': GND, '5': 'FLASH_D0', '6': 'FLASH_SCK_R', '7': 'FLASH_D3', '8': V33},
             'Package_SO:SOIC-8_5.3x5.3mm_P1.27mm', {'Datasheet': 'https://www.winbond.com/hq/product/code-storage-flash-memory/serial-nor-flash/?__locale=en&partNo=W25Q128JV',
                                                     'LCSC': LCSC['W25Q128JVSIQ'][0], 'MPN': 'W25Q128JVSIQ'})
    sh.res('R1', '33', 'FLASH_SCK', 'FLASH_SCK_R')
    sh.res('R2', '1k', V33, 'FLASH_SCK_R')
    sh.res('R3', '4.7k', V33, 'FLASH_CS_N')
    sh.res('R4', '10k', V33, 'FLASH_D2')
    sh.res('R5', '10k', V33, 'FLASH_D3')
    sh.cap('C31', '100nF', V33, GND)
    sh.res('R6', '4.7k', V33, 'FPGA_CFG1')     # CFG[2:0] = 010: master SPI boot (v1 wiring, TN-02039)
    sh.res('R7', '4.7k', V33, 'FPGA_PROGRAMN')
    sh.res('R8', '4.7k', V33, 'FPGA_INITN')
    sh.res('R9', '4.7k', V33, 'FPGA_DONE')
    sh.res('R10', '10k', GND, 'FPGA_CFG0')
    sh.res('R11', '10k', GND, 'FPGA_CFG2')
    sh.newline()
    # JTAG service pads (no header fitted) and pulls
    for i, net in enumerate(['JTAG_TCK', 'JTAG_TMS', 'JTAG_TDI', 'JTAG_TDO', GND], start=1):
        sh.place(f'TP{i}', 'Connector:TestPoint', net, {'1': net}, 'TestPoint:TestPoint_Pad_1.5x1.5mm')
    sh.res('R12', '4.7k', V33, 'JTAG_TDI')
    sh.res('R13', '4.7k', V33, 'JTAG_TMS')
    sh.res('R14', '4.7k', V33, 'JTAG_TDO')
    sh.newline()
    # 27 MHz oscillator (all clocks come from the FPGA PLLs: docs/design/v2-board.md)
    sh.place('X1', 'Oscillator:ASE-xxxMHz', '27MHz 1631-27005-BTBEYA', {'1': V33, '2': GND, '3': 'OSC_27', '4': V33},
             'Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm',
             {'Datasheet': 'https://www.lcsc.com/product-detail/C3003262.html', 'LCSC': LCSC['1631-27005-BTBEYA'][0],
              'MPN': '1631-27005-BTBEYA', 'Frequency': '27MHz', 'Note': 'CMOS 3.3 V, +-50 ppm, 10 mA (JLC stock 7439)'})
    sh.cap('C32', '100nF', V33, GND)
    # Reset supervisor: TPS3808G01 on FPGA_3V3 (v1 values 649k/100k: 3.03 V threshold), RESET -> BOARD_RESET_N
    sh.place('U3', 'Power_Supervisor:TPS3808DBV', 'TPS3808G01DBVR',
             {'1': 'BOARD_RESET_N', '2': GND, '3': None, '4': None, '5': 'SENSE_3V3', '6': V33},
             'Package_TO_SOT_SMD:SOT-23-6', {'Datasheet': 'https://www.ti.com/lit/ds/symlink/tps3808.pdf', 'LCSC': LCSC['TPS3808G01DBVR'][0], 'MPN': 'TPS3808G01DBVR'})
    sh.res('R15', '649k 1%', V33, 'SENSE_3V3')
    sh.res('R16', '100k 1%', GND, 'SENSE_3V3')
    sh.res('R17', '10k', V33, 'BOARD_RESET_N')
    sh.cap('C33', '100nF', V33, GND)
    # Status LED
    sh.place('D1', 'Device:LED', 'LED green 0603', {'1': 'LED_K', '2': V33}, 'LED_SMD:LED_0603_1608Metric')
    sh.res('R18', '1k', 'LED_K', 'LED')
    sh.newline()
    # USB device: D+/D- straight to the FPGA (OrangeCrab / TinyFPGA practice): 22R series, 1.5k pull-up switched by USB_PU
    sh.res('R19', '22', 'USB_DP', 'USB_DP_F')
    sh.res('R20', '22', 'USB_DN', 'USB_DN_F')
    sh.res('R21', '1.5k', 'USB_PU', 'USB_DP')
    sh.newline()
    # Telemetry ADC: TLA2528 (8 ch, 12 bit, I2C). AVDD is the reference, so FPGA_3V3 itself is watched by U3.
    sh.place('U6', 'SN64_V2:TLA2528RTE', 'TLA2528IRTER',
             {'15': 'MON_HOST_3V3', '16': 'MON_VBUS', '1': 'MON_5V_SYS', '2': 'MON_CART_5V', '3': V11, '4': 'MON_NTC',
              '5': 'USB_CC1', '6': 'USB_CC2', '13': 'ADC_SCL', '14': 'ADC_SDA', '11': GND, '8': 'ADC_DECAP', '12': None,
              '7': V33, '10': V33, '9': GND, '17': GND},
             'Package_DFN_QFN:Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm',
             {'Datasheet': 'https://www.ti.com/lit/ds/symlink/tla2528.pdf', 'LCSC': LCSC['TLA2528IRTER'][0], 'MPN': 'TLA2528IRTER',
              'Note': 'ADDR=GND; AIN4 = FPGA_1V1 direct; footprint EP size to verify against SBAS961A mechanical drawing'})
    sh.cap('C34', '1uF', 'ADC_DECAP', GND)
    sh.cap('C35', '100nF', V33, GND)
    sh.res('R22', '4.7k', V33, 'ADC_SCL')
    sh.res('R23', '4.7k', V33, 'ADC_SDA')
    sh.res('R24', '10k 1%', HOST, 'MON_HOST_3V3'); sh.res('R25', '10k 1%', GND, 'MON_HOST_3V3')       # /2
    sh.res('R26', '20k 1%', VBUS, 'MON_VBUS'); sh.res('R27', '10k 1%', GND, 'MON_VBUS')               # /3
    sh.res('R28', '20k 1%', V5, 'MON_5V_SYS'); sh.res('R29', '10k 1%', GND, 'MON_5V_SYS')             # /3
    sh.res('R30', '20k 1%', CART5, 'MON_CART_5V'); sh.res('R31', '10k 1%', GND, 'MON_CART_5V')        # /3
    sh.place('RT1', 'Device:Thermistor_NTC', 'NTC 10k B3950 0603', {'1': V33, '2': 'MON_NTC'}, 'Resistor_SMD:R_0603_1608Metric',
             {'Note': 'board temperature for telemetry (replaces the v1 TMP302 switch); threshold in FPGA logic'})
    sh.res('R32', '10k 1%', GND, 'MON_NTC')
    sh.newline()
    # Sigma-delta audio ADC front end (2 ch): LVDS comparator, 1st-order RC integrator on the feedback pin.
    for ch, src, p, n, fb, r0 in (('L', 'SNES_AUDIO_L_IN', 'AUD_L_P', 'AUD_L_N', 'AUD_L_FB', 33), ('R', 'SNES_AUDIO_R_IN', 'AUD_R_P', 'AUD_R_N', 'AUD_R_FB', 36)):
        sh.cap(f'C{36 if ch == "L" else 38}', '1uF', src, f'AUD_{ch}_AC')            # AC coupling from the socket line
        sh.res(f'R{r0}', '10k', f'AUD_{ch}_AC', p)                                  # into the + input
        sh.res(f'R{r0 + 1}', '10k', 'AUD_BIAS', p)                                  # bias the + input at mid-rail
        sh.res(f'R{r0 + 2}', '10k', fb, n)                                          # feedback into the - input (integrator)
        sh.cap(f'C{37 if ch == "L" else 39}', '1nF C0G', n, GND)
    sh.res('R39', '10k', V33, 'AUD_BIAS'); sh.res('R40', '10k', GND, 'AUD_BIAS'); sh.cap('C40', '1uF', 'AUD_BIAS', GND)
    sh.newline()
    # Rails: flags for ERC
    for net in (GND, V33, V11, VBUS, HOST):        # rails without a power-output pin of their own
        sh.flag(net)


def build_cart_sheet(sh):
    sh.note('SN64 v2 CARTRIDGE SHEET - N64 edge J1 and SNES socket J2 on the one board, four SN74ALVC164245 translators (A = 3.3 V, B = 5 V), '
            'SN74LVC07A open-drain driver for the 5 V lines the FPGA pulls.', 1.8)
    sh.place('J2', 'SN64:SNES_Female_Slot_62', 'SNES cartridge socket 62', {str(k): v for k, v in SOCKET.items()},
             'SN64_V2:SNES_Slot_Console_Straddle', {'Note': 'console-replacement socket with ears (sample candidate NES Repair Shop snspt043); straddles the board top edge, pins 1-31 on B.Cu (front of the console); ears screw to the shell; pin geometry from OpenSFC CartSlot'})
    sh.newline()
    A = [f'L_A{i}' for i in range(24)]; SA = [f'SNES_A{i}' for i in range(24)]
    ctl_l = ['L_RD_N', 'L_WR_N', 'L_PRD_N', 'L_PWR_N', 'L_ROMSEL_N', 'L_WRAMSEL_N', 'L_REFRESH', 'L_PHI2']
    ctl_s = ['SNES_RD_N', 'SNES_WR_N', 'SNES_PRD_N', 'SNES_PWR_N', 'SNES_ROMSEL_N', 'SNES_WRAMSEL_N', 'SNES_REFRESH', 'SNES_PHI2']
    translator(sh, 'U201', A[0:8], SA[0:8], A[8:16], SA[8:16], V33, 'CTL_OE_N', V33, 'CTL_OE_N')
    translator(sh, 'U202', A[16:24], SA[16:24], ctl_l, ctl_s, V33, 'CTL_OE_N', V33, 'CTL_OE_N')
    translator(sh, 'U203', [f'L_PA{i}' for i in range(8)], [f'SNES_PA{i}' for i in range(8)],
               ['L_SYSTEM_CLK', 'L_CIC_CLK', 'L_CIC_SLAVE_RESET', GND, GND, GND, GND, GND],
               ['SNES_SYSTEM_CLK', 'SNES_CIC_CLK', 'SNES_CIC_SLAVE_RESET', None, None, None, None, None],
               V33, 'CTL_OE_N', V33, 'CIC_OE_N')
    translator(sh, 'U204', [f'L_D{i}' for i in range(8)], [f'SNES_D{i}' for i in range(8)],
               ['L_CIC_DATA0_IN', 'L_CIC_DATA1_IN', 'L_IRQ_N', 'L_RESET_N_SENSE', 'L_EXPAND', None, None, None],
               ['SNES_CIC_DATA0', 'SNES_CIC_DATA1', 'SNES_IRQ_N', 'SNES_RESET_N', 'SNES_EXPAND', GND, GND, GND],
               'DATA_DIR', 'DATA_OE_N', GND, GND)
    sh.newline()
    n = 201
    for _ in range(4):
        sh.cap(f'C{n}', '100nF', V33, GND); sh.cap(f'C{n + 1}', '100nF', CART5, GND); n += 2
    sh.cap('C209', '22uF 10V', CART5, GND, C0805); sh.cap('C210', '22uF 10V', CART5, GND, C0805)
    sh.newline()
    # Open-drain driver at 3.3 V, outputs pulled to 5 V (LVC07A outputs are 5.5 V tolerant)
    gates = [('PROGRAMN_PULL', 'FPGA_PROGRAMN'), ('CIC_DATA0_OD', 'SNES_CIC_DATA0'), ('CIC_DATA1_OD', 'SNES_CIC_DATA1'),
             ('RESET_PULL_OD', 'SNES_RESET_N'), (GND, None), (GND, None)]
    pinmap = [('1', '2'), ('3', '4'), ('5', '6'), ('9', '8'), ('11', '10'), ('13', '12')]
    fields = {'Datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc07a.pdf', 'LCSC': LCSC['SN74LVC07APWR'][0], 'MPN': 'SN74LVC07APWR'}
    for u, ((i, o), (ni, no)) in enumerate(zip(pinmap, gates), start=1):
        sh.place('U205', '74xx:74LS07', 'SN74LVC07APWR', {i: ni, o: no}, 'Package_SO:TSSOP-14_4.4x5mm_P0.65mm', fields, unit=u)
    sh.place('U205', '74xx:74LS07', 'SN74LVC07APWR', {'7': GND, '14': V33}, 'Package_SO:TSSOP-14_4.4x5mm_P0.65mm', fields, unit=7)
    sh.cap('C211', '100nF', V33, GND)
    for i, net in enumerate(['PROGRAMN_PULL', 'CIC_DATA0_OD', 'CIC_DATA1_OD', 'RESET_PULL_OD'], start=201):
        sh.res(f'R{i}', '10k', V33, net)            # released until the FPGA drives
    sh.newline()
    # Cartridge-side pulls (5 V) and translator defaults (disabled until the FPGA drives)
    sh.res('R205', '4.7k', CART5, 'SNES_CIC_DATA0'); sh.res('R206', '4.7k', CART5, 'SNES_CIC_DATA1')
    sh.res('R207', '4.7k', CART5, 'SNES_RESET_N'); sh.res('R208', '4.7k', CART5, 'SNES_IRQ_N'); sh.res('R209', '10k', CART5, 'SNES_EXPAND')
    sh.res('R210', '100k', V33, 'CTL_OE_N'); sh.res('R211', '100k', V33, 'CIC_OE_N'); sh.res('R212', '100k', V33, 'DATA_OE_N')
    sh.res('R213', '100k', GND, 'DATA_DIR')
    sh.newline()
    # N64 cartridge edge on this board (one board: the card stands in the console slot). 12 V, audio,
    # video-sync and key fingers are left open. SummerCart64 finger geometry (CERN-OHL-S-2.0).
    edge = {str(k): (None if v in ('HOST_12V', 'N64_AUDIO_L', 'N64_AUDIO_R', 'N64_KEY1_RESERVED', 'N64_KEY2_RESERVED',
                                   'N64_VIDEO_SYNC_RESERVED') else v) for k, v in N64_EDGE.items()}
    sh.place('J1', 'SN64:N64_Cartridge_Edge_50', 'N64 cartridge edge', edge, 'SN64:N64_Edge_SC64_Reference',
             {'Note': 'SummerCart64 edge geometry; 12 V, audio, sync and key fingers unused'})
    sh.cap('C212', '10uF 10V', HOST, GND, C0805)


def build_power_sheet(sh):
    sh.note('SN64 v2 POWER SHEET - TPS2121 input mux (USB priority) -> TPS63070 buck-boost 5V_SYS -> TLV62569 x2 (3V3, 1V1), '
            'AP2112K-2.5 LDO (2V5), TPS2553 cartridge switch, USB-C receptacle. Converter values are the v1 ones (verified pin tables).', 1.8)
    # USB-C receptacle (v1 J101 wiring), ESD, Rd
    sh.place('J101', 'SN64_USB:USB_C_Receptacle_USB2.0', 'DX07S016JA3R1500',
             {'A1': GND, 'A4': VBUS, 'A5': 'USB_CC1', 'A6': 'USB_DP', 'A7': 'USB_DN', 'A8': None, 'A9': VBUS, 'A12': GND,
              'B1': GND, 'B4': VBUS, 'B5': 'USB_CC2', 'B6': 'USB_DP', 'B7': 'USB_DN', 'B8': None, 'B9': VBUS, 'B12': GND, 'S1': GND},
             'SN64_USB:USB_C_JAE_DX07S016JA3R1500', {'LCSC': LCSC['DX07S016JA3R1500'][0], 'MPN': 'DX07S016JA3R1500', 'Note': 'side-mounted, mandatory rev 1 port'})
    sh.place('U4', 'Power_Protection:USBLC6-2SC6', 'USBLC6-2SC6', {'1': 'USB_DN', '2': GND, '3': 'USB_DP', '4': 'USB_DP', '5': VBUS, '6': 'USB_DN'},
             'Package_TO_SOT_SMD:SOT-23-6', {'LCSC': LCSC['USBLC6-2SC6'][0], 'MPN': 'USBLC6-2SC6'})
    sh.res('R301', '5.1k 1%', GND, 'USB_CC1'); sh.res('R302', '5.1k 1%', GND, 'USB_CC2')
    sh.cap('C301', '4.7uF 10V', VBUS, GND, C0805); sh.cap('C302', '1uF 10V', VBUS, GND)
    sh.newline()
    # Input mux: IN1 = USB (priority when VBUS > 4.0 V: PR1 divider 274k/100k, VREF 1.06 V), IN2 = host 3.3 V
    # (CP2 divider 182k/100k: IN2 usable above 3.0 V), OV1/OV2 grounded (unused), ILM 44.2k = 2.5 A, SS 1 nF, ST -> FPGA.
    sh.place('U7', 'SN64_V2:TPS2121RUX', 'TPS2121RUXR',
             {'7': VBUS, '2': HOST, '6': 'MUX_PR1', '3': 'MUX_CP2', '5': GND, '4': GND, '1': VIN, '8': VIN, '9': 'MUX_ST',
              '10': 'MUX_ILM', '11': 'MUX_SS', '12': GND},
             'Package_DFN_QFN:Texas_VQFN-HR-12_2x2.5mm_P0.5mm',
             {'Datasheet': 'https://www.ti.com/lit/ds/symlink/tps2121.pdf', 'LCSC': LCSC['TPS2121RUXR'][0], 'MPN': 'TPS2121RUXR',
              'Note': 'SLVSEA3F: RILM 18-100k (44.2k = 2.5 A typ), PR1/CP2/OV thresholds 1.06 V rising, ST pull-up 6-20k'})
    sh.res('R303', '274k 1%', VBUS, 'MUX_PR1'); sh.res('R304', '100k 1%', GND, 'MUX_PR1')
    sh.res('R305', '182k 1%', HOST, 'MUX_CP2'); sh.res('R306', '100k 1%', GND, 'MUX_CP2')
    sh.res('R307', '44.2k 1%', GND, 'MUX_ILM'); sh.cap('C303', '1nF', 'MUX_SS', GND); sh.res('R308', '10k', V33, 'MUX_ST')
    sh.cap('C304', '10uF 10V', VBUS, GND, C0805); sh.cap('C305', '10uF 10V', HOST, GND, C0805); sh.cap('C306', '10uF 10V', VIN, GND, C0805)
    sh.newline()
    # Buck-boost 5V_SYS (v1 U304 wiring and values: FB 232k/44.2k, L 1.5 uH, PS/SYNC low = PFM, VSEL low)
    sh.place('U8', 'SN64_POWER:TPS63070RNM', 'TPS63070RNMR',
             {'1': GND, '2': 'PG_5V', '3': 'VAUX_5V', '4': GND, '5': 'FB_5V', '6': None, '7': V5, '8': V5, '9': 'L2_5V', '10': GND,
              '11': 'L1_5V', '12': VIN, '13': VIN, '14': VIN, '15': GND},
             'SN64:Texas_RNM0015A_VQFN-HR-15_2.5x3mm',
             {'Datasheet': 'https://www.ti.com/lit/ds/symlink/tps63070.pdf', 'LCSC': LCSC['TPS63070RNMR'][0], 'MPN': 'TPS63070RNMR'})
    sh.place('L1', 'Device:L', '1.5uH PNR4020-1R5M', {'1': 'L1_5V', '2': 'L2_5V'}, 'SN64:L_APV_PNR4020', {'LCSC': LCSC['PNR4020-1R5M'][0], 'MPN': 'PNR4020-1R5M'})
    sh.res('R309', '232k 0.1%', V5, 'FB_5V'); sh.res('R310', '44.2k 0.1%', GND, 'FB_5V'); sh.res('R311', '100k', V5, 'PG_5V')
    sh.cap('C307', '100nF', 'VAUX_5V', GND)
    sh.cap('C308', '10uF 25V', VIN, GND, C0805); sh.cap('C309', '22uF 25V', VIN, GND, C0805)
    for i in range(310, 314):
        sh.cap(f'C{i}', '22uF 10V', V5, GND, C0805)
    sh.newline()
    # Bucks: 3V3 and 1V1 (v1 U307/U305 values), EN from the 5 V power-good
    for ref, lref, rail, rt, rb, ct in (('U9', 'L2', V33, '459k 0.1%', '102k 0.1%', 'C314'), ('U10', 'L3', V11, '100k 0.1%', '120k 0.1%', 'C315')):
        sw, fb = f'SW_{rail[-3:]}', f'FB_{rail[-3:]}'
        sh.place(ref, 'Regulator_Switching:TLV62569DBV', 'TLV62569DBVR', {'1': 'PG_5V', '2': GND, '3': sw, '4': V5, '5': fb},
                 'Package_TO_SOT_SMD:SOT-23-5', {'Datasheet': 'https://www.ti.com/lit/ds/symlink/tlv62569.pdf', 'LCSC': LCSC['TLV62569DBVR'][0], 'MPN': 'TLV62569DBVR'})
        sh.place(lref, 'Device:L', '2.2uH FNR4030S2R2MT', {'1': sw, '2': rail}, 'Inductor_SMD:L_Changjiang_FNR4030S', {'LCSC': LCSC['FNR4030S2R2MT'][0], 'MPN': 'FNR4030S2R2MT'})
        n = 312 if ref == 'U9' else 315
        sh.res(f'R{n}', rt, rail, fb); sh.res(f'R{n + 1}', rb, GND, fb); sh.cap(ct, '6.8pF C0G', rail, fb)
        sh.cap(f'C{316 if ref == "U9" else 318}', '22uF 10V', rail, GND, C0805); sh.cap(f'C{317 if ref == "U9" else 319}', '22uF 10V', rail, GND, C0805)
    sh.newline()
    # 2.5 V auxiliary from 3.3 V: LDO (v1 used a third buck; ~20 mW traded for an inductor and three parts)
    sh.place('U11', 'Regulator_Linear:AP2112K-2.5', 'AP2112K-2.5TRG1', {'1': V33, '2': GND, '3': V33, '4': None, '5': V25},
             'Package_TO_SOT_SMD:SOT-23-5', {'Datasheet': 'https://www.diodes.com/assets/Datasheets/AP2112.pdf', 'LCSC': LCSC['AP2112K-2.5TRG1'][0], 'MPN': 'AP2112K-2.5TRG1'})
    sh.cap('C320', '1uF 10V', V33, GND); sh.cap('C321', '4.7uF 10V', V25, GND, C0805)
    sh.newline()
    # Cartridge 5 V switch with current limit and fault flag (replaces the v1 TPS259470L eFuse)
    sh.place('U12', 'SN64_V2:TPS2553DBV', 'TPS2553DBVR', {'1': V5, '3': 'CART_5V_EN', '5': 'CART_ILIM', '6': CART5, '4': 'EFUSE_FAULT_N', '2': GND},
             'Package_TO_SOT_SMD:SOT-23-6', {'Datasheet': 'https://www.ti.com/lit/ds/symlink/tps2553.pdf', 'LCSC': LCSC['TPS2553DBVR'][0], 'MPN': 'TPS2553DBVR',
                                             'Note': 'RILIM 24.9k: 1.04 A nominal, 0.96 to 1.12 A (SLVS841F equations, checked 2026-10-01)'})
    sh.res('R318', '24.9k 1%', GND, 'CART_ILIM'); sh.res('R319', '100k', GND, 'CART_5V_EN'); sh.res('R320', '10k', V33, 'EFUSE_FAULT_N')
    sh.cap('C322', '100nF', V5, GND); sh.cap('C323', '10uF 10V', CART5, GND, C0805)


def write_tables(proj, own_libs, extra_fp):
    sym = ['(sym_lib_table (version 7)']
    for name in own_libs:
        sym.append(f'  (lib (name "{name}")(type "KiCad")(uri "${{KIPRJMOD}}/libraries/{name}.kicad_sym")(options "")(descr ""))')
    sym.append(')')
    save(proj / 'sym-lib-table', '\n'.join(sym))
    fp = ['(fp_lib_table (version 7)']
    for name in extra_fp:
        fp.append(f'  (lib (name "{name}")(type "KiCad")(uri "${{KIPRJMOD}}/libraries/{name}.pretty")(options "")(descr ""))')
    fp.append(')')
    save(proj / 'fp-lib-table', '\n'.join(fp))


def write_project(path, name):
    pro = {"board": {"design_settings": {"defaults": {}, "rules": {"max_error": 0.005, "min_clearance": 0.1, "min_connection": 0.0, "min_copper_edge_clearance": 0.3, "min_groove_width": 0.0, "min_hole_clearance": 0.2, "min_hole_to_hole": 0.25, "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1, "min_resolved_spokes": 2, "min_silk_clearance": 0.0, "min_text_height": 0.8, "min_text_thickness": 0.08, "min_through_hole_diameter": 0.2, "min_track_width": 0.1, "min_via_annular_width": 0.125, "min_via_diameter": 0.45, "solder_mask_to_copper_clearance": 0.0, "use_height_for_length_calcs": True}, "drc_exclusions": [], "meta": {"version": 2}, "rule_severities": {"solder_mask_bridge": "warning"}}, "layer_presets": [], "viewports": []},
           "boards": [], "cvpcb": {"equivalence_files": []}, "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
           "meta": {"filename": f"{name}.kicad_pro", "version": 3},
           "net_settings": {"classes": [{"bus_width": 12, "clearance": 0.1, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2,
                                         "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1, "name": "Default", "pcb_color": "rgba(0, 0, 0, 0.000)",
                                         "priority": 2147483647, "schematic_color": "rgba(0, 0, 0, 0.000)", "track_width": 0.15, "via_diameter": 0.45, "via_drill": 0.2, "wire_width": 6},
                                        {"bus_width": 12, "clearance": 0.1, "line_style": 0, "name": "power", "priority": 0, "track_width": 0.4, "via_diameter": 0.6, "via_drill": 0.3, "wire_width": 6}],
                            "meta": {"version": 4},
                            "netclass_patterns": [{"netclass": "power", "pattern": "GND"}, {"netclass": "power", "pattern": "FPGA_3V3"}, {"netclass": "power", "pattern": "FPGA_1V1"},
                                                  {"netclass": "power", "pattern": "FPGA_2V5"}, {"netclass": "power", "pattern": "5V_SYS"}, {"netclass": "power", "pattern": "SYS_VIN"},
                                                  {"netclass": "power", "pattern": "USB_VBUS"}, {"netclass": "power", "pattern": "HOST_3V3"}, {"netclass": "power", "pattern": "SNES_5V_CART"}]},
           "pcbnew": {"last_paths": {}, "page_layout_descr_file": ""},
           "schematic": {"drawing": {}, "legacy_lib_dir": "", "legacy_lib_list": [], "meta": {"version": 1}},
           "sheets": [], "text_variables": {}}
    save(path / f'{name}.kicad_pro', json.dumps(pro, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    if (V2 / 'sn64-v2.kicad_sch').exists() and not a.force:
        ap.error('sn64-v2.kicad_sch exists; --force regenerates every sheet (native edits are lost)')
    balls, rows = pin_plan.plan()
    pin_plan.write_outputs(rows)
    # Libraries: reuse v1 symbol/footprint libraries unchanged, plus the v2 drawn symbols.
    (V2 / 'libraries').mkdir(parents=True, exist_ok=True)
    for name in ('SN64', 'SN64_POWER', 'SN64_USB'):
        shutil.copy(V1 / 'libraries' / f'{name}.kicad_sym', V2 / 'libraries' / f'{name}.kicad_sym')
    for name in ('SN64', 'SN64_USB'):
        dst = V2 / 'libraries' / f'{name}.pretty'
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(V1 / 'libraries' / f'{name}.pretty', dst)
    v2lib = parse_text('(kicad_symbol_lib (version 20241209) (generator "sn64_v2_authoring") (generator_version "10.0"))')
    for name, value, pins, descr, ds, fp in (
            ('TPS2121RUX', 'TPS2121RUXR', TPS2121_PINS, '2.8-22 V priority power mux, 4.5 A, current limit, VQFN-HR-12',
             'https://www.ti.com/lit/ds/symlink/tps2121.pdf', 'Package_DFN_QFN:Texas_VQFN-HR-12_2x2.5mm_P0.5mm'),
            ('TLA2528RTE', 'TLA2528IRTER', TLA2528_PINS, '8-channel 12-bit I2C ADC, WQFN-16',
             'https://www.ti.com/lit/ds/symlink/tla2528.pdf', 'Package_DFN_QFN:Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm'),
            ('TPS2553DBV', 'TPS2553DBVR', TPS2553_PINS, 'Power-distribution switch 1.5 A, adjustable current limit, fault flag, SOT-23-6',
             'https://www.ti.com/lit/ds/symlink/tps2553.pdf', 'Package_TO_SOT_SMD:SOT-23-6')):
        v2lib.append(own_symbol('SN64_V2', name, value, pins, descr, ds, fp))
    save(V2 / 'libraries' / 'SN64_V2.kicad_sym', dump(v2lib))
    own = {n: parse(V2 / 'libraries' / f'{n}.kicad_sym') for n in ('SN64', 'SN64_POWER', 'SN64_USB', 'SN64_V2')}

    root_uuid = uid('root:' + PROJECT)
    fpga = Sheet('FPGA', 'fpga.kicad_sch', '2', 'A0', root_uuid, own)
    cart = Sheet('Cartridge', 'cart.kicad_sch', '3', 'A1', root_uuid, own)
    power = Sheet('Power and USB', 'power.kicad_sch', '4', 'A1', root_uuid, own)
    build_fpga_sheet(fpga, balls, rows)
    build_cart_sheet(cart)
    build_power_sheet(power)
    for sh in (fpga, cart, power):
        save(V2 / sh.file, sh.render(f'SN64 v2 - {sh.name}'))
    save(V2 / f'{PROJECT}.kicad_sch', root_sheet(root_uuid, [fpga, cart, power], 'SN64 v2: one board in the N64 slot with the SNES socket on its face; FPGA, translators, power, USB'))
    write_tables(V2, ['SN64', 'SN64_POWER', 'SN64_USB', 'SN64_V2'], ['SN64', 'SN64_USB', 'SN64_V2'])
    write_project(V2, PROJECT)

    prov = {'schema_version': 1, 'recorded_date': '2026-09-30', 'scope': 'SN64 v2 schematic draft 0.1 (branch v2); not a manufacturing release',
            'drawn_symbols': {'TPS2121RUX': {'pins': {n: [lab, typ] for n, lab, typ, _ in TPS2121_PINS}, 'source': 'TI SLVSEA3F (Aug 2020) pin table via LCSC C485916 pinout; design values from SLVSEA3F sections 7.5/9.3'},
                              'TLA2528RTE': {'pins': {n: [lab, typ] for n, lab, typ, _ in TLA2528_PINS}, 'source': 'TI SBAS961A pin table (LCSC C2866175 pinout, checked against the datasheet 2026-10-01)'},
                              'TPS2553DBV': {'pins': {n: [lab, typ] for n, lab, typ, _ in TPS2553_PINS}, 'source': 'TI SLVS841F pin table (LCSC C55266 pinout, checked against the datasheet 2026-10-01)'}},
            'reused_v1_libraries': ['SN64 (socket, N64 edge: Sanni CC-BY-4.0, SummerCart64 CERN-OHL-S-2.0)', 'SN64_POWER (TPS63070RNM, TI SLVSC58B)', 'SN64_USB (JAE DX07S016JA3R1500)'],
            'installed_kicad_symbols': ['FPGA_Lattice:LFE5U-85F-8BG381x', '74xx:74ALVC164245', '74xx:74LS07 (as SN74LVC07APW)', 'Memory_Flash:W25Q128JVS', 'Power_Supervisor:TPS3808DBV',
                                        'Regulator_Switching:TLV62569DBV', 'Regulator_Linear:AP2112K-2.5', 'Power_Protection:USBLC6-2SC6', 'Oscillator:ASE-xxxMHz'],
            'lcsc_stock_2026_09_30': LCSC, 'provisional_values': ['TPS2553 RILIM 24.9k', 'TPS2121 CSS 1 nF', 'decoupling counts (Lattice checklist, not per ball)',
                                                                   'sigma-delta ADC RC (10k/1nF)', 'NTC part'],
            'bom': {'main': fpga.bom + cart.bom + power.bom}}
    save(V2 / 'libraries' / 'v2-provenance.json', json.dumps(prov, indent=1))
    n_main = len(fpga.bom) + len(cart.bom) + len(power.bom)
    print(f'wrote {PROJECT}: {n_main} parts (fpga {len(fpga.bom)}, cart {len(cart.bom)}, power {len(power.bom)})')


if __name__ == '__main__':
    main()
