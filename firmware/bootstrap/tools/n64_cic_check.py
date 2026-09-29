#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check that an N64 ROM image boots against SN64's emulated CIC-6102.

The console's PIF (IPL2) hashes the cartridge IPL3 (ROM bytes 0x40..0xFFF)
with the CIC seed and compares the 48-bit result with the checksum the CIC
sends. SN64 emulates CIC-6102: seed 0x3F, checksum 0xA536C0F1D859
(fpga/rtl/sn64_n64_endpoint.sv, docs/design/n64-cic-implementation.md).
libdragon's IPL3 is signed for 6102 and needs no header CRC, so this hash is
the complete boot check for a libdragon ROM.

`ipl2_checksum` is a Python port of `Nintendo64::ipl2checksum` from ares
(mia/medium/nintendo-64.cpp, commit 433d07fbdb90b02e6a0947b9de0fe5670378c375,
https://github.com/ares-emulator/ares), used under the ISC license:

    Copyright (c) 2004-2025 ares team, Near et al
    Permission to use, copy, modify, and/or distribute this software for any
    purpose with or without fee is hereby granted, provided that the above
    copyright notice and this permission notice appear in all copies.
    THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
    WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
    MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
    ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
    WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
    ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
    OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

Exit status: 0 = valid for CIC-6102, 1 = invalid, 2 = usage/file error.
"""
import argparse
import struct
import sys

M32 = 0xFFFFFFFF
Z64_MAGIC = 0x80371240          # big-endian (.z64) PI domain-1 config word
CIC_6102_SEED = 0x3F
CIC_6102_CHECKSUM = 0xA536C0F1D859

# Other retail CICs (ares' table), used only to say what an image IS signed for.
KNOWN_CICS = [
    (0x3F, 0x45CC73EE317A, "6101"),
    (0x3F, 0x44160EC5D9AF, "7102"),
    (0x3F, 0xA536C0F1D859, "6102/7101"),
    (0x78, 0x586FD4709867, "6103/7103"),
    (0x91, 0x8618A45BC2D3, "6105/7105"),
    (0x85, 0x2BBAD4E6EB74, "6106/7106"),
]


def _rotl(v, s):
    s &= 31
    return ((v << s) | (v >> ((32 - s) & 31))) & M32 if s else v


def _rotr(v, s):
    s &= 31
    return ((v >> s) | (v << ((32 - s) & 31))) & M32 if s else v


def _csum(a0, a1, a2):
    if a1 == 0:
        a1 = a2
    prod = (a0 * a1) & 0xFFFFFFFFFFFFFFFF
    diff = ((prod >> 32) - (prod & M32)) & M32
    return diff if diff else a0


def ipl2_checksum(seed, ipl3):
    """48-bit IPL2 hash of the 0xFC0-byte IPL3 block (ROM 0x40..0xFFF)."""
    if len(ipl3) < 0xFC0:
        raise ValueError("IPL3 block must be 0xFC0 bytes")
    words = struct.unpack(">1008I", bytes(ipl3[:0xFC0]))
    pos = 0
    init = (0x6C078965 * (seed & 0xFF) + 1) & M32
    data = words[pos]; pos += 1
    init ^= data
    st = [init] * 16
    data_next = data
    loop = 0
    while True:
        loop += 1
        data_last = data
        data = data_next
        st[0] = (st[0] + _csum((1007 - loop) & M32, data, loop)) & M32
        st[1] = _csum(st[1], data, loop)
        st[2] ^= data
        st[3] = (st[3] + _csum((data + 5) & M32, 0x6C078965, loop)) & M32
        st[9] = _csum(st[9], data, loop) if data_last < data else (st[9] + data) & M32
        st[4] = (st[4] + _rotr(data, data_last & 0x1F)) & M32
        st[7] = _csum(st[7], _rotl(data, data_last & 0x1F), loop)
        if data < st[6]:
            st[6] = ((st[3] + st[6]) & M32) ^ ((data + loop) & M32)
        else:
            st[6] = ((st[4] + data) & M32) ^ st[6]
        st[5] = (st[5] + _rotl(data, data_last >> 27)) & M32
        st[8] = _csum(st[8], _rotr(data, data_last >> 27), loop)
        if loop == 1008:
            break
        data_next = words[pos]; pos += 1
        st[15] = _csum(_csum(st[15], _rotl(data, data_last >> 27), loop), _rotl(data_next, data >> 27), loop)
        st[14] = _csum(_csum(st[14], _rotr(data, data_last & 0x1F), loop), _rotr(data_next, data & 0x1F), loop)
        st[13] = (st[13] + _rotr(data, data & 0x1F) + _rotr(data_next, data_next & 0x1F)) & M32
        st[10] = _csum((st[10] + data) & M32, data_next, loop)
        st[11] = _csum(st[11] ^ data, data_next, loop)
        st[12] = (st[12] + (st[8] ^ data)) & M32

    buf = [st[0]] * 4
    for loop in range(16):
        data = st[loop]
        tmp = (buf[0] + _rotr(data, data & 0x1F)) & M32
        buf[0] = tmp
        buf[1] = (buf[1] + data) & M32 if data < tmp else _csum(buf[1], data, loop)
        tmp = (data & 0x02) >> 1
        tmp2 = data & 0x01
        buf[2] = (buf[2] + data) & M32 if tmp == tmp2 else _csum(buf[2], data, loop)
        buf[3] = buf[3] ^ data if tmp2 == 1 else _csum(buf[3], data, loop)
    return ((_csum(buf[0], buf[1], 16) << 32) | (buf[3] ^ buf[2])) & 0xFFFFFFFFFFFF


def check_rom(rom):
    """Return (ok, messages) for a .z64 image against CIC-6102."""
    msgs = []
    if len(rom) < 0x1000:
        return False, [f"image is {len(rom)} bytes; a bootable ROM needs at least 0x1000 (header + IPL3)"]
    magic = struct.unpack(">I", rom[0:4])[0]
    if magic != Z64_MAGIC:
        return False, [f"header word 0x{magic:08X} is not the big-endian .z64 value 0x{Z64_MAGIC:08X}"]
    h = ipl2_checksum(CIC_6102_SEED, rom[0x40:0x1000])
    msgs.append(f"IPL2 checksum (seed 0x{CIC_6102_SEED:02X}) = 0x{h:012X}, CIC-6102 expects 0x{CIC_6102_CHECKSUM:012X}")
    if h != CIC_6102_CHECKSUM:
        other = [name for seed, cs, name in KNOWN_CICS if ipl2_checksum(seed, rom[0x40:0x1000]) == cs]
        msgs.append("IPL3 matches " + (", ".join("CIC-" + o for o in other) if other else "no known retail CIC"))
        return False, msgs
    title = rom[0x20:0x34].decode("ascii", "replace").rstrip(" \x00")
    msgs.append(f"title '{title}', size {len(rom)} bytes")
    return True, msgs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rom", help=".z64 image (big-endian)")
    a = ap.parse_args(argv)
    try:
        with open(a.rom, "rb") as f:
            rom = f.read()
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    ok, msgs = check_rom(rom)
    for m in msgs:
        print(("  " if ok else "  ") + m)
    print(("OK: " if ok else "FAIL: ") + f"{a.rom} {'is' if ok else 'is NOT'} bootable with CIC-6102")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
