"""SN64 v2 shell: N64 cartridge body with a rounded mushroom cap (2026-09-30). build123d, mm.

Owner's direction: one continuous vertical item. The part that plugs into the console must look
like an N64 cartridge (rounded front corners, grooves, the real port opening), and the cap that
holds the SNES cartridge must be smooth and round, in Nintendo's own design language.

How it is built
  lower body   the real N64-shaped shell of SummerCart64, both halves fused, from its bottom up to
               24.5 mm above the board's shoulders: port opening, feet, board ledges and the two
               mounting bosses exactly as SummerCart64 has them. One support post that would sit
               under our FPGA and 1.3 mm of the right locating post are removed.
  stem         the same shell's outer outline at 24.5 mm (flat back with 1 mm corners, 9 mm front
               corners, two grooves) extruded up to the flare, so the cartridge body continues
               without SummerCart64's own side openings.
  flare        smooth S-curve loft from that outline to the cap outline.
  cap          same outline language (9 mm front corners, 6 mm back corners), 5 mm walls around a
               pocket for the SNES cartridge, rim arched like the top of an N64 cartridge and
               filleted.

License: the lower body and the outline are derived from SummerCart64's shell
(references/downloads/summercart64/hw/shell/injection mold/sc64_shell.stp, commit a1e7996d,
CERN-OHL-S-2.0), so this shell model is CERN-OHL-S-2.0 as well.

Frame (the KiCad board view): X across the board, Y up with 0 at the N64 tongue shoulders, Z out of
the board's F.Cu face. This is SummerCart64's own shell frame moved +0.6 mm in Z (its board lies
z -1.2..0, ours -0.6..0.6); its mounting bosses are at (+-47.5, -3.25) like our H1/H2. F.Cu faces
the BACK of the console, so +Z is the screw side of the cartridge and the label side is -Z; a
player sees the -Z side and the USB-C (at +X) on their left. Exported files are turned +90 degrees
about X so a viewer sees Z up (FreeCAD "Front" looks at the back of the console, "Rear" at the
label side).

Sourced
  SummerCart64 shell geometry and frame (file above; measured in this session)
  SummerCart64's own USB-C opening spans 25.8-39.2 mm above the shoulders, so the console top line
      is below about 25 mm
  board 1.2 thick, tongue 64.5 wide and 10.5 below the shoulders, outline as hardware/sn64-v2
  socket, console-replacement family (OpenSFC CartSlot, docs/dimensions.md): body 99.0 x 11.25,
      ear holes 3.2 at +-47.5, rows 7.0 apart, 85.0 first to last
  USB-C receptacle J101 body 8.94 x 6.9 x 3.16 (its footprint)
  cartridge shell 136 x 88 x 20 (North American; Wikipedia, unverified; SFC/PAL 130 x 86 x 20)

Assumed, to be measured before anything is cut
  console top line drawn at 25; the M64 opening is unknown
  socket base 6.0 and nose 9.0 high, nose 88 x 9 (one listing: 21 mm overall with tails)
  cartridge seats with its bottom face on the socket shoulder
  cap: 5 mm walls, 0.3 mm pocket clearance, rim 21.5 mm above the seat at the centre and 6 mm
      lower at the ends, flare from 57.5 to 70
  USB-C plug overmold 12.35 x 6.5 (window 13 x 7)

In the build123d MCP session: execute_file this script. Elsewhere (Python with build123d), run it
from the repository root: python mechanical/sn64-v2-shell/sn64_v2_shell.py
"""
import build123d as bd
from build123d import *

# sourced
SC64_REL = "references/downloads/summercart64/hw/shell/injection mold/sc64_shell.stp"
SC64_ROOTS = ("", "../../", "C:/Users/RyanB/.claude/projects/SN64/")   # cwd, script folder, this PC
DZ = 0.6                                # SummerCart64 shell frame -> board mid-plane at z = 0
BOARD_T, TONGUE_W, TONGUE_H, BOARD_W_SLOT = 1.2, 64.5, 10.5, 101.8
SOCK_L, SOCK_D, EAR_X, EAR_HOLE, ROW_Z, PIN_SPAN = 99.0, 11.25, 47.5, 3.2, 3.5, 85.0
USB_W, USB_D, USB_H = 8.94, 6.9, 3.16
CART_W, CART_H, CART_T = 136.0, 88.0, 20.0
W_STEM = 116.12                         # N64 cartridge width (measured on the SummerCart64 shell)
# N64 cartridge plan outline, right half (X, Z): back end, back-corner mid, back-corner end, widest
# point, parting notch, front-corner mid, front-corner end. Back corners 1 mm, front corners 9 mm.
STEM_O = [(56.78, 9.60), (57.476, 9.318), (57.78, 8.63), (58.06, 0.60), (58.00, 0.40), (55.297, -5.830), (49.00, -8.40)]

