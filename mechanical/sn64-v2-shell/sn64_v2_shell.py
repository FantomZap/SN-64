"""SN64 v2 shell: upright in-line tower with a mushroom cap (2026-09-30). build123d, millimetres.

Owner's arrangement: one continuous vertical item. The board stands in the N64/M64 slot and the
SNES cartridge stands upright on top of it, in line, like a TriStar 64. Above the USB-C the shell
flares out into a mushroom cap whose pocket wraps the bottom of the cartridge on all four sides,
so the shell holds the cartridge upright (owner, 2026-09-30).

The SNES socket is the 62-contact console-replacement part with ears. It sits on the board's top
edge with its tails on pads on both faces (pins 1-31 on B.Cu, the face toward the front of the
console; 32-62 on F.Cu; how the tails reach the pads is settled in the board footprint once a
sample is measured) and its ears screw into the shell, so the shell takes the cartridge insertion
force and the solder joints none.

Build frame (the KiCad board view): X across the board, Y up with 0 at the N64 tongue shoulders,
Z out of the board's F.Cu face. F.Cu faces the BACK of the console (N64 edge pins 1-25 are on
B.Cu, and pin 1 is on the front row), so a player sees the B.Cu side and the USB-C (at +X) on
their left. Exported files are turned +90 degrees about X so a viewer sees Z up and the F.Cu face
toward -Y (the FreeCAD "Front" view looks at the F.Cu face, i.e. from behind the console).

Sourced
  SummerCart64 shell outer width 116.1, thickness 18.06
      (references/downloads/summercart64/hw/shell/injection mold/sc64_shell.stp, CERN-OHL-S-2.0)
  board 1.2 thick, tongue 64.5 wide and 10.5 below the shoulders, 101.8 wide in the slot region
      (hardware/sn64-v2/sn64-v2.kicad_pcb, SummerCart64 edge geometry)
  socket, console-replacement family (OpenSFC CartSlot.kicad_mod, SHA-256 1f9b60dd...,
      docs/dimensions.md): 62 contacts, 31 per row, 2.5 pitch with two 7.5 gaps, 85.0 first to
      last, rows 7.0 apart, body 99.0 x 11.25, mounting holes 3.2 at +-47.5 (95.0 apart)
  pins 1-31 face the front of the console (the cartridge label side) with pin 1 at the left end
      seen from the front (SNESdev wiki "Cartridge connector"; OpenSFC SHVC-CPU-01 board); pins 31
      and 62 are the cartridge audio inputs
  N64 edge pin 1 on the front row of the slot (n64brew "Game Pak")
  USB-C receptacle J101 body 8.94 x 6.9 x 3.16 (its footprint)
  cartridge shell 136 x 88 x 20 (North American; Wikipedia, unverified; SFC/PAL 130 x 86 x 20)

Assumed, to be measured before anything is cut
  console top line 28 above the shoulders (N64); the M64 opening is unknown
  shell bottom 2.5 below the tongue tip; walls 2.0, cap walls 3.0
  socket base 6.0 and nose 9.0 high, nose 88 x 9. One marketplace listing gives 97 x 21 x 9 mm
      without ears and 137 x 21 x 9 mm with ears, which conflicts with the 95 mm hole spacing;
      the sample decides.
  tails drawn as a jog from each row to the board face and a 3 mm lap on each face
  cartridge seats with its bottom face on the socket shoulder, 20 mm deep in the cap pocket
  flare from 57.5 to 68 above the shoulders, cap corner radius 4
  USB-C plug overmold 12.35 x 6.5 (window 13 x 7)

Proposal (board changes that follow this shell; the board is not changed yet)
  socket on the top edge at 70 (the committed board height)
  board widened to 111 between 32 and 60 so the USB-C reaches the right wall; USB-C centre at 50
  top 10 mm narrowed to 88 so the ear screws pass beside the board

In the build123d MCP session: execute_file this script. Elsewhere (Python with build123d), run it
from the output folder: python sn64_v2_shell.py
"""
from build123d import *

# sourced
W_STEM, T_STEM = 116.1, 18.06
BOARD_T, TONGUE_W, TONGUE_H, BOARD_W_SLOT = 1.2, 64.5, 10.5, 101.8
SOCK_L, SOCK_D, EAR_X, EAR_HOLE, ROW_Z, PIN_SPAN = 99.0, 11.25, 47.5, 3.2, 3.5, 85.0
USB_W, USB_D, USB_H = 8.94, 6.9, 3.16
CART_W, CART_H, CART_T = 136.0, 88.0, 20.0

