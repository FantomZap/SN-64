"""Split the SNES socket onto its own board (two-board design, docs/design/mechanical-architecture.md).

Main project (hardware/sn64): the root's J2 becomes the socket-board joint, a 2x40 2.00 mm
right-angle pin header (SN64:SN64_Socket_Joint_2x40). Its pins 1-62 keep the socket symbol's
names and drawing positions, so the existing root wiring is untouched; pins 63-66 (SNES_5V_CART)
and 67-80 (GND) get new wires and labels.

Socket project (hardware/sn64-socket): a new KiCad project with J1 = the real socket on the
console-replacement footprint built from OpenSFC's CartSlot geometry (7.0 mm rows, ears 95 mm
apart) and J2 = the mating 2x40 2.00 mm vertical socket, wired 1:1 with the same net names as
the main root, plus two 100 nF capacitors on the cartridge 5 V.

Idempotent: refuses to run twice unless --force (which regenerates the socket project and
re-applies the root edit only if J2 is still the old socket symbol). Never rerun the root
generators; this script edits the root natively, line by line.
"""
import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent                       # hardware/sn64
SOCKET = PROJECT.parent / 'sn64-socket'     # hardware/sn64-socket
LIB_SYM = PROJECT / 'libraries/SN64.kicad_sym'
LIB_FP = PROJECT / 'libraries/SN64.pretty'
ROOT = PROJECT / 'sn64.kicad_sch'

JOINT = 'SN64_Socket_Joint_2x40'
JOINT_FP_MAIN = 'Connector_PinHeader_2.00mm:PinHeader_2x40_P2.00mm_Horizontal'
JOINT_FP_SOCKET = 'Connector_PinSocket_2.00mm:PinSocket_2x40_P2.00mm_Vertical'
SOCKET_FP = 'SNES_Slot_Console_7mm'
EXTRA = [(n, 'SNES_5V_CART') for n in range(63, 67)] + [(n, 'GND') for n in range(67, 81)]
# OpenSFC CartSlot.kicad_mod, commit 6574450b, SHA-256 1f9b60dd...48b5a0 (docs/dimensions.md)
OPENSFC = {'pad_size': 1.5, 'drill': 1.0, 'row_y': 3.5, 'pitch': 2.5, 'gap': 7.5, 'x0': -42.5,
           'body': (-49.5, -5.65, 49.5, 5.60), 'ear_x': 47.5, 'ear_d': 3.2}


def uid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'sn64-socket-split/' + '/'.join(map(str, parts))))


def pad_x(index):
    """x of contact 1..31 along a row: 2.5 mm pitch with 7.5 mm gaps after contacts 4 and 27."""
    x = OPENSFC['x0']
    for k in range(1, index):
        x += OPENSFC['gap'] if k in (4, 27) else OPENSFC['pitch']
    return round(x, 3)


def write_socket_footprint():
    o = OPENSFC
    lines = [f'(footprint "{SOCKET_FP}" (version 20241229) (generator "sn64_split_socket_board") (generator_version "10.0") (layer "F.Cu")',
             '(descr "SNES/SFC 62-contact cartridge socket, console-replacement family: 2.5 mm pitch, 7.5 mm gaps, 7.0 mm row spacing, ears 95 mm apart. Geometry from OpenSFC CartSlot.kicad_mod (commit 6574450b); body and ear sizes from its silkscreen and edge cuts. Unverified on a sample.")',
             '(tags "SNES SFC cartridge socket 62")', '(attr through_hole)',
             f'(property "Reference" "REF**" (at 0 -8 0) (layer "F.SilkS") (uuid "{uid("fp", "ref")}") (effects (font (size 1 1) (thickness 0.15))))',
             f'(property "Value" "{SOCKET_FP}" (at 0 8 0) (layer "F.Fab") (uuid "{uid("fp", "val")}") (effects (font (size 1 1) (thickness 0.15))))',
             f'(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uid("fp", "ds")}") (effects (font (size 1.27 1.27))))',
             f'(property "Description" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uid("fp", "desc")}") (effects (font (size 1.27 1.27))))']
    x1, y1, x2, y2 = o['body']
    for layer, w, m in (('F.Fab', 0.1, 0.0), ('F.SilkS', 0.12, 0.11), ('F.CrtYd', 0.05, 0.25)):
        lines.append(f'(fp_rect (start {x1 - m} {y1 - m}) (end {x2 + m} {y2 + m}) (stroke (width {w}) (type default)) (fill no) (layer "{layer}") (uuid "{uid("fp", layer)}"))')
    lines.append(f'(fp_line (start {o["x0"] - 1.5} {o["row_y"] + 2.3}) (end {o["x0"] + 1.5} {o["row_y"] + 2.3}) (stroke (width 0.12) (type default)) (layer "F.SilkS") (uuid "{uid("fp", "pin1")}"))')
    for n in range(1, 63):
        col = n if n <= 31 else n - 31
        y = o['row_y'] if n <= 31 else -o['row_y']
        shape = 'rect' if n == 1 else 'circle'
        lines.append(f'(pad "{n}" thru_hole {shape} (at {pad_x(col)} {y}) (size {o["pad_size"]} {o["pad_size"]}) (drill {o["drill"]}) (layers "*.Cu" "*.Mask") (uuid "{uid("fp", "pad", n)}"))')
    for k, sx in enumerate((-1, 1)):
        lines.append(f'(pad "" np_thru_hole circle (at {sx * o["ear_x"]} 0) (size {o["ear_d"]} {o["ear_d"]}) (drill {o["ear_d"]}) (layers "*.Cu" "*.Mask") (uuid "{uid("fp", "ear", k)}"))')
    lines.append(')')
    (LIB_FP / f'{SOCKET_FP}.kicad_mod').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')


