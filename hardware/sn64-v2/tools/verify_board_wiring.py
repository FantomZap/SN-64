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
import math
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
JTAG_BALLS = {'tck': 'T5', 'tms': 'U5', 'tdi': 'R5', 'tdo': 'V4'}
# FT231XS (FTDI FT_000565 v1.2, table 3.5 and 3.6), SSOP-20: the USB loader chip.
FT231X = {'dtr': '1', 'rts': '2', 'vccio': '3', 'rxd': '4', 'ri': '5', 'dsr': '7', 'dcd': '8', 'cts': '9',
          'usbdp': '11', 'usbdm': '12', '3v3out': '13', 'reset': '14', 'vcc': '15', 'txd': '20'}
FT231X_GND, FT231X_CBUS = ['6', '16'], ['18', '17', '10', '19']
# The pins openFPGALoader moves for its board entry "ulx3s" (src/board.hpp at commit 676e53ec:
# JTAG_BITBANG_BOARD("ulx3s", "", "ft231X", ..., FT232RL_DCD, FT232RL_DSR, FT232RL_RI, FT232RL_CTS, ...)
# in the order TMS, TCK, TDI, TDO). The ULX3S schematic (emard/ulx3s usb.sch, commit 6a92cec6) agrees.
LOADER_JTAG = {'tms': 'dcd', 'tck': 'dsr', 'tdi': 'ri', 'tdo': 'cts'}

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
           ('cart_reset_n_sense', '/RESET')]
# TLA2528 (TI SBAS961A), RTE package: inputs AIN0..AIN7, and the rest.
ADC_AIN = ['15', '16', '1', '2', '3', '4', '5', '6']
ADC = {'avdd': '7', 'decap': '8', 'gnd': '9', 'dvdd': '10', 'addr': '11', 'scl': '13', 'sda': '14'}
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


