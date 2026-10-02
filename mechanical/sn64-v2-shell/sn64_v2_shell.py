"""SN64 v2 shell: N64 cartridge body with a rounded mushroom cap (2026-09-30). build123d, mm.

Owner's direction: one continuous vertical item. The part that plugs into the console must look
like an N64 cartridge (rounded front corners, grooves, the real port opening), and the cap that
holds the SNES cartridge must be smooth and round, in Nintendo's own design language.

How it is built
  lower body   the real N64-shaped shell of SummerCart64, its two halves, from its bottom up to
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
  halves       the shell is two parts, like an N64 cartridge: the label-side half carries the board,
               the back half closes over it. They part at the board's back face, where SummerCart64's
               halves part. Six screws from the back hold them: four through the board, two into
               the brackets under the socket ears.
  board        mounted the way a Nintendo cartridge mounts its board (owner, 2026-10-01): at the four
               screw holes the label-side post has a shelf the board sits on and a hollow spigot that
               goes through the board, 1.1 high, a little less than the board is thick, so the back
               post lands on the board and holds it down. The board cannot shift and is not held by
               the screws alone.
  registration two solid pins on the label-side half go through the other two board holes, which are
               at different heights left and right: a board turned back to front cannot seat, and
               the shell will not close on it.
  logo         the SN64 logo stamped into the front of the cap the way a Game Boy cartridge has its
               logo (owner, 2026-10-01): a pill-shaped pocket 19 mm high and 0.6 mm deep, which is
               the inside of the logo's ring, with the buttons and letters of
               assets/logo/sn64-logo-mono.svg standing in it level with the face. Nothing is proud.
  back logo    the owner's FantomZap logo stamped into the back of the cap the same way (owner,
               2026-10-01): a pill-shaped pocket of the same height and depth, with the warning
               triangle, the bolt and the letters of assets/logo/fantomzap/fantomzap-wordmark-mono.svg
               standing in it level with the face. It reads the right way round from behind.

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
  console top surface: the owner measured 30 mm from it down to the plastic floor of the cartridge
      hole, where the cartridge shell rests, the same on the N64 and the M64 (2026-10-01). The shell
      bottom is 12.31 below the shoulders, so the console top is 17.7 above them.
  SummerCart64's own USB-C opening spans 25.8-39.2 mm above the shoulders (8 mm above that top)
  board 1.2 thick, tongue 64.5 wide and 10.5 below the shoulders, outline as hardware/sn64-v2
  socket, console-replacement family (OpenSFC CartSlot, docs/dimensions.md): body 99.0 x 11.25,
      ear holes 3.2 at +-47.5, rows 7.0 apart, 85.0 first to last
  USB-C receptacle J101 body 8.94 x 6.9 x 3.16 (its footprint)
  US cartridge: caliper measurements by rainwarrior (NESdev forum t=23890), listed with the constants

Assumed, to be measured before anything is cut
  socket base 6.0 high (one listing: 21 mm overall with tails); nose from the SNES Jr connector
  cartridge seats with its bottom face on the socket shoulder
  cap: 5 mm walls, pocket clearance 0.6 / 0.3, rim 21.5 mm above the seat at the centre and 6 mm
      lower at the ends
  USB-C plug overmold 12.35 x 6.5 at most (recess 13 x 7)

Two geometries, picked by VARIANT below
  "board-60"  the board in hardware/sn64-v2 as it is since 2026-10-01 (owner: shorter, with about
      5 mm clear on each side of the USB port): top edge 60 above the shoulders.
        USB-C centre 32.5: the lowest the board allows (its side notches for the shell's locating
            posts end at 26.4) and the height of SummerCart64's own port; window 26.0-39.0, 8.3 above
            the console top
        flare from 44.0 (5 above the window) to the board top
        board top 60.0: translator row (top at 47.7), 8 mm of fan-out, then the socket pads
      The tracked STEP, STL and shell-*.png show this one.
  "board-70"  the geometry before that: top edge 70, USB-C centre 50, flare 57.5-70. Kept for
      comparison; its files carry "board-70" in the name and are not tracked.

In the build123d MCP session: execute_file this script. Elsewhere (Python with build123d), run it
from the repository root: python mechanical/sn64-v2-shell/sn64_v2_shell.py
"""
import build123d as bd
from build123d import *

