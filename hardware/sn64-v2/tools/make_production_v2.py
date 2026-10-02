"""Make the manufacturing files of the v2 board and the sheet of values for a quotation (KiCad's python).

  python make_production_v2.py [--board sn64-v2.kicad_pcb] [--out production] [--kicad-cli PATH]

Nothing is sent anywhere. The tool writes into hardware/sn64-v2/production/:

  fabrication/   Gerber files of the 6 copper layers, paste, silkscreen, mask and outline; drill files
                 (plated and unplated apart) with a drill map; an IPC-D-356 netlist for the electrical
                 test; fabrication-notes.txt
  assembly/      parts list (one line per maker's part number), placement file, assembly drawings of
                 both faces, the schematic as a PDF
  quote-sheet.md what to enter in PCBWay's forms, with every number taken from the board
  README.md      what the folder is and what state the board is in
  *.zip          the two folders packed for uploading (not committed)

It refuses to run unless KiCad's rule check of the board, with the comparison against the schematic,
shows no error, no open connection and no difference, and only the known notes at the edge fingers.
"""
import argparse
import csv
import datetime
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pcbnew

V2 = Path(__file__).resolve().parents[1]
REPO = V2.parents[1]
MM = pcbnew.ToMM
LAYERS = 'F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts'
LAYER_USE = (('F.Cu', 'top copper: the back face of the cartridge'), ('In1.Cu', 'inner 1: ground plane'),
             ('In2.Cu', 'inner 2: signals'), ('In3.Cu', 'inner 3: 3.3 V plane'),
             ('In4.Cu', 'inner 4: signals and the 1.1 V area'), ('B.Cu', 'bottom copper: the label side of the cartridge'))
RING_ASKED = 0.15            # PCBWay's stated smallest annular ring (capabilities page read 2026-10-02)
NPTH_SLOT_ASKED = 0.8        # PCBWay's stated smallest unplated slot width
NAME = 'sn64-v2'


