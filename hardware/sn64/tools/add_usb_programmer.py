"""Author the initial USB programmer child sheet from pinned/reference symbols.

This is a one-time draft authoring utility. --force overwrites this child sheet,
not hand edits on the cartridge interface sheet. Run with KiCad's Python.
"""
import argparse
import copy
import csv
import json
import math
from pathlib import Path
import re
import shutil
import uuid
import pcbnew

ROOT = Path(__file__).resolve().parents[1]
NS = uuid.UUID('c48b72b8-46e0-43b5-9e5e-ac401736d1c1')
def uid(s): return str(uuid.uuid5(NS, s))
def q(s): return json.dumps(str(s), ensure_ascii=False)
class Quoted(str): pass
def parse(path):
    stack=[]; result=[]
    for token in re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', path.read_text(encoding='utf-8-sig')):
        if token=='(':
            item=[]; (stack[-1] if stack else result).append(item); stack.append(item)
        elif token==')': stack.pop()
        else: stack[-1].append(Quoted(json.loads(token)) if token.startswith('"') else token)
    assert len(result)==1 and not stack
    return result[0]
def dump(n):
    if isinstance(n,list): return '('+' '.join(dump(v) for v in n)+')'
    return q(n) if isinstance(n,Quoted) else str(n)
def items(n,k): return [v for v in n if isinstance(v,list) and v and v[0]==k]
def get(n,k): return next(iter(items(n,k)),None)
def save(path,text): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text+'\n',encoding='utf-8',newline='\n')
def prop(k,v,x,y,hide=False,left=False):
    return f'(property {q(k)} {q(v)} (at {x:g} {y:g} 0) (effects (font (size 1.27 1.27)){" (justify left)" if left else ""}{" (hide yes)" if hide else ""}))'