def lib_body(text):
    """The library text without its final closing paren (which may share the last symbol's line)."""
    t = text.rstrip()
    assert t.endswith(')')
    return t[:-1]


def socket_symbol_block(text, name):
    body = lib_body(text)
    i = body.index(f'(symbol "{name}"')
    m = re.search(r'\n\(symbol "(?!' + re.escape(name) + ')', body[i + 10:])
    j = i + 10 + m.start() if m else len(body)
    return i, j, body[i:j]


def joint_symbol_from(block, embedded_prefix=''):
    """Build the joint symbol text from the socket symbol block (same 62 pins) plus 18 pins."""
    b = block.replace('SNES_Female_Slot_62', JOINT)
    if embedded_prefix:
        b = b.replace(f'(symbol "{JOINT}"', f'(symbol "{embedded_prefix}{JOINT}"', 1)
    b = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{JOINT}"', b, 1)
    b = re.sub(r'\(property "Footprint" "[^"]*"', f'(property "Footprint" "{JOINT_FP_MAIN}"', b, 1)
    b = re.sub(r'\(property "Description" "[^"]*"',
               '(property "Description" "Socket-board joint: 2x40 2.00 mm header. Pins 1-62 = SNES socket contacts 1-62 (same names), 63-66 cartridge 5 V, 67-80 GND. The socket itself is J1 on hardware/sn64-socket."', b, 1)
    extra = []
    for k, (n, net) in enumerate(EXTRA):
        x = round(-21.59 + k * 2.54, 2)
        extra.append(f'(pin passive line (at {x} -83.82 90) (length 5.08) (name "{net}" (effects (font (size 1.016 1.016)))) (number "{n}" (effects (font (size 1.016 1.016)))))')
    unit = f'(symbol "{JOINT}_1_1"'
    assert unit in b
    k = b.index(unit) + len(unit)
    return b[:k] + '\n' + '\n'.join(extra) + b[k:]


def update_library():
    text = LIB_SYM.read_text(encoding='utf-8')
    if f'(symbol "{JOINT}"' in text:
        return False
    i, j, block = socket_symbol_block(text, 'SNES_Female_Slot_62')
    joint = joint_symbol_from(block)
    body = lib_body(text)
    body = body[:j] + '\n' + joint.rstrip('\n') + body[j:]
    LIB_SYM.write_text(body.rstrip('\n') + '\n)\n', encoding='utf-8', newline='\n')
    return True


