"""Trace every signal of the v2 board from the FPGA to the connector pin it belongs on.

  "C:/Program Files/KiCad/10.0/bin/python.exe" hardware/sn64-v2/tools/export_board_nets.py
  python hardware/sn64-v2/tools/verify_board_wiring.py [--negative]

What is compared with what:
  the board     build/board-sim/board-nets.json: every pad's net, read from sn64-v2.kicad_pcb
  the FPGA      fpga/constraints/sn64_board.lpf (port -> ball) and the ports of fpga/rtl/sn64_board_top.sv
  the schematic hardware/sn64-v2/validation/sn64-v2.xml
  the truth     the two connector tables of v1 (hardware/sn64/interfaces/snes-pin-map.csv from OpenSFC,
                sd2snes and Sanni; n64-pin-map.csv from SummerCart64 and the M64 schematics), the pin
                tables of the parts below (typed here from the makers' data sheets, not taken from
                the schematic generator), and the Lattice pin-out CSV when it is present

The checks follow the copper's names, not the generator's intentions: a port is right when its ball's
net reaches the connector pin that carries that signal on a real console, through a level-shifter
channel that points the right way and is switched by the right FPGA port. A check that cannot be
made (a file is missing) is reported as skipped, never as passed.

--negative: each of a list of deliberate wiring mistakes must be caught by at least one check.
Static check only: it says the board is wired as intended. It says nothing about voltages, timing,
footprints or whether the logic works; see docs/design/board-verification.md.
"""
import argparse
import copy
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
ROOT = V2.parents[1]

# ---- pin tables of the parts (data sheets) --------------------------------------------------
# SN74ALVC164245 (TI SCAS416), DGG package: two bytes, A port on VCCA, B port on VCCB.
# DIR high: A to B. /OE low: enabled.
T245 = {
    1: {'dir': '1', 'oe': '48', 'a': ['47', '46', '44', '43', '41', '40', '38', '37'], 'b': ['2', '3', '5', '6', '8', '9', '11', '12']},
    2: {'dir': '24', 'oe': '25', 'a': ['36', '35', '33', '32', '30', '29', '27', '26'], 'b': ['13', '14', '16', '17', '19', '20', '22', '23']},
}
T245_VCCB, T245_VCCA, T245_GND = ['7', '18'], ['31', '42'], ['4', '10', '15', '21', '28', '34', '39', '45']
# SN74LVC07A (TI SCAS595), PW package: six open-drain buffers, input -> output.
LVC07 = {'1': '2', '3': '4', '5': '6', '9': '8', '11': '10', '13': '12'}
# W25Q128JV (Winbond), SOIC-8.
FLASH = {'cs': '1', 'd1': '2', 'd2': '3', 'gnd': '4', 'd0': '5', 'clk': '6', 'd3': '7', 'vcc': '8'}
# ECP5 CABGA381 configuration balls (Lattice pin-out CSV, bank 8) and what must hang on them.
CONFIG_BALLS = {'cclk': 'U3', 'csspin': 'R2', 'd0': 'W2', 'd1': 'V2', 'd2': 'Y2', 'd3': 'W1',
                'done': 'Y3', 'initn': 'V3', 'programn': 'W3', 'cfg0': 'U4', 'cfg1': 'T4', 'cfg2': 'R4'}

# ---- what each FPGA port has to reach --------------------------------------------------------
SNES_OUT = ([('cart_address[%d]' % i, 'A%d' % i, 'ctl_oe_n') for i in range(24)] +
            [('cart_pa[%d]' % i, 'PA%d' % i, 'ctl_oe_n') for i in range(8)] +
            [('cart_rd_n', '/RD', 'ctl_oe_n'), ('cart_wr_n', '/WR', 'ctl_oe_n'), ('cart_prd_n', '/PRD', 'ctl_oe_n'),
             ('cart_pwr_n', '/PWR', 'ctl_oe_n'), ('cart_romsel_n', '/ROMSEL', 'ctl_oe_n'),
             ('cart_wramsel_n', '/WRAMSEL', 'ctl_oe_n'), ('cart_refresh', 'REFRESH', 'ctl_oe_n'),
             ('cart_phi2', 'PHI2', 'ctl_oe_n'),
             # The 21 MHz clock shares the CIC's byte and its enable, which the logic holds on from the
             # moment the interface is up to the end of the run (sn64_top: cic_enable = IFACE or RUN).
             ('cart_sysclk', 'SYSTEM_CLK', 'cic_oe_n'),
             ('snes_cic_clk', 'CIC_CLK', 'cic_oe_n'), ('snes_cic_slave_reset', 'CIC_SLAVE_RESET', 'cic_oe_n')])
