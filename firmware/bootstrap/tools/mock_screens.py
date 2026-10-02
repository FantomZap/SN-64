"""Draw mock-ups of the boot menu's screens: the two splash screens, the main menu and Settings,
the colour themes, the controller mapping screen, the cartridge-check screens, the
compatibility-mode screens, About and the credits roll.

What the code draws is not copied by hand: `make test-menuview` and `make test-mapscreen` run the
code the ROM runs (src/sn64_menuview.c, src/sn64_theme.c, src/sn64_mapscreen.c,
src/sn64_padview.c) and write each screen's pixels and its text with positions to
build/n64-bootstrap/host/screens/; here the pixels are enlarged and the text is set in this tool's
font. That covers the main menu, Settings and the mapping screen whole, and of every text screen
the background, the small title and the colours of its theme. The About text is written by the
same test with the code under test.

The lines of the other text screens are laid out here as src/main.c lays them out (8x8 character
cells at x = 16, y = 12 + 10 * row on a 320 x 240 screen). Their wording is read from the sources
where it can be: the alerts from src/sn64_cartcheck.c, the compatibility-mode confirmation from
the file the host test writes (`make test-framelock` -> build/n64-bootstrap/host/compat-screen.txt,
numbers included), the credits roll from src/sn64_credits_data.c, laid out as src/sn64_credits.c
lays it out. The splash pictures are read from src/sn64_splash_data.c, pixel for pixel as the ROM
holds them.

This is a drawing, not a capture: the menu has not run on a console or an emulator yet, and the
console's own font looks different.

  python tools/mock_screens.py        writes docs/design/img/cart-check-screens.png, splash-screens.png,
                                      menu-screens.png, theme-screens.png, theme-other-screens.png,
                                      mapping-screens.png, compat-screens.png and credits-screens.png
"""
import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SCALE = 3
W, H, CELL, ROW = 320, 240, 8, 10
MADE = HERE.parents[2] / 'build/n64-bootstrap/host/screens'
THEMES = 6


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


def rgb(hex6):
    return tuple(int(hex6[i:i + 2], 16) for i in (0, 2, 4))


def made_text(name):
    """[(x, y, colour, text), ...] of a screen the code under test drew."""
    out = []
    for row in (MADE / (name + '.txt')).read_text(encoding='utf-8').splitlines():
        x, y, colour, text = row.split(' ', 3)
        out.append((int(x), int(y), rgb(colour), text))
    return out


def theme_colours(k):
    """{'text': ..., 'dim': ..., 'hi': ..., 'warn': ..., 'name': ...} of theme k, as src/sn64_theme.c has them."""
    rows = made_text('menu-colours-%d' % k)
    out = {text: colour for _, _, colour, text in rows[:4]}
    out['name'] = rows[4][3]
    return out


class Screen:
    """A screen of the menu, three times its size. `base` is a frame the code under test drew
    (its pixels, and its text unless `words` is False); without one it is black."""

    def __init__(self, title, base=None, theme=0, words=True):
        self.title = title
        self.f = font()
        self.col = theme_colours(theme)
        if base:
            small = Image.open(MADE / (base + '.ppm')).convert('RGB')
        else:
            small = Image.new('RGB', (W, H), (0, 0, 0))
        self.im = small.resize((W * SCALE, H * SCALE), Image.NEAREST)
        self.d = ImageDraw.Draw(self.im)
        if base and words:
            for x, y, colour, text in made_text(base):
                self.text(x, y, colour, text)

    def text(self, x, y, colour, text):
        """Text in 8 x 8 cells with the top left corner at (x, y), as graphics_draw_text places it."""
        for i, ch in enumerate(text):
            self.d.text(((x + i * CELL + CELL / 2) * SCALE, (y + CELL / 2) * SCALE), ch, font=self.f, fill=colour, anchor='mm')

    def line(self, row, kind, text):
        """line() of src/main.c: `kind` is 'text', 'dim', 'hi' or 'warn'."""
        assert len(text) <= 38, (len(text), text)        # 38 columns fit the screen from x = 16
        assert row >= 2, row                             # rows 0 and 1 are the small title's
        self.text(16, 12 + row * ROW, self.col[kind], text)


def made(title, name):
    """A screen the code under test drew whole: the main menu, Settings, the mapping screen."""
    return Screen(title, name)


def text_screen(title, theme=0):
    """The start of a text screen: the theme's background with the small title, as draw_header() gives it."""
    return Screen(title, 'menu-text-%d' % theme, theme, words=False)


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


def main_c_number(name):
    """A `#define <name> <number>` of src/main.c."""
    return int(re.search(r'^#define %s\s+(\d+)' % name, (HERE.parent / 'src/main.c').read_text(encoding='utf-8'), re.M).group(1))


