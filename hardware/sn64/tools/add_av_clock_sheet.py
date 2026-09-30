"""Author the clock, HDMI and cartridge-audio child sheet (av-clock.kicad_sch).

One-time draft authoring utility in the style of add_cart_interface.py. It
writes av-clock.kicad_sch, the project-local SN64_AV symbol library (the two
parts KiCad does not ship: TI TPD12S016 and TI PCM1808) and av-provenance.json.

It does NOT touch the real root sheet or sym-lib-table. Attaching the sheet to
a root is an integration step: pass --attach-root <root.kicad_sch> (used on a
validation COPY of hardware/sn64; the integration pass may use it on the real
root). With --attach-root the script appends ONE sheet symbol (rails, SNES
audio and GND pins labelled with the same-name root labels; FPGA-side pins
closed with no-connect markers until the FPGA sheet exists) and adds the
SN64_AV entry to the sym-lib-table next to that root.

It refuses to replace an existing child sheet unless --force is given; after
native KiCad editing starts, edit the KiCad files instead of regenerating.

  python add_av_clock_sheet.py --kicad-share "C:/Program Files/KiCad/10.0/share/kicad"
       [--datasheets <dir with the downloaded PDFs>] [--force] [--attach-root <copy>/sn64.kicad_sch]

Pure Python 3 (no pcbnew needed). Standard symbols are copied from the
installed KiCad library; the two drawn symbols use the TI pin tables in PIN
TABLES below. Every value on the sheet carries its source in the notes and in
libraries/av-provenance.json; values marked "provisional" are engineering
choices awaiting bring-up measurement.
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
NS = uuid.UUID('7c1e3a90-5b2d-4f61-9e0a-2d4b6a8c1f37')   # verify_av_clock_sheet.py uses it to find labels for mutations
SHEET_FILE = 'av-clock.kicad_sch'
SHEET_NAME = 'AV clock and cartridge audio'
LIB = 'SN64_AV'
PAGE = '7'


def uid(s):
    return str(uuid.uuid5(NS, s))


def q(s):
    return json.dumps(str(s), ensure_ascii=False)


class Quoted(str):
    pass


def parse_text(text):
    stack, result = [], []
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
# PIN TABLES (drawn symbols). Checked independently by
# tools/verify_av_clock_sheet.py against its own copy of these tables.
#   TI TPD12S016, SLLSE96F (Oct 2015), Section 5, PW package pin functions
#   TI PCM1808,   SLES177B (Aug 2015),  Section 5, PW package pin functions
# (number, name, electrical type, x, y, angle)
# ---------------------------------------------------------------------------
TPD12S016_PINS = [
    ('1', 'CEC_A', 'bidirectional', -17.78, 12.7, 0), ('2', 'SCL_A', 'bidirectional', -17.78, 10.16, 0),
    ('3', 'SDA_A', 'bidirectional', -17.78, 7.62, 0), ('4', 'HPD_A', 'output', -17.78, 5.08, 0),
    ('5', 'LS_OE', 'input', -17.78, 0, 0), ('12', 'CT_HPD', 'input', -17.78, -2.54, 0),
    ('7', 'CEC_B', 'bidirectional', 17.78, 12.7, 180), ('8', 'SCL_B', 'bidirectional', 17.78, 10.16, 180),
    ('9', 'SDA_B', 'bidirectional', 17.78, 7.62, 180), ('10', 'HPD_B', 'input', 17.78, 5.08, 180),
    ('13', '5V_OUT', 'power_out', 17.78, 0, 180),
    ('23', 'D2+', 'passive', 17.78, -2.54, 180), ('22', 'D2-', 'passive', 17.78, -5.08, 180),
    ('21', 'D1+', 'passive', 17.78, -7.62, 180), ('20', 'D1-', 'passive', 17.78, -10.16, 180),
    ('18', 'D0+', 'passive', 17.78, -12.7, 180), ('17', 'D0-', 'passive', 17.78, -15.24, 180),
    ('16', 'CLK+', 'passive', 17.78, -17.78, 180), ('15', 'CLK-', 'passive', 17.78, -20.32, 180),
    ('24', 'VCCA', 'power_in', -2.54, 20.32, 270), ('11', 'VCC5V', 'power_in', 2.54, 20.32, 270),
    ('6', 'GND', 'power_in', -2.54, -27.94, 90), ('14', 'GND', 'power_in', 0, -27.94, 90),
    ('19', 'GND', 'power_in', 2.54, -27.94, 90)]
PCM1808_PINS = [
    ('13', 'VINL', 'input', -17.78, 7.62, 0), ('14', 'VINR', 'input', -17.78, 5.08, 0),
    ('1', 'VREF', 'passive', -17.78, 0, 0), ('6', 'SCKI', 'input', -17.78, -5.08, 0),
    ('8', 'BCK', 'bidirectional', 17.78, 7.62, 180), ('7', 'LRCK', 'bidirectional', 17.78, 5.08, 180),
    ('9', 'DOUT', 'output', 17.78, 2.54, 180), ('10', 'MD0', 'input', 17.78, -2.54, 180),
    ('11', 'MD1', 'input', 17.78, -5.08, 180), ('12', 'FMT', 'input', 17.78, -7.62, 180),
    ('3', 'VCC', 'power_in', -2.54, 15.24, 270), ('4', 'VDD', 'power_in', 2.54, 15.24, 270),
    ('2', 'AGND', 'power_in', -2.54, -15.24, 90), ('5', 'DGND', 'power_in', 2.54, -15.24, 90)]


def own_symbol(name, value, pins, descr, datasheet, footprint, top, bottom):
    lines = [f'(symbol {q(LIB + ":" + name)} (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)',
             prop('Reference', 'U', 0, top + 3.81), prop('Value', value, 0, bottom - 3.81),
             prop('Footprint', footprint, 0, bottom - 6.35, True), prop('Datasheet', datasheet, 0, bottom - 8.89, True),
             prop('Description', descr, 0, bottom - 11.43, True),
             f'(symbol {q(name + "_0_1")} (rectangle (start -12.7 {g(top)}) (end 12.7 {g(bottom)}) '
             f'(stroke (width 0.254) (type default)) (fill (type background))))',
             f'(symbol {q(name + "_1_1")}']
    for number, label, typ, x, y, angle in pins:
        lines.append(f'(pin {typ} line (at {g(x)} {g(y)} {angle}) (length 5.08) (name {q(label)} '
                     f'(effects (font (size 1.27 1.27)))) (number {q(number)} (effects (font (size 1.016 1.016)))))')
    return parse_text('\n'.join(lines) + ') (embedded_fonts no))')


# ---------------------------------------------------------------------------
# Shared net-name contract (hierarchical ports). Shapes are from this sheet's view.
# ---------------------------------------------------------------------------
RAIL3, RAIL5, GND = 'FPGA_3V3', '5V_PRE', 'GND'
ROOT_PORTS = [(GND, 'passive'), ('SNES_AUDIO_L_IN', 'passive'), ('SNES_AUDIO_R_IN', 'passive')]
PENDING_PORTS = ([(RAIL3, 'input'), (RAIL5, 'input'),
                  ('osc_25', 'output'), ('si_clk0', 'output'), ('si_clk1', 'output'), ('si_clk2', 'output'),
                  ('si_scl', 'input'), ('si_sda', 'bidirectional')]
                 + [(f'hdmi_{lane}_{pol}', 'input') for lane in ('d0', 'd1', 'd2', 'ck') for pol in ('p', 'n')]
                 + [('hdmi_hpd', 'output'), ('hdmi_scl', 'input'), ('hdmi_sda', 'bidirectional'),
                    ('adc_bck', 'output'), ('adc_lrck', 'output'), ('adc_dout', 'output')])

# LCSC parts (JLC stock snapshot 2026-09-29, pcbparts jlc_get_part)
LCSC = {'Si5351A-B-GTR': 'C504891', 'X322525MMB4SI': 'C70582', 'CJO05-250003320B30': 'C712741',
        'CJO05-122883320B30': 'C712747', 'TPD12S016PWR': 'C201665', 'PCM1808PWR': 'C55513',
        '10029449-111RLF': 'C427307', 'GZ1608D601TF': 'C1002'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--kicad-share', type=Path, required=True)
    ap.add_argument('--datasheets', type=Path, help='directory holding the downloaded PDFs (hashes recorded)')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--attach-root', type=Path, help='root schematic to receive the sheet symbol (validation copy)')
    ap.add_argument('--project-root', type=Path, default=ROOT,
                    help='directory that receives the child sheet and library (default: hardware/sn64)')
    a = ap.parse_args()
    proj = a.project_root.resolve()
    dest = proj / SHEET_FILE
    if dest.exists() and not a.force:
        ap.error('Child sheet exists; use KiCad to edit, or --force to replace the initial draft')

    real_root = parse(ROOT / 'sn64.kicad_sch')
    root_uuid = str(get(real_root, 'uuid')[1])
    sheet_uuid = uid('sheet')
    page_uuid = uid('page')
    libs, parts, fps = {}, [], set()
    anchors = {}     # (x, y) -> (kind, name): catches accidental label/pin coincidences

    def claim(x, y, kind, name):
        key = (round(x, 3), round(y, 3))
        prev = anchors.get(key)
        assert prev is None or prev == (kind, name) or (prev[0] == 'label' and kind == 'label' and prev[1] == name), \
            f'anchor collision at {key}: {prev} vs {(kind, name)}'
        anchors[key] = (kind, name)

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

    TI = {'tpd12s016': 'https://www.ti.com/lit/ds/symlink/tpd12s016.pdf',
          'pcm1808': 'https://www.ti.com/lit/ds/symlink/pcm1808.pdf'}
    libs[LIB + ':TPD12S016PW'] = own_symbol(
        'TPD12S016PW', 'TPD12S016PWR', TPD12S016_PINS,
        'HDMI companion: 12-channel ESD, DDC/CEC level shifting, HPD buffer, 55 mA current-limited 5 V load switch',
        TI['tpd12s016'], 'Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm', 15.24, -22.86)
    libs[LIB + ':PCM1808PW'] = own_symbol(
        'PCM1808PW', 'PCM1808PWR', PCM1808_PINS,
        'Stereo 24-bit audio ADC, single-ended 0.6 VCC Vp-p input, I2S/LJ, master or slave',
        TI['pcm1808'], 'Package_SO:TSSOP-14_4.4x5mm_P0.65mm', 10.16, -10.16)

    def place(ref, lib_id, value, x, y, nets, fp='', fields=None):
        sym = load(lib_id)
        pins = [p for u in items(sym, 'symbol') for p in items(u, 'pin')]
        assert {str(get(p, 'number')[1]) for p in pins} == set(nets), (ref, sorted(nets))
        small = lib_id in ('Device:R', 'Device:C', 'Device:FerriteBead', 'Connector:TestPoint', 'power:PWR_FLAG')
        if small:
            rx, ry, vx, vy, just = x + 2.54, y - 1.27, x + 2.54, y + 1.27, 'left'
        else:
            tops = [y - float(get(p, 'at')[2]) for p in pins]
            rx, ry, vx, vy, just = x - 12.7, min(tops) - 10.16, x - 12.7, min(tops) - 7.62, 'left'
        hidden = ref.startswith('#')
        out = [f'(symbol (lib_id {q(lib_id)}) (at {g(x)} {g(y)} 0) (unit 1) (exclude_from_sim no) (in_bom {"no" if hidden else "yes"}) '
               f'(on_board {"no" if hidden else "yes"}) (dnp no) (uuid {q(uid(ref))})',
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
                continue            # stacked pins (e.g. crystal G pins 2/4) share one wire and label
            seen.add((px, py, net))
            claim(px, py, 'pin', role)
            if net is None:
                parts.append(f'(no_connect (at {g(px)} {g(py)}) (uuid {q(uid("nc:" + role))}))')
                continue
            dx = -5.08 * round(math.cos(math.radians(angle)))
            dy = 5.08 * round(math.sin(math.radians(angle)))
            ex, ey = px + dx, py + dy
            claim(ex, ey, 'label', net + '@' + role)
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

    R0603, C0603, C0805 = 'Resistor_SMD:R_0603_1608Metric', 'Capacitor_SMD:C_0603_1608Metric', 'Capacitor_SMD:C_0805_2012Metric'

    def res(ref, value, n1, n2, x, y, fields=None):
        place(ref, 'Device:R', value, x, y, {'1': n1, '2': n2}, R0603, fields)

    def cap(ref, value, n1, n2, x, y, fp=C0603, fields=None):
        place(ref, 'Device:C', value, x, y, {'1': n1, '2': n2}, fp, fields)

    # ======================= CLOCKS =========================================
    # Si5351A-B-GT, Skyworks Si5351-B Rev 1.3: Table 20 (10-MSOP pins), Table 8
    # (crystal 25/27 MHz, CL 6-12 pF, ESR <= 150 ohm, drive level >= 100 uW),
    # 7.1 (0.1-1.0 uF per supply pin), 7.2 (VDDO with/before VDD: same rail),
    # 7.4 (internal CL; no external load caps), 7.6 (50 ohm driver, 0 ohm optional
    # series resistor), Figure 5 (SCL/SDA pull-ups to VDD, >1k, 4.7k shown).
    place('U701', 'Oscillator:Si5351A-B-GT', 'Si5351A-B-GTR', 80.01, 91.44,
          {'1': RAIL3, '2': 'SI_XA', '3': 'SI_XB', '4': 'si_scl', '5': 'si_sda', '6': 'SI_CLK2_SRC',
           '7': RAIL3, '8': GND, '9': 'SI_CLK1_SRC', '10': 'SI_CLK0_SRC'},
          'Package_SO:MSOP-10_3x3mm_P0.5mm',
          fields={'Datasheet': 'https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/data-sheets/Si5351-B.pdf',
                  'LCSC': LCSC['Si5351A-B-GTR'], 'MPN': 'Si5351A-B-GTR'})
    # 25 MHz, CL 10 pF crystal (YXC YSX321SL family): pins 1/3 crystal, 2/4 GND.
    # CL 10 pF == register 183 XTAL_CL = 11b (0xD2) written by fpga/rtl/sn64_clock_init.sv.
    place('Y701', 'Device:Crystal_GND24', '25MHz 10pF', 30.48, 83.82,
          {'1': 'SI_XA', '2': GND, '3': 'SI_XB', '4': GND}, 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm',
          fields={'LCSC': LCSC['X322525MMB4SI'], 'MPN': 'X322525MMB4SI', 'Frequency': '25MHz', 'Load_Capacitance': '10pF',
                  'ESR_max': '50 ohm (YSX321SL table, 16-31 MHz)', 'Drive_level_max': '200 uW',
                  'Datasheet': 'https://www.lcsc.com/datasheet/lcsc_datasheet_2403291504_YXC-Crystal-Oscillators-X322525MMB4SI_C70582.pdf'})
    res('R701', '4.7k', RAIL3, 'si_scl', 30.48, 127.0)
    res('R702', '4.7k', RAIL3, 'si_sda', 45.72, 127.0)
    res('R703', '0R', 'SI_CLK0_SRC', 'si_clk0', 60.96, 127.0)
    res('R704', '0R', 'SI_CLK1_SRC', 'si_clk1', 76.2, 127.0)
    res('R705', '0R', 'SI_CLK2_SRC', 'si_clk2', 91.44, 127.0)
    cap('C701', '100nF', RAIL3, GND, 106.68, 127.0)
    cap('C702', '100nF', RAIL3, GND, 121.92, 127.0)
    # 25 MHz FPGA housekeeping oscillator, JSCJ CJO05-250003320B30 spec rev1.0:
    # pin 1 enable (high or open = run), 2 GND, 3 output, 4 VDD 3.3 V.
    OSC_DS = 'https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2104221204_Jiangsu-Changjing-Electronics-Technology-Co---Ltd--CJO05-250003320B30_C712741.pdf'
    place('X701', 'Oscillator:ASE-xxxMHz', '25MHz CJO05-250003320B30', 165.1, 91.44,
          {'1': RAIL3, '2': GND, '3': 'OSC25_SRC', '4': RAIL3}, 'Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm',
          fields={'LCSC': LCSC['CJO05-250003320B30'], 'MPN': 'CJO05-250003320B30', 'Frequency': '25MHz', 'Datasheet': OSC_DS})
    res('R706', '0R', 'OSC25_SRC', 'osc_25', 152.4, 127.0)
    cap('C703', '100nF', RAIL3, GND, 167.64, 127.0)

    # ======================= HDMI ===========================================
    # TMDS: ULX3S gpdi.sch @6a92cec: each FPGA LVCMOS33D pseudo-differential
    # output reaches the connector through a 22 nF series capacitor (C38-C45),
    # nothing else. TPD12S016 ESD pins sit on the connector side (datasheet:
    # connect to controller and connector directly).
    tmds = [('d2', 'D2', '1', '3', '23', '22'), ('d1', 'D1', '4', '6', '21', '20'),
            ('d0', 'D0', '7', '9', '18', '17'), ('ck', 'CK', '10', '12', '16', '15')]
    k = 0
    for lane, up, jp, jn, tp, tn in tmds:
        for pol, jpin in (('p', jp), ('n', jn)):
            cap(f'C{704 + k}', '22nF', f'hdmi_{lane}_{pol}', f'HDMI_J_{up}_{pol.upper()}', 30.48 + 15.24 * k, 218.44,
                fields={'Reference_design': f'ULX3S gpdi.sch C{38 + k} (22nF series TMDS coupling)'})
            k += 1
    place('U702', LIB + ':TPD12S016PW', 'TPD12S016PWR', 91.44, 284.48,
          {'1': 'HDMI_CEC_A', '2': 'hdmi_scl', '3': 'hdmi_sda', '4': 'hdmi_hpd', '5': RAIL3, '12': RAIL3,
           '7': 'HDMI_CEC_B', '8': 'HDMI_SCL_B', '9': 'HDMI_SDA_B', '10': 'HDMI_HPD_B', '13': 'HDMI_5V',
           '23': 'HDMI_J_D2_P', '22': 'HDMI_J_D2_N', '21': 'HDMI_J_D1_P', '20': 'HDMI_J_D1_N',
           '18': 'HDMI_J_D0_P', '17': 'HDMI_J_D0_N', '16': 'HDMI_J_CK_P', '15': 'HDMI_J_CK_N',
           '24': RAIL3, '11': RAIL5, '6': GND, '14': GND, '19': GND},
          'Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm',
          fields={'Datasheet': TI['tpd12s016'], 'LCSC': LCSC['TPD12S016PWR'], 'MPN': 'TPD12S016PWR'})
    place('J701', 'Connector:HDMI_A', 'HDMI_A 10029449-111RLF', 187.96, 284.48,
          {'1': 'HDMI_J_D2_P', '2': GND, '3': 'HDMI_J_D2_N', '4': 'HDMI_J_D1_P', '5': GND, '6': 'HDMI_J_D1_N',
           '7': 'HDMI_J_D0_P', '8': GND, '9': 'HDMI_J_D0_N', '10': 'HDMI_J_CK_P', '11': GND, '12': 'HDMI_J_CK_N',
           '13': 'HDMI_CEC_B', '14': None, '15': 'HDMI_SCL_B', '16': 'HDMI_SDA_B', '17': GND, '18': 'HDMI_5V',
           '19': 'HDMI_HPD_B', 'SH': GND},
          'Connector_Video:HDMI_A_Amphenol_10029449-x01xLF_Horizontal',
          fields={'LCSC': LCSC['10029449-111RLF'], 'MPN': '10029449-111RLF',
                  'Datasheet': 'https://www.lcsc.com/datasheet/lcsc_datasheet_2304140030_Amphenol-ICC-10029449-111RLF_C427307.pdf',
                  'Footprint_status': 'PROVISIONAL: drawing 10029449 rev Y lists -001/-101/-002 variants, not -111RLF'})
    cap('C712', '100nF', RAIL3, GND, 30.48, 345.44)
    cap('C713', '100nF', RAIL5, GND, 45.72, 345.44)
    cap('C714', '100nF', 'HDMI_5V', GND, 60.96, 345.44)
    place('TP701', 'Connector:TestPoint', 'CEC_A', 76.2, 345.44, {'1': 'HDMI_CEC_A'}, 'TestPoint:TestPoint_Pad_D1.0mm')

    # ======================= CARTRIDGE AUDIO ADC ============================
    # PCM1808 SLES177B: Table 2 (MD1 H, MD0 L = master 384 fs), Table 3 (FMT L =
    # I2S 24-bit), 8.2.2.1 (straps: 10k to VDD or GND), Figure 26 notes (1 uF
    # input coupling -> 2.7 Hz with the 60 k input; VREF 0.1 uF + 10 uF;
    # supplies 0.1 uF + 10 uF), 6.5 (input 0.6 VCC Vp-p, 60 k, VREF 0.5 VCC).
    place('U703', LIB + ':PCM1808PW', 'PCM1808PWR', 452.12, 91.44,
          {'13': 'ADC_VINL', '14': 'ADC_VINR', '1': 'ADC_VREF', '6': 'ADC_SCKI',
           '8': 'adc_bck', '7': 'adc_lrck', '9': 'adc_dout', '10': 'ADC_MD0', '11': 'ADC_MD1', '12': 'ADC_FMT',
           '3': 'ADC_VCC_5V', '4': RAIL3, '2': GND, '5': GND},
          'Package_SO:TSSOP-14_4.4x5mm_P0.65mm',
          fields={'Datasheet': TI['pcm1808'], 'LCSC': LCSC['PCM1808PWR'], 'MPN': 'PCM1808PWR'})
    OSC12_DS = 'https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2009031207_Jiangsu-Changjing-Electronics-Technology-Co---Ltd--CJ005-122883320B30_C712747.pdf'
    place('X702', 'Oscillator:ASE-xxxMHz', '12.288MHz CJO05-122883320B30', 518.16, 91.44,
          {'1': RAIL3, '2': GND, '3': 'ADC_SCKI_SRC', '4': RAIL3}, 'Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm',
          fields={'LCSC': LCSC['CJO05-122883320B30'], 'MPN': 'CJO05-122883320B30', 'Frequency': '12.288MHz',
                  'Datasheet': OSC12_DS})
    res('R707', '0R', 'ADC_SCKI_SRC', 'ADC_SCKI', 502.92, 127.0)
    cap('C715', '100nF', RAIL3, GND, 518.16, 127.0)
    res('R708', '10k', 'ADC_MD1', RAIL3, 345.44, 162.56)
    res('R709', '10k', 'ADC_MD0', GND, 360.68, 162.56)
    res('R710', '10k', 'ADC_FMT', GND, 375.92, 162.56)
    place('FB701', 'Device:FerriteBead', 'GZ1608D601TF 600R@100MHz', 391.16, 162.56, {'1': RAIL5, '2': 'ADC_VCC_5V'},
          'Inductor_SMD:L_0603_1608Metric',
          fields={'LCSC': LCSC['GZ1608D601TF'], 'MPN': 'GZ1608D601TF',
                  'Datasheet': 'https://www.lcsc.com/product-detail/ferrite-beads_sunlord-gz1608d601tf_C1002.html'})
    cap('C716', '10uF', 'ADC_VCC_5V', GND, 406.4, 162.56, C0805)
    cap('C717', '100nF', 'ADC_VCC_5V', GND, 421.64, 162.56)
    cap('C718', '10uF', RAIL3, GND, 436.88, 162.56, C0805)
    cap('C719', '100nF', RAIL3, GND, 452.12, 162.56)
    cap('C720', '10uF', 'ADC_VREF', GND, 467.36, 162.56, C0805)
    cap('C721', '100nF', 'ADC_VREF', GND, 482.6, 162.56)
    # Input network per channel (see docs/design/av-clock-schematic.md, level math):
    #   R_load 200 R to GND  = console load (OpenSFC SHVC-CPU-01 R95/R96 = 200, AC path 1 uF + 10 k)
    #   R_top 4.7k / R_bot 5.1k (|| 60 k ADC input) = gain 0.500: 5.0 Vp-p (5 V-rail maximum) -> 2.5 Vp-p
    #   C_aa 1 nF C0G at the divider node: fc = 1/(2 pi 2.35k 1n) = 67.7 kHz (-0.24 dB at 16 kHz)
    #   C_c 1 uF to VINx (datasheet Figure 26 value; X7R ceramic instead of electrolytic: provisional)
    for i, (ch, src, dst) in enumerate((('L', 'SNES_AUDIO_L_IN', 'ADC_VINL'), ('R', 'SNES_AUDIO_R_IN', 'ADC_VINR'))):
        base, x0 = 711 + 3 * i, 345.44 + 91.44 * i
        div = f'AUD_{ch}_DIV'
        res(f'R{base}', '200', src, GND, x0, 213.36)
        res(f'R{base + 1}', '4.7k', src, div, x0 + 15.24, 213.36)
        res(f'R{base + 2}', '5.1k', div, GND, x0 + 30.48, 213.36)
        cap(f'C{722 + 2 * i}', '1nF C0G', div, GND, x0 + 45.72, 213.36)
        cap(f'C{723 + 2 * i}', '1uF 25V X7R', div, dst, x0 + 60.96, 213.36, C0805)

    # FPGA_3V3 and 5V_PRE come from the power sheet (FPGA_3V3 flagged there as #FLG304, 5V_PRE driven by
    # the TPS63070 power output), so #FLG701/#FLG702 were removed at the round-3 integration (a second
    # power origin on one net is an ERC error).
    # ADC_VCC_5V is 5V_PRE after FB701 (a passive part): flag it as a supplied rail (standard post-filter flag).
    place('#FLG703', 'power:PWR_FLAG', 'PWR_FLAG', 406.4, 187.96, {'1': 'ADC_VCC_5V'})

    # ---- Hierarchical ports: hier label -- wire -- same-name local label ----
    def port(name, shape, x, y):
        claim(x + 7.62, y, 'label', name + '@port')
        parts.append(f'(hierarchical_label {q(name)} (shape {shape}) (at {g(x)} {g(y)} 180) '
                     f'(effects (font (size 1.27 1.27)) (justify right)) (uuid {q(uid("hl:" + name))}))')
        parts.append(f'(wire (pts (xy {g(x)} {g(y)}) (xy {g(x + 7.62)} {g(y)})) (stroke (width 0) (type default)) '
                     f'(uuid {q(uid("pw:" + name))}))')
        parts.append(f'(label {q(name)} (at {g(x + 7.62)} {g(y)} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) '
                     f'(uuid {q(uid("pl:" + name))}))')
    allports = ROOT_PORTS + PENDING_PORTS
    for i, (name, shape) in enumerate(allports):
        col, row = divmod(i, 14)
        port(name, shape, 297.18 + 60.96 * col, 294.64 + 5.08 * row)

    notes = [
        txt('SN 64 - CLOCKS, HDMI OUTPUT AND CARTRIDGE AUDIO ADC (DRAFT 0.1-av)', 20.32, 15.24, 2.54),
        txt('CLOCKS (docs/design/clock-plan.md). U701 Si5351A-B-GT (Skyworks Si5351-B Rev 1.3): CLK0 = NTSC master 21.4772727 MHz, '
            'CLK1 = PAL master 21.28137 MHz, CLK2 = HDMI pixel 27.0197947 MHz;\n'
            'programmed at power-on by fpga/rtl/sn64_clock_init.sv over si_scl/si_sda (I2C address 0x60, 400 kHz). '
            'VDD and VDDO both FPGA_3V3 (sec. 7.2: VDDO with or before VDD). One 100 nF per supply pin (sec. 7.1).\n'
            'Y701 25 MHz crystal, CL 10 pF: matches register 183 XTAL_CL = 11b (0xD2) in sn64_clock_init.sv (AN619 Rev 0.8). '
            'Internal load capacitance only; no external load caps (sec. 7.4).\n'
            'Crystal (YXC YSX321SL datasheet): ESR <= 50 R, drive level up to 200 uW, C0 <= 3 pF; Si5351 Table 8 needs ESR <= 150 R, '
            'max drive level >= 100 uW, CL 6-12 pF.\n'
            'R701/R702 4.7k pull-ups to VDD (Figure 5; >= 1k per Table 20). R703-R705 0R: Si5351 drives 50 R (Table 5, ZO) into a 50 R trace; '
            'sec. 7.6 shows an optional 0 R series resistor (EMI).\n'
            'X701 25 MHz 3.3 V CMOS oscillator (FPGA housekeeping, osc_25): pin 1 enable tied high (run), R706 0R optional damping. '
            'Footprint pads differ slightly from the CJO05 suggested layout: PROVISIONAL.',
            20.32, 22.86),
        txt('HDMI (docs/design/av-output-implementation.md): 720x480p, ECP5 LVCMOS33D pseudo-differential outputs. TMDS network reused from '
            'ULX3S gpdi.sch @6a92cec (MIT + logo condition, hardware/sn64/THIRD_PARTY.md):\n'
            'each TMDS line = 22 nF series capacitor (ULX3S C38-C45), no series resistor. U702 TPD12S016 (TI SLLSE96F) on the connector side: '
            'TMDS ESD, DDC/CEC level shift (A = FPGA_3V3, B = 5V_OUT),\n'
            'HPD buffer (HPD_A referenced to VCCA = 3.3 V), and the HDMI +5V pin from its 55 mA current-limited load switch '
            '(VCC5V = 5V_PRE). LS_OE and CT_HPD tied to VCCA = fully on (Table 1).\n'
            'No external DDC/CEC/HPD pull-ups (sec. 7.3.15). A-side VIL max 0.082 x VCCA (0.27 V at 3.3 V): the FPGA DDC master must pull '
            'hard low - check at bring-up. CEC_A has no FPGA pin in the contract: TP701 only.\n'
            'UTILITY/HEC (pin 14) not connected. J701 Amphenol 10029449-111RLF (LCSC C427307, as ULX3S v1.8.1+); '
            'footprint 10029449-x01xLF PROVISIONAL until the -111RLF drawing is checked.',
            20.32, 170.18),
        txt('CARTRIDGE AUDIO (SNES socket pins 31 AUDIO_L_IN / 62 AUDIO_R_IN). U703 PCM1808 (TI SLES177B) in I2S MASTER mode, 384 fs: '
            'MD1 = H (R708 to VDD), MD0 = L, FMT = L (I2S 24-bit).\n'
            'X702 12.288 MHz = 384 x 32 kHz -> fs = 32.000 kHz (own oscillator; asynchronous to the SNES master: '
            'the FPGA must rate-match). BCK = 64 fs = 2.048 MHz, outputs at VDD = FPGA_3V3.\n'
            'VCC (analog 5 V) = 5V_PRE through FB701 + 10 uF + 100 nF; VDD (digital) = FPGA_3V3; AGND/DGND to GND at the device.\n'
            'Input per channel: R711/R714 200 R to GND = console load (OpenSFC SHVC-CPU-01 R95/R96 200 R; its 1 uF + 10 k summing input in parallel).\n'
            'Divider 4.7k / (5.1k || 60k ADC input) = 0.500: 5.0 Vp-p at the pin (largest swing from the 5 V-only cartridge supply) -> 2.5 Vp-p; '
            'ADC full scale 0.6 x VCC = 3.0 Vp-p (2.85 Vp-p at 4.75 V).\n'
            'Input impedance at the pin 200 R || 9.4k = 196 R (console: 200 R || 10k = 196 R). 1 nF C0G: 67.7 kHz anti-alias pole '
            '(internal filter -3 dB at 1.3 MHz). 1 uF coupling: 2.6 Hz high-pass.\n'
            'Reference level: sd2snes Rev F (CS4344 at 3.3 V, 0.65 x VA typ = 2.15 Vp-p, 100 R + 470 R) gives ~0.56 Vp-p '
            'into the 200 R console load -> -20.6 dBFS here. SNES audio does NOT go to N64_AUDIO_L/R (no requirement; see doc).',
            297.18, 22.86),
        txt('HIERARCHICAL PORTS (shared net-name contract; GND/SNES_AUDIO_* are root labels, the rest pending on the FPGA/power sheets)',
            297.18, 287.02, 1.524),
        txt('DRAFT 0.1-av: schematic circuit candidate only. No PCB, SI simulation, HDMI compliance or audio measurement has been performed.\n'
            'FPGA_3V3 and 5V_PRE are hierarchical inputs from the power sheet (ERC origins there: #FLG304 and the TPS63070 VOUT).\n'
            'Provisional: 0R series values, 200 R console-equivalent load (OpenSFC value, verify on SHVC-CPU-01), X7R 1 uF coupling, footprints of '
            'J701/X701/X702.\nSources and SHA-256 of every datasheet: libraries/av-provenance.json. See docs/design/av-clock-schematic.md.',
            20.32, 381.0)]

    contents = (f'(kicad_sch (version 20250114) (generator "sn64_av_clock_authoring") (uuid {q(page_uuid)}) (paper "A2") '
                f'(title_block (title "SN 64 - clocks, HDMI and cartridge audio") (date "2026-09-29") (rev "0.1-av") (company "SN 64") '
                f'(comment 1 "DESIGN DRAFT - NOT FOR MANUFACTURE"))\n(lib_symbols\n'
                + '\n'.join(dump(s) for s in libs.values()) + ')\n' + '\n'.join(parts + notes)
                + f'\n(sheet_instances (path {q("/" + root_uuid + "/" + sheet_uuid)} (page {q(PAGE)}))) (embedded_fonts no))')
    save(dest, contents)

    own = [copy.deepcopy(s) for key, s in libs.items() if key.startswith(LIB + ':')]
    for s in own:
        s[1] = Quoted(str(s[1]).split(':', 1)[1])
    save(proj / 'libraries' / f'{LIB}.kicad_sym',
         '(kicad_symbol_lib (version 20250114) (generator "sn64_av_clock_authoring")\n' + '\n'.join(dump(s) for s in own) + ')')

    ds_files = {
        'Si5351-B.pdf': ('https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/data-sheets/Si5351-B.pdf',
                         'Skyworks Si5351A/B/C-B Rev 1.3 (Aug 27 2021)'),
        'AN619.pdf': ('https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/application-notes/AN619.pdf',
                      'Skyworks AN619 Rev 0.8 (Sep 23 2021), register 183'),
        'tpd12s016.pdf': (TI['tpd12s016'], 'TI SLLSE96F, revised October 2015'),
        'pcm1808.pdf': (TI['pcm1808'], 'TI SLES177B, revised August 2015'),
        'CS4344-45-48_F2.pdf': ('https://statics.cirrus.com/pubs/proDatasheet/CS4344-45-48_F2.pdf',
                                'Cirrus DS613F2 (sd2snes cartridge-audio DAC level reference)'),
        'CJO05-250003320B30_C712741.pdf': (OSC_DS, 'JSCJ spec rev1.0 (2020-11-05)'),
        'CJO05-122883320B30_C712747.pdf': (OSC12_DS, 'JSCJ spec rev1.1 (2024-12-02)'),
        'X322525MMB4SI_C70582.pdf': ('https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2403291504_YXC-Crystal-Oscillators-X322525MMB4SI_C70582.pdf',
                                     'YXC YSX321SL crystal unit sheet'),
        '10029449-111RLF_C427307.pdf': ('https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2304140030_Amphenol-ICC-10029449-111RLF_C427307.pdf',
                                        'Amphenol FCI drawing 10029449 rev Y (2023-01-12)'),
        'ulx3s-gpdi.sch': ('https://raw.githubusercontent.com/emard/ulx3s/6a92cec6b177191c5b0f80e260013a1f8ec147dd/gpdi.sch',
                           'ULX3S gpdi.sch at the pinned commit 6a92cec6b177191c5b0f80e260013a1f8ec147dd'),
        'ulx3s-LICENSE.md': ('https://raw.githubusercontent.com/emard/ulx3s/6a92cec6b177191c5b0f80e260013a1f8ec147dd/LICENSE.md',
                             'ULX3S LICENSE.md at the pinned commit'),
    }
    sources = {}
    for name, (url, rev) in ds_files.items():
        rec = {'url': url, 'revision': rev}
        if a.datasheets and (a.datasheets / name).exists():
            rec['sha256_of_downloaded_copy'] = hashlib.sha256((a.datasheets / name).read_bytes()).hexdigest()
        sources[name] = rec
    std = sorted({key for key in libs if not key.startswith(LIB + ':')})
    provenance = {
        'schema_version': 1, 'recorded_date': '2026-09-29',
        'scope': 'Clock/HDMI/cartridge-audio child-sheet symbols and component evidence; schematic draft only.',
        'tool_version': 'KiCad 10.0.6',
        'drawn_symbols': {
            'TPD12S016PW': {'library': f'libraries/{LIB}.kicad_sym', 'source': sources['tpd12s016.pdf'],
                            'source_section': 'Section 5 Pin Configuration and Functions, PW (24-pin TSSOP) column',
                            'pins': {p[0]: p[1] for p in TPD12S016_PINS},
                            'footprint': 'Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm (installed KiCad library)'},
            'PCM1808PW': {'library': f'libraries/{LIB}.kicad_sym', 'source': sources['pcm1808.pdf'],
                          'source_section': 'Section 5 Pin Configuration and Functions (14-pin TSSOP PW)',
                          'pins': {p[0]: p[1] for p in PCM1808_PINS},
                          'footprint': 'Package_SO:TSSOP-14_4.4x5mm_P0.65mm (installed KiCad library)'}},
        'installed_kicad_symbols_used_unmodified': std,
        'installed_kicad_footprints_referenced': sorted(fps),
        'sources': sources,
        'lcsc_parts_2026_09_29': LCSC,
        'facts_used': {
            'si5351_msop10_pins_table_20': {'1': 'VDD', '2': 'XA', '3': 'XB', '4': 'SCL', '5': 'SDA', '6': 'CLK2', '7': 'VDDO',
                                            '8': 'GND', '9': 'CLK1', '10': 'CLK0'},
            'si5351_crystal_table_8': 'fXTAL 25-27 MHz; CL 6-12 pF; rESR <= 150 ohm; crystal max drive level >= 100 uW',
            'an619_register_183': 'bits 7:6 XTAL_CL: 01 = 6 pF, 10 = 8 pF, 11 = 10 pF; bits 5:0 write 010010b. '
                                  'sn64_clock_init.sv writes 0xD2 = 11 010010b = 10 pF.',
            'si5351_output': 'ZO 50 ohm at 3.3 V VDDO default high drive; sec. 7.6 Figure 16: optional 0 ohm series resistor',
            'si5351_i2c': 'pull-ups to VDD, at least 1 k (Table 20); Figure 5 shows 4.7 k; address 0x60',
            'crystal_ysx321sl': 'pins 1/3 crystal, 2/4 GND; CL 10 pF (X322525MMB4SI); ESR 50 ohm max 16-31 MHz; DL 10-200 uW; C0 3 pF max',
            'cjo05_oscillators': 'pin 1 enable/disable (>= 0.7 VDD or open = run), 2 GND, 3 output, 4 VDD; 3.3 V +/-10 %; 15 pF load; '
                                 'suggested pads 25 MHz rev1.0: 1.3 x 1.2 mm, gaps 0.9/0.5; 12.288 MHz rev1.1: 1.4 x 1.2 mm, gaps 0.8/0.5',
            'kicad_ase_footprint_pads': 'Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm: 1.3 x 1.1 mm pads at +/-1.05, +/-0.825 (gaps 0.8/0.55)',
            'kicad_crystal_3225_pads': 'Crystal_SMD_3225-4Pin_3.2x2.5mm: 1.4 x 1.2 mm pads at +/-1.1, +/-0.85 (gaps 0.8/0.5) = YXC suggested layout',
            'tpd12s016': 'LS_OE/CT_HPD active-high, referenced to VCCA; H/H = fully on (Table 1); 55 mA current-limited 5V_OUT; '
                         'no external DDC/CEC/HPD pull-ups needed (7.3.15); D/CLK abs max 6 V; VCCA 1.1-3.6 V; VCC5V 4.5-5.5 V; '
                         'SCL_A/SDA_A VIL max 0.082 x VCCA',
            'pcm1808': 'MD1/MD0: LL slave, LH master 512 fs, HL master 384 fs, HH master 256 fs (Table 2); FMT L = I2S 24-bit, '
                       'H = left-justified 24-bit (Table 3); 32 kHz x 384 = 12.288 MHz (Table 1); input 0.6 VCC Vp-p, 60 k, '
                       'VREF 0.5 VCC, internal anti-alias -3 dB 1.3 MHz (6.5); straps 10 k to VDD/GND (8.2.2.1); '
                       'master mode BCK = 64 fs (7.3.5.1.1); VCC 4.5-5.5 V, VDD 2.7-3.6 V',
            'ulx3s_gpdi_tmds': 'FPDI_D0+..FPDI_CLK- -> 22 nF (C38..C45, 0603) -> GPDI connector pins; note "SINGLE ENDED - NOT '
                               'DIFFERENTIAL"; HPD via 549 R + 3.6 V zener, DDC via PCA9306, +5V direct (not reused: TPD12S016 '
                               'replaces them)',
            'hdmi_type_a_pins': 'KiCad Connector:HDMI_A symbol numbering and ULX3S gpdi.sch connector order agree: 1 D2+, 2 D2 shield, '
                                '3 D2-, 4 D1+, 5 D1S, 6 D1-, 7 D0+, 8 D0S, 9 D0-, 10 CK+, 11 CKS, 12 CK-, 13 CEC, 14 UTILITY, 15 SCL, '
                                '16 SDA, 17 GND, 18 +5V, 19 HPD',
            'opensfc_cart_audio_load': 'OpenSFC SHVC-CPU-01 Rev A @6574450: P1.31 SL.IN / P1.62 SR.IN each: R96/R95 200 to GND, '
                                       '1 uF (C28/C25) to 10 k (R62/R55) into the LM358 inverting summer (24 k feedback, +9 V)',
            'sd2snes_revf_cart_audio_source': 'sd2snes Rev F @cf7e21d: CS4344 (VA = +3.3VDAC) AOUT -> 3.3 uF -> 10 k to AGND -> '
                                              '470 R -> J101.31/62 with 10 nF to AGND',
            'cs4344_full_scale': 'Full scale output 0.60/0.65/0.70 x VA Vpp (min/typ/max), ZOUT 100 ohm (DS613F2)'},
        'licenses': 'KiCad library content: CC-BY-SA-4.0 with the KiCad library exception. Drawn symbols: SN64 project content; '
                    'pin data are facts from the cited TI datasheets. ULX3S TMDS coupling network reused as a circuit idea '
                    '(22 nF series capacitor per line); no ULX3S layout or artwork imported.'}
    save(proj / 'libraries' / 'av-provenance.json', json.dumps(provenance, indent=2))

    if a.attach_root:
        attach(a.attach_root.resolve(), root_uuid, sheet_uuid, allports)
    n_pins = sum(1 for p in parts if p.startswith('(pin '))
    print('Authored AV/clock sheet:', len([p for p in parts if p.startswith('(symbol (lib_id')]), 'symbols;',
          n_pins, 'pins;', len(fps), 'footprints;', len(allports), 'ports')


def attach(root_path, root_uuid, sheet_uuid, allports):
    """Append the sheet symbol to a root schematic (validation copy or, at integration, the real root)."""
    original = root_path.read_text(encoding='utf-8')
    if sheet_uuid in original:
        print('Sheet symbol already present in', root_path)
        return
    if str(get(parse_text(original), 'uuid')[1]) != root_uuid:
        raise SystemExit('Root uuid differs from hardware/sn64/sn64.kicad_sch; instance paths would not match')
    sx, sy, w = 302.26, 45.72, 20.32
    root_named = {n for n, _ in ROOT_PORTS}
    pins, labels = [], []
    for i, (name, shape) in enumerate(allports):
        py = sy + 5.08 + 2.54 * i
        pins.append(f'(pin {q(name)} {shape} (at {g(sx)} {g(py)} 180) (effects (font (size 1.27 1.27)) (justify left)) '
                    f'(uuid {q(uid("root-pin:" + name))}))')
        if name in root_named:
            labels.append(f'(label {q(name)} (at {g(sx)} {g(py)} 180) (effects (font (size 1.016 1.016)) (justify right bottom)) '
                          f'(uuid {q(uid("root-label:" + name))}))')
        else:
            # Pending: no root net yet (FPGA and power sheets). Remove the marker when they connect.
            labels.append(f'(no_connect (at {g(sx)} {g(py)}) (uuid {q(uid("root-nc:" + name))}))')
    h = round(5.08 + 2.54 * len(allports) + 2.54, 2)
    block = (f'(sheet (at {g(sx)} {g(sy)}) (size {g(w)} {g(h)}) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0)) '
             f'(uuid {q(sheet_uuid)}) '
             + prop('Sheetname', SHEET_NAME, sx, sy - 1.27, justify='left bottom')
             + prop('Sheetfile', SHEET_FILE, sx, sy + h + 1.27, justify='left top')
             + ' ' + ' '.join(pins)
             + f' (instances (project "sn64" (path {q("/" + root_uuid)} (page {q(PAGE)})))))\n' + '\n'.join(labels))
    save(root_path, original.rstrip()[:-1].rstrip() + '\n' + block + '\n)')
    table_path = root_path.parent / 'sym-lib-table'
    if table_path.exists():
        table = parse(table_path)
        if not any(isinstance(e, list) and e and e[0] == 'lib' and get(e, 'name')[1] == LIB for e in table):
            table.append(['lib', ['name', Quoted(LIB)], ['type', Quoted('KiCad')],
                          ['uri', Quoted('${KIPRJMOD}/libraries/' + LIB + '.kicad_sym')], ['options', Quoted('')],
                          ['descr', Quoted('Clock/HDMI/cartridge-audio draft; see libraries/av-provenance.json')]])
            save(table_path, dump(table))
    print('Attached sheet symbol to', root_path)


if __name__ == '__main__':
    main()
