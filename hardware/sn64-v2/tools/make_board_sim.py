"""Turn the v2 board file's own connection list into a simulation of the board.

  "C:/Program Files/KiCad/10.0/bin/python.exe" hardware/sn64-v2/tools/export_board_nets.py
  python hardware/sn64-v2/tools/make_board_sim.py

Reads build/board-sim/board-nets.json (every pad's net, from sn64-v2.kicad_pcb), the FPGA
constraints (port -> ball), the top level's ports and the maker's FPGA pin table, and writes
  build/board-sim/sn64_board_netlist.sv   module sn64_board: one net per board net, the real FPGA
                                          top level (sn64_board_top) on its balls, a model of every
                                          part that takes part in the logic on its pads
                                          (fpga/tests/board_models.sv), the board's resistors, and
                                          the two connectors as pins by number
  build/board-sim/board_pins.svh          which connector pin carries which signal, from the two
                                          connector tables v1 drew from other people's working boards
  build/board-sim/board-sim.json          what was made of every part, for the write-up
A bench (fpga/tests/tb_board_game.sv) plugs a cartridge into socket pins by their numbers and an
N64 onto the edge fingers by theirs. If the board wires a signal to the wrong pin, the cartridge
and the FPGA no longer meet, and the game does not run.

What becomes what:
  nets        ground and the fixed supplies are constants; the switched cartridge supply follows
              the model of the cartridge switch; every other net is a net
  resistors   to a supply: a pull-up or pull-down (to the switched supply: one that follows it);
              up to 100 ohm between two signals: the two nets are one; from an FPGA output to a
              signal: a pull to that output's level; dividers and the sound network: worked out
              here and handed to the part model as numbers
  FPGA        sn64_board_top, each port on the net of its ball; the pull the constraints give a
              pad is added where the board has none; the flash clock leaves through the USRMCLK
              stand-in; a comparator input takes the net of its ball and of the ball the maker's
              table pairs with it
  converter   the voltage on each input pin is worked out from the resistors on that pin's net
  left out    capacitors on supplies, inductors, the converters that make the supplies, the ESD
              part, the USB socket and its loader chip (no cable: the chip has no supply and its
              pins are open; the JTAG port it drives is no part of the logic), test points,
              mounting holes
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
ROOT = V2.parents[1]
sys.path.insert(0, str(HERE))
from verify_board_wiring import read_lpf, read_map, CONFIG_BALLS      # noqa: E402

# Supplies that are up whenever the board is in a console, in volts. No USB cable in this simulation.
RAIL_VOLTS = {'GND': 0.0, 'FPGA_3V3': 3.3, 'FPGA_2V5': 2.5, 'FPGA_1V1': 1.1, '5V_SYS': 5.0, 'SYS_VIN': 3.3, 'HOST_3V3': 3.3,
              'USB_VBUS': 0.0}
# What the netlist has to know about the inside of the FPGA: where the flash clock leaves user
# logic, the clock the sound comparators are sampled with, and when the FPGA drives the data lines.
USRMCLK_PATH = 'U1.top.endpoint.g_rom_flash.u_flash.u_mclk.g_usrmclk.u_usrmclk.pin'
SD_SAMPLE_CLOCK = 'U1.clk_host'
DATA_DRIVE = 'U1.data_dir'
T245_PINS = [1, 2, 3, 5, 6, 8, 9, 11, 12, 13, 14, 16, 17, 19, 20, 22, 23, 24, 25, 26, 27, 29, 30, 32, 33, 35, 36, 37, 38,
             40, 41, 43, 44, 46, 47, 48]
T245_B = {1: [2, 3, 5, 6, 8, 9, 11, 12], 2: [13, 14, 16, 17, 19, 20, 22, 23]}
T245_A = {1: [47, 46, 44, 43, 41, 40, 38, 37], 2: [36, 35, 33, 32, 30, 29, 27, 26]}
LVC07_PINS = [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13]
LVC07_OUT_IN = {2: 1, 4: 3, 6: 5, 8: 9, 10: 11, 12: 13}
ADC_INPUT_PINS = [15, 16, 1, 2, 3, 4, 5, 6]                # TLA2528 AIN0..AIN7


def ohms(value):
    m = re.search(r'(\d[\d.]*)\s*([kKM]?)(?![\w.])', value)
    return float(m.group(1)) * {'': 1.0, 'k': 1e3, 'K': 1e3, 'M': 1e6}[m.group(2)] if m else None


def farads(value):
    m = re.search(r'(\d[\d.]*)\s*([pnu])F', value)
    return float(m.group(1)) * {'p': 1e-12, 'n': 1e-9, 'u': 1e-6}[m.group(2)] if m else None


def read_port_dirs(path):
    """{port bit: direction} of the top module."""
    text = re.sub(r'//.*', '', path.read_text(encoding='utf-8'))
    body = re.search(r'module\s+sn64_board_top\s*\((.*?)\);', text, re.S).group(1)
    out, width, direction = {}, None, None
    for part in body.split(','):
        part = part.strip()
        m = re.match(r'(input|output|inout)\s+(?:wire|reg|logic)?\s*(\[(\d+):(\d+)\])?\s*(\w+)$', part)
        if m:
            direction = m.group(1)
            width = (int(m.group(3)), int(m.group(4))) if m.group(2) else None
            name = m.group(5)
        else:
            name = part
        if not re.match(r'^\w+$', name):
            raise SystemExit('cannot read the port list near: ' + part)
        for bit in (['%s[%d]' % (name, i) for i in range(min(width), max(width) + 1)] if width else [name]):
            out[bit] = direction
    return out


def read_pairs(path):
    """{true ball: complement ball} of the CABGA381 package, from the maker's pin table."""
    rows = [r for r in csv.reader(path.open(encoding='utf-8-sig', newline='')) if len(r) > 9]
    head = next(i for i, r in enumerate(rows) if r[0] == 'PAD')
    col = rows[head].index('CABGA381')
    ball = {r[1]: r[col] for r in rows[head + 1:] if r[col] not in ('-', '')}
    out = {}
    for r in rows[head + 1:]:
        m = re.match(r'True_OF_(\w+)$', r[4])
        if m and r[col] not in ('-', '') and m.group(1) in ball:
            out[r[col]] = ball[m.group(1)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--nets', type=Path, default=ROOT / 'build/board-sim/board-nets.json')
    ap.add_argument('--lattice-csv', type=Path, default=ROOT / 'build/fpga-sheet/datasheets/ECP5U-85-pinout.csv')
    ap.add_argument('--out', type=Path, default=ROOT / 'build/board-sim')
    ap.add_argument('--mutate', action='append', default=[], metavar='REF.PAD=NET',
                    help='put a pad on another net before the netlist is written: a deliberate wiring mistake that '
                         'the game run must refuse (give another --out)')
    args = ap.parse_args()
    raw = args.nets.read_bytes()
    data = json.loads(raw)
    comps = data['components']
    for m in args.mutate:
        where, new_net = m.split('=', 1)
        ref, pad = where.split('.', 1)
        if pad not in comps[ref]['pads']:
            sys.exit('--mutate: %s has no pad %s' % (ref, pad))
        print('MISTAKE put in: %s pad %s on %s instead of %s' % (ref, pad, new_net, comps[ref]['pads'][pad]))
        comps[ref]['pads'][pad] = new_net
    lpf_path = ROOT / 'fpga/constraints/sn64_board.lpf'
    lpf_text = lpf_path.read_text(encoding='utf-8')
    lpf = read_lpf(lpf_path)
    pad_pull = dict(re.findall(r'IOBUF PORT "([^"]+)" IO_TYPE=\w+ PULLMODE=(\w+);', lpf_text))
    lvds_ports = re.findall(r'IOBUF PORT "([^"]+)" IO_TYPE=LVDS;', lpf_text)
    dirs = read_port_dirs(ROOT / 'fpga/rtl/sn64_board_top.sv')
    if args.lattice_csv.exists():
        pairs, pair_source = read_pairs(args.lattice_csv), 'the maker\'s pin table'
    else:                                                # the project's own pin map, made from that table
        rows = list(csv.DictReader((l for l in (V2 / 'interfaces/fpga-pin-map.csv').open(encoding='utf-8') if not l.startswith('#'))))
        byf = {r['function']: r['ball'] for r in rows}
        pairs = {r['ball']: byf[r['function'][:-1] + {'A': 'B', 'C': 'D'}[r['function'][-1]]] for r in rows if r['iotype'] == 'LVDS'}
        pair_source = 'the project\'s pin map (the maker\'s table is not on this PC)'

    def is_open(net):
        return not net or net.startswith('unconnected')

    def by_value(text):
        return [r for r, c in comps.items() if text in c['value']]

    u1 = by_value('LFE5U')[0]
    switch, adc = by_value('TPS2553')[0], by_value('TLA2528')[0]
    cart_rail = comps[switch]['pads']['6']
    if RAIL_VOLTS.get(comps[switch]['pads']['1']) != 5.0:
        sys.exit('%s pin 1 is not on the 5 V supply' % switch)
    supplies = set(RAIL_VOLTS) | {cart_rail}
    resistors = {r: (ohms(c['value']), list(c['pads'].values())) for r, c in comps.items()
                 if r.startswith('R') and len(c['pads']) == 2}
    capacitors = {r: (farads(c['value']), list(c['pads'].values())) for r, c in comps.items()
                  if r.startswith('C') and len(c['pads']) == 2}
    for r, (v, _) in list(resistors.items()) + list(capacitors.items()):
        if v is None:
            sys.exit('cannot read the value of %s: %s' % (r, comps[r]['value']))
    used = {}                                            # resistor -> what it became

    def r_on(net):
        """Resistors on a net: [(ref, ohms, the net on its other end)]."""
        return [(r, v, n[1] if n[0] == net else n[0]) for r, (v, n) in sorted(resistors.items()) if net in n]

    fpga_net = {p: comps[u1]['pads'].get(ball) for p, ball in lpf.items()}
    out_nets = {n for p, n in fpga_net.items() if dirs.get(p) == 'output'}

    # ---- nets joined by a small series resistor are one net
    parent = {}

    def find(n):
        while parent.get(n, n) != n:
            n = parent[n]
        return n

    series = []
    for ref, (v, (a, b)) in sorted(resistors.items()):
        if v <= 100.0 and a not in supplies and b not in supplies and not is_open(a) and not is_open(b):
            parent[find(b)] = find(a)
            series.append('%s %s: %s = %s' % (ref, comps[ref]['value'], a, b))
            used[ref] = 'in series, the two nets are one'

    # ---- names
    conn = {}                                           # net -> connector pin expression
    for jref, bus in (('J1', 'j1'), ('J2', 'j2')):
        for pad, net in comps[jref]['pads'].items():
            if not is_open(net) and net not in supplies:
                conn.setdefault(find(net), '%s[%s]' % (bus, pad))
    declared = {}

    def ident(net):
        """The expression that stands for a board net."""
        if is_open(net):
            return None
        if net in RAIL_VOLTS:
            return 'rail_hi' if RAIL_VOLTS[net] > 0.0 else 'rail_lo'
        if net == cart_rail:
            return 'cart_rail_on'
        c = find(net)
        if c in conn:
            return conn[c]
        name = 'n_' + re.sub(r'\W', '_', c)
        declared[name] = c
        return name

    def pins(ref, numbers):
        return ', '.join('.p%d(%s)' % (n, ident(comps[ref]['pads'].get(str(n))) or '') for n in numbers)

    body, report = [], {'parts': {}, 'left_out': {}}

    # ---- the cartridge's sound input: what is on each comparator pin
    analog = {}
    for port in lvds_ports:
        ball = lpf[port]
        nets = {'true': comps[u1]['pads'][ball], 'comp': comps[u1]['pads'][pairs[ball]]}
        fb_side = v_ref = tau = fb_net = None
        for side, net in nets.items():
            rs, cs = r_on(net), [(c, v, n) for c, (v, n) in capacitors.items() if net in n]
            feed = [(r, v, o) for r, v, o in rs if o in out_nets]
            if feed and len(rs) == 1:                    # the feedback output through one resistor, a capacitor to ground
                cap = [v for _, v, n in cs if 'GND' in n]
                if len(cap) != 1:
                    sys.exit('%s: the feedback pin has no single capacitor to ground' % port)
                fb_side, fb_net, tau = side, feed[0][2], feed[0][1] * cap[0]
                used[feed[0][0]] = 'sound input %s: feedback resistor' % port
            else:                                        # the bias through a resistor, the cartridge through a resistor and a capacitor
                bias = None
                for r, v, o in rs:
                    legs = [(rr, vv, oo) for rr, vv, oo in r_on(o) if rr != r]
                    to_supply = [(rr, vv, oo) for rr, vv, oo in legs if oo in RAIL_VOLTS]
                    if len(to_supply) >= 2:              # a divider between supplies: the bias
                        g = sum(1.0 / vv for _, vv, _ in to_supply)
                        bias = sum(RAIL_VOLTS[oo] / vv for _, vv, oo in to_supply) / g
                        for rr, _, _ in to_supply:
                            used[rr] = 'sound input: bias divider'
                    used[r] = 'sound input %s: into the reference pin' % port
                if bias is None:
                    sys.exit('%s: no bias divider on the reference pin' % port)
                v_ref = bias
        if fb_side is None or v_ref is None:
            sys.exit('%s: cannot make out the sound input network' % port)
        analog[port] = (fb_side, fb_net, tau, v_ref)
        report['parts']['sound input ' + port] = {'true ball': ball, 'complement ball': pairs[ball], 'pairs from': pair_source,
                                                  'feedback on the': fb_side + ' pin', 'time constant, us': round(tau * 1e6, 3),
                                                  'reference, V': round(v_ref, 4)}

    # ---- the FPGA
    buses = {}
    for p in dirs:
        m = re.match(r'(\w+)\[(\d+)\]$', p)
        buses.setdefault(m.group(1) if m else p, []).append((int(m.group(2)) if m else None, p))
    con = []
    for name, bits in buses.items():
        if name in analog:
            con.append('.%s(sd_%s)' % (name, name))
            continue
        exprs = []
        for idx, p in sorted(bits, key=lambda t: -1 if t[0] is None else -t[0]):
            e = ident(fpga_net.get(p))
            if e is None:
                sys.exit('port %s: ball %s is on no net' % (p, lpf.get(p)))
            exprs.append(e)
        con.append('.%s(%s)' % (name, exprs[0] if bits[0][0] is None else '{' + ', '.join(exprs) + '}'))
    for port, (fb_side, fb_net, tau, v_ref) in analog.items():
        body.append('    wire sd_%s;\n    bm_sd_input #(.TAU_NS(%.3f), .VDD(3.3), .V_REF(%.4f), .FB_ON_COMP(1\'b%d)) in_%s (.clk(%s), .fb(%s), .cmp(sd_%s));' % (
            port, tau * 1e9, v_ref, fb_side == 'comp', port, SD_SAMPLE_CLOCK, ident(fb_net), port))
    body.append('    sn64_board_top %s (\n        %s);' % (u1, ',\n        '.join(con)))
    cclk = ident(comps[u1]['pads'][CONFIG_BALLS['cclk']])
    body.append('    assign %s = %s;      // the configuration clock ball, driven by user logic through USRMCLK' % (cclk, USRMCLK_PATH))

    # ---- the parts
    j2_drive, j2_pull_low, a_conflict, rule = {}, {}, [], []
    data_nets = {find(fpga_net[p]): p for p in dirs if p.startswith('cart_data[')}
    for ref, comp in sorted(comps.items()):
        v, pads = comp['value'], comp['pads']
        if 'ALVC164245' in v:
            if pads['31'] != pads['42'] or pads['7'] != pads['18']:
                sys.exit('%s: the two pins of a supply are on different nets' % ref)
            body.append('    bm_sn74alvc164245 %s (%s,\n        .vcca_on(%s), .vccb_on(%s));' % (
                ref, pins(ref, T245_PINS), ident(pads['31']), ident(pads['7'])))
            for byte in (1, 2):
                for b in T245_B[byte]:
                    e = ident(pads.get(str(b)))
                    if e and e.startswith('j2['):
                        j2_drive.setdefault(e, []).append('%s.ab%d' % (ref, byte))
                if any(find(pads.get(str(a), '')) in data_nets for a in T245_A[byte]):
                    a_conflict.append('(%s.ba%d & %s)' % (ref, byte, DATA_DRIVE))
            rule.append('%s.rule_broken' % ref)
            report['parts'][ref] = 'SN74ALVC164245: A side supply %s, B side supply %s' % (pads['31'], pads['7'])
        elif 'LVC07' in v:
            body.append('    bm_sn74lvc07a %s (%s, .vcc_on(%s));' % (ref, pins(ref, LVC07_PINS), ident(pads['14'])))
            for o in LVC07_OUT_IN:
                e = ident(pads.get(str(o)))
                if e and e.startswith('j2['):
                    j2_pull_low.setdefault(e, []).append('%s.y%d' % (ref, o))
            report['parts'][ref] = 'SN74LVC07A: supply %s' % pads['14']
        elif 'W25Q128' in v:
            body.append('    bm_w25q128 %s (%s);' % (ref, pins(ref, [1, 2, 3, 5, 6, 7])))
            body.append('    task automatic flash_poke(input [23:0] a, input [7:0] v); %s.chip.mem[a] = v; endtask      // the bench fills the flash' % ref)
            report['parts'][ref] = 'flash'
        elif ref.startswith('X'):
            body.append('    bm_osc_27mhz %s (%s);' % (ref, pins(ref, [1, 3])))
            report['parts'][ref] = 'oscillator'
        elif 'TPS3808' in v:
            body.append('    bm_tps3808 %s (%s);' % (ref, pins(ref, [1])))
            report['parts'][ref] = 'reset supervisor'
        elif 'FT231X' in v:
            # The USB loader chip takes its supply from the cable, and there is none here: its pins are
            # open. What it drives, the FPGA's JTAG port, is no port of the logic.
            if RAIL_VOLTS.get(pads['15']) != 0.0:
                sys.exit('%s: the loader chip is not on the USB supply (%s); it would need a model' % (ref, pads['15']))
            report['left_out'][ref] = v + ' (USB loader chip: no cable, so no supply; its pins are open)'
        elif ref.startswith('U') and ref not in (u1, switch, adc):
            report['left_out'][ref] = v + ' (makes or guards a supply)'

    # ---- the cartridge switch, its rail and the converter
    def pin_volts(net):
        """What the board puts on a converter input: volts, or 'rail' with the divider's two resistors."""
        if net in RAIL_VOLTS:
            return RAIL_VOLTS[net], None
        rs = r_on(net) + [(r, ohms(comps[r]['value']), [n for n in comps[r]['pads'].values() if n != net][0])
                          for r in comps if r.startswith('RT') and net in comps[r]['pads'].values()]
        rs = list({r: (r, v, o) for r, v, o in rs}.values())
        if not rs or any(o not in supplies for _, _, o in rs):
            sys.exit('converter input on %s: not fed by resistors from supplies alone' % net)
        for r, _, _ in rs:
            used[r] = 'divider on the converter input %s' % net
        top = [(r, v) for r, v, o in rs if o == cart_rail]
        if top:
            bot = [v for r, v, o in rs if o == 'GND']
            if len(top) != 1 or len(bot) != 1 or len(rs) != 2:
                sys.exit('converter input on %s: not a plain divider from the cartridge supply' % net)
            return 'rail', (top[0][1], bot[0])
        g = sum(1.0 / v for _, v, _ in rs)
        return sum(RAIL_VOLTS[o] / v for _, v, o in rs) / g, None

    # the converter's address: what hangs on its ADDR pin (TI SBAS961A table 2; R1 to DECAP, R2 to ground)
    addr_net, decap = comps[adc]['pads'].get('11'), comps[adc]['pads'].get('8')
    if is_open(addr_net):
        i2c_addr = 0x10
    else:
        legs = sorted((o, v) for _, v, o in r_on(addr_net))
        table = {('GND', 11e3): 0x11, ('GND', 33e3): 0x12, ('GND', 100e3): 0x13, (decap, 0.0): 0x17, (decap, 11e3): 0x16,
                 (decap, 33e3): 0x15, (decap, 100e3): 0x14}
        i2c_addr = 0x17 if addr_net == decap else table.get(legs[0], -1) if len(legs) == 1 else -1
    report['parts'].setdefault(adc, {})['ADDR pin'] = '%s: %s' % (addr_net or 'open', ('address 0x%02X' % i2c_addr) if i2c_addr >= 0 else
                                                                 'not a setting of the data sheet: the model answers at no address')
    params, divider = ['.I2C_ADDR(%d)' % i2c_addr], None
    for pin in ADC_INPUT_PINS:
        volts, div = pin_volts(comps[adc]['pads'][str(pin)])
        if volts == 'rail':
            divider = div
            params.append('.V_P%d(-1.0)' % pin)
        else:
            params.append('.V_P%d(%.4f)' % (pin, volts))
        report['parts'].setdefault(adc, {})['pin %d' % pin] = '%s: %s' % (comps[adc]['pads'][str(pin)], volts if volts == 'rail' else '%.3f V' % volts)
    if divider is None:
        sys.exit('no converter input carries the cartridge supply')
    c_rail = sum(v for c, (v, n) in capacitors.items() if cart_rail in n and 'GND' in n)
    loads = []                                           # pull-ups to the switched supply whose line an open-drain output can hold low
    for r, v, o in r_on(cart_rail):
        e = ident(o)
        if e in j2_pull_low:
            loads.append('((%s) ? %.6e : 0.0)' % (' | '.join(j2_pull_low[e]), 1.0 / v))
    body.append('    // the cartridge switch %s, the rail it feeds (%.1f uF on the board) and the converter %s that watches the supplies' % (switch, c_rail * 1e6, adc))
    body.append('    real rail_g_load;\n    always_comb rail_g_load = %s;' % (' + '.join(loads) or '0.0'))
    body.append('    bm_cart_rail #(.C_BOARD(%.4e), .R_TOP(%.1f), .R_BOT(%.1f),\n        %s) rail (\n        .en(%s), .fault_n(%s), .scl(%s), .sda(%s),\n'
                '        .g_load(rail_g_load), .cartridge(cartridge), .rail_on(cart_rail_on), .rail_mv(cart_rail_mv));' % (
                    c_rail, divider[0], divider[1], ', '.join(params), ident(comps[switch]['pads']['3']), ident(comps[switch]['pads']['4']),
                    ident(comps[adc]['pads']['13']), ident(comps[adc]['pads']['14'])))
    report['parts'][switch] = 'cartridge switch: in %s, out %s, %.1f uF on the rail' % (comps[switch]['pads']['1'], cart_rail, c_rail * 1e6)

    # ---- the status LED: lit when its anode side is high and its cathode side is low
    led = by_value('LED')
    led_expr = "1'b0"
    if led:
        def side(net):
            if net in supplies:
                return ident(net)
            for r, v, o in r_on(net):
                used[r] = 'LED series resistor'
                return ident(o)
            return ident(net)
        led_expr = '%s & !%s' % (side(comps[led[0]]['pads']['2']), side(comps[led[0]]['pads']['1']))      # pad 2 anode, pad 1 cathode
        report['parts'][led[0]] = 'LED: lit when ' + led_expr
    body.append('    assign led = %s;' % led_expr)

    # ---- the resistors that are left: pulls
    pull_lines, pulled = [], set()
    for ref, (v, (a, b)) in sorted(resistors.items()):
        if ref in used:
            continue
        ends = [n for n in (a, b) if n in supplies]
        if len(ends) == 2 or is_open(a) or is_open(b):
            used[ref] = 'between supplies or open: not part of the logic'
            continue
        if len(ends) == 1:
            sig = b if a == ends[0] else a
            e = ident(sig)
            if not (re.search(r'(?<!\w)%s(?!\w)' % re.escape(e), '\n'.join(body))):
                declared.pop(e, None)
                used[ref] = 'on a net no modelled part uses (%s)' % sig
                continue
            if ends[0] == cart_rail:
                pull_lines.append('    bm_pull_rail %s (.p(%s), .on(cart_rail_on));      // %s to %s' % (ref, e, comps[ref]['value'], ends[0]))
            else:
                pull_lines.append('    %s %s (.p(%s));      // %s to %s' % (
                    'bm_pullup' if RAIL_VOLTS[ends[0]] > 0.0 else 'bm_pulldown', ref, e, comps[ref]['value'], ends[0]))
            pulled.add(e)
            used[ref] = 'pull on %s to %s' % (sig, ends[0])
        elif (a in out_nets) != (b in out_nets):
            src, sig = (a, b) if a in out_nets else (b, a)
            pull_lines.append('    bm_pull_to %s (.p(%s), .level(%s));      // %s from the FPGA output %s' % (ref, ident(sig), ident(src), comps[ref]['value'], src))
            pulled.add(ident(sig))
            used[ref] = 'pull on %s to the level of %s' % (sig, src)
        else:
            report['left_out'][ref] = '%s between %s and %s' % (comps[ref]['value'], a, b)
    for p, mode in sorted(pad_pull.items()):
        if mode not in ('UP', 'DOWN') or p not in fpga_net:
            continue
        e = ident(fpga_net[p])
        if e in pulled:
            continue
        pulled.add(e)
        pull_lines.append('    %s pad_%s (.p(%s));      // the FPGA pad of %s (PULLMODE=%s in the constraints)' % (
            'bm_pullup' if mode == 'UP' else 'bm_pulldown', re.sub(r'\W', '_', p), e, p, mode))

    def vector(table, width):
        return '{' + ', '.join(' | '.join(table.get('j2[%d]' % i, ["1'b0"])) for i in range(width, 0, -1)) + '}'

    text = '\n'.join(body + pull_lines)
    wires = sorted(n for n in declared if re.search(r'(?<!\w)%s(?!\w)' % re.escape(n), text))
    sha = hashlib.sha256(raw).hexdigest()
    out = ['// GENERATED by hardware/sn64-v2/tools/make_board_sim.py: do not edit.'] + [
           '// WITH A DELIBERATE WIRING MISTAKE: ' + m for m in args.mutate] + [
           '// The SN64 v2 board as its board file connects it: %s, connection list SHA-256 %s.' % (data['board'], sha[:16]),
           '// %d nets, %d pulls, %d pairs of nets joined by a series resistor.' % (len(wires), len(pull_lines), len(series)),
           '`timescale 1ns/1fs',
           'module sn64_board (',
           '    inout  wire [50:1] j1,                 // N64 edge fingers, by number',
           '    inout  wire [62:1] j2,                 // SNES socket pins, by number',
           '    input  wire [1:0]  cartridge,          // for the rail model: 0 nothing in the socket, 1 a cartridge, 2 a cartridge back to front',
           '    output wire        cart_rail_on,       // the switched cartridge supply is up',
           '    output wire [15:0] cart_rail_mv,',
           '    output wire [62:1] j2_drive,           // the board drives this socket pin (a level shifter output that is on)',
           '    output wire [62:1] j2_pull_low,        // an open-drain output of the board holds this socket pin low',
           '    output wire        bus_a_conflict,     // the FPGA and a level shifter drive the same 3.3 V data line',
           '    output wire        shifter_rule_broken, // a level shifter byte is enabled while its 5 V side has no supply',
           '    output wire        led',
           ');',
           '    wire rail_hi = 1\'b1, rail_lo = 1\'b0;      // the fixed supplies and ground']
    out += ['    tri %s;' % n for n in wires]
    out += body
    out += ['    // ---- pulls'] + pull_lines
    out += ['    assign j2_drive = %s;' % vector(j2_drive, 62),
            '    assign j2_pull_low = %s;' % vector(j2_pull_low, 62),
            '    assign bus_a_conflict = %s;' % (' | '.join(a_conflict) or "1'b0"),
            '    assign shifter_rule_broken = %s;' % (' | '.join(rule) or "1'b0")]
    out += ['    // ---- joined by a series resistor: ' + '; '.join(series)]
    out.append('endmodule')
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'sn64_board_netlist.sv').write_text('\n'.join(out) + '\n', encoding='utf-8', newline='\n')

    # ---- the connectors' pin numbers by signal, from the tables of other people's working boards
    snes = read_map(ROOT / 'hardware/sn64/interfaces/snes-pin-map.csv')
    n64 = read_map(ROOT / 'hardware/sn64/interfaces/n64-pin-map.csv')

    def pin(table, signal):
        got = [int(p) for p, s in table.items() if s == signal]
        assert len(got) == 1, (signal, got)
        return got[0]

    h = ['// GENERATED by hardware/sn64-v2/tools/make_board_sim.py from hardware/sn64/interfaces/snes-pin-map.csv and n64-pin-map.csv.',
         '// Which pin of each connector carries which signal on a real console.',
         'localparam int J2_A [0:23] = \'{%s};' % ', '.join(str(pin(snes, 'A%d' % i)) for i in range(24)),
         'localparam int J2_D [0:7] = \'{%s};' % ', '.join(str(pin(snes, 'D%d' % i)) for i in range(8)),
         'localparam int J2_PA [0:7] = \'{%s};' % ', '.join(str(pin(snes, 'PA%d' % i)) for i in range(8))]
    for name, signal in (('RD', '/RD'), ('WR', '/WR'), ('PRD', '/PRD'), ('PWR', '/PWR'), ('ROMSEL', '/ROMSEL'), ('WRAMSEL', '/WRAMSEL'),
                         ('REFRESH', 'REFRESH'), ('PHI2', 'PHI2'), ('SYSTEM_CLK', 'SYSTEM_CLK'), ('IRQ', '/IRQ'), ('RESET', '/RESET'),
                         ('EXPAND', 'EXPAND'), ('CIC_DATA0', 'CIC_DATA0'), ('CIC_DATA1', 'CIC_DATA1'), ('CIC_CLK', 'CIC_CLK'),
                         ('CIC_SLAVE_RESET', 'CIC_SLAVE_RESET'), ('AUDIO_L', 'AUDIO_L_IN'), ('AUDIO_R', 'AUDIO_R_IN')):
        h.append('localparam int J2_%s = %d;' % (name, pin(snes, signal)))
    h.append('localparam int J1_AD [0:15] = \'{%s};' % ', '.join(str(pin(n64, 'AD%d' % i)) for i in range(16)))
    for name, signal in (('ALE_L', 'ALE_L'), ('ALE_H', 'ALE_H'), ('READ', '/READ'), ('WRITE', '/WRITE'), ('RESET', '/RESET'), ('NMI', '/NMI'),
                         ('INT', '/INT'), ('CIC_CLK', 'CIC_CLK'), ('CIC_DATA', 'CIC_DATA'), ('PIF_CLK', 'PIF_CLK'), ('JOYBUS', 'JOYBUS')):
        h.append('localparam int J1_%s = %d;' % (name, pin(n64, signal)))
    (args.out / 'board_pins.svh').write_text('\n'.join(h) + '\n', encoding='utf-8', newline='\n')

    report['resistors'] = {r: used.get(r, 'LEFT OUT') for r in sorted(resistors, key=lambda r: int(re.sub(r'\D', '', r)))}
    report['series'] = series
    report['nets'] = len(wires)
    report['connection_list_sha256'] = sha
    for ref, c in sorted(comps.items()):
        if ref[0] in 'LJHT' or ref.startswith('RT') or ref.startswith('C'):
            continue
        if ref.startswith('R') or ref in report['parts'] or ref in report['left_out'] or ref == u1:
            continue
        report['left_out'][ref] = c['value']
    (args.out / 'board-sim.json').write_text(json.dumps(report, indent=1), encoding='utf-8', newline='\n')
    print('%d nets, %d pulls, %d series joins; left out: %s' % (len(wires), len(pull_lines), len(series), ', '.join(sorted(report['left_out'])) or 'nothing'))
    print('sn64_board_netlist.sv, board_pins.svh, board-sim.json in %s' % args.out.as_posix())


if __name__ == '__main__':
    main()
