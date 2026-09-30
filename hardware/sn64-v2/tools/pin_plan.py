"""SN64 v2 FPGA pin plan: every signal on the outer rings of the LFE5U-85F CABGA381.

Rings are counted from the package edge (ring 1 = outermost). v1 used 122 signal
balls spread over rings 1-5; here signals are packed onto rings 1-3 so rings 1-2
escape on the surface without a via and the inner rings are left to power/ground.
Bank sides (package top view, A1 corner top-left; footprint at 0 degrees):
  banks 0/1 top    -> riser socket (N64 bus), USB, housekeeping
  banks 7/6 left   -> cartridge address and control (translators U201/U202)
  banks 2/3 right  -> cartridge data, PA, CIC, sense inputs, audio ADC (U203/U204)
  bank 8 bottom    -> sysCONFIG: SPI flash, DONE/INITN/PROGRAMN, CFG, JTAG (fixed balls)

Source: Lattice "Pin Out For ECP5U-85" CSV rev 1.0 (Nov 2, 2015), CABGA381 column
(build/fpga-sheet/datasheets/ECP5U-85-pinout.csv, sha256 in fpga-pin-map.csv header).

  python pin_plan.py            # writes interfaces/fpga-pin-map.csv and fpga/constraints/sn64_board.lpf
"""
import csv
import hashlib
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
REPO = V2.parents[1]
CSV = REPO / 'build/fpga-sheet/datasheets/ECP5U-85-pinout.csv'
ROWS = 'ABCDEFGHJKLMNPRTUVWY'          # 20 rows, JEDEC letters (no I, O, Q, S, X)


def ring(ball):
    m = re.match(r'([A-Z]+)(\d+)$', ball)
    r = ROWS.index(m.group(1)); c = int(m.group(2)) - 1
    return min(r, 19 - r, c, 19 - c) + 1


def load_csv():
    rows = list(csv.reader(open(CSV, encoding='utf-8')))
    hdr = rows[4]
    ib, ibank, ifn, idf, idiff = (hdr.index(k) for k in ('CABGA381', 'Bank', 'Pin/Ball Function', 'Dual Function', 'Differential'))
    balls = {}
    for r in rows[5:]:
        if len(r) <= ib or r[ib] in ('-', ''):
            continue
        balls[r[ib]] = {'bank': r[ibank], 'fn': r[ifn], 'dual': r[idf], 'diff': r[idiff]}
    return balls


# ---------------------------------------------------------------------------
# Signals: (rtl port, schematic net, io type). Order inside a group = allocation order.
# ---------------------------------------------------------------------------
N64 = ([(f'n64_ad[{i}]', f'N64_AD{i}', 'LVCMOS33') for i in range(16)] +
       [('n64_alel', 'N64_ALE_L', 'LVCMOS33'), ('n64_aleh', 'N64_ALE_H', 'LVCMOS33'),
        ('n64_read_n', 'N64_READ_N', 'LVCMOS33'), ('n64_write_n', 'N64_WRITE_N', 'LVCMOS33'),
        ('n64_reset_n', 'N64_RESET_N', 'LVCMOS33'), ('n64_nmi_n', 'N64_NMI_N', 'LVCMOS33'),
        ('n64_int_n', 'N64_INT_N', 'LVCMOS33'), ('n64_cic_clk', 'N64_CIC_CLK', 'LVCMOS33'),
        ('n64_cic_dq', 'N64_CIC_DATA', 'LVCMOS33'), ('n64_si_clk', 'N64_PIF_CLK', 'LVCMOS33'),
        ('n64_si_dq', 'N64_JOYBUS', 'LVCMOS33')])
HOUSE = [('usb_dp', 'USB_DP_F', 'LVCMOS33'), ('usb_dn', 'USB_DN_F', 'LVCMOS33'), ('usb_pu', 'USB_PU', 'LVCMOS33'),
         ('adc_scl', 'ADC_SCL', 'LVCMOS33'), ('adc_sda', 'ADC_SDA', 'LVCMOS33'),
         ('efuse_fault_n', 'EFUSE_FAULT_N', 'LVCMOS33'), ('board_reset_n', 'BOARD_RESET_N', 'LVCMOS33'),
         ('cart_5v_enable', 'CART_5V_EN', 'LVCMOS33'), ('programn_od', 'PROGRAMN_PULL', 'LVCMOS33'),
         ('led_status', 'LED', 'LVCMOS33'), ('mux_status', 'MUX_ST', 'LVCMOS33')]
