"""Prepare the placed main board for autorouting (KiCad's python, run from anywhere).

What it does to hardware/sn64/sn64.kicad_pcb (in place, idempotent: it removes what it
added before):
  1. Netclasses in sn64.kicad_pro: "power" (0.4 mm tracks, 0.6/0.3 vias) for the rails,
     "usb" (0.2 mm) for the USB data pair; Default stays 0.15 mm / 0.45/0.2 vias, 0.1 mm clearance.
  2. BGA fan-out for U401 (LFE5U-85F caBGA-381, 0.8 mm pitch): every used ball in rings 1-9 gets
     a dog-bone via 0.4 mm diagonally outward (0.45 mm / 0.2 mm drill, standard 0.8 mm scheme:
     ball-to-via copper gap 0.14 mm, hole-to-ball 0.27 mm) and a 0.15 mm F.Cu stub. Ring 0
     escapes straight out on F.Cu (left to the router).
  3. Planes: In1.Cu = GND over the whole board; In3.Cu = FPGA_3V3 over the whole board; In4.Cu =
     FPGA_1V1 island over the FPGA core balls and the decoupling bands (the rest of In4 is free).
     F.Cu, In2.Cu, B.Cu (and In4.Cu outside the island) are signal layers.
  4. Fills the zones, saves the board and exports build/route-pcb/sn64.dsn for Freerouting.
Then: java -jar freerouting.jar -de build/route-pcb/sn64.dsn -do build/route-pcb/sn64.ses ...
and hardware/sn64/tools/finish_route.py imports the session.
"""
import json
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parents[1]         # hardware/sn64
REPO = HERE.parents[1]
PCB, PRO = HERE / 'sn64.kicad_pcb', HERE / 'sn64.kicad_pro'
OUT = REPO / 'build' / 'route-pcb'
mm = pcbnew.FromMM
V = pcbnew.VECTOR2I
TAG = 'sn64_prepare_route'

POWER_NETS = ['/FPGA_1V1', '/FPGA_2V5', '/FPGA_3V3', '/FPGA/FPGA_VCCAUX', '/5V_PRE', '/INTERFACE_3V3', '/HOST_3V3',
              '/SNES_5V_CART', '/USB_VBUS', '/USB_3V3', '/HOST_12V', '/AV clock and cartridge audio/ADC_VCC_5V',
              '/Power/SW_1V1', '/Power/SW_2V5', '/Power/SW_3V3', '/Power/L1_5V', '/Power/L2_5V', '/GND']
USB_NETS = ['/USB-C programmer/USB_DP', '/USB-C programmer/USB_DM']


def netclasses_in_project():
    pro = json.loads(PRO.read_text(encoding='utf-8'))
    ns = pro.setdefault('net_settings', {})
    classes = ns.setdefault('classes', [])
    default = next(c for c in classes if c.get('name') == 'Default')
    default.update({'clearance': 0.1, 'track_width': 0.15, 'via_diameter': 0.45, 'via_drill': 0.2,
                    'diff_pair_width': 0.15, 'diff_pair_gap': 0.15})
    classes[:] = [c for c in classes if c.get('name') in ('Default',)]
    # Clearance stays at the board's 0.1 mm: a dog-bone via is 0.14 mm from its neighbouring balls.
    power = dict(default); power.update({'name': 'power', 'clearance': 0.1, 'track_width': 0.4, 'via_diameter': 0.6,
                                         'via_drill': 0.3, 'priority': 1})
    usb = dict(default); usb.update({'name': 'usb', 'track_width': 0.2, 'diff_pair_width': 0.2, 'diff_pair_gap': 0.15,
                                     'priority': 2})
    classes += [power, usb]
    ns['netclass_patterns'] = ([{'netclass': 'power', 'pattern': n} for n in POWER_NETS]
                               + [{'netclass': 'usb', 'pattern': n} for n in USB_NETS])
    PRO.write_text(json.dumps(pro, indent=2) + '\n', encoding='utf-8', newline='\n')


def apply_netclasses(board):
    """Fallback if LoadBoard did not pick the project patterns up."""
    ni = board.GetNetInfo()
    if ni.GetNetItem('/FPGA_1V1').GetNetClassName() == 'power':
        return 'from project file'
    ns = board.GetDesignSettings().m_NetSettings
    for name, width, via, drill, clr, nets in (('power', 0.4, 0.6, 0.3, 0.1, POWER_NETS), ('usb', 0.2, 0.45, 0.2, 0.1, USB_NETS)):
        nc = pcbnew.NETCLASS(name)
        nc.SetTrackWidth(mm(width)); nc.SetViaDiameter(mm(via)); nc.SetViaDrill(mm(drill)); nc.SetClearance(mm(clr))
        ns.SetNetclass(name, nc)
        for n in nets:
            ns.SetNetclassPatternAssignment(n, name)
    board.SynchronizeNetsAndNetClasses(False)
    return 'set through the API: ' + ni.GetNetItem('/FPGA_1V1').GetNetClassName()


