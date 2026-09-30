// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 mailbox register map, as seen from the N64/M64 CPU.
//
// Contract: docs/design/n64-endpoint-implementation.md and
// fpga/rtl/sn64_n64_endpoint.sv. Registers are 16-bit at even offsets from
// 0x1FFF_0000 (SummerCart64's register window, registers unlocked).
//
// Access rule: the CPU only performs 32-bit PI accesses (libdragon io_read /
// io_write; sub-word CPU writes to PI space are unreliable on real hardware).
// A 32-bit access at offset N is split by the PI into two 16-bit bus cycles:
// bits 31:16 go to/come from offset N, bits 15:0 to/from offset N+2. The
// bootstrap therefore always accesses registers in these pairs:
//
//   0x00  {MAGIC,        VERSION}       read
//   0x04  {STATUS,       SEQ}           read
//   0x08  {FAULT,        reserved}      read   (FAULT = fault_code << 8)
//   0x10  {JOY1_BUTTONS, JOY2_BUTTONS}  write (and read back)
//   0x14  {JOY1_STICK,   CONTROL}       write (and read back)
//   0x18  {COMMIT,       REGION_INFO}   write COMMIT (0x1A is read-only, the write is ignored);
//                                        read: COMMIT reads 0, low half = REGION_INFO
//   0x1C  {REGION_SOURCE, reserved}     read
#ifndef SN64_MAILBOX_H
#define SN64_MAILBOX_H

#include <stdint.h>

#define SN64_ROM_BASE            0x10000000u   // bootstrap ROM window (N64 cartridge domain 1)
#define SN64_MBOX_BASE           0x1FFF0000u

#define SN64_REG_MAGIC_VERSION   0x00u
#define SN64_REG_STATUS_SEQ      0x04u
#define SN64_REG_FAULT           0x08u
#define SN64_REG_JOY1_JOY2       0x10u
#define SN64_REG_STICK_CONTROL   0x14u
#define SN64_REG_COMMIT          0x18u
#define SN64_REG_COMMIT_REGION   0x18u         // read: low half = REGION_INFO (0x1A)
#define SN64_REG_REGION_SOURCE   0x1Cu         // read: high half = REGION_SOURCE (0x1C), low half = FRAME_STATUS (0x1E)
#define SN64_REG_AUDIO_MODE      0x20u         // read: high half = AUDIO_WPTR (0x20), low half = VIDEO_MODE (0x22)

// Console video path (docs/design/console-video-path.md): the SNES frame and audio ring the
// N64 reads through PI domain 2 at SN64_FRAME_BASE. Frame: 240 lines x 256 pixels RGBA5551,
// line*512 + x*2. Audio ring: 1024 stereo pairs at SN64_AUDIO_OFFSET, pair*4 = {left, right}.
#define SN64_FRAME_BASE          0x08000000u
#define SN64_FRAME_LINE_BYTES    512u
#define SN64_FRAME_LINES         224u          // lines shown (the buffer holds 240)
#define SN64_AUDIO_OFFSET        0x1E000u
#define SN64_AUDIO_PAIRS         1024u
#define SN64_FRAME_STATUS_COUNT(w)  (((w) >> 8) & 0xFFu)   // FRAME_STATUS: frames completed
#define SN64_FRAME_STATUS_LINES(w)  ((w) & 0xFFu)          // FRAME_STATUS: last line done (0xFF = none yet)
#define SN64_VMODE_OVERSCAN      0x0001u
#define SN64_VMODE_HIRES         0x0002u
#define SN64_VMODE_INTERLACE     0x0004u
#define SN64_VMODE_PAL           0x0008u
// PI domain-2 timing used for the frame window (62.5 MHz PI cycles): /RD low (PWD+1), high (RLS+1);
// simulated: PWD 5 / RLS 1 streams at 128 ns per word, 2.3x what a 60 Hz frame needs.
#define SN64_PI_DOM2_LAT         0x40u
#define SN64_PI_DOM2_PWD         0x05u
#define SN64_PI_DOM2_PGS         0x07u
#define SN64_PI_DOM2_RLS         0x01u

#define SN64_MAGIC               0x534Eu       // "SN"
#define SN64_CONTROL_RUN_REQUEST 0x0001u       // CONTROL bit 0: cartridge power and run
#define SN64_CONTROL_SOFT_RESET  0x0002u       // CONTROL bit 1: reset SNES (keeps cartridge power)
#define SN64_CONTROL_REGION_SHIFT 2            // CONTROL bits 3:2: 0 auto, 1 NTSC, 2 PAL (next power-up)
#define SN64_CONTROL_REGION_MASK  0x000Cu

