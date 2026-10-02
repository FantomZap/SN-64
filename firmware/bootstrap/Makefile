# SN64 bootstrap ROM (N64/M64 side menu program).
#
#   make            build build/n64-bootstrap/sn64_bootstrap.z64 (needs N64_INST)
#   make check      verify the ROM header and its CIC-6102 IPL2 checksum
#   make words      convert the ROM to the FPGA ROM-window word image (.mem)
#   make test       host tests: mapping table, controller pictures, mapping screen, the menu's look
#                   (title, themes, rows), cartridge-check screens, splash screens, frame lock,
#                   sound resampler, sound output queue, credits roll + ROM tools
#   make splash     regenerate src/sn64_splash_data.c from the logo files (needs PyMuPDF and Pillow)
#   make credits    regenerate src/sn64_credits_data.c (the credits roll) from CREDITS.md and NOTICE
#   make padshapes  regenerate src/sn64_padshape_data.c (the controller outlines of the mapping screen)
#   make title      regenerate src/sn64_title_data.c (the logo as the menu's title; needs PyMuPDF and Pillow)
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
# Must equal the ROM_ADDR_BITS parameter of sn64_n64_endpoint in the top level: 17 on the v2
# board (a 256 KiB window in the configuration flash, fpga/rtl/sn64_board_top.sv). The program
# was 131,072 bytes and fitted 16 until the frame lock and the sound queue (2026-10-01); it is
# 163,840 bytes now. The RTL default is still 12 = 8 KiB, too small; see the design note.
ROM_ADDR_BITS ?= 17

all: rom
.PHONY: all rom check words splash credits padshapes title test test-mapping test-padview test-mapscreen test-menuview test-cartcheck test-splash test-framelock test-resample test-audioout test-credits test-tools test-negative clean

rom:
	mkdir -p $(OUT)
	$(MAKE) -C $(OUT) -f $(CURDIR)/rom.mk SRC_DIR=$(CURDIR)/src

check: rom
	$(PYTHON) tools/n64_cic_check.py $(ROM)

words: rom
	$(PYTHON) tools/z64_to_rom_words.py $(ROM) --rom-addr-bits $(ROM_ADDR_BITS) \
	    --out $(OUT)/sn64_bootstrap_words.mem --manifest $(OUT)/sn64_bootstrap_words.json

test: test-mapping test-padview test-mapscreen test-menuview test-cartcheck test-splash test-framelock test-resample test-audioout test-credits test-tools

splash:
	$(PYTHON) tools/make_splash.py

credits:
	$(PYTHON) tools/make_credits.py

padshapes:
	$(PYTHON) tools/make_padshapes.py

title:
	$(PYTHON) tools/make_title.py

# Credits roll: the generated text is what CREDITS.md gives now, it fits the screen, the crew and the
# cats come last, and no line is ever drawn across the edge of the window.
test-credits:
	mkdir -p $(OUT)/host
	$(PYTHON) tools/make_credits.py --check
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_credits tests/test_credits.c src/sn64_credits.c src/sn64_credits_data.c
	$(OUT)/host/test_credits

test-splash:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_splash tests/test_splash.c src/sn64_splash.c src/sn64_splash_data.c
	$(OUT)/host/test_splash

# Frame lock: timing numbers, the confirmation screen's text and the control loop against a model
# of the two clocks. Also writes the confirmation screen's lines for tools/mock_screens.py.
test-framelock:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_framelock tests/test_framelock.c src/sn64_framelock.c -lm
	$(OUT)/host/test_framelock --screens $(OUT)/host/compat-screen.txt

test-resample:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_resample tests/test_resample.c src/sn64_resample.c -lm
	$(OUT)/host/test_resample

# Sound output queue with the resampler and its rate control, against a model of the console's sound output.
test-audioout:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_audioout tests/test_audioout.c src/sn64_audioout.c src/sn64_resample.c -lm
	$(OUT)/host/test_audioout

test-cartcheck:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_cartcheck tests/test_cartcheck.c src/sn64_cartcheck.c
	$(OUT)/host/test_cartcheck

test-mapping:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_mapping tests/test_mapping.c src/sn64_mapping.c
	$(OUT)/host/test_mapping

# Controller pictures of the mapping screen: the outlines are what tools/make_padshapes.py gives
# now, the shapes are the right ones, and every button lights its own place and no other.
test-padview:
	mkdir -p $(OUT)/host
	$(PYTHON) tools/make_padshapes.py --check
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_padview tests/test_padview.c src/sn64_padview.c src/sn64_padshape_data.c src/sn64_mapping.c
	$(OUT)/host/test_padview

# The mapping screen: what the buttons do and what is drawn. Also writes the screens for
# tools/mock_screens.py, pixels and text, with the code under test.
test-mapscreen:
	mkdir -p $(OUT)/host/screens
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_mapscreen tests/test_mapscreen.c src/sn64_mapscreen.c src/sn64_theme.c src/sn64_padview.c src/sn64_padshape_data.c src/sn64_mapping.c
	$(OUT)/host/test_mapscreen --screens $(OUT)/host/screens