# assumed
WALL, Y_LINE = 2.0, 25.0
Y_CUT = 24.5                            # real SummerCart64 shell below, extruded outline above
SOCK_BASE_H, NOSE_H, NOSE_L, NOSE_D = 6.0, 9.0, 88.0, 9.0
TAIL_T, TAIL_LAP = 0.5, 3.0
PLUG_W, PLUG_T = 13.0, 7.0
CAP_WALL, POCKET_CLR, POCKET_R = 5.0, 0.3, 1.0
Y_F0, Y_F1 = 57.5, 70.0                 # S-curve flare, above the USB-C window
RIM_ABOVE_SEAT, RIM_SAG = 21.5, 6.0     # arched rim: height at the centre, drop at the ends
RIM_FILLETS, LIP_CHAMFERS = (2.5, 2.0, 1.5, 1.2), (0.8, 0.5)
FLARE_U = (0.0, 0.12, 0.25, 0.4, 0.5, 0.6, 0.75, 0.88, 1.0)

# board proposal already applied to hardware/sn64-v2 (2026-09-30)
Y_BOARD_TOP, Y_WIDE0, Y_WIDE1, BOARD_W_WIDE, NECK_W, Y_USB = 70.0, 32.0, 60.0, 111.0, 88.0, 50.0

# derived
Y_SOCK0 = Y_BOARD_TOP + 0.5             # socket body underside
Y_TOP = Y_SOCK0 + SOCK_BASE_H           # nose shoulder = pocket floor = cartridge seat
RIM_C = Y_TOP + RIM_ABOVE_SEAT          # rim height at the centre
POCKET_W, POCKET_T = CART_W + 2 * POCKET_CLR, CART_T + 2 * POCKET_CLR
CAP_HW, CAP_HT = POCKET_W / 2 + CAP_WALL, POCKET_T / 2 + CAP_WALL
R_RIM = (CAP_HW ** 2 + RIM_SAG ** 2) / (2 * RIM_SAG)
USB_ZC = BOARD_T / 2 + USB_H / 2
C45 = 0.70710678
# cap outline: 6 mm back corners, 9 mm front corners (the N64 cartridge's own radius)
CAP_O = [(CAP_HW - 6, CAP_HT), (CAP_HW - 6 + 6 * C45, CAP_HT - 6 + 6 * C45), (CAP_HW, CAP_HT - 6), (CAP_HW, 0.0),
         (CAP_HW, -CAP_HT + 9), (CAP_HW - 9 + 9 * C45, -CAP_HT + 9 - 9 * C45), (CAP_HW - 9, -CAP_HT)]
# cavities: 2 mm inside the stem and the cap
STEM_I = [(55.56, 7.60), (55.914, 7.454), (56.06, 7.10), (56.06, 1.20), (56.00, 0.60), (53.95, -4.35), (49.00, -6.40)]
CAP_I = [(CAP_HW - 6, CAP_HT - 2), (CAP_HW - 6 + 4 * C45, CAP_HT - 6 + 4 * C45), (CAP_HW - 2, CAP_HT - 6), (CAP_HW - 2, 0.0),
         (CAP_HW - 2, -CAP_HT + 9), (CAP_HW - 9 + 7 * C45, -CAP_HT + 9 - 7 * C45), (CAP_HW - 9, -CAP_HT + 2)]
NOTES = []


def box(x, y0, y1, z, w, t):
    """Box spanning y0..y1, centred on x and z, w wide (X) and t thick (Z)."""
    return Pos(x, (y0 + y1) / 2, z) * Box(w, y1 - y0, t)


def y_cyl(x, y0, y1, z, d):
    """Cylinder of diameter d along Y."""
    return Pos(x, (y0 + y1) / 2, z) * Cylinder(d / 2, y1 - y0, rotation=(90, 0, 0))


def outline(y, pts):
    """Closed N64-style outline at height y from the seven right-half control points."""
    def p(i, sgn=1):
        return (sgn * pts[i][0], y, pts[i][1])
    e = [Line(p(0, -1), p(0)), ThreePointArc(p(0), p(1), p(2)), Line(p(2), p(3)), Line(p(3), p(4)),
         ThreePointArc(p(4), p(5), p(6)), Line(p(6), p(6, -1)), ThreePointArc(p(6, -1), p(5, -1), p(4, -1)),
         Line(p(4, -1), p(3, -1)), Line(p(3, -1), p(2, -1)), ThreePointArc(p(2, -1), p(1, -1), p(0, -1))]
    return Face(Wire(e))


