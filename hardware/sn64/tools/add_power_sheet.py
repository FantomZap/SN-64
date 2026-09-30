"""Author the SN64 power child sheet (power.kicad_sch) from the recorded power architecture.

One-time draft authoring utility in the style of add_cart_interface.py. It writes
power.kicad_sch, the project-local SN64_POWER symbol library (only the parts the
installed KiCad library lacks) and libraries/power-provenance.json. It does NOT
touch sn64.kicad_sch or sym-lib-table unless --attach is given; --attach is meant
for a validation COPY of the project (or for the integration pass) and appends ONE
sheet symbol plus labels/no-connects on its pins, and the SN64_POWER sym-lib-table
entry. It refuses to replace an existing power.kicad_sch unless --force is given;
after native KiCad editing starts, edit the KiCad files instead of regenerating.

  python add_power_sheet.py --kicad-share "C:/Program Files/KiCad/10.0/share/kicad"
       [--datasheets <dir with the downloaded PDFs>] [--project-dir <dir>] [--force]
  python add_power_sheet.py --kicad-share ... --project-dir <copy> --attach-only

Circuit (docs/design/power-schematic.md has the equations and sources):
  HOST_3V3 -> U303 TPS259470L (auxiliary) --+
  USB_VBUS -> U302 TPS259470L (priority)  --+--> SYS_VIN -> U304 TPS63070 -> 5V_PRE
  U301 TUSB320I (UFP, GPIO) + Q301-Q303 default-off permission on U302 EN/UVLO;
  U302 AUXOFF -> Q304 -> U303 EN/UVLO (TPS25947 SLVSFC9C Figure 8-14 priority mux).
  5V_PRE -> U305/U306/U307 TLV62569 -> FPGA_1V1 / FPGA_2V5 / FPGA_3V3 (ULX3S topology)
  5V_PRE -> U309 TPS259470L (default off via Q305/Q306, discharge Q307) -> SNES_5V_CART
  FPGA_3V3 -> U308 TPS22918 (default off, QOD) -> INTERFACE_3V3
  U310-U315 TPS3700 window monitors, U316 TPS3808G01 supervisor, U317 TMP302A + Q308.
Pure Python 3 (no pcbnew needed).
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_cart_interface import Quoted, dump, get, items, parse, parse_text, q, save  # noqa: E402  (house helpers)

TOOLS = Path(__file__).resolve().parent
NS = uuid.UUID('7a3c1e4e-2f5b-4c61-9a0e-5b1d0f6c2d77')
SHEET_FILE = 'power.kicad_sch'
SHEET_NAME = 'Power'
LIB = 'SN64_POWER'


def uid(s):
    return str(uuid.uuid5(NS, s))


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
# PIN TABLES for drawn symbols (independently re-typed in verify_power_sheet.py)
#   TPS259470L RPW  : TI SLVSFC9C (May 2026) Figure 5-1 / Table 5-1
#   TPS63070 RNM    : TI SLVSC58B (March 2019) Pin Functions table
#   TPS3700 DDC     : TI SBVS187G (February 2019) Pin Functions (DDC column)
#   TPS22918 DBV    : TI SLVSD76C (July 2017) Pin Functions
#   TMP302 DRL      : TI SBOS488E (December 2018) Pin Functions
# Switch outputs (eFuse OUT, load-switch VOUT) are drawn passive: they pass, not
# generate, power, and two eFuse outputs share SYS_VIN in the priority mux.
# ---------------------------------------------------------------------------
L, R = -17.78, 17.78
TPS25947_PINS = [('1', 'EN/UVLO', 'input', L, 5.08, 0), ('2', 'OVLO', 'input', L, 2.54, 0),
                 ('3', 'AUXOFF', 'open_collector', R, 0, 180), ('4', '~{FLT}', 'open_collector', R, -2.54, 180),
                 ('5', 'IN', 'power_in', L, 10.16, 0), ('6', 'OUT', 'passive', R, 10.16, 180),
                 ('7', 'DVDT', 'passive', L, -5.08, 0), ('8', 'GND', 'power_in', 0, -25.4, 90),
                 ('9', 'ILM', 'passive', L, -7.62, 0), ('10', 'ITIMER', 'passive', L, -10.16, 0)]
TPS63070_PINS = [('1', 'PS/SYNC', 'input', L, -2.54, 0), ('2', 'PG', 'open_collector', R, -2.54, 180),
                 ('3', 'VAUX', 'passive', L, -7.62, 0), ('4', 'GND', 'power_in', -2.54, -25.4, 90),
                 ('5', 'FB', 'input', R, 2.54, 180), ('6', 'FB2', 'passive', R, -7.62, 180),
                 ('7', 'VOUT', 'power_out', R, 10.16, 180), ('8', 'VOUT', 'passive', R, 7.62, 180),
                 ('9', 'L2', 'passive', 2.54, 17.78, 270), ('10', 'PGND', 'power_in', 2.54, -25.4, 90),
                 ('11', 'L1', 'passive', -2.54, 17.78, 270), ('12', 'VIN', 'power_in', L, 10.16, 0),
                 ('13', 'VIN', 'power_in', L, 7.62, 0), ('14', 'EN', 'input', L, 2.54, 0),
                 ('15', 'VSEL', 'input', L, -5.08, 0)]
TPS3700_PINS = [('1', 'OUTA', 'open_collector', R, 2.54, 180), ('2', 'GND', 'power_in', 0, -25.4, 90),
                ('3', 'INA+', 'input', L, 2.54, 0), ('4', 'INB-', 'input', L, -2.54, 0),
                ('5', 'VDD', 'power_in', 0, 17.78, 270), ('6', 'OUTB', 'open_collector', R, -2.54, 180)]
TPS22918_PINS = [('1', 'VIN', 'power_in', L, 5.08, 0), ('2', 'GND', 'power_in', 0, -25.4, 90),
                 ('3', 'ON', 'input', L, 0, 0), ('4', 'CT', 'passive', L, -5.08, 0),
                 ('5', 'QOD', 'passive', R, 0, 180), ('6', 'VOUT', 'passive', R, 5.08, 180)]
TMP302_PINS = [('1', 'TRIPSET0', 'input', L, 2.54, 0), ('2', 'GND', 'power_in', 0, -25.4, 90),
               ('3', '~{OUT}', 'open_collector', R, 0, 180), ('4', 'HYSTSET', 'input', L, -2.54, 0),
               ('5', 'VS', 'power_in', 0, 17.78, 270), ('6', 'TRIPSET1', 'input', L, 0, 0)]


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
# Design values (math in docs/design/power-schematic.md). PROV = provisional.
# ---------------------------------------------------------------------------
TI = 'https://www.ti.com/lit/ds/symlink/'
LCSC = {'TPS259470LRPWR': 'C3662793', 'TUSB320IRWBR': 'C80170', 'TPS3700DDCR': 'C33002',
        'TPS63070RNMR': 'C109322', 'TLV62569DBVR': 'C141836', 'TPS22918DBVR': 'C131941',
        'TPS3808G01DBVR': 'C19653', 'TMP302ADRLR': 'C2877557', 'BSS138BK,215': 'C282529',
        'PNR4020-1R5M': 'C54620133', 'FNR4030S2R2MT': 'C167869'}
# TPS3700 windows: (ref, monitored rail, output net, R1 top, R2 mid, R3 bottom), E192 0.1 %
WINDOWS = [('U310', 'SYS_VIN', 'host_3v3_ok', '442k', '37.4k', '33.6k'),
           ('U311', 'FPGA_1V1', 'fpga_rails_ok', '115k', '3.74k', '64.2k'),
           ('U312', 'FPGA_2V5', 'fpga_rails_ok', '287k', '3.16k', '53.0k'),
           ('U313', 'FPGA_3V3', 'fpga_rails_ok', '277k', '2.37k', '37.0k'),
           ('U314', 'SNES_5V_CART', 'cart_5v_ok', '530k', '3.79k', '44.2k'),
           ('U315', 'INTERFACE_3V3', 'iface_rail_ok', '232k', '5.05k', '30.1k')]
# Buck feedback: (ref, rail, SW net, FB net, R1 top, R2 bottom), E192 0.1 %
BUCKS = [('U305', 'FPGA_1V1', 'SW_1V1', 'FB_1V1', '100k', '120k', 'L302'),
         ('U306', 'FPGA_2V5', 'SW_2V5', 'FB_2V5', '361k', '114k', 'L303'),
         ('U307', 'FPGA_3V3', 'SW_3V3', 'FB_3V3', '459k', '102k', 'L304')]
# eFuses: (ref, IN, OUT, EN net, OVLO net, UVLO R1, OVLO R1, RILM, CdVdt, CITIMER, FLT net, AUXOFF net)
EFUSES = [('U302', 'USB_VBUS', 'SYS_VIN', 'USB_EN', 'USB_OVLO', '267k', '383k', '2.55k', '1.5nF', '1.2nF',
           'USB_FLT_N', 'USB_AUXOFF'),
          ('U303', 'HOST_3V3', 'SYS_VIN', 'HOST_EN', 'HOST_OVLO', '150k', '215k', '6.65k', '1.5nF', '1.2nF',
           'HOST_FLT_N', 'HOST_AUXOFF'),
          ('U309', '5V_PRE', 'SNES_5V_CART', 'CART_EN', 'CART_OVLO', '287k', '357k', '3.32k', '680pF', '1.2nF',
           'efuse_fault_n', 'CART_AUXOFF')]

# Hierarchical interface (name, shape). Names follow the shared net contract.
PORTS = ([('GND', 'passive'), ('HOST_3V3', 'input'), ('USB_VBUS', 'input'), ('USB_3V3', 'input'),
          ('USB_CC1', 'bidirectional'), ('USB_CC2', 'bidirectional'),
          ('5V_PRE', 'output'), ('FPGA_1V1', 'output'), ('FPGA_2V5', 'output'), ('FPGA_3V3', 'output'),
          ('SNES_5V_CART', 'output'), ('INTERFACE_3V3', 'output'),
          ('cart_5v_enable', 'input'), ('iface_rail_enable', 'input')]
         + [(n, 'output') for n in ['host_3v3_ok', 'fpga_rails_ok', 'cart_5v_ok', 'iface_rail_ok',
                                    'efuse_fault_n', 'overtemp', 'board_reset_n']])


def build(a, root_uuid):
    sheet_uuid = uid('power-sheet')
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

    libs[LIB + ':TPS259470LRPW'] = own_symbol('TPS259470LRPW', 'TPS259470LRPWR', TPS25947_PINS,
                                              '2.7-23 V eFuse, adjustable UVLO/OVLO, active current limit, latch-off, true reverse blocking',
                                              TI + 'tps25947.pdf', '')
    libs[LIB + ':TPS63070RNM'] = own_symbol('TPS63070RNM', 'TPS63070RNMR', TPS63070_PINS,
                                            '2-16 V input buck-boost converter, adjustable output, power good',
                                            TI + 'tps63070.pdf', '')
    libs[LIB + ':TPS3700DDC'] = own_symbol('TPS3700DDC', 'TPS3700DDCR', TPS3700_PINS,
                                           'Window comparator, 400 mV references, open-drain outputs',
                                           TI + 'tps3700.pdf', 'Package_TO_SOT_SMD:SOT-23-6')
    libs[LIB + ':TPS22918DBV'] = own_symbol('TPS22918DBV', 'TPS22918DBVR', TPS22918_PINS,
                                            '1-5.5 V 2 A load switch, adjustable rise time and quick output discharge',
                                            TI + 'tps22918.pdf', 'Package_TO_SOT_SMD:SOT-23-6')
    libs[LIB + ':TMP302DRL'] = own_symbol('TMP302DRL', 'TMP302ADRLR', TMP302_PINS,
                                          'Temperature switch, pin-selectable trip and hysteresis, open-drain active-low output',
                                          TI + 'tmp302.pdf', 'Package_TO_SOT_SMD:SOT-563')

    def place(ref, lib_id, value, x, y, nets, fp='', dnp=False, fields=None):
        sym = load(lib_id)
        pins = [p for u in items(sym, 'symbol') for p in items(u, 'pin')]
        assert {str(get(p, 'number')[1]) for p in pins} == set(nets), (ref, sorted(nets))
        small = lib_id in ('Device:R', 'Device:C', 'Device:L', 'Connector:TestPoint', 'power:PWR_FLAG')
        if small:
            rx, ry, vx, vy, just = x + 2.54, y - 1.27, x + 2.54, y + 1.27, 'left'
        else:
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
    R0805 = 'Resistor_SMD:R_0805_2012Metric'
    C0603 = 'Capacitor_SMD:C_0603_1608Metric'
    C0805 = 'Capacitor_SMD:C_0805_2012Metric'
    C1206 = 'Capacitor_SMD:C_1206_3216Metric'
    FET = 'Transistor_FET:BSS138'
    FETF = {'Datasheet': 'https://assets.nexperia.com/documents/data-sheet/BSS138BK.pdf', 'MPN': 'BSS138BK,215',
            'LCSC': LCSC['BSS138BK,215']}
    passives = []   # (ref, kind, value, n1, n2, fp)

    def R(ref, value, n1, n2, fp=R0603):
        passives.append((ref, 'Device:R', value, n1, n2, fp))

    def C(ref, value, n1, n2='GND', fp=C0603):
        passives.append((ref, 'Device:C', value, n1, n2, fp))

    # --- Row 1: USB current-class detection, permission, input eFuses ------
    y1 = 76.2
    place('U301', 'Interface_USB:TUSB320I', 'TUSB320IRWBR', 60.96, y1,
          {'1': 'USB_CC1', '2': 'USB_CC2', '3': 'GND', '4': 'VBUS_DET', '5': None, '6': None,
           '7': 'TC_OUT1', '8': 'TC_OUT2', '9': None, '10': 'GND', '11': 'GND', '12': 'USB_3V3'},
          'Package_DFN_QFN:Texas_X2QFN-12_1.6x1.6mm_P0.4mm',
          fields={'Datasheet': TI + 'tusb320.pdf', 'LCSC': LCSC['TUSB320IRWBR']})
    R('R301', '887k 1%', 'USB_VBUS', 'VBUS_DET')
    R('R302', '100k', 'USB_3V3', 'TC_OUT1')
    R('R303', '100k', 'USB_3V3', 'TC_OUT2')
    C('C301', '100nF', 'USB_3V3')
    # Default-off permission: U302 may enable only while TC_OUT1 is actively low (>=1.5 A class)
    # AND USB_3V3 is present. Any other state (unattached, default USB, TUSB320 or USB_3V3 absent)
    # leaves USB_INHIBIT pulled to VBUS, Q303 on, U302 EN/UVLO low.
    place('Q301', FET, 'BSS138BK', 121.92, y1, {'1': 'TC_OUT1', '2': 'GND', '3': 'USB_PERMIT'}, 'Package_TO_SOT_SMD:SOT-23', fields=FETF)
    place('Q302', FET, 'BSS138BK', 147.32, y1, {'1': 'USB_PERMIT', '2': 'GND', '3': 'USB_INHIBIT'}, 'Package_TO_SOT_SMD:SOT-23', fields=FETF)
    place('Q303', FET, 'BSS138BK', 172.72, y1, {'1': 'USB_INHIBIT', '2': 'GND', '3': 'USB_EN'}, 'Package_TO_SOT_SMD:SOT-23', fields=FETF)
    R('R304', '100k', 'USB_3V3', 'USB_PERMIT')
    R('R305', '100k', 'USB_VBUS', 'USB_INHIBIT')
    place('Q304', FET, 'BSS138BK', 198.12, y1, {'1': 'USB_AUXOFF', '2': 'GND', '3': 'HOST_EN'}, 'Package_TO_SOT_SMD:SOT-23', fields=FETF)
    R('R306', '100k', 'USB_3V3', 'USB_AUXOFF')

    rn, cn = 307, 302
    for i, (ref, vin, vout, en, ovlo, r_uv, r_ov, rilm, cdvdt, ctimer, flt, aux) in enumerate(EFUSES):
        x = 256.54 + 76.2 * i
        tag = ref
        place(ref, LIB + ':TPS259470LRPW', 'TPS259470LRPWR', x, y1,
              {'1': en, '2': ovlo, '3': aux, '4': flt, '5': vin, '6': vout, '7': 'DVDT_' + tag, '8': 'GND',
               '9': 'ILM_' + tag, '10': 'ITIMER_' + tag}, 'SN64:Texas_RPW0010A_VQFN-HR-10_2x2mm',
              fields={'Datasheet': TI + 'tps25947.pdf', 'LCSC': LCSC['TPS259470LRPWR'],
                      'Footprint_status': 'RPW0010A from TI 4225183/A example board layout (tools/make_power_footprints.py); unbuilt'})
        R(f'R{rn}', r_uv + ' 1%', vin, en); R(f'R{rn + 1}', '100k 1%', en, 'GND')
        R(f'R{rn + 2}', r_ov + ' 1%', vin, ovlo); R(f'R{rn + 3}', '100k 1%', ovlo, 'GND')
        R(f'R{rn + 4}', rilm + ' 1%', 'ILM_' + tag, 'GND')
        rn += 5
        C(f'C{cn}', cdvdt + ' 25V', 'DVDT_' + tag); C(f'C{cn + 1}', ctimer, 'ITIMER_' + tag)
        C(f'C{cn + 2}', '1uF 25V', vin, 'GND', C0805)
        cn += 3
    # FLT/AUXOFF pull-ups of the two input eFuses (observation only, test points)
    R('R322', '100k', 'USB_3V3', 'USB_FLT_N')
    R('R323', '100k', 'HOST_3V3', 'HOST_FLT_N')
    R('R324', '100k', 'HOST_3V3', 'HOST_AUXOFF')
    R('R325', '100k', 'FPGA_3V3', 'CART_AUXOFF')
    # Cartridge eFuse enable: default off. cart_5v_enable high -> Q305 on -> CART_INHIBIT low ->
    # Q306 (EN clamp) and Q307 (discharge) off. Pull-down 1k: ECP5 IPU <= 150 uA -> <= 0.15 V.
    place('Q305', FET, 'BSS138BK', 480.06, y1 + 50.8, {'1': 'cart_5v_enable', '2': 'GND', '3': 'CART_INHIBIT'}, 'Package_TO_SOT_SMD:SOT-23', fields=FETF)
    place('Q306', FET, 'BSS138BK', 505.46, y1 + 50.8, {'1': 'CART_INHIBIT', '2': 'GND', '3': 'CART_EN'}, 'Package_TO_SOT_SMD:SOT-23', fields=FETF)
    place('Q307', FET, 'BSS138BK', 530.86, y1 + 50.8, {'1': 'CART_INHIBIT', '2': 'GND', '3': 'CART_DIS'}, 'Package_TO_SOT_SMD:SOT-23', fields=FETF)
    R('R326', '1k', 'cart_5v_enable', 'GND')
    R('R327', '100k', '5V_PRE', 'CART_INHIBIT')
    R('R328', '470 0805', 'SNES_5V_CART', 'CART_DIS', R0805)
    # efuse_fault_n: FLT open drain pulled up to FPGA_3V3 like every other monitor output. A 5V_PRE
    # divider would back-drive left-bank ball K4 while FPGA_3V3 ramps (DS-02012 3.4 section 3.6: left/right
    # banks are not hot-socket capable). FLT is rated -0.3..6.5 V, leakage +/-1 uA (SLVSFC9C). Loss of
    # 5V_PRE is caught by cart_5v_ok and the sequencer's rail timeout, not by this line.
    R('R329', '10k', 'FPGA_3V3', 'efuse_fault_n')

    # --- Row 2: system regulator (TPS63070) and FPGA bucks (TLV62569) -----
    y2 = 177.8
    place('U304', LIB + ':TPS63070RNM', 'TPS63070RNMR', 60.96, y2,
          {'1': 'GND', '2': 'PG_5V', '3': 'VAUX_5V', '4': 'GND', '5': 'FB_5V', '6': None, '7': '5V_PRE',
           '8': '5V_PRE', '9': 'L2_5V', '10': 'GND', '11': 'L1_5V', '12': 'SYS_VIN', '13': 'SYS_VIN',
           '14': 'SYS_VIN', '15': 'GND'}, 'SN64:Texas_RNM0015A_VQFN-HR-15_2.5x3mm',
          fields={'Datasheet': TI + 'tps63070.pdf', 'LCSC': LCSC['TPS63070RNMR'],
                  'Footprint_status': 'RNM0015A from TI SLVSC58B example board layout (tools/make_power_footprints.py); unbuilt'})
    passives.append(('L301', 'Device:L', '1.5uH PNR4020-1R5M', 'L1_5V', 'L2_5V', 'SN64:L_APV_PNR4020'))
    R('R331', '232k 0.1%', '5V_PRE', 'FB_5V'); R('R332', '44.2k 0.1%', 'FB_5V', 'GND')
    R('R333', '100k', '5V_PRE', 'PG_5V')
    C('C311', '100nF', 'VAUX_5V')
    C('C312', '10uF 25V', 'SYS_VIN', 'GND', C0805); C('C313', '10uF 25V', 'SYS_VIN', 'GND', C0805)
    C('C314', '22uF 25V', 'SYS_VIN', 'GND', C1206); C('C315', '22uF 25V', 'SYS_VIN', 'GND', C1206)
    C('C316', '22uF 10V', '5V_PRE', 'GND', C0805); C('C317', '22uF 10V', '5V_PRE', 'GND', C0805)
    C('C318', '22uF 10V', '5V_PRE', 'GND', C0805)
    rn, cn = 334, 319
    for i, (ref, rail, sw, fbn, r1, r2, lref) in enumerate(BUCKS):
        x = 139.7 + 60.96 * i
        place(ref, 'Regulator_Switching:TLV62569DBV', 'TLV62569DBVR', x, y2,
              {'1': 'PG_5V', '2': 'GND', '3': sw, '4': '5V_PRE', '5': fbn}, 'Package_TO_SOT_SMD:SOT-23-5',
              fields={'Datasheet': TI + 'tlv62569.pdf', 'LCSC': LCSC['TLV62569DBVR']})
        passives.append((lref, 'Device:L', '2.2uH FNR4030S2R2MT', sw, rail, 'Inductor_SMD:L_Changjiang_FNR4030S'))
        R(f'R{rn}', r1 + ' 0.1%', rail, fbn); R(f'R{rn + 1}', r2 + ' 0.1%', fbn, 'GND')
        rn += 2
        C(f'C{cn}', '6.8pF C0G', rail, fbn)
        C(f'C{cn + 1}', '22uF 10V', '5V_PRE', 'GND', C0805)
        C(f'C{cn + 2}', '22uF 10V', rail, 'GND', C0805); C(f'C{cn + 3}', '22uF 10V', rail, 'GND', C0805)
        cn += 4

    # --- Row 2b: INTERFACE_3V3 switch -------------------------------------
    place('U308', LIB + ':TPS22918DBV', 'TPS22918DBVR', 358.14, y2,
          {'1': 'FPGA_3V3', '2': 'GND', '3': 'iface_rail_enable', '4': 'CT_IFACE', '5': 'QOD_IFACE', '6': 'INTERFACE_3V3'},
          'Package_TO_SOT_SMD:SOT-23-6', fields={'Datasheet': TI + 'tps22918.pdf', 'LCSC': LCSC['TPS22918DBVR']})
    R('R340', '1k', 'iface_rail_enable', 'GND')
    R('R341', '100', 'QOD_IFACE', 'INTERFACE_3V3')
    C('C331', '470pF 25V C0G', 'CT_IFACE')
    C('C332', '1uF 10V', 'FPGA_3V3')

    # --- Row 3: monitors ----------------------------------------------------
    y3 = 279.4
    rn, cn = 342, 333
    for i, (ref, rail, out, r1, r2, r3) in enumerate(WINDOWS):
        x = 60.96 + 60.96 * i
        ina, inb = 'MON_A_' + ref, 'MON_B_' + ref
        place(ref, LIB + ':TPS3700DDC', 'TPS3700DDCR', x, y3,
              {'1': out, '2': 'GND', '3': ina, '4': inb, '5': 'FPGA_3V3', '6': out}, 'Package_TO_SOT_SMD:SOT-23-6',
              fields={'Datasheet': TI + 'tps3700.pdf', 'LCSC': LCSC['TPS3700DDCR']})
        R(f'R{rn}', r1 + ' 0.1%', rail, ina); R(f'R{rn + 1}', r2 + ' 0.1%', ina, inb); R(f'R{rn + 2}', r3 + ' 0.1%', inb, 'GND')
        rn += 3
        C(f'C{cn}', '100nF', 'FPGA_3V3')
        cn += 1
    # Output pull-ups to the monitors' own supply (FPGA_3V3): 3.3 V-safe, and loss of that
    # supply removes the pull-up (TPS3700 also drives OUTA low below its UVLO).
    R('R360', '10k', 'FPGA_3V3', 'host_3v3_ok')
    R('R361', '10k', 'FPGA_3V3', 'fpga_rails_ok')
    R('R362', '10k', 'FPGA_3V3', 'cart_5v_ok')
    R('R363', '10k', 'FPGA_3V3', 'iface_rail_ok')
    # Supervisor: SENSE watches FPGA_3V3, MR is the FPGA-rail window node; CT open = 20 ms typ.
    place('U316', 'Power_Supervisor:TPS3808DBV', 'TPS3808G01DBVR', 426.72, y3,
          {'1': 'board_reset_n', '2': 'GND', '3': 'fpga_rails_ok', '4': None, '5': 'SENSE_3V3', '6': 'FPGA_3V3'},
          'Package_TO_SOT_SMD:SOT-23-6', fields={'Datasheet': TI + 'tps3808.pdf', 'LCSC': LCSC['TPS3808G01DBVR']})
    R('R364', '649k 1%', 'FPGA_3V3', 'SENSE_3V3'); R('R365', '100k 1%', 'SENSE_3V3', 'GND')
    R('R366', '10k', 'FPGA_3V3', 'board_reset_n')
    C('C339', '100nF', 'FPGA_3V3')
    # Temperature switch: TMP302A, TRIPSET1=TRIPSET0=VS -> 65 C, HYSTSET=VS -> 10 C (PROV).
    place('U317', LIB + ':TMP302DRL', 'TMP302ADRLR', 487.68, y3,
          {'1': 'FPGA_3V3', '2': 'GND', '3': 'OT_N', '4': 'FPGA_3V3', '5': 'FPGA_3V3', '6': 'FPGA_3V3'},
          'Package_TO_SOT_SMD:SOT-563', fields={'Datasheet': TI + 'tmp302.pdf', 'LCSC': LCSC['TMP302ADRLR']})
    R('R367', '47k', 'FPGA_3V3', 'OT_N')
    place('Q308', FET, 'BSS138BK', 530.86, y3, {'1': 'OT_N', '2': 'GND', '3': 'overtemp'}, 'Package_TO_SOT_SMD:SOT-23', fields=FETF)
    R('R368', '10k', 'FPGA_3V3', 'overtemp')
    C('C340', '100nF', 'FPGA_3V3')

    # --- Passive rows --------------------------------------------------------
    for i, (ref, lib_id, value, n1, n2, fp) in enumerate(passives):
        place(ref, lib_id, value, 30.48 + 17.78 * (i % 30), 358.14 + 30.48 * (i // 30), {'1': n1, '2': n2}, fp,
              fields={'MPN': value.split()[1], 'LCSC': LCSC[value.split()[1]]} if lib_id == 'Device:L' else None)
    tps = [('TP301', 'SYS_VIN'), ('TP302', 'USB_FLT_N'), ('TP303', 'HOST_FLT_N'), ('TP304', 'HOST_AUXOFF'),
           ('TP305', 'CART_AUXOFF'), ('TP306', 'TC_OUT2'), ('TP307', '5V_PRE'), ('TP308', 'SNES_5V_CART'),
           ('TP309', 'USB_AUXOFF'), ('TP310', 'ILM_U309')]
    for i, (ref, net) in enumerate(tps):
        place(ref, 'Connector:TestPoint', net, 30.48 + 17.78 * i, 480.06, {'1': net}, 'TestPoint:TestPoint_Pad_D1.0mm')
    # ERC origin flags: SYS_VIN is fed only by passive-typed eFuse OUT pins; the three bucks feed their
    # rails through inductors; HOST_3V3 arrives on passive N64 edge contacts. They mark intended power
    # origins for ERC, not supplies.
    for i, net in enumerate(['SYS_VIN', 'FPGA_1V1', 'FPGA_2V5', 'FPGA_3V3', 'HOST_3V3']):
        place(f'#FLG{301 + i}', 'power:PWR_FLAG', 'PWR_FLAG', 238.76 + 17.78 * i, 480.06, {'1': net})

    # --- Hierarchical ports --------------------------------------------------
    for i, (name, shape) in enumerate(PORTS):
        x, y = 640.08, 330.2 + 5.08 * i
        parts.append(f'(hierarchical_label {q(name)} (shape {shape}) (at {g(x)} {g(y)} 180) '
                     f'(effects (font (size 1.27 1.27)) (justify right)) (uuid {q(uid("hl:" + name))}))')
        parts.append(f'(wire (pts (xy {g(x)} {g(y)}) (xy {g(x + 7.62)} {g(y)})) (stroke (width 0) (type default)) '
                     f'(uuid {q(uid("pw:" + name))}))')
        parts.append(f'(label {q(name)} (at {g(x + 7.62)} {g(y)} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) '
                     f'(uuid {q(uid("pl:" + name))}))')

    notes = [
        txt('SN64 POWER - source selection, system regulator, FPGA rails, cartridge eFuse, interface rail, monitors', 20.32, 17.78, 2.54),
        txt('Implements docs/design/power-architecture.md; math and sources in docs/design/power-schematic.md. HOST_12V is not used on this sheet.\n'
            'Priority power mux (TI SLVSFC9C Figure 8-14): U302 (USB, priority) AUXOFF -> Q304 pulls U303 (HOST_3V3, auxiliary) EN/UVLO low.\n'
            'Both eFuses have true reverse-current blocking; no source is ever directly paralleled onto SYS_VIN.',
            20.32, 25.4),
        txt('USB permission (default off): U302 enables only when TUSB320 OUT1 is low (1.5 A or 3 A advertised) AND USB_3V3 is present.\n'
            'TUSB320: PORT=GND (UFP), ADDR open (GPIO mode), EN_N=GND, VDD=USB_3V3 (power register PWR-L06). The USB sheet 5.1k Rd must be DNP.',
            20.32, 38.1),
        txt('SYSTEM REGULATOR: U304 TPS63070 buck-boost (forced PWM, +/-1% FB), SYS_VIN 2.7-6 V -> 5V_PRE 5.00 V. PG_5V enables the three TLV62569 bucks.\n'
            'ECP5: VCCIO8 must be valid before VCC/VCCAUX reach POR, or PROGRAMN/INITN held low (FPGA-DS-02012 3.4 sec. 3.5):\n'
            'fpga_rails_ok gates PROGRAMN on the FPGA sheet (its U307); board_reset_n (U316) releases 12-28 ms after all FPGA rails are in window.',
            20.32, 139.7),
        txt('CARTRIDGE 5 V: U309 TPS259470L, EN/UVLO default low (Q306 clamp until cart_5v_enable), UVLO 4.64 V / OVLO 5.48 V rising,\n'
            'ILIM 1.00 A (PROV), dVdt 680 pF (PROV), ITIMER 1.2 nF. Q307 + R328 470R discharge while inhibited (<=12 mA into an energized rail).\n'
            'INTERFACE_3V3: U308 TPS22918, ON default low (R340 1k), CT 470 pF, QOD via R341 100R.',
            20.32, 152.4),
        txt('MONITORS (all powered from FPGA_3V3, outputs pulled up to FPGA_3V3 = 3.3 V-safe; supply loss reads NOT OK):\n'
            'U310 SYS_VIN -> host_3v3_ok | U311-U313 FPGA rails -> fpga_rails_ok | U314 SNES_5V_CART (socket side) -> cart_5v_ok |\n'
            'U315 INTERFACE_3V3 -> iface_rail_ok | U309 FLT (10k to FPGA_3V3) -> efuse_fault_n | U317 TMP302A + Q308 -> overtemp (1 = hot or sensor dead).',
            20.32, 241.3),
        txt('DRAFT 0.1-power: schematic candidate only. No PCB, no measured load. Values marked PROV depend on unmeasured cartridge and FPGA current.\n'
            'Footprints for U302/U303/U309 (RPW0010A), U304 (RNM0015A) and L301 (PNR4020) are drawn from the manufacturer land patterns by tools/make_power_footprints.py; L302-L304 use KiCad Inductor_SMD:L_Changjiang_FNR4030S, checked against the Changjiang datasheet. Unbuilt.',
            20.32, 518.16)]
    contents = (f'(kicad_sch (version 20250114) (generator "sn64_power_authoring") (uuid {q(uid("page"))}) (paper "A1") '
                f'(title_block (title "SN 64 - Power") (date "2026-09-29") (rev "0.1-power") (company "SN 64") '
                f'(comment 1 "DESIGN DRAFT - NOT FOR MANUFACTURE"))\n(lib_symbols\n'
                + '\n'.join(dump(s) for s in libs.values()) + ')\n' + '\n'.join(parts + notes)
                + f'\n(sheet_instances (path {q("/" + root_uuid + "/" + sheet_uuid)} (page "4"))) (embedded_fonts no))')
    return contents, libs, fps, parts, sheet_uuid


def attach(project, sheet_uuid):
    """Append the power sheet symbol to <project>/sn64.kicad_sch and the SN64_POWER lib entry."""
    rootf = project / 'sn64.kicad_sch'
    original = rootf.read_text(encoding='utf-8')
    if sheet_uuid in original:
        print('Power sheet already attached in', rootf)
        return
    root_labels = {'GND', 'HOST_3V3', 'SNES_5V_CART', 'INTERFACE_3V3', 'USB_VBUS', 'USB_3V3', 'USB_CC1', 'USB_CC2'}
    sx, sy, w = 431.8, 38.1, 30.48
    pins, labels = [], []
    for i, (name, shape) in enumerate(PORTS):
        py = sy + 5.08 + 5.08 * i
        pins.append(f'(pin {q(name)} {shape} (at {g(sx)} {g(py)} 180) (effects (font (size 1.27 1.27)) (justify left)) '
                    f'(uuid {q(uid("root-pin:" + name))}))')
        if name in root_labels:
            labels.append(f'(label {q(name)} (at {g(sx)} {g(py)} 180) (effects (font (size 1.016 1.016)) (justify right bottom)) '
                          f'(uuid {q(uid("root-label:" + name))}))')
        else:
            # FPGA / A-V side pins: no root net until those sheets exist.
            labels.append(f'(no_connect (at {g(sx)} {g(py)}) (uuid {q(uid("root-nc:" + name))}))')
    h = round(5.08 * (len(PORTS) + 1), 2)
    block = (f'(sheet (at {g(sx)} {g(sy)}) (size {g(w)} {g(h)}) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0)) '
             f'(uuid {q(sheet_uuid)}) '
             + prop('Sheetname', SHEET_NAME, sx, sy - 1.27, justify='left bottom')
             + prop('Sheetfile', SHEET_FILE, sx, sy + h + 1.27, justify='left top')
             + ' ' + ' '.join(pins)
             + f' (instances (project "sn64" (path {q("/" + str(get(parse_text(original), "uuid")[1]))} (page "4")))))\n'
             + '\n'.join(labels))
    save(rootf, (original.rstrip()[:-1] + '\n' + block + '\n)').rstrip())
    table = parse(project / 'sym-lib-table')
    table[:] = [e for e in table if not (isinstance(e, list) and e and e[0] == 'lib' and get(e, 'name')[1] == LIB)]
    table.append(['lib', ['name', Quoted(LIB)], ['type', Quoted('KiCad')], ['uri', Quoted('${KIPRJMOD}/libraries/' + LIB + '.kicad_sym')],
                  ['options', Quoted('')], ['descr', Quoted('Power sheet draft; see libraries/power-provenance.json')]])
    save(project / 'sym-lib-table', dump(table))
    print('Attached power sheet to', rootf)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--kicad-share', type=Path, required=True)
    ap.add_argument('--datasheets', type=Path, help='directory holding the downloaded PDFs (hashes recorded)')
    ap.add_argument('--project-dir', type=Path, default=TOOLS.parent)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--attach', action='store_true', help='also attach the sheet to --project-dir root (copy/integration only)')
    ap.add_argument('--attach-only', action='store_true', help='only attach an already written sheet')
    a = ap.parse_args()
    project = a.project_dir.resolve()
    root_uuid = str(get(parse(project / 'sn64.kicad_sch'), 'uuid')[1])
    if a.attach_only:
        attach(project, uid('power-sheet'))
        return
    dest = project / SHEET_FILE
    if dest.exists() and not a.force:
        ap.error('power.kicad_sch exists; edit it in KiCad, or use --force to replace the initial draft')
    contents, libs, fps, parts, sheet_uuid = build(a, root_uuid)
    save(dest, contents)
    own = [copy.deepcopy(s) for k, s in libs.items() if k.startswith(LIB + ':')]
    for s in own:
        s[1] = Quoted(str(s[1]).split(':', 1)[1])
    save(project / 'libraries' / f'{LIB}.kicad_sym',
         '(kicad_symbol_lib (version 20250114) (generator "sn64_power_authoring")\n' + '\n'.join(dump(s) for s in own) + ')')

    sheets = [('tps25947', 'SLVSFC9C, revised May 2026'), ('tps63070', 'SLVSC58B, revised March 2019'),
              ('tps3700', 'SBVS187G, revised February 2019'), ('tps22918', 'SLVSD76C, revised July 2017'),
              ('tmp302', 'SBOS488E, revised December 2018'), ('tusb320', 'SLLSEN9F, revised March 2022'),
              ('tlv62569', 'SLVSDG1C, revised October 2017'), ('tps3808', 'SBVS050N, revised August 2026')]
    ds = {}
    for name, rev in sheets:
        rec = {'url': TI + name + '.pdf', 'revision': rev}
        if a.datasheets and (a.datasheets / f'{name}.pdf').exists():
            rec['sha256_of_downloaded_copy'] = hashlib.sha256((a.datasheets / f'{name}.pdf').read_bytes()).hexdigest()
        ds[name] = rec
    extra = {'ecp5_ds.pdf': ('https://www.latticesemi.com/view_document?document_id=50461', 'FPGA-DS-02012-3.4'),
             'bss138.pdf': ('https://assets.nexperia.com/documents/data-sheet/BSS138BK.pdf', 'BSS138BK Rev. 1, 4 August 2011'),
             'ulx3s_power.sch': ('https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/power.sch',
                                 'ULX3S rev 1.0.8 power sheet at commit 6a92cec (MIT)')}
    for f, (url, rev) in extra.items():
        rec = {'url': url, 'revision': rev}
        if a.datasheets and (a.datasheets / f).exists():
            rec['sha256_of_downloaded_copy'] = hashlib.sha256((a.datasheets / f).read_bytes()).hexdigest()
        ds[f.rsplit('.', 1)[0]] = rec
    drawn = {'TPS259470LRPW': (TPS25947_PINS, 'tps25947', 'Figure 5-1 RPW 10-pin QFN and Table 5-1'),
             'TPS63070RNM': (TPS63070_PINS, 'tps63070', 'Pin Functions table (pdftotext -raw re-read)'),
             'TPS3700DDC': (TPS3700_PINS, 'tps3700', 'DDC (SOT) top view and Pin Functions'),
             'TPS22918DBV': (TPS22918_PINS, 'tps22918', 'DBV 6-pin SOT-23 top view and Pin Functions'),
             'TMP302DRL': (TMP302_PINS, 'tmp302', 'DRL 6-pin SOT top view and Pin Functions')}
    provenance = {
        'schema_version': 1, 'recorded_date': '2026-09-29',
        'scope': 'Power child-sheet symbols; schematic draft only, not a manufacturing or functional-validation release.',
        'tool_version': 'KiCad 10.0.6',
        'drawn_symbols': {k: {'library': f'libraries/{LIB}.kicad_sym', 'source': ds[src], 'source_section': sec,
                              'pins': {p[0]: [p[1], p[2]] for p in pins}} for k, (pins, src, sec) in drawn.items()},
        'pin_type_note': 'eFuse OUT and load-switch VOUT drawn passive (switch outputs; two eFuses share SYS_VIN). '
                         'TPS63070 pin 8 drawn passive so the stacked VOUT pair has one power_out.',
        'installed_kicad_symbols_used_unmodified': sorted(k for k in libs if not k.startswith(LIB + ':')),
        'installed_kicad_footprints_referenced': sorted(fps),
        'footprints_pending': {'U302/U303/U309 TPS259470LRPWR': 'TI RPW0010A (VQFN-HR 2x2)',
                               'U304 TPS63070RNMR': 'TI RNM0015A (VQFN-HR 2.5x3)',
                               'L301 PNR4020-1R5M, L302-L304 FNR4030S2R2MT': 'vendor land patterns'},
        'datasheets': ds,
        'lcsc_parts_stock_2026_09_29': {
            'TPS259470LRPWR': ['C3662793', 2797], 'TUSB320IRWBR': ['C80170', 1628], 'TPS3700DDCR': ['C33002', 8920],
            'TPS63070RNMR': ['C109322', 25100], 'TLV62569DBVR': ['C141836', 246272], 'TPS22918DBVR': ['C131941', 18885],
            'TPS3808G01DBVR': ['C19653', 18100], 'TMP302ADRLR': ['C2877557', 39857], 'BSS138BK,215': ['C282529', 52253],
            'PNR4020-1R5M': ['C54620133', 7449], 'FNR4030S2R2MT': ['C167869', 67195]},
        'lcsc_source': 'pcbparts MCP jlc_get_part/jlc_search database query, 2026-09-29; re-check before ordering.',
        'licenses': 'KiCad library content: CC-BY-SA-4.0 with the KiCad library exception. Drawn symbols: SN64 project content; '
                    'pin data are facts from the cited TI datasheets. Buck topology follows ULX3S (MIT); no ULX3S files are copied.'}
    save(project / 'libraries' / 'power-provenance.json', json.dumps(provenance, indent=2))
    n_sym = len([p for p in parts if p.startswith('(symbol (lib_id')])
    print('Authored power sheet:', n_sym, 'symbols;', len(fps), 'installed footprints referenced ->', dest)
    if a.attach:
        attach(project, sheet_uuid)


if __name__ == '__main__':
    main()
