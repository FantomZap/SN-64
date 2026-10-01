"""Preview sheet for the SN64 logo files. Needs PyMuPDF (renders the SVG) and Pillow (lays out the sheet).

    python assets/logo/make_logo.py
    python assets/logo/render_previews.py
"""
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

D = Path(__file__).resolve().parent
PAPER, NIGHT, SHELL, PAGE = (255, 255, 255), (29, 29, 35), (150, 152, 156), (238, 238, 242)
INK, GREY = (30, 30, 36), (105, 105, 115)
FT = ImageFont.truetype('arialbd.ttf', 54)
FB = ImageFont.truetype('arialbd.ttf', 36)
F = ImageFont.truetype('arial.ttf', 28)
GAP = 20


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


def tile(img, w, h, bg, label):
    """Picture centred on a w x h tile with a caption underneath."""
    out = Image.new('RGB', (w, h + 46), PAGE)
    out.paste(Image.new('RGB', (w, h), bg), (0, 0))
    out.paste(img, ((w - img.size[0]) // 2, (h - img.size[1]) // 2))
    ImageDraw.Draw(out).text((w / 2, h + 8), label, font=F, fill=GREY, anchor='ma')
    return out


def sheet():
    tw, th, hgt = 1000, 380, 270
    logo = [tile(on(render('sn64-logo.svg', hgt), PAPER), tw, th, PAPER, 'colour'),
            tile(on(render('sn64-logo-on-dark.svg', hgt), NIGHT), tw, th, NIGHT, 'colour on dark'),
            tile(on(render('sn64-logo-mono.svg', hgt), PAPER), tw, th, PAPER, 'one colour'),
            tile(relief('sn64-logo-mono.svg', hgt), tw, th, SHELL, 'one colour, raised (embossing)'),
            tile(on(render('sn64-logo-mono-plain.svg', hgt), PAPER), tw, th, PAPER, 'one colour, plain buttons: for small embossing'),
            tile(relief('sn64-logo-mono-plain.svg', hgt), tw, th, SHELL, 'plain buttons, raised')]
    pw, ph = (2 * tw + GAP - 2 * GAP) // 3, 230
    parts = [tile(on(render('sn64-lockup.svg', 110), PAPER), pw, ph, PAPER, 'without the ring'),
             tile(on(render('sn64-buttons.svg', 170), PAPER), pw, ph, PAPER, 'buttons alone, for an icon'),
             tile(on(render('sn64-wordmark.svg', 130), PAPER), pw, ph, PAPER, 'letters alone'),
             tile(on(render('sn64-lockup-mono.svg', 110), PAPER), pw, ph, PAPER, 'one colour'),
             tile(on(render('sn64-buttons-mono.svg', 170), PAPER), pw, ph, PAPER, 'one colour'),
             tile(on(render('sn64-wordmark-mono.svg', 130), PAPER), pw, ph, PAPER, 'one colour')]
    width = 2 * tw + 3 * GAP
    y_logo = 110
    y_parts = y_logo + 3 * (th + 46 + GAP) + 70
    height = y_parts + 2 * (ph + 46 + GAP) + 10
    out = Image.new('RGB', (width, height), PAGE)
    d = ImageDraw.Draw(out)
    d.text((GAP, 24), 'SN64 logo', font=FT, fill=INK)
    for i, t in enumerate(logo):
        out.paste(t, (GAP + (i % 2) * (tw + GAP), y_logo + (i // 2) * (th + 46 + GAP)))
    d.text((GAP, y_parts - 56), 'The same parts on their own, for small or narrow places', font=FB, fill=INK)
    for i, t in enumerate(parts):
        out.paste(t, (GAP + (i % 3) * (pw + GAP), y_parts + (i // 3) * (ph + 46 + GAP)))
    out.save(D / 'sn64-logo-sheet.png', optimize=True)
    return out.size


if __name__ == '__main__':
    print('sheet', sheet())