def prism(y0, y1, pts):
    return extrude(outline(y0, pts), amount=y1 - y0, dir=(0, 1, 0))


def flare(y0, y1, a, b):
    """Smooth S-curve loft from outline a at y0 to outline b at y1 (smoothstep growth)."""
    secs = []
    for u in FLARE_U:
        s = u * u * (3 - 2 * u)
        pts = [(pa[0] + (pb[0] - pa[0]) * s, pa[1] + (pb[1] - pa[1]) * s) for pa, pb in zip(a, b)]
        secs.append(outline(y0 + (y1 - y0) * u, pts))
    return bd.loft(secs)


def load_sc64():
    err = None
    for root in SC64_ROOTS:
        try:
            return import_step(root + SC64_REL)
        except Exception as ex:          # try the next place
            err = ex
    raise err


def cap_with_rim():
    """Cap block, arched on top, with the cartridge pocket, a filleted rim and a chamfered lip."""
    cap = prism(Y_F1, RIM_C + 2, CAP_O) & (Pos(0, RIM_C - R_RIM, 0) * Cylinder(R_RIM, 4 * CAP_HT))
    pocket = box(0, Y_TOP, RIM_C + 5, 0, POCKET_W, POCKET_T)
    pocket = bd.fillet(pocket.edges().filter_by(Axis.Y), POCKET_R)
    cap = cap - pocket

    def rim_face(s):
        return [f for f in s.faces() if f.geom_type == GeomType.CYLINDER and abs((f.radius or 0) - R_RIM) < 0.5][0]
    for r in RIM_FILLETS:
        try:
            t = bd.fillet(rim_face(cap).outer_wire().edges(), r)
            if t.is_valid:
                cap = t
                NOTES.append(f"rim fillet {r} mm")
                break
        except Exception:
            pass
    else:
        NOTES.append("rim fillet failed")
    for c in LIP_CHAMFERS:
        try:
            t = bd.chamfer([e for w in rim_face(cap).inner_wires() for e in w.edges()], c)
            if t.is_valid:
                cap = t
                NOTES.append(f"pocket lip chamfer {c} mm")
                break
        except Exception:
            pass
    else:
        NOTES.append("pocket lip chamfer failed")
    return cap, pocket


