"""Create the initial editable connector sheet; never overwrite edits implicitly.

Run with KiCad's Python (pcbnew) and --references pointing at the downloaded
reference collection. This is an initial authoring tool, not a board generator.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import uuid

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = uuid.UUID("b0b9778b-5663-434b-9e08-e934d14c6f8a")


def uid(role):
    return str(uuid.uuid5(NAMESPACE, role))


def q(value):
    return json.dumps(str(value), ensure_ascii=False)


def prop(name, value, x=0, y=0, hide=False, size=1.27):
    return (f'(property {q(name)} {q(value)} (at {x:g} {y:g} 0) '
            f'(effects (font (size {size} {size}))'
            f'{" (hide yes)" if hide else ""}))')


def net_name(side, signal):
    if signal == "GND":
        return "GND"
    if side == "N64" and signal in ("3V3", "12V"):
        return "HOST_" + signal
    if signal == "+5V_CART":
        return "SNES_5V_CART"
    if signal.startswith("/"):
        return f"{side}_{signal[1:]}_N"
    return f"{side}_{signal}"


def text(value, x, y, size=1.27):
    return (f'(text {q(value)} (at {x:g} {y:g} 0) '
            f'(effects (font (size {size} {size})) (justify left top)) '
            f'(uuid {q(uid("text:"+value))}))')


def symbol_body(name, rows, footprint, embedded=False):
    count = len(rows) // 2
    top = (count - 1) * 2.54
    full_name = f"SN64:{name}" if embedded else name
    body = [f'(symbol {q(full_name)} (pin_names (offset 1.27)) '
            '(exclude_from_sim no) (in_bom yes) (on_board yes)',
            prop("Reference", "J", 0, top+7.62),
            prop("Value", name, 0, top+5.08),
            prop("Footprint", "SN64:"+footprint, hide=True),
            prop("Datasheet", "", hide=True),
            prop("Description", "Reference-verified connector; passive pin types. See interface CSV for endpoint directions.", hide=True),
            f'(symbol {q(name+"_0_1")} (rectangle '
            f'(start -38.1 {top+2.54:g}) (end 38.1 {-top-2.54:g}) '
            '(stroke (width 0.254) (type default)) (fill (type background))))',
            f'(symbol {q(name+"_1_1")}']
    for row in rows:
        number = int(row["pin"])
        left = number <= count
        y = top - ((number-1) % count) * 5.08
        x, angle = (-43.18, 0) if left else (43.18, 180)
        body.append(f'(pin passive line (at {x:g} {y:g} {angle}) (length 5.08) '
                    f'(name {q(row["signal"])} (effects (font (size 1.016 1.016)))) '
                    f'(number {q(number)} (effects (font (size 1.016 1.016)))))')
    return "\n".join(body) + "))"


def placed_symbol(side, name, rows, footprint, reference, x, y):
    top = (len(rows)//2 - 1) * 2.54
    parts = [f'(symbol (lib_id {q("SN64:"+name)}) (at {x:g} {y:g} 0) (unit 1) '
             '(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) '
             f'(uuid {q(uid(reference))})',
             prop("Reference", reference, x, y-top-7.62),
             prop("Value", name, x, y-top-5.08),
             prop("Footprint", "SN64:"+footprint, x, y, True),
             prop("Datasheet", "", x, y, True),
             prop("Description", "Interface draft only; see hardware/sn64/README.md", x, y, True)]
    for row in rows:
        parts.append(f'(pin {q(row["pin"])} (uuid {q(uid(reference+":"+row["pin"]))}))')
    parts.append(f'(instances (project "sn64" (path {q("/"+uid("root"))} '
                 f'(reference {q(reference)}) (unit 1)))))')
    for row in rows:
        number = int(row["pin"])
        count = len(rows)//2
        left = number <= count
        yy = y-top+((number-1)%count)*5.08
        pin_x = x+(-43.18 if left else 43.18)
        label_x = x+(-55.88 if left else 55.88)
        role = reference+":"+row["pin"]
        parts.append(f'(wire (pts (xy {pin_x:g} {yy:g}) (xy {label_x:g} {yy:g})) '
                     f'(stroke (width 0) (type default)) (uuid {q(uid("wire:"+role))}))')
        # Keep long net names outside the short connector wires.
        parts.append(f'(label {q(net_name(side, row["signal"]))} (at {label_x:g} {yy:g} 0) '
                     f'(effects (font (size 1.016 1.016)) (justify {"right" if left else "left"} bottom)) '
                     f'(uuid {q(uid("label:"+role))}))')
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", required=True, type=Path)
    parser.add_argument("--project-template", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="Replace the generated initial draft, discarding subsequent edits")
    args = parser.parse_args()
    if (ROOT / "sn64.kicad_sch").exists() and not args.force:
        parser.error("sn64.kicad_sch exists; edit it in KiCad or explicitly use --force")

    sources = args.references
    snes_source = sources / "sanni/hardware/footprints/!OSCR.pretty/SNES Slot.kicad_mod"
    n64_source = sources / "summercart64/hw/pcb/sc64v2.kicad_pcb"
    library = ROOT / "libraries/SN64.pretty"
    library.mkdir(parents=True, exist_ok=True)
    licenses = ROOT / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copyfile(sources / "sanni/hardware/LICENSE.txt", licenses / "Sanni-CC-BY-4.0.txt")
    shutil.copyfile(sources / "summercart64/hw/pcb/LICENSE", licenses / "SummerCart64-CERN-OHL-S-2.0.txt")

    # Preserve the actual upstream female footprint, with its original name.
    shutil.copyfile(snes_source, library / "SNES Slot.kicad_mod")
    board = pcbnew.LoadBoard(str(n64_source))
    connector = next(f for f in board.GetFootprints() if f.GetReference() == "J_N1")
    connector.SetFPIDAsString("SN64:N64_Edge_SC64_Reference")
    connector.SetReference("REF**")
    connector.SetValue("N64_Edge_SC64_Reference")
    connector.SetPosition(pcbnew.VECTOR2I(0, 0))
    for pad in connector.Pads():
        pad.SetNetCode(0)
    pcbnew.FootprintSave(str(library), connector)

    specs = [("N64", "N64_Cartridge_Edge_50", "N64_Edge_SC64_Reference", "J1", 101.6, 127.0),
             ("SNES", "SNES_Female_Slot_62", "SNES Slot", "J2", 292.1, 127.0)]
    parts, embedded, symbols = [], [], []
    for side, name, footprint, reference, x, y in specs:
        with (ROOT / f"interfaces/{side.lower()}-pin-map.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        expected = 50 if side == "N64" else 62
        assert sorted(int(r["pin"]) for r in rows) == list(range(1, expected+1))
        symbols.append(symbol_body(name, rows, footprint))
        embedded.append(symbol_body(name, rows, footprint, True))
        parts.append(placed_symbol(side, name, rows, footprint, reference, x, y))

    header = (f'(kicad_sch (version 20250114) (generator "sn64_interface_builder") '
              f'(uuid {q(uid("root"))}) (paper "A3") '
              '(title_block (title "SN 64 - cartridge interfaces") (date "2026-09-28") '
              '(rev "0.1-interface") (company "SN 64") '
              '(comment 1 "INTERFACE DRAFT ONLY - NOT FOR MANUFACTURE") '
              '(comment 2 "Source attribution and limits: hardware/sn64/README.md"))')
    notes = [
        text("N64 / M64 HOST EDGE", 35.56, 20.32, 2.0),
        text("SNES / SUPER FAMICOM SOCKET", 226.06, 20.32, 2.0),
        text("Same 50-contact interface for both host systems", 35.56, 27.94),
        text("All 62 contacts retained, including analog cartridge audio", 226.06, 27.94),
        text("HOST INTERFACE\n3.3 V logic; power inputs remain separate from local rails.\nAD[15:0] is bidirectional. CIC_DATA / JOYBUS require release.\nReserved contacts and audio are identified only; no drivers fitted.\nHOST_12V is reserved, with no selected load. No 5 V edge supply.", 30.48, 208.28),
        text("SNES INTERFACE\n5 V cartridge logic requires reviewed translation and isolation.\nSNES_5V_CART: protected switched supply, default OFF (pending).\nSystem RESET must support cartridge assertion and input sensing.\nCIC_SLAVE_RESET is separate; AUDIO_L/R_IN are analog inputs.\nNo universal NC contacts. Full pin behavior is recorded in the CSV.", 220.98, 213.36),
        text("DRAFT BOUNDARY: connectors and net identities only. FPGA, power, protection, translators, memory, recovery and A/V circuits are pending.\nOnly GND is common between the two connectors. Matching names within one domain identify the same net; _N means active low.\nConnector pin types are passive; electrical directions and source evidence are in interfaces/*.csv and docs/design/*-interface-notes.md.", 20.32, 248.92),
    ]
    schematic = "\n".join([header, "(lib_symbols", *embedded, ")", *parts, *notes,
                           '(sheet_instances (path "/" (page "1"))) (embedded_fonts no))']) + "\n"
    (ROOT / "sn64.kicad_sch").write_text(schematic, encoding="utf-8", newline="\n")
    (ROOT / "libraries/SN64.kicad_sym").write_text(
        '(kicad_symbol_lib (version 20250114) (generator "sn64_interface_builder")\n'
        + "\n".join(symbols) + ")\n", encoding="utf-8", newline="\n")
    (ROOT / "sym-lib-table").write_text(
        '(sym_lib_table (version 7) (lib (name "SN64") (type "KiCad") '
        '(uri "${KIPRJMOD}/libraries/SN64.kicad_sym") (options "") '
        '(descr "SN 64 project connector symbols")))\n', encoding="utf-8", newline="\n")
    (ROOT / "fp-lib-table").write_text(
        '(fp_lib_table (version 7) (lib (name "SN64") (type "KiCad") '
        '(uri "${KIPRJMOD}/libraries/SN64.pretty") (options "") '
        '(descr "Upstream reference footprints; see THIRD_PARTY.md")))\n', encoding="utf-8", newline="\n")
    project = json.loads(args.project_template.read_text(encoding="utf-8"))
    project["meta"]["filename"] = "sn64.kicad_pro"
    (ROOT / "sn64.kicad_pro").write_text(json.dumps(project, indent=2)+"\n", encoding="utf-8", newline="\n")
    provenance = {
        "status": "reference footprints only; no final socket MPN, PCB outline, fit or release approval",
        "snes_footprint": {"project": "sanni/cartreader", "commit": "060d8ae0bf4be40bfc6a368bf6fbf7b594b3884d", "sha256": hashlib.sha256(snes_source.read_bytes()).hexdigest(), "changes": "none; byte-identical copy"},
        "n64_footprint": {"project": "Polprzewodnikowy/SummerCart64", "commit": "a1e7996d2cbece686820a5c785029c68514f17b0", "source_board_sha256": hashlib.sha256(n64_source.read_bytes()).hexdigest(), "source_reference": "J_N1", "changes": "Extracted with KiCad 10 pcbnew; origin at source (150,125), renamed reference/value/library ID, pad net assignments removed; source pad geometry and copper sides retained. Six source Edge.Cuts segments retain the open connector-edge profile; no complete PCB perimeter or mounting holes. Do not duplicate the retained profile during layout."},
    }
    (ROOT / "libraries/provenance.json").write_text(json.dumps(provenance, indent=2)+"\n", encoding="utf-8", newline="\n")
    print("Created initial connector schematic, project-local symbols, and reused footprints in", ROOT)


if __name__ == "__main__":
    main()
