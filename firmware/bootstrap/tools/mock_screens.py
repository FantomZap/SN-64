"""Draw mock-ups of the boot menu's screens: the two splash screens, the cartridge-check screens,
the compatibility-mode screens and the credits roll.

The splash pictures are read from src/sn64_splash_data.c, pixel for pixel as the ROM holds them.
The texts are read from src/sn64_cartcheck.c, so the picture cannot drift from the wording; the
layout (8x8 character cells at x = 16, y = 12 + 10 * row on a 320 x 240 screen, the colours) is
copied by hand from src/main.c. The compatibility-mode confirmation is read from the file the
host test writes with the code under test (`make test-framelock` ->
build/n64-bootstrap/host/compat-screen.txt), numbers included. This is a drawing, not a capture:
the menu has not run on a console or an emulator yet, and the console's own font looks different.

The credits roll is read from src/sn64_credits_data.c, text and line kinds, and laid out as
src/sn64_credits.c lays it out.

  python tools/mock_screens.py        writes docs/design/img/cart-check-screens.png, splash-screens.png,
                                      compat-screens.png and credits-screens.png
"""
import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SCALE = 3
W, H, CELL, ROW = 320, 240, 8, 10
BG, TEXT, DIM, HI, WARN = (0x10, 0x18, 0x30), (0xE0, 0xE0, 0xE0), (0x80, 0x88, 0x98), (0xFF, 0xD8, 0x40), (0xFF, 0x60, 0x50)


def font():
    for name in ('courbd.ttf', 'DejaVuSansMono-Bold.ttf', 'LiberationMono-Bold.ttf'):
        try:
            return ImageFont.truetype(name, 9 * SCALE)
        except OSError:
            continue
    return ImageFont.load_default(9 * SCALE)