def build():
    sc = load_sc64()
    halves = [Pos(0, 0, DZ) * s for s in sc.solids()]
    n64 = halves[0] + halves[1]
    y_bot = n64.bounding_box().min.Y

    # lower body: the real N64-shaped shell up to Y_CUT
    lower = n64 & box(0, y_bot - 1, Y_CUT, 0, 130, 30)
    lower = lower - box(-8.5, 17.5, Y_CUT + 0.1, 0.6, 7.0, 13.8)      # support post under our FPGA (both halves)
    lower = lower - box(50.15, 20.4, 21.95, 0.0, 1.6, 1.6)            # right locating post: our notch starts 1.3 mm higher

    # stem: the shell's own outline at Y_CUT (grooves and all) extruded to the flare
    ring = sorted(bd.section(n64, section_by=Plane(origin=(0, Y_CUT, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))).faces(),
                  key=lambda f: f.area, reverse=True)[0]
    stem = extrude(Face(ring.outer_wire()), amount=Y_F0 - Y_CUT, dir=(0, 1, 0))

    cap, pocket = cap_with_rim()
    outer = stem + flare(Y_F0, Y_F1, STEM_O, CAP_O) + cap
    inner = (prism(Y_CUT, Y_F0 + 1, STEM_I) + flare(Y_F0 + 1, Y_F1 + 1, STEM_I, CAP_I)
             + prism(Y_F1 + 1, Y_TOP - WALL, CAP_I))
    upper = outer - inner - pocket
    upper = upper - box(0, Y_TOP - WALL - 1, Y_TOP + 1, 0, SOCK_L + 0.5, SOCK_D + 0.5)          # socket opening
    upper = upper - box(W_STEM / 2 - 1.0, Y_USB - PLUG_W / 2, Y_USB + PLUG_W / 2, USB_ZC, 5.0, PLUG_T)  # USB-C window
    # brackets under the socket ears, reaching out to the flared wall
    x0, x1 = NECK_W / 2 + 0.5, CAP_HW
    brackets = None
    for s in (-1, 1):
        b = box(s * (x0 + x1) / 2, Y_SOCK0 - 10, Y_SOCK0, 0, x1 - x0, 14.0)
        b = b - y_cyl(s * EAR_X, Y_SOCK0 - 8, Y_SOCK0 + 1, 0, 2.5)                               # ear screw pilot
        brackets = b if brackets is None else brackets + b
    upper = upper + (brackets & outer)
    shell = lower + upper

    board = (box(0, -TONGUE_H, 0, 0, TONGUE_W, BOARD_T) + box(0, 0, Y_WIDE0, 0, BOARD_W_SLOT, BOARD_T)
             + box(0, Y_WIDE0, Y_WIDE1, 0, BOARD_W_WIDE, BOARD_T)
             + box(0, Y_WIDE1, Y_BOARD_TOP, 0, NECK_W, BOARD_T))
    for s in (-1, 1):                                                 # SummerCart64 shell notches in the board
        board = board - box(s * 50.15, 21.9, 24.9, 0, 1.5, 2) - box(s * 48.9, 24.9, 26.4, 0, 4.0, 2)

    socket = box(0, Y_SOCK0, Y_TOP, 0, SOCK_L, SOCK_D) + box(0, Y_TOP, Y_TOP + NOSE_H, 0, NOSE_L, NOSE_D)
    socket = socket - box(0, Y_TOP + 1.0, Y_TOP + NOSE_H + 1, 0, NOSE_L - 3, 1.6)               # cartridge slot
    for s in (-1, 1):
        socket = socket - y_cyl(s * EAR_X, Y_SOCK0 - 1, Y_TOP + 1, 0, EAR_HOLE)
        z_in, z_out = BOARD_T / 2, ROW_Z + TAIL_T / 2                                            # tails, one strip per row
        socket = socket + box(0, Y_BOARD_TOP, Y_SOCK0, s * (z_in + z_out) / 2, PIN_SPAN + 1.5, z_out - z_in)
        socket = socket + box(0, Y_BOARD_TOP - TAIL_LAP, Y_SOCK0, s * (z_in + TAIL_T / 2), PIN_SPAN + 1.5, TAIL_T)

    cart = (box(0, Y_TOP, Y_TOP + CART_H, 0, CART_W, CART_T)
            - box(0, Y_TOP - 1, Y_TOP + NOSE_H + 0.5, 0, NOSE_L + 1, NOSE_D + 1))               # opening for the nose

    usb = box(W_STEM / 2 - WALL - 0.06 - USB_D / 2, Y_USB - USB_W / 2, Y_USB + USB_W / 2, USB_ZC, USB_D, USB_H)

    console = (box(0, Y_LINE - 1, Y_LINE, DZ, 200, 90)
               - box(0, Y_LINE - 2, Y_LINE + 1, DZ, W_STEM + 2, 18.06 + 2))                      # console top (assumed)

    return {"shell": shell, "board": board, "socket": socket, "cartridge": cart, "usbc": usb,
            "console_top": console}


def viewer_frame(parts):
    """Rotated copies (Z up, F.Cu face toward -Y) as a labelled assembly."""
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
    # 0.03 mm chord tolerance: well below print resolution, a fraction of the default file size
    export_stl(asm, f"{out_dir}/sn64-v2-shell-assembly.stl", tolerance=0.03, angular_tolerance=0.2)
    export_stl(rotated["shell"], f"{out_dir}/sn64-v2-shell-only.stl", tolerance=0.03, angular_tolerance=0.2)


def report(parts):
    sh = parts["shell"]
    bb = sh.bounding_box()
    print(f"shell {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, bottom {bb.min.Y:.2f}, "
          f"solids {len(sh.solids())}, volume {sh.volume / 1000:.1f} cm3, valid {sh.is_valid}")
    print(f"console line {Y_LINE} (assumed), USB-C centre {Y_USB} ({Y_USB - Y_LINE:.0f} above the line), "
          f"real N64 shell to {Y_CUT}, flare {Y_F0}..{Y_F1}, cartridge seat {Y_TOP}, rim {RIM_C} at the centre and "
          f"{RIM_C - RIM_SAG} at the ends, cap {2 * CAP_HW:.1f} x {2 * CAP_HT:.1f}, cartridge top {Y_TOP + CART_H}")
    print("notes:", "; ".join(NOTES))


parts = build()
try:
    for _name, _obj in parts.items():
        show(_obj, _name)          # build123d MCP session
    IN_SESSION = True
except NameError:
    IN_SESSION = False

if __name__ == "__main__" and not IN_SESSION:
    report(parts)
    export_all(parts, "mechanical/sn64-v2-shell")
