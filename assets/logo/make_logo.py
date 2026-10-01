"""SN64 logo: writes the SVG files in this folder. Pure Python, no dependencies.

    python assets/logo/make_logo.py

Original artwork for SN64. It borrows the feel of early-1990s console design (heavy geometric
letters, an italic slant, four button colours, a controller's slanted button pads) and copies no
Nintendo logo, typeface or trademark. The letters S, N, 6 and 4 are drawn here as outlines, so the
files need no font.

The logo (the choice of the owner, 2026-10-01) is the button pads and the letters inside a ring,
with the pads about the height of the letters. The lockup (no ring), the buttons and the wordmark
are the same parts on their own.

Every piece has a colour version and a one-colour version. One-colour files use a single black
fill on a transparent background: black is the raised (or printed) part, so they can be used for
embossing, silkscreen or a stamp. The "plain" logo leaves the characters off the buttons so it can
be embossed small.
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent
H = 100.0                 # cap height of the letter drawings
STROKE = 20.0             # stem thickness of the letters
SLANT = math.tan(math.radians(12))

PAL = {
    'green': '#1E9B55', 'blue': '#2449B8', 'yellow': '#F4B400', 'red': '#E0352B',
    'ink': '#25252C', 'pad': '#D8D6DD', 'white': '#FFFFFF', 'paper': '#FFFFFF', 'night': '#1D1D23',
}
ORDER = ('green', 'blue', 'yellow', 'red')      # S, N, 6, 4


def n(v):
    """Short number for SVG."""
    s = f'{v:.3f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


# ---------------------------------------------------------------- letters (upright, 0..W x 0..100)
def glyph_s(s=STROKE):
    ro, ri = (H + s) / 4, (H - 3 * s) / 4
    w = 2 * ro
    d = (f'M{n(w)},0 H{n(ro)} A{n(ro)},{n(ro)} 0 0 0 {n(ro)},{n(2 * ro)} '
         f'A{n(ri)},{n(ri)} 0 0 1 {n(ro)},{n(2 * ro + 2 * ri)} H0 V{n(H)} H{n(ro)} '
         f'A{n(ro)},{n(ro)} 0 0 0 {n(ro)},{n(H - 2 * ro)} A{n(ri)},{n(ri)} 0 0 1 {n(ro)},{n(s)} H{n(w)} Z')
    return d, w


def glyph_n(s=STROKE):
    w, dw = 3.5 * s, 1.2 * s
    k = (w - dw) / H                      # slope of the diagonal
    y_r, y_l = (w - s - dw) / k, s / k    # where the diagonal meets the right and the left stem
    d = (f'M0,0 H{n(dw)} L{n(w - s)},{n(y_r)} V0 H{n(w)} V{n(H)} H{n(w - dw)} '
         f'L{n(s)},{n(y_l)} V{n(H)} H0 Z')
    return d, w


def glyph_6(s=STROKE):
    ro, ri = (H + s) / 4, (H - 3 * s) / 4
    w = 2 * ro
    xt = 0.9 * w                          # end of the top stroke
    yj = H - ro - math.sqrt(ro * ro - (ro - s) ** 2)
    d = (f'M{n(xt)},0 V{n(s)} H{n(ro)} A{n(ri)},{n(ri)} 0 0 0 {n(s)},{n(ro)} V{n(yj)} '
         f'A{n(ro)},{n(ro)} 0 1 1 0,{n(H - ro)} V{n(ro)} A{n(ro)},{n(ro)} 0 0 1 {n(ro)},0 Z '
         f'M{n(ro)},{n(H - ro - ri)} A{n(ri)},{n(ri)} 0 1 0 {n(ro)},{n(H - ro + ri)} '
         f'A{n(ri)},{n(ri)} 0 1 0 {n(ro)},{n(H - ro - ri)} Z')
    return d, w


def glyph_4(s=STROKE):
    x0, x1 = 2 * s, 3 * s                 # stem
    y0, y1 = 0.58 * H, 0.58 * H + s       # bar
    w = x1 + 0.4 * s
    apex = x0 - 0.2 * s
    dw = 1.2 * s
    k = apex / y0                         # diagonal: x falls by k per unit of y
    yc = (apex + dw - x0) / k             # top of the counter on the stem
    xc = apex + dw - k * y0               # left end of the counter on the bar
    d = (f'M{n(apex)},0 H{n(x1)} V{n(y0)} H{n(w)} V{n(y1)} H{n(x1)} V{n(H)} H{n(x0)} V{n(y1)} H0 V{n(y0)} Z '
         f'M{n(x0)},{n(yc)} V{n(y0)} H{n(xc)} Z')
    return d, w


GLYPHS = [glyph_s, glyph_n, glyph_6, glyph_4]
GAPS = [8.0, 8.0, 7.0]                    # after S, N, 6 (7 % of the letter height is the tightest gap)


def path(d, fill, matrix=None):
    t = '' if matrix is None else ' transform="matrix(' + ' '.join(n(v) for v in matrix) + ')"'
    return f'<path d="{d}" fill="{fill}" fill-rule="evenodd"{t}/>'


def rect_skew(x, y, w, h, fill, k, base):
    """Parallelogram: a w x h box at (x, y), sheared like the letters around the baseline y = base."""
    pts = [(x + k * (base - y), y), (x + w + k * (base - y), y), (x + w + k * (base - y - h), y + h), (x + k * (base - y - h), y + h)]
    return '<path d="M' + ' L'.join(f'{n(px)},{n(py)}' for px, py in pts) + f' Z" fill="{fill}"/>'


# ---------------------------------------------------------------- wordmark
def wordmark(x, y, size, fills, slant=SLANT, bar=None):
    """Letters with their top-left at (x, y), cap height `size`. fills: 4 colours. bar: None, or 4 colours.
    Returns (elements, width, height)."""
    sc = size / H
    out, cx, spans = [], 0.0, []
    for i, g in enumerate(GLYPHS):
        d, w = g()
        # x' = sc * (gx + slant * (H - gy)) + x + cx * sc ; y' = sc * gy + y
        out.append(path(d, fills[i], (sc, 0, -sc * slant, sc, x + sc * (cx + slant * H), y)))
        spans.append((cx, w))
        cx += w + (GAPS[i] if i < 3 else 0)
    width = sc * (cx + slant * H)
    height = size
    if bar:
        by, bh = H + 14, 12
        for (gx, w), c in zip(spans, bar):
            out.append(rect_skew(x + sc * gx, y + sc * by, sc * w, sc * bh, c, slant, y + sc * H))
        height = sc * (by + bh)
    return out, width, height


# ---------------------------------------------------------------- button pads
PX, PY, R_BTN, R_PAD = 54.0, 38.0, 22.0, 28.0
BTN = [(-PX, 0.0), (0.0, -PY), (0.0, PY), (PX, 0.0)]          # S left, N top, 6 bottom, 4 right


def stadium(c1, c2, r):
    ux, uy = c2[0] - c1[0], c2[1] - c1[1]
    ln = math.hypot(ux, uy)
    nx, ny = -uy / ln * r, ux / ln * r
    p1, p2 = (c1[0] + nx, c1[1] + ny), (c2[0] + nx, c2[1] + ny)
    p3, p4 = (c2[0] - nx, c2[1] - ny), (c1[0] - nx, c1[1] - ny)
    return (f'M{n(p1[0])},{n(p1[1])} L{n(p2[0])},{n(p2[1])} A{n(r)},{n(r)} 0 0 0 {n(p3[0])},{n(p3[1])} '
            f'L{n(p4[0])},{n(p4[1])} A{n(r)},{n(r)} 0 0 0 {n(p1[0])},{n(p1[1])} Z')


def circle(c, r):
    return (f'M{n(c[0] - r)},{n(c[1])} A{n(r)},{n(r)} 0 1 0 {n(c[0] + r)},{n(c[1])} '
            f'A{n(r)},{n(r)} 0 1 0 {n(c[0] - r)},{n(c[1])} Z')


def buttons(x, y, size, mono=None, pad=PAL['pad'], letters=True):
    """Button pads with their box's top-left at (x, y) and height `size`. mono: None or one colour.
    letters=False leaves the characters off the buttons (one colour only, for small embossing).
    Returns (elements, width, height)."""
    half_w, half_h = PX + R_PAD, PY + R_PAD
    sc = size / (2 * half_h)
    cs = [(x + sc * (bx + half_w), y + sc * (by + half_h)) for bx, by in BTN]
    out = []
    letter = 0.27 * sc * (R_BTN / 22.0)
    for a, b in ((0, 1), (2, 3)):
        d = stadium(cs[a], cs[b], sc * R_PAD)
        if mono:
            d += ' ' + circle(cs[a], sc * R_BTN) + ' ' + circle(cs[b], sc * R_BTN)
        out.append(path(d, mono or pad))
    for i, c in enumerate(cs):
        d, w = GLYPHS[i]()
        m = (letter, 0, 0, letter, c[0] - letter * w / 2, c[1] - letter * H / 2)
        if mono:
            if letters:
                out.append(path(d, mono, m))
        else:
            out.append(f'<circle cx="{n(c[0])}" cy="{n(c[1])}" r="{n(sc * R_BTN)}" fill="{PAL[ORDER[i]]}"/>')
            out.append(path(d, PAL['ink'] if ORDER[i] == 'yellow' else PAL['white'], m))
    return out, sc * 2 * half_w, size


# ---------------------------------------------------------------- files
def svg(els, w, h, margin=0.0, bg=None):
    vb = f'{n(-margin)} {n(-margin)} {n(w + 2 * margin)} {n(h + 2 * margin)}'
    body = ''
    if bg:
        body += f'<rect x="{n(-margin)}" y="{n(-margin)}" width="{n(w + 2 * margin)}" height="{n(h + 2 * margin)}" fill="{bg}"/>\n'
    body += '\n'.join(els)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{n(w + 2 * margin)}" height="{n(h + 2 * margin)}">\n'
            f'<title>SN64</title>\n{body}\n</svg>\n')


CAP_H = 100.0             # letter height in the logo
BTN_RATIO = 1.15          # height of the button pads as a multiple of the letter height
LOCKUP_GAP = 24.0         # between the pads and the letters
RING_T, RING_PAD_V, RING_CLEAR = 12.0, 20.0, 20.0


def lockup(x=0.0, y=0.0, mono=None, ink=PAL['ink'], ratio=None, letters=True):
    """Button pads with the letters to their right, top-left at (x, y). Returns (elements, width, height)."""
    ratio = BTN_RATIO if ratio is None else ratio
    bh = ratio * CAP_H
    h = max(bh, CAP_H)
    b, bw, _ = buttons(x, y + (h - bh) / 2, bh, mono=mono, letters=letters)
    fills = [mono or ink] * 4
    wm, ww, _ = wordmark(x + bw + LOCKUP_GAP, y + (h - CAP_H) / 2, CAP_H, fills)
    return b + wm, bw + LOCKUP_GAP + ww, h


def logo(mono=None, ink=PAL['ink'], ratio=None, letters=True):
    """The SN64 logo (owner's choice, 2026-10-01): the button pads and the letters inside a ring."""
    _, w, h = lockup(mono=mono, ink=ink, ratio=ratio, letters=letters)
    r_in = h / 2 + RING_PAD_V
    r_out = r_in + RING_T
    # the letters' top right corner is half a letter height above the centre line, where the round
    # end of the ring has already come in by `inset`
    inset = r_in - math.sqrt(r_in ** 2 - (CAP_H / 2) ** 2)
    pad_l, pad_r = RING_CLEAR, RING_CLEAR + inset
    width = 2 * RING_T + pad_l + w + pad_r
    c1, c2 = (r_out, r_out), (width - r_out, r_out)
    ring = path(stadium(c1, c2, r_out) + ' ' + stadium(c1, c2, r_in), mono or ink)
    els, _, _ = lockup(RING_T + pad_l, RING_T + RING_PAD_V, mono=mono, ink=ink, ratio=ratio, letters=letters)
    return [ring] + els, width, 2 * r_out


def build():
    ink = PAL['ink']
    colours = [PAL[c] for c in ORDER]
    files = {}
    for tag, mono, text in (('', None, ink), ('-mono', '#000000', '#000000'), ('-on-dark', None, '#F2F1F5')):
        m = 12.0
        els, w, h = logo(mono=mono, ink=text)
        files[f'sn64-logo{tag}.svg'] = svg(els, w, h, m)
        if mono:                                # plain buttons: no characters on them, for small embossing
            els, w, h = logo(mono=mono, ink=text, letters=False)
            files[f'sn64-logo{tag}-plain.svg'] = svg(els, w, h, m)
        els, w, h = lockup(mono=mono, ink=text)
        files[f'sn64-lockup{tag}.svg'] = svg(els, w, h, m)
        if tag != '-on-dark':
            els, w, h = buttons(0, 0, 132.0, mono=mono)
            files[f'sn64-buttons{tag}.svg'] = svg(els, w, h, m)
        els, w, h = wordmark(0, 0, 100.0, [text] * 4, bar=None if mono else colours)
        if mono:
            els, w, h = wordmark(0, 0, 100.0, [text] * 4, bar=[text] * 4)
        files[f'sn64-wordmark{tag}.svg'] = svg(els, w, h, m)
    for name, text in files.items():
        (OUT / name).write_text(text, encoding='utf-8', newline='\n')
    return sorted(files)


if __name__ == '__main__':
    for name in build():
        print('wrote', name)