def alert_lines(source, array):
    """The string literals of one `static const char *const <array>[] = {...}` block."""
    block = re.search(r'%s\[\]\s*=\s*\{(.*?)\};' % re.escape(array), source, re.S).group(1)
    return [m.group(1) for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', block)]


class Screen:
    def __init__(self, title):
        self.title = title
        self.im = Image.new('RGB', (W * SCALE, H * SCALE), BG)
        self.d = ImageDraw.Draw(self.im)
        self.f = font()

    def line(self, row, colour, text):
        assert len(text) <= 38, (len(text), text)        # 38 columns fit the screen from x = 16
        for i, ch in enumerate(text):
            x = (16 + i * CELL + CELL / 2) * SCALE
            y = (12 + row * ROW + CELL / 2) * SCALE
            self.d.text((x, y), ch, font=self.f, fill=colour, anchor='mm')

    def header(self):
        self.line(0, HI, 'SN64 bootstrap v0.1.0')
        self.line(1, TEXT, 'SN64 build 0.1 (0x0001)')


def splash_pictures(source):
    """{name: (width, height, palette, pixels)} from the generated C file."""
    out = {}
    for m in re.finditer(r'const sn64_splash_image_t sn64_splash_(\w+) = \{ (\d+), (\d+), (\d+), ', source):
        name, w, h = m.group(1), int(m.group(2)), int(m.group(3))
        pal = re.search(r'%s_palette\[\d+\]\[3\] = \{(.*?)\};' % name, source, re.S).group(1)
        pal = [tuple(int(v) for v in c.split(',')) for c in re.findall(r'\{(\d+,\d+,\d+)\}', pal)]
        px = re.search(r'%s_pixels\[\d+\] = \{(.*?)\};' % name, source, re.S).group(1)
        px = [int(v) for v in re.findall(r'\d+', px)]
        assert len(px) == w * h, (name, len(px), w, h)
        out[name] = (w, h, pal, px)
    return out


def splash(title, picture):
    """The picture centred on a black 320 x 240 screen at full brightness, as sn64_splash_draw does."""
    w, h, pal, px = picture
    s = Screen(title)
    small = Image.new('RGB', (W, H), (0, 0, 0))
    art = Image.new('RGB', (w, h))
    art.putdata([pal[v] for v in px])
    small.paste(art, ((W - w) // 2, (H - h) // 2))
    s.im = small.resize((W * SCALE, H * SCALE), Image.NEAREST)
    return s


def credits_roll(source):
    """[(text, kind), ...] from the generated C file."""
    block = re.search(r'sn64_credits_lines\[\]\s*=\s*\{(.*?)\n\};', source, re.S).group(1)
    lines = [m.group(1).replace('\\"', '"') for m in re.finditer(r'^\s*"((?:[^"\\]|\\.)*)",', block, re.M)]
    kinds = [int(v) for v in re.findall(r'\d+', re.search(r'sn64_credits_kind\[\]\s*=\s*\{(.*?)\};', source, re.S).group(1))]
    assert len(lines) == len(kinds), (len(lines), len(kinds))
    return list(zip(lines, kinds))


CREDITS_TOP, CREDITS_BOTTOM = 22, 228              # src/main.c


def credits_end(roll):
    middle = CREDITS_TOP + (CREDITS_BOTTOM - CREDITS_TOP - CELL) // 2
    return CREDITS_BOTTOM + (len(roll) - 1) * ROW - middle


def credits(title, roll, scroll):
    """The roll at one scroll position, as draw_credits() and sn64_credits_visible() place it."""
    s = Screen(title)
    for i, (text, kind) in enumerate(roll):
        y = CREDITS_BOTTOM + i * ROW - scroll
        if y < CREDITS_TOP or y + CELL > CREDITS_BOTTOM or not text:
            continue
        colour = HI if kind == 1 else DIM if kind == 2 else TEXT
        for k, ch in enumerate(text):
            s.d.text(((16 + k * CELL + CELL / 2) * SCALE, (y + CELL / 2) * SCALE), ch, font=s.f, fill=colour, anchor='mm')
    s.line(22, DIM, 'A: faster   B: back')
    return s


def sheet_of(screens, cols):
    gap, cap = 30, 60
    rows = (len(screens) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * W * SCALE + (cols + 1) * gap, rows * (H * SCALE + cap) + gap), (0x28, 0x28, 0x2C))
    d = ImageDraw.Draw(sheet)
    try:
        cf = ImageFont.truetype('arial.ttf', 30)
    except OSError:
        cf = ImageFont.load_default(30)
    for i, s in enumerate(screens):
        x = gap + (i % cols) * (W * SCALE + gap)
        y = gap + (i // cols) * (H * SCALE + cap)
        d.text((x, y), s.title + ' (mock-up)', font=cf, fill=(0xD0, 0xD0, 0xD0))
        sheet.paste(s.im, (x, y + cap - 14))
    return sheet


def main_menu(check_summary, summary_colour, cursor=0, compat=False, message=''):
    s = Screen('Main menu')
    s.header()
    s.line(2, TEXT, 'Status 0x0003  seq 512  OFF')
    s.line(4, TEXT, 'Cartridge: off')
    s.line(5, TEXT, 'Region: not decided yet')
    items = ['Start SNES cartridge', 'Controller mapping', 'Compatibility mode: ' + ('ON' if compat else 'off'),
             'Status / diagnostics', 'Power down cartridge', 'Credits']
    for i, name in enumerate(items):
        s.line(6 + i, HI if i == cursor else TEXT, ('> ' if i == cursor else '  ') + name)
    s.line(13, WARN, message)
    if compat:
        s.line(16, WARN, 'Compatibility mode: games run slower')
    s.line(20, DIM, 'Up/Down select  A choose  B back')
    return s


def compat_confirm(title, lines):
    """The confirmation screen as draw_compat() lays it out: text from row 3, the two figures in the warning colour."""
    s = Screen(title)
    s.header()
    for i, text in enumerate(lines):
        s.line(3 + i, HI if i == 0 else WARN if i in (11, 12) else TEXT, text)
    s.line(21, DIM, 'A: turn it on        B: cancel')
    return s


def service(check_summary, summary_colour, lock=('no game shown yet', 'Slow 0.00 %  off +0  lost 0', '-')):
    s = Screen('Service screen (Status / diagnostics, then Z)')
    s.header()
    s.line(3, HI, 'Service: cartridge check')
    s.line(5, TEXT, 'The check runs whenever a cartridge')
    s.line(6, TEXT, 'is started. These are its test tools.')
    s.line(8, TEXT, 'Mode: enforce')
    s.line(9, DIM, 'a failed check stops the start')
    s.line(11, summary_colour, 'Last check: ' + check_summary)
    s.line(14, HI, 'Frame lock: ' + lock[0])
    s.line(15, TEXT, lock[1])
    s.line(16, DIM, 'Console timing: ' + lock[2])
    s.line(17, DIM, 'Readout over the game: off')
    s.line(19, DIM, 'A: check the cartridge now, no power')
    s.line(20, DIM, 'L or R: change the check mode')
    s.line(21, DIM, 'C-up: readout over the game')
    s.line(22, DIM, 'B: back')
    return s


def alert(title, lines, good, detail, fault=None):
    s = Screen(title)
    s.header()
    for i, text in enumerate(lines):
        s.line(3 + i, (HI if good else WARN) if i == 0 else TEXT, text)
    s.line(13, DIM, detail)
    if fault:
        s.line(14, DIM, fault)
    s.line(20, DIM, 'A or B: back to the menu')
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out-dir', type=Path, default=HERE.parents[2] / 'docs/design/img')
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    src = (HERE.parent / 'src/sn64_cartcheck.c').read_text(encoding='utf-8')
    screens = [
        main_menu('none yet', DIM),
        alert('After Start with the cartridge in backwards', alert_lines(src, 'lines_backwards'), False, 'Rail test 0.43 V, check enforce', 'Fault code 0x01'),
        service('ok, 0.79 V', TEXT),
        alert('Short on the supply', alert_lines(src, 'lines_short'), False, 'Rail test 0.00 V, check enforce', 'Fault code 0x01'),
    ]
    sheet = sheet_of(screens, 2)
    sheet.save(args.out_dir / 'cart-check-screens.png')
    print('wrote cart-check-screens.png', sheet.size)
    pictures = splash_pictures((HERE.parent / 'src/sn64_splash_data.c').read_text(encoding='utf-8'))
    order = [splash('1. At start-up: SN64 logo', pictures['sn64']),
             splash('2. Then: FantomZap logo', pictures['fantomzap']),
             main_menu('none yet', DIM)]
    order[2].title = '3. Then the menu'
    sheet = sheet_of(order, 3)
    sheet.save(args.out_dir / 'splash-screens.png')
    print('wrote splash-screens.png', sheet.size)
    # Compatibility mode: the menu row, the confirmation with its figures, the menu with it on, and
    # the service screen's frame-lock lines as they would read after a game in normal mode.
    made = HERE.parents[2] / 'build/n64-bootstrap/host/compat-screen.txt'
    if not made.exists():
        raise SystemExit('run `make test-framelock` first: it writes ' + str(made))
    text = {}
    for row in made.read_text(encoding='utf-8').splitlines():
        key, _, body = row.partition('|')
        text.setdefault(key, []).append(body)
    screens = [
        main_menu('none yet', DIM, cursor=2),
        compat_confirm('Choosing it asks first (N64 or M64, 60 Hz)', text['ntsc']),
        main_menu('none yet', DIM, cursor=2, compat=True, message='Compatibility mode on'),
        compat_confirm('The same on a 50 Hz console', text['pal']),
        service('ok, 0.79 V', TEXT, ('locked', 'Slow 0.04 %  off +1  lost 0', 'Super NES')),
        service('ok, 0.79 V', TEXT, ('locked', 'Slow 0.45 %  off -1  lost 0', 'its own')),
    ]
    screens[0].title = 'Main menu: the new row'
    screens[2].title = 'After A: it is on, and says so'
    screens[4].title = 'Service screen after a game, normal'
    screens[5].title = 'Service screen after a game, compatibility'
    sheet = sheet_of(screens, 2)
    sheet.save(args.out_dir / 'compat-screens.png')
    print('wrote compat-screens.png', sheet.size)
    # Credits roll: the menu row, the roll as it opens, part of the way through, and where it stops.
    roll = credits_roll((HERE.parent / 'src/sn64_credits_data.c').read_text(encoding='utf-8'))
    end = credits_end(roll)
    screens = [
        main_menu('none yet', DIM, cursor=5),
        credits('The roll opens', roll, CREDITS_BOTTOM - CREDITS_TOP),
        credits('Part of the way through', roll, CREDITS_BOTTOM - CREDITS_TOP + 37 * ROW),
        credits('Where it stops', roll, end),
    ]
    screens[0].title = 'Main menu: Credits'
    sheet = sheet_of(screens, 2)
    sheet.save(args.out_dir / 'credits-screens.png')
    print('wrote credits-screens.png', sheet.size)


if __name__ == '__main__':
    main()