# sourced
SC64_REL = "references/downloads/summercart64/hw/shell/injection mold/sc64_shell.stp"
SC64_ROOTS = ("", "../../")             # repository root (cwd) or the script folder
DZ = 0.6                                # SummerCart64 shell frame -> board mid-plane at z = 0
BOARD_T, TONGUE_W, TONGUE_H, BOARD_W_SLOT = 1.2, 64.5, 10.5, 101.8
SOCK_L, SOCK_D, EAR_X, EAR_HOLE, ROW_Z, PIN_SPAN = 99.0, 11.25, 47.5, 3.2, 3.5, 85.0
USB_W, USB_D, USB_H = 8.94, 6.9, 3.16
W_STEM = 116.12                         # N64 cartridge width (measured on the SummerCart64 shell)
# US SNES cartridge: caliper measurements by rainwarrior, NESdev forum t=23890, 2022-05-21 ("a little
# rough" in the author's words). Depth = front to back.
CART_W, CART_MID_W = 135.4, 92.2        # total width, width of the thicker middle section
CART_SIDE_T, CART_MID_T = 17.0, 19.9    # thickness of the side sections and of the middle section
CART_SIDE_H, CART_MID_H = 84.2, 87.5    # heights
NOTCH_FROM_SIDE, NOTCH_W, NOTCH_H = 10.0, 4.9, 12.1          # two notches on the rear
FSLOT_Y, FSLOT_H, FSLOT_W, FSLOT_D, FSLOT_D_MID, FSLOT_MID_W = 28.9, 5.0, 83.6, 5.4, 3.9, 24.8   # slot on the front
HOLE_W, HOLE_T = 97.5, 10.9             # card-edge hole in the bottom face
EDGE_W, EDGE_T, EDGE_EXT_W, EDGE_TAB_W, EDGE_GAP = 59.9, 1.27, 89.9, 12.55, 2.2   # PCB edge: normal, extended, tabs
PIN_X = [42.5, 40.0, 37.5, 35.0] + [27.5 - 2.5 * i for i in range(23)] + [-35.0, -37.5, -40.0, -42.5]  # our socket
# console connector nose that enters the cartridge: SNES Jr connector model in qwertymodo's
# kicad-snn-cpu-01 (commit a0018661, CERN-OHL-S-2.0, simplified, SHA-256 7621e92d...): a different
# connector of the same family, used until the sample socket is measured
NOSE_L, NOSE_D, NOSE_H = 94.9, 8.75, 10.55
# N64 cartridge plan outline, right half (X, Z): back end, back-corner mid, back-corner end, widest
# point, parting notch, front-corner mid, front-corner end. Back corners 1 mm, front corners 9 mm.
STEM_O = [(56.78, 9.60), (57.476, 9.318), (57.78, 8.63), (58.06, 0.60), (58.00, 0.40), (55.297, -5.830), (49.00, -8.40)]

CART_HOLE_DEPTH = 30.0                  # console top surface down to the plastic floor the cartridge rests on
                                        # (owner's measurement, N64 and M64, 2026-10-01)
N64_SHELL_BOTTOM = -12.31               # SummerCart64 shell bottom below the shoulders (its STEP)
Y_LINE = N64_SHELL_BOTTOM + CART_HOLE_DEPTH   # console top surface above the shoulders: 17.69

# assumed
WALL = 2.0
Y_CUT = 24.5                            # real SummerCart64 shell below, extruded outline above
SOCK_BASE_H = 6.0
TAIL_T, TAIL_LAP = 0.5, 3.0
PLUG_W, PLUG_T = 13.0, 7.0               # recess for the cable plug's overmold (12.35 x 6.5 at most, ASSUMED)
# USB-C port (owner, 2026-10-01: the plain window was a placeholder). Two steps with rounded ends, as on
# a console: a recess for the plug's overmold, and through its floor an opening just larger than the
# receptacle's face. JAE drawing SJ122205 (docs/design/usb-connector-mechanics.md): receptacle 8.94 x
# 3.16; a mated plug's overmold stops 1.95 in front of the receptacle. The receptacle's face is 2.06
# behind the wall's outer surface here, so without the recess a plug would stop 0.1 short of home.
USB_SIDE = 1                            # +1: board +X, the player's left; -1 if the port moves to the other side
USB_RECESS_DEPTH = 1.0                  # leaves a 1.0 rim around the opening; the overmold ends 0.9 above its floor
USB_OPEN_CLR = 0.33                     # opening larger than the receptacle's face all round
CAP_WALL, POCKET_CLR_X, POCKET_CLR_Z, POCKET_R = 5.0, 0.6, 0.3, 1.0
# cartridge unknowns, to be replaced by two caliper readings on a real cartridge
CART_BACK_TO_PCB = 8.5                  # back face to the PCB mid-plane (ASSUMED: PCB centred in the side sections,
                                        # back face flat, the middle section proud on the label side)