# Capacitors that may be further than 3.5 mm from their pin, and why.
NEAR = {'C306': 5.0,     # the selector's output: on the loop that joins its two OUT pads, with C308 nearer
        'C43': 4.5,      # the loader chip's I/O supply, as placed with the chip on 2026-10-02
        'C209': 6.0, 'C210': 6.0}    # the two 22 uF of the cartridge's 5 V: at the socket's 5 V pads, behind its courtyard


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
    pulls = [b.two_pin(b.port_net(p), 'R') for p in ('ctl_oe_n', 'cic_oe_n', 'data_oe_n', 'sense_oe_n')]
    check('the four level-shifter enables are pulled to 3.3 V, so every byte is off until the FPGA drives them',
          all(any(o == v33 for _, _, o in pl) for pl in pulls), str(pulls))
    check('data_dir is pulled low, so the data byte points away from the cartridge until the FPGA drives it',
          any(o == gnd for _, _, o in b.two_pin(b.port_net('data_dir'), 'R')), str(b.two_pin(b.port_net('data_dir'), 'R')))

    # 4. Cartridge inputs: a channel that points B to A, switched by sense_oe_n.
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
        if b.net(ref, t['dir']) != gnd or b.net(ref, t['oe']) != b.port_net('sense_oe_n'):
            bad.append('%s: direction on %s (should be ground), enable on %s (should be the net of sense_oe_n)' % (
                port, b.net(ref, t['dir']), b.net(ref, t['oe'])))
    check('%d cartridge inputs come from their own socket pin through a channel that points to the FPGA and is switched by sense_oe_n' % len(SNES_IN),
          not bad, '; '.join(bad[:6]))

    # 4b. Rules of the level shifter's data sheet (TI SCAS416Q). Section 10: /OE is to be high until
    #     both supplies are up; the B side's supply is the switched cartridge 5 V, so no byte may be
    #     enabled by a fixed level. Section 3: the inputs of both ports are always active and must
    #     not float: no pin of the A side (always powered) is open, and no B-side input.
    bad = []
    enables = {b.port_net(p) for p in ('ctl_oe_n', 'cic_oe_n', 'data_oe_n', 'sense_oe_n')}
    for ref in b.translators():
        for sec, t in T245.items():
            if b.net(ref, t['oe']) not in enables:
                bad.append('%s byte %d: enable on %s, which the FPGA does not drive' % (ref, sec, b.net(ref, t['oe'])))
            if b.open(ref, t['dir']):
                bad.append('%s byte %d: direction pin open' % (ref, sec))
            a_to_b = b.net(ref, t['dir']) == v33
            for i in range(8):
                a_open, b_open = b.open(ref, t['a'][i]), b.open(ref, t['b'][i])
                if a_open:
                    # the A side always has its 3.3 V: an open pin there floats for as long as the byte is off
                    bad.append('%s byte %d channel %d: its A-side pin is open' % (ref, sec, i + 1))
                elif b_open and not a_to_b:
                    bad.append('%s byte %d channel %d: its B-side input is open' % (ref, sec, i + 1))
                # An open B-side pin of a byte that points to the cartridge is an output: driven while the
                # byte is on, and without supply while the cartridge is off. It floats only for the few
                # milliseconds between the 5 V coming up and the byte being switched on. Accepted.
    check('level shifters: every byte enable is driven by the FPGA, and no pin that can float for long is left open (TI SCAS416Q sections 3 and 10)', not bad, '; '.join(bad[:6]))

    # 4c. The converter that watches the supplies (TLA2528, TI SBAS961A).
    bad = []
    adc = sorted(r for r, comp in b.c.items() if 'TLA2528' in comp['value'])
    if len(adc) != 1:
        bad.append('%d converters' % len(adc))
    else:
        u = adc[0]
        if not b.open(u, ADC['addr']):
            bad.append('ADDR on %s: the logic talks to address 0x10, which the data sheet (table 2) gives for the pin left open' % b.net(u, ADC['addr']))
        if b.net(u, ADC['scl']) != b.port_net('adc_scl') or b.net(u, ADC['sda']) != b.port_net('adc_sda'):
            bad.append('SCL/SDA on %s / %s' % (b.net(u, ADC['scl']), b.net(u, ADC['sda'])))
        for name in ('scl', 'sda'):
            if not any(o == v33 for _, _, o in b.two_pin(b.net(u, ADC[name]), 'R')):
                bad.append('%s has no pull-up to 3.3 V' % name.upper())
        if b.net(u, ADC['avdd']) != v33 or b.net(u, ADC['dvdd']) != v33 or b.net(u, ADC['gnd']) != gnd:
            bad.append('supply pins on %s / %s / %s' % (b.net(u, ADC['avdd']), b.net(u, ADC['dvdd']), b.net(u, ADC['gnd'])))
        if not any(o == gnd for _, _, o in b.two_pin(b.net(u, ADC['decap']), 'C')):
            bad.append('DECAP has no capacitor to ground')
        rail_inputs = [i for i, pad in enumerate(ADC_AIN) if any(o == cart5 for _, _, o in b.two_pin(b.net(u, pad), 'R'))]
        if rail_inputs != [3]:
            bad.append('the cartridge supply is divided into inputs %s; the logic reads it, and feeds its test current, on input 3' % rail_inputs)
        if any(b.open(u, pad) for pad in ADC_AIN):
            bad.append('an input is open')
    check('supply converter: address pin open (0x10), I2C lines pulled up and on their balls, supplies, DECAP capacitor, cartridge supply on input 3',
          not bad, '; '.join(bad[:6]))

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
    driven = {b.port_net(port) for port, _ in SNES_PULL}
    programn = b.net('U1', CONFIG_BALLS['programn'])
    for r in od:
        if b.net(r, '14') != v33 or b.net(r, '7') != gnd:
            bad.append('%s supply pins: %s / %s' % (r, b.net(r, '14'), b.net(r, '7')))
        for i, o in LVC07.items():
            if b.net(r, i) in driven:
                continue
            # a gate the logic does not drive: input tied, output on nothing. On PROGRAMN it would hold
            # the FPGA unconfigured for ever (the gate that pulled PROGRAMN went with the FPGA's USB part).
            if b.net(r, i) not in (gnd, v33):
                bad.append('%s pin %s: input of an unused gate on %s' % (r, i, b.net(r, i)))
            if not b.open(r, o):
                bad.append('%s pin %s: output of an unused gate on %s' % (r, o, b.net(r, o)))
    if any(r in od for r, _ in b.on(programn)):
        bad.append('an open-drain gate is on the PROGRAMN ball')
    check('the open-drain pulls (CIC data, /RESET) go through the SN74LVC07A to the right pins, with pull-ups; '
          'unused gates are tied off and none is on PROGRAMN', not bad, '; '.join(bad[:6]))

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

    # 11. USB: the connector's data lines go to the loader chip and nowhere else.
    bad = []
    usb = sorted(r for r, comp in b.c.items() if r.startswith('J') and r not in ('J1', 'J2'))
    ft = sorted(r for r, comp in b.c.items() if 'FT231X' in comp['value'])
    if len(usb) != 1 or len(ft) != 1:
        bad.append('USB connectors: %s, loader chips: %s' % (usb, ft))
    else:
        j, u = usb[0], ft[0]
        dp, dn = {b.net(j, 'A6'), b.net(j, 'B6')}, {b.net(j, 'A7'), b.net(j, 'B7')}
        vbus = {b.net(j, x) for x in ('A4', 'A9', 'B4', 'B9')}
        if len(dp) != 1 or len(dn) != 1 or dp == dn or len(vbus) != 1:
            bad.append('D+ %s D- %s VBUS %s' % (dp, dn, vbus))
        else:
            dp, dn, vbus = dp.pop(), dn.pop(), vbus.pop()
            for line, name, pin in ((dp, 'D+', 'usbdp'), (dn, 'D-', 'usbdm')):
                ser = [(v, o) for _, v, o in b.two_pin(line, 'R')]
                if [o for v, o in ser if v.startswith('27')] != [b.net(u, FT231X[pin])]:
                    bad.append('%s does not reach the chip pin %s through one 27 ohm resistor (%s)' % (name, pin.upper(), ser))
                if not any(v.startswith('47pF') and o == gnd for _, v, o in b.two_pin(line, 'C')):
                    bad.append('%s has no 47 pF to ground' % name)
                if any(r == 'U1' for r, _ in b.on(line)) or any(r == 'U1' for r, _ in b.on(b.net(u, FT231X[pin]))):
                    bad.append('%s reaches an FPGA ball' % name)
            if b.net(u, FT231X['vcc']) != vbus:
                bad.append('chip VCC on %s, not on the connector VBUS %s' % (b.net(u, FT231X['vcc']), vbus))
            if not any(o == gnd for _, _, o in b.two_pin(vbus, 'C')):
                bad.append('no capacitor from VBUS to ground')
            own = b.net(u, FT231X['3v3out'])
            # FT_000565 figure 6.1: VCCIO and RESET# on the chip's own 3.3 V output. On another supply the
            # chip's pins would stay powered while its core is not, and could drive the JTAG lines.
            if b.net(u, FT231X['vccio']) != own or b.net(u, FT231X['reset']) != own or own in (gnd, v33, vbus):
                bad.append('3V3OUT %s, VCCIO %s, RESET# %s' % (own, b.net(u, FT231X['vccio']), b.net(u, FT231X['reset'])))
            if [r for r, _ in b.on(own) if not (r == u or r.startswith('C'))]:
                bad.append('something else hangs on the chip 3.3 V output: %s' % b.on(own))
            if not any(o == gnd for _, _, o in b.two_pin(own, 'C')):
                bad.append('no capacitor on the chip 3.3 V output')
            if any(b.net(u, g) != gnd for g in FT231X_GND):
                bad.append('chip ground pins')
            for name in ('dtr', 'rts', 'rxd', 'txd'):
                if not b.open(u, FT231X[name]):
                    bad.append('chip pin %s is not open (%s)' % (name.upper(), b.net(u, FT231X[name])))
            if any(not b.open(u, c) for c in FT231X_CBUS):
                bad.append('a CBUS pin is not open')
        for cc in ('A5', 'B5'):
            if not any(v.startswith('5.1k') and o == gnd for _, v, o in b.two_pin(b.net(j, cc), 'R')):
                bad.append('%s has no 5.1 k to ground' % cc)
    check('USB: D+ and D- each through 27 ohm to the loader chip and to nothing else, 47 pF on each; the chip on VBUS with '
          'VCCIO and RESET# on its own 3.3 V output; its serial and CBUS pins open; 5.1 k on each CC pin', not bad, '; '.join(bad[:6]))

    # 11b. JTAG: the loader chip's four pins on the FPGA's JTAG balls, as the PC tool expects them.
    bad = []
    if len(ft) == 1:
        u = ft[0]
        for sig, ball in JTAG_BALLS.items():
            net = b.net('U1', ball)
            pin = FT231X[LOADER_JTAG[sig]]
            if b.net(u, pin) != net or not net or net.startswith('unconnected'):
                bad.append('%s: FPGA ball %s on %s, chip pin %s (%s#) on %s' % (sig.upper(), ball, net, pin, LOADER_JTAG[sig].upper(), b.net(u, pin)))
                continue
            others = [(r, q) for r, q in b.on(net) if r not in ('U1', u) and not r.startswith(('R', 'TP'))]
            if others:
                bad.append('%s also reaches %s' % (sig.upper(), others))
            if not b.on(net, 'TP'):
                bad.append('%s has no test pad' % sig.upper())
            pulls = [o for _, _, o in b.two_pin(net, 'R')]
            if pulls != ([gnd] if sig == 'tck' else [v33]):
                bad.append('%s pulls: %s (TCK wants one resistor to ground, the others one to 3.3 V)' % (sig.upper(), pulls))
    else:
        bad.append('no loader chip')
    check('JTAG: the loader chip is on the FPGA JTAG balls as openFPGALoader drives it (TCK = DSR#, TMS = DCD#, TDI = RI#, '
          'TDO = CTS#), nothing else is; TMS, TDI, TDO pulled up, TCK pulled down, a test pad on each', not bad, '; '.join(bad[:6]))

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
        for sig, ball in JTAG_BALLS.items():
            if lattice.get(ball, {'fn': ''})['fn'] != sig.upper():
                bad.append('ball %s is not %s in the table (%s)' % (ball, sig.upper(), lattice.get(ball, {'fn': ''})['fn']))
        d = lattice.get(b.lpf.get('osc_27', ''), {'dual': ''})
        if 'PCLK' not in d['dual']:
            bad.append('osc_27 is on %s, which is not a clock input ball (%s)' % (b.lpf.get('osc_27'), d['dual']))
        for port in ('aud_l_cmp', 'aud_r_cmp'):
            d = lattice.get(b.lpf.get(port, ''), {'diff': '', 'bank': ''})
            if not d['diff'].startswith('True_OF_') or d['bank'] not in ('2', '3', '6', '7'):
                bad.append('%s on %s is not the true side of a differential pair on a side bank (%s, bank %s)' % (port, b.lpf.get(port), d['diff'], d['bank']))
        check('FPGA supply and ground balls on their rails, ports on user I/O balls, configuration, clock and comparator balls as the Lattice table names them',
              not bad, '; '.join(bad[:6]))

    # 15a. Rules of the power parts' data sheets that are wiring, found in the review of 2026-10-02.
    bad = []
    en = b.net('U8', '14')
    if en == b.net('U8', '12'):
        bad.append('U8 EN is tied straight to VIN (TI SLVSC58B 11.1: through 10 k)')
    else:
        r = [x for x in b.two_pin(en, 'R') if x[2] == b.net('U8', '12')]
        if len(r) != 1 or len(b.on(en)) != 2:
            bad.append('U8 EN (%s) is not on VIN through one resistor: %s' % (en, b.on(en)))
    for cap, pin in (('C35', '7'), ('C46', '10')):
        c = b.c.get(cap)
        if c is None or not c['value'].startswith('1uF') or b.net('U6', pin) not in c['pads'].values():
            bad.append('%s is not a 1 uF on the supply of U6 pin %s (TI SBAS961A: 1 uF on AVDD and on DVDD)' % (cap, pin))
    for ref in ('C324', 'C325'):
        if ref not in b.c or not b.c[ref]['value'].startswith('10uF') or '0603' not in b.c[ref]['footprint']:
            bad.append('%s is not a 10 uF 0603 (TI SLVSC58B 11.1: a 0603 at the VIN pins and one at the VOUT pins)' % ref)
    check('5 V converter: enable through a resistor, a 0603 capacitor on its input and on its output; measuring chip: 1 uF on each supply pin',
          not bad, '; '.join(bad))

    # 15b. Every capacitor is at the pin it serves. The table is AT_PIN in build_v2_schematic.py; the distance is
    # between the pin and the capacitor's pad on the same net, whichever face the capacitor is on.
    table = json.loads((V2 / 'libraries' / 'v2-provenance.json').read_text(encoding='utf-8')).get('capacitor_at_pin', {})
    bad, worst = [], (0.0, '')
    for cap, (chip, pin) in sorted(table.items()):
        if cap not in b.c or chip not in b.c or 'at' not in b.c[cap]:
            bad.append('%s or %s is not on the board' % (cap, chip))
            continue
        net = b.net(chip, pin)
        mine = [p for p, n in b.c[cap]['pads'].items() if n == net]
        if not mine:
            bad.append('%s has no pad on %s, the net of %s pin %s' % (cap, net, chip, pin))
            continue
        d = math.dist(b.c[cap]['at'][mine[0]], b.c[chip]['at'][pin])
        limit = NEAR.get(cap, 3.5)
        worst = max(worst, (d / limit, '%s %.1f of %.1f mm' % (cap, d, limit)))
        if d > limit:
            bad.append('%s is %.1f mm from %s pin %s (limit %.1f)' % (cap, d, chip, pin, limit))
    check('%d capacitors are at the pin they serve (3.5 mm at most, the few exceptions named in the tool; nearest to its limit: %s)'
          % (len(table), worst[1]), not bad, '; '.join(bad[:8]))

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