CREDITS_TOP, CREDITS_BOTTOM = main_c_number('CREDITS_TOP'), main_c_number('CREDITS_BOTTOM')


def credits_end(roll):
    middle = CREDITS_TOP + (CREDITS_BOTTOM - CREDITS_TOP - CELL) // 2
    return CREDITS_BOTTOM + (len(roll) - 1) * ROW - middle


def credits(title, roll, scroll, theme=0):
    """The roll at one scroll position, as draw_credits() and sn64_credits_visible() place it."""
    s = text_screen(title, theme)
    for i, (text, kind) in enumerate(roll):
        y = CREDITS_BOTTOM + i * ROW - scroll
        if y < CREDITS_TOP or y + CELL > CREDITS_BOTTOM or not text:
            continue
        s.text(16, y, s.col['hi' if kind == 1 else 'dim' if kind == 2 else 'text'], text)
    s.line(22, 'dim', 'A: faster   B: back')
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


def about(title, name='about', theme=0):
    """draw_about(): the lines the code under test wrote, from row 2."""
    s = text_screen(title, theme)
    kinds = ['text', 'dim', 'hi', 'warn']               # SN64_LINE_* of src/sn64_menuview.h
    for i, row in enumerate((MADE / (name + '.txt')).read_text(encoding='utf-8').splitlines()):
        kind, _, text = row.partition('|')
        s.line(2 + i, kinds[int(kind)], text)
    s.line(22, 'dim', 'B: back')
    return s


def waiting(title, theme=0):
    """draw_wait() while a cartridge is being started."""
    s = text_screen(title, theme)
    s.line(4, 'hi', 'Starting the cartridge...')
    s.line(6, 'text', 'Sequencer: 5V RAMP')
    s.line(20, 'dim', 'All four C buttons: back to the menu')
    return s


def compat_confirm(title, lines, theme=0):
    """The confirmation screen as draw_compat() lays it out: text from row 3, the two figures in the warning colour."""
    s = text_screen(title, theme)
    for i, text in enumerate(lines):
        s.line(3 + i, 'hi' if i == 0 else 'warn' if i in (11, 12) else 'text', text)
    s.line(21, 'dim', 'A: turn it on        B: cancel')
    return s


def service(check_summary, summary_kind, lock=('no game shown yet', 'Slow 0.00 %  off +0  lost 0', '-'), theme=0):
    s = text_screen('Service screen (Settings, Status, then Z)', theme)
    s.line(3, 'hi', 'Service: cartridge check')
    s.line(5, 'text', 'The check runs whenever a cartridge')
    s.line(6, 'text', 'is started. These are its test tools.')
    s.line(8, 'text', 'Mode: enforce')
    s.line(9, 'dim', 'a failed check stops the start')
    s.line(11, summary_kind, 'Last check: ' + check_summary)
    s.line(14, 'hi', 'Frame lock: ' + lock[0])
    s.line(15, 'text', lock[1])
    s.line(16, 'dim', 'Console timing: ' + lock[2])
    s.line(17, 'dim', 'Readout over the game: off')
    s.line(19, 'dim', 'A: check the cartridge now, no power')
    s.line(20, 'dim', 'L or R: change the check mode')
    s.line(21, 'dim', 'C-up: readout over the game')
    s.line(22, 'dim', 'B: back')
    return s


