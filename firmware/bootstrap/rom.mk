# SN64 bootstrap ROM: libdragon build. Invoked by ./Makefile with the output
# directory as the working directory (make -C $(OUT) -f .../rom.mk), so every
# build product (objects, ELF, .z64) lands under build/, never in the source tree.
#
# Required: N64_INST (libdragon toolchain + installed libdragon), SRC_DIR.

all: sn64_bootstrap.z64
.PHONY: all

SOURCE_DIR = $(SRC_DIR)
BUILD_DIR  = obj
# ELF compression inside the ROM (libdragon: 0 none, 1 LZ4 [n64.mk default],
# 2 aPLib, 3 Shrinkler). Level 2 shrinks this ROM from 147,456 to 114,688
# bytes, which fits ROM_ADDR_BITS=16 instead of 17 (see
# docs/design/n64-bootstrap.md). Must be set before n64.mk, which uses ?=.
N64_ROM_ELFCOMPRESS ?= 2
include $(N64_INST)/include/n64.mk

SN64_BOOTSTRAP_VERSION ?= 0.1.0
CFLAGS += -DSN64_BOOTSTRAP_VERSION=\"$(SN64_BOOTSTRAP_VERSION)\"
# Keep the builder's absolute source path out of the ROM (backtrace symbols).
CFLAGS += -ffile-prefix-map="$(SRC_DIR)"=sn64_bootstrap
# For a measuring build beside the real one, for example
#   make rom OUT=<other dir> SN64_EXTRA_CFLAGS="-DSN64_READOUT_DEFAULT=true -DSN64_START_SCREEN=SCREEN_MAPPING"
SN64_EXTRA_CFLAGS ?=
CFLAGS += $(SN64_EXTRA_CFLAGS)

OBJS = $(BUILD_DIR)/main.o $(BUILD_DIR)/sn64_mapping.o $(BUILD_DIR)/sn64_cartcheck.o \
       $(BUILD_DIR)/sn64_splash.o $(BUILD_DIR)/sn64_splash_data.o \
       $(BUILD_DIR)/sn64_framelock.o $(BUILD_DIR)/sn64_resample.o $(BUILD_DIR)/sn64_audioout.o \
       $(BUILD_DIR)/sn64_credits.o $(BUILD_DIR)/sn64_credits_data.o \
       $(BUILD_DIR)/sn64_padview.o $(BUILD_DIR)/sn64_padshape_data.o $(BUILD_DIR)/sn64_mapscreen.o \
       $(BUILD_DIR)/sn64_theme.o $(BUILD_DIR)/sn64_menuview.o $(BUILD_DIR)/sn64_title_data.o

# Standard libdragon header: libdragon IPL3 (signed for CIC-6102), title below.
sn64_bootstrap.z64: N64_ROM_TITLE = "SN64 BOOTSTRAP"

$(BUILD_DIR)/sn64_bootstrap.elf: $(OBJS)

-include $(wildcard $(BUILD_DIR)/*.d)