def clear_previous(board):
    """Remove tracks/vias/zones this script added earlier (tagged by zone name / stub geometry)."""
    n = 0
    u = next(fp for fp in board.GetFootprints() if fp.GetReference() == 'U401')
    xs = [p.GetPosition().x for p in u.Pads()]
    ys = [p.GetPosition().y for p in u.Pads()]
    x0, x1, y0, y1 = min(xs) - mm(1), max(xs) + mm(1), min(ys) - mm(1), max(ys) + mm(1)

    def inside(pt):
        return x0 <= pt.x <= x1 and y0 <= pt.y <= y1
    # Collect first, remove afterwards: once board.Remove() has run, further lookups on the
    # board hand back bare SWIG pointers in this KiCad build.
    doomed = [t for t in board.GetTracks() if inside(t.GetStart()) and inside(t.GetEnd())]
    doomed += [z for z in board.Zones() if z.GetZoneName().startswith(TAG)]
    for item in doomed:
        board.Remove(item); n += 1
    return n


def fanout(board):
    u = board.FindFootprintByReference('U401')
    c = u.GetPosition()
    pitch = mm(0.8)
    n_via = 0
    for p in u.Pads():
        net = p.GetNetname()
        if not net or net.startswith('unconnected'):
            continue
        pos = p.GetPosition()
        i = round((pos.x - c.x) / pitch + 9.5)
        j = round((pos.y - c.y) / pitch + 9.5)
        assert 0 <= i <= 19 and 0 <= j <= 19, (p.GetNumber(), i, j)
        if min(i, 19 - i, j, 19 - j) == 0:
            continue
        sx = 1 if i >= 10 else -1
        sy = 1 if j >= 10 else -1
        vpos = V(pos.x + sx * mm(0.4), pos.y + sy * mm(0.4))
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetPosition(vpos)
        via.SetDrill(mm(0.2))
        via.SetWidth(mm(0.45))
        via.SetNetCode(p.GetNetCode())
        board.Add(via)
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pos); t.SetEnd(vpos); t.SetWidth(mm(0.15)); t.SetLayer(pcbnew.F_Cu); t.SetNetCode(p.GetNetCode())
        board.Add(t)
        n_via += 1
    return n_via


def add_zone(board, net, layer, pts, priority, name):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNetCode(board.GetNetcodeFromNetname(net))
    z.SetAssignedPriority(priority)
    z.SetZoneName(f'{TAG}:{name}')
    z.SetMinThickness(mm(0.15))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.2))
    z.SetThermalReliefSpokeWidth(mm(0.3))
    try:
        z.SetLocalClearance(mm(0.15))
    except Exception:
        pass
    for x, y in pts:
        z.AppendCorner(V(mm(x), mm(y)), -1)
    board.Add(z)
    return z


def planes(board):
    bb = board.GetBoardEdgesBoundingBox()
    x0, y0, x1, y1 = bb.GetLeft() / 1e6 - 1, bb.GetTop() / 1e6 - 1, bb.GetRight() / 1e6 + 1, bb.GetBottom() / 1e6 + 1
    whole = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    add_zone(board, '/GND', pcbnew.In1_Cu, whole, 0, 'gnd_in1')
    add_zone(board, '/FPGA_3V3', pcbnew.In3_Cu, whole, 0, 'fpga_3v3_in3')
    # 1.1 V island on In4.Cu: the 20 core balls (ring 7) and the 1.1 V decoupling bands above and
    # below the BGA, plus 1 mm. On its own layer it leaves the 3.3 V plane on In3 whole (the ring-5/6
    # VCCIO vias sit 0.4 mm outside the core balls); the cost is that In4 carries no signals in
    # this region, so BGA escapes use F.Cu, In2.Cu and B.Cu.
    u = board.FindFootprintByReference('U401')
    c = u.GetPosition()
    xs, ys = [], []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == '/FPGA_1V1' and abs(p.GetPosition().x - c.x) < mm(25) and abs(p.GetPosition().y - c.y) < mm(25):
                xs.append(p.GetPosition().x / 1e6); ys.append(p.GetPosition().y / 1e6)
    m = 1.0
    island = [(min(xs) - m, min(ys) - m), (max(xs) + m, min(ys) - m), (max(xs) + m, max(ys) + m), (min(xs) - m, max(ys) + m)]
    add_zone(board, '/FPGA_1V1', pcbnew.In4_Cu, island, 0, 'fpga_1v1_in4')
    return island


def main():
    netclasses_in_project()
    board = pcbnew.LoadBoard(str(PCB))
    removed = clear_previous(board)
    print('removed previous items:', removed)
    if removed:
        # After board.Remove() this KiCad build hands back bare SWIG pointers for every further
        # lookup, even from a fresh LoadBoard in the same process: save the cleared board and stop.
        pcbnew.SaveBoard(str(PCB), board)
        print('cleared the earlier fan-out and planes; run this script once more to rebuild them')
        return 0
    print('netclasses:', apply_netclasses(board))
    print('fan-out vias:', fanout(board))
    print('1V1 island (mm):', [(round(x, 1), round(y, 1)) for x, y in planes(board)])
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(str(PCB), board)
    OUT.mkdir(parents=True, exist_ok=True)
    dsn = OUT / 'sn64.dsn'
    ok = pcbnew.ExportSpecctraDSN(board, str(dsn))
    print('DSN export:', ok, dsn)
    text = dsn.read_text(encoding='utf-8', errors='replace')
    print('DSN classes:', sorted(set(__import__('re').findall(r'\(class (\S+)', text))), 'planes:', text.count('(plane '))
    for n in ('/FPGA_1V1', '/FPGA_3V3', '/GND', '/USB-C programmer/USB_DP', '/N64_AD0'):
        print(f'  {n}: netclass {board.GetNetInfo().GetNetItem(n).GetNetClassName()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
