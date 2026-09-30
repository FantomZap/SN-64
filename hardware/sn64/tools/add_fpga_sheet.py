"""Author the SN64 FPGA child sheet, the board pin map and the board LPF.

One-time draft authoring utility in the style of add_cart_interface.py. It
writes, from ONE pin table (PINMAP below):

  hardware/sn64/fpga.kicad_sch            child sheet "FPGA" (LFE5U-85F CABGA381,
                                          config flash, JTAG, N64 bus switches)
  hardware/sn64/interfaces/fpga-pin-map.csv
  fpga/constraints/sn64_board.lpf

By default it never edits the real root sheet (sn64.kicad_sch), the
sym-lib-table or any other sheet: attaching the sheet is an integration step,
available as --attach-real-root for the integrator. For validation,
--validation-copy DIR copies hardware/sn64 to DIR (DIR must be under build/)
and attaches the sheet to THAT copy's root: N64 edge and HOST_3V3/GND pins get
the existing root labels, the cartridge-side pins get labels that replace the
no-connect markers add_cart_interface.py put on the cartridge sheet's FPGA
pins, and every other pin (power, clock/A-V, USB/JTAG sheets that do not
exist yet) gets a no-connect marker.

It refuses to replace an existing fpga.kicad_sch unless --force is given;
after native KiCad editing starts, edit the KiCad files instead. Output is
deterministic (UUIDv5), so a rerun with --force is byte-identical.

  python add_fpga_sheet.py --kicad-share "C:/Program Files/KiCad/10.0/share/kicad" [--force]
  python add_fpga_sheet.py --kicad-share ... --validation-copy build/fpga-sheet/proj

Sources (details and SHA-256 of the downloaded copies in docs/design/fpga-schematic.md):
  Lattice ECP5U-85 pinout CSV (document 50487, rev 1.0) - every ball below
  Lattice FPGA-DS-02012-3.4 (ECP5 data sheet), FPGA-TN-02038-2.1 (hardware
  checklist), FPGA-TN-02039-2.5 (sysCONFIG), FPGA-TN-02032-1.4 (sysI/O),
  FPGA-TN-02200-1.3 (sysCLOCK); Winbond W25Q128JV rev F; TI SCDS114E
  (SN74CB3Q3384A), SCES218AA (SN74LVC1G14), SCES296AG (SN74LVC1G07).
Pure Python 3 (no pcbnew needed).
"""
import argparse
import copy
import csv
import io
import json
import math
from pathlib import Path
import re
import shutil
import uuid

ROOT = Path(__file__).resolve().parents[1]          # hardware/sn64
REPO = ROOT.parents[1]
NS = uuid.UUID('8f0c8a0e-5b1e-4c55-9a8e-0f64a5e0c301')
CART_NS = uuid.UUID('5d0f7c52-1c1e-4d8a-9a57-3c3c8b1f6a40')   # add_cart_interface.py
SHEET_FILE = 'fpga.kicad_sch'
SHEET_NAME = 'FPGA'
REV = '0.5-fpga'      # 0.5: HDMI pins removed (console video path)


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
    path.write_text(text if text.endswith('\n') else text + '\n', encoding='utf-8', newline='\n')


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
# Rails and bank plan. Every VCCIO bank is 3.3 V (LVCMOS33 everywhere): the
# cartridge translators' B side, the N64 PI behind the bus switches, the
# configuration flash (bank 8) and JTAG (VCCIO8) are all 3.3 V.
# ---------------------------------------------------------------------------
GND, V11, V25, V33 = 'GND', 'FPGA_1V1', 'FPGA_2V5', 'FPGA_3V3'
VAUX = 'FPGA_VCCAUX'          # VCCAUX after the TN-02038 Figure 3.1 ferrite bead
POWER_NETS = {'VCC': V11, 'VCCAUX': VAUX, 'GND': GND,
              **{f'VCCIO{b}': V33 for b in (0, 1, 2, 3, 6, 7, 8)}}

# ---------------------------------------------------------------------------
# PINMAP: port (sn64_board_top after the documented integration edit), ball,
# IO_TYPE, extra LPF attributes, FPGA-side net, exported hierarchical label,
# note. Balls/banks/functions: Lattice ECP5U-85 pinout CSV, CABGA381 column.
# ---------------------------------------------------------------------------
N64 = [  # port, ball, pull (SummerCart64 a1e7996d sc64.lpf), root edge label
    ('n64_ad[0]', 'E6', 'NONE', 'N64_AD0'), ('n64_ad[1]', 'D6', 'NONE', 'N64_AD1'),
    ('n64_ad[2]', 'E7', 'NONE', 'N64_AD2'), ('n64_ad[3]', 'D7', 'NONE', 'N64_AD3'),
    ('n64_ad[4]', 'C6', 'NONE', 'N64_AD4'), ('n64_ad[5]', 'C7', 'NONE', 'N64_AD5'),
    ('n64_ad[6]', 'E8', 'NONE', 'N64_AD6'), ('n64_ad[7]', 'D8', 'NONE', 'N64_AD7'),
    ('n64_ad[8]', 'C8', 'NONE', 'N64_AD8'), ('n64_ad[9]', 'B8', 'NONE', 'N64_AD9'),
    ('n64_ad[10]', 'A7', 'NONE', 'N64_AD10'), ('n64_ad[11]', 'A8', 'NONE', 'N64_AD11'),
    ('n64_ad[12]', 'D9', 'NONE', 'N64_AD12'), ('n64_ad[13]', 'E9', 'NONE', 'N64_AD13'),
    ('n64_ad[14]', 'C9', 'NONE', 'N64_AD14'), ('n64_ad[15]', 'D10', 'NONE', 'N64_AD15'),
    ('n64_alel', 'E10', 'DOWN', 'N64_ALE_L'), ('n64_aleh', 'B9', 'UP', 'N64_ALE_H'),
    ('n64_read_n', 'C10', 'UP', 'N64_READ_N'), ('n64_write_n', 'A9', 'UP', 'N64_WRITE_N'),
    ('n64_reset_n', 'B10', 'DOWN', 'N64_RESET_N'), ('n64_nmi_n', 'A11', 'DOWN', 'N64_NMI_N'),
    ('n64_cic_clk', 'A10', 'UP', 'N64_CIC_CLK'), ('n64_si_clk', 'B11', 'DOWN', 'N64_PIF_CLK'),
    ('n64_cic_dq', 'C11', 'UP', 'N64_CIC_DATA'), ('n64_si_dq', 'A6', 'UP', 'N64_JOYBUS'),
    ('n64_int_n', 'B6', 'UP', 'N64_INT_N'),
]