def update_root():
    lines = ROOT.read_text(encoding='utf-8').split('\n')
    if any(f'(lib_id "SN64:{JOINT}")' in l for l in lines):
        return None
    # embedded symbol
    i0 = next(i for i, l in enumerate(lines) if l.startswith('(symbol "SN64:SNES_Female_Slot_62"'))
    i1 = next(i for i in range(i0 + 1, len(lines)) if lines[i].startswith('(symbol "SN64:') or lines[i] == ')')
    block = '\n'.join(lines[i0:i1])
    joint = joint_symbol_from(block, embedded_prefix='SN64:')
    joint = joint.replace(f'(symbol "SN64:{JOINT}_', f'(symbol "{JOINT}_')   # unit names stay unprefixed
    lines[i1:i1] = joint.split('\n')
    # J2 instance
    j = next(i for i, l in enumerate(lines) if l.startswith('(symbol (lib_id "SN64:SNES_Female_Slot_62")'))
    m = re.search(r'\(at ([-\d.]+) ([-\d.]+) (\d+)\)', lines[j])
    ox, oy = float(m.group(1)), float(m.group(2))
    assert m.group(3) == '0', 'J2 is expected unrotated'
    lines[j] = lines[j].replace('(lib_id "SN64:SNES_Female_Slot_62")', f'(lib_id "SN64:{JOINT}")', 1)
    k = j + 1
    ref = None
    while not lines[k].startswith('(instances'):
        if lines[k].startswith('(property "Reference"'):
            ref = re.search(r'"Reference" "([^"]*)"', lines[k]).group(1)
        if lines[k].startswith('(property "Value"'):
            lines[k] = re.sub(r'"Value" "[^"]*"', f'"Value" "{JOINT}"', lines[k], count=1)
        if lines[k].startswith('(property "Footprint"'):
            lines[k] = re.sub(r'"Footprint" "[^"]*"', f'"Footprint" "{JOINT_FP_MAIN}"', lines[k], count=1)
        if lines[k].startswith('(property "Description"'):
            lines[k] = re.sub(r'"Description" "[^"]*"', '"Description" "Socket-board joint (2x40 2.00 mm right-angle header); the SNES socket is J1 on hardware/sn64-socket"', lines[k], count=1)
        k += 1
    assert ref == 'J2'
    last_pin = max(i for i in range(j, k) if lines[i].startswith('(pin "'))
    lines[last_pin + 1:last_pin + 1] = [f'(pin "{n}" (uuid "{uid("root", "pin", n)}"))' for n, _ in EXTRA]
    # wires and labels for the new pins (schematic y grows downward: y = oy - sym_y)
    new = []
    for kk, (n, net) in enumerate(EXTRA):
        x = round(ox + (-21.59 + kk * 2.54), 2)
        y0 = round(oy + 83.82, 2)
        y1 = round(y0 + 7.62, 2)
        new.append(f'(wire (pts (xy {x} {y0}) (xy {x} {y1})) (stroke (width 0) (type default)) (uuid "{uid("root", "wire", n)}"))')
        new.append(f'(label "{net}" (at {x} {y1} 270) (effects (font (size 1.016 1.016)) (justify right bottom)) (uuid "{uid("root", "label", n)}"))')
    end = max(i for i, l in enumerate(lines) if l == ')')
    lines[end:end] = new
    ROOT.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    return (ox, oy)


def root_net_names():
    """Net name per J2 pin 1..62 from the root wiring (wire from the pin end to a label)."""
    text = ROOT.read_text(encoding='utf-8')
    lib = LIB_SYM.read_text(encoding='utf-8')
    _, _, block = socket_symbol_block(lib, 'SNES_Female_Slot_62')
    pins = re.findall(r'\(pin \w+ \w+ \(at ([-\d.]+) ([-\d.]+) (\d+)\) \(length [\d.]+\) \(name "([^"]*)"[^\n]*?\(number "(\d+)"', block)
    m = re.search(r'\(symbol \(lib_id "SN64:(?:SNES_Female_Slot_62|' + JOINT + r')"\) \(at ([-\d.]+) ([-\d.]+) 0\)', text)
    ox, oy = float(m.group(1)), float(m.group(2))
    wires = re.findall(r'\(wire \(pts \(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)\)', text)
    labels = {(float(a), float(b)): n for n, a, b in re.findall(r'\(label "([^"]*)" \(at ([-\d.]+) ([-\d.]+) \d+\)', text)}
    names = {}
    for px, py, rot, pname, num in pins:
        ex, ey = round(ox + float(px), 2), round(oy - float(py), 2)
        for a, b, c, d in wires:
            a, b, c, d = map(float, (a, b, c, d))
            other = None
            if (round(a, 2), round(b, 2)) == (ex, ey):
                other = (c, d)
            elif (round(c, 2), round(d, 2)) == (ex, ey):
                other = (a, b)
            if other and other in labels:
                names[int(num)] = (pname, labels[other])
                break
        assert int(num) in names, f'no label found for J2 pin {num} ({pname})'
    return names