// JOY1_STICK packing: {y, x}, two's-complement bytes (y in bits 15:8).
static inline uint16_t sn64_pack_stick(int8_t x, int8_t y)
{
    return (uint16_t)(((uint16_t)(uint8_t)y << 8) | (uint8_t)x);
}

// STATUS bit allocation, wired in fpga/rtl/sn64_top.sv. A latched fault is
// cleared by dropping CONTROL.run_request (the menu's power-down).
typedef struct {
    uint16_t    mask;
    const char *name;
} sn64_status_bit_t;

#define SN64_STATUS_CONFIGURED    0x0001u  // FPGA configured, safe image running
#define SN64_STATUS_HOST_RAILS_OK 0x0002u  // host_3v3_ok && fpga_rails_ok
#define SN64_STATUS_CART_5V_OK    0x0004u  // cartridge 5 V window monitor
#define SN64_STATUS_IFACE_RAIL_OK 0x0008u  // switched interface 3.3 V rail
#define SN64_STATUS_BUS_PERMIT    0x0010u  // hardware permission chain satisfied (cartridge running)
#define SN64_STATUS_FAULT_LATCHED 0x0020u  // power fault latched; needs fault_clear
#define SN64_STATUS_RUN_REQUEST   0x0040u  // echo of CONTROL.run_request as seen by the sequencer
#define SN64_STATUS_PAL           0x0080u  // region configuration = PAL
#define SN64_STATUS_SEQ_STATE_SHIFT 8      // bits 11:8 = power sequencer state[3:0]
#define SN64_STATUS_SEQ_STATE_MASK  0x0F00u
#define SN64_STATUS_SNES_CLOCK    0x1000u  // SNES master clock running
#define SN64_STATUS_KEY_CIC_OK    0x2000u  // SNES key CIC answered correctly
#define SN64_STATUS_KEY_CIC_FAIL  0x4000u  // SNES key CIC mismatch or absent
#define SN64_STATUS_CLOCK_ERROR   0x8000u  // Si5351 did not answer or lock

static const sn64_status_bit_t sn64_status_bits[] = {
    { SN64_STATUS_CONFIGURED,    "FPGA configured"   },
    { SN64_STATUS_HOST_RAILS_OK, "Host/FPGA rails"   },
    { SN64_STATUS_CART_5V_OK,    "Cart 5V ok"        },
    { SN64_STATUS_IFACE_RAIL_OK, "Interface 3V3 ok"  },
    { SN64_STATUS_BUS_PERMIT,    "Bus permit"        },
    { SN64_STATUS_FAULT_LATCHED, "FAULT LATCHED"     },
    { SN64_STATUS_RUN_REQUEST,   "Run request seen"  },
    { SN64_STATUS_PAL,           "PAL region"        },
    { SN64_STATUS_SNES_CLOCK,    "SNES clock running"},
    { SN64_STATUS_KEY_CIC_OK,    "Cart key CIC ok"   },
    { SN64_STATUS_KEY_CIC_FAIL,  "Cart key CIC fail" },
    { SN64_STATUS_CLOCK_ERROR,   "CLOCK CHIP ERROR"  },
};
#define SN64_STATUS_BIT_COUNT (sizeof(sn64_status_bits) / sizeof(sn64_status_bits[0]))

// REGION_INFO (0x1A): ROM-header probe result, snapshot taken when the SNES
// clock started (live until the first decision). Layout from sn64_top.sv.
#define SN64_RINFO_COUNTRY_MASK   0x00FFu  // raw country byte ($FFD9)
#define SN64_RINFO_REJECT_SHIFT   8        // bits 11:8 reject {unstable, checksum, map, country}
#define SN64_RINFO_REJECT_MASK    0x0F00u
#define SN64_RINFO_DONE           0x1000u  // probe finished
#define SN64_RINFO_VALID          0x2000u  // header passed every check
#define SN64_RINFO_PAL            0x4000u  // header country implies PAL
#define SN64_RINFO_ABORTED        0x8000u  // permission lost mid-probe

// REGION_SOURCE (0x1C): how the region of the last cartridge start was decided.
#define SN64_RSRC_SOURCE_MASK     0x0003u  // 0 forced (menu), 1 key CIC, 2 ROM header, 3 NTSC default
#define SN64_RSRC_DECIDED         0x0004u  // fields describe the last cartridge start
#define SN64_RSRC_TIMEOUT         0x0008u  // region timeout expired before the decision
#define SN64_RSRC_PAL             0x0010u  // decided region is PAL

static const char *const sn64_region_source_names[4] = {
    "menu (forced)", "key CIC", "ROM header", "default",
};

#endif
