"""Write the four footprints the power sheet left empty, from manufacturer drawings.

- Texas_RPW0010A_VQFN-HR-10_2x2mm: TPS259470L eFuse. TI SLVSFC9C mechanical data 4225183/A
  (08/2019), "example board layout": pins 2/3/8/9 0.6 x 0.25 at (+-0.9, +-0.225); pins 1/4/7/10
  L-shaped, bar 0.6 x 0.3 at (+-0.9, +-0.7) plus a 0.25-wide leg at x = +-0.725 out to y = +-1.2;
  pins 5/6 0.3 x 2.4 at x = +-0.25. Cross-checked against three independent KiCad footprints
  (cheyao/ckl CERN-OHL-P-2.0, ISSUIUC/ISS-PCB, ripaaf/ups-orangepizero3w MIT), which agree.
- Texas_RNM0015A_VQFN-HR-15_2.5x3mm: TPS63070. TI SLVSC58B mechanical data "example board
  layout": pins 1-4 0.6 x 0.25 at x = -1.15, y = -0.75..0.75 step 0.5; pins 5/6/14/15 0.25 x 0.6
  at x = -0.725 / -0.225, y = +-1.4; pins 9/11 1.35 x 0.25 at (0.725, +-0.5); pin 10 1.7 x 0.25 at
  (0.55, 0); VOUT (7+8) and VIN (12+13) as one U-shaped pad each (both pins of a pair are the
  same signal, datasheet Pin Functions): legs 0.25 wide at x = 0.25 and 0.775 from |y| = 1.1 to
  1.7 plus a bar 0.775 x 0.25 at |y| = 1.575. Cross-checked against mehrantsi/MSAP-2 (MIT) and
  the JLCPCB/EasyEDA footprint for TPS63070RNMR.
- L_APV_PNR4020: APV PNR series datasheet (rev 2026-06-06) p.2: body 4.0 x 4.0 x 2.0 max, land
  pattern b = 1.20 wide, c = 3.50 long, gap a = 1.80 (pad centres +-1.50).
- The FNR4030S inductors use KiCad's own Inductor_SMD:L_Changjiang_FNR4030S, which matches the
  Changjiang FNR datasheet (rev. as downloaded 2026-09-29, p.2): a 1.9, b 1.1, c 3.7.

Every pad is a rounded rectangle on F.Cu/F.Paste/F.Mask. Courtyards are 0.25 mm outside the
land. Nothing here has been built; a stencil/assembly check on the prototype is still required.
"""
import uuid
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'libraries/SN64.pretty'


def uid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'sn64-power-footprints/' + '/'.join(map(str, parts))))


def pad(name, num, x, y, w, h, rr=0.25):
    return (f'(pad "{num}" smd roundrect (at {x} {y}) (size {w} {h}) (layers "F.Cu" "F.Paste" "F.Mask") '
            f'(roundrect_rratio {rr}) (uuid "{uid(name, "pad", num, x, y)}"))')


def header(name, descr, tags):
    return [f'(footprint "{name}" (version 20241229) (generator "sn64_make_power_footprints") (generator_version "10.0") (layer "F.Cu")',
            f'(descr "{descr}")', f'(tags "{tags}")', '(attr smd)',
            f'(property "Reference" "REF**" (at 0 -2.6 0) (layer "F.SilkS") (uuid "{uid(name, "ref")}") (effects (font (size 1 1) (thickness 0.15))))',
            f'(property "Value" "{name}" (at 0 2.6 0) (layer "F.Fab") (uuid "{uid(name, "val")}") (effects (font (size 1 1) (thickness 0.15))))',
            f'(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uid(name, "ds")}") (effects (font (size 1.27 1.27))))',
            f'(property "Description" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uid(name, "desc")}") (effects (font (size 1.27 1.27))))']


def outlines(name, bx, by, cx, cy, pin1):
    """Body rectangle on F.Fab, silkscreen corners, courtyard, pin-1 marks."""
    L = [f'(fp_rect (start {-bx} {-by}) (end {bx} {by}) (stroke (width 0.1) (type default)) (fill no) (layer "F.Fab") (uuid "{uid(name, "fab")}"))',
         f'(fp_rect (start {-cx} {-cy}) (end {cx} {cy}) (stroke (width 0.05) (type default)) (fill no) (layer "F.CrtYd") (uuid "{uid(name, "crtyd")}"))',
         f'(fp_circle (center {pin1[0]} {pin1[1]}) (end {pin1[0] + 0.15} {pin1[1]}) (stroke (width 0.1) (type default)) (fill yes) (layer "F.Fab") (uuid "{uid(name, "p1fab")}"))',
         f'(fp_circle (center {pin1[2]} {pin1[3]}) (end {pin1[2] + 0.1} {pin1[3]}) (stroke (width 0.12) (type default)) (fill yes) (layer "F.SilkS") (uuid "{uid(name, "p1silk")}"))']
    return L


