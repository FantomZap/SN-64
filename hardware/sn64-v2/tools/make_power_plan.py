"""Write power_layout_plan.json: where every part of the v2 power section goes and which supply
paths are drawn by hand (plain python). apply_power_layout_v2.py carries the plan onto the board.

The section is built from one cell for each regulator. A cell is drawn here in the chip's own
frame (chip at 0, 0, not turned) and then turned and moved as a whole, so the distances between
a chip and its capacitors are the same wherever the cell ends up. Distances come from the pad
positions of the footprints (read from the board 2026-10-02) and the courtyards KiCad checks.

Makers' rules behind the cells: see the head of apply_power_layout_v2.py.

A part's turn is a number of degrees for the chips and, for two-pad parts, the side its pad 1 is
on (N, E, S, W on the board, north = away from the N64 edge). Pad 1 is the first net of the part
in build_v2_schematic.py: the rail for a capacitor.
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIRS = ['W', 'S', 'E', 'N']           # pad 1 side of a two-pad part at 0, 90, 180, 270 degrees (KiCad's turn)


class Cell:
    """Chip frame to board frame. Turned like a KiCad footprint: (x, y) -> (x cos a + y sin a, -x sin a + y cos a)."""

    def __init__(self, x, y, turn):
        self.x, self.y, self.turn = x, y, turn
        a = math.radians(turn)
        self.c, self.s = round(math.cos(a)), round(math.sin(a))

    def at(self, lx, ly):
        return (round(self.x + lx * self.c + ly * self.s, 3), round(self.y - lx * self.s + ly * self.c, 3))

    def side(self, d):
        """A pad-1 side given in the chip frame, as a side on the board."""
        return DIRS[(DIRS.index(d) + self.turn // 90) % 4]


place, copper = {}, {}


def put(ref, face, xy, turn):
    assert ref not in place, ref
    place[ref] = [face, xy[0], xy[1], turn]


def run(net, w, path, layer='F', vias=()):
    copper.setdefault(net, []).append({'w': w, 'layer': layer, 'path': [list(p) if not isinstance(p, str) else p for p in path],
                                       'vias': [list(v) for v in vias]})


# ---------------------------------------------------------------------------------------------
# 5 V converter U8 (TPS63070) with its coil L1. Chip turned 270: VIN pins to the east, VOUT pins to
# the west, the three long pads (L1, PGND, L2) to the south, where the coil sits.
# Distances are from the chip's centre, on the board's axes.
c = Cell(-38.5, -9.5, 0)                 # board axes already: the chip itself is turned, the cell is not
put('U8', 'F', c.at(0, 0), 270)
put('L1', 'F', c.at(0, 3.9), 'E')        # coil pad 1 (L1_5V) on the east, pad 2 (L2_5V) on the west
put('C324', 'F', c.at(3.2, 1.275), 'N')  # 10 uF 0603 at the VIN pins: 0.43 mm from the pins to its pad
put('C309', 'F', c.at(5.05, 1.45), 'N')
put('C325', 'F', c.at(-3.2, 1.275), 'N')  # 10 uF 0603 at the VOUT pins
put('C310', 'F', c.at(-5.05, 1.45), 'N')
put('C311', 'F', c.at(-7.2, -1.7), 'S')
put('C307', 'F', c.at(-1.0, -2.8), 'E')   # VAUX capacitor: 0.9 mm from pin 3
put('R309', 'B', c.at(-3.0, -1.6), 'W')   # feedback divider on the label side, under the chip's corner
put('R310', 'B', c.at(-3.0, -3.2), 'W')
put('R311', 'B', c.at(1.4, -3.2), 'E')
put('R321', 'B', c.at(3.4, -1.3), 'E')
run('SYS_VIN', 0.8, [c.at(1.2, 0.5), c.at(5.05, 0.5)])
run('5V_SYS', 0.8, [c.at(-1.2, 0.5), c.at(-5.05, 0.5)])
run('5V_SYS', 0.8, [c.at(-5.05, 0.5), c.at(-5.05, -0.75), c.at(-7.2, -0.75)])
run('L1_5V', 0.25, [c.at(0.5, 0.9), c.at(0.5, 1.9)])
run('L1_5V', 0.5, [c.at(0.5, 1.9), c.at(1.2, 2.6), c.at(1.5, 3.2)])
run('L2_5V', 0.25, [c.at(-0.5, 0.9), c.at(-0.5, 1.9)])
run('L2_5V', 0.5, [c.at(-0.5, 1.9), c.at(-1.2, 2.6), c.at(-1.5, 3.2)])
run('GND', 0.3, [c.at(0, 0.9), c.at(0, 3.1)])
run('GND', 0.8, [c.at(0, 3.1), c.at(0, 6.3)], vias=[c.at(0, 3.5), c.at(0, 4.5), c.at(0, 5.5)])
run('VAUX_5V', 0.25, [c.at(-0.25, -1.3), c.at(-0.25, -2.5)])
run('GND', 0.25, [c.at(-0.75, -1.3), c.at(-0.75, -1.7), c.at(-1.5, -2.45)])

# ---------------------------------------------------------------------------------------------
# Input selector U7 (TPS2121), not turned: the two OUT pads on the north row, IN2 (console) south-west,
# IN1 (USB) south-east. The two OUT pads leave on both sides and join above the chip.
c = Cell(-30.6, -4.2, 0)
put('U7', 'F', c.at(0, 0), 0)
put('C306', 'F', c.at(3.1, -1.6), 'N')       # the selector's output: on the loop that joins its two OUT pads
put('C308', 'F', c.at(0.3, -3.7), 'W')
put('C304', 'F', c.at(3.3, 2.15), 'W')       # USB side, 1.9 mm from the IN1 pad
put('C305', 'F', c.at(-3.0, 1.3), 'N')       # console side, 1.6 mm from the IN2 pad
put('C212', 'F', c.at(-6.0, 2.6), 'E')
put('C303', 'B', c.at(-1.4, -4.2), 'E')
put('R307', 'B', c.at(1.8, -4.2), 'E')
put('R308', 'B', c.at(2.4, -2.5), 'E')
put('R305', 'B', c.at(-2.4, 2.2), 'W')
put('R306', 'B', c.at(-2.4, 0.6), 'W')
put('R303', 'B', c.at(2.4, 2.2), 'E')
put('R304', 'B', c.at(2.4, 0.6), 'E')
run('SYS_VIN', 0.4, [c.at(-0.9, -0.35), c.at(-1.4, -0.35)])
run('SYS_VIN', 0.6, [c.at(-1.4, -0.35), c.at(-1.6, -0.35), c.at(-1.6, -4.8), c.at(-2.85, -4.8)])    # up to the 5 V converter's input rail
run('SYS_VIN', 0.4, [c.at(0.9, -0.35), c.at(1.5, -0.35)])
run('SYS_VIN', 0.6, [c.at(1.5, -0.35), c.at(1.7, -0.35), c.at(1.7, -2.55), c.at(-1.6, -2.55)])
run('SYS_VIN', 0.6, [c.at(1.7, -2.55), c.at(3.1, -2.55)])
run('SYS_VIN', 0.6, [c.at(-1.6, -3.7), c.at(-0.65, -3.7)])
run('USB_VBUS', 0.4, [c.at(0.9, 0.35), c.at(1.6, 0.35)])
run('USB_VBUS', 0.5, [c.at(1.6, 0.35), c.at(2.35, 1.1), c.at(2.35, 2.15)])
run('HOST_3V3', 0.4, [c.at(-0.9, 0.35), c.at(-1.3, 0.35)])
run('HOST_3V3', 0.5, [c.at(-1.3, 0.35), c.at(-1.7, 0.75), c.at(-3.0, 0.75)])
run('HOST_3V3', 0.5, [c.at(-3.0, 0.75), c.at(-4.4, 0.75), c.at(-4.4, 2.0), c.at(-5.05, 2.6)])

# ---------------------------------------------------------------------------------------------
# The two small converters (TLV62569). Chip not turned in its cell: VIN pin 4 south-east, SW pin 3
# south-west, GND pin 2 west. Input capacitor east of the chip, 0.85 mm from the VIN pin; its ground
# end joins the chip's ground pin by a track under the body; the coil south-west; the two output
# capacitors east of the coil.
def buck(u, coil, cin, cout, top, bottom, cff, x, y, turn, sw, rail, fb):
    c = Cell(x, y, turn)
    put(u, 'F', c.at(0, 0), turn)
    put(cin, 'F', c.at(3.15, 0), c.side('S'))
    put(coil, 'F', c.at(-1.3, 4.2), c.side('W'))
    put(cout[0], 'F', c.at(2.6, 4.2), c.side('N'))
    put(cout[1], 'F', c.at(4.7, 4.2), c.side('N'))
    put(top, 'B', c.at(3.3, 1.2), c.side('E'))        # feedback parts on the label side, under the chip
    put(bottom, 'B', c.at(0.1, 1.2), c.side('W'))
    put(cff, 'B', c.at(3.3, 2.8), c.side('E'))
    run('5V_SYS', 0.6, [c.at(1.4, 0.95), c.at(3.15, 0.95)])
    run(sw, 0.5, [c.at(-1.2, 0.95), c.at(-1.2, 1.6), c.at(-2.4, 2.8), c.at(-2.6, 3.3)])
    run(rail, 0.8, [c.at(0.2, 3.25), c.at(4.7, 3.25)], vias=[c.at(1.31, 3.25)])
    run(rail, 0.5, [c.at(1.31, 3.25), c.at(1.31, 2.5)], vias=[c.at(1.31, 2.5)])        # into the plane, between the pads
    run('GND', 0.4, [c.at(-1.0, 0), c.at(2.0, 0), c.at(2.7, -0.7)])
    # the rail ends of the two feedback parts on the label side: their own via into the plane
    run(rail, 0.25, [c.at(4.075, 1.2), c.at(4.9, 2.0), c.at(4.075, 2.8)], layer='B', vias=[c.at(4.9, 2.0)])


buck('U10', 'L3', 'C313', ('C318', 'C319'), 'R315', 'R316', 'C315', -45.9, -19.5, 0, 'SW_1V1', 'FPGA_1V1', 'FB_1V1')
buck('U9', 'L2', 'C312', ('C316', 'C317'), 'R312', 'R313', 'C314', -36.3, -25.2, 0, 'SW_3V3', 'FPGA_3V3', 'FB_3V3')

# ---------------------------------------------------------------------------------------------
# Cartridge switch U12 (TPS2553): its 100 nF 1 mm from the IN pin, the 10 uF at the OUT pin.
c = Cell(-35.0, -15.6, 0)
put('U12', 'F', c.at(0, 0), 0)
put('C322', 'F', c.at(-2.95, -0.475), 'N')
put('C323', 'F', c.at(3.15, 0), 'N')
put('R318', 'B', c.at(2.9, 0.0), 'E')
put('R319', 'B', c.at(-2.9, -1.7), 'W')
put('R320', 'B', c.at(2.9, -1.7), 'E')
run('5V_SYS', 0.5, [c.at(-1.4, -0.95), c.at(-2.95, -0.95), c.at(-2.95, -1.25)])
run('SNES_5V_CART', 0.6, [c.at(1.4, -0.95), c.at(3.15, -0.95)])

# 2.5 V regulator U11 (AP2112K), turned 90: input capacitor south, output capacitor north.
c = Cell(-28.4, -21.5, 90)
put('U11', 'F', c.at(0, 0), 90)
put('C320', 'F', c.at(-2.95, -0.475), c.side('N'))
put('C321', 'F', c.at(3.15, 0), c.side('N'))
run('FPGA_2V5', 0.5, [c.at(1.4, -0.95), c.at(3.15, -0.95)])
run('FPGA_3V3', 0.4, [c.at(-1.4, -0.95), c.at(-2.95, -0.95), c.at(-2.95, -1.25)])
run('FPGA_3V3', 0.4, [c.at(-2.95, -1.25), c.at(-2.95, -2.2)], vias=[c.at(-2.95, -2.2)])

# ---------------------------------------------------------------------------------------------
# The measuring chip U6 (TLA2528) and the supply supervisor U3, outside the power section. U6 stays.
# AVDD (pin 7) is also the chip's reference: its 1 uF sits above the pin row, joined by 1 mm of track with no
# via between pin and capacitor. DVDD (pin 10): its 1 uF beside the pin, 0.6 mm of track. The supervisor sat
# 0.6 mm above U6, on a part of the label side that is full of small parts, so that neither capacitor nor a
# via had room: it moves 10 mm to the west with its 100 nF and its two divider resistors. Board coordinates.
put('U3', 'F', (-23.2, -20.0), 180)
put('C33', 'F', (-23.6, -17.4), 'W')
put('R15', 'B', (-24.6, -20.6), 'W')
put('R16', 'B', (-24.6, -22.2), 'W')
put('C35', 'F', (-14.75, -20.1), 'E')
put('C46', 'F', (-17.25, -17.25), 'E')
run('FPGA_3V3', 0.25, [(-13.75, -18.6), (-13.75, -19.9)])
run('FPGA_3V3', 0.25, [(-15.2, -17.25), (-16.45, -17.25)])
run('FPGA_3V3', 0.25, [(-16.475, -17.0), (-16.23, -16.45)], vias=[(-16.23, -16.45)])      # into the plane, behind the capacitor
run('FPGA_3V3', 0.25, [(-24.337, -19.2), (-24.337, -17.6)], vias=[(-24.337, -18.3)])
run('GND', 0.2, [(-14.9, -17.75), (-14.2, -17.75)])

(HERE / 'power_layout_plan.json').write_text(json.dumps({'place': place, 'copper': copper, 'keep_vias_of': []}, indent=1) + '\n', encoding='utf-8')
print('plan: %d parts, %d runs of copper on %d nets' % (len(place), sum(len(v) for v in copper.values()), len(copper)))