LEFT = ([(f'cart_address[{i}]', f'L_A{i}', 'LVCMOS33') for i in range(24)] +
        [('cart_rd_n', 'L_RD_N', 'LVCMOS33'), ('cart_wr_n', 'L_WR_N', 'LVCMOS33'), ('cart_prd_n', 'L_PRD_N', 'LVCMOS33'),
         ('cart_pwr_n', 'L_PWR_N', 'LVCMOS33'), ('cart_romsel_n', 'L_ROMSEL_N', 'LVCMOS33'),
         ('cart_wramsel_n', 'L_WRAMSEL_N', 'LVCMOS33'), ('cart_refresh', 'L_REFRESH', 'LVCMOS33'),
         ('cart_phi2', 'L_PHI2', 'LVCMOS33'), ('cart_sysclk', 'L_SYSTEM_CLK', 'LVCMOS33')])
RIGHT = ([(f'cart_data[{i}]', f'L_D{i}', 'LVCMOS33') for i in range(8)] +
         [(f'cart_pa[{i}]', f'L_PA{i}', 'LVCMOS33') for i in range(8)] +
         [('snes_cic_clk', 'L_CIC_CLK', 'LVCMOS33'), ('snes_cic_slave_reset', 'L_CIC_SLAVE_RESET', 'LVCMOS33'),
          ('cic_data0_in', 'L_CIC_DATA0_IN', 'LVCMOS33'), ('cic_data1_in', 'L_CIC_DATA1_IN', 'LVCMOS33'),
          ('cart_irq_n', 'L_IRQ_N', 'LVCMOS33'), ('cart_reset_n_sense', 'L_RESET_N_SENSE', 'LVCMOS33'),
          ('expand_sense', 'L_EXPAND', 'LVCMOS33'),
          ('cic_data0_od', 'CIC_DATA0_OD', 'LVCMOS33'), ('cic_data1_od', 'CIC_DATA1_OD', 'LVCMOS33'),
          ('reset_pull_od', 'RESET_PULL_OD', 'LVCMOS33'),
          ('ctl_oe_n', 'CTL_OE_N', 'LVCMOS33'), ('cic_oe_n', 'CIC_OE_N', 'LVCMOS33'),
          ('data_oe_n', 'DATA_OE_N', 'LVCMOS33'), ('data_dir', 'DATA_DIR', 'LVCMOS33'),
          ('aud_l_fb', 'AUD_L_FB', 'LVCMOS33'), ('aud_r_fb', 'AUD_R_FB', 'LVCMOS33')])
# LVDS comparator inputs (sigma-delta audio ADC): (port, net of the T ball, net of the C ball)
RIGHT_PAIRS = [('aud_l_cmp', 'AUD_L_P', 'AUD_L_N'), ('aud_r_cmp', 'AUD_R_P', 'AUD_R_N')]
# Fixed sysCONFIG balls (Lattice CSV, bank 8 dual functions) and the 27 MHz clock on a PCLK ball.
FIXED = [('osc_27', 'OSC_27', 'B12', 'LVCMOS33'),                       # PCLKT1_0
         ('flash_dq[0]', 'FLASH_D0', 'W2', 'LVCMOS33'), ('flash_dq[1]', 'FLASH_D1', 'V2', 'LVCMOS33'),
         ('flash_dq[2]', 'FLASH_D2', 'Y2', 'LVCMOS33'), ('flash_dq[3]', 'FLASH_D3', 'W1', 'LVCMOS33'),
         ('flash_cs_n', 'FLASH_CS_N', 'R2', 'LVCMOS33')]
# Non-port configuration balls, wired on the schematic only.
CONFIG_NETS = {'U3': 'FLASH_SCK', 'Y3': 'FPGA_DONE', 'V3': 'FPGA_INITN', 'W3': 'FPGA_PROGRAMN',
               'U4': 'FPGA_CFG0', 'T4': 'FPGA_CFG1', 'R4': 'FPGA_CFG2'}
JTAG = {'TCK': 'JTAG_TCK', 'TMS': 'JTAG_TMS', 'TDI': 'JTAG_TDI', 'TDO': 'JTAG_TDO'}


