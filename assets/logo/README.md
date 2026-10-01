# SN64 logo: options (2026-10-01, none chosen yet)

The owner asked for a simple logo that uses Nintendo-style design elements, with one-colour versions that can be embossed later. These are the first options. Preview of all of them: [sn64-logo-options.png](sn64-logo-options.png).

| Option | Files | What it is |
|---|---|---|
| A, buttons | `sn64-buttons.svg`, `sn64-buttons-mono.svg` | Four buttons on two slanted pads, the way a controller has them, in green, blue, yellow and red. They read SN over 64. An icon. |
| B, wordmark | `sn64-wordmark.svg`, `-on-dark`, `-mono` | SN64 in heavy slanted letters over a four-colour bar. |
| A + B | `sn64-lockup.svg`, `-on-dark`, `-mono` | The buttons with the letters beside them. |
| C, badge | `sn64-badge.svg`, `-on-dark`, `-mono` | The same letters in a ring. |

`-on-dark` files have light letters for dark backgrounds. `-mono` files are one colour.

## One-colour files and embossing

A `-mono` file is a single black fill on a transparent background. Black is the raised or printed part, so the same file serves embossing, silkscreen or a stamp. In the buttons, the pads are raised, each button is a round pocket in its pad and the letter stands in the pocket.

Smallest features, as a share of the height of the piece:

| File | Height measured | Thinnest raised part | Narrowest gap or pocket |
|---|---|---|---|
| `sn64-wordmark-mono.svg` | letters | 20 % (letter strokes); the bar is 12 % | 7 % (between the 6 and the 4) |
| `sn64-buttons-mono.svg` | whole icon | 4.1 % (letter strokes) | 3.3 % (inside the 4) |
| `sn64-badge-mono.svg` | whole badge | 7.5 % (the ring) | 3.2 % (between the 6 and the 4) |

So letters 12 mm tall have 2.4 mm strokes and a 0.8 mm tightest gap, and the buttons need to be about 30 mm tall before their smallest pocket reaches 1 mm.

## How the files are made

[make_logo.py](make_logo.py) writes every SVG (pure Python). The four characters are drawn in the script as outlines, so no font is needed or embedded. [render_previews.py](render_previews.py) builds the preview sheet and needs PyMuPDF and Pillow.

```
python assets/logo/make_logo.py
python assets/logo/render_previews.py
```

The files were checked in two renderers (MuPDF and Qt) and look the same in both.

## Origin and names

This is original artwork for SN64. It borrows the feel of early-1990s console design: heavy geometric letters, a slant, four button colours and a controller's slanted button pads. It copies no Nintendo logo, typeface or trademark, and SN64 is not affiliated with or endorsed by Nintendo.

The SN64 name and logo identify this project. They are not covered by the project's open licences: see item 3 under "Attribution" in [NOTICE](../../NOTICE).