SNES_DATA = [('cart_data[%d]' % i, 'D%d' % i) for i in range(8)]
SNES_IN = [('cic_data0_in', 'CIC_DATA0'), ('cic_data1_in', 'CIC_DATA1'), ('cart_irq_n', '/IRQ'),
           ('cart_reset_n_sense', '/RESET'), ('expand_sense', 'EXPAND')]
SNES_PULL = [('cic_data0_od', 'CIC_DATA0'), ('cic_data1_od', 'CIC_DATA1'), ('reset_pull_od', '/RESET')]
N64 = ([('n64_ad[%d]' % i, 'AD%d' % i) for i in range(16)] +
       [('n64_alel', 'ALE_L'), ('n64_aleh', 'ALE_H'), ('n64_read_n', '/READ'), ('n64_write_n', '/WRITE'),
        ('n64_reset_n', '/RESET'), ('n64_nmi_n', '/NMI'), ('n64_int_n', '/INT'), ('n64_cic_clk', 'CIC_CLK'),
        ('n64_cic_dq', 'CIC_DATA'), ('n64_si_clk', 'PIF_CLK'), ('n64_si_dq', 'JOYBUS')])


class Board:
    def __init__(self, data, lpf, ports):
        self.c = data['components']
        self.lpf = lpf                       # port -> ball
        self.ports = ports                   # list of port bits of the RTL top
        self.index()

    def index(self):
        self.nets = {}
        for ref, comp in self.c.items():
            for pad, net in comp['pads'].items():
                self.nets.setdefault(net, []).append((ref, pad))

    def net(self, ref, pad):
        return self.c[ref]['pads'].get(pad)

    def open(self, ref, pad):
        """The pad is on no net (the board file leaves the name empty, the schematic says unconnected-...)."""
        n = self.net(ref, pad)
        return not n or n.startswith('unconnected')

    def port_net(self, port):
        ball = self.lpf.get(port)
        return self.net('U1', ball) if ball else None

    def on(self, net, kind=None):
        """Pads on a net, optionally only those of parts whose reference starts with `kind`."""
        return [(r, p) for r, p in self.nets.get(net, []) if kind is None or r.startswith(kind)]

    def translators(self):
        return sorted(r for r, comp in self.c.items() if 'ALVC164245' in comp['value'])

    def through_translator(self, net):
        """[(ref, section, index, side)] for every translator data pin on the net."""
        out = []
        for ref in self.translators():
            for sec, t in T245.items():
                for side in ('a', 'b'):
                    for i, pad in enumerate(t[side]):
                        if self.net(ref, pad) == net:
                            out.append((ref, sec, i, side))
        return out

    def two_pin(self, net, prefix):
        """(ref, value, net on the other pad) for every two-pad part with that prefix on the net."""
        out = []
        for ref, pad in self.on(net, prefix):
            pads = self.c[ref]['pads']
            if len(pads) == 2:
                other = next(n for p, n in pads.items() if p != pad)
                out.append((ref, self.c[ref]['value'], other))
        return out


def read_lpf(path):
    return dict(re.findall(r'LOCATE COMP "([^"]+)" SITE "([^"]+)";', path.read_text(encoding='utf-8')))


def read_ports(path):
    """Port bits of the top module: ['osc_27', 'n64_ad[0]', ...]."""
    text = re.sub(r'//.*', '', path.read_text(encoding='utf-8'))
    body = re.search(r'module\s+sn64_board_top\s*\((.*?)\);', text, re.S).group(1)
    out = []
    width = None
    for part in body.split(','):
        part = part.strip()
        m = re.match(r'(input|output|inout)\s+(?:wire|reg|logic)?\s*(\[(\d+):(\d+)\])?\s*(\w+)$', part)
        if m:
            width = (int(m.group(3)), int(m.group(4))) if m.group(2) else None
            name = m.group(5)
        else:
            name = part
        if not re.match(r'^\w+$', name):
            raise SystemExit('cannot read the port list near: ' + part)
        if width:
            out += ['%s[%d]' % (name, i) for i in range(min(width), max(width) + 1)]
        else:
            out.append(name)
    return out


def read_map(path):
    return {r['pin']: r['signal'] for r in csv.DictReader(path.open(encoding='utf-8-sig', newline=''))}


def pins_of(table, signal):
    return sorted(p for p, s in table.items() if s == signal)