def plan():
    balls = load_csv()
    user = {b: d for b, d in balls.items() if d['fn'].startswith('P') and d['bank'] not in ('-', '')}
    taken = {}                                   # ball -> (port, net, iotype)
    for port, net, ball, io in FIXED:
        assert ball in balls, ball
        taken[ball] = (port, net, io)
    for ball, fn in JTAG.items():
        b = next(k for k, d in balls.items() if d['fn'] == ball)
        taken[b] = ('', fn, 'JTAG')
    for ball, net in CONFIG_NETS.items():
        taken[ball] = ('', net, 'CONFIG')

    def candidates(banks, max_ring=3):
        out = [b for b, d in user.items() if d['bank'] in banks and b not in taken]
        out.sort(key=lambda b: (ring(b), banks.index(user[b]['bank']), ROWS.index(re.match(r'[A-Z]+', b).group(0)), int(re.search(r'\d+', b).group(0))))
        return out

    def allocate(signals, banks):
        cands = candidates(banks)
        assert len(cands) >= len(signals), (banks, len(cands), len(signals))
        for (port, net, io), ball in zip(signals, cands):
            taken[ball] = (port, net, io)

    # LVDS pairs first (both balls on the outer rings of the right banks)
    for port, net_p, net_n in RIGHT_PAIRS:
        best = None
        for b, d in user.items():
            if d['bank'] not in ('2', '3') or b in taken or not d['diff'].startswith('True_OF_'):
                continue
            comp = next((k for k, e in user.items() if e['fn'] == d['diff'][8:]), None)
            if comp is None or comp in taken:
                continue
            key = (max(ring(b), ring(comp)), ring(b) + ring(comp), b)
            if best is None or key < best[0]:
                best = (key, b, comp)
        assert best, port
        taken[best[1]] = (port, net_p, 'LVDS')
        taken[best[2]] = ('', net_n, 'LVDS_COMP')
    allocate(N64, ['0', '1'])
    allocate(HOUSE, ['1', '0'])
    allocate(LEFT, ['7', '6'])
    allocate(RIGHT, ['2', '3'])
    rows = []
    for ball, d in balls.items():
        if ball in taken:
            port, net, io = taken[ball]
            rows.append((ball, d['bank'], d['fn'], ring(ball), port, net, io))
    return balls, rows


def fpga_nets(balls, rows):
    """ball -> net for the schematic symbol (power/ground balls included, unused user balls None)."""
    nets = {}
    for ball, d in balls.items():
        fn = d['fn']
        if fn == 'GND':
            nets[ball] = 'GND'
        elif fn == 'VCC':
            nets[ball] = 'FPGA_1V1'
        elif fn == 'VCCAUX':
            nets[ball] = 'FPGA_2V5'
        elif fn.startswith('VCCIO'):
            nets[ball] = 'FPGA_3V3'
        else:
            nets[ball] = None
    for ball, bank, fn, rg, port, net, io in rows:
        nets[ball] = net
    return nets


def write_outputs(rows):
    sha = hashlib.sha256(CSV.read_bytes()).hexdigest()
    out = V2 / 'interfaces' / 'fpga-pin-map.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='', encoding='utf-8') as f:
        f.write(f'# SN64 v2 pin map; source Lattice ECP5U-85 pinout CSV rev 1.0 (CABGA381), sha256 {sha}\n')
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['ball', 'bank', 'function', 'ring', 'rtl_port', 'net', 'iotype'])
        for r in sorted(rows, key=lambda r: (r[1], r[3], r[0])):
            w.writerow(r)
    lpf = REPO / 'fpga/constraints/sn64_board.lpf'
    lines = ['# SN64 v2 board constraints for sn64_board_top (LFE5U-85F, CABGA381), generated by',
             '# hardware/sn64-v2/tools/pin_plan.py from the Lattice pinout CSV. Do not edit by hand.',
             'BLOCK RESETPATHS;', 'BLOCK ASYNCPATHS;',
             'FREQUENCY PORT "osc_27" 27.0 MHz;']
    for ball, bank, fn, rg, port, net, io in sorted(rows, key=lambda r: r[4]):
        if not port or io in ('CONFIG', 'JTAG', 'LVDS_COMP'):
            continue
        lines.append(f'LOCATE COMP "{port}" SITE "{ball}";')
        if io == 'LVDS':
            lines.append(f'IOBUF PORT "{port}" IO_TYPE=LVDS;')
        else:
            pull = 'UP' if port in ('n64_cic_clk', 'n64_cic_dq', 'n64_int_n', 'n64_read_n', 'n64_write_n', 'n64_aleh', 'n64_si_dq',
                                    'efuse_fault_n', 'board_reset_n', 'cart_irq_n') else \
                   'DOWN' if port in ('n64_reset_n', 'n64_nmi_n', 'n64_alel', 'n64_si_clk', 'usb_pu') else 'NONE'
            lines.append(f'IOBUF PORT "{port}" IO_TYPE=LVCMOS33 PULLMODE={pull};')
    lpf.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return out, lpf


if __name__ == '__main__':
    balls, rows = plan()
    out, lpf = write_outputs(rows)
    by_ring = {}
    for r in rows:
        if r[4]:
            by_ring[r[3]] = by_ring.get(r[3], 0) + 1
    print(f'{len([r for r in rows if r[4]])} ports placed; balls by ring {dict(sorted(by_ring.items()))}; wrote {out.name}, {lpf.name}')
