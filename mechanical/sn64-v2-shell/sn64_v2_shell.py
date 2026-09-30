"""SN64 v2 shell: first envelope model (2026-09-30). build123d, millimetres.

Build frame (the same view as the KiCad board): X across the board, Y up with 0 at the N64
tongue shoulders, Z out of the board's front face (the socket side). The exported files are
turned +90 degrees about X so a viewer sees Z up and the front face toward -Y (FreeCAD "Front").

Sourced dimensions
  SummerCart64 shell outer width 116.1 and thickness 18.06
      (references/downloads/summercart64/hw/shell/injection mold/sc64_shell.stp, CERN-OHL-S-2.0)
  board profile 101.8 wide, tongue 64.5 wide and 10.5 below the shoulders, 1.2 thick
      (hardware/sn64-v2/sn64-v2.kicad_pcb, SummerCart64 edge geometry)
  USB-C receptacle J101 body 8.94 x 6.9 x 3.16 (its footprint in hardware/sn64-v2)
  SNES socket body 99 x 11.25, nose 7 (docs/design/socket-selection.md, console-replacement family)

Assumed or nominal, to be replaced by measurement before any shell is cut
  console top line 28.0 above the shoulders (N64; the M64 opening is unknown)
  shell bottom 2.5 below the tongue tip (Y_BOT = -13)
  socket body height 12 above the board face
  cartridge envelope 136 x 88 x 20 (nominal; measure a real cartridge)
  USB-C plug envelope 12.35 x 6.5 (window 13 x 7)
  wall 2.0, cartridge tray plate 3.0 with 10 mm rails and two triangular ribs, no split line yet

Board position in this model: socket centreline 74.5 above the shoulders (the committed board has
it at 56.5; the 18 mm lift is the proposal under discussion), board top at 85, USB-C centre at 50.

Run inside the build123d MCP session (execute_file) or with any Python that has build123d:
    python sn64_v2_shell.py <output directory>
"""
from build123d import *

W, T, WALL = 116.1, 18.06, 2.0
Y_BOT, Y_LINE = -13.0, 28.0          # shell bottom; console top line (ASSUMED)
Y_SOCK = 74.5                        # socket centreline above the shoulders
Y_USB = 50.0                         # USB-C centre: 22 above the console line, plug top 5 under the tray
Y_BOARD_TOP = 85.0
Y_TOP = Y_BOARD_TOP + 1.0 + WALL     # 88
ZF = T / 2                           # front outer face
Y_TRAY = Y_SOCK - 10 - 3             # tray plate under the flat cartridge (cartridge underside at Y_SOCK - 10)


def build():
    body = Pos(0, (Y_BOT + Y_TOP) / 2, 0) * Box(W, Y_TOP - Y_BOT, T)
    cav = Pos(0, (Y_BOT + Y_TOP) / 2, 0) * Box(W - 2 * WALL, Y_TOP - Y_BOT - 2 * WALL, T - 2 * WALL)
    body = body - cav
    body = body - (Pos(0, Y_BOT, 0) * Box(66.0, 2 * WALL + 1, 3.2))                     # tongue opening, bottom
    body = body - (Pos(0, Y_SOCK, ZF - WALL / 2) * Box(100.5, 12.5, WALL + 1))           # socket window, front wall
    body = body - (Pos(W / 2 - WALL / 2, Y_USB, 0.6 + 1.6) * Box(WALL + 1, 13.0, 7.0))  # USB-C window, right wall
    # cartridge tray: plate under the cartridge, side rails, two ribs back to the front wall
    tray = Pos(0, Y_TRAY + 1.5, ZF + 45) * Box(142, 3, 90)
    rail_l = Pos(-69.5, Y_TRAY + 5, ZF + 45) * Box(3, 10, 90)
    rail_r = Pos(69.5, Y_TRAY + 5, ZF + 45) * Box(3, 10, 90)
    rib = Plane.YZ * extrude(Polygon((Y_TRAY, ZF), (Y_TRAY, ZF + 60), (Y_TRAY - 30, ZF)), 3)
    rib_l = Pos(-40, 0, 0) * rib
    rib_r = Pos(40, 0, 0) * rib
    shell = body + tray + rail_l + rail_r + rib_l + rib_r
    # references drawn with the shell
    board = (Pos(0, Y_BOARD_TOP / 2, 0) * Box(101.8, Y_BOARD_TOP, 1.2)) + (Pos(0, -5.25, 0) * Box(64.5, 10.5, 1.2))
    socket = Pos(0, Y_SOCK, 0.6 + 6) * Box(99, 11.25, 12)
    cart = Pos(0, Y_SOCK, ZF + 3 + 44) * Box(136, 20, 88)   # overlaps the socket nose by 0.57 mm: envelope only
    usb = Pos(50.9 - 3.45 + 0.6, Y_USB, 0.6 + 1.58) * Box(6.9, 8.94, 3.16)
    return {"shell": shell, "board": board, "socket": socket, "cartridge": cart, "usbc": usb}


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
    print(f"shell {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, volume {parts['shell'].volume / 1000:.1f} cm3, "
          f"valid {parts['shell'].is_valid()}")
    print(f"cartridge underside Y={Y_SOCK - 10:.1f}, tray {Y_TRAY:.1f}..{Y_TRAY + 3:.1f}, "
          f"USB plug top Y={Y_USB + 6.2:.1f}, console line {Y_LINE} (assumed)")


parts = build()
try:
    for _name, _obj in parts.items():
        show(_obj, _name)          # build123d MCP session only
except NameError:
    pass

if __name__ == "__main__":
    import sys
    report(parts)
    export_all(parts, sys.argv[1] if len(sys.argv) > 1 else ".")
