#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert a .z64 bootstrap ROM into the SN64 FPGA ROM-window word image.

sn64_n64_endpoint.sv holds the bootstrap ROM as `rom[0 : 2**ROM_ADDR_BITS-1]`
of 16-bit words, loaded through `rom_we/rom_waddr/rom_wdata`, and serves
N64 byte address 0x1000_0000 + 2*i from word i. The N64 is big-endian and the
PI bus carries the even-address byte on AD[15:8], so

    word[i] = (rom[2*i] << 8) | rom[2*i + 1]        (big-endian 16-bit)

Output: a $readmemh file with exactly 2**ROM_ADDR_BITS lines of 4 hex digits
(line i = rom_waddr i), padded with 0x0000, usable both for simulation and as
the image a loader streams into rom_waddr/rom_wdata; and an optional JSON
manifest (sizes, SHA-256, the ROM_ADDR_BITS the image needs).

The image must fit the configured window: anything larger is rejected, never
truncated. Exit status: 0 ok, 1 rejected, 2 usage/file error.
"""
import argparse
import hashlib
import json
import struct
import sys

Z64_MAGIC = 0x80371240


class RomImageError(Exception):
    pass


def min_addr_bits(n_bytes):
    words = (n_bytes + 1) // 2
    bits = 0
    while (1 << bits) < words:
        bits += 1
    return bits


def to_words(rom, rom_addr_bits, enforce_size=True):
    """Return the padded word list; raise RomImageError if the image is unusable.

    `enforce_size=False` exists only for the test harness's fault injection.
    """
    if len(rom) < 4 or struct.unpack(">I", rom[:4])[0] != Z64_MAGIC:
        raise RomImageError("not a big-endian .z64 image (header word must be 0x80371240); "
                            "convert .v64/.n64 byte order first")
    if len(rom) % 2:
        raise RomImageError(f"odd image length {len(rom)}; N64 ROMs are whole 16-bit words")
    depth = 1 << rom_addr_bits
    n_words = len(rom) // 2
    if enforce_size and n_words > depth:
        raise RomImageError(
            f"image is {len(rom)} bytes = {n_words} words but ROM_ADDR_BITS={rom_addr_bits} "
            f"holds {depth} words ({depth * 2} bytes); needs ROM_ADDR_BITS >= {min_addr_bits(len(rom))}")
    words = list(struct.unpack(f">{n_words}H", rom))
    words = words[:depth]
    words += [0] * (depth - len(words))
    return words


def write_mem(path, words):
    with open(path, "w", newline="\n") as f:
        for w in words:
            f.write(f"{w:04X}\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rom", help="input .z64 image")
    ap.add_argument("--rom-addr-bits", type=int, required=True,
                    help="ROM_ADDR_BITS of sn64_n64_endpoint (window = 2**N 16-bit words)")
    ap.add_argument("--out", required=True, help="output $readmemh word file")
    ap.add_argument("--manifest", help="optional JSON summary")
    a = ap.parse_args(argv)
    if not 1 <= a.rom_addr_bits <= 25:
        print("ERROR: --rom-addr-bits must be 1..25 (the PI ROM window is 64 MiB)", file=sys.stderr)
        return 2
    try:
        with open(a.rom, "rb") as f:
            rom = f.read()
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    try:
        words = to_words(rom, a.rom_addr_bits)
    except RomImageError as e:
        print(f"REJECTED: {a.rom}: {e}", file=sys.stderr)
        return 1
    write_mem(a.out, words)
    info = {
        "source": a.rom,
        "source_bytes": len(rom),
        "source_sha256": hashlib.sha256(rom).hexdigest(),
        "image_words": len(rom) // 2,
        "rom_addr_bits": a.rom_addr_bits,
        "window_words": len(words),
        "min_rom_addr_bits": min_addr_bits(len(rom)),
        "format": "readmemh, one 16-bit big-endian word per line, line i = rom_waddr i, pad 0x0000",
        "output": a.out,
    }
    if a.manifest:
        with open(a.manifest, "w", newline="\n") as f:
            json.dump(info, f, indent=2)
            f.write("\n")
    print(f"OK: {len(rom)} bytes -> {len(rom) // 2} words in a {len(words)}-word window "
          f"(ROM_ADDR_BITS={a.rom_addr_bits}, minimum {info['min_rom_addr_bits']}) -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