# The menu's look: the themes, the logo as the title, the rows of the two menus. The title is
# from the logo files as they are now. Also writes the screens for tools/mock_screens.py.
MENUVIEW_SRC := src/sn64_menuview.c src/sn64_theme.c src/sn64_title_data.c src/sn64_padview.c src/sn64_padshape_data.c src/sn64_mapping.c
test-menuview:
	mkdir -p $(OUT)/host/screens
	$(PYTHON) tools/make_title.py --check
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o $(OUT)/host/test_menuview tests/test_menuview.c $(MENUVIEW_SRC)
	$(OUT)/host/test_menuview --screens $(OUT)/host/screens

test-tools:
	$(PYTHON) tools/test_rom_tools.py --rom $(ROM) --work $(OUT)/tooltest

# Fault injection: every one of these runs must FAIL for the target to pass.
test-negative:
	mkdir -p $(OUT)/host
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_SWAP_AB -Isrc -o $(OUT)/host/test_mapping_fault tests/test_mapping.c src/sn64_mapping.c
	if $(OUT)/host/test_mapping_fault; then echo "NOT DETECTED: swapped A/B table"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_STICK_AXES -Isrc -o $(OUT)/host/test_mapping_fault2 tests/test_mapping.c src/sn64_mapping.c
	if $(OUT)/host/test_mapping_fault2; then echo "NOT DETECTED: the stick judged one axis at a time"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_PAD_WRONG_BUTTON -Isrc -o $(OUT)/host/test_padview_fault tests/test_padview.c src/sn64_padview.c src/sn64_padshape_data.c src/sn64_mapping.c
	if $(OUT)/host/test_padview_fault; then echo "NOT DETECTED: a button lights the wrong place"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_MAPSCREEN_CANCEL_SETS -Isrc -o $(OUT)/host/test_mapscreen_fault tests/test_mapscreen.c src/sn64_mapscreen.c src/sn64_theme.c src/sn64_padview.c src/sn64_padshape_data.c src/sn64_mapping.c
	if $(OUT)/host/test_mapscreen_fault; then echo "NOT DETECTED: giving a choice up changes the mapping"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_TITLE_OFFCENTRE -Isrc -o $(OUT)/host/test_menuview_fault tests/test_menuview.c $(MENUVIEW_SRC)
	if $(OUT)/host/test_menuview_fault; then echo "NOT DETECTED: the title's logo off centre"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_CHECK_LEVELS -Isrc -o $(OUT)/host/test_cartcheck_fault tests/test_cartcheck.c src/sn64_cartcheck.c
	if $(OUT)/host/test_cartcheck_fault; then echo "NOT DETECTED: wrong short/backwards level"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_SPLASH_OFFCENTRE -Isrc -o $(OUT)/host/test_splash_fault tests/test_splash.c src/sn64_splash.c src/sn64_splash_data.c
	if $(OUT)/host/test_splash_fault; then echo "NOT DETECTED: splash picture off centre"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_PACE_SIGN -Isrc -o $(OUT)/host/test_framelock_fault tests/test_framelock.c src/sn64_framelock.c -lm
	if $(OUT)/host/test_framelock_fault; then echo "NOT DETECTED: frame lock pushes the wrong way"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_RESAMPLE_NO_CARRY -Isrc -o $(OUT)/host/test_resample_fault tests/test_resample.c src/sn64_resample.c -lm
	if $(OUT)/host/test_resample_fault; then echo "NOT DETECTED: resampler loses its carry"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_AOUT_NO_CARRY -Isrc -o $(OUT)/host/test_audioout_fault tests/test_audioout.c src/sn64_audioout.c src/sn64_resample.c -lm
	if $(OUT)/host/test_audioout_fault; then echo "NOT DETECTED: sound queue loses the pairs it holds back"; exit 1; fi
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -DSN64_FAULT_CREDITS_OVERRUN -Isrc -o $(OUT)/host/test_credits_fault tests/test_credits.c src/sn64_credits.c src/sn64_credits_data.c
	if $(OUT)/host/test_credits_fault; then echo "NOT DETECTED: credits line drawn across the window edge"; exit 1; fi
	if $(PYTHON) tools/test_rom_tools.py --rom $(ROM) --work $(OUT)/tooltest-fault1 --inject-fault size-guard; then echo "NOT DETECTED: size guard"; exit 1; fi
	if $(PYTHON) tools/test_rom_tools.py --rom $(ROM) --work $(OUT)/tooltest-fault2 --inject-fault checksum; then echo "NOT DETECTED: checksum"; exit 1; fi
	@echo "NEGATIVE: all fault-injected runs failed as required"

clean:
	rm -rf $(OUT)