def _n64_net(port):
    return 'fpga_n64_' + port[4:].replace('[', '').replace(']', '')


PINMAP = []   # dicts: port ball iotype attrs net label group note
for port, ball, pull, edge in N64:
    PINMAP.append(dict(port=port, ball=ball, iotype='LVCMOS33', attrs=f'PULLMODE={pull}', net=_n64_net(port),
                       label=edge, group='n64',
                       note=f'via N64 bus switch to root {edge}; pull as SummerCart64 sc64.lpf'))

CART_B2 = ['C18', 'D17', 'E16', 'F16', 'D18', 'E17', 'E18', 'F18', 'F17', 'G18', 'G16', 'H16', 'H18', 'H17',
           'J17', 'J16', 'K16', 'K17', 'C20', 'D19', 'D20', 'E19', 'E20', 'F19', 'F20', 'G20', 'G19', 'H20',
           'J18', 'K18', 'J19', 'K19']
for i in range(24):
    PINMAP.append(dict(port=f'cart_address[{i}]', ball=CART_B2[i], iotype='LVCMOS33', attrs='', net=f'cart_address{i}',
                       label='cart_address[0..23]', group='cart', note='U201-U203 B side (cart sheet)'))
for i in range(8):
    PINMAP.append(dict(port=f'cart_pa[{i}]', ball=CART_B2[24 + i], iotype='LVCMOS33', attrs='', net=f'cart_pa{i}',
                       label='cart_pa[0..7]', group='cart', note='U204 B side (cart sheet)'))
CART_B3 = [  # port, ball, attrs, cart-sheet label, note
    ('cart_sysclk', 'L20', '', 'cart_sysclk', 'U206 B; SNES master clock out (DCSC output)'),
    ('cart_phi2', 'M20', '', 'cart_phi2', 'U205 B'), ('cart_refresh', 'L19', '', 'cart_refresh', 'U205 B'),
    ('cart_rd_n', 'M19', '', 'cart_rd_n', 'U205 B')] + [
    (f'cart_data[{i}]', b, 'PULLMODE=DOWN', f'cart_data{i}', 'U207 B; FPGA drives only while data_dir=1')
    for i, b in enumerate(['L16', 'L17', 'L18', 'M18', 'N16', 'M17', 'N18', 'P17'])] + [
    ('cart_wr_n', 'N17', '', 'cart_wr_n', 'U205 B'), ('cart_prd_n', 'P16', '', 'cart_prd_n', 'U205 B'),
    ('cart_pwr_n', 'R16', '', 'cart_pwr_n', 'U205 B'), ('cart_romsel_n', 'R17', '', 'cart_romsel_n', 'U205 B'),
    ('cart_wramsel_n', 'T16', '', 'cart_wramsel_n', 'U205 B'),
    ('ctl_oe_n', 'N19', '', 'ctl_oe_n', 'U210 input (0 = translators on)'),
    ('data_oe_n', 'N20', '', 'data_oe_n', 'U212 input (0 = data octet on)'),
    ('data_dir', 'P19', '', 'data_dir', 'U213 input (1 = FPGA drives)'),
    ('snes_cic_oe_n', 'P18', '', 'cic_oe_n', 'U211 input'),
    ('snes_cic_clk', 'P20', '', 'cic_clk', 'U206 B'),
    ('snes_cic_slave_reset', 'R20', '', 'cic_slave_reset', 'U206 B'),
    ('cic_data0', 'T20', 'PULLMODE=DOWN', 'cic_data0', 'U215 A (100k pull-down on cart sheet)'),
    ('cic_data0_dir', 'U20', '', 'cic_data0_dir', 'U215 DIR (1 = drive cartridge)'),
    ('cic_data1', 'T19', 'PULLMODE=DOWN', 'cic_data1', 'U216 A (100k pull-down on cart sheet)'),
    ('cic_data1_dir', 'R18', '', 'cic_data1_dir', 'U216 DIR'),
    ('cart_reset_pull_n', 'U19', '', 'cart_reset_pull_n', 'U214 input (1 = release /RESET); board-top edit'),
    ('cart_irq_n', 'T18', '', 'cart_irq_n', 'U209 1Y1'),
    ('cart_reset_n_sense', 'U18', '', 'cart_reset_n_sense', 'U209 1Y2'),
    ('expand_sense', 'U17', '', 'expand_sense', 'U209 1Y3; new board-top input')]
for port, ball, attrs, label, note in CART_B3:
    exp = {'cart_data': 'cart_data[0..7]'}.get(port.split('[')[0], label)
    PINMAP.append(dict(port=port, ball=ball, iotype='LVCMOS33', attrs=attrs, net=label, label=exp, group='cart', note=note))