def run_checks(b, snes, n64, schematic, lattice):
    res = []

    def check(name, ok, detail=''):
        res.append({'check': name, 'result': 'pass' if ok else 'FAIL', 'detail': detail})

    def skip(name, why):
        res.append({'check': name, 'result': 'skipped', 'detail': why})

    gnd, v33 = 'GND', 'FPGA_3V3'
    cart5 = b.net('J2', '27')

    # 1. Every port of the logic has a ball, and every ball in the constraints is a port.
    missing = [p for p in b.ports if p not in b.lpf]
    extra = [p for p in b.lpf if p not in b.ports]
    balls = list(b.lpf.values())
    check('every port of sn64_board_top has a ball, and no ball is given twice',
          not missing and not extra and len(set(balls)) == len(balls) and all(x in b.c['U1']['pads'] for x in balls),
          '%d ports; missing %s; unknown %s' % (len(b.ports), missing[:5], extra[:5]))

    # 2. Cartridge outputs: FPGA ball -> A side of a channel that points A to B and is switched by
    #    the right enable -> B side -> the socket pin that carries that signal.
    bad = []
    for port, signal, enable in SNES_OUT:
        want_pins = pins_of(snes, signal)
        net = b.port_net(port)
        hops = [h for h in b.through_translator(net) if h[3] == 'a']
        if len(hops) != 1:
            bad.append('%s: its net %s is on %d level-shifter A pins' % (port, net, len(hops)))
            continue
        ref, sec, i, _ = hops[0]
        t = T245[sec]
        far = b.net(ref, t['b'][i])
        got = sorted(p for r, p in b.on(far, 'J2'))
        if got != want_pins:
            bad.append('%s (%s): reaches socket pins %s, should be %s' % (port, signal, got, want_pins))
        if b.net(ref, t['dir']) != v33:
            bad.append('%s: %s byte %d direction pin is on %s, not on 3.3 V (A to B)' % (port, ref, sec, b.net(ref, t['dir'])))
        if b.net(ref, t['oe']) != b.port_net(enable):
            bad.append('%s: %s byte %d enable is on %s, not on the net of %s' % (port, ref, sec, b.net(ref, t['oe']), enable))
        others = [(r, p) for r, p in b.on(far) if r[0] == 'U' and r != ref]
        if others:
            bad.append('%s: its socket net %s also meets %s' % (port, far, others))
    check('%d cartridge outputs reach their own socket pin through a channel that points to the cartridge' % len(SNES_OUT), not bad, '; '.join(bad[:6]))

    # 3. Data bus: both ways, direction from data_dir, enable from data_oe_n.
    bad = []
    for port, signal in SNES_DATA:
        net = b.port_net(port)
        hops = [h for h in b.through_translator(net) if h[3] == 'a']
        if len(hops) != 1:
            bad.append('%s: net %s on %d level-shifter A pins' % (port, net, len(hops)))
            continue
        ref, sec, i, _ = hops[0]
        t = T245[sec]
        got = sorted(p for r, p in b.on(b.net(ref, t['b'][i]), 'J2'))
        if got != pins_of(snes, signal):
            bad.append('%s (%s): reaches socket pins %s' % (port, signal, got))
        if b.net(ref, t['dir']) != b.port_net('data_dir') or b.net(ref, t['oe']) != b.port_net('data_oe_n'):
            bad.append('%s: direction on %s, enable on %s' % (port, b.net(ref, t['dir']), b.net(ref, t['oe'])))
    check('D0-D7 reach their socket pins through one byte whose direction is data_dir and whose enable is data_oe_n', not bad, '; '.join(bad[:6]))
    pulls = [b.two_pin(b.port_net(p), 'R') for p in ('ctl_oe_n', 'cic_oe_n', 'data_oe_n')]
    check('the three level-shifter enables are pulled to 3.3 V, so the socket is released until the FPGA drives them',
          all(any(o == v33 for _, _, o in pl) for pl in pulls), str(pulls))
    check('data_dir is pulled low, so the data byte points away from the cartridge until the FPGA drives it',
          any(o == gnd for _, _, o in b.two_pin(b.port_net('data_dir'), 'R')), str(b.two_pin(b.port_net('data_dir'), 'R')))

    # 4. Cartridge inputs: a channel that points B to A and is always enabled.
    bad = []
    for port, signal in SNES_IN:
        net = b.port_net(port)
        hops = [h for h in b.through_translator(net) if h[3] == 'a']
        if len(hops) != 1:
            bad.append('%s: net %s on %d level-shifter A pins' % (port, net, len(hops)))
            continue
        ref, sec, i, _ = hops[0]
        t = T245[sec]
        got = sorted(p for r, p in b.on(b.net(ref, t['b'][i]), 'J2'))
        if got != pins_of(snes, signal):
            bad.append('%s (%s): comes from socket pins %s' % (port, signal, got))
        if b.net(ref, t['dir']) != gnd or b.net(ref, t['oe']) != gnd:
            bad.append('%s: direction on %s, enable on %s (both should be ground)' % (port, b.net(ref, t['dir']), b.net(ref, t['oe'])))
    check('%d cartridge inputs come from their own socket pin through a channel that points to the FPGA' % len(SNES_IN), not bad, '; '.join(bad[:6]))

    # 5. Open-drain pulls: FPGA -> SN74LVC07A input -> its output -> the socket pin, with a pull-up to cartridge 5 V.
    bad = []
    od = sorted(r for r, comp in b.c.items() if 'LVC07' in comp['value'])
    for port, signal in SNES_PULL:
        net = b.port_net(port)
        ins = [(r, p) for r, p in b.on(net) if r in od and p in LVC07]
        if len(ins) != 1:
            bad.append('%s: net %s on %d open-drain inputs' % (port, net, len(ins)))
            continue
        out = b.net(ins[0][0], LVC07[ins[0][1]])
        got = sorted(p for r, p in b.on(out, 'J2'))
        if got != pins_of(snes, signal):
            bad.append('%s (%s): pulls socket pins %s' % (port, signal, got))
        if not any(o == cart5 for _, _, o in b.two_pin(out, 'R')):
            bad.append('%s: %s has no pull-up to the cartridge 5 V' % (port, out))
        if not any(o == v33 for _, _, o in b.two_pin(net, 'R')):
            bad.append('%s: its driver input %s has no pull-up, so it would pull while the FPGA is not configured' % (port, net))
    net = b.port_net('programn_od')
    ins = [(r, p) for r, p in b.on(net) if r in od and p in LVC07]
    if len(ins) != 1 or b.net(ins[0][0], LVC07[ins[0][1]]) != b.net('U1', CONFIG_BALLS['programn']):
        bad.append('programn_od does not reach the PROGRAMN ball through an open-drain buffer')
    for r in od:
        if b.net(r, '14') != v33 or b.net(r, '7') != gnd:
            bad.append('%s supply pins: %s / %s' % (r, b.net(r, '14'), b.net(r, '7')))
    check('the open-drain pulls (CIC data, /RESET, PROGRAMN) go through the SN74LVC07A to the right pins, with pull-ups', not bad, '; '.join(bad[:6]))

    # 6. Level-shifter supplies.
    bad = []
    for ref in b.translators():
        if any(b.net(ref, p) != cart5 for p in T245_VCCB):
            bad.append('%s VCCB on %s' % (ref, [b.net(ref, p) for p in T245_VCCB]))
        if any(b.net(ref, p) != v33 for p in T245_VCCA):
            bad.append('%s VCCA on %s' % (ref, [b.net(ref, p) for p in T245_VCCA]))
        if any(b.net(ref, p) != gnd for p in T245_GND):
            bad.append('%s ground pins on %s' % (ref, sorted({b.net(ref, p) for p in T245_GND})))
    check('%d level shifters: A side on 3.3 V, B side on the cartridge 5 V, eight grounds each' % len(b.translators()),
          not bad and len(b.translators()) == 4, '; '.join(bad[:4]))

    # 7. Socket power and ground.
    sw = sorted(r for r, comp in b.c.items() if 'TPS2553' in comp['value'])
    check('socket +5 V pins on the switched cartridge supply, socket grounds on ground',
          all(b.net('J2', p) == cart5 for p in pins_of(snes, '+5V_CART')) and all(b.net('J2', p) == gnd for p in pins_of(snes, 'GND'))
          and len(sw) == 1 and b.net(sw[0], '6') == cart5 and cart5 not in (gnd, v33, None),
          'socket +5 V net %s, switch %s output %s' % (cart5, sw, b.net(sw[0], '6') if sw else None))
    check('the cartridge switch is off until the FPGA turns it on (enable pulled low, driven by cart_5v_enable)',
          len(sw) == 1 and b.net(sw[0], '3') == b.port_net('cart_5v_enable') and any(o == gnd for _, _, o in b.two_pin(b.net(sw[0], '3'), 'R')),
          str(b.two_pin(b.net(sw[0], '3'), 'R')) if sw else '')

    # 8. N64 edge: ports straight on their fingers.
    bad = []
    for port, signal in N64:
        got = sorted(p for r, p in b.on(b.port_net(port), 'J1'))
        if got != pins_of(n64, signal):
            bad.append('%s (%s): on edge pins %s, should be %s' % (port, signal, got, pins_of(n64, signal)))
    host = {b.net('J1', p) for p in pins_of(n64, '3V3')}
    mux = sorted(r for r, comp in b.c.items() if 'TPS2121' in comp['value'])
    if len(host) != 1 or not mux or b.net(mux[0], '2') not in host:
        bad.append('the edge 3.3 V pins %s do not all feed input 2 of the power mux' % sorted(host))
    if any(b.net('J1', p) != gnd for p in pins_of(n64, 'GND')):
        bad.append('an edge ground pin is not on ground')
    if any(not b.open('J1', p) for p in pins_of(n64, '12V')):
        bad.append('a 12 V finger is connected: %s' % [b.net('J1', p) for p in pins_of(n64, '12V')])
    check('%d N64 signals on their own edge fingers; 3.3 V fingers feed the power mux; 12 V fingers left open' % len(N64), not bad, '; '.join(bad[:6]))

    # 9. Configuration: flash on the configuration balls, master SPI mode, pulls.
    bad = []
    fl = sorted(r for r, comp in b.c.items() if 'W25Q128' in comp['value'])
    if len(fl) != 1:
        bad.append('flash parts: %s' % fl)
    else:
        f = fl[0]
        for pin, ball in (('cs', 'csspin'), ('d0', 'd0'), ('d1', 'd1'), ('d2', 'd2'), ('d3', 'd3')):
            if b.net(f, FLASH[pin]) != b.net('U1', CONFIG_BALLS[ball]):
                bad.append('flash %s on %s, ball %s on %s' % (pin, b.net(f, FLASH[pin]), CONFIG_BALLS[ball], b.net('U1', CONFIG_BALLS[ball])))
        series = [o for _, _, o in b.two_pin(b.net(f, FLASH['clk']), 'R')]
        if b.net('U1', CONFIG_BALLS['cclk']) not in series:
            bad.append('flash clock does not reach the CCLK ball through a series resistor')
        if b.net(f, FLASH['vcc']) != v33 or b.net(f, FLASH['gnd']) != gnd:
            bad.append('flash supply pins')
        for port, pin in (('flash_cs_n', 'cs'), ('flash_dq[0]', 'd0'), ('flash_dq[1]', 'd1'), ('flash_dq[2]', 'd2'), ('flash_dq[3]', 'd3')):
            if b.port_net(port) != b.net(f, FLASH[pin]):
                bad.append('port %s is not on flash pin %s' % (port, pin))
    for name, rail in (('cfg0', gnd), ('cfg1', v33), ('cfg2', gnd), ('done', v33), ('initn', v33), ('programn', v33)):
        if not any(o == rail for _, _, o in b.two_pin(b.net('U1', CONFIG_BALLS[name]), 'R')):
            bad.append('%s ball has no resistor to %s' % (name, rail))
    check('configuration flash on the configuration balls; CFG = 010 (master SPI); DONE, INITN, PROGRAMN pulled up', not bad, '; '.join(bad[:6]))

    # 10. Clock and reset.
    osc = sorted(r for r, comp in b.c.items() if r.startswith('X'))
    sup = sorted(r for r, comp in b.c.items() if 'TPS3808' in comp['value'])
    check('the 27 MHz oscillator output is on the osc_27 ball and the supervisor output on board_reset_n',
          len(osc) == 1 and b.net(osc[0], '3') == b.port_net('osc_27') and len(sup) == 1 and b.net(sup[0], '1') == b.port_net('board_reset_n'),
          '%s %s' % (osc, sup))

    # 11. USB.
    bad = []
    usb = sorted(r for r, comp in b.c.items() if r.startswith('J') and r not in ('J1', 'J2'))
    if len(usb) != 1:
        bad.append('USB connectors: %s' % usb)
    else:
        j = usb[0]
        dp, dn = {b.net(j, 'A6'), b.net(j, 'B6')}, {b.net(j, 'A7'), b.net(j, 'B7')}
        if len(dp) != 1 or len(dn) != 1 or dp == dn:
            bad.append('D+ %s D- %s' % (dp, dn))
        else:
            dp, dn = dp.pop(), dn.pop()
            if b.port_net('usb_dp') not in [o for _, _, o in b.two_pin(dp, 'R')]:
                bad.append('usb_dp does not reach D+ through a series resistor')
            if b.port_net('usb_dn') not in [o for _, _, o in b.two_pin(dn, 'R')]:
                bad.append('usb_dn does not reach D- through a series resistor')
            if b.port_net('usb_pu') not in [o for _, v, o in b.two_pin(dp, 'R') if v.startswith('1.5k')]:
                bad.append('no 1.5 k from usb_pu to D+')
        for cc in ('A5', 'B5'):
            if not any(v.startswith('5.1k') and o == gnd for _, v, o in b.two_pin(b.net(j, cc), 'R')):
                bad.append('%s has no 5.1 k to ground' % cc)
    check('USB: D+ and D- through series resistors to the FPGA, 1.5 k pull-up from usb_pu on D+, 5.1 k on each CC pin', not bad, '; '.join(bad[:6]))

    # 12. Telemetry converter and the cartridge check's test current.
    bad = []
    adc = sorted(r for r, comp in b.c.items() if 'TLA2528' in comp['value'])
    if len(adc) != 1:
        bad.append('converters: %s' % adc)
    else:
        a = adc[0]
        if b.net(a, '13') != b.port_net('adc_scl') or b.net(a, '14') != b.port_net('adc_sda'):
            bad.append('SCL/SDA on %s / %s' % (b.net(a, '13'), b.net(a, '14')))
        for pin in ('13', '14'):
            if not any(o == v33 for _, _, o in b.two_pin(b.net(a, pin), 'R')):
                bad.append('no pull-up on pin %s' % pin)
        ain3 = b.two_pin(b.net(a, '2'), 'R')
        if not any(o == cart5 and v.startswith('20k') for _, v, o in ain3) or not any(o == gnd and v.startswith('10k') for _, v, o in ain3):
            bad.append('channel 3 is not the cartridge rail through 20 k with 10 k to ground: %s' % ain3)
    check('telemetry converter on the I2C ports with pull-ups; its channel 3 on the cartridge rail (20 k / 10 k), as the cartridge check needs',
          not bad, '; '.join(bad[:6]))

    # 13. Cartridge sound input: socket pin -> capacitor -> resistor -> comparator ball; feedback resistor to the other ball.
    bad = []
    for port, fb, signal in (('aud_l_cmp', 'aud_l_fb', 'AUDIO_L_IN'), ('aud_r_cmp', 'aud_r_fb', 'AUDIO_R_IN')):
        plus = b.port_net(port)
        src = b.net('J2', pins_of(snes, signal)[0])
        after_cap = [o for _, _, o in b.two_pin(src, 'C')]
        into_plus = [o for _, _, o in b.two_pin(plus, 'R')]
        if not set(after_cap) & set(into_plus):
            bad.append('%s: socket %s does not reach the comparator through a capacitor and a resistor' % (port, signal))
        fbnet = b.port_net(fb)
        minus = [o for _, _, o in b.two_pin(fbnet, 'R')]
        if len(minus) != 1 or not any(r == 'U1' for r, _ in b.on(minus[0])) or not any(o == gnd for _, _, o in b.two_pin(minus[0], 'C')):
            bad.append('%s: feedback %s does not reach an FPGA ball through one resistor with a capacitor to ground' % (port, fbnet))
    check('cartridge sound: each socket pin through a capacitor and a resistor to its comparator ball, feedback through an RC to the other ball',
          not bad, '; '.join(bad[:4]))

    # 14. The board and the schematic are the same list.
    if schematic is None:
        skip('the board carries the nets the schematic has', 'validation/sn64-v2.xml not found')
    else:
        diff = []
        for ref, pads in schematic.items():
            if ref not in b.c:
                diff.append('%s is not on the board' % ref)
                continue
            for pad, net in pads.items():
                got = b.net(ref, pad)
                if b.open(ref, pad) and net.startswith('unconnected'):
                    continue
                if got != net:
                    diff.append('%s pad %s: board %s, schematic %s' % (ref, pad, got, net))
        extra = [r for r in b.c if r not in schematic and not r.startswith('H')]
        check('every pad of the board is on the net the schematic gives it (%d parts)' % len(schematic), not diff and not extra,
              '; '.join(diff[:5]) + (' extra parts on the board: %s' % extra[:5] if extra else ''))

    # 15. The FPGA's own balls, against Lattice's table.
    if lattice is None:
        skip('FPGA supply, ground and special balls agree with the Lattice pin-out table', 'build/fpga-sheet/datasheets/ECP5U-85-pinout.csv not found')
    else:
        bad = []
        want = {'GND': gnd, 'VCC': 'FPGA_1V1', 'VCCAUX': 'FPGA_2V5'}
        for ball, d in lattice.items():
            fn = d['fn']
            rail = want.get(fn) or (v33 if fn.startswith('VCCIO') else None)
            if rail and b.net('U1', ball) != rail:
                bad.append('%s (%s) on %s' % (ball, fn, b.net('U1', ball)))
        for port, ball in b.lpf.items():
            d = lattice.get(ball)
            if d is None or not d['fn'].startswith('P') or d['bank'] in ('-', ''):
                bad.append('%s on %s, which is not a user I/O ball' % (port, ball))
        for name, word in (('cclk', 'CCLK'), ('done', 'DONE'), ('initn', 'INITN'), ('programn', 'PROGRAMN'),
                           ('cfg0', 'CFG_0'), ('cfg1', 'CFG_1'), ('cfg2', 'CFG_2'), ('csspin', 'CSSPIN'),
                           ('d0', 'MOSI'), ('d1', 'MISO'), ('d2', 'D2'), ('d3', 'D3')):
            d = lattice.get(CONFIG_BALLS[name], {'fn': '', 'dual': ''})
            if word not in (d['fn'] + ' ' + d['dual']).replace('/', ' / '):
                bad.append('ball %s is not %s in the table (%s %s)' % (CONFIG_BALLS[name], word, d['fn'], d['dual']))
        d = lattice.get(b.lpf.get('osc_27', ''), {'dual': ''})
        if 'PCLK' not in d['dual']:
            bad.append('osc_27 is on %s, which is not a clock input ball (%s)' % (b.lpf.get('osc_27'), d['dual']))
        for port in ('aud_l_cmp', 'aud_r_cmp'):
            d = lattice.get(b.lpf.get(port, ''), {'diff': '', 'bank': ''})
            if not d['diff'].startswith('True_OF_') or d['bank'] not in ('2', '3', '6', '7'):
                bad.append('%s on %s is not the true side of a differential pair on a side bank (%s, bank %s)' % (port, b.lpf.get(port), d['diff'], d['bank']))
        check('FPGA supply and ground balls on their rails, ports on user I/O balls, configuration, clock and comparator balls as the Lattice table names them',
              not bad, '; '.join(bad[:6]))

    # 16. Nothing else hangs on an FPGA signal ball.
    used = set(b.lpf.values()) | set(CONFIG_BALLS.values())
    stray = []
    for ball, net in b.c['U1']['pads'].items():
        if ball in used or not net or net.startswith('unconnected') or net in (gnd, v33, 'FPGA_1V1', 'FPGA_2V5'):
            continue
        if net.startswith('JTAG_') or net in ('AUD_L_N', 'AUD_R_N'):
            continue
        stray.append('%s on %s' % (ball, net))
    check('no FPGA ball carries a signal that the logic has no port for (JTAG and the two comparator return balls apart)', not stray, '; '.join(stray[:8]))
    return res