def run(cli, *args, cwd=None):
    r = subprocess.run([str(cli), *[str(a) for a in args]], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('kicad-cli %s failed:\n%s%s' % (' '.join(str(a) for a in args[:3]), r.stdout, r.stderr))
    return r.stdout


def natural(ref):
    m = re.match(r'([A-Za-z]+)(\d+)', ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_board(cli, board):
    with tempfile.TemporaryDirectory() as tmp:
        rep = Path(tmp) / 'drc.json'
        run(cli, 'pcb', 'drc', '--format', 'json', '--severity-all', '--schematic-parity', '--output', rep, board.name, cwd=board.parent)
        d = json.loads(rep.read_text(encoding='utf-8'))
    kinds = Counter((v['severity'], v['type']) for v in d.get('violations', []))
    errors = sum(n for (sev, _), n in kinds.items() if sev == 'error')
    other = {k: n for k, n in kinds.items() if k != ('warning', 'solder_mask_bridge')}
    not_edge = [v for v in d.get('violations', []) if v['type'] == 'solder_mask_bridge' and not any('J1' in i['description'] for i in v['items'])]
    problems = []
    if errors:
        problems.append('%d errors' % errors)
    if d.get('unconnected_items'):
        problems.append('%d open connections' % len(d['unconnected_items']))
    if d.get('schematic_parity'):
        problems.append('%d differences from the schematic' % len(d['schematic_parity']))
    if other:
        problems.append('warnings other than the edge fingers: %s' % other)
    if not_edge:
        problems.append('%d solder mask notes away from the edge fingers' % len(not_edge))
    if problems:
        sys.exit('the board is not in a state to make files from: ' + '; '.join(problems))
    return kinds[('warning', 'solder_mask_bridge')]


def read_parts(netlist):
    parts = {}
    for c in ET.parse(netlist).getroot().find('components'):
        f = {x.get('name'): (x.text or '') for x in c.findall('fields/field')}
        lib = c.find('libsource')
        parts[c.get('ref')] = {'value': c.findtext('value') or '', 'footprint': (c.findtext('footprint') or '').split(':')[-1],
                               'mpn': f.get('MPN', ''), 'maker': f.get('Manufacturer', ''),
                               'source': f.get('LCSC') or f.get('Source', ''), 'note': f.get('Note', ''),
                               'text': f.get('Description') or (lib.get('description') if lib is not None else '') or ''}
    return parts


def package(fp):
    for pat, name in ((r'_0603_', '0603'), (r'_0805_', '0805'), (r'caBGA-381', 'caBGA-381, 0.8 mm pitch'), (r'TSSOP-48', 'TSSOP-48, 0.5 mm pitch'),
                      (r'TSSOP-14', 'TSSOP-14'), (r'SSOP-20', 'SSOP-20, 0.635 mm pitch'), (r'SOIC-8_5.3', 'SOIC-8, 5.3 mm body'),
                      (r'SOT-23-5', 'SOT-23-5'), (r'SOT-23-6', 'SOT-23-6'), (r'WQFN-16', 'WQFN-16, 3 x 3 mm, 0.5 mm pitch'),
                      (r'VQFN-HR-12', 'VQFN-HR-12, 2 x 2.5 mm'), (r'VQFN-HR-15', 'VQFN-HR-15, 2.5 x 3 mm'), (r'PNR4020', '4 x 4 x 2 mm inductor'),
                      (r'FNR4030', '4 x 4 x 3 mm inductor'), (r'ASE-4Pin_3.2x2.5', '3.2 x 2.5 mm, 4 pads'),
                      (r'USB_C_JAE', 'USB-C receptacle, 16 pads and 4 legs in plated slots')):
        if re.search(pat, fp):
            return name
    return fp


def substitute(ref, part):
    kind = natural(ref)[0]
    if kind == 'C':
        return 'yes: same value, size and dielectric, same voltage or higher'
    if kind == 'R':
        return 'yes: same value, size and tolerance'
    if kind == 'D':
        return 'yes: any yellow-green 0603 lamp with about 2 V across it'
    if kind == 'RT':
        return 'yes: 10 k, 1 %, B(25/50) 3950 K, 0603'
    return 'no'


def board_facts(board):
    b = pcbnew.LoadBoard(str(board))
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    vias = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    by_size = Counter((MM(v.GetWidth(pcbnew.F_Cu)), MM(v.GetDrillValue())) for v in vias)
    thin = sum(n for (pad, drill), n in by_size.items() if (pad - drill) / 2 < RING_ASKED - 1e-6)
    in_pad = defaultdict(set)
    for f in fps.values():
        for p in f.Pads():
            if p.GetDrillSize().x > 0 or not (p.IsOnLayer(pcbnew.F_Paste) or p.IsOnLayer(pcbnew.B_Paste)):
                continue
            box = p.GetBoundingBox()
            box.Inflate(pcbnew.FromMM(0.3))
            for v in vias:
                if box.Contains(v.GetPosition()) and p.HitTest(v.GetPosition(), v.GetDrillValue() // 2):
                    in_pad[f.GetReference()].add((v.GetPosition().x, v.GetPosition().y))
    tracks = [t for t in b.GetTracks() if t.Type() != pcbnew.PCB_VIA_T]
    return {'fps': fps, 'via_sizes': by_size, 'thin_ring': thin, 'via_in_pad': {r: len(s) for r, s in in_pad.items()},
            'tracks': len(tracks), 'vias': len(vias), 'length': round(sum(t.GetLength() for t in tracks) / 1e6),
            'min_track': min(MM(t.GetWidth()) for t in tracks), 'layers': b.GetCopperLayerCount(),
            'thickness': MM(b.GetDesignSettings().GetBoardThickness())}


def write_bom(path, parts, fps):
    groups = defaultdict(list)
    for ref, p in parts.items():
        if p['mpn'] and not fps[ref].IsExcludedFromBOM():
            groups[p['mpn']].append(ref)
    rows = []
    for mpn, refs in groups.items():
        refs.sort(key=natural)
        p = parts[refs[0]]
        sides = sorted({'top' if fps[r].GetLayer() == pcbnew.F_Cu else 'bottom' for r in refs})
        fitted = [r for r in refs if not fps[r].IsExcludedFromPosFiles()]
        text = p['text'] if natural(refs[0])[0] in ('C', 'R', 'D', 'RT') else (p['value'] + ('. ' + p['text'] if p['text'] and p['text'] != p['value'] else ''))
        rows.append({'refs': refs, 'qty': len(fitted), 'maker': p['maker'], 'mpn': mpn, 'text': text, 'package': package(p['footprint']),
                     'side': ' and '.join(sides), 'source': p['source'], 'sub': substitute(refs[0], p)})
    rows.sort(key=lambda r: natural(r['refs'][0]))
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Item', 'Designator', 'Qty', 'Manufacturer', 'Mfg Part #', 'Description / Value', 'Package / Footprint', 'Type', 'Side',
                    'LCSC or other source #', 'Substitute allowed', 'Notes'])
        for i, r in enumerate(rows, start=1):
            note = 'USB-C: surface-mount pads and four legs in plated slots' if 'USB-C' in r['package'] else ''
            w.writerow([i, ', '.join(r['refs']), r['qty'], r['maker'], r['mpn'], r['text'], r['package'], 'SMD', r['side'], r['source'], r['sub'], note])
        w.writerow([])
        w.writerow(['', 'Not fitted by the assembler'])
        for ref in sorted((r for r in fps if r in parts and not parts[r]['mpn'] or r not in parts), key=natural):
            what = {'J1': 'N64 edge fingers: copper of the board, no part', 'J2': 'SNES cartridge socket, 62 contacts: supplied and soldered by hand after delivery'}.get(
                ref, 'test pad: bare copper, no part' if ref.startswith('TP') else 'hole in the board, no part')
            w.writerow(['', ref, 0, '', '', what])
    return rows


def size(text):
    return float(text.split()[0])


def write_notes(path, facts, stats, date):
    holes = stats['drill_holes']
    lines = ['SN64 v1 main board (files named sn64-v2): fabrication notes', 'Made %s for a quotation. Board file sn64-v2.kicad_pcb.' % date, '',
             '1. Layers: %d. Order from the top:' % facts['layers']]
    lines += ['      %-7s %s' % (n, u) for n, u in LAYER_USE]
    lines += ['2. Size %g x %g mm, routed outline (Edge.Cuts). Finished thickness %.1f mm.' % (size(stats['board']['width']), size(stats['board']['height']), facts['thickness']),
              '3. Material FR-4, Tg 150 C or higher. Copper 1 oz finished on the outer layers, 1 oz on the inner layers.',
              '   Stack-up: the maker\'s standard for 6 layers at this thickness. No impedance control.',
              '4. Smallest track %.2f mm, smallest clearance %g mm.' % (facts['min_track'], size(stats['board']['min_track_clearance'])),
              '5. Holes:']
    for h in holes:
        lines.append('      %4d x %s %g%s mm, %s (%s)' % (h['count'], h['shape'].lower(), size(h['x_size']),
                                                          '' if h['shape'] == 'Round' else ' x %g' % size(h['y_size']),
                                                          'plated' if h['plated'] else 'not plated', h['source'].lower()))
    lines += ['   Vias are tented on both faces.',
              '6. Via in pad: %d vias of 0.2 mm lie in surface-mount pads, %d of them in pads of the BGA U1.' % (
                  sum(facts['via_in_pad'].values()), facts['via_in_pad'].get('U1', 0)),
              '   Wanted: these filled with resin and plated over. Please quote this and say if another way is advised.',
              '7. Annular ring: %d vias have a %.2f mm pad on a %.2f mm hole, a ring of %.3f mm. Please say whether this is' % (
                  facts['thin_ring'], 0.45, 0.2, 0.125),
              '   accepted as drawn. If not, these may be drilled 0.15 mm.',
              '8. The unplated oval hole of 0.85 x 0.6 mm and the round one of 0.6 mm locate the USB-C receptacle',
              '   (JAE DX07S016JA3R1500, drawing SJ122205). The oval may be made as two overlapping 0.6 mm drill hits.',
              '9. Edge connector: 50 gold fingers, 25 on each face, at the bottom edge. Surface finish immersion gold (ENIG)',
              '   on the whole board. Bevel 45 degrees on the finger edge. The solder mask is open across the whole',
              '   row of fingers on purpose. No copper lies between the fingers or on the inner layers under them.',
              '10. Solder mask on both faces, silkscreen on both faces, white. Solder mask red. Smallest silkscreen text 0.8 mm high, 0.15 mm line.',
              '11. Electrical test of every board against sn64-v2.d356 (IPC-D-356).',
              '12. For assembly: tooling rails and fiducials may be added by the maker. The board itself has none.', '']
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')


def pack(zip_path, folder):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.iterdir()):
            info = zipfile.ZipInfo(f.name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, f.read_bytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--board', type=Path, default=V2 / 'sn64-v2.kicad_pcb')
    ap.add_argument('--netlist', type=Path, default=V2 / 'validation' / 'sn64-v2.xml')
    ap.add_argument('--out', type=Path, default=V2 / 'production')
    ap.add_argument('--kicad-cli', type=Path, default=Path(sys.executable).with_name('kicad-cli.exe'))
    a = ap.parse_args()
    cli, board = a.kicad_cli, a.board.resolve()
    date = datetime.date.today().isoformat()
    mask_notes = check_board(cli, board)
    facts = board_facts(board)
    parts = read_parts(a.netlist)
    fps = facts['fps']

    fab, asm = a.out / 'fabrication', a.out / 'assembly'
    for d in (fab, asm):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    run(cli, 'pcb', 'export', 'gerbers', '--output', str(fab) + '/', '--layers', LAYERS, '--no-x2', '--subtract-soldermask', board)
    run(cli, 'pcb', 'export', 'drill', '--output', str(fab) + '/', '--format', 'excellon', '--excellon-units', 'mm',
        '--excellon-zeros-format', 'decimal', '--excellon-separate-th', '--generate-map', '--map-format', 'pdf', board)
    run(cli, 'pcb', 'export', 'ipcd356', '--output', fab / (NAME + '.d356'), board)
    with tempfile.TemporaryDirectory() as tmp:
        sj = Path(tmp) / 'stats.json'
        run(cli, 'pcb', 'export', 'stats', '--format', 'json', '--units', 'mm', '--output', sj, board)
        stats = json.loads(sj.read_text(encoding='utf-8'))
    write_notes(fab / 'fabrication-notes.txt', facts, stats, date)

    pos = asm / (NAME + '-positions.csv')
    run(cli, 'pcb', 'export', 'pos', '--output', pos, '--format', 'csv', '--units', 'mm', '--side', 'both', '--exclude-dnp', board)
    placed = [r for r in csv.DictReader(open(pos, encoding='utf-8'))]
    placed_refs = {r['Ref'] for r in placed}
    want = {r for r, p in parts.items() if p['mpn'] and not fps[r].IsExcludedFromPosFiles()}
    if placed_refs != want:
        sys.exit('placement file and parts list disagree: %s' % sorted(placed_refs ^ want))
    rows = write_bom(asm / (NAME + '-bom.csv'), parts, fps)
    if sum(r['qty'] for r in rows) != len(placed):
        sys.exit('parts list counts %d parts, the placement file %d' % (sum(r['qty'] for r in rows), len(placed)))
    run(cli, 'pcb', 'export', 'pdf', '--output', asm / (NAME + '-assembly-top.pdf'), '--layers', 'F.Fab,Edge.Cuts', '--mode-single',
        '--black-and-white', '--no-property-popups', '--scale', '0', '--exclude-value', board)
    run(cli, 'pcb', 'export', 'pdf', '--output', asm / (NAME + '-assembly-bottom.pdf'), '--layers', 'B.Fab,Edge.Cuts', '--mode-single',
        '--black-and-white', '--mirror', '--no-property-popups', '--scale', '0', '--exclude-value', board)
    run(cli, 'sch', 'export', 'pdf', '--output', asm / (NAME + '-schematic.pdf'), V2 / (NAME + '.kicad_sch'))
    for stray in a.out.glob('*.zip'):
        stray.unlink()
    pack(a.out / (NAME + '-fabrication.zip'), fab)
    pack(a.out / (NAME + '-assembly.zip'), asm)

    # numbers for the two documents
    side = Counter(r['Side'] for r in placed)
    kinds = Counter()
    for r in placed:
        fp = parts[r['Ref']]['footprint']
        kinds['bga'] += 'BGA' in fp
        kinds['leadless'] += any(k in fp for k in ('QFN', 'DFN'))
        kinds['fine'] += any(k in fp for k in ('TSSOP-48', 'USB_C', 'WQFN'))
    vip = facts['via_in_pad']
    via_text = ', '.join('%d x %.2f mm pad on %.2f mm hole' % (n, pad, drill) for (pad, drill), n in sorted(facts['via_sizes'].items()))
    fit_lines = len([r for r in rows if r['qty']])
    npth_slots = [h for h in stats['drill_holes'] if h['shape'] == 'Slot' and not h['plated']]
    ctx = {'date': date, 'w': '%g' % size(stats['board']['width']), 'h': '%g' % size(stats['board']['height']),
           'layers': facts['layers'], 't': '%.1f' % facts['thickness'], 'min_track': '%.2f' % facts['min_track'],
           'min_clear': '%g' % size(stats['board']['min_track_clearance']),
           'vias': facts['vias'], 'via_text': via_text, 'thin': facts['thin_ring'], 'vip': sum(vip.values()), 'vip_bga': vip.get('U1', 0),
           'vip_parts': ', '.join('%s (%d)' % (r, n) for r, n in sorted(vip.items(), key=lambda kv: natural(kv[0]))),
           'lines': fit_lines, 'placed': len(placed), 'top': side.get('top', 0), 'bottom': side.get('bottom', 0),
           'bga': kinds['bga'], 'leadless': kinds['leadless'], 'fine': kinds['fine'], 'mask_notes': mask_notes,
           'smd_pads': stats['pads']['smd'], 'board_sha': sha256(board), 'net_sha': sha256(a.netlist),
           'npth_slot': '%g x %g' % (size(npth_slots[0]['x_size']), size(npth_slots[0]['y_size'])) if npth_slots else 'none',
           'tracks': facts['tracks'], 'length': facts['length'],
           'files': '\n'.join('| `%s` | %s |' % (f.name, describe(f.name)) for f in sorted(fab.iterdir())),
           'asm_files': '\n'.join('| `%s` | %s |' % (f.name, describe(f.name)) for f in sorted(asm.iterdir()))}
    (a.out / 'quote-sheet.md').write_text(QUOTE.format(**ctx), encoding='utf-8', newline='\n')
    (a.out / 'README.md').write_text(README.format(**ctx), encoding='utf-8', newline='\n')
    (a.out / '.gitignore').write_text('*.zip\n', encoding='utf-8', newline='\n')
    print('production files in %s: %d fabrication files, %d assembly files; %d lines in the parts list, %d parts placed '
          '(%d top, %d bottom); %d vias in pads (%d in BGA pads); %d vias with a ring under %.2f mm'
          % (a.out.name, len(list(fab.iterdir())), len(list(asm.iterdir())), fit_lines, len(placed), side.get('top', 0), side.get('bottom', 0),
             sum(vip.values()), vip.get('U1', 0), facts['thin_ring'], RING_ASKED))
    sys.stdout.flush()


def describe(name):
    low = name.lower()
    table = (('.gtl', 'top copper (F.Cu), the back face of the cartridge'), ('.g1', 'inner layer 1, ground plane'), ('.g2', 'inner layer 2, signals'),
             ('.g3', 'inner layer 3, 3.3 V plane'), ('.g4', 'inner layer 4, signals and the 1.1 V area'),
             ('.gbl', 'bottom copper (B.Cu), the label side of the cartridge'), ('.gtp', 'solder paste, top'), ('.gbp', 'solder paste, bottom'),
             ('.gto', 'silkscreen, top'), ('.gbo', 'silkscreen, bottom'), ('.gts', 'solder mask, top'), ('.gbs', 'solder mask, bottom'),
             ('.gm1', 'board outline'), ('.gbrjob', 'job file that lists the Gerber files'), ('-npth.drl', 'holes that are not plated'),
             ('-pth.drl', 'plated holes and vias'), ('npth-drl_map.pdf', 'drawing of the unplated holes'), ('pth-drl_map.pdf', 'drawing of the plated holes'),
             ('.d356', 'netlist for the electrical test of the bare board (IPC-D-356)'), ('fabrication-notes.txt', 'the notes for the board maker'),
             ('-bom.csv', 'parts list: one line for each maker\'s part number'), ('-positions.csv', 'where each part goes: centre, angle and face'),
             ('-assembly-top.pdf', 'drawing of the parts on the top face'), ('-assembly-bottom.pdf', 'drawing of the parts on the bottom face, mirrored as seen from that side'),
             ('-schematic.pdf', 'the schematic'))
    for end, text in table:
        if low.endswith(end):
            return text
    return ''


QUOTE = """# SN64 v1 board (files named sn64-v2): what to enter for a PCBWay quote

Written by `hardware/sn64-v2/tools/make_production_v2.py` on {date} from the board file. Every number below is read from the board.
**Nothing has been sent to PCBWay.** The files are for a price. Before an order the list at the end still applies.

## 1. The bare board (PCBWay's "PCB Instant Quote")

| Field | Enter | Where the value comes from |
|---|---|---|
| Board type | Single pieces | |
| Size | {w} x {h} mm | board outline |
| Quantity | 5 | their smallest lot |
| Layers | {layers} | |
| Material | FR-4, TG 150 or higher | lead-free soldering on both faces |
| Thickness | {t} mm | the console's slot. SummerCart64 uses the same |
| Min track / spacing | 4/4 mil | the board's smallest track is {min_track} mm and its smallest gap {min_clear} mm |
| Min hole size | 0.2 mm | {vias} vias: {via_text} |
| Solder mask | red | chosen by the owner, 2026-10-02 |
| Silkscreen | white | |
| Edge connector | Yes | the 50 gold fingers |
| Bevelling | 45 degrees | SummerCart64's build guide |
| Surface finish | Immersion gold (ENIG) | the fingers and the 381-ball chip. SummerCart64 orders ENIG. Hard gold on the fingers lasts longer and costs much more |
| Via process | Tenting vias | set on the board |
| Finished copper | 1 oz outer, 1 oz inner | the form offers nothing thinner for the inner layers |
| Stack-up | their standard one, no impedance control | |

## 2. Four things to put in the remarks box

PCBWay's form has no field for these. Their engineer answers them with the quote.

1. **Via in pad.** {vip} of the small holes sit in solder pads, {vip_bga} of them under the 381-ball chip. Left open they draw the solder away from the joint. Ask for them to be **filled with resin and plated over**, and for the price with and without. If the difference is large, the {vip} holes can be moved instead. That is a routing job of about a day, not a new design.
2. **Annular ring.** {thin} vias have a 0.45 mm pad on a 0.2 mm hole, which leaves a copper ring of 0.125 mm. PCBWay's page states 0.15 mm. Ask whether 0.125 mm is accepted as drawn. If not, those holes may be drilled 0.15 mm, which changes no copper.
3. **One small oval hole.** The USB-C socket's maker asks for an unplated oval hole of {npth_slot} mm. PCBWay's page states 0.8 mm as the narrowest unplated slot. It may be made as two overlapping 0.6 mm drill hits.
4. **Rails and marks for assembly.** The board has no fiducial marks of its own. Ask them to add tooling rails with fiducials.

The same four points are in `fabrication/fabrication-notes.txt` inside the zip, so the engineer sees them with the files.

## 3. Assembly (PCBWay's "Assembly" quote)

| Field | Enter |
|---|---|
| Service | Turnkey: they buy the parts |
| Assembly sides | Both |
| Unique parts | {lines} |
| SMD parts | {placed} ({top} on the top face, {bottom} on the bottom face) |
| BGA / QFP parts | {bga} BGA with 381 balls at 0.8 mm. Also {leadless} leadless chips and {fine} parts with 0.5 mm lead pitch |
| Through-hole parts | 0. The USB-C socket is surface-mount with four legs in plated slots |
| Files | `assembly/{name}-bom.csv` and `assembly/{name}-positions.csv` |

Not fitted by PCBWay: the **SNES cartridge socket** (J2). It is soldered by hand after delivery. Say so in the remarks, so that they do not ask for the part.

## 4. What makes this board cost more than a simple one

Six layers. Gold fingers with a bevel. ENIG. Parts on both faces. A 381-ball chip, which is X-rayed after soldering. Filled vias, if point 1 stays. The FPGA is the dearest part.

## 5. Before an order, not before a quote

- The SNES socket's footprint waits for a measured sample of the socket. The price does not depend on it.
- The open points in [board-verification.md](../../../docs/design/board-verification.md) under "Still open".

Sources for PCBWay's limits and SummerCart64's order settings, and what the review behind these files found: [pre-order-review.md](../../../docs/design/pre-order-review.md).
""".replace('{name}', NAME)

README = """# SN64 v1 board (files named sn64-v2): manufacturing files

Made by `hardware/sn64-v2/tools/make_production_v2.py` on {date}. **For a quotation. Not released for manufacture, and nothing has been sent to a maker.**

- The SNES socket's footprint (J2) waits for a measured sample of the socket.
- No board has been built. What has and has not been checked is in [board-verification.md](../../../docs/design/board-verification.md).
- What to enter in PCBWay's forms: [quote-sheet.md](quote-sheet.md).

| | |
|---|---|
| Board | {w} x {h} mm, {layers} copper layers, {t} mm, {tracks} tracks, {vias} vias, {length} mm of track |
| Parts | {placed} placed by the assembler ({top} top, {bottom} bottom), {lines} different part numbers, {smd_pads} surface-mount pads |
| KiCad's rule check | no error, no open connection, no difference from the schematic. {mask_notes} notes, all about the solder mask being open across the row of edge fingers, which is on purpose |
| Board file SHA-256 | `{board_sha}` |
| Netlist SHA-256 | `{net_sha}` |

The top face in these files (F.Cu) is the back of the cartridge. The bottom face (B.Cu) is the label side, which faces the player.

## fabrication/

| File | What it is |
|---|---|
{files}

## assembly/

| File | What it is |
|---|---|
{asm_files}

The two zip files beside this text hold the same two folders for uploading. They are made by the tool and are not kept in the repository.

To make everything again after a change to the board:

```
python hardware/sn64-v2/tools/make_production_v2.py
```

with KiCad's Python. The tool refuses a board whose rule check is not clean.
"""


if __name__ == '__main__':
    main()
