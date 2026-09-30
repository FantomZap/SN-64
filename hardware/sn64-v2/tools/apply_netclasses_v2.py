"""Assign the v2 netclasses on the board itself (pcbnew.BOARD() boards do not read the project patterns)."""
import sys
from pathlib import Path
import pcbnew

PCB = Path(__file__).resolve().parents[1] / 'sn64-v2.kicad_pcb'
mm = pcbnew.FromMM
POWER = ['GND', 'FPGA_3V3', 'FPGA_1V1', 'FPGA_2V5', '5V_SYS', 'SYS_VIN', 'USB_VBUS', 'HOST_3V3', 'SNES_5V_CART',
         'SW_3V3', 'SW_1V1', 'L1_5V', 'L2_5V']
USB = ['USB_DP', 'USB_DN', 'USB_DP_F', 'USB_DN_F']


def main():
    board = pcbnew.LoadBoard(str(sys.argv[1] if len(sys.argv) > 1 else PCB))
    ns = board.GetDesignSettings().m_NetSettings
    for name, width, via, drill, nets in (('power', 0.4, 0.6, 0.3, POWER), ('usb', 0.2, 0.45, 0.2, USB)):
        nc = pcbnew.NETCLASS(name)
        nc.SetTrackWidth(mm(width)); nc.SetViaDiameter(mm(via)); nc.SetViaDrill(mm(drill)); nc.SetClearance(mm(0.1))
        ns.SetNetclass(name, nc)
        for n in nets:
            ns.SetNetclassPatternAssignment(n, name)
    board.SynchronizeNetsAndNetClasses(False)
    ni = board.GetNetInfo()
    print({n: ni.GetNetItem(n).GetNetClassName() for n in ('GND', 'FPGA_1V1', 'USB_DP', 'N64_AD0')})
    pcbnew.SaveBoard(board.GetFileName(), board)


if __name__ == '__main__':
    main()