OTHER = [  # port, ball, iotype, attrs, net == exported label, group, note
    ('osc_25', 'G2', 'LVCMOS33', 'PULLMODE=NONE', 'osc_25', 'clock', 'PCLKT6_1: primary clock pin; housekeeping + host PLL CLKI via primary clock'),
    ('si_clk0', 'H2', 'LVCMOS33', 'PULLMODE=NONE', 'si_clk0', 'clock', 'PCLKT6_0: DCSC CLK0 (NTSC)'),
    ('si_clk1', 'G3', 'LVCMOS33', 'PULLMODE=NONE', 'si_clk1', 'clock', 'PCLKT7_1: DCSC CLK1 (PAL)'),
    ('si_scl', 'E4', 'LVCMOS33', 'PULLMODE=UP', 'si_scl', 'clock', 'open drain (board-top edit); bus pull-ups on clock sheet'),
    ('si_sda', 'F4', 'LVCMOS33', 'PULLMODE=UP', 'si_sda', 'clock', 'open drain (board-top edit)'),
    ('adc_bck', 'J4', 'LVCMOS33', 'PULLMODE=DOWN', 'adc_bck', 'av', 'GR_PCLK6_0; ADC is I2S master (reserved port)'),
    ('adc_lrck', 'J3', 'LVCMOS33', 'PULLMODE=DOWN', 'adc_lrck', 'av', 'GR_PCLK6_1 (reserved port)'),
    ('adc_dout', 'K3', 'LVCMOS33', 'PULLMODE=DOWN', 'adc_dout', 'av', 'reserved port'),
    ('host_3v3_ok', 'K2', 'LVCMOS33', 'PULLMODE=DOWN', 'host_3v3_ok', 'power', 'floating = not ok'),
    ('fpga_rails_ok', 'J1', 'LVCMOS33', 'PULLMODE=DOWN', 'fpga_rails_ok', 'power', 'also holds PROGRAMN low via U407'),
    ('cart_5v_ok', 'H1', 'LVCMOS33', 'PULLMODE=DOWN', 'cart_5v_ok', 'power', 'floating = not ok'),
    ('iface_rail_ok', 'K1', 'LVCMOS33', 'PULLMODE=DOWN', 'iface_rail_ok', 'power', 'floating = not ok'),
    ('efuse_fault_n', 'K4', 'LVCMOS33', 'PULLMODE=DOWN', 'efuse_fault_n', 'power', 'floating = fault'),
    ('overtemp', 'K5', 'LVCMOS33', 'PULLMODE=UP', 'overtemp', 'power', 'floating = overtemp; VREF1_6 ball used as I/O'),
    ('board_reset_n', 'L4', 'LVCMOS33', 'PULLMODE=DOWN', 'board_reset_n', 'power', 'floating = reset'),
    ('cart_5v_enable', 'L5', 'LVCMOS33', '', 'cart_5v_enable', 'power', 'power sheet keeps its own default-off pull-down'),
    ('iface_rail_enable', 'M5', 'LVCMOS33', '', 'iface_rail_enable', 'power', 'power sheet keeps its own default-off pull-down'),
    ('flash_cs_n', 'R2', 'LVCMOS33', '', 'flash_cs_n', 'flash', 'CSSPIN (bank 8); GPIO after configuration (MASTER_SPI_PORT=DISABLE default)'),
    ('flash_dq[0]', 'W2', 'LVCMOS33', '', 'flash_dq0', 'flash', 'D0/MOSI -> W25Q128JV DI/IO0 (pin 5)'),
    ('flash_dq[1]', 'V2', 'LVCMOS33', '', 'flash_dq1', 'flash', 'D1/MISO -> DO/IO1 (pin 2)'),
    ('flash_dq[2]', 'Y2', 'LVCMOS33', '', 'flash_dq2', 'flash', 'D2 -> IO2 (pin 3), 10k pull-up'),
    ('flash_dq[3]', 'W1', 'LVCMOS33', '', 'flash_dq3', 'flash', 'D3 -> IO3 (pin 7), 10k pull-up'),
    ('led_status', 'B1', 'LVCMOS33', 'DRIVE=8', 'led_status', 'misc', 'D401 via R (active high)'),
]
LOCAL_ONLY = {'flash_cs_n', 'flash_dq0', 'flash_dq1', 'flash_dq2', 'flash_dq3', 'led_status'}
for port, ball, iot, attrs, net, group, note in OTHER:
    PINMAP.append(dict(port=port, ball=ball, iotype=iot, attrs=attrs, net=net,
                       label='' if net in LOCAL_ONLY else net, group=group, note=note))
# LVCMOS33D complements: ball -> net (not LPF ports; nextpnr drives them from the true pad).
# Empty since rev 0.5-fpga: the HDMI TMDS pairs (A16/B16, A14/C14, A12/A13, A17/B18) are gone; the
# picture goes to the console over the cartridge bus (docs/design/console-video-path.md).
DIFF_COMP = {}
# Dedicated configuration / JTAG balls (Lattice pinout: bank 8 / "40")
DEDICATED = {'U3': 'fpga_mclk', 'U4': GND, 'T4': 'fpga_cfg1', 'R4': GND, 'W3': 'fpga_programn',
             'V3': 'fpga_initn', 'Y3': 'fpga_done', 'T5': 'jtag_tck', 'R5': 'jtag_tdi', 'V4': 'jtag_tdo',
             'U5': 'jtag_tms'}
FREQ = [('PORT', 'osc_25', '25'), ('PORT', 'si_clk0', '21.477272'), ('PORT', 'si_clk1', '21.28137'),
        ('NET', 'clk_snes', '21.477272')]

# N64 bus switches: SN74CB3Q3384A (TI SCDS114E Figure 3-1). (A pin, B pin) per channel.
CB3Q_CH = [('3', '2'), ('4', '5'), ('7', '6'), ('8', '9'), ('11', '10'),
           ('14', '15'), ('17', '16'), ('18', '19'), ('21', '20'), ('22', '23')]
N64_SW = ['U402', 'U403', 'U404']
SW_OE = 'n64_sw_oe_n'


