// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 N64/M64 cartridge endpoint.
//
// Reuses SummerCart64's proven PI-bus controller (fpga/vendor/summercart64,
// GPL-3.0, unmodified) and gives it two SN64-specific back ends:
//   * a bootstrap ROM window at N64 address 0x1000_0000 (the ordinary
//     cartridge-ROM range the console boots from), served from block RAM
//     (ROM_FROM_FLASH = 0) or from the FPGA configuration flash through
//     SummerCart64's flash controller (ROM_FROM_FLASH = 1, sn64_bootrom_flash.sv,
//     docs/design/bootrom-flash.md);
//   * a mailbox register block at 0x1FFF_0000 (SummerCart64's register range,
//     so its unlocked-register convention carries over): controller state
//     from the N64 bootstrap program to the SNES core, and status/control.
// CIC (lockout), SI/joybus and /INT are NOT implemented here; see
// docs/design/n64-endpoint-implementation.md.
module sn64_n64_endpoint #(
    parameter ROM_ADDR_BITS = 12,         // bootstrap ROM window = 2^ROM_ADDR_BITS 16-bit words (mirrored above)
    parameter ROM_FROM_FLASH = 0,         // 0: block RAM loaded through rom_we; 1: SPI configuration flash
    parameter [23:0] FLASH_OFFSET = 24'h40_0000, // flash byte address of ROM word 0 (ROM_FROM_FLASH = 1)
    parameter FLASH_USE_USRMCLK = 1       // 1: ECP5 USRMCLK drives MCLK; 0: SCK on flash_sck (simulation)
) (
    input  wire        clk,               // host clock: clk_host 62.5 MHz in sn64_top (PI logic is synchronous to it)
    input  wire        reset,             // active-high local reset
    input  wire        cic_cpu_clk,       // CIC soft-CPU clock (62.5 MHz from the PLL, as in SummerCart64)

    // N64 cartridge edge (through the host-side I/O)
    input  wire        n64_reset,         // host /RESET, active low (low = held in reset)
    input  wire        n64_nmi,
    input  wire        n64_pi_alel, n64_pi_aleh, n64_pi_read, n64_pi_write,
    inout  wire [15:0] n64_pi_ad,

    // Bootstrap ROM load port (from the programmer/USB path at build time or run time).
    // Unused when ROM_FROM_FLASH = 1 (the image is programmed into the flash).
    input  wire        rom_we,
    input  wire [ROM_ADDR_BITS-1:0] rom_waddr,
    input  wire [15:0] rom_wdata,

    // Configuration flash (ROM_FROM_FLASH = 1). BRAM build: CS high, SCK low, DQ released.
    output wire        flash_sck,         // only with FLASH_USE_USRMCLK = 0; else MCLK comes from USRMCLK
    output wire        flash_cs_n,
    inout  wire [3:0]  flash_dq,

    // Mailbox: N64 -> SNES side
    output reg  [15:0] joy1_buttons, joy2_buttons,   // SNES button image (active-high bits)
    output reg  [7:0]  joy1_stick_x, joy1_stick_y,   // retained for the deferred virtual mouse
    output reg         run_request,                  // bootstrap asks for cartridge power/run
    output reg         soft_reset,                   // "reset SNES" (holds /RESET, keeps cartridge power)
    output reg  [1:0]  region_mode,                  // 0 auto, 1 NTSC, 2 PAL (applies at next cartridge power-up)
    output reg  [1:0]  cart_check_mode,              // 0 enforce, 1 report only, 2 off, 3 check only (taken when a request starts)
    output reg  [15:0] pace_rate,                    // SNES clock pace for sn64_clock_pace: 0 = full speed
    output reg  [15:0] mailbox_seq,                   // increments on every controller update

    // Mailbox: SNES/system -> N64 side
    input  wire [15:0] status_flags,      // STATUS layout: docs/design/n64-endpoint-implementation.md
    input  wire [15:0] fault_flags,       // {fault_code, reserved}
    input  wire [15:0] cart_check,        // CART_CHECK: result of the last cartridge check (layout in the register map below)
    input  wire [15:0] build_id,
    input  wire [15:0] features,          // FEATURES: what this build can do (layout in the register map below)
    input  wire [15:0] region_info,       // REGION_INFO: ROM-header probe result (layout in the register map below)
    input  wire [15:0] region_source,     // REGION_SOURCE: how the region was decided
    // ---------------- Frame window: SNES picture and audio for the console (clk_snes domain) ----------------
    input  wire        clk_snes,
    input  wire        rst_snes_n,
    input  wire [14:0] video_rgb,
    input  wire        video_hde, video_vde,
    input  wire [8:0]  video_x, video_y,
    input  wire        video_high_res, video_interlace, video_pal,
    input  wire [15:0] audio_left, audio_right,
    input  wire        audio_ready,

    // CIC lockout (vendored SummerCart64 implementation on a SERV soft core)
    input  wire        n64_cic_clk,
    inout  wire        n64_cic_dq,
    input  wire        n64_si_clk,        // CIC timeout timer reference (PIF clock)
    input  wire        cic_region,        // 0 = NTSC (6102), 1 = PAL (7101)
    output wire        cic_invalid_region,
    output wire [3:0]  cic_step,          // CIC firmware progress, for diagnostics

    // Events
    output wire        host_reset_event,  // rising edge of host reset release
    output wire        host_nmi_event
);
    // Vendored interfaces
    mem_bus      mem_bus ();
    n64_reg_bus  reg_bus ();
    n64_scb      n64_scb ();

    // Static configuration of the vendored PI controller: plain ROM at
    // 0x1000_0000 (bootloader window disabled), registers unlocked, nothing else.
    assign n64_scb.bootloader_enabled   = 1'b0;
    assign n64_scb.rom_write_enabled    = 1'b0;
    assign n64_scb.rom_shadow_enabled   = 1'b0;
    assign n64_scb.rom_extended_enabled = 1'b0;
    assign n64_scb.sram_enabled         = 1'b1;   // frame/audio window at 0x0800_0000 (PI domain 2), docs/design/console-video-path.md
    assign n64_scb.sram_banked          = 1'b0;
    assign n64_scb.flashram_enabled     = 1'b0;
    assign n64_scb.dd_enabled           = 1'b0;
    assign n64_scb.ddipl_enabled        = 1'b0;
    assign n64_scb.flashram_read_mode   = 1'b0;
    assign n64_scb.cfg_unlock           = 1'b1;

    n64_pi pi (
        .clk(clk), .reset(reset),
        .mem_bus(mem_bus), .reg_bus(reg_bus), .n64_scb(n64_scb),
        .n64_reset(n64_reset), .n64_nmi(n64_nmi),
        .n64_pi_alel(n64_pi_alel), .n64_pi_aleh(n64_pi_aleh),
        .n64_pi_read(n64_pi_read), .n64_pi_write(n64_pi_write),
        .n64_pi_ad(n64_pi_ad));

    assign host_reset_event = n64_scb.n64_reset;
    assign host_nmi_event   = n64_scb.n64_nmi;

    // CIC configuration: cartridge type, standard CIC-6102/7101 seed and
    // checksum (SummerCart64 defaults: seed 0x3F, checksum 0xA536C0F1D859).
    assign n64_scb.cic_disabled  = 1'b0;
    assign n64_scb.cic_64dd_mode = 1'b0;
    assign n64_scb.cic_region    = cic_region;
    assign n64_scb.cic_seed      = 8'h3F;
    assign n64_scb.cic_checksum  = 48'hA536C0F1D859;
    assign cic_invalid_region    = n64_scb.cic_invalid_region;
    assign cic_step              = n64_scb.cic_debug_step;

    // The CIC soft CPU (bit-serial SERV) must answer each CIC bit within the
    // console's bit period; at 21.477 MHz it is too slow, so it runs from its
    // own PLL clock, as in SummerCart64 (62.5 MHz). Its inputs are already
    // synchronised inside n64_cic; only its reset needs a synchroniser here.
    reg [1:0] cic_reset_ff = 2'b11;
    always @(posedge cic_cpu_clk) cic_reset_ff <= {cic_reset_ff[0], reset};
    n64_cic cic (
        .clk(cic_cpu_clk), .reset(cic_reset_ff[1]), .n64_scb(n64_scb),
        .n64_reset(n64_reset), .n64_cic_clk(n64_cic_clk), .n64_cic_dq(n64_cic_dq), .n64_si_clk(n64_si_clk));

    // ---------------------------------------------------------------------
    // mem_bus split: the SRAM window (mem_bus 0x03FE_0000-0x03FF_FFFF, SummerCart64
    // SAVE_OFFSET) goes to the frame window; everything else is the ROM window.
    // ---------------------------------------------------------------------
    mem_bus rom_bus ();
    wire sel_fb = (mem_bus.address[26:17] == 10'h1FF);
    assign rom_bus.request = mem_bus.request & ~sel_fb;
    assign rom_bus.write   = mem_bus.write;
    assign rom_bus.wmask   = mem_bus.wmask;
    assign rom_bus.address = mem_bus.address;
    assign rom_bus.wdata   = mem_bus.wdata;
    wire        fb_ack;
    wire [15:0] fb_rdata, frame_status, audio_wptr, video_mode, frame_phase;
    sn64_frame_window frame_window (
        .clk_snes(clk_snes), .rst_snes_n(rst_snes_n),
        .rgb(video_rgb), .hde(video_hde), .vde(video_vde), .video_x(video_x), .video_y(video_y),
        .high_res(video_high_res), .interlace(video_interlace), .pal(video_pal),
        .audio_left(audio_left), .audio_right(audio_right), .audio_ready(audio_ready),
        .clk_host(clk), .reset(reset),
        .req(mem_bus.request & sel_fb), .write(mem_bus.write), .address(mem_bus.address), .wdata(mem_bus.wdata),
        .ack(fb_ack), .rdata(fb_rdata),
        .frame_status(frame_status), .audio_wptr(audio_wptr), .video_mode(video_mode), .frame_phase(frame_phase));
    assign mem_bus.ack   = sel_fb ? fb_ack   : rom_bus.ack;
    assign mem_bus.rdata = sel_fb ? fb_rdata : rom_bus.rdata;

    // ---------------------------------------------------------------------
    // Bootstrap ROM: mem_bus memory. Word address = byte address >> 1. Reads
    // outside the ROM return the word address mirrored into the ROM (small
    // ROM mirrored across the window); writes are ignored (rom_write_enabled=0).
    // ---------------------------------------------------------------------
    if (ROM_FROM_FLASH) begin : g_rom_flash
        sn64_bootrom_flash #(.FLASH_OFFSET(FLASH_OFFSET), .WINDOW_BITS(ROM_ADDR_BITS + 1),
                             .USE_USRMCLK(FLASH_USE_USRMCLK)) u_flash (
            .clk(clk), .reset(reset), .mem_bus(rom_bus),
            .flash_sck_pin(flash_sck), .flash_cs_n(flash_cs_n), .flash_dq(flash_dq));
    end else begin : g_rom_bram
        reg [15:0] rom [0:(1<<ROM_ADDR_BITS)-1];
        always @(posedge clk) if (rom_we) rom[rom_waddr] <= rom_wdata;

        reg mem_ack;
        reg [15:0] mem_rdata;
        always @(posedge clk) begin
            mem_ack <= 1'b0;
            if (rom_bus.request && !mem_ack) begin
                mem_rdata <= rom[rom_bus.address[ROM_ADDR_BITS:1]];
                mem_ack   <= 1'b1;
            end
        end
        assign rom_bus.ack   = mem_ack;
        assign rom_bus.rdata = mem_rdata;
        assign flash_sck     = 1'b0;
        assign flash_cs_n    = 1'b1;
        // flash_dq is left undriven (released) in the block-RAM build.
    end

    // ---------------------------------------------------------------------
    // Mailbox registers (16-bit words at 0x1FFF_0000 + offset)
    //   0x00 SN64_MAGIC     r  0x534E ("SN")      0x02 SN64_VERSION  r  build_id
    //   0x04 STATUS         r  status_flags        0x06 SEQ           r  mailbox_seq
    //   0x08 FAULT          r  {fault_code, 8'h00} 0x0A CART_CHECK    r  [15] done, [14] pass, [13:12] mode used,
    //                                                                        [8] this build has the check,
    //                                                                        [7:0] rail reading (9.67 mV per count)
    //   0x0C FEATURES       r  [0] the SNES clock can be paced (PACE works), [1] FRAME_PHASE exists
    //   0x10 JOY1_BUTTONS   w                      0x12 JOY2_BUTTONS  w
    //   0x14 JOY1_STICK     w  {y,x}               0x16 CONTROL       w  bit0 run_request, bit1 soft reset,
    //                                                                        bits3:2 region mode (0 auto, 1 NTSC, 2 PAL),
    //                                                                        bits5:4 cartridge check (0 enforce,
    //                                                                        1 report only, 2 off, 3 check only)
    //   0x18 COMMIT         w  any write increments SEQ (bootstrap writes after a full update); reads 0
    //   0x1A REGION_INFO    r  ROM-header probe snapshot: [7:0] country byte ($FFD9), [11:8] reject
    //                          {unstable, checksum, map, country}, [12] done, [13] valid, [14] PAL, [15] aborted
    //   0x1C REGION_SOURCE  r  [1:0] source (0 forced by CONTROL, 1 key CIC, 2 ROM header, 3 NTSC default
    //                          or timeout), [2] decided (fields describe the last cartridge start),
    //                          [3] region timeout expired, [4] decided region PAL, [15:5] 0
    //   0x1E FRAME_STATUS  r  {frame_count[7:0], lines_done[7:0]} of the frame window (0x0800_0000)
    //   0x20 AUDIO_WPTR    r  next stereo pair index the audio ring will receive
    //   0x22 VIDEO_MODE    r  {12'd0, pal, interlace, high_res, overscan}
    //   0x24 FRAME_PHASE   r  {frames_started[4:0], position[10:0]}: quarter lines (341 master clocks) since the
    //                         SNES's visible area began, and a count of frame starts that steps when the position
    //                         returns to 0; position 0x7FF until the first frame (docs/design/frame-lock.md)
    //   0x26 PACE          w  SNES clock pace: this many of every 1,048,576 master clock periods are half a
    //                         period longer (0 = full speed, 0xFFFF = 3.03 % slower); cleared by a host reset.
    //                         Reads back. A 32-bit write at 0x24 writes it (0x24 itself is read-only).
    //   Writes to 0x1A/0x1C are ignored (a 32-bit write at 0x18 also writes 0x1A).
    //   Both words are produced in the clk_25 domain and cross with sn64_cdc_word (sn64_top).
    // ---------------------------------------------------------------------
    localparam [15:0] MAGIC = 16'h534E;
    wire [16:0] ra = reg_bus.address;
    always @(posedge clk) begin
        if (reset) begin
            joy1_buttons <= 16'h0; joy2_buttons <= 16'h0;
            joy1_stick_x <= 8'h0; joy1_stick_y <= 8'h0;
            run_request  <= 1'b0; mailbox_seq  <= 16'h0; soft_reset <= 1'b0; region_mode <= 2'd0;
            cart_check_mode <= 2'd0; pace_rate <= 16'h0;
        end else if (reg_bus.write && reg_bus.cfg_select) begin
            case (ra[7:0])
                8'h10: joy1_buttons <= reg_bus.wdata;
                8'h12: joy2_buttons <= reg_bus.wdata;
                8'h14: {joy1_stick_y, joy1_stick_x} <= reg_bus.wdata;
                8'h16: begin run_request <= reg_bus.wdata[0]; soft_reset <= reg_bus.wdata[1]; region_mode <= reg_bus.wdata[3:2];
                             cart_check_mode <= reg_bus.wdata[5:4]; end
                8'h18: mailbox_seq  <= mailbox_seq + 16'd1;
                8'h26: pace_rate    <= reg_bus.wdata;
                default: ;
            endcase
        end
        // Host reset drops the run request: cartridge power must be re-requested
        // by the bootstrap after every console reset (safety principle).
        // The cartridge check goes back to "enforce" with it: a relaxed mode has to be asked for again.
        // The SNES clock goes back to full speed.
        if (!n64_reset) begin run_request <= 1'b0; soft_reset <= 1'b0; cart_check_mode <= 2'd0; pace_rate <= 16'h0; end
    end

    reg [15:0] cfg_rdata;
    always @* begin
        case (ra[7:0])
            8'h00: cfg_rdata = MAGIC;
            8'h02: cfg_rdata = build_id;
            8'h04: cfg_rdata = status_flags;
            8'h06: cfg_rdata = mailbox_seq;
            8'h08: cfg_rdata = fault_flags;
            8'h0A: cfg_rdata = cart_check;
            8'h0C: cfg_rdata = features;
            8'h10: cfg_rdata = joy1_buttons;
            8'h12: cfg_rdata = joy2_buttons;
            8'h14: cfg_rdata = {joy1_stick_y, joy1_stick_x};
            8'h16: cfg_rdata = {10'd0, cart_check_mode, region_mode, soft_reset, run_request};
`ifdef SN64_FAULT_REGION_SWAP
            8'h1A: cfg_rdata = region_source;   // fault injection: words swapped (tb_n64_endpoint must fail)
            8'h1C: cfg_rdata = region_info;
`else
            8'h1A: cfg_rdata = region_info;
            8'h1C: cfg_rdata = region_source;
`endif
            8'h1E: cfg_rdata = frame_status;
            8'h20: cfg_rdata = audio_wptr;
            8'h22: cfg_rdata = video_mode;
`ifdef SN64_FAULT_PACE_SWAP
            8'h24: cfg_rdata = pace_rate;       // fault injection: words swapped (tb_n64_endpoint must fail)
            8'h26: cfg_rdata = frame_phase;
`else
            8'h24: cfg_rdata = frame_phase;
            8'h26: cfg_rdata = pace_rate;
`endif
            default: cfg_rdata = 16'h0000;
        endcase
    end
    assign reg_bus.cfg_rdata      = cfg_rdata;
    assign reg_bus.flashram_rdata = 16'h0000;
    assign reg_bus.dd_rdata       = 16'h0000;
endmodule
