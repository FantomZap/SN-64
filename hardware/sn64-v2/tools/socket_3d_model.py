"""3D model of the SNES socket straddling the board's top edge (build123d, millimetres).

KiCad footprint-model frame for SN64_V2:SNES_Slot_Console_Straddle: X = footprint x, Y = -footprint y
(up, away from the board), Z up from the F.Cu surface. The board (1.2 mm) spans Z -1.2..0 and its
top edge is Y = 0, so the socket body sits at Y > 0 centred on the board mid-plane Z = -0.6.

Sourced: body 99.0 x 11.25, ear holes 3.2 at X +-47.5, rows 7.0 apart, pin x positions (OpenSFC
CartSlot). Assumed until a sample is measured: base 6.0 and nose 9.0 high, nose 88 x 9, slot 1.6
wide, 0.5 mm gap above the edge, tails 0.6 x 0.3 with a 3.9 mm lap on each face.

In the build123d MCP session: execute_file, then export the registered "socket" to
hardware/sn64-v2/libraries/3d/SNES_Slot_Console_Straddle.step. Elsewhere: python socket_3d_model.py
(writes the STEP into the current folder).
"""
from build123d import *

BOARD_T, ZMID = 1.2, -0.6
GAP, BASE_H, NOSE_H = 0.5, 6.0, 9.0
BODY_L, BODY_D, NOSE_L, NOSE_D, SLOT_W = 99.0, 11.25, 88.0, 9.0, 1.6
EAR_X, EAR_D, ROW_Z = 47.5, 3.2, 3.5
TAIL_W, TAIL_T, LAP = 0.6, 0.3, 3.9
X = [42.5, 40.0, 37.5, 35.0] + [27.5 - 2.5 * i for i in range(23)] + [-35.0, -37.5, -40.0, -42.5]


def blk(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def build():
    y0, y1, y2 = GAP, GAP + BASE_H, GAP + BASE_H + NOSE_H
    body = blk(-BODY_L / 2, BODY_L / 2, y0, y1, ZMID - BODY_D / 2, ZMID + BODY_D / 2)
    body = body + blk(-NOSE_L / 2, NOSE_L / 2, y1, y2, ZMID - NOSE_D / 2, ZMID + NOSE_D / 2)
    body = body - blk(-NOSE_L / 2 + 1.5, NOSE_L / 2 - 1.5, y1 + 1.0, y2 + 1, ZMID - SLOT_W / 2, ZMID + SLOT_W / 2)
    for sx in (-1, 1):
        body = body - Pos(sx * EAR_X, (y0 + y1) / 2, ZMID) * Cylinder(EAR_D / 2, BASE_H + 2, rotation=(90, 0, 0))
    tails = []
    for x in X:
        xa, xb = x - TAIL_W / 2, x + TAIL_W / 2
        # F.Cu side (pins 32-62): jog from the row at Z = ZMID + ROW_Z down to the F face, lap on the face
        tails.append(blk(xa, xb, 0.05, GAP - 0.05, 0.0, ZMID + ROW_Z + TAIL_T / 2))
        tails.append(blk(xa, xb, -LAP, GAP - 0.05, 0.0, TAIL_T))
        # B.Cu side (pins 1-31)
        tails.append(blk(xa, xb, 0.05, GAP - 0.05, ZMID - ROW_Z - TAIL_T / 2, -BOARD_T))
        tails.append(blk(xa, xb, -LAP, GAP - 0.05, -BOARD_T - TAIL_T, -BOARD_T))
    socket = Compound(children=[body] + tails)
    socket.label = "SNES_Slot_Console_Straddle"
    return socket


socket = build()
try:
    show(socket, "socket")         # build123d MCP session
    IN_SESSION = True
except NameError:
    IN_SESSION = False

if __name__ == "__main__" and not IN_SESSION:
    export_step(socket, "SNES_Slot_Console_Straddle.step")