def hier_ports():
    """(name, shape) for every hierarchical label on the sheet."""
    ports = [(e[3], 'bidirectional') for e in N64] + [('HOST_3V3', 'input')]
    seen = set()
    for p in PINMAP:
        if p['group'] == 'n64' or not p['label'] or p['label'] in seen:
            continue
        seen.add(p['label'])
        shape = 'bidirectional'
        base = p['port'].split('[')[0]
        if base in ('osc_25', 'si_clk0', 'si_clk1', 'adc_bck', 'adc_lrck', 'adc_dout',
                    'host_3v3_ok', 'fpga_rails_ok', 'cart_5v_ok', 'iface_rail_ok', 'efuse_fault_n', 'overtemp',
                    'board_reset_n', 'cart_irq_n', 'cart_reset_n_sense', 'expand_sense'):
            shape = 'input'
        elif base in ('cart_data', 'cic_data0', 'cic_data1', 'si_sda', 'si_scl'):
            shape = 'bidirectional'
        else:
            shape = 'output'
        ports.append((p['label'], shape))
    ports += [(n, 'output') for n in DIFF_COMP.values()]
    ports += [('jtag_tck', 'input'), ('jtag_tms', 'input'), ('jtag_tdi', 'input'), ('jtag_tdo', 'output'),
              ('TARGET_VREF', 'output')]
    ports += [(GND, 'input'), (V11, 'input'), (V25, 'input'), (V33, 'input')]
    return ports


def lpf_text():
    out = io.StringIO()
    w = out.write
    w('# SN64 board pin constraints for sn64_board_top (LFE5U-85F, CABGA381).\n'
      '# GENERATED by hardware/sn64/tools/add_fpga_sheet.py from the same pin table as\n'
      '# hardware/sn64/fpga.kicad_sch and hardware/sn64/interfaces/fpga-pin-map.csv;\n'
      '# checked by hardware/sn64/tools/verify_fpga_sheet.py. Do not edit by hand.\n'
      '# Port names follow sn64_board_top AFTER the integration edit listed in\n'
      '# docs/design/fpga-schematic.md (cart_data inout, si_scl/si_sda open drain,\n'
      '# cart_reset_pull_n, expand_sense, n64_si_dq, n64_int_n, adc_*). No HDMI pins since rev 0.5-fpga.\n'
      '# Every bank VCCIO = 3.3 V (FPGA_3V3). Balls: Lattice ECP5U-85 pinout CSV rev 1.0.\n'
      '# DRAFT: schematic-level pinout, no PCB escape routing or SI review yet.\n')
    w('SYSCONFIG CONFIG_IOVOLTAGE=3.3 COMPRESS_CONFIG=ON;\n')
    for kind, name, mhz in FREQ:
        w(f'FREQUENCY {kind} "{name}" {mhz} MHZ;\n')
    group = None
    for p in PINMAP:
        if p['group'] != group:
            group = p['group']
            w(f'# --- {group} ---\n')
        w(f'LOCATE COMP "{p["port"]}" SITE "{p["ball"]}";\n')
        attrs = (' ' + p['attrs']) if p['attrs'] else ''
        w(f'IOBUF PORT "{p["port"]}" IO_TYPE={p["iotype"]}{attrs};\n')
    return out.getvalue()