def move_part(data, ref, dx):
    for xy in data['components'][ref]['at'].values():
        xy[0] += dx


MISTAKES = [
    ('the 5 V converter enable tied straight to its supply', lambda d, l: d['components']['U8']['pads'].__setitem__('14', d['components']['U8']['pads']['12'])),
    ('the 1.1 V converter input capacitor 20 mm from its pin', lambda d, l: move_part(d, 'C313', 20.0)),
    ('a level-shifter capacitor back in the clump', lambda d, l: move_part(d, 'C202', -30.0)),
    ('the measuring chip with 100 nF on its analog supply', lambda d, l: d['components']['C35'].__setitem__('value', '100nF')),
    ('two address lines swapped at a level shifter', lambda d, l: swap(d, ('U201', '2'), ('U201', '3'))),
    ('two socket pins swapped', lambda d, l: swap(d, ('J2', '19'), ('J2', '20'))),
    ('socket rows exchanged (pins 1-31 with 32-62)', lambda d, l: [swap(d, ('J2', str(i)), ('J2', str(i + 31))) for i in range(1, 32)]),
    ('socket mirrored left to right', lambda d, l: [swap(d, ('J2', str(i)), ('J2', str(32 - i))) for i in range(1, 16)] +
                                                     [swap(d, ('J2', str(i + 31)), ('J2', str(63 - i))) for i in range(1, 16)]),
    ('a level-shifter byte pointing the wrong way', lambda d, l: d['components']['U202']['pads'].__setitem__('1', 'GND')),
    ('the data byte enabled all the time', lambda d, l: d['components']['U204']['pads'].__setitem__('48', 'GND')),
    ('the byte from the socket to the FPGA enabled all the time', lambda d, l: d['components']['U204']['pads'].__setitem__('25', 'GND')),
    ('an unused level-shifter pin left open', lambda d, l: d['components']['U204']['pads'].__setitem__('26', 'unconnected-(U204-2A7-Pad26)')),
    ('the supply converter address pin tied to ground', lambda d, l: d['components']['U6']['pads'].__setitem__('11', 'GND')),
    ('the cartridge supply divider on the wrong converter input', lambda d, l: swap(d, ('U6', '2'), ('U6', '3'))),
    ('level shifter B side on 3.3 V', lambda d, l: d['components']['U203']['pads'].__setitem__('7', 'FPGA_3V3')),
    ('two FPGA ports exchanged in the constraints', lambda d, l: l.update({'cart_rd_n': l['cart_wr_n'], 'cart_wr_n': l['cart_rd_n']})),
    ('N64 address/data lines swapped on the edge', lambda d, l: swap(d, ('J1', '28'), ('J1', '29'))),
    ('N64 edge rows exchanged (pins 1-25 with 26-50)', lambda d, l: [swap(d, ('J1', str(i)), ('J1', str(i + 25))) for i in range(1, 26)]),
    ('flash data lines swapped', lambda d, l: swap(d, ('U2', '2'), ('U2', '5'))),
    ('configuration mode pin pulled the wrong way', lambda d, l: [d['components'][r]['pads'].update({p: 'GND' if n == 'FPGA_3V3' else n for p, n in d['components'][r]['pads'].items()})
                                                                  for r in ('R6',)]),
    ('USB data lines swapped at the connector', lambda d, l: [swap(d, ('J101', 'A6'), ('J101', 'A7')), swap(d, ('J101', 'B6'), ('J101', 'B7'))]),
    ('JTAG clock and mode select swapped at the loader chip', lambda d, l: swap(d, ('U13', '7'), ('U13', '8'))),
    ('JTAG data in and data out swapped at the loader chip', lambda d, l: swap(d, ('U13', '5'), ('U13', '9'))),
    ('loader chip I/O supply on the board 3.3 V', lambda d, l: d['components']['U13']['pads'].__setitem__('3', 'FPGA_3V3')),
    ('JTAG clock pulled up instead of down', lambda d, l: d['components']['R41']['pads'].__setitem__('1', 'FPGA_3V3')),
    ('an unused open-drain gate left on PROGRAMN', lambda d, l: d['components']['U205']['pads'].__setitem__('2', 'FPGA_PROGRAMN')),
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
