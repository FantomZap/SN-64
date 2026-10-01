# SN64 logo

Chosen by the owner on 2026-10-01: four coloured buttons on two slanted pads that read SN over 64, the name in heavy slanted letters beside them, and a ring around both. Preview of every file: [sn64-logo-sheet.png](sn64-logo-sheet.png).

| Files | What it is | Use |
|---|---|---|
| `sn64-logo.svg`, `-on-dark`, `-mono`, `-mono-plain` | The logo: buttons and letters in the ring | Wherever there is room |
| `sn64-lockup.svg`, `-on-dark`, `-mono` | The same without the ring | Where the ring would crowd the surroundings |
| `sn64-buttons.svg`, `-mono` | The buttons alone | Icons and small square places |
| `sn64-wordmark.svg`, `-on-dark`, `-mono` | The letters alone, over a four-colour bar | Narrow places and small embossing |

`-on-dark` files have light letters and a light ring for dark backgrounds. `-mono` files are one colour. `-mono-plain` is the one-colour logo without the characters on the buttons, for embossing at small sizes.

Proportions (owner, 2026-10-01): the buttons are about the height of the letters. They measure 1.15 times the letter height, because their rounded tips make them look smaller than they measure. The buttons use the colours and positions of a Super Famicom controller: green on the left, blue on top, yellow at the bottom, red on the right.

## One-colour files and embossing

A one-colour file is a single black fill on a transparent background. Black is the raised or printed part, so the same file serves embossing, silkscreen or a stamp. In the buttons, each pad is raised, each button is a round pocket in its pad and the character stands in the pocket.

Finest detail, as a share of the height of the piece, and the size at which that detail is 1 mm:

| File | Height measured | Thinnest raised part | Narrowest gap or pocket | Size for 1 mm detail |
|---|---|---|---|---|
| `sn64-logo-mono.svg` | whole logo | 2.6 % (characters on the buttons); the ring is 6.7 % | 2.1 % (inside the 4 on its button) | 48 mm tall, 147 mm wide |
| `sn64-logo-mono-plain.svg` | whole logo | 2.9 % (rim of a pad around its button) | 3.0 % (between the two pads) | 34 mm tall, 106 mm wide |
| `sn64-lockup-mono.svg` | whole piece | 4.1 % | 3.3 % | 31 mm tall, 125 mm wide |
| `sn64-buttons-mono.svg` | whole icon | 4.1 % | 3.3 % | 31 mm tall, 38 mm wide |
| `sn64-wordmark-mono.svg` | letters | 20 % (letter strokes); the bar is 12 % | 7 % (between the 6 and the 4) | letters 15 mm tall, 45 mm wide |

The characters on the buttons are what limits the full logo, which is why the plain version exists. At 22 mm tall the plain logo is 68 mm wide and its finest detail is 0.64 mm. Where even that is too fine, use the letters alone.

## On the shell

The v2 shell carries the logo on the front of its cap, stamped in the way a Game Boy cartridge carries its logo (owner, 2026-10-01): the inside of the ring is a pill-shaped pocket 64.7 x 19.0 mm and 0.6 mm deep, and the buttons and letters stand in it level with the surface, so nothing is proud. `mechanical/sn64-v2-shell/sn64_v2_shell.py` reads `sn64-logo-mono.svg` for this. At that size the letters are 12.3 mm tall with 2.45 mm strokes, the characters on the buttons have 0.58 mm strokes and the narrowest opening is 0.46 mm; `sn64-logo-mono-plain.svg` is the fallback for a process that cannot hold that.

The letters in every file are written in final coordinates with their arcs as Bezier curves and no `transform` attribute. A slanted arc is a piece of an ellipse, and the CAD importer used for the shell broke the S and the 6 when they were written as transformed arcs.

The back of the cap carries the owner's own FantomZap logo in the same style; that logo is in [fantomzap/](fantomzap/README.md) and is not an SN64 logo.

## How the files are made

[make_logo.py](make_logo.py) writes every SVG (pure Python). The four characters are drawn in the script as outlines, so no font is needed or embedded. [render_previews.py](render_previews.py) builds the preview sheet and needs PyMuPDF and Pillow.

```
python assets/logo/make_logo.py
python assets/logo/render_previews.py
```

The files were checked in two renderers (MuPDF and Qt) and look the same in both.

Earlier options, including the letters in a ring without the buttons, are in the history of this folder (commit `b71e1d2`).

## Origin and names

This is original artwork for SN64. It borrows the feel of early-1990s console design: heavy geometric letters, a slant, four button colours, a controller's slanted button pads and a rounded ring. It copies no Nintendo logo, typeface or trademark, and SN64 is not affiliated with or endorsed by Nintendo.

The SN64 name and logo identify this project. They are not covered by the project's open licences: see item 3 under "Attribution" in [NOTICE](../../NOTICE).
