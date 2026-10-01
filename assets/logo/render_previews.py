"""Preview sheet for the SN64 logo files. Needs PyMuPDF (renders the SVG) and Pillow (lays out the sheet).

    python assets/logo/make_logo.py
    python assets/logo/render_previews.py
"""
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageFont

D = Path(__file__).resolve().parent
PAPER, NIGHT, SHELL = (255, 255, 255), (29, 29, 35), (150, 152, 156)
INK, GREY = (30, 30, 36), (105, 105, 115)
FB = ImageFont.truetype('arialbd.ttf', 40)
F = ImageFont.truetype('arial.ttf', 28)
FS = ImageFont.truetype('arial.ttf', 24)


def render(name, height):
    """SVG file -> RGBA image of the given height (transparent background)."""
    doc = pymupdf.open(str(D / name))
    page = doc[0]
    z = height / page.rect.height
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=True)
    return Image.frombytes('RGBA', (pix.width, pix.height), pix.samples)


def on(img, bg):
    out = Image.new('RGB', img.size, bg)
    out.paste(img, (0, 0), img)
    return out


def relief(name, height, base=SHELL):
    """One-colour file shown as raised plastic: highlight up-left, shadow down-right."""
    mask = render(name, height).getchannel('A')
    w, h = mask.size
    out = Image.new('RGB', (w + 12, h + 12), base)
    for dx, dy, col in ((4, 4, (96, 98, 102)), (-3, -3, (214, 216, 220)), (0, 0, (168, 170, 175))):
        out.paste(Image.new('RGB', (w, h), col), (6 + dx, 6 + dy), mask)
    return out


def tile(img, w, h, bg):
    out = Image.new('RGB', (w, h), bg)
    out.paste(img, ((w - img.size[0]) // 2, (h - img.size[1]) // 2))
    return out


def row(title, note, base, hgt):
    """One option: colour on white, colour on dark, one colour, raised plastic."""
    tw, th = 560, 250
    dark = f'sn64-{base}-on-dark.svg' if (D / f'sn64-{base}-on-dark.svg').exists() else f'sn64-{base}.svg'
    tiles = [tile(on(render(f'sn64-{base}.svg', hgt), PAPER), tw, th, PAPER),
             tile(on(render(dark, hgt), NIGHT), tw, th, NIGHT),
             tile(on(render(f'sn64-{base}-mono.svg', hgt), PAPER), tw, th, PAPER),
             tile(relief(f'sn64-{base}-mono.svg', hgt), tw, th, SHELL)]
    out = Image.new('RGB', (4 * tw + 5 * 20, th + 120), (238, 238, 242))
    d = ImageDraw.Draw(out)
    d.text((20, 14), title, font=FB, fill=INK)
    d.text((20, 66), note, font=FS, fill=GREY)
    for i, t in enumerate(tiles):
        out.paste(t, (20 + i * (tw + 20), 108))
    return out


def sheet():
    rows = [row('A  Buttons', 'Four buttons on two slanted pads, like a controller. Reads SN over 64. Good as an icon.', 'buttons', 170),
            row('B  Wordmark', 'Heavy slanted letters with a four-colour bar. Good for a header or the front of the cap.', 'wordmark', 120),
            row('A + B  together', 'Buttons and letters side by side: the full logo.', 'lockup', 130),
            row('C  Badge', 'The same letters in a ring. The plainest one to emboss.', 'badge', 150)]
    w = rows[0].size[0]
    head = 150
    out = Image.new('RGB', (w, head + sum(r.size[1] for r in rows) + 30), (238, 238, 242))
    d = ImageDraw.Draw(out)
    d.text((20, 22), 'SN64 logo options', font=ImageFont.truetype('arialbd.ttf', 54), fill=INK)
    tw = 560
    for i, s in enumerate(('colour', 'colour on dark', 'one colour', 'one colour, raised (embossing)')):
        d.text((20 + i * (tw + 20) + tw / 2, 104), s, font=F, fill=GREY, anchor='ma')
    y = head
    for r in rows:
        out.paste(r, (0, y))
        y += r.size[1]
    out.save(D / 'sn64-logo-options.png', optimize=True)
    return out.size


if __name__ == '__main__':
    print('sheet', sheet())