def alert(title, lines, good, detail, fault=None, theme=0):
    s = text_screen(title, theme)
    for i, text in enumerate(lines):
        s.line(3 + i, ('hi' if good else 'warn') if i == 0 else 'text', text)
    s.line(13, 'dim', detail)
    if fault:
        s.line(14, 'dim', fault)
    s.line(20, 'dim', 'A or B: back to the menu')
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out-dir', type=Path, default=HERE.parents[2] / 'docs/design/img')
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    host = HERE.parents[2] / 'build/n64-bootstrap/host'
    for needed, target in (('menu-main-0.ppm', 'test-menuview'), ('map-open.ppm', 'test-mapscreen')):
        if not (MADE / needed).exists():
            raise SystemExit('run `make %s` first: it writes %s' % (target, MADE))

    def write(name, screens, cols):
        sheet = sheet_of(screens, cols)
        sheet.save(args.out_dir / name)
        print('wrote', name, sheet.size)

    src = (HERE.parent / 'src/sn64_cartcheck.c').read_text(encoding='utf-8')
    backwards, short = alert_lines(src, 'lines_backwards'), alert_lines(src, 'lines_short')
    write('cart-check-screens.png', [
        made('Main menu', 'menu-main-0'),
        alert('After Play with the cartridge in backwards', backwards, False, 'Rail test 0.43 V, check enforce', 'Fault code 0x01'),
        service('ok, 0.79 V', 'text'),
        alert('Short on the supply', short, False, 'Rail test 0.00 V, check enforce', 'Fault code 0x01'),
    ], 2)
    pictures = splash_pictures((HERE.parent / 'src/sn64_splash_data.c').read_text(encoding='utf-8'))
    write('splash-screens.png', [
        splash('1. At start-up: SN64 logo', pictures['sn64']),
        splash('2. Then: FantomZap logo', pictures['fantomzap']),
        made('3. Then the menu', 'menu-main-0'),
    ], 3)
    # The main menu and what is under Settings; what Play shows; the menu brought up from a game.
    write('menu-screens.png', [
        made('Main menu: the logo, four rows', 'menu-main-0'),
        made('Settings holds the rest', 'menu-settings-compat'),
        about('Settings, About: versions and the odd facts'),
        waiting('After Play'),
        made('All four C in a game: the menu again', 'menu-main-running'),
        made('No SN64 answering', 'menu-main-missing'),
    ], 3)
    # The themes: the main menu in each, then other screens in some of them.
    names = [theme_colours(k)['name'] for k in range(THEMES)]
    write('theme-screens.png', [made('Theme: %s%s' % (names[k], ' (as it starts)' if k == 0 else ''), 'menu-main-%d' % k)
                                for k in range(THEMES)], 3)
    roll = credits_roll((HERE.parent / 'src/sn64_credits_data.c').read_text(encoding='utf-8'))
    write('theme-other-screens.png', [
        made('Settings, Theme: Left and Right change it', 'menu-settings-grape'),
        made('Controller mapping in Jungle', 'map-theme-3'),
        made('Controller mapping in Ice', 'map-theme-4'),
        about('About in Fire', theme=5),
        alert('An alert in Smoke', backwards, False, 'Rail test 0.43 V, check enforce', 'Fault code 0x01', theme=1),
        credits('The credits in Grape', roll, CREDITS_BOTTOM - CREDITS_TOP, theme=2),
    ], 3)
    # Controller mapping: drawn by the code under test.
    write('mapping-screens.png', [
        made('Controller mapping as it opens', 'map-open'),
        made('The stick up and right: two directions', 'map-stick'),
        made('A on the stick row: how far to push', 'map-stick-choices'),
        made('A held: A lights on both', 'map-a'),
        made('Cursor on Z, Z held: Select lights', 'map-z'),
        made('A on a row: what should Z give?', 'map-choices'),
        made('The list of controllers', 'map-list'),
        made('Another controller; the list scrolled', 'map-other'),
        made('A changed mapping, C-Up held', 'map-changed'),
        made('All four C held: the menu shortcut', 'map-shortcut'),
    ], 2)
    # Compatibility mode: the Settings row, the confirmation with its figures, Settings with it on,
    # the main menu saying so, and the service screen's frame-lock lines as they would read after a
    # game in normal mode and in compatibility mode.
    compat = host / 'compat-screen.txt'
    if not compat.exists():
        raise SystemExit('run `make test-framelock` first: it writes ' + str(compat))
    text = {}
    for row in compat.read_text(encoding='utf-8').splitlines():
        key, _, body = row.partition('|')
        text.setdefault(key, []).append(body)
    screens = [
        made('Settings: the row', 'menu-settings-compat'),
        compat_confirm('Choosing it asks first (N64 or M64, 60 Hz)', text['ntsc']),
        made('After A: it is on, and says so', 'menu-settings-compat-on'),
        made('The main menu says so too', 'menu-main-compat'),
        compat_confirm('The same on a 50 Hz console', text['pal']),
        service('ok, 0.79 V', 'text', ('locked', 'Slow 0.04 %  off +1  lost 0', 'Super NES')),
        service('ok, 0.79 V', 'text', ('locked', 'Slow 0.45 %  off -1  lost 0', 'its own')),
    ]
    screens[5].title = 'Service screen after a game, normal'
    screens[6].title = 'Service screen after a game, compatibility'
    write('compat-screens.png', screens, 2)
    # Credits roll: the Settings row, the roll as it opens, part of the way through, and where it stops.
    end = credits_end(roll)
    write('credits-screens.png', [
        made('Settings: Credits', 'menu-settings-credits'),
        credits('The roll opens', roll, CREDITS_BOTTOM - CREDITS_TOP),
        credits('Part of the way through', roll, CREDITS_BOTTOM - CREDITS_TOP + 37 * ROW),
        credits('Where it stops', roll, end),
    ], 2)


if __name__ == '__main__':
    main()