# assumed
WALL, CAP_WALL, Y_BOT, Y_LINE = 2.0, 3.0, -13.0, 28.0
SOCK_BASE_H, NOSE_H, NOSE_L, NOSE_D = 6.0, 9.0, 88.0, 9.0
TAIL_T, TAIL_LAP = 0.5, 3.0
PLUG_W, PLUG_T = 13.0, 7.0
POCKET_D, POCKET_CLR = 20.0, 0.3
Y_F0, Y_F1 = 57.5, 68.0                # flare from the stem to the cap, above the USB-C window
R_STEM, R_CAP = 1.0, 4.0               # corner radii

# proposal
Y_BOARD_TOP, Y_WIDE0, Y_WIDE1, BOARD_W_WIDE, NECK_W, Y_USB = 70.0, 32.0, 60.0, 111.0, 88.0, 50.0

# derived
Y_SOCK0 = Y_BOARD_TOP + 0.5            # socket body underside
Y_TOP = Y_SOCK0 + SOCK_BASE_H          # nose shoulder = pocket floor = cartridge seat
Y_CAP_TOP = Y_TOP + POCKET_D
INNER_X = W_STEM / 2 - WALL            # inner face of the stem side walls
POCKET_W, POCKET_T = CART_W + 2 * POCKET_CLR, CART_T + 2 * POCKET_CLR
CAP_W, CAP_T = POCKET_W + 2 * CAP_WALL, POCKET_T + 2 * CAP_WALL
USB_ZC = BOARD_T / 2 + USB_H / 2       # receptacle centre off the board mid-plane


def box(x, y0, y1, z, w, t):
    """Box spanning y0..y1, centred on x and z, w wide (X) and t thick (Z)."""
    return Pos(x, (y0 + y1) / 2, z) * Box(w, y1 - y0, t)


def y_cyl(x, y0, y1, z, d):
    """Cylinder of diameter d along Y."""
    return Pos(x, (y0 + y1) / 2, z) * Cylinder(d / 2, y1 - y0, rotation=(90, 0, 0))


def section(y, w, t, r):
    """Rounded rectangle w (X) by t (Z) in the horizontal plane at height y, normal +Y."""
    return Plane(origin=(0, y, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0)) * RectangleRounded(w, t, r)


def prism(y0, y1, w, t, r):
    return extrude(section(y0, w, t, r), amount=y1 - y0)


def bell(y0, y1, w0, t0, r0, w1, t1, r1):
    """Mushroom underside: smooth loft that widens fast near the top (convex bell)."""
    ym = y0 + 0.6 * (y1 - y0)
    k = 0.8
    mid = section(ym, w0 + k * (w1 - w0), t0 + k * (t1 - t0), r0 + k * (r1 - r0))
    return loft([section(y0, w0, t0, r0), mid, section(y1, w1, t1, r1)])