CART_EDGE_RECESS = 2.0                  # bottom face up to the PCB edge (ASSUMED)
CART_HOLE_UP, NOTCH_D = 13.0, 3.0       # how far the hole and the rear notches go in (ASSUMED)
RIM_ABOVE_SEAT, RIM_SAG = 21.5, 6.0     # arched rim: height at the centre, drop at the ends
RIM_FILLETS, LIP_CHAMFERS = (2.5, 2.0, 1.5, 1.2), (0.8, 0.5)
FLARE_U = (0.0, 0.12, 0.25, 0.4, 0.5, 0.6, 0.75, 0.88, 1.0)
# logo stamped into the front (label side) of the cap like the logo on a Game Boy cartridge: owner,
# 2026-10-01. The inside of the logo's ring is a pocket; what is black inside it stays level with the
# face. sn64-logo-mono-plain.svg is the same without the characters on the buttons, for a coarse process.
LOGO_REL = "assets/logo/sn64-logo-mono.svg"
LOGO_H = 19.0                           # height of the pocket; the flat face is about 25 high
LOGO_UP = 12.25                         # its centre above the board's top edge: the middle of the flat face
LOGO_DEPTH = 0.6                        # depth of the pocket
# the owner's FantomZap logo stamped into the back of the cap the same way (owner, 2026-10-01). The
# outlines are traced from his artwork (assets/logo/fantomzap/trace_logo.py). The pocket has the height
# and depth of the front one; the artwork is 14.6 high in it, which makes its strokes 1.1 to 1.4 mm
# wide and the whole logo 88 mm long.
BACK_LOGO_REL = "assets/logo/fantomzap/fantomzap-wordmark-mono.svg"
BACK_LOGO_ART_H = 14.6                  # height of the artwork (the triangle) inside the 19 mm pocket
BACK_LOGO_END = 7.0                     # pocket beyond the artwork at each end (the ends are half circles)
BOARD_W_WIDE, NECK_W = 111.0, 88.0
# two halves and their fasteners (2026-10-01). The parting plane is the board's back face, as in
# SummerCart64's shell.
PART_Z = DZ
# Board mounting the way a Nintendo cartridge does it (owner, 2026-10-01). On the label-side half each
# screw post has a shelf the board rests on and a hollow spigot that passes through the board's hole, so
# the board sits in one place and cannot shift. The spigot is 1.1 high, 0.1 less than the board is
# thick, so the back half's post lands on the board and holds it on the shelf. The four screw holes in
# the board are 4.0 for this (hardware/sn64-v2/tools/set_mounting_holes_v2.py); 2.5 could not take a
# hollow post. The screw head sits in a well 2.5 above the board, as in SummerCart64's shell.
BOARD_HOLE_D, SPIGOT_D, SPIGOT_H, SHELF_D = 4.0, 3.8, 1.1, 6.5
# ASSUMED until a screw is chosen: M2 thread-forming, the size SummerCart64's build guide uses. Pilot
# 1.7 below the shelf; 2.2 through the spigot so no thread is cut in its 0.8 wall; clearance 2.4 and a
# 4.6 well (pan head up to 4.0) in the back post.
PILOT_D, PILOT_DEPTH, RELIEF_D = 1.7, 5.0, 2.2
SHANK_D, WELL_D, SEAT_UP, POST_B_D = 2.4, 4.6, 2.5, 7.0
LOWER_HOLES = [(-47.5, -3.25), (47.5, -3.25)]   # board holes H1 and H2 (SummerCart64's positions)
# The back of an N64 cartridge is stepped in round its two lower screws. SummerCart64's back half has
# that recess: its floor is 5.6 from the board's mid-plane here (5.0 in its own frame; measured on the
# STEP file 2026-10-01), 4.0 below the back face at 9.6. Our two lower posts end level with that floor
# (owner, 2026-10-01: they stood out of the recess as cylinders and should be flush with it).
LOWER_POST_TOP = 5.6
HOLE56_X = 52.4                         # board holes H5 and H6 (their height depends on the variant)
# Registration (owner, 2026-10-01): two solid pins on the label-side half go through board holes H3 and
# H4, which are at different heights left and right. A board turned back to front has no holes under
# the pins, sits on their tips and the shell cannot close.
PIN_HOLES = [(-47.5, 6.5), (47.5, 9.5)]
PIN_D, PIN_UP, PIN_POST_D = 2.3, 2.0, 5.0   # pin in a 2.5 hole, standing 2.0 beyond the board's back face
CAP_SCREW_X, CAP_POST_D = 57.5, 8.0     # two screws through the back half into the socket ear brackets
BRACKET_Z = 7.0                         # the ear brackets reach this far each side of the board's mid-plane
BRACKET_GAP = 0.25                      # between the brackets (label-side half) and the back half's wall

VARIANT = "board-60"                    # "board-60": the board as it is; "board-70": the taller one before 2026-10-01
if VARIANT == "board-60":               # hardware/sn64-v2 today
    USB_CLEAR = 5.0                     # plain wall above the USB-C window before the flare starts (owner)
    Y_BOARD_TOP, Y_WIDE0, Y_WIDE1, Y_USB = 60.0, 26.4, 50.0, 32.5
    Y_HOLE56 = 44.5
    Y_F0 = Y_USB + PLUG_W / 2 + USB_CLEAR   # 44.0
