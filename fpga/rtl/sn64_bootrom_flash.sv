// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 bootstrap ROM window served from the FPGA's SPI configuration flash.
//
// Replaces the 64-block-RAM bootstrap ROM (docs/design/system-integration.md,
// open decision 1). The N64 PI controller (vendored SummerCart64 n64_pi) reads
// the ROM window through mem_bus (16-bit words, request/ack, byte address).
// This wrapper translates the address into the configuration flash and hands
// the request to SummerCart64's own flash controller (memory_flash, vendored
// unmodified: Quad I/O Fast Read EBh, SCK = clk/2, stream kept open while the
// requests stay sequential; SummerCart64 serves its N64 bootloader this way).
//
//   flash byte address = FLASH_OFFSET + (mem_bus byte address mod 2^WINDOW_BITS)
//
// The mirroring matches the block-RAM window (small ROM mirrored across the
// window). Words come out big-endian: {flash[a], flash[a+1]}, the byte order of
// a .z64 image, so the flash holds the bootstrap ROM file unchanged.
//
// Writes on mem_bus (possible at 0x1FFE_0000 while cfg_unlock is set) are
// acknowledged and discarded here; they never reach the flash controller, so
// the N64 can never program or erase the configuration flash.
//
// Clocking: after configuration the ECP5 MCLK/CCLK pin is only reachable from
// user logic through the USRMCLK primitive (FPGA-TN-02039, ECP5 sysCONFIG
// usage guide). sn64_flash_mclk hides that primitive; see
// docs/design/bootrom-flash.md for the pin and timing notes.
module sn64_bootrom_flash #(
    parameter [23:0] FLASH_OFFSET = 24'h40_0000, // image start in flash; after the bitstream (LFE5U-85 ~2.2 MB)
    parameter        WINDOW_BITS  = 17,          // byte-address bits of the window (17 = 128 KiB = 64 K words)
    parameter        USE_USRMCLK  = 1            // 1: ECP5 USRMCLK drives MCLK; 0: SCK on flash_sck_pin (simulation / GPIO-wired flash)
) (
    input  wire       clk,                       // clk_host, 62.5 MHz (SCK = 31.25 MHz)
    input  wire       reset,
    mem_bus.memory    mem_bus,                   // from n64_pi

    output wire       flash_sck_pin,             // only meaningful when USE_USRMCLK = 0
    output wire       flash_cs_n,
    inout  wire [3:0] flash_dq                   // D0/MOSI, D1/MISO, D2/WP#, D3/HOLD# (QE must be set in the flash)
);
    // Elaboration checks: the offset must be window-aligned and the window must
    // fit in the 24-bit (16 MiB) address space memory_flash uses.
    if (WINDOW_BITS < 2 || WINDOW_BITS > 24) begin : g_bad_window
        $error("sn64_bootrom_flash: WINDOW_BITS must be 2..24");
    end
    if ((FLASH_OFFSET & ((24'd1 << WINDOW_BITS) - 24'd1)) != 24'd0) begin : g_bad_offset
        $error("sn64_bootrom_flash: FLASH_OFFSET must be aligned to 2^WINDOW_BITS");
    end

    localparam [26:0] WINDOW_MASK = (27'd1 << WINDOW_BITS) - 27'd1;

    mem_bus   flash_bus ();
    flash_scb flash_scb ();

    // Read-only use of the flash controller: no erase, no program.
    assign flash_scb.erase_pending = 1'b0;
    assign flash_scb.erase_block   = 8'd0;

    wire [26:0] window_addr = mem_bus.address & WINDOW_MASK;

    assign flash_bus.request = mem_bus.request && !mem_bus.write;
    assign flash_bus.write   = 1'b0;
    assign flash_bus.wmask   = 2'b11;
    assign flash_bus.wdata   = 16'h0000;
    assign flash_bus.address = {3'b000, FLASH_OFFSET + window_addr[23:0]};

    // Writes: one-clock acknowledge, data discarded (same as the block-RAM window).
    reg write_ack;
    always @(posedge clk) begin
        if (reset) write_ack <= 1'b0;
        else       write_ack <= mem_bus.request && mem_bus.write && !write_ack;
    end

    assign mem_bus.ack   = flash_bus.ack | write_ack;
    assign mem_bus.rdata = flash_bus.rdata;

    wire flash_sck;

    memory_flash u_mem (
        .clk(clk), .reset(reset),
        .flash_scb(flash_scb),
        .mem_bus(flash_bus),
        .flash_clk(flash_sck),
        .flash_cs(flash_cs_n),
        .flash_dq(flash_dq));

    sn64_flash_mclk #(.USE_USRMCLK(USE_USRMCLK)) u_mclk (.sck(flash_sck), .sck_pin(flash_sck_pin));
endmodule

// SCK output abstraction.
// USE_USRMCLK = 1: ECP5 USRMCLK primitive. It drives the dedicated MCLK/CCLK
//   configuration pin; USRMCLKTS = 0 enables the output. sck_pin is unused.
//   Synthesis needs the ECP5 cell library read before read_slang
//   (read_verilog -lib +/ecp5/cells_bb.v).
// USE_USRMCLK = 0: SCK leaves on an ordinary output (simulation model, or a
//   board that wires a second flash to general-purpose I/O).
// The simulation bench adds the USRMCLK/board delay in its flash model.
module sn64_flash_mclk #(
    parameter USE_USRMCLK = 1
) (
    input  wire sck,
    output wire sck_pin
);
    if (USE_USRMCLK) begin : g_usrmclk
        USRMCLK u_usrmclk (.USRMCLKI(sck), .USRMCLKTS(1'b0));
        assign sck_pin = 1'b0;
    end else begin : g_pin
        assign sck_pin = sck;
    end
endmodule