def device_c_symbol():
    """KiCad's own Device:C symbol text (multi-line), embedded as "Device:C"."""
    lib = Path(r'C:/Program Files/KiCad/10.0/share/kicad/symbols/Device.kicad_sym').read_text(encoding='utf-8')
    i = lib.index('(symbol "C"\n')
    depth = 0
    j = i
    while True:
        c = lib[j]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                j += 1
                break
        j += 1
    return lib[i:j].replace('(symbol "C"', '(symbol "Device:C"', 1)


def write_socket_project(names):
    SOCKET.mkdir(exist_ok=True)
    (SOCKET / 'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "SN64") (type "KiCad") (uri "${KIPRJMOD}/../sn64/libraries/SN64.kicad_sym") (options "") (descr "Shared with the main board")))\n', encoding='utf-8', newline='\n')
    (SOCKET / 'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "SN64") (type "KiCad") (uri "${KIPRJMOD}/../sn64/libraries/SN64.pretty") (options "") (descr "Shared with the main board")))\n', encoding='utf-8', newline='\n')
    pro = {'board': {'design_settings': {'defaults': {}, 'rules': {}}, 'layer_presets': [], 'viewports': []},
           'boards': [], 'cvpcb': {'equivalence_files': []}, 'libraries': {'pinned_footprint_libs': [], 'pinned_symbol_libs': []},
           'meta': {'filename': 'sn64-socket.kicad_pro', 'version': 3}, 'net_settings': {'classes': [{'name': 'Default', 'clearance': 0.2, 'track_width': 0.25, 'via_diameter': 0.6, 'via_drill': 0.3}], 'meta': {'version': 4}},
           'pcbnew': {'page_layout_descr_file': ''}, 'schematic': {'legacy_lib_dir': '', 'legacy_lib_list': []}, 'sheets': [], 'text_variables': {}}
    (SOCKET / 'sn64-socket.kicad_pro').write_text(json.dumps(pro, indent=2) + '\n', encoding='utf-8', newline='\n')
    lib = LIB_SYM.read_text(encoding='utf-8')
    _, _, sock_block = socket_symbol_block(lib, 'SNES_Female_Slot_62')
    _, _, joint_block = socket_symbol_block(lib, JOINT)
    pins = re.findall(r'\(pin \w+ \w+ \(at ([-\d.]+) ([-\d.]+) (\d+)\) \(length [\d.]+\) \(name "([^"]*)"[^\n]*?\(number "(\d+)"', sock_block)
    sheet_uuid = uid('socket', 'sheet')
    L = [f'(kicad_sch (version 20250114) (generator "sn64_split_socket_board") (generator_version "10.0") (uuid "{sheet_uuid}") (paper "A3")',
         '(title_block (title "SN 64 socket board") (rev "0.1-socket") (comment 1 "SNES/SFC socket on its own horizontal board; joined to the main board by a 2x40 2.00 mm header (J2 on both boards). Net names match the main root sheet.") (comment 2 "Socket footprint: console-replacement family, OpenSFC geometry (7.0 mm rows, ears 95 mm). Unverified on a sample; see docs/dimensions.md."))',
         '(lib_symbols',
         sock_block.replace('(symbol "SNES_Female_Slot_62"', '(symbol "SN64:SNES_Female_Slot_62"', 1).rstrip('\n'),
         joint_block.replace(f'(symbol "{JOINT}"', f'(symbol "SN64:{JOINT}"', 1).rstrip('\n'),
         device_c_symbol(),
         ')']
    def place(ref, lib_id, value, fp, x, y, desc, pin_numbers):
        u = uid('socket', 'sym', ref)
        s = [f'(symbol (lib_id "{lib_id}") (at {x} {y} 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid "{u}")',
             f'(property "Reference" "{ref}" (at {x} {y - 86} 0) (effects (font (size 1.27 1.27))))',
             f'(property "Value" "{value}" (at {x} {y - 83.5} 0) (effects (font (size 1.27 1.27))))',
             f'(property "Footprint" "{fp}" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
             f'(property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
             f'(property "Description" "{desc}" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))']
        s += [f'(pin "{n}" (uuid "{uid("socket", "pin", ref, n)}"))' for n in pin_numbers]
        s.append(f'(instances (project "sn64-socket" (path "/{sheet_uuid}" (reference "{ref}") (unit 1)))))')
        return s
    J1 = (111.76, 127.0)
    J2 = (261.62, 127.0)
    L += place('J1', 'SN64:SNES_Female_Slot_62', 'SNES socket (console-replacement, 7.0 mm rows)', f'SN64:{SOCKET_FP}', *J1,
               'The physical SNES/SFC cartridge socket. Contacts 1-62 per the interface CSV; footprint geometry from OpenSFC.', range(1, 63))
    L += place('J2', f'SN64:{JOINT}', JOINT, JOINT_FP_SOCKET, *J2,
               'Joint to the main board: 2x40 2.00 mm vertical socket mating the main board J2 header. Pins 1-62 = socket contacts, 63-66 cartridge 5 V, 67-80 GND.', range(1, 81))
    # wires + labels at every pin of both symbols
    for px, py, rot, pname, num in pins:
        net = names[int(num)][1]
        for (ox, oy) in (J1, J2):
            ex, ey = round(ox + float(px), 2), round(oy - float(py), 2)
            left = float(px) < 0
            fx = round(ex - 12.7, 2) if left else round(ex + 12.7, 2)
            L.append(f'(wire (pts (xy {ex} {ey}) (xy {fx} {ey})) (stroke (width 0) (type default)) (uuid "{uid("socket", "wire", ox, num)}"))')
            L.append(f'(label "{net}" (at {fx} {ey} {0 if left else 180}) (effects (font (size 1.016 1.016)) (justify right bottom)) (uuid "{uid("socket", "label", ox, num)}"))')
    for kk, (n, net) in enumerate(EXTRA):
        x = round(J2[0] + (-21.59 + kk * 2.54), 2)
        y0 = round(J2[1] + 83.82, 2)
        y1 = round(y0 + 7.62, 2)
        L.append(f'(wire (pts (xy {x} {y0}) (xy {x} {y1})) (stroke (width 0) (type default)) (uuid "{uid("socket", "wire", "x", n)}"))')
        L.append(f'(label "{net}" (at {x} {y1} 270) (effects (font (size 1.016 1.016)) (justify right bottom)) (uuid "{uid("socket", "label", "x", n)}"))')
    # two 100 nF decoupling capacitors on the cartridge 5 V (near the socket)
    for k, cx in enumerate((160.02, 175.26)):
        ref = f'C{k + 1}'
        cy = 229.87
        u = uid('socket', 'sym', ref)
        L += [f'(symbol (lib_id "Device:C") (at {cx} {cy} 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid "{u}")',
              f'(property "Reference" "{ref}" (at {cx + 2.54} {cy - 1.27} 0) (effects (font (size 1.27 1.27)) (justify left)))',
              f'(property "Value" "100nF 16V X7R" (at {cx + 2.54} {cy + 1.27} 0) (effects (font (size 1.27 1.27)) (justify left)))',
              f'(property "Footprint" "Capacitor_SMD:C_0603_1608Metric" (at {cx} {cy} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
              f'(property "Datasheet" "~" (at {cx} {cy} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
              f'(pin "1" (uuid "{uid("socket", "pin", ref, 1)}"))', f'(pin "2" (uuid "{uid("socket", "pin", ref, 2)}"))',
              f'(instances (project "sn64-socket" (path "/{sheet_uuid}" (reference "{ref}") (unit 1)))))']
        for pin_y, net, rot in ((cy - 3.81, 'SNES_5V_CART', 90), (cy + 3.81, 'GND', 270)):
            fy = round(pin_y - 5.08, 2) if net == 'SNES_5V_CART' else round(pin_y + 5.08, 2)
            L.append(f'(wire (pts (xy {cx} {pin_y}) (xy {cx} {fy})) (stroke (width 0) (type default)) (uuid "{uid("socket", "wire", ref, net)}"))')
            L.append(f'(label "{net}" (at {cx} {fy} {rot}) (effects (font (size 1.016 1.016)) (justify right bottom)) (uuid "{uid("socket", "label", ref, net)}"))')
    L.append(f'(sheet_instances (path "/" (page "1")))')
    L.append(')')
    (SOCKET / 'sn64-socket.kicad_sch').write_text('\n'.join(L) + '\n', encoding='utf-8', newline='\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--force', action='store_true', help='regenerate the socket project and footprint (the root edit is applied only once)')
    a = ap.parse_args()
    if (SOCKET / 'sn64-socket.kicad_sch').exists() and not a.force:
        raise SystemExit('socket project exists; use --force to regenerate it')
    write_socket_footprint()
    lib_changed = update_library()
    origin = update_root()
    names = root_net_names()
    write_socket_project(names)
    print(f'footprint {SOCKET_FP}: written; library symbol {JOINT}: {"added" if lib_changed else "present"}; root J2: {"converted" if origin else "already the joint"}')
    print('net names per pin:', {k: v[1] for k, v in sorted(names.items())})


if __name__ == '__main__':
    main()
