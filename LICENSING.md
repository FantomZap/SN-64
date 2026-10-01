# Licensing

SN64 is open hardware and free software. Two licences cover the project's own work. They were not
picked freely: SN64 is built on other people's work that already uses them (see
[CREDITS.md](CREDITS.md)), and both require what is built on them to stay under the same terms.

| What | Where | Licence |
|---|---|---|
| FPGA logic, test benches, firmware and their scripts | `fpga/`, `firmware/` | [GPL-3.0-or-later](LICENSE-GPL-3.0-or-later.txt) |
| Schematics, boards, symbols, footprints, shell and other mechanical design files, and the scripts that generate them | `hardware/`, `mechanical/` | [CERN-OHL-S-2.0](LICENSE-CERN-OHL-S-2.0.txt) |
| Documentation | `docs/`, the top-level `.md` files | CERN-OHL-S-2.0 |

A file with its own licence line, such as an `SPDX-License-Identifier` header, is under that licence.
Vendored and derived third-party material keeps its own licence and notices; they are listed in
[CREDITS.md](CREDITS.md) and stored beside the material (`fpga/vendor/*/LICENSE`,
`hardware/sn64/licenses/`, `hardware/sn64/THIRD_PARTY.md`, `mechanical/licenses/`).

## What you may do

Use it, build it, change it and sell it, in whole or in part.

## What you must do

- Keep the notices: the [NOTICE](NOTICE) file, the licence texts and the credits in the files.
- If you pass on a changed version, or a product made from one, publish your changed sources under
  the same licence, and mark what you changed and when.
- **Credit.** Keep the attribution "SN64 by FantomZap" and the source location
  `https://github.com/FantomZap/SN-64` where the files carry them. A product made from the hardware
  design must show that source location on the board's silkscreen (it is in the design files), or
  on its packaging or documentation if the silkscreen is not practical. The exact terms are in
  [NOTICE](NOTICE): GPL-3.0 section 7(b) for the code, a CERN-OHL-S section 4 notice for the hardware.

## What the licences do not give

The names "SN64" and "SN 64" and any SN64 logo. Call a modified design "based on SN64".

There is no warranty. Nintendo 64, Super NES, Super Famicom and M64 are trademarks of their owners;
SN64 is not affiliated with or endorsed by Nintendo or ModRetro.