def csv_text(bank_of):
    out = io.StringIO()
    wr = csv.writer(out, lineterminator='\n')
    wr.writerow(['port', 'ball', 'bank', 'IO_TYPE', 'lpf_attributes', 'fpga_net', 'sheet_label', 'group', 'notes'])
    for p in PINMAP:
        wr.writerow([p['port'], p['ball'], bank_of[p['ball']], p['iotype'], p['attrs'], p['net'], p['label'],
                     p['group'], p['note']])
    for ball, net in DIFF_COMP.items():
        wr.writerow(['(LVCMOS33D complement)', ball, bank_of[ball], 'LVCMOS33D', '', net, net, 'av',
                     'complement pad of the pair above; driven by nextpnr from the true pad'])
    for ball, net in DEDICATED.items():
        wr.writerow(['(dedicated)', ball, 'JTAG (VCCIO8)' if net.startswith('jtag_') else '8', '-', '', net,
                     net if net.startswith('jtag_') else '', 'config', 'sysCONFIG/JTAG dedicated ball'])
    return out.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--kicad-share', type=Path, required=True)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--validation-copy', type=Path, help='copy hardware/sn64 here (under build/) and attach the sheet to the copy')
    ap.add_argument('--attach-real-root', action='store_true',
                    help='INTEGRATION STEP ONLY: apply the same attachment to hardware/sn64/sn64.kicad_sch in place')
    a = ap.parse_args()
    dest = ROOT / SHEET_FILE
    if dest.exists() and not a.force and not a.validation_copy:
        ap.error('fpga.kicad_sch exists; use KiCad to edit, or --force to replace the initial draft')

    root = parse(ROOT / 'sn64.kicad_sch')
    root_uuid = str(get(root, 'uuid')[1])
    sheet_uuid = uid('sheet')
    page_uuid = uid('page')

    if a.validation_copy:
        attach_copy(a.validation_copy, root_uuid, sheet_uuid)
        return
    if a.attach_real_root:
        assert dest.exists(), 'author the sheet first'
        attach(ROOT, root_uuid, sheet_uuid)
        return

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

    def unit_pins(sym, unit):
        out = []
        for u in items(sym, 'symbol'):
            m = re.match(r'.*_(\d+)_(\d+)$', str(u[1]))
            if m and int(m.group(1)) in (0, unit):
                out += items(u, 'pin')
        return out

    def place(ref, lib_id, value, x, y, nets, fp='', unit=1, fields=None, all_units=None):
        sym = load(lib_id)
        pins = unit_pins(sym, unit)
        if all_units is None:
            assert {str(get(p, 'number')[1]) for p in pins} == set(nets), (ref, sorted(nets))
        small = lib_id in ('Device:R', 'Device:C', 'Connector:TestPoint', 'power:PWR_FLAG', 'Device:LED',
                           'Device:FerriteBead_Small')
        if small:
            rx, ry, vx, vy, just = x + 2.54, y - 1.27, x + 2.54, y + 1.27, 'left'
        else:
            tops = [y - float(get(p, 'at')[2]) for p in pins]
            rx, ry, vx, vy, just = x - 10.16, min(tops) - 12.7, x - 10.16, min(tops) - 10.16, 'left'
        hidden = ref.startswith('#')
        key = ref + (f':u{unit}' if unit != 1 else '')
        out = [f'(symbol (lib_id {q(lib_id)}) (at {g(x)} {g(y)} 0) (unit {unit}) (exclude_from_sim no) '
               f'(in_bom {"no" if hidden else "yes"}) (on_board {"no" if hidden else "yes"}) (dnp no) (uuid {q(uid(key))})',
               prop('Reference', ref, rx, ry, hidden, just), prop('Value', value, vx, vy, hidden, just),
               prop('Footprint', fp, x, y, True), prop('Datasheet', (fields or {}).get('Datasheet', ''), x, y, True)]
        for k, v in (fields or {}).items():
            if k != 'Datasheet':
                out.append(prop(k, v, x, y, True))
        for pin in pins:
            out.append(f'(pin {q(get(pin, "number")[1])} (uuid {q(uid(ref + ":" + str(get(pin, "number")[1])))}))')
        out.append(f'(instances (project "sn64" (path {q("/" + root_uuid + "/" + sheet_uuid)} (reference {q(ref)}) (unit {unit}))))')
        parts.append(' '.join(out) + ')')
        seen = {}
        for pin in pins:
            number = str(get(pin, 'number')[1])
            net = nets[number]
            at = get(pin, 'at')
            px, py, angle = x + float(at[1]), y - float(at[2]), int(float(at[3]))
            role = ref + ':' + number
            if (px, py) in seen:
                assert seen[(px, py)] == net, (ref, number, net, seen[(px, py)])   # stacked pins share a net
                continue
            seen[(px, py)] = net
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
        return pins

    # ------------------------------------------------------------------ FPGA
    fpga_id = 'FPGA_Lattice:LFE5U-85F-6BG381x'
    sym = load(fpga_id)
    ball_net = {}
    for p in PINMAP:
        ball_net[p['ball']] = p['net']
    ball_net.update(DIFF_COMP)
    ball_net.update(DEDICATED)
    extent_x = 25.4
    unit_pos = {1: (60.96, 180.34), 9: (60.96, 360.68), 2: (203.2, 101.6), 3: (203.2, 266.7),
                4: (355.6, 101.6), 5: (355.6, 271.78), 6: (508.0, 101.6), 7: (508.0, 271.78), 8: (203.2, 424.18)}
    fpga_fields = {'Datasheet': 'https://www.latticesemi.com/view_document?document_id=50461',
                   'Alternate': 'LFE5U-85F-8BG381I (same CABGA381 ball map; re-run timing for grade 8)',
                   'Pinout source': 'Lattice ECP5U-85 pinout CSV rev 1.0 (document 50487)'}
    for unit in range(1, 10):
        pins = unit_pins(sym, unit)
        nets = {}
        for pin in pins:
            num, name = str(get(pin, 'number')[1]), str(get(pin, 'name')[1])
            base = name.split('/')[0]
            if base in POWER_NETS:
                nets[num] = POWER_NETS[base]
            elif base == 'RESERVED':
                nets[num] = None          # DS-02012 4.1: reserved, not connected to anything
            else:
                nets[num] = ball_net.get(num)   # unused user I/O -> no-connect
        x, y = unit_pos[unit]
        place('U401', fpga_id, 'LFE5U-85F-6BG381C', x, y, nets, 'Package_BGA:Lattice_caBGA-381_17x17mm_Layout20x20_P0.8mm',
              unit=unit, fields=fpga_fields, all_units=True)

    # ------------------------------------------------ decoupling (TN-02038 Table 3.1)
    caps = []
    for i in range(20):
        caps.append((V11, '100nF', 'VCC ball'))
    caps += [(V11, '10uF', 'VCC bulk')] * 3
    caps += [(VAUX, '100nF', 'VCCAUX ball')] * 4 + [(VAUX, '10uF', 'VCCAUX bulk')]
    for bank, n in [(0, 2), (1, 2), (2, 3), (3, 3), (6, 3), (7, 3), (8, 2)]:
        caps += [(V33, '100nF', f'VCCIO{bank} ball')] * n + [(V33, '10uF', f'VCCIO{bank} bulk')]
    c_start = len(caps)
    caps += [(V33, '100nF', 'U402 VCC'), (V33, '100nF', 'U403 VCC'), (V33, '100nF', 'U404 VCC'),
             (V33, '100nF', 'U405 flash VCC'), (V33, '100nF', 'U406 VCC'), (V33, '100nF', 'U407 VCC')]
    for i, (net, value, why) in enumerate(caps):
        big = value == '10uF'
        place(f'C{401 + i}', 'Device:C', value + (' 10V X5R' if big else ' 16V X7R'),
              660.4 + 15.24 * (i % 16), 101.6 + 20.32 * (i // 16), {'1': net, '2': GND},
              'Capacitor_SMD:C_0603_1608Metric' if big else 'Capacitor_SMD:C_0402_1005Metric',
              fields={'Purpose': why})
    place('FB401', 'Device:FerriteBead_Small', 'BLM18PG121SN1D', 660.4, 60.96, {'1': V25, '2': VAUX},
          'Inductor_SMD:L_0603_1608Metric', fields={'LCSC': 'C14709', 'Purpose': 'VCCAUX filter, TN-02038 Figure 3.1'})

    # ------------------------------------------------ configuration + flash
    R0402 = 'Resistor_SMD:R_0402_1005Metric'
    res = [  # ref, value, n1, n2, purpose
        ('R401', '4.7k', V33, 'fpga_cfg1', 'CFG1=1 (MSPI 010), TN-02038 Table 6.2'),
        ('R402', '4.7k', V33, 'fpga_programn', 'PROGRAMN pull-up, TN-02038 Table 6.2'),
        ('R403', '4.7k', V33, 'fpga_initn', 'INITN pull-up'),
        ('R404', '4.7k', V33, 'fpga_done', 'DONE pull-up'),
        ('R405', '33', 'fpga_mclk', 'flash_sck', 'MCLK series, 22-80 ohm near the FPGA (TN-02038 Table 6.2 note 1)'),
        ('R406', '1k', V33, 'flash_sck', 'MCLK pull-up 510R-1k (TN-02038 Table 6.2)'),
        ('R407', '4.7k', V33, 'flash_cs_n', 'CSSPIN pull-up 4.7-10k, place at the flash'),
        ('R408', '10k', V33, 'flash_dq2', 'IO2 pull-up (bootrom-flash.md; ULX3S R11)'),
        ('R409', '10k', V33, 'flash_dq3', 'IO3 pull-up (bootrom-flash.md; ULX3S R12)'),
        ('R410', '4.7k', V33, 'jtag_tdi', 'TDI pull-up, TN-02038 Table 6.1'),
        ('R411', '4.7k', V33, 'jtag_tms', 'TMS pull-up'),
        ('R412', '4.7k', V33, 'jtag_tdo', 'TDO pull-up'),
        ('R413', '4.7k', 'jtag_tck', GND, 'TCK pull-down'),
        ('R414', '0', V33, 'TARGET_VREF', 'TARGET_VREF = VCCIO8 rail (JTAG bank) for the USB sheet translator VCCB'),
        ('R415', '100k', 'fpga_rails_ok', GND, 'U407 input default low = hold PROGRAMN'),
        ('R416', '10k', 'HOST_3V3', 'host_det', 'host-presence divider (provisional)'),
        ('R417', '33k', 'host_det', GND, 'host-presence divider: switch on at HOST_3V3 1.95-2.44 V (provisional)'),
        ('R418', '10k', V33, SW_OE, 'SCDS114E: OE tied to VCC through a pull-up (default off)'),
        ('R419', '1k', 'led_status', 'led_a', 'status LED current ~1.3 mA'),
    ]
    for i, (ref, value, n1, n2, why) in enumerate(res):
        place(ref, 'Device:R', value, 660.4 + 15.24 * (i % 16), 322.58 + 20.32 * (i // 16), {'1': n1, '2': n2}, R0402,
              fields={'Purpose': why})
    place('D401', 'Device:LED', 'LED green 0603', 660.4 + 15.24 * 4, 365.76, {'1': GND, '2': 'led_a'},
          'LED_SMD:LED_0603_1608Metric', fields={'Purpose': 'status (led_status)'})
    tps = [('TP401', 'fpga_programn', 'PROGRAMN'), ('TP402', 'fpga_initn', 'INITN'), ('TP403', 'fpga_done', 'DONE'),
           ('TP404', V11, 'FPGA_1V1'), ('TP405', VAUX, 'VCCAUX'), ('TP406', V33, 'FPGA_3V3'),
           ('TP407', 'flash_sck', 'FLASH_SCK'), ('TP408', SW_OE, 'N64_SW_OE_N')]
    for i, (ref, net, value) in enumerate(tps):
        place(ref, 'Connector:TestPoint', value, 660.4 + 15.24 * i, 396.24, {'1': net}, 'TestPoint:TestPoint_Pad_D1.0mm')
    place('U405', 'Memory_Flash:W25Q128JVS', 'W25Q128JVSIQ', 660.4, 469.9,
          {'1': 'flash_cs_n', '2': 'flash_dq1', '3': 'flash_dq2', '4': GND, '5': 'flash_dq0', '6': 'flash_sck',
           '7': 'flash_dq3', '8': V33}, 'Package_SO:SOIC-8_5.3x5.3mm_P1.27mm',
          fields={'Datasheet': 'https://www.winbond.com/resource-files/w25q128jv%20revf%2003272018%20plus.pdf',
                  'LCSC': 'C97521', 'Note': 'IQ ordering option: QE=1 factory fixed (rev F 7.1.4)'})
    place('U406', '74xGxx:74LVC1G14', 'SN74LVC1G14DBVR', 746.76, 469.9,
          {'1': None, '2': 'host_det', '3': GND, '4': SW_OE, '5': V33}, 'Package_TO_SOT_SMD:SOT-23-5',
          fields={'Datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc1g14.pdf', 'LCSC': 'C7835'})
    place('U407', '74xGxx:74LVC1G07', 'SN74LVC1G07DBVR', 822.96, 469.9,
          {'1': None, '2': 'fpga_rails_ok', '3': GND, '4': 'fpga_programn', '5': V33}, 'Package_TO_SOT_SMD:SOT-23-5',
          fields={'Datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc1g07.pdf', 'LCSC': 'C7829'})

    # ------------------------------------------------ N64 bus switches
    sigs = [(e[3], _n64_net(e[0])) for e in N64]
    for k, ref in enumerate(N64_SW):
        nets = {'1': SW_OE, '13': SW_OE, '12': GND, '24': V33}
        for c, (pa, pb) in enumerate(CB3Q_CH):
            idx = 10 * k + c
            if idx < len(sigs):
                nets[pa], nets[pb] = sigs[idx]
            else:
                nets[pa] = nets[pb] = None     # spare FET channel: open
        place(ref, '74xx:SN74CB3Q3384APW', 'SN74CB3Q3384APWR', 203.2 + 101.6 * k, 594.36, nets,
              'Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm',
              fields={'Datasheet': 'https://www.ti.com/lit/ds/symlink/sn74cb3q3384a.pdf', 'LCSC': 'C469874'})

    # ERC rail-origin marker: FPGA_1V1/2V5/3V3 are flagged on the power sheet (#FLG302-#FLG304, bucks
    # feed them through inductors), so #FLG401-#FLG403 were removed at the round-3 integration (two
    # PWR_FLAGs on one net are an ERC error). #FLG404 stays: FPGA_VCCAUX is fed only through FB401.
    place('#FLG404', 'power:PWR_FLAG', 'PWR_FLAG', 914.4 + 20.32 * 3, 60.96, {'1': VAUX})

    # ------------------------------------------------ hierarchical ports
    def port(name, shape, x, y):
        bus = '[' in name
        parts.append(f'(hierarchical_label {q(name)} (shape {shape}) (at {g(x)} {g(y)} 180) '
                     f'(effects (font (size 1.27 1.27)) (justify right)) (uuid {q(uid("hl:" + name))}))')
        kind = 'bus' if bus else 'wire'
        parts.append(f'({kind} (pts (xy {g(x)} {g(y)}) (xy {g(x + 7.62)} {g(y)})) (stroke (width 0) (type default)) '
                     f'(uuid {q(uid("pw:" + name))}))')
        parts.append(f'(label {q(name)} (at {g(x + 7.62)} {g(y)} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) '
                     f'(uuid {q(uid("pl:" + name))}))')
    for i, (name, shape) in enumerate(hier_ports()):
        port(name, shape, 1016.0 + 60.96 * (i // 60), 60.96 + 5.08 * (i % 60))

    notes = [
        txt('SN64 FPGA - LFE5U-85F CABGA381, CONFIGURATION FLASH, JTAG, N64 HOST ISOLATION', 20.32, 17.78, 2.54),
        txt('Rails: VCC = FPGA_1V1 (1.1 V, DS-02012 Table 3.2), VCCAUX = FPGA_2V5 through FB401 (TN-02038 Figure 3.1), '
            'every VCCIO0/1/2/3/6/7/8 = FPGA_3V3.\n'
            'Bank plan: 0 = N64 PI/CIC/SI behind the bus switches (top bank, hot-socket capable), 1 = spare (HDMI removed in 0.5-fpga: '
            'video goes to the console over the cartridge bus), 2+3 = cartridge translators B side, 6+7 = clocks, Si5351 I2C, ADC, '
            'power control, LED, 8 = configuration flash.\n'
            'GND: all 113 GND balls (the LFE5U pinout lists the SERDES-supply positions as GND). RESERVED (10 balls): not connected '
            '(DS-02012 4.1). Unused user I/O: open (tri-state + weak pull-down after configuration, TN-02039 4.5).',
            20.32, 25.4),
        txt('Configuration: CFG[2:0] = 010 Master SPI (CFG0/CFG2 to GND, CFG1 4.7k to VCCIO8). PROGRAMN/INITN/DONE 4.7k to VCCIO8 '
            '(TN-02038 Table 6.2).\nU307 holds PROGRAMN low until fpga_rails_ok (DS-02012 3.5: MSPI needs VCCIO8 above the flash VIH '
            'before VCC/VCCAUX reach VPORUP, or PROGRAMN/INITN held low).\n'
            'U405 W25Q128JVSIQ: QE=1 factory fixed (IQ option), EBh = 2 mode + 4 dummy clocks, tCLQV 6 ns; bitstream at 0x000000, '
            'N64 bootstrap at 0x400000 (bootrom-flash.md).\n'
            'MCLK: R405 33R series at the FPGA + R406 1k pull-up; CSSPIN R407 4.7k at the flash; IO2/IO3 10k pull-ups. '
            'JTAG: TDI/TMS/TDO 4.7k up, TCK 4.7k down (TN-02038 Table 6.1); TARGET_VREF = VCCIO8 rail via R414.',
            20.32, 43.18),
        txt('N64 HOST ISOLATION: U402-U404 SN74CB3Q3384A FET bus switches (A = N64 edge, B = FPGA bank 0), VCC = FPGA_3V3.\n'
            'OE = NOT(HOST_3V3 present): U406 Schmitt inverter on the R416/R417 divider. USB-only (HOST_3V3 absent): OE high, switch off.\n'
            'FPGA_3V3 absent: switch unpowered, "isolation during power off" + Ioff (TI SCDS114E). R418 keeps OE at VCC (datasheet).\n'
            'No series resistors: SummerCart64 a1e7996d connects J_N1 straight to the FPGA (netlist checked).',
            20.32, 640.08),
        txt(f'DRAFT {REV}: schematic only - no PCB, no SI or power-integrity analysis, no hardware test. FPGA_1V1/2V5/3V3 come from the power sheet '
            '(its #FLG302-#FLG304 are their ERC origins). #FLG404 marks FPGA_VCCAUX, fed '
            'only through FB401.\nPin map: interfaces/fpga-pin-map.csv; constraints: '
            'fpga/constraints/sn64_board.lpf; doc: docs/design/fpga-schematic.md.', 20.32, 680.72)]
    contents = (f'(kicad_sch (version 20250114) (generator "sn64_fpga_authoring") (uuid {q(page_uuid)}) (paper "A0") '
                f'(title_block (title "SN 64 - FPGA") (date "2026-09-29") (rev {q(REV)}) (company "SN 64") '
                f'(comment 1 "DESIGN DRAFT - NOT FOR MANUFACTURE"))\n(lib_symbols\n'
                + '\n'.join(dump(s) for s in libs.values()) + ')\n' + '\n'.join(parts + notes)
                + f'\n(sheet_instances (path {q("/" + root_uuid + "/" + sheet_uuid)} (page "4"))) (embedded_fonts no))')
    save(dest, contents)

    bank_of = lattice_banks()
    save(ROOT / 'interfaces' / 'fpga-pin-map.csv', csv_text(bank_of))
    save(REPO / 'fpga' / 'constraints' / 'sn64_board.lpf', lpf_text())
    n_sym = sum(1 for p in parts if p.startswith('(symbol (lib_id'))
    print(f'Authored FPGA sheet: {n_sym} symbol units, {len(PINMAP)} mapped ports, {len(fps)} footprints; '
          f'wrote fpga-pin-map.csv and sn64_board.lpf')


def lattice_banks():
    """Bank per user-I/O ball (BANK_BALLS below, from the Lattice pinout CSV)."""
    banks = {}
    for bank, balls in BANK_BALLS.items():
        for b in balls.split():
            banks[b] = bank
    return banks


# Lattice ECP5U-85 pinout CSV rev 1.0, CABGA381 column: user I/O balls per bank.
BANK_BALLS = {
    '0': 'A6 B6 E6 D6 E7 D7 C6 C7 E8 D8 C8 B8 A7 A8 D9 E9 C9 D10 E10 B9 C10 A9 B10 A10 A11 B11 C11',
    '1': 'D11 E11 B12 C12 D12 E12 A12 A13 B13 C13 D13 E13 A14 C14 D14 E14 A15 B15 C15 D15 E15 A16 B16 C16 D16 '
         'B17 C17 A17 B18 A18 B19 A19 B20',
    '2': 'C18 D17 E16 F16 D18 E17 E18 F18 F17 G18 G16 H16 H18 H17 J17 J16 K16 K17 C20 D19 D20 E19 E20 F19 F20 G20 '
         'G19 H20 J18 K18 J19 K19 J20 K20',
    '3': 'L20 M20 L19 M19 L16 L17 L18 M18 N16 M17 N18 P17 N17 P16 R16 R17 T16 N19 N20 P19 P18 P20 R20 T20 U20 T19 '
         'R18 U19 T18 U18 U17 U16 T17',
    '6': 'G2 F1 H2 G1 J4 J5 J3 K3 K2 J1 H1 K1 K4 K5 L4 L5 M5 M4 N5 N4 P5 N3 M3 L3 L2 N2 M1 L1 N1 P1 P2 P3 P4',
    '7': 'A4 A5 B5 C5 C4 B4 A3 B3 E4 D5 C3 D3 F4 E3 E5 F5 A2 B1 B2 C2 C1 D1 D2 E1 H4 G5 H5 H3 G3 F3 F2 E2',
    '8': 'R1 T1 U1 V1 W1 Y2 V2 W2 T2 U2 R2 R3 T3',
}


def attach_copy(dest, root_uuid, sheet_uuid):
    dest = dest.resolve()
    assert (REPO / 'build') in dest.parents, 'validation copies live under build/'
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns('*-backups', 'fp-info-cache', '__pycache__'))
    attach(dest, root_uuid, sheet_uuid)


def attach(dest, root_uuid, sheet_uuid):
    """Append the FPGA sheet symbol to dest/sn64.kicad_sch (A3 -> A2 page; sheet at x=449.58 mm,
    right of the cartridge sheet), label its N64/HOST_3V3/GND/cartridge pins, replace the cartridge
    sheet's FPGA-side root no-connects by labels, and no-connect every still-pending pin."""
    rpath = dest / 'sn64.kicad_sch'
    text = rpath.read_text(encoding='utf-8')
    assert sheet_uuid not in text, 'the real root already holds the FPGA sheet'
    # Cartridge sheet FPGA-side pins: replace their no-connect markers by labels.
    lines = text.rstrip().split('\n')
    cart_nc = {}
    for name in [p for p, _ in hier_ports()]:
        cart_nc[json.dumps(str(uuid.uuid5(CART_NS, 'root-nc:' + name)))] = name
    replaced = set()
    for i, line in enumerate(lines):
        m = re.match(r'\(no_connect \(at ([\d.]+) ([\d.]+)\) \(uuid ("[^"]+")\)\)$', line)
        if m and m.group(3) in cart_nc:
            name = cart_nc[m.group(3)]
            lines[i] = (f'(label {q(name)} (at {m.group(1)} {m.group(2)} 180) (effects (font (size 1.016 1.016)) '
                        f'(justify right bottom)) (uuid {q(uid("copy-cart-label:" + name))}))')
            replaced.add(name)
    text = '\n'.join(lines)
    text = text.replace('(paper "A3")', '(paper "A2")', 1)
    connect = {e[3] for e in N64} | {'HOST_3V3', GND} | replaced
    sx, sy, w = 449.58, 30.48, 30.48
    pins, marks = [], []
    ports = hier_ports()
    for i, (name, shape) in enumerate(ports):
        py = sy + 5.08 + 2.54 * i
        pins.append(f'(pin {q(name)} {shape} (at {g(sx)} {g(py)} 180) (effects (font (size 1.27 1.27)) (justify left)) '
                    f'(uuid {q(uid("root-pin:" + name))}))')
        if name in connect:
            marks.append(f'(label {q(name)} (at {g(sx)} {g(py)} 180) (effects (font (size 1.016 1.016)) (justify right bottom)) '
                         f'(uuid {q(uid("root-label:" + name))}))')
        else:
            marks.append(f'(no_connect (at {g(sx)} {g(py)}) (uuid {q(uid("root-nc:" + name))}))')
    h = round(5.08 + 2.54 * len(ports) + 2.54, 2)
    block = (f'(sheet (at {g(sx)} {g(sy)}) (size {g(w)} {g(h)}) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0)) '
             f'(uuid {q(sheet_uuid)}) ' + prop('Sheetname', SHEET_NAME, sx, sy - 1.27, justify='left bottom')
             + prop('Sheetfile', SHEET_FILE, sx, sy + h + 1.27, justify='left top') + ' ' + ' '.join(pins)
             + f' (instances (project "sn64" (path {q("/" + root_uuid)} (page "4")))))\n' + '\n'.join(marks))
    text = text.rstrip()[:-1] + '\n' + block + '\n)'
    save(rpath, text)
    print(f'{dest}: FPGA sheet attached with {len(ports)} pins '
          f'({len([n for n, _ in ports if n in connect])} connected), {len(replaced)} cartridge-sheet no-connects replaced by labels')


if __name__ == '__main__':
    main()