elif VARIANT == "board-70":             # before the refit of 2026-10-01
    Y_BOARD_TOP, Y_WIDE0, Y_WIDE1, Y_USB = 70.0, 32.0, 60.0, 50.0
    Y_HOLE56 = 38.0
    Y_F0 = 57.5                         # S-curve flare starts 1 mm above the USB-C window
else:
    raise ValueError(f"unknown VARIANT {VARIANT!r}")
Y_F1 = Y_BOARD_TOP                      # the flare ends at the board's top edge
TAG = "" if VARIANT == "board-60" else "-" + VARIANT     # in the names of exported files

# derived
Y_SOCK0 = Y_BOARD_TOP + 0.5             # socket body underside
Y_TOP = Y_SOCK0 + SOCK_BASE_H           # nose shoulder = pocket floor = cartridge seat
RIM_C = Y_TOP + RIM_ABOVE_SEAT          # rim height at the centre
# cartridge in the shell frame: its PCB is in the socket slot at z = 0, label side toward -Z
CART_ZB = CART_BACK_TO_PCB              # back face
CART_ZF_SIDE, CART_ZF_MID = CART_ZB - CART_SIDE_T, CART_ZB - CART_MID_T
POCKET_W = CART_W + 2 * POCKET_CLR_X
POCKET_Z0, POCKET_Z1 = CART_ZF_MID - POCKET_CLR_Z, CART_ZB + POCKET_CLR_Z
POCKET_T, ZC = POCKET_Z1 - POCKET_Z0, (POCKET_Z0 + POCKET_Z1) / 2   # the cap is centred on the pocket
CAP_HW, CAP_HT = POCKET_W / 2 + CAP_WALL, POCKET_T / 2 + CAP_WALL
R_RIM = (CAP_HW ** 2 + RIM_SAG ** 2) / (2 * RIM_SAG)
USB_ZC = BOARD_T / 2 + USB_H / 2
C45 = 0.70710678
# cap outline: 6 mm back corners, 9 mm front corners (the N64 cartridge's own radius)
CAP_O = [(CAP_HW - 6, ZC + CAP_HT), (CAP_HW - 6 + 6 * C45, ZC + CAP_HT - 6 + 6 * C45), (CAP_HW, ZC + CAP_HT - 6),
         (CAP_HW, ZC), (CAP_HW, ZC - CAP_HT + 9), (CAP_HW - 9 + 9 * C45, ZC - CAP_HT + 9 - 9 * C45), (CAP_HW - 9, ZC - CAP_HT)]
# cavities: 2 mm inside the stem and the cap
STEM_I = [(55.56, 7.60), (55.914, 7.454), (56.06, 7.10), (56.06, 1.20), (56.00, 0.60), (53.95, -4.35), (49.00, -6.40)]
CAP_I = [(CAP_HW - 6, ZC + CAP_HT - 2), (CAP_HW - 6 + 4 * C45, ZC + CAP_HT - 6 + 4 * C45), (CAP_HW - 2, ZC + CAP_HT - 6),
         (CAP_HW - 2, ZC), (CAP_HW - 2, ZC - CAP_HT + 9), (CAP_HW - 9 + 7 * C45, ZC - CAP_HT + 9 - 7 * C45),
         (CAP_HW - 9, ZC - CAP_HT + 2)]
NOTES = []


def box(x, y0, y1, z, w, t):
    """Box spanning y0..y1, centred on x and z, w wide (X) and t thick (Z)."""
    return Pos(x, (y0 + y1) / 2, z) * Box(w, y1 - y0, t)


def y_cyl(x, y0, y1, z, d):
    """Cylinder of diameter d along Y."""
    return Pos(x, (y0 + y1) / 2, z) * Cylinder(d / 2, y1 - y0, rotation=(90, 0, 0))


def z_cyl(x, y, z0, z1, d):
    """Cylinder of diameter d along Z."""
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(d / 2, z1 - z0)


def front_post(x, y, envelope=None):
    """Label-side screw post: (what to add, what to cut). Shelf at the board's front face, spigot
    through the board, pilot hole below the shelf. envelope clips the post to the outside of the shell."""
    zb = BOARD_T / 2
    body = (z_cyl(x, y, -14, -zb, SHELF_D) & envelope) if envelope is not None else z_cyl(x, y, -6.5, -zb, SHELF_D)
    add = body + z_cyl(x, y, -zb, -zb + SPIGOT_H, SPIGOT_D)
    cut = z_cyl(x, y, -zb - PILOT_DEPTH, -zb + 0.01, PILOT_D) + z_cyl(x, y, -zb, zb + 0.5, RELIEF_D)
    return add, cut


