# FantomZap logo

The owner's own logo: a warning triangle with a lightning bolt, and the word FantomZap beside it. He picked this version from his artwork on 2026-10-01 for two places: stamped into the back of the shell's cap, and as the second splash screen when the console starts.

**The FantomZap name and logo belong to the owner. They are not covered by the project's open licences** (item 3 under "Attribution" in [NOTICE](../../../NOTICE)). They are in this repository so that the shell and the boot program can be built as designed. A modified design should take them out or replace them.

| File | What it is |
|---|---|
| `fantomzap-wordmark-mono.svg` | The logo as outlines, one colour: eleven shapes (triangle, bolt, nine letters) |
| `trace_logo.py` | Makes that file from the artwork |
| `trace-report.json` | Which artwork it was made from, the settings, and the result |

## Where the outlines come from

The logo exists as pixel artwork only: a white-on-transparent PNG, 3088 x 673 pixels. That file stays with the owner and is not in this repository; `trace-report.json` records its name, size and SHA-256. `trace_logo.py` traces it with the potrace algorithm (the `potracer` package) at full resolution, taking every pixel that is more than half covered as logo, and writes each shape with its own holes as plain M/L/C/Z paths.

```
uv run --no-project --with potracer --with pillow --with numpy python assets/logo/fantomzap/trace_logo.py <the owner's PNG>
```

Check made on 2026-10-01: the outlines drawn back at the artwork's size differ from it in 0.85 % of the logo's pixels, and no differing pixel is more than one pixel from the artwork's edge.

## Sizes of its details

Measured on the outlines, as a share of the logo's height (the triangle's height):

| Detail | Share of the height | At 14.6 mm high (on the shell) |
|---|---|---|
| Triangle's border | 7.8 % | 1.1 mm |
| Letter strokes | 8 to 10 % | 1.2 to 1.4 mm |
| Whole logo, length | 605 % | 88.4 mm |
| Sharp tips (bolt, feet of the letters) | under 5 % | under 0.7 mm |
| Tightest gaps (inside corners, bolt against the triangle) | under 2.5 % | under 0.35 mm |

## Where it is used

- **Shell**: stamped into the back of the cap the way the SN64 logo is stamped into the front, see [v2-shell.md](../../../docs/design/v2-shell.md).
- **Boot program**: the second splash screen, 280 pixels wide, white on black, see [n64-bootstrap.md](../../../docs/design/n64-bootstrap.md). `firmware/bootstrap/tools/make_splash.py` draws it from the outlines.