def txt(s,x,y,size=1.27):
    return f'(text {q(s)} (at {x:g} {y:g} 0) (effects (font (size {size} {size})) (justify left top)) (uuid {q(uid(s))}))'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-root',type=Path,required=True)
    ap.add_argument('--kicad-share',type=Path,required=True)
    ap.add_argument('--force',action='store_true')
    a=ap.parse_args()
    dest=ROOT/'usb-programmer.kicad_sch'
    if dest.exists() and not a.force: ap.error('Child sheet exists; use KiCad to edit, or --force to replace the initial draft')
    source=a.source_root/'references/downloads/summercart64/hw/pcb'
    source_sch=parse(source/'sc64v2.kicad_sch')
    upstream={str(s[1]):s for s in items(get(source_sch,'lib_symbols'),'symbol')}
    libs={}; parts=[]; records=[]; fps=set()
    def load(lib_id):
        if lib_id in libs: return libs[lib_id]
        if lib_id in upstream: s=copy.deepcopy(upstream[lib_id])
        else:
            lib,name=lib_id.split(':'); db=parse(a.kicad_share/'symbols'/f'{lib}.kicad_sym')
            byname={str(s[1]):s for s in items(db,'symbol')}
            def resolve(name):
                node=copy.deepcopy(byname[name]); ext=get(node,'extends')
                if not ext: return node
                base=resolve(str(ext[1])); old=str(base[1]); base[1]=Quoted(name)
                for unit in items(base,'symbol'): unit[1]=Quoted(str(unit[1]).replace(old+'_',name+'_',1))
                for p in items(node,'property'):
                    base[:]=[v for v in base if not(isinstance(v,list) and v[:2]==p[:2])]
                    base.append(p)
                return base
            s=resolve(name); s[1]=Quoted(lib_id)
        if lib_id=='Interface_USB:FT232H':
            # Correct two upstream symbol types against FTDI table 3.3: the
            # bridge drives EEPROM chip-select and clock. No circuit changed.
            for unit in items(s,'symbol'):
                for pin in items(unit,'pin'):
                    if str(get(pin,'number')[1]) in ('44','45'): pin[1]='output'
        libs[lib_id]=s; return s
    def own(name,pins):
        # Compact custom 16-pin translator symbol, numbered from TI PW datasheet.
        lines=[f'(symbol {q("SN64_USB:"+name)} (pin_names (offset 1.016)) (in_bom yes) (on_board yes)',prop('Reference','U',0,24.13),prop('Value',name,0,21.59),
               f'(symbol {q(name+"_0_1")} (rectangle (start -15.24 20.32) (end 15.24 -20.32) (stroke (width 0.254) (type default)) (fill (type background))))',f'(symbol {q(name+"_1_1")}']
        for number,label,typ,x,y,angle in pins:
            lines.append(f'(pin {typ} line (at {x} {y} {angle}) (length 5.08) (name {q(label)} (effects (font (size 1.27 1.27)))) (number {q(number)} (effects (font (size 1.016 1.016)))))')
        raw='\n'.join(lines)+'))'
        temp=ROOT/'.usb-symbol.tmp'; save(temp,raw); s=parse(temp); temp.unlink(); libs['SN64_USB:'+name]=s
    own('SN74AXC4T774PW',[
        ('16','VCCA','power_in',-20.32,17.78,0),('15','VCCB','power_in',20.32,17.78,180),
        ('3','A1','bidirectional',-20.32,12.7,0),('14','B1','bidirectional',20.32,12.7,180),
        ('4','A2','bidirectional',-20.32,7.62,0),('13','B2','bidirectional',20.32,7.62,180),
        ('5','A3','bidirectional',-20.32,2.54,0),('12','B3','bidirectional',20.32,2.54,180),
        ('6','A4','bidirectional',-20.32,-2.54,0),('11','B4','bidirectional',20.32,-2.54,180),
        ('1','DIR1','input',-20.32,-7.62,0),('2','DIR2','input',-20.32,-12.7,0),
        ('7','DIR3','input',20.32,-7.62,180),('8','DIR4','input',20.32,-12.7,180),
        ('9','~{OE}','input',-20.32,-17.78,0),('10','GND','power_in',20.32,-17.78,180)])
    def place(ref,lib_id,value,x,y,nets,fp='',dnp=False,fields=None):
        sym=load(lib_id); pins=[p for u in items(sym,'symbol') for p in items(u,'pin')]
        # All selected symbols have one unit. Pin number/net map is explicit.
        assert {str(get(p,'number')[1]) for p in pins}==set(nets),(ref,set(nets),[get(p,'number') for p in pins])
        small=lib_id in ('Device:R','Device:C','Device:L','Device:Ferrite_Bead','Device:Crystal_GND24')
        if small: rx,ry=x+3.81,y-1.27; vx,vy=x+3.81,y+1.27
        if not small:
            top=min(y-float(get(p,'at')[2]) for p in pins)
            rx,ry=x-10.16,top-8.89; vx,vy=x-10.16,top-6.35
        if ref=='U104': rx=vx=x-38.1
        if ref in ('U101','U102','U106'): rx=vx=x-25.4
        if ref=='Y101': rx=vx=x; ry=y-15.24; vy=y-12.7
        p=[f'(symbol (lib_id {q(lib_id)}) (at {x:g} {y:g} 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp {"yes" if dnp else "no"}) (uuid {q(uid(ref))})',
           prop('Reference',ref,rx,ry,ref.startswith('#'),small and ref!='Y101'),prop('Value',value,vx,vy,ref.startswith('#'),small and ref!='Y101'),prop('Footprint',('SN64_USB:'+fp.split(':')[1]) if fp else '',x,y,True),prop('Datasheet',(fields or {}).get('Datasheet',''),x,y,True)]
        for k,v in (fields or {}).items():
            if k!='Datasheet': p.append(prop(k,v,x,y,True))
        for pin in pins: p.append(f'(pin {q(get(pin,"number")[1])} (uuid {q(uid(ref+":"+str(get(pin,"number")[1])))}))')
        p.append(f'(instances (project "sn64" (path {q("/"+root_uuid+"/"+sheet_uuid)} (reference {q(ref)}) (unit 1)))))')
        parts.extend(p); seen=set()
        for pin in pins:
            number=str(get(pin,'number')[1]); net=nets[number]; at=get(pin,'at'); px=x+float(at[1]); py=y-float(at[2]); angle=int(at[3]); role=ref+':'+number
            records.append({'reference':ref,'pin':number,'pin_name':str(get(pin,'name')[1]),'net':net,'value':value,'dnp':dnp})
            if (px,py,net) in seen: continue
            seen.add((px,py,net))
            if net is None:
                parts.append(f'(no_connect (at {px:g} {py:g}) (uuid {q(uid("nc:"+role))}))'); continue
            dx=-5.08*round(math.cos(math.radians(angle))); dy=5.08*round(math.sin(math.radians(angle)))
            ex,ey=px+dx,py+dy
            parts.append(f'(wire (pts (xy {px:g} {py:g}) (xy {ex:g} {ey:g})) (stroke (width 0) (type default)) (uuid {q(uid("w:"+role))}))')
            justify='right' if dx<0 else 'left'
            label_angle=90 if dy else 0
            parts.append(f'(label {q(net)} (at {ex:g} {ey:g} {label_angle}) (effects (font (size 1.016 1.016)) (justify {justify} bottom)) (uuid {q(uid("l:"+role))}))')
        if fp: fps.add(fp)
    root=parse(ROOT/'sn64.kicad_sch'); root_uuid=str(get(root,'uuid')[1]); sheet_uuid=uid('sheet'); page_uuid=uid('page')
    # USB inlet and separate CC termination; source pin identities retained.
    usb={p:'GND' for p in ('A1','A12','B1','B12','S1')}
    usb.update({p:'USB_VBUS' for p in ('A4','A9','B4','B9')})
    usb.update({'A5':'USB_CC1','B5':'USB_CC2','A6':'USB_DP','B6':'USB_DP','A7':'USB_DM','B7':'USB_DM','A8':None,'B8':None})
    place('J101','Connector:USB_C_Receptacle_USB2.0','DX07S016JA3R1500',45.72,81.28,usb,'SN64_USB:USB_C_JAE_DX07S016JA3R1500')
    place('R101','Device:R','5.1k 1%',101.6,60.96,{'1':'USB_CC1','2':'GND'},'Resistor_SMD:R_0603_1608Metric')
    place('R102','Device:R','5.1k 1%',139.7,60.96,{'1':'USB_CC2','2':'GND'},'Resistor_SMD:R_0603_1608Metric')
    # Both flow-through pairs remain the same net in the schematic; PCB routes
    # connector -> ESD pad -> paired ESD pad -> FTDI, not a long protection stub.
    place('U101','Power_Protection:USBLC6-2SC6','USBLC6-2SC6',127,106.68,{'1':'USB_DM','6':'USB_DM','3':'USB_DP','4':'USB_DP','2':'GND','5':'USB_VBUS'},'Package_TO_SOT_SMD:SOT-23-6',fields={'Datasheet':'https://www.st.com/resource/en/datasheet/usblc6-2.pdf'})
    place('U102','Power_Protection:USBLC6-2SC6','USBLC6-2SC6',127,157.48,{'1':'USB_CC1','6':'USB_CC1','3':'USB_CC2','4':'USB_CC2','2':'GND','5':'USB_VBUS'},'Package_TO_SOT_SMD:SOT-23-6')
    place('U103','Regulator_Linear:AP2112K-3.3','AP2112K-3.3TRG1',50.8,172.72,{'1':'USB_VBUS','2':'GND','3':'USB_VBUS','4':None,'5':'USB_3V3'},'Package_TO_SOT_SMD:SOT-23-5',fields={'Datasheet':'https://www.diodes.com/assets/Datasheets/AP2112.pdf'})
    # FT232HL support topology from SC64; VREGIN=3.3V requires FTDI revision C.
    fn={str(i):None for i in range(1,49)}
    for p in (4,9,10,11,22,23,35,36,41,47,48,42): fn[str(p)]='GND'
    for p in (12,24,39,40,46): fn[str(p)]='USB_3V3'
    fn.update({'1':'XTAL_IN','2':'XTAL_OUT','3':'FT_VPHY','5':'FT_REF','6':'USB_DM','7':'USB_DP','8':'FT_VPLL','13':'FT_TCK','14':'FT_TDI','15':'FT_TDO','16':'FT_TMS','30':'JTAG_OE_N','34':'FT_RESET_N','37':'FT_1V8A','38':'FT_1V8CORE','43':'EE_DATA','44':'EE_CLK','45':'EE_CS'})
    place('U104','Interface_USB:FT232H','FT232HL (rev C)',269.24,104.14,fn,'Package_QFP:LQFP-48_7x7mm_P0.5mm',fields={'Datasheet':'https://www.ftdichip.cn/Support/Documents/DataSheets/ICs/DS_FT232H.pdf'})
    place('U105','SN64_USB:SN74AXC4T774PW','SN74AXC4T774PWR',429.26,91.44,{'1':'USB_3V3','2':'USB_3V3','3':'FT_TCK','4':'FT_TDI','5':'FT_TDO','6':'FT_TMS','7':'GND','8':'USB_3V3','9':'JTAG_OE_N','10':'GND','11':'TMS_DRV','12':'TDO_RCV','13':'TDI_DRV','14':'TCK_DRV','15':'TARGET_VREF','16':'USB_3V3'},'Package_SO:TSSOP-16_4.4x5mm_P0.65mm',fields={'Datasheet':'https://www.ti.com/lit/ds/symlink/sn74axc4t774.pdf'})
    place('J102','Connector_Generic:Conn_01x06','JTAG_SERVICE',528.32,93.98,{'1':'TARGET_VREF','2':'GND','3':'JTAG_TCK','4':'JTAG_TDI','5':'JTAG_TDO','6':'JTAG_TMS'},'Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical')
    place('Y101','Device:Crystal_GND24','ABM3B-12.000MHZ-10-1-U-T',187.96,200.66,{'1':'XTAL_IN','2':'GND','3':'XTAL_OUT','4':'GND'},'Crystal:Crystal_SMD_Abracon_ABM3B-4Pin_5.0x3.2mm')
    place('U106','Memory_EEPROM:93AAxxBT-xOT','93AA56BT-I/OT (DNP)',292.1,205.74,{'1':'EE_DO','2':'GND','3':'EE_DATA','4':'EE_CLK','5':'EE_CS','6':'USB_3V3'},'Package_TO_SOT_SMD:SOT-23-6',dnp=True)
    resistor_data=[('R103','12k 1%','FT_REF','GND'),('R104','12k','USB_3V3','FT_RESET_N'),('R105','10k','USB_3V3','JTAG_OE_N'),('R106','2.2k','EE_DO','EE_DATA'),('R107','10k','USB_3V3','EE_DO'),('R108','33','TCK_DRV','JTAG_TCK'),('R109','33','TDI_DRV','JTAG_TDI'),('R110','33','TDO_RCV','JTAG_TDO'),('R111','33','TMS_DRV','JTAG_TMS'),('R112','10k','JTAG_TCK','GND'),('R113','10k','TARGET_VREF','JTAG_TDI'),('R114','10k','TARGET_VREF','JTAG_TMS')]
    for i,(ref,value,n1,n2) in enumerate(resistor_data):
        place(ref,'Device:R',value,25.4+(i%6)*93.98,259.08+(i//6)*30.48,{'1':n1,'2':n2},'Resistor_SMD:R_0603_1608Metric')
    cap_data=[('C101','4.7uF 10V','USB_VBUS'),('C102','1uF 10V','USB_VBUS'),('C103','4.7uF 10V','USB_3V3'),('C104','100nF','FT_VPHY'),('C105','100nF','FT_VPLL'),('C106','100nF','USB_3V3'),('C107','100nF','USB_3V3'),('C108','100nF','USB_3V3'),('C109','100nF','USB_3V3'),('C110','100nF','FT_1V8A'),('C111','100nF','FT_1V8CORE'),('C112','100nF','USB_3V3'),('C113','100nF','TARGET_VREF'),('C114','100nF','USB_3V3'),('C115','11pF C0G (tune)','XTAL_IN'),('C116','11pF C0G (tune)','XTAL_OUT')]
    for i,(ref,value,net) in enumerate(cap_data):
        place(ref,'Device:C',value,25.4+(i%8)*68.58,327.66+(i//8)*30.48,{'1':net,'2':'GND'},'Capacitor_SMD:C_0603_1608Metric')
    place('L101','Device:L','470R @ 100MHz',198.12,157.48,{'1':'USB_3V3','2':'FT_VPHY'},'Inductor_SMD:L_0603_1608Metric')
    place('L102','Device:L','470R @ 100MHz',236.22,157.48,{'1':'USB_3V3','2':'FT_VPLL'},'Inductor_SMD:L_0603_1608Metric')
    # External-source flags reflect connector power inputs, not completed target power generation.
    place('#FLG101','power:PWR_FLAG','PWR_FLAG',73.66,127,{'1':'USB_VBUS'})
    place('#FLG102','power:PWR_FLAG','PWR_FLAG',355.6,139.7,{'1':'GND'})
    place('#FLG103','power:PWR_FLAG','PWR_FLAG',490.22,147.32,{'1':'TARGET_VREF'})
    place('#FLG104','power:PWR_FLAG','PWR_FLAG',198.12,175.26,{'1':'FT_VPHY'})
    place('#FLG105','power:PWR_FLAG','PWR_FLAG',236.22,175.26,{'1':'FT_VPLL'})
    # One hierarchical return connects to the cartridge-interface sheet's GND.
    parts.append(f'(hierarchical_label "GND" (shape passive) (at 25.4 121.92 0) (effects (font (size 1.27 1.27)) (justify left)) (uuid {q(uid("ground-port"))}))')
    parts.append(f'(label "GND" (at 25.4 121.92 0) (effects (font (size 1.016 1.016)) (justify right bottom)) (uuid {q(uid("ground-port-label"))}))')
    notes=[txt('SIDE USB-C: INITIAL PROGRAMMING + RECOVERY',20.32,17.78,2.54),txt('USB 2.0 device; 5V input only. Side location is mandatory; exact PCB/enclosure placement remains open.',20.32,25.4),
           txt('FT232H HARDWARE BRIDGE',208.28,35.56,1.778),txt('TARGET ISOLATION + SERVICE ACCESS',373.38,35.56,1.778),
           txt('TARGET_VREF comes from the future FPGA programming rail.\nIt powers the B-side translator; it is NOT a USB power output.\nJTAG_TCK/TDI/TDO/TMS need final FPGA/flash integration.\nOnly one programmer may own JTAG at a time.',373.38,175.26),
           txt('DEFAULT DISABLED: R105 pulls /OE high. FTDI ACBUS6 is\ninput/pulled-up at blank startup. Host enters MPSSE first,\nthen enables the buffer with --status-pin 14.\nGeneric ft232 without that flag leaves the buffer disabled.',373.38,198.12),
           txt('USB_3V3 powers this programmer only. No USB/host power tie.\nMain FPGA/system power and cartridge power remain separate work.\nUSB suspend, inrush, ESD and power-off behavior require bench tests.',20.32,198.12),
           txt('12MHz crystal replaces SC64 external oscillator.\n11pF caps are provisional: verify frequency/load after layout.\nOptional blank EEPROM: no main-FPGA firmware needed to enumerate.',177.8,231.14),
           txt('SUPPORT PASSIVES (place at their associated IC/pin; electrical grouping here is not PCB placement)',20.32,241.3),
           txt('DRAFT 0.2: USB programmer circuitry only. FPGA/storage choice, persistent-image map, system power, routing and physical validation are pending.\nSources: SummerCart64 a1e7996 (CERN-OHL-S-2.0), FTDI FT232H v2.2, TI SN74AXC4T774, JAE drawing SJ122205. See docs/design/usb-programming-architecture.md.',20.32,386.08)]
    contents=f'(kicad_sch (version 20250114) (generator "sn64_usb_authoring") (uuid {q(page_uuid)}) (paper "A2") (title_block (title "SN 64 - side USB-C programmer") (date "2026-09-29") (rev "0.2-usb") (company "SN 64") (comment 1 "DESIGN DRAFT - NOT FOR MANUFACTURE"))\n(lib_symbols\n'+ '\n'.join(dump(s) for s in libs.values())+')\n'+'\n'.join(parts+notes)+f'\n(sheet_instances (path {q("/"+root_uuid+"/"+sheet_uuid)} (page "2"))) (embedded_fonts no))'
    save(dest,contents)
    # Local library names replace original IDs consistently for portable editing.
    symbols=[]
    for key,sym in libs.items():
        sym=copy.deepcopy(sym); sym[1]=Quoted(key.split(':')[1]); symbols.append(dump(sym))
    save(ROOT/'libraries/SN64_USB.kicad_sym','(kicad_symbol_lib (version 20250114) (generator "sn64_usb_authoring")\n'+'\n'.join(symbols)+')')
    text=dest.read_text(encoding='utf-8')
    for key in libs: text=text.replace(q(key),q('SN64_USB:'+key.split(':')[1]))
    save(dest,text.rstrip())
    for filename,typ,uri in [('sym-lib-table','KiCad','${KIPRJMOD}/libraries/SN64_USB.kicad_sym'),('fp-lib-table','KiCad','${KIPRJMOD}/libraries/SN64_USB.pretty')]:
        table=parse(ROOT/filename); table[:]=[e for e in table if not(isinstance(e,list) and e and e[0]=='lib' and get(e,'name')[1]=='SN64_USB')]
        table.append(['lib',['name',Quoted('SN64_USB')],['type',Quoted(typ)],['uri',Quoted(uri)],['options',Quoted('')],['descr',Quoted('USB programmer draft; see THIRD_PARTY.md')]])
        save(ROOT/filename,dump(table))
    fpdir=ROOT/'libraries/SN64_USB.pretty'; fpdir.mkdir(exist_ok=True)
    for fp in sorted(fps):
        lib,name=fp.split(':')
        if lib!='SN64_USB': shutil.copyfile(a.kicad_share/'footprints'/(lib+'.pretty')/(name+'.kicad_mod'),fpdir/(name+'.kicad_mod'))
    board=pcbnew.LoadBoard(str(source/'sc64v2.kicad_pcb'))
    connector=next(f for f in board.GetFootprints() if f.GetReference()=='J1')
    connector.SetOrientationDegrees(0); connector.SetPosition(pcbnew.VECTOR2I(0,0)); connector.SetFPIDAsString('SN64_USB:USB_C_JAE_DX07S016JA3R1500'); connector.SetReference('REF**'); connector.SetValue('DX07S016JA3R1500'); connector.Models().clear()
    for p in connector.Pads(): p.SetNetCode(0)
    pcbnew.FootprintSave(str(fpdir),connector)
    for footprint in fpdir.glob('*.kicad_mod'):
        footprint.write_text(footprint.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    with (ROOT/'interfaces/usb-programmer-net-map.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator='\n'); w.writeheader(); w.writerows(records)
    # Add the child sheet to the root without rewriting existing source objects.
    original=(ROOT/'sn64.kicad_sch').read_text(encoding='utf-8')
    if sheet_uuid not in original:
        block=f'(sheet (at 20.32 229.87) (size 76.2 12.7) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0)) (uuid {q(sheet_uuid)}) '+prop('Sheetname','USB-C programmer',20.32,227.33,left=True)+prop('Sheetfile','usb-programmer.kicad_sch',20.32,245.11,left=True)+f' (pin "GND" passive (at 96.52 236.22 0) (effects (font (size 1.27 1.27)) (justify right)) (uuid {q(uid("root-ground-pin"))})) (instances (project "sn64" (path {q("/"+root_uuid)} (page "2")))))\n(label "GND" (at 96.52 236.22 0) (effects (font (size 1.016 1.016)) (justify left bottom)) (uuid {q(uid("root-ground-label"))}))'
        original=original.rstrip()[:-1]+'\n'+block+'\n)'
        original=original.replace('(rev "0.1-interface")','(rev "0.2-usb")')
        original=original.replace('DRAFT BOUNDARY: connectors and net identities only. FPGA, power, protection, translators, memory, recovery and A/V circuits are pending.', 'DRAFT BOUNDARY: cartridge connectors + USB programmer child sheet. Main FPGA, system power, cartridge translation and A/V remain pending.')
        save(ROOT/'sn64.kicad_sch',original)
    print('Authored USB programmer sheet:',len(records),'pin assignments;',len(fps),'footprints')

if __name__=='__main__': main()