def read_schematic(path):
    if not path.exists():
        return None
    comps = {}
    for net in ET.parse(path).getroot().iter('net'):
        for node in net.iter('node'):
            comps.setdefault(node.get('ref'), {})[node.get('pin')] = net.get('name').lstrip('/')
    return comps


def read_lattice(path):
    if not path.exists():
        return None
    rows = list(csv.reader(open(path, encoding='utf-8')))
    hdr = rows[4]
    ib, ibank, ifn, idf, idiff = (hdr.index(k) for k in ('CABGA381', 'Bank', 'Pin/Ball Function', 'Dual Function', 'Differential'))
    return {r[ib]: {'bank': r[ibank], 'fn': r[ifn], 'dual': r[idf], 'diff': r[idiff]}
            for r in rows[5:] if len(r) > ib and r[ib] not in ('-', '')}


# ---- deliberate mistakes ---------------------------------------------------------------------
def swap(data, a, b_):
    (ra, pa), (rb, pb) = a, b_
    data['components'][ra]['pads'][pa], data['components'][rb]['pads'][pb] = data['components'][rb]['pads'][pb], data['components'][ra]['pads'][pa]


MISTAKES = [
    ('two address lines swapped at a level shifter', lambda d, l: swap(d, ('U201', '2'), ('U201', '3'))),
    ('two socket pins swapped', lambda d, l: swap(d, ('J2', '19'), ('J2', '20'))),
    ('socket rows exchanged (pins 1-31 with 32-62)', lambda d, l: [swap(d, ('J2', str(i)), ('J2', str(i + 31))) for i in range(1, 32)]),
    ('socket mirrored left to right', lambda d, l: [swap(d, ('J2', str(i)), ('J2', str(32 - i))) for i in range(1, 16)] +
                                                     [swap(d, ('J2', str(i + 31)), ('J2', str(63 - i))) for i in range(1, 16)]),
    ('a level-shifter byte pointing the wrong way', lambda d, l: d['components']['U202']['pads'].__setitem__('1', 'GND')),
    ('the data byte enabled all the time', lambda d, l: d['components']['U204']['pads'].__setitem__('48', 'GND')),
    ('level shifter B side on 3.3 V', lambda d, l: d['components']['U203']['pads'].__setitem__('7', 'FPGA_3V3')),
    ('two FPGA ports exchanged in the constraints', lambda d, l: l.update({'cart_rd_n': l['cart_wr_n'], 'cart_wr_n': l['cart_rd_n']})),
    ('N64 address/data lines swapped on the edge', lambda d, l: swap(d, ('J1', '28'), ('J1', '29'))),
    ('N64 edge rows exchanged (pins 1-25 with 26-50)', lambda d, l: [swap(d, ('J1', str(i)), ('J1', str(i + 25))) for i in range(1, 26)]),
    ('flash data lines swapped', lambda d, l: swap(d, ('U2', '2'), ('U2', '5'))),
    ('configuration mode pin pulled the wrong way', lambda d, l: [d['components'][r]['pads'].update({p: 'GND' if n == 'FPGA_3V3' else n for p, n in d['components'][r]['pads'].items()})
                                                                  for r in ('R6',)]),
    ('USB data lines swapped at the connector', lambda d, l: [swap(d, ('J101', 'A6'), ('J101', 'A7')), swap(d, ('J101', 'B6'), ('J101', 'B7'))]),
    ('open-drain driver output on the wrong socket pin', lambda d, l: swap(d, ('U205', '4'), ('U205', '6'))),
    ('cartridge 5 V switch enabled by default', lambda d, l: [d['components'][r]['pads'].update({p: 'FPGA_3V3' if n == 'GND' else n for p, n in d['components'][r]['pads'].items()})
                                                              for r in ('R319',)]),
    ('an FPGA core supply ball on 3.3 V', lambda d, l: d['components']['U1']['pads'].__setitem__(
        next(k for k, v in d['components']['U1']['pads'].items() if v == 'FPGA_1V1'), 'FPGA_3V3')),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--nets', type=Path, default=ROOT / 'build/board-sim/board-nets.json')
    ap.add_argument('--negative', action='store_true')
    ap.add_argument('--out', type=Path, default=V2 / 'validation/board-wiring.json')
    args = ap.parse_args()
    if not args.nets.exists():
        sys.exit('run tools/export_board_nets.py with KiCad\'s Python first: %s is missing' % args.nets)
    data = json.loads(args.nets.read_text(encoding='utf-8'))
    lpf = read_lpf(ROOT / 'fpga/constraints/sn64_board.lpf')
    ports = read_ports(ROOT / 'fpga/rtl/sn64_board_top.sv')
    snes = read_map(ROOT / 'hardware/sn64/interfaces/snes-pin-map.csv')
    n64 = read_map(ROOT / 'hardware/sn64/interfaces/n64-pin-map.csv')
    schematic = read_schematic(V2 / 'validation/sn64-v2.xml')
    lattice = read_lattice(ROOT / 'build/fpga-sheet/datasheets/ECP5U-85-pinout.csv')

    if args.negative:
        caught = 0
        for name, mutate in MISTAKES:
            d, l = copy.deepcopy(data), dict(lpf)
            mutate(d, l)
            res = run_checks(Board(d, l, ports), snes, n64, None, lattice)      # the schematic comparison would catch everything; leave it out
            fails = [r['check'] for r in res if r['result'] == 'FAIL']
            caught += bool(fails)
            print('%-52s %s' % (name, 'caught by %d check(s): %s' % (len(fails), fails[0][:70]) if fails else 'NOT CAUGHT'))
        print('NEGATIVE: %d of %d deliberate mistakes caught' % (caught, len(MISTAKES)))
        return 0 if caught == len(MISTAKES) else 1

    res = run_checks(Board(data, lpf, ports), snes, n64, schematic, lattice)
    for r in res:
        print('%-7s %s%s' % (r['result'], r['check'], ('\n        ' + r['detail']) if r['result'] != 'pass' and r['detail'] else ''))
    n_pass = sum(r['result'] == 'pass' for r in res)
    n_fail = sum(r['result'] == 'FAIL' for r in res)
    n_skip = sum(r['result'] == 'skipped' for r in res)
    args.out.write_text(json.dumps({'board': data['board'], 'ports': len(ports), 'checks': res,
                                    'summary': {'pass': n_pass, 'fail': n_fail, 'skipped': n_skip}}, indent=1), encoding='utf-8', newline='\n')
    print('%d passed, %d failed, %d skipped -> %s' % (n_pass, n_fail, n_skip, args.out.name))
    return 1 if n_fail else 0


if __name__ == '__main__':
    sys.exit(main())