def build():
    # outer: SummerCart64-width stem, bell flare, cap
    outer = (prism(Y_BOT, Y_F0, W_STEM, T_STEM, R_STEM)
             + bell(Y_F0, Y_F1, W_STEM, T_STEM, R_STEM, CAP_W, CAP_T, R_CAP)
             + prism(Y_F1, Y_CAP_TOP, CAP_W, CAP_T, R_CAP))
    # inner cavity, raised 1 mm through the flare so the sloped wall keeps about 2 mm
    wi, ti, ci, cti = W_STEM - 2 * WALL, T_STEM - 2 * WALL, CAP_W - 2 * WALL, CAP_T - 2 * WALL
    inner = (prism(Y_BOT + WALL, Y_F0 + 1, wi, ti, 0.5)
             + bell(Y_F0 + 1, Y_F1 + 1, wi, ti, 0.5, ci, cti, R_CAP - WALL)
             + prism(Y_F1 + 1, Y_TOP - WALL, ci, cti, R_CAP - WALL))
    shell = outer - inner
    shell = shell - box(0, Y_TOP, Y_CAP_TOP + 1, 0, POCKET_W, POCKET_T)                  # cartridge pocket
    shell = shell - box(0, Y_TOP - WALL - 1, Y_TOP + 1, 0, SOCK_L + 0.5, SOCK_D + 0.5)  # socket opening
    shell = shell - box(0, Y_BOT - 1, Y_BOT + WALL + 1, 0, TONGUE_W + 1.5, BOARD_T + 2.0)  # tongue opening
    shell = shell - box(W_STEM / 2 - WALL / 2, Y_USB - PLUG_W / 2, Y_USB + PLUG_W / 2, USB_ZC,
                        WALL + 1, PLUG_T)                                                # USB-C window
    # brackets under the socket ears, reaching out to the flared wall
    x0, x1 = NECK_W / 2 + 0.5, CAP_W / 2
    brackets = None
    for s in (-1, 1):
        b = box(s * (x0 + x1) / 2, Y_SOCK0 - 10, Y_SOCK0, 0, x1 - x0, T_STEM - 2 * WALL)
        b = b - y_cyl(s * EAR_X, Y_SOCK0 - 8, Y_SOCK0 + 1, 0, 2.5)                         # ear screw pilot
        brackets = b if brackets is None else brackets + b
    shell = shell + (brackets & outer)

    board = (box(0, -TONGUE_H, 0, 0, TONGUE_W, BOARD_T) + box(0, 0, Y_WIDE0, 0, BOARD_W_SLOT, BOARD_T)
             + box(0, Y_WIDE0, Y_WIDE1, 0, BOARD_W_WIDE, BOARD_T)
             + box(0, Y_WIDE1, Y_BOARD_TOP, 0, NECK_W, BOARD_T))

    socket = box(0, Y_SOCK0, Y_TOP, 0, SOCK_L, SOCK_D) + box(0, Y_TOP, Y_TOP + NOSE_H, 0, NOSE_L, NOSE_D)
    socket = socket - box(0, Y_TOP + 1.0, Y_TOP + NOSE_H + 1, 0, NOSE_L - 3, 1.6)   # cartridge slot
    for s in (-1, 1):
        socket = socket - y_cyl(s * EAR_X, Y_SOCK0 - 1, Y_TOP + 1, 0, EAR_HOLE)
        # tails, one strip per row: jog in from the row to the face, then lap down the face
        z_in, z_out = BOARD_T / 2, ROW_Z + TAIL_T / 2
        socket = socket + box(0, Y_BOARD_TOP, Y_SOCK0, s * (z_in + z_out) / 2, PIN_SPAN + 1.5, z_out - z_in)
        socket = socket + box(0, Y_BOARD_TOP - TAIL_LAP, Y_SOCK0, s * (z_in + TAIL_T / 2), PIN_SPAN + 1.5, TAIL_T)

    cart = (box(0, Y_TOP, Y_TOP + CART_H, 0, CART_W, CART_T)
            - box(0, Y_TOP - 1, Y_TOP + NOSE_H + 0.5, 0, NOSE_L + 1, NOSE_D + 1))   # opening for the nose

    usb = box(INNER_X - 0.05 - USB_D / 2, Y_USB - USB_W / 2, Y_USB + USB_W / 2, USB_ZC, USB_D, USB_H)

    console = (box(0, Y_LINE - 1, Y_LINE, 0, 200, 90)
               - box(0, Y_LINE - 2, Y_LINE + 1, 0, W_STEM + 2, T_STEM + 2))        # console top (assumed)

    return {"shell": shell, "board": board, "socket": socket, "cartridge": cart, "usbc": usb,
            "console_top": console}


def viewer_frame(parts):
    """Rotated copies (Z up, front face toward -Y) as a labelled assembly."""
    rotated = {}
    for name, obj in parts.items():
        r = obj.rotate(Axis.X, 90)
        r.label = name
        rotated[name] = r
    asm = Compound(children=list(rotated.values()))
    asm.label = "sn64_v2_shell"
    return asm, rotated


def export_all(parts, out_dir):
    asm, rotated = viewer_frame(parts)
    export_step(asm, f"{out_dir}/sn64-v2-shell-assembly.step")
    export_stl(asm, f"{out_dir}/sn64-v2-shell-assembly.stl")
    export_stl(rotated["shell"], f"{out_dir}/sn64-v2-shell-only.stl")


def report(parts):
    bb = parts["shell"].bounding_box()
    print(f"shell {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, "
          f"volume {parts['shell'].volume / 1000:.1f} cm3, valid {parts['shell'].is_valid}")
    print(f"console line {Y_LINE} (assumed), USB-C centre {Y_USB} ({Y_USB - Y_LINE:.0f} above the line), "
          f"flare {Y_F0}..{Y_F1}, board top {Y_BOARD_TOP}, cartridge seat {Y_TOP}, cap top {Y_CAP_TOP} "
          f"(pocket {POCKET_D:.0f} deep), cartridge top {Y_TOP + CART_H} "
          f"({Y_TOP + CART_H - Y_LINE:.1f} above the console line), cap {CAP_W:.1f} x {CAP_T:.1f}")


parts = build()
try:
    for _name, _obj in parts.items():
        show(_obj, _name)          # build123d MCP session
    IN_SESSION = True
except NameError:
    IN_SESSION = False

if __name__ == "__main__" and not IN_SESSION:
    report(parts)
    export_all(parts, ".")
