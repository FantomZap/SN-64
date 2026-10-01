# SN64 bootstrap ROM (N64/M64 side menu program).
#
#   make            build build/n64-bootstrap/sn64_bootstrap.z64 (needs N64_INST)
#   make check      verify the ROM header and its CIC-6102 IPL2 checksum
#   make words      convert the ROM to the FPGA ROM-window word image (.mem)
#   make test       host tests: mapping table, cartridge-check screens, splash screens + ROM tools
#   make splash     regenerate src/sn64_splash_data.c from the logo files (needs PyMuPDF and Pillow)
#   make test-negative  the same tests with injected faults: every run must fail
#   make clean      remove build/n64-bootstrap
#
# Toolchain setup: tools/setup_libdragon.sh (see README.md). Run from Git Bash
# with N64_INST set and $(N64_INST)/bin on PATH.

ROOT          := $(abspath $(CURDIR)/../..)
OUT           ?= $(ROOT)/build/n64-bootstrap
ROM           := $(OUT)/sn64_bootstrap.z64
PYTHON        ?= python
HOST_CC       ?= gcc
# Must equal the ROM_ADDR_BITS parameter of sn64_n64_endpoint in the top level
# (the RTL default is still 12 = 8 KiB, too small; see the design note).
ROM_ADDR_BITS ?= 16

all: rom
.PHONY: all rom check words splash test test-mapping test-cartcheck test-splash test-tools test-negative clean

rom:
	mkdir -p $(OUT)
	$(MAKE) -C $(OUT) -f $(CURDIR)/rom.mk SRC_DIR=$(CURDIR)/src

check: rom
	$(PYTHON) tools/n64_cic_check.py $(ROM)

words: rom
	$(PYTHON) tools/z64_to_rom_words.py $(ROM) --rom-addr-bits $(ROM_ADDR_BITS) \
	    --out $(OUT)/sn64_bootstrap_words.mem --manifest $(OUT)/sn64_bootstrap_words.json

test: test-mapping test-cartcheck test-splash test-tools

splash:
	$(PYTHON) tools/make_splash.py

test-splash:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_splash tests/test_splash.c src/sn64_splash.c src/sn64_splash_data.c
	$(OUT)/host/test_splash

test-cartcheck:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_cartcheck tests/test_cartcheck.c src/sn64_cartcheck.c
	$(OUT)/host/test_cartcheck

test-mapping:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_mapping tests/test_mapping.c src/sn64_mapping.c
	$(OUT)/host/test_mapping

test-tools:
	$(PYTHON) tools/test_rom_tools.py --rom $(ROM) --work $(OUT)/tooltest

# Fault injection: every one of these runs must FAIL for the target to pass.
test-negative:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_SWAP_AB -Isrc -o $(OUT)/host/test_mapping_fault tests/test_mapping.c src/sn64_mapping.c
	if $(OUT)/host/test_mapping_fault; then echo "NOT DETECTED: swapped A/B table"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_CHECK_LEVELS -Isrc -o $(OUT)/host/test_cartcheck_fault tests/test_cartcheck.c src/sn64_cartcheck.c
	if $(OUT)/host/test_cartcheck_fault; then echo "NOT DETECTED: wrong short/backwards level"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_SPLASH_OFFCENTRE -Isrc -o $(OUT)/host/test_splash_fault tests/test_splash.c src/sn64_splash.c src/sn64_splash_data.c
	if $(OUT)/host/test_splash_fault; then echo "NOT DETECTED: splash picture off centre"; exit 1; fi
	if $(PYTHON) tools/test_rom_tools.py --rom $(ROM) --work $(OUT)/tooltest-fault1 --inject-fault size-guard; then echo "NOT DETECTED: size guard"; exit 1; fi
	if $(PYTHON) tools/test_rom_tools.py --rom $(ROM) --work $(OUT)/tooltest-fault2 --inject-fault checksum; then echo "NOT DETECTED: checksum"; exit 1; fi
	@echo "NEGATIVE: all fault-injected runs failed as required"

clean:
	rm -rf $(OUT)