def back_post(x, y, z0, d, envelope=None, top=9.6):
    """Back screw post from z0 to the back wall: (what to add, what to cut). Hole for the screw and a
    well in which its head sits SEAT_UP above z0. The post ends at the outside of the shell: where
    envelope gives it, or at top."""
    body = (z_cyl(x, y, z0, 16, d) & envelope) if envelope is not None else z_cyl(x, y, z0, top, d)
    cut = z_cyl(x, y, z0 - 0.6, z0 + SEAT_UP + 0.05, SHANK_D) + z_cyl(x, y, z0 + SEAT_UP, 30, WELL_D)
    return body, cut


def inset(pts, d):
    """Outline control points moved d toward the middle in X."""
    return [(x - d, z) for x, z in pts]


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
    pocket = box(0, Y_TOP, RIM_C + 5, ZC, POCKET_W, POCKET_T)
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


def logo_recess(z_face):
    """The logo stamped into the cap's front face the way a Game Boy cartridge carries its logo: a
    pill-shaped pocket LOGO_DEPTH deep (the inside of the logo's ring) with the button pads and the
    letters standing in it, level with the face. Nothing is proud of the surface.
    Returns (pocket to cut, islands to put back), or None if the logo file is missing."""
    faces = []
    for root in SC64_ROOTS:
        try:
            faces = [f for f in import_svg(root + LOGO_REL) if isinstance(f, Face)]
            break
        except Exception:               # try the next place
            pass
    if not faces:
        NOTES.append("logo file not found: no logo on the cap")
        return None
    ring = max(faces, key=lambda f: f.bounding_box().size.X)
    inside = ring.inner_wires()[0].bounding_box()
    k = LOGO_H / inside.size.Y
    width = k * inside.size.X
    # imported faces carry the importer's own placement, so scale first (all about the same point),
    # then measure and centre
    centre = ring.scale(k).bounding_box().center()
    front = Plane(origin=(0, Y_F1 + LOGO_UP, z_face), x_dir=(-1, 0, 0), z_dir=(0, 0, -1))
    # seen from the front the board's +X is on the left, so the logo's own x runs toward -X
    pocket = extrude(front.from_local_coords(Pos(0, 0, 0.2) * SlotOverall(width, LOGO_H)),
                     amount=LOGO_DEPTH + 0.2, dir=(0, 0, 1))
    islands = []
    for f in faces:
        if f is ring:
            continue
        g = front.from_local_coords(f.scale(k).translate((-centre.X, -centre.Y, 0)))
        islands.append(extrude(g, amount=LOGO_DEPTH + 0.2, dir=(0, 0, 1)))
    NOTES.append(f"logo recess {width:.1f} x {LOGO_H:.1f} mm on the cap front, {LOGO_DEPTH} mm deep, "
                 f"{len(islands)} pieces standing in it level with the face")
    return pocket, islands[0].fuse(*islands[1:])


