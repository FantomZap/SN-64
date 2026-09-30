"""Independent static check of the clock / cartridge-audio child sheet.

Exports a fresh KiCad netlist and ERC report of a project that has
av-clock.kicad_sch attached to its root, and checks them against tables kept
HERE (datasheet pinouts, the shared net-name contract, the Si5351 register
183 value in fpga/rtl/sn64_clock_init.sv), not against the authoring script:

  * Si5351A-B-GT pins match Skyworks Si5351-B Rev 1.3 Table 20; VDD/VDDO on
    FPGA_3V3; the crystal sits alone on XA/XB (internal load caps, sec. 7.4),
    meets Table 8, and its load capacitance equals XTAL_CL in register 183;
  * si_scl/si_sda pulled up to FPGA_3V3 (>= 1 k, Table 20); CLK0/1 reach
    si_clk0/1 through a series element; CLK2 is left open (the RTL powers it
    down: no pixel clock, the picture goes to the console over the cartridge
    bus); the 25 MHz oscillator drives osc_25;
  * every contract label is a hierarchical port and a matching root sheet pin;
  * no HDMI part remains on the sheet (draft 0.2-av);
  * PCM1808 straps decode (TI SLES177B Tables 2/3) to I2S master at a ratio
    whose oscillator gives fs = 32 kHz exactly, outputs on adc_bck/lrck/dout;
  * cartridge audio: L -> VINL, R -> VINR through the documented network; the
    5.0 Vp-p worst case stays under 0.6 x 4.75 V full scale; input impedance
    matches the console load; anti-alias and high-pass corners in range;
  * no 5 V net reaches an FPGA-facing label (DC through resistors/ferrites),
    and every device driving an FPGA label is referenced to FPGA_3V3;
  * decoupling, footprints, LCSC fields; KiCad ERC reports zero errors.

Usage (KiCad's python):
  python verify_av_clock_sheet.py --project build/av-clock/proj [--output JSON] [--kicad-cli EXE]
  python verify_av_clock_sheet.py --project build/av-clock/proj --negative-test   # each mutation must FAIL

Writes hardware/sn64/validation/av-clock-check.json unless --output is given.
Static schematic check only: no SI, jitter, audio or hardware behavior is
proven.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
SHEET = 'av-clock.kicad_sch'
# Deterministic uuid namespace of the authoring script: used ONLY to locate
# pin labels ("l:REF:PIN") for the negative-test mutations.
AUTHOR_NS = uuid.UUID('7c1e3a90-5b2d-4f61-9e0a-2d4b6a8c1f37')

# ---- independent datasheet tables -------------------------------------------
SI5351A_MSOP10 = {'1': 'VDD', '2': 'XA', '3': 'XB', '4': 'SCL', '5': 'SDA', '6': 'CLK2', '7': 'VDDO', '8': 'GND',
                  '9': 'CLK1', '10': 'CLK0'}                     # Si5351-B Rev 1.3 Table 20
PCM1808_PW ={'1': 'VREF', '2': 'AGND', '3': 'VCC', '4': 'VDD', '5': 'DGND', '6': 'SCKI', '7': 'LRCK', '8': 'BCK',
              '9': 'DOUT', '10': 'MD0', '11': 'MD1', '12': 'FMT', '13': 'VINL', '14': 'VINR'}   # SLES177B section 5
PCM1808_MODE = {('L', 'L'): ('slave', None), ('L', 'H'): ('master', 512), ('H', 'L'): ('master', 384),
                ('H', 'H'): ('master', 256)}                     # Table 2, key (MD1, MD0)
PCM1808_FMT = {'L': 'I2S 24-bit', 'H': 'left-justified 24-bit'}  # Table 3
PCM1808_FS_RATIO_VCC = 0.6            # full scale = 0.6 x VCC Vp-p (6.5)
PCM1808_RIN = 60e3                    # input impedance, typical (6.5)
PCM1808_AA_MHZ = 1.3                  # internal anti-alias -3 dB (6.5)
OSC_CJO05 = {'1': 'EN', '2': 'GND', '3': 'OUT', '4': 'VDD'}      # JSCJ CJO05 pin connection table
CRYSTAL_3225 = {'1': 'X', '3': 'X', '2': 'GND', '4': 'GND'}      # YXC YSX321SL top-view connection
HDMI_PARTS = ('HDMI_A', 'TPD12S016PW')                             # must be absent since draft 0.2-av
SI5351_XTAL ={'f_mhz': (25.0, 27.0), 'cl_pf': (6.0, 12.0)}      # Table 8
XTAL_CL_BITS = {1: 6.0, 2: 8.0, 3: 10.0}                         # AN619 register 183 bits 7:6

# ---- shared net-name contract ------------------------------------------------
RAIL3, RAIL5, GND = 'FPGA_3V3', '5V_PRE', 'GND'
ROOT_LABELLED = {'GND', 'SNES_AUDIO_L_IN', 'SNES_AUDIO_R_IN'}
FPGA_REFS = {'U401'}   # the ECP5 on the FPGA sheet, attached at the round-3 integration
FPGA_LABELS = ['osc_25', 'si_clk0', 'si_clk1', 'si_scl', 'si_sda', 'adc_bck', 'adc_lrck', 'adc_dout']
CONTRACT = sorted(ROOT_LABELLED | {RAIL3, RAIL5} | set(FPGA_LABELS))
CART_MAX_VPP =5.0          # largest swing a cartridge powered only from +5 V can present (derived)
VCC_MIN = 4.75              # provisional 5 V window, docs/design/power-architecture.md
CONSOLE_LOAD_OHMS = 1 / (1 / 200 + 1 / 10e3)    # OpenSFC R95/R96 200 R || 10 k summing input (1 uF coupled)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value_si(text):
    """'4.7k' -> 4700, '22nF' -> 22e-9, '0R' -> 0, '1uF 25V X7R' -> 1e-6, '25MHz' -> 25e6."""
    m = re.match(r'\s*([\d.]+)\s*([pnumkKMG]?)', text or '')
    if not m:
        return None
    mult = {'': 1, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9}[m.group(2)]
    return float(m.group(1)) * mult


def pin_name(node):
    name = node.get('pinfunction') or ''
    suffix = '_' + node.get('pin', '')
    if name.endswith(suffix):
        name = name[:-len(suffix)]
    return name.replace('~{', '').replace('}', '')


def base(net):
    return None if net is None else net.rsplit('/', 1)[-1]


def run_checks(project: Path, cli: Path, rtl: Path):
    checks = []

    def check(name, ok, detail=''):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})
        return ok

    root_text = (project / 'sn64.kicad_sch').read_text(encoding='utf-8')
    if not check('sheet_attached_to_root', f'"{SHEET}"' in root_text,
                 'av-clock.kicad_sch must be a sheet of sn64.kicad_sch (run on the validation copy until integration)'):
        return checks, {}
    with tempfile.TemporaryDirectory(prefix='sn64-av-') as temp:
        net_path, erc_path = Path(temp) / 'net.xml', Path(temp) / 'erc.json'
        sch = project / 'sn64.kicad_sch'
        exp = subprocess.run([str(cli), 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', str(net_path), str(sch)],
                             capture_output=True, text=True)
        if not check('fresh_netlist_export', exp.returncode == 0 and net_path.exists(), (exp.stdout + exp.stderr).strip()[-400:]):
            return checks, {}
        subprocess.run([str(cli), 'sch', 'erc', '--format', 'json', '--output', str(erc_path), str(sch)],
                       capture_output=True, text=True)
        xml = ET.parse(net_path)
        erc_ok = erc_path.exists()
        erc_data = json.loads(erc_path.read_text(encoding='utf-8')) if erc_ok else {'sheets': []}

    summary, ours = {}, {}
    for sheet in erc_data.get('sheets', []):
        for v in sheet.get('violations', []):
            key = f"{v['severity']}:{v['type']}"
            summary[key] = summary.get(key, 0) + 1
            if sheet.get('path', '').startswith('/AV clock'):
                ours[key] = ours.get(key, 0) + 1
    errors = {k: v for k, v in summary.items() if k.startswith('error:')}
    check('erc_zero_errors', erc_ok and not errors, {'report_written': erc_ok, 'violations_by_type': summary})
    check('erc_no_violations_on_this_sheet', erc_ok and not ours, ours)

    # ---- netlist model ---------------------------------------------------------
    comps = {}
    for c in xml.iter('comp'):
        fields = {f.get('name'): (f.text or '') for f in c.iter('field')}
        lib = c.find('libsource')
        props = {pp.get('name'): pp.get('value') for pp in c.iter('property')}
        comps[c.get('ref')] = {'value': c.findtext('value') or '', 'footprint': c.findtext('footprint') or '',
                               'part': lib.get('part') if lib is not None else '', 'fields': fields,
                               'sheetfile': props.get('Sheetfile', '')}
    nodes, pinnet = {}, {}
    for n in xml.iter('net'):
        name = n.get('name')
        mem = [{'ref': x.get('ref'), 'pin': x.get('pin'), 'name': pin_name(x), 'type': x.get('pintype') or ''}
               for x in n.iter('node')]
        nodes[name] = mem
        for m in mem:
            pinnet[(m['ref'], m['pin'])] = name

    def members(net):
        return nodes.get(net, [])

    def pnet(ref, pin):
        return pinnet.get((ref, str(pin)))

    def by_part(part):
        return sorted(r for r, c in comps.items() if c['part'] == part and c['sheetfile'] == SHEET)

    def two_pin(kind):
        return [r for r, c in comps.items() if c['part'] == kind]

    resistors, capacitors, beads = two_pin('R'), two_pin('C'), two_pin('FerriteBead')

    def ends(ref):
        return pnet(ref, 1), pnet(ref, 2)

    def other(ref, net):
        a, b = ends(ref)
        return b if a == net else a if b == net else None

    def parts_on(net, kinds):
        return [m['ref'] for m in members(net) if m['ref'] in kinds]

    def named(label):
        """Net carrying a contract/local label name (any sheet path)."""
        hits = [n for n in nodes if base(n) == label]
        return hits[0] if len(hits) == 1 else (hits if hits else None)

    def is_rail(net, rail):
        return base(net) == rail

    si, adc = by_part('Si5351A-B-GT'), by_part('PCM1808PW')
    xtal, oscs = by_part('Crystal_GND24'), by_part('ASE-xxxMHz')
    check('expected_parts_present', len(si) == 1 and len(adc) == 1 and len(xtal) == 1 and len(oscs) == 2,
          {'Si5351': si, 'PCM1808': adc, 'crystal': xtal, 'oscillators': oscs})
    hdmi_left = {p: by_part(p) for p in HDMI_PARTS}
    hdmi_left = {p: r for p, r in hdmi_left.items() if r}
    check('no_hdmi_parts_on_sheet', not hdmi_left, hdmi_left or 'no HDMI connector or TPD12S016 (draft 0.2-av)')
    if not (si and adc and xtal and len(oscs) == 2):
        return checks, {'erc': summary}
    U_SI, U_ADC, Y = si[0], adc[0], xtal[0]

    def pin_identity(ref, table):
        seen = {m['pin']: m['name'] for net in nodes.values() for m in net if m['ref'] == ref}
        bad = {p: (seen.get(p), n) for p, n in table.items() if seen.get(p) != n}
        extra = sorted(set(seen) - set(table))
        return not bad and not extra, {'mismatch_pin:(netlist,datasheet)': bad, 'extra_pins': extra}

    for ref, table, title in [(U_SI, SI5351A_MSOP10, 'si5351_pins_match_table_20'),
                              (U_ADC, PCM1808_PW, 'pcm1808_pins_match_datasheet')]:
        ok, d = pin_identity(ref, table)
        check(title, ok, d)

    # ---- Si5351 and crystal --------------------------------------------------------
    sp = {name: pnet(U_SI, p) for p, name in SI5351A_MSOP10.items()}
    check('si5351_supplies_and_ground', is_rail(sp['VDD'], RAIL3) and is_rail(sp['VDDO'], RAIL3) and is_rail(sp['GND'], GND),
          {k: base(sp[k]) for k in ('VDD', 'VDDO', 'GND')})
    xa, xb = sp['XA'], sp['XB']
    ynets = {p: pnet(Y, p) for p in '1234'}
    alone = all({m['ref'] for m in members(n)} == {U_SI, Y} and len(members(n)) == 2 for n in (xa, xb))
    check('crystal_on_XA_XB_only', {ynets['1'], ynets['3']} == {xa, xb} and xa != xb and alone
          and is_rail(ynets['2'], GND) and is_rail(ynets['4'], GND),
          {'XA': [(m['ref'], m['pin']) for m in members(xa)], 'XB': [(m['ref'], m['pin']) for m in members(xb)],
           'crystal_gnd': [base(ynets['2']), base(ynets['4'])],
           'rule': 'Si5351-B 7.4: internal load capacitance; nothing else on XA/XB'})
    yf = comps[Y]['fields']
    f_x = value_si(yf.get('Frequency', ''))
    cl_x = value_si(yf.get('Load_Capacitance', ''))
    t8 = (f_x is not None and SI5351_XTAL['f_mhz'][0] <= f_x / 1e6 <= SI5351_XTAL['f_mhz'][1]
          and cl_x is not None and SI5351_XTAL['cl_pf'][0] <= cl_x * 1e12 <= SI5351_XTAL['cl_pf'][1])
    check('crystal_meets_si5351_table_8', t8, {'frequency_MHz': f_x and f_x / 1e6, 'CL_pF': cl_x and cl_x * 1e12,
                                               'LCSC': yf.get('LCSC'), 'MPN': yf.get('MPN')})
    rtl_text = rtl.read_text(encoding='utf-8') if rtl.exists() else ''
    m = re.search(r"8'd183\s*,\s*8'h([0-9A-Fa-f]{2})", rtl_text)
    reg = int(m.group(1), 16) if m else None
    cl_reg = XTAL_CL_BITS.get(reg >> 6) if reg is not None else None
    check('crystal_CL_matches_register_183', reg is not None and cl_reg is not None and cl_x is not None
          and abs(cl_reg - cl_x * 1e12) < 0.01 and (reg & 0x3F) == 0b010010,
          {'rtl': str(rtl.relative_to(REPO)) if rtl.exists() and REPO in rtl.parents else str(rtl),
           'register_183': f'0x{reg:02X}' if reg is not None else None, 'XTAL_CL_pF': cl_reg,
           'reserved_bits_5_0_ok': reg is not None and (reg & 0x3F) == 0b010010, 'crystal_CL_pF': cl_x and cl_x * 1e12})

    def pullup(net, rail, lo=1e3, hi=10e3):
        found = [(r, comps[r]['value']) for r in parts_on(net, resistors) if is_rail(other(r, net), rail)]
        return found and all(v is not None and lo <= v <= hi for v in (value_si(x) for _, x in found)), found
    scl_ok, scl_r = pullup(named('si_scl') if isinstance(named('si_scl'), str) else None, RAIL3)
    sda_ok, sda_r = pullup(named('si_sda') if isinstance(named('si_sda'), str) else None, RAIL3)
    check('si_i2c_pullups_to_FPGA_3V3', scl_ok and sda_ok and base(sp['SCL']) == 'si_scl' and base(sp['SDA']) == 'si_sda',
          {'si_scl': scl_r, 'si_sda': sda_r, 'SCL_net': base(sp['SCL']), 'SDA_net': base(sp['SDA']),
           'rule': 'pull-up to VDD, >= 1 k (Table 20), <= 10 k for 400 kHz'})

    def series_to(src_net, label, max_ohms=50):
        rs = parts_on(src_net, resistors)
        hits = [(r, comps[r]['value']) for r in rs if base(other(r, src_net)) == label]
        ok = len(hits) == 1 and (value_si(hits[0][1]) or 0) <= max_ohms
        return ok, hits
    clk_detail, clk_ok = {}, True
    for out, label in (('CLK0', 'si_clk0'), ('CLK1', 'si_clk1')):
        ok, hits = series_to(sp[out], label)
        clk_ok &= ok
        clk_detail[out] = {'to': label, 'series': hits}
    check('si5351_clk_outputs_to_contract_labels', clk_ok, clk_detail)
    # CLK2: nothing on the pin (the RTL leaves it powered down and disabled; a KiCad no-connect marker
    # exports as a single-node "unconnected-..." net).
    clk2_others = [(m['ref'], m['pin']) for m in members(sp['CLK2']) if m['ref'] != U_SI]
    m183 = re.search(r"8'd3\s*,\s*8'h([0-9A-Fa-f]{2})", rtl_text)
    oe_regs = [int(x, 16) for x in re.findall(r"8'd3\s*,\s*8'h([0-9A-Fa-f]{2})", rtl_text)]
    check('si5351_clk2_open_and_disabled_in_rtl', not clk2_others and oe_regs and (oe_regs[-1] & 0x04) == 0x04,
          {'CLK2_net': base(sp['CLK2']), 'other_members': clk2_others,
           'register_3_writes': [f'0x{v:02X}' for v in oe_regs], 'rule': 'last register-3 write must keep OEB2 = 1 (disabled)'})

    osc = {}
    for r in oscs:
        f = value_si(comps[r]['fields'].get('Frequency', ''))
        osc[r] = {'f': f, 'nets': {name: pnet(r, p) for p, name in OSC_CJO05.items()}}
    o25 = [r for r in oscs if osc[r]['f'] == 25e6]
    o12 = [r for r in oscs if osc[r]['f'] == 12.288e6]
    ok25 = len(o25) == 1
    if ok25:
        n = osc[o25[0]]['nets']
        s_ok, s_hits = series_to(n['OUT'], 'osc_25')
        ok25 = s_ok and is_rail(n['VDD'], RAIL3) and is_rail(n['EN'], RAIL3) and is_rail(n['GND'], GND)
    check('osc_25MHz_drives_osc_25', ok25, {r: {k: base(v) for k, v in osc[r]['nets'].items()} for r in o25})

    # ---- contract labels and sheet pins ------------------------------------------------
    child_text = (project / SHEET).read_text(encoding='utf-8')
    hier = set(re.findall(r'\(hierarchical_label "([^"]+)"', child_text))
    sheet_block = root_text.split(f'"{SHEET}"')
    sheet_pins = set()
    if len(sheet_block) > 1:
        blk = sheet_block[0].rsplit('(sheet ', 1)[-1] + sheet_block[1].split('(instances')[0]
        sheet_pins = set(re.findall(r'\(pin "([^"]+)" \w+ \(at', blk))
    missing = sorted(set(CONTRACT) - hier)
    check('contract_labels_present', not missing and hier == set(CONTRACT),
          {'missing': missing, 'unexpected': sorted(hier - set(CONTRACT))})
    check('sheet_pins_match_child_hierarchical_labels', sheet_pins and sheet_pins == hier,
          {'only_in_root': sorted(sheet_pins - hier), 'only_in_child': sorted(hier - sheet_pins)})
    rootlab = {n: [m for m in members('/' + n)] for n in ('SNES_AUDIO_L_IN', 'SNES_AUDIO_R_IN')}
    check('snes_audio_labels_reach_socket', all(any(m['ref'] == 'J2' for m in v) for v in rootlab.values()),
          {k: [(m['ref'], m['pin']) for m in v] for k, v in rootlab.items()})

    # ---- PCM1808 -----------------------------------------------------------------------
    ap_ = {name: pnet(U_ADC, p) for p, name in PCM1808_PW.items()}

    def level(net):
        """Static strap level: rail directly or through one resistor; floating = L (internal 50 k pull-down)."""
        if is_rail(net, RAIL3):
            return 'H'
        if is_rail(net, GND):
            return 'L'
        rails = {base(other(r, net)) for r in parts_on(net, resistors)}
        others = [m for m in members(net) if m['ref'] not in resistors and m['ref'] != U_ADC]
        if others or len(rails) > 1:
            return '?'
        return 'H' if rails == {RAIL3} else 'L'
    md1, md0, fmt = level(ap_['MD1']), level(ap_['MD0']), level(ap_['FMT'])
    mode, ratio = PCM1808_MODE.get((md1, md0), ('?', None))
    fmt_name = PCM1808_FMT.get(fmt)
    sck_src = None
    for r in oscs:
        n = osc[r]['nets']['OUT']
        if n == ap_['SCKI'] or any(other(x, n) == ap_['SCKI'] for x in parts_on(n, resistors)):
            sck_src = r
    f_sck = osc[sck_src]['f'] if sck_src else None
    fs = f_sck / ratio if (f_sck and ratio) else None
    osc12_ok = sck_src is not None and is_rail(osc[sck_src]['nets']['VDD'], RAIL3) and is_rail(osc[sck_src]['nets']['EN'], RAIL3)
    check('adc_straps_i2s_master_fs_32kHz', mode == 'master' and fmt_name == 'I2S 24-bit' and fs is not None
          and abs(fs - 32000) < 1e-6 and osc12_ok,
          {'MD1': md1, 'MD0': md0, 'FMT': fmt, 'mode': mode, 'ratio_fs': ratio, 'format': fmt_name,
           'SCKI_source': sck_src, 'SCKI_Hz': f_sck, 'fs_Hz': fs, 'oscillator_on_3V3_enabled': osc12_ok,
           'rule': 'SLES177B Table 2 (MD1,MD0), Table 3 (FMT); fs = SCKI / ratio must be 32 kHz'})
    check('adc_i2s_outputs_to_contract', base(ap_['BCK']) == 'adc_bck' and base(ap_['LRCK']) == 'adc_lrck'
          and base(ap_['DOUT']) == 'adc_dout', {k: base(ap_[k]) for k in ('BCK', 'LRCK', 'DOUT')})
    vcc_beads = [b for b in parts_on(ap_['VCC'], beads) if is_rail(other(b, ap_['VCC']), RAIL5)]

    def caps_to_gnd(net):
        return sorted(comps[c]['value'] for c in parts_on(net, capacitors) if is_rail(other(c, net), GND))
    vcc_caps, vref_caps, vdd_caps = caps_to_gnd(ap_['VCC']), caps_to_gnd(ap_['VREF']), caps_to_gnd(ap_['VDD'])
    check('adc_supplies_and_reference', not is_rail(ap_['VCC'], RAIL5) and len(vcc_beads) == 1 and is_rail(ap_['VDD'], RAIL3)
          and is_rail(ap_['AGND'], GND) and is_rail(ap_['DGND'], GND)
          and {'100nF', '10uF'} <= set(vcc_caps) and {'100nF', '10uF'} <= set(vref_caps) and {'100nF', '10uF'} <= set(vdd_caps),
          {'VCC': base(ap_['VCC']), 'VCC_filter_from_5V_PRE': vcc_beads, 'VCC_caps': vcc_caps, 'VREF_caps': vref_caps,
           'VDD': base(ap_['VDD']), 'VDD_rail_caps': vdd_caps, 'rule': 'SLES177B Figure 26 notes 2/3: 0.1 uF + 10 uF'})

    # ---- cartridge audio input network ---------------------------------------------------
    audio = {}
    audio_ok = True
    for ch, pin_name_ in (('L', 'VINL'), ('R', 'VINR')):
        src = '/SNES_AUDIO_%s_IN' % ch
        d = {'input_net': src}
        rl = [r for r in parts_on(src, resistors) if is_rail(other(r, src), GND)]
        rt = [r for r in parts_on(src, resistors) if not is_rail(other(r, src), GND)]
        ok = len(rl) == 1 and len(rt) == 1
        if ok:
            div = other(rt[0], src)
            rb = [r for r in parts_on(div, resistors) if is_rail(other(r, div), GND)]
            caa = [c for c in parts_on(div, capacitors) if is_rail(other(c, div), GND)]
            cc = [c for c in parts_on(div, capacitors) if not is_rail(other(c, div), GND)]
            ok = len(rb) == 1 and len(caa) == 1 and len(cc) == 1
            if ok:
                vin = other(cc[0], div)
                R_load, R_top, R_bot = (value_si(comps[r]['value']) for r in (rl[0], rt[0], rb[0]))
                C_aa, C_c = value_si(comps[caa[0]]['value']), value_si(comps[cc[0]]['value'])
                r_bot_eff = 1 / (1 / R_bot + 1 / PCM1808_RIN)
                gain = r_bot_eff / (R_top + r_bot_eff)
                z_in = 1 / (1 / R_load + 1 / (R_top + r_bot_eff))
                r_th = 1 / (1 / R_top + 1 / R_bot + 1 / PCM1808_RIN)
                f_aa = 1 / (2 * math.pi * r_th * C_aa)
                f_hp = 1 / (2 * math.pi * (PCM1808_RIN + r_th) * C_c)
                fs_min = PCM1808_FS_RATIO_VCC * VCC_MIN
                pk = CART_MAX_VPP * gain
                d.update({'R_load': (rl[0], R_load), 'R_top': (rt[0], R_top), 'R_bot': (rb[0], R_bot), 'C_aa': (caa[0], C_aa),
                          'C_couple': (cc[0], C_c), 'to_pin': base(vin), 'gain': round(gain, 4),
                          'cart_max_Vpp_at_ADC': round(pk, 3), 'ADC_full_scale_Vpp_at_4V75': round(fs_min, 3),
                          'headroom_dB': round(20 * math.log10(fs_min / pk), 2),
                          'input_impedance_ohm': round(z_in, 1), 'console_load_ohm': round(CONSOLE_LOAD_OHMS, 1),
                          'anti_alias_pole_kHz': round(f_aa / 1e3, 1), 'high_pass_Hz': round(f_hp, 2),
                          'passband_loss_16kHz_dB': round(-10 * math.log10(1 + (16e3 / f_aa) ** 2), 3)})
                ok = (vin == ap_[pin_name_] and pk <= fs_min and gain >= 0.3
                      and abs(z_in - CONSOLE_LOAD_OHMS) <= 0.1 * CONSOLE_LOAD_OHMS
                      and 40e3 <= f_aa <= PCM1808_AA_MHZ * 1e6 and f_hp <= 20)
        d['ok'] = ok
        audio_ok &= ok
        audio[ch] = d
    check('cartridge_audio_input_network', audio_ok, audio)

    # ---- no 5 V on FPGA-facing labels ------------------------------------------------------
    fpga_nets = {}
    for label in FPGA_LABELS:
        n = named(label)
        fpga_nets[label] = n if isinstance(n, str) else None
    five = {n for n in nodes if base(n) in (RAIL5,)}
    five |= {ap_['VCC'], '/SNES_AUDIO_L_IN', '/SNES_AUDIO_R_IN'}
    five.discard(None)
    leaks = []
    for label, start in fpga_nets.items():
        if start is None:
            leaks.append((label, 'missing'))
            continue
        seen, frontier = {start}, [start]
        while frontier:
            net = frontier.pop()
            if net in five:
                leaks.append((label, base(net)))
            for r in parts_on(net, resistors + beads):
                o = other(r, net)
                if o is None or is_rail(o, RAIL3) or is_rail(o, GND):
                    continue
                if is_rail(o, RAIL5) or o in five:
                    leaks.append((label, r, base(o)))
                elif o not in seen:
                    seen.add(o)
                    frontier.append(o)
    # Every active pin on an FPGA label net (directly or via one series resistor) must belong to a
    # device whose I/O reference is FPGA_3V3, and must be the expected pin.
    io_ref = {U_SI: ('VDDO', sp['VDDO']), U_ADC: ('VDD', ap_['VDD'])}
    for r in oscs:
        io_ref[r] = ('VDD', osc[r]['nets']['VDD'])
    allowed = {U_SI: {'SCL', 'SDA', 'CLK0', 'CLK1'}, U_ADC: {'BCK', 'LRCK', 'DOUT'}, **{r: {'OUT'} for r in oscs}}
    bad_ref, unexpected = [], []
    for label, start in fpga_nets.items():
        if start is None:
            continue
        reach = [start] + [other(r, start) for r in parts_on(start, resistors) if not (is_rail(other(r, start), RAIL3)
                                                                                     or is_rail(other(r, start), GND))]
        for net in reach:
            for m in members(net):
                if m['ref'] in resistors or m['ref'] in capacitors:
                    continue
                if m['ref'] in FPGA_REFS and net == start:
                    continue    # the ECP5 ball itself (bank VCCIO = FPGA_3V3, checked by verify_fpga_sheet.py)
                if m['ref'] not in allowed or m['name'] not in allowed[m['ref']]:
                    unexpected.append((label, m['ref'], m['pin'], m['name']))
                elif not is_rail(io_ref[m['ref']][1], RAIL3):
                    bad_ref.append((label, m['ref'], io_ref[m['ref']][0], base(io_ref[m['ref']][1])))
    check('no_5V_on_FPGA_labels', not leaks and not bad_ref and not unexpected,
          {'fpga_labels_checked': len(fpga_nets), 'dc_paths_to_5V_nets': leaks,
           'drivers_not_referenced_to_FPGA_3V3': bad_ref, 'unexpected_members': unexpected,
           'five_volt_nets': sorted(base(n) for n in five)})

    # ---- decoupling, footprints, sourcing ------------------------------------------------------
    supply_pins = {}
    for ref in [U_SI, U_ADC] + oscs:
        for m in [m for net in nodes.values() for m in net if m['ref'] == ref and m['type'].startswith('power_in')
                  and m['name'] not in ('GND', 'AGND', 'DGND')]:
            n = pnet(ref, m['pin'])
            supply_pins[base(n)] = supply_pins.get(base(n), 0) + 1
    decap = {}
    for c in capacitors:
        a, b = ends(c)
        if comps[c]['value'] == '100nF' and (is_rail(a, GND) or is_rail(b, GND)):
            rail = base(b if is_rail(a, GND) else a)
            decap[rail] = decap.get(rail, 0) + 1
    check('one_100nF_per_supply_pin', all(decap.get(k, 0) >= v for k, v in supply_pins.items()),
          {'supply_pins': supply_pins, '100nF_caps': decap})
    sheet_refs = [r for r, c in comps.items() if c['sheetfile'] == SHEET and not r.startswith('#')]
    missing_fp = sorted(r for r in sheet_refs if not comps[r]['footprint'])
    check('every_part_has_footprint', sheet_refs and not missing_fp, missing_fp)
    no_lcsc = sorted(r for r in [U_SI, U_ADC, Y] + oscs + beads if not comps[r]['fields'].get('LCSC'))
    check('active_parts_have_LCSC_numbers', not no_lcsc, {r: comps[r]['fields'].get('LCSC') for r in [U_SI, U_ADC, Y] + oscs + beads})
    return checks, {'erc': summary, 'audio': audio}


def mutate(text, mutations):
    applied = True
    for kind, key, new in mutations:
        if kind == 'label':
            u = str(uuid.uuid5(AUTHOR_NS, 'l:' + key))
            lines = text.split('\n')
            hits = [i for i, l in enumerate(lines) if l.startswith('(label ') and f'(uuid "{u}")' in l]
            if len(hits) != 1:
                applied = False
                continue
            lines[hits[0]] = re.sub(r'^\(label "[^"]*"', f'(label "{new}"', lines[hits[0]])
            text = '\n'.join(lines)
        else:
            if text.count(key) != 1:
                applied = False
                continue
            text = text.replace(key, new)
    return text, applied


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project', type=Path, default=HERE.parents[1])
    ap.add_argument('--output', type=Path)
    ap.add_argument('--kicad-cli', type=Path)
    ap.add_argument('--rtl', type=Path, default=REPO / 'fpga' / 'rtl' / 'sn64_clock_init.sv')
    ap.add_argument('--negative-test', action='store_true', help='mutate temporary copies; every mutation must fail')
    a = ap.parse_args()
    cli = a.kicad_cli or Path(sys.executable).with_name('kicad-cli.exe')
    if not cli.exists():
        cli = Path(shutil.which('kicad-cli') or r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe')
    project = a.project.resolve()

    if a.negative_test:
        mutations = [
            ('Y701 pin 3 lifted off XB (crystal not across XA/XB)', [('label', 'Y701:3', 'SI_XB_OPEN')],
             ['crystal_on_XA_XB_only']),
            ('Y701 replaced by an 8 pF crystal (register 183 programs 10 pF)',
             [('text', '(property "Load_Capacitance" "10pF"', '(property "Load_Capacitance" "8pF"')],
             ['crystal_CL_matches_register_183']),
            ('R701 si_scl pull-up disconnected', [('label', 'R701:1', 'R701_OPEN')], ['si_i2c_pullups_to_FPGA_3V3']),
            ('R702 si_sda pull-up to 5V_PRE (5 V on an FPGA label)', [('label', 'R702:1', '5V_PRE')],
             ['no_5V_on_FPGA_labels', 'si_i2c_pullups_to_FPGA_3V3']),
            ('MD1 strap to GND (PCM1808 becomes I2S slave)', [('label', 'R708:2', 'GND')], ['adc_straps_i2s_master_fs_32kHz']),
            ('FMT strap to FPGA_3V3 (left-justified instead of I2S)', [('label', 'R710:2', 'FPGA_3V3')],
             ['adc_straps_i2s_master_fs_32kHz']),
            ('Si5351 CLK2 wired to the si_clk1 label (pixel-clock output brought back)',
             [('text', '(no_connect (at 92.71 96.52)', '(label "si_clk1" (at 92.71 96.52 0) (effects (font (size 1.27 1.27)) (justify left bottom))')],
             ['si5351_clk2_open_and_disabled_in_rtl']),
            ('Cartridge audio L/R swapped at the ADC', [('label', 'C723:2', 'ADC_VINR'), ('label', 'C725:2', 'ADC_VINL')],
             ['cartridge_audio_input_network']),
            ('R713 divider bottom open (gain 0.93: 5 Vp-p overdrives the ADC)', [('label', 'R713:2', 'R713_OPEN')],
             ['cartridge_audio_input_network']),
            ('Contract label adc_dout renamed', [('text', '(hierarchical_label "adc_dout"', '(hierarchical_label "adc_data"')],
             ['contract_labels_present']),
        ]
        results = []
        for title, muts, must_fail in mutations:
            with tempfile.TemporaryDirectory(prefix='sn64-av-neg-') as temp:
                cp = Path(temp) / 'sn64'
                shutil.copytree(project, cp, ignore=shutil.ignore_patterns('exports', 'validation'))
                text, applied = mutate((cp / SHEET).read_text(encoding='utf-8'), muts)
                (cp / SHEET).write_text(text, encoding='utf-8', newline='\n')
                checks, _ = run_checks(cp, cli, a.rtl)
            failed = [c['check'] for c in checks if not c['passed']]
            detected = applied and set(must_fail) <= set(failed)
            results.append({'mutation': title, 'applied': applied, 'detected': detected, 'required_failures': must_fail,
                            'failed_checks': failed})
            print(('FAIL (as required): ' if detected else 'NOT DETECTED: ') + title + ' -> ' + ', '.join(failed))
        ok = all(r['detected'] for r in results)
        print(json.dumps({'negative_test': 'pass' if ok else 'fail', 'mutations': len(results),
                          'detected': sum(r['detected'] for r in results)}, indent=2))
        return 0 if ok else 1

    checks, extra = run_checks(project, cli, a.rtl)
    failed = [c for c in checks if not c['passed']]
    result = {
        'status': 'pass' if not failed else 'fail',
        'scope': 'static schematic/netlist check of the clock and cartridge-audio child sheet only (draft 0.2-av, no HDMI)',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'project_checked': str(project),
        'checks_passed': len(checks) - len(failed), 'checks_failed': len(failed),
        'inputs': {p: sha256(project / p) for p in ['sn64.kicad_sch', SHEET, 'libraries/SN64_AV.kicad_sym']
                   if (project / p).exists()} | ({'fpga/rtl/sn64_clock_init.sv': sha256(a.rtl)} if a.rtl.exists() else {}),
        'erc_violations_by_type': extra.get('erc', {}),
        'checks': checks,
        'limitations': [
            'Static connectivity only: no signal-integrity, jitter, audio or hardware test was performed.',
            'Since the round-3 integration the sheet is attached to the real root: FPGA-side pins reach ECP5 balls on the FPGA '
            'sheet and FPGA_3V3/5V_PRE come from the power sheet (#FLG701/#FLG702 removed; #FLG703 on ADC_VCC_5V stays).',
            'Provisional values: 0 R series resistors, 200 R console-equivalent load (OpenSFC value), X7R 1 uF coupling, '
            'X701/X702 footprints.',
            'PCM1808 input impedance is a typical value (60 k); the gain check uses it.',
        ]}
    out = a.output or HERE.parents[1] / 'validation' / 'av-clock-check.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'status': result['status'], 'checks_passed': result['checks_passed'],
                      'checks_failed': len(failed), 'failures': [c['check'] for c in failed]}, indent=2))
    if not failed:
        print(f"PASS: {result['checks_passed']} AV/clock checks; ERC {extra.get('erc')}")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
