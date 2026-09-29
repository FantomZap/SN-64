#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Self-checking test of the bootstrap ROM tools against a built ROM.

Checks: the built ROM passes the CIC-6102 check; deliberately corrupted
images fail it; the word converter round-trips the image exactly and rejects
images too large for the configured ROM window and non-.z64 byte order.

--inject-fault disables one safeguard inside the tools (size guard, or the
IPL2 hash comparison); the run must then FAIL, proving the checks can fail.
Prints a final line starting with PASS: or FAIL:.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True       # keep __pycache__ out of the source tree
sys.path.insert(0, HERE)
import n64_cic_check as cic          # noqa: E402
import z64_to_rom_words as conv      # noqa: E402

failures = []
checks = 0


def expect(cond, what):
    global checks
    checks += 1
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        failures.append(what)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True, help="built sn64_bootstrap.z64")
    ap.add_argument("--work", required=True, help="scratch directory for outputs")
    ap.add_argument("--rtl-rom-addr-bits", type=int, default=12,
                    help="ROM_ADDR_BITS currently in sn64_n64_endpoint.sv (default 12)")
    ap.add_argument("--inject-fault", choices=["size-guard", "checksum"],
                    help="disable a safeguard; the test must then fail")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)

    with open(a.rom, "rb") as f:
        rom = f.read()

    check_rom = cic.check_rom
    enforce = True
    if a.inject_fault == "checksum":
        # Fault: a checker that only looks at the header word, not the IPL2 hash.
        def check_rom(img):
            return len(img) >= 0x1000 and img[:4] == b"\x80\x37\x12\x40", ["header-only (fault injected)"]
    elif a.inject_fault == "size-guard":
        enforce = False
    if a.inject_fault:
        print(f"FAULT INJECTED: {a.inject_fault}")

    # 1. CIC-6102 check
    ok, msgs = check_rom(rom)
    expect(ok, f"built ROM passes CIC-6102 IPL2 check ({msgs[0]})")

    bad = bytearray(rom); bad[0x800] ^= 0x01                       # one bit inside IPL3
    expect(not check_rom(bytes(bad))[0], "one flipped bit inside IPL3 (0x800) fails the check")
    bad = bytearray(rom); bad[0xFFC] ^= 0x80                       # last IPL3 word
    expect(not check_rom(bytes(bad))[0], "flipped bit in last IPL3 word (0xFFC) fails the check")
    bad = bytearray(rom); bad[0:4] = bytes([0x37, 0x80, 0x40, 0x12])  # .v64 byte order
    expect(not check_rom(bytes(bad))[0], "byte-swapped (.v64) header fails the check")
    zero = rom[:0x40] + bytes(0xFC0) + rom[0x1000:]
    expect(not check_rom(zero)[0], "all-zero IPL3 fails the check")
    # Characterisation of a limit: IPL2 only hashes IPL3; later bytes are not covered.
    late = bytearray(rom); late[0x2000] ^= 0xFF
    expect(cic.check_rom(bytes(late))[0],
           "limit recorded: corruption after IPL3 (0x2000) is NOT caught by the CIC check (use SHA-256)")

    # CLI exit codes (real tool, no fault injection possible here)
    corrupt_path = os.path.join(a.work, "corrupt_ipl3.z64")
    bad = bytearray(rom); bad[0x800] ^= 0x01
    with open(corrupt_path, "wb") as f:
        f.write(bad)
    r_ok = subprocess.run([sys.executable, os.path.join(HERE, "n64_cic_check.py"), a.rom], capture_output=True, text=True)
    r_bad = subprocess.run([sys.executable, os.path.join(HERE, "n64_cic_check.py"), corrupt_path], capture_output=True, text=True)
    expect(r_ok.returncode == 0, "n64_cic_check.py exits 0 on the built ROM")
    expect(r_bad.returncode == 1, f"n64_cic_check.py exits 1 on the corrupted ROM: {r_bad.stdout.strip().splitlines()[-1]}")

    # 2. Word converter
    need = conv.min_addr_bits(len(rom))
    words = conv.to_words(rom, need, enforce_size=enforce)
    back = b"".join(w.to_bytes(2, "big") for w in words[:len(rom) // 2])
    expect(len(words) == (1 << need), f"window has 2**{need} = {1 << need} words")
    expect(back == rom, f"big-endian word image round-trips all {len(rom)} bytes")
    expect(words[0] == 0x8037 and words[1] == 0x1240, "word 0/1 = 0x8037 0x1240 (AD[15:8] = even byte)")
    expect(all(w == 0 for w in words[len(rom) // 2:]), "padding words are 0x0000")

    for bits in sorted({a.rtl_rom_addr_bits, need - 1}):
        try:
            conv.to_words(rom, bits, enforce_size=enforce)
            rejected, why = False, "accepted"
        except conv.RomImageError as e:
            rejected, why = True, str(e)
        expect(rejected, f"image rejected for ROM_ADDR_BITS={bits}: {why}")

    try:
        conv.to_words(bytes([0x37, 0x80, 0x40, 0x12]) + rom[4:], need)   # .v64 byte order
        rejected = False
    except conv.RomImageError:
        rejected = True
    expect(rejected, "non-.z64 header rejected by the converter")

    mem = os.path.join(a.work, "words.mem")
    if os.path.exists(mem):
        os.remove(mem)                     # a stale file from an earlier run must not mask a write
    r_small =subprocess.run([sys.executable, os.path.join(HERE, "z64_to_rom_words.py"), a.rom,
                              "--rom-addr-bits", str(a.rtl_rom_addr_bits), "--out", mem], capture_output=True, text=True)
    expect(r_small.returncode == 1 and not os.path.exists(mem),
           f"z64_to_rom_words.py exits 1 and writes nothing for ROM_ADDR_BITS={a.rtl_rom_addr_bits}")
    r_fit = subprocess.run([sys.executable, os.path.join(HERE, "z64_to_rom_words.py"), a.rom,
                            "--rom-addr-bits", str(need), "--out", mem], capture_output=True, text=True)
    lines = open(mem).read().split() if os.path.exists(mem) else []
    expect(r_fit.returncode == 0 and len(lines) == (1 << need) and lines[0] == "8037",
           f"z64_to_rom_words.py writes {1 << need} readmemh lines for ROM_ADDR_BITS={need}")

    if failures:
        print(f"FAIL: {len(failures)} of {checks} ROM-tool checks failed"
              + (f" (fault injected: {a.inject_fault})" if a.inject_fault else ""))
        return 1
    print(f"PASS: ROM tools, {checks} checks: CIC-6102 IPL2 hash 0xA536C0F1D859 on {os.path.basename(a.rom)} "
          f"({len(rom)} bytes), corrupted images rejected, word image round-trips, needs ROM_ADDR_BITS>={need}, "
          f"rejected at {a.rtl_rom_addr_bits} and {need - 1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