def rpw0010a():
    n = 'Texas_RPW0010A_VQFN-HR-10_2x2mm'
    L = header(n, 'TI RPW0010A VQFN-HR 10, 2 x 2 mm, 0.475 mm pitch (TPS25947 eFuse); land pattern per TI 4225183/A example board layout', 'VQFN HotRod TPS25947')
    L += outlines(n, 1.0, 1.0, 1.45, 1.45, (-0.8, -0.8, -1.35, -1.35))
    for num, x, y in ((2, -0.9, -0.225), (3, -0.9, 0.225), (8, 0.9, 0.225), (9, 0.9, -0.225)):
        L.append(pad(n, num, x, y, 0.6, 0.25))
    for num, sx, sy in ((1, -1, -1), (4, -1, 1), (7, 1, 1), (10, 1, -1)):
        L.append(pad(n, num, sx * 0.9, sy * 0.7, 0.6, 0.3))              # bar
        L.append(pad(n, num, sx * 0.725, sy * 0.875, 0.25, 0.65, 0.2))   # leg to |y| = 1.2
    L.append(pad(n, 5, -0.25, 0, 0.3, 2.4, 0.15))
    L.append(pad(n, 6, 0.25, 0, 0.3, 2.4, 0.15))
    L.append(')')
    return n, L


def rnm0015a():
    n = 'Texas_RNM0015A_VQFN-HR-15_2.5x3mm'
    L = header(n, 'TI RNM0015A VQFN-HR 15, 2.5 x 3 mm (TPS63070); land pattern per TI SLVSC58B example board layout; VOUT (7+8) and VIN (12+13) as one U pad each', 'VQFN HotRod TPS63070')
    L += outlines(n, 1.25, 1.5, 1.65, 1.95, (-1.05, -1.3, -1.55, -1.3))
    for num, y in ((1, -0.75), (2, -0.25), (3, 0.25), (4, 0.75)):
        L.append(pad(n, num, -1.15, y, 0.6, 0.25))
    for num, x, y in ((5, -0.725, 1.4), (6, -0.225, 1.4), (14, -0.225, -1.4), (15, -0.725, -1.4)):
        L.append(pad(n, num, x, y, 0.25, 0.6))
    L.append(pad(n, 9, 0.725, 0.5, 1.35, 0.25))
    L.append(pad(n, 11, 0.725, -0.5, 1.35, 0.25))
    L.append(pad(n, 10, 0.55, 0.0, 1.7, 0.25))
    for a, b, sy in ((7, 8, 1), (13, 12, -1)):               # U pads: legs carry both pin numbers of the pair
        L.append(pad(n, a, 0.25, sy * 1.4, 0.25, 0.6, 0.2))   # (same signal: VOUT 7+8, VIN 12+13), joined by the bar
        L.append(pad(n, b, 0.775, sy * 1.4, 0.25, 0.6, 0.2))
        L.append(pad(n, a, 0.5125, sy * 1.575, 0.775, 0.25, 0.2))
    L.append(')')
    return n, L


def pnr4020():
    n = 'L_APV_PNR4020'
    L = header(n, 'Inductor, APV, PNR4020, 4.0 x 4.0 x 2.0 mm max; land pattern per APV PNR series datasheet p.2 (a 1.80, b 1.20, c 3.50)', 'inductor APV PNR4020')
    L += outlines(n, 2.0, 2.0, 2.35, 2.05, (-1.7, -1.7, -2.2, -2.2))
    L.append(pad(n, 1, -1.5, 0, 1.2, 3.5, 0.1))
    L.append(pad(n, 2, 1.5, 0, 1.2, 3.5, 0.1))
    L.append(')')
    return n, L


def main():
    for n, L in (rpw0010a(), rnm0015a(), pnr4020()):
        (LIB / f'{n}.kicad_mod').write_text('\n'.join(L) + '\n', encoding='utf-8', newline='\n')
        print('wrote', n)


if __name__ == '__main__':
    main()