def back_logo_recess(z_face):
    """The owner's FantomZap logo stamped into the cap's back face like the logo on the front: a
    pill-shaped pocket LOGO_H high and LOGO_DEPTH deep with the triangle, the bolt and the letters
    standing in it, level with the face. Seen from behind it reads the right way round.
    Returns (pocket to cut, islands to put back), or None if the logo file is missing."""
    faces = []
    for root in SC64_ROOTS:
        try:
            faces = [f for f in import_svg(root + BACK_LOGO_REL) if isinstance(f, Face)]
            break
        except Exception:               # try the next place
            pass
    if not faces:
        NOTES.append("back logo file not found: no logo on the back of the cap")
        return None
    # imported faces carry the importer's own placement, so scale first (all about the same point),
    # then measure and centre
    k = BACK_LOGO_ART_H / Compound(children=faces).bounding_box().size.Y
    scaled = [f.scale(k) for f in faces]
    bb = Compound(children=scaled).bounding_box()
    centre, width = bb.center(), bb.size.X + 2 * BACK_LOGO_END
    # seen from behind the board's +X is on the right, so the logo's own x runs toward +X
    back = Plane(origin=(0, Y_F1 + LOGO_UP, z_face), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    pocket = extrude(back.from_local_coords(Pos(0, 0, 0.2) * SlotOverall(width, LOGO_H)),
                     amount=LOGO_DEPTH + 0.2, dir=(0, 0, -1))
    islands = [extrude(back.from_local_coords(f.translate((-centre.X, -centre.Y, 0))),
                       amount=LOGO_DEPTH + 0.2, dir=(0, 0, -1)) for f in scaled]
    NOTES.append(f"back logo recess {width:.1f} x {LOGO_H:.1f} mm on the cap back, {LOGO_DEPTH} mm deep, artwork "
                 f"{bb.size.X:.1f} x {bb.size.Y:.1f}, {len(islands)} pieces standing in it level with the face")
    return pocket, islands[0].fuse(*islands[1:])


def usb_port():
    """What to cut from the stem's side wall for the USB-C port: a recess with rounded ends for the
    plug's overmold, and an opening with rounded ends for the plug itself through the floor of it."""
    x_out = USB_SIDE * W_STEM / 2                        # the wall's outer surface at the port
    # sketch plane on the wall, seen from outside: local x up the board (the port's long side), normal outward
    face = Plane(origin=(x_out, Y_USB, USB_ZC), x_dir=(0, 1, 0), z_dir=(USB_SIDE, 0, 0))
    inward = (-USB_SIDE, 0, 0)
    recess = extrude(face.from_local_coords(Pos(0, 0, 1.0) * SlotOverall(PLUG_W, PLUG_T)),
                     amount=1.0 + USB_RECESS_DEPTH, dir=inward)
    opening = extrude(face.from_local_coords(Pos(0, 0, 1.0) * SlotOverall(USB_W + 2 * USB_OPEN_CLR, USB_H + 2 * USB_OPEN_CLR)),
                      amount=1.0 + WALL + 1.5, dir=inward)
    NOTES.append(f"USB-C port: recess {PLUG_W} x {PLUG_T} with rounded ends, {USB_RECESS_DEPTH} deep; opening "
                 f"{USB_W + 2 * USB_OPEN_CLR:.1f} x {USB_H + 2 * USB_OPEN_CLR:.1f} through a {WALL - USB_RECESS_DEPTH:.1f} rim")
    return recess + opening


def build():
    sc = load_sc64()
    halves = [Pos(0, 0, DZ) * s for s in sc.solids()]
    n64 = halves[0] + halves[1]
    y_bot = n64.bounding_box().min.Y
    back_sc, front_sc = sorted(halves, key=lambda h: h.bounding_box().max.Z, reverse=True)

    # lower body: the two real halves of the N64-shaped shell up to Y_CUT
    keep = box(0, y_bot - 1, Y_CUT, 0, 130, 30)
    drop = (box(-8.5, 17.5, Y_CUT + 0.1, 0.6, 7.0, 13.8)             # support post under our FPGA (both halves)
            + box(50.15, 20.4, 21.95, 0.0, 1.6, 1.6))                 # right locating post: our notch starts 1.3 mm higher
    front = (front_sc & keep) - drop
    back = (back_sc & keep) - drop
    zb = BOARD_T / 2
    for x, y in LOWER_HOLES:                                          # H1, H2: our posts in place of SummerCart64's
        add, cut = front_post(x, y)
        front = front + add - cut
        add, cut = back_post(x, y, zb, POST_B_D, top=LOWER_POST_TOP)   # level with the floor of the recess
        back = back + add - cut
    for x, y in PIN_HOLES:                                            # registration pins through board holes H3, H4
        front = front + z_cyl(x, y, -6.5, -zb, PIN_POST_D) + z_cyl(x, y, -zb, zb + PIN_UP, PIN_D)
        back = back + z_cyl(x, y, zb, 7.7, PIN_POST_D)
        back = back - z_cyl(x, y, 0, zb + PIN_UP + 0.4, PIN_D + 0.4)

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
    upper = upper - usb_port()
    logo = logo_recess(ZC - CAP_HT)
    if logo is not None:
        upper = upper - logo[0] + logo[1]
    back_logo = back_logo_recess(ZC + CAP_HT)
    if back_logo is not None:
        upper = upper - back_logo[0] + back_logo[1]

    # the two halves part at the board's back face
    front_space = Pos(0, 60, PART_Z - 100) * Box(400, 400, 200)
    back_space = Pos(0, 60, PART_Z + 100) * Box(400, 400, 200)
    upper_front, upper_back = upper & front_space, upper & back_space

    # brackets under the socket ears, part of the label-side half: below the parting plane they run into
    # the flared wall, above it they stand free of the back half's wall
    x0, x1 = NECK_W / 2 + 0.5, CAP_HW
    blocks = None
    for s in (-1, 1):
        blk = box(s * (x0 + x1) / 2, Y_SOCK0 - 10, Y_SOCK0, 0, x1 - x0, 2 * BRACKET_Z)
        blk = blk - y_cyl(s * EAR_X, Y_SOCK0 - 8, Y_SOCK0 + 1, 0, 2.5)                           # ear screw pilot
        blocks = blk if blocks is None else blocks + blk
    room = (prism(Y_CUT, Y_F0 + 1, inset(STEM_I, BRACKET_GAP))
            + flare(Y_F0 + 1, Y_F1 + 1, inset(STEM_I, BRACKET_GAP), inset(CAP_I, BRACKET_GAP))
            + prism(Y_F1 + 1, Y_TOP - WALL, inset(CAP_I, BRACKET_GAP)))
    upper_front = upper_front + (blocks & outer & front_space) + (blocks & room & back_space)

    # screws from the back: through board holes H5 and H6, and into the ear brackets
    for s in (-1, 1):
        add, cut = front_post(s * HOLE56_X, Y_HOLE56, outer)
        upper_front = upper_front + add - cut
        add, cut = back_post(s * HOLE56_X, Y_HOLE56, zb, POST_B_D, outer)
        upper_back = upper_back + add - cut
        x, y = s * CAP_SCREW_X, Y_SOCK0 - 5
        upper_front = upper_front - z_cyl(x, y, BRACKET_Z - 6, BRACKET_Z + 0.1, PILOT_D)
        add, cut = back_post(x, y, BRACKET_Z, CAP_POST_D, outer)
        upper_back = upper_back + add - cut
    front, back = front + upper_front, back + upper_back
    NOTES.append("two halves parting at the board's back face; 6 screws from the back; board on shelves with "
                 f"{SPIGOT_H} mm spigots through 4 holes; 2 registration pins")

    board = (box(0, -TONGUE_H, 0, 0, TONGUE_W, BOARD_T) + box(0, 0, Y_WIDE0, 0, BOARD_W_SLOT, BOARD_T)
             + box(0, Y_WIDE0, Y_WIDE1, 0, BOARD_W_WIDE, BOARD_T)
             + box(0, Y_WIDE1, Y_BOARD_TOP, 0, NECK_W, BOARD_T))
    for s in (-1, 1):                                                 # SummerCart64 shell notches in the board
        board = board - box(s * 50.15, 21.9, 24.9, 0, 1.5, 2) - box(s * 48.9, 24.9, 26.4, 0, 4.0, 2)
    for x, y in LOWER_HOLES + [(-HOLE56_X, Y_HOLE56), (HOLE56_X, Y_HOLE56)]:               # screw holes H1, H2, H5, H6
        board = board - z_cyl(x, y, -1, 1, BOARD_HOLE_D)
    for x, y in PIN_HOLES:                                                                # registration holes H3, H4
        board = board - z_cyl(x, y, -1, 1, 2.5)

    socket = box(0, Y_SOCK0, Y_TOP, 0, SOCK_L, SOCK_D) + box(0, Y_TOP, Y_TOP + NOSE_H, 0, NOSE_L, NOSE_D)
    slot_y0 = Y_TOP + CART_EDGE_RECESS                                                          # the PCB edge bottoms here
    socket = socket - box(0, slot_y0, Y_TOP + NOSE_H + 1, 0, EDGE_EXT_W + 0.6, 1.6)             # cartridge slot
    for s in (-1, 1):
        socket = socket + box(s * (EDGE_W + EDGE_GAP) / 2, slot_y0, Y_TOP + NOSE_H, 0, EDGE_GAP - 0.6, 1.6)  # key in the PCB gap
        socket = socket - y_cyl(s * EAR_X, Y_SOCK0 - 1, Y_TOP + 1, 0, EAR_HOLE)
        z_in, z_out = BOARD_T / 2, ROW_Z + TAIL_T / 2                                            # tails, one strip per row
        socket = socket + box(0, Y_BOARD_TOP, Y_SOCK0, s * (z_in + z_out) / 2, PIN_SPAN + 1.5, z_out - z_in)
        socket = socket + box(0, Y_BOARD_TOP - TAIL_LAP, Y_SOCK0, s * (z_in + TAIL_T / 2), PIN_SPAN + 1.5, TAIL_T)

    cart, cart_pcb = us_cartridge(Y_TOP)

    usb = box(USB_SIDE * (W_STEM / 2 - WALL - 0.06 - USB_D / 2), Y_USB - USB_W / 2, Y_USB + USB_W / 2, USB_ZC, USB_D, USB_H)

    console = (box(0, Y_LINE - 1, Y_LINE, DZ, 200, 90)
               - box(0, Y_LINE - 2, Y_LINE + 1, DZ, W_STEM + 2, 18.06 + 2))                      # console top surface (measured)

    return {"shell_front": front, "shell_back": back, "board": board, "socket": socket, "cartridge": cart,
            "cart_pcb": cart_pcb, "usbc": usb, "console_top": console}


def us_cartridge(y0):
    """US SNES cartridge from the measured numbers: bottom face at y0, PCB mid-plane at z = 0, label side -Z."""
    side_w = (CART_W - CART_MID_W) / 2
    body = box(0, y0, y0 + CART_MID_H, (CART_ZB + CART_ZF_MID) / 2, CART_MID_W, CART_MID_T)
    for s in (-1, 1):
        body = body + box(s * (CART_MID_W + side_w) / 2, y0, y0 + CART_SIDE_H, (CART_ZB + CART_ZF_SIDE) / 2,
                          side_w, CART_SIDE_T)
    body = body - box(0, y0 - 1, y0 + CART_HOLE_UP, 0, HOLE_W, HOLE_T)                           # card-edge hole
    body = body - box(0, y0 + CART_HOLE_UP - 0.1, y0 + 72, 0, EDGE_EXT_W + 6, 6.0)               # room for the PCB
    for s in (-1, 1):
        body = body - box(s * (CART_W / 2 - NOTCH_FROM_SIDE - NOTCH_W / 2), y0 - 1, y0 + NOTCH_H,
                          CART_ZB - NOTCH_D / 2 + 0.5, NOTCH_W, NOTCH_D + 1)                     # rear notch
    # front slot: FSLOT_D deep, FSLOT_D_MID deep across the centre trench
    zf, ys = CART_ZF_MID, y0 + FSLOT_Y
    body = body - box(0, ys, ys + FSLOT_H, zf + FSLOT_D_MID / 2 - 0.5, FSLOT_W, FSLOT_D_MID + 1)
    w = (FSLOT_W - FSLOT_MID_W) / 2
    for s in (-1, 1):
        body = body - box(s * (FSLOT_MID_W + w) / 2, ys, ys + FSLOT_H, zf + FSLOT_D / 2 - 0.5, w, FSLOT_D + 1)
    # PCB: extended (62-contact) edge with its two tabs, then the board above
    ye = y0 + CART_EDGE_RECESS
    pcb = box(0, ye, ye + 10, 0, EDGE_W, EDGE_T)
    for s in (-1, 1):
        pcb = pcb + box(s * (EDGE_W / 2 + EDGE_GAP + EDGE_TAB_W / 2), ye, ye + 10, 0, EDGE_TAB_W, EDGE_T)
    pcb = pcb + box(0, ye + 10, y0 + 70, 0, EDGE_EXT_W + 4, EDGE_T)
    return body, pcb


def interface_checks():
    """Numbers that say whether cartridge, socket and pocket agree (printed by report)."""
    tab0 = EDGE_W / 2 + EDGE_GAP
    on_edge = [abs(x) + 0.75 <= EDGE_W / 2 or (tab0 <= abs(x) - 0.75 and abs(x) + 0.75 <= tab0 + EDGE_TAB_W) for x in PIN_X]
    return {
        "socket contacts on the cartridge's PCB edge": f"{sum(on_edge)} of {len(PIN_X)} per side",
        "PCB edge margin beyond the outer contacts": round(tab0 + EDGE_TAB_W - (PIN_X[0] + 0.75), 2),
        "nose clearance in the card-edge hole, each side (width, thickness)": (round((HOLE_W - NOSE_L) / 2, 2), round((HOLE_T - NOSE_D) / 2, 2)),
        "socket base wider than the hole, each side (width, thickness)": (round((SOCK_L - HOLE_W) / 2, 2), round((SOCK_D - HOLE_T) / 2, 2)),
        "contact slot engagement on the PCB": round(NOSE_H - CART_EDGE_RECESS, 2),
        "pocket clearance each side (width, thickness)": (POCKET_CLR_X, POCKET_CLR_Z),
        "pocket and cap offset toward the label side": round(-ZC, 2),
    }


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
    export_step(asm, f"{out_dir}/sn64-v2-shell{TAG}-assembly.step")
    # 0.03 mm chord tolerance: well below print resolution, a fraction of the default file size
    export_stl(asm, f"{out_dir}/sn64-v2-shell{TAG}-assembly.stl", tolerance=0.03, angular_tolerance=0.2)
    for half in ("front", "back"):
        export_stl(rotated["shell_" + half], f"{out_dir}/sn64-v2-shell{TAG}-{half}.stl", tolerance=0.03, angular_tolerance=0.2)


def report(parts):
    front, back = parts["shell_front"], parts["shell_back"]
    bb = Compound(children=[front, back]).bounding_box()
    print(f"variant {VARIANT}: shell {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, bottom {bb.min.Y:.2f}")
    for name, h in (("label-side half", front), ("back half", back)):
        print(f"  {name}: solids {len(h.solids())}, volume {h.volume / 1000:.1f} cm3, valid {h.is_valid}")
    print(f"console top {Y_LINE:.2f} above the shoulders (measured: 30 mm hole), USB-C centre {Y_USB} (window {Y_USB - PLUG_W / 2 - Y_LINE:.1f} above the console top, flare {Y_F0 - Y_USB - PLUG_W / 2:.1f} above the window), "
          f"real N64 shell to {Y_CUT}, flare {Y_F0}..{Y_F1}, cartridge seat {Y_TOP}, rim {RIM_C} at the centre and "
          f"{RIM_C - RIM_SAG} at the ends, cap {2 * CAP_HW:.1f} x {2 * CAP_HT:.1f}, cartridge top {Y_TOP + CART_MID_H}")
    print("notes:", "; ".join(NOTES))
    for k, v in interface_checks().items():
        print(f"  {k}: {v}")


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
