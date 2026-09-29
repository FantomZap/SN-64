#!/usr/bin/env bash
# SN64 bootstrap: install a pinned libdragon toolchain natively on Windows
# (Git Bash + w64devkit; no admin, no Docker, no WSL, no MSYS2).
#
# What it does (idempotent):
#   1. downloads libdragon's prebuilt gcc-toolchain-mips64-win64.zip and checks
#      its SHA-256 against the digest GitHub publishes for the release asset;
#   2. unzips it to $TC_DIR/n64inst (this becomes N64_INST);
#   3. clones libdragon at a pinned trunk commit;
#   4. builds and installs libdragon (MIPS side) into N64_INST;
#   5. builds the three host tools a ROM build needs (n64tool, n64sym,
#      n64elfcompress) with w64devkit's mingw-w64 gcc and installs them.
#
# Usage (Git Bash):  bash firmware/bootstrap/tools/setup_libdragon.sh
# Override locations with SN64_TOOLS / W64DEVKIT_BIN if needed.
set -euo pipefail

TOOLS="${SN64_TOOLS:-/c/Users/RyanB/.codex/tools}"
W64="${W64DEVKIT_BIN:-$TOOLS/w64devkit-2.10.0/w64devkit/bin}"

TC_TAG="toolchain-continuous-prerelease"
TC_ASSET="gcc-toolchain-mips64-win64.zip"
TC_URL="https://github.com/DragonMinded/libdragon/releases/download/$TC_TAG/$TC_ASSET"
TC_SHA256="bd201c35afee4aceb9d2a80c6dc9d25eb2a4d426b1b26ef38e33881641b4d1d0"   # asset uploaded 2026-09-15, GCC 16.2.0
TC_DIR="$TOOLS/libdragon-gcc-toolchain-20260915"

LD_REPO="https://github.com/DragonMinded/libdragon.git"
LD_COMMIT="e356bf3f56f7afbf7e5246329562f145965cfdfc"                         # trunk, 2026-09-15
LD_SRC="$TOOLS/libdragon-trunk-e356bf3"

mkdir -p "$TC_DIR"
if [ ! -f "$TC_DIR/$TC_ASSET" ]; then
    echo "[setup] downloading $TC_URL"
    curl -sSL -o "$TC_DIR/$TC_ASSET" "$TC_URL"
fi
echo "$TC_SHA256 *$TC_DIR/$TC_ASSET" | sha256sum -c -

if [ ! -x "$TC_DIR/n64inst/bin/mips64-elf-gcc.exe" ]; then
    echo "[setup] extracting toolchain"
    mkdir -p "$TC_DIR/n64inst"
    unzip -q -o "$TC_DIR/$TC_ASSET" -d "$TC_DIR/n64inst"
fi

if [ ! -d "$LD_SRC/.git" ]; then
    git clone --filter=blob:none --no-checkout "$LD_REPO" "$LD_SRC"
fi
git -C "$LD_SRC" checkout -q "$LD_COMMIT"
test "$(git -C "$LD_SRC" rev-parse HEAD)" = "$LD_COMMIT"

N64_INST="$(cygpath -m "$TC_DIR/n64inst")"
export N64_INST
# Toolchain first (its make.exe and mips64-elf-*), Git Bash POSIX tools next,
# w64devkit last so only its gcc/g++/ar are picked up explicitly below.
export PATH="$TC_DIR/n64inst/bin:$PATH:$W64"

cd "$LD_SRC"
make install-mk
make -j8 libdragon
make install
# MSYS2_AGE is normally read from pacman; w64devkit has none. A date before the
# 2026-04-13 cut-off enables libdragon's own strndup fallback, which is harmless
# when the C runtime already provides strndup.
make -C tools -j8 CC="$W64/gcc.exe" CXX="$W64/g++.exe" AR="$W64/ar.exe" \
     MSYS2_AGE=20260101 \
     n64tool-install n64sym-install n64elfcompress-install

"$N64_INST/bin/mips64-elf-gcc" --version | head -n 1
ls -l "$N64_INST/bin/n64tool.exe" "$N64_INST/bin/n64sym.exe" "$N64_INST/bin/n64elfcompress.exe"
echo "[setup] N64_INST=$N64_INST"
