// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 N64/M64 cartridge endpoint.
//
// Reuses SummerCart64's proven PI-bus controller (fpga/vendor/summercart64,
// GPL-3.0, unmodified) and gives it two SN64-specific back ends:
//   * a bootstrap ROM window at N64 address 0x1000_0000 (the ordinary
//     cartridge-ROM range the console boots from), served from block RAM;
//   * a mailbox register block at 0x1FFF_0000 (SummerCart64's register range,
//     so its unlocked-register convention carries over): controller state
//     from the N64 bootstrap program to the SNES core, and status/control.
// CIC (lockout), SI/joybus and /INT are NOT implemented here; see
// docs/design/n64-endpoint-implementation.md.
module sn64_n64_endpoint #(
    parameter ROM_ADDR_BITS = 12          // bootstrap ROM size = 2^ROM_ADDR_BITS 16-bit words
) (
    input  wire        clk,               // 21.477 MHz master clock (PI logic is synchronous to it)
    input  wire        reset,             // active-high local reset
    input  wire        cic_cpu_clk,       // CIC soft-CPU clock (62.5 MHz from the PLL, as in SummerCart64)

    // N64 cartridge edge (through the host-side I/O)
    input  wire        n64_reset,         // host /RESET, active low (low = held in reset)
    input  wire        n64_nmi,
    input  wire        n64_pi_alel, n64_pi_aleh, n64_pi_read, n64_pi_write,
    inout  wire [15:0] n64_pi_ad,

    // Bootstrap ROM load port (from the programmer/USB path at build time or run time)
    input  wire        rom_we,
    input  wire [ROM_ADDR_BITS-1:0] rom_waddr,
    input  wire [15:0] rom_wdata,

    // Mailbox: N64 -> SNES side
    output reg  [15:0] joy1_buttons, joy2_buttons,   // SNES button image (active-high bits)
    output reg  [7:0]  joy1_stick_x, joy1_stick_y,   // retained for the deferred virtual mouse
    output reg         run_request,                  // bootstrap asks for cartridge power/run
    output reg  [15:0] mailbox_seq,                   // increments on every controller update

    // Mailbox: SNES/system -> N64 side
    input  wire [15:0] status_flags,      // rail/fault/config bits from the power/bridge logic
    input  wire [15:0] build_id,

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
    assign n64_scb.sram_enabled         = 1'b0;
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
    // Bootstrap ROM: mem_bus memory. Word address = byte address >> 1. Reads
    // outside the ROM return the word address mirrored into the ROM (small
    // ROM mirrored across the window); writes are ignored (rom_write_enabled=0).
    // ---------------------------------------------------------------------
    reg [15:0] rom [0:(1<<ROM_ADDR_BITS)-1];
    always @(posedge clk) if (rom_we) rom[rom_waddr] <= rom_wdata;

    reg mem_ack;
    reg [15:0] mem_rdata;
    always @(posedge clk) begin
        mem_ack <= 1'b0;
        if (mem_bus.request && !mem_ack) begin
            mem_rdata <= rom[mem_bus.address[ROM_ADDR_BITS:1]];
            mem_ack   <= 1'b1;
        end
    end
    assign mem_bus.ack   = mem_ack;
    assign mem_bus.rdata = mem_rdata;

    // ---------------------------------------------------------------------
    // Mailbox registers (16-bit words at 0x1FFF_0000 + offset)
    //   0x00 SN64_MAGIC     r  0x534E ("SN")      0x02 SN64_VERSION  r  build_id
    //   0x04 STATUS         r  status_flags        0x06 SEQ           r  mailbox_seq
    //   0x10 JOY1_BUTTONS   w                      0x12 JOY2_BUTTONS  w
    //   0x14 JOY1_STICK     w  {y,x}               0x16 CONTROL       w  bit0 = run_request
    //   0x18 COMMIT         w  any write increments SEQ (bootstrap writes after a full update)
    // ---------------------------------------------------------------------
    localparam [15:0] MAGIC = 16'h534E;
    wire [16:0] ra = reg_bus.address;
    always @(posedge clk) begin
        if (reset) begin
            joy1_buttons <= 16'h0; joy2_buttons <= 16'h0;
            joy1_stick_x <= 8'h0; joy1_stick_y <= 8'h0;
            run_request  <= 1'b0; mailbox_seq  <= 16'h0;
        end else if (reg_bus.write && reg_bus.cfg_select) begin
            case (ra[7:0])
                8'h10: joy1_buttons <= reg_bus.wdata;
                8'h12: joy2_buttons <= reg_bus.wdata;
                8'h14: {joy1_stick_y, joy1_stick_x} <= reg_bus.wdata;
                8'h16: run_request  <= reg_bus.wdata[0];
                8'h18: mailbox_seq  <= mailbox_seq + 16'd1;
                default: ;
            endcase
        end
        // Host reset drops the run request: cartridge power must be re-requested
        // by the bootstrap after every console reset (safety principle).
        if (!n64_reset) run_request <= 1'b0;
    end

    reg [15:0] cfg_rdata;
    always @* begin
        case (ra[7:0])
            8'h00: cfg_rdata = MAGIC;
            8'h02: cfg_rdata = build_id;
            8'h04: cfg_rdata = status_flags;
            8'h06: cfg_rdata = mailbox_seq;
            8'h10: cfg_rdata = joy1_buttons;
            8'h12: cfg_rdata = joy2_buttons;
            8'h14: cfg_rdata = {joy1_stick_y, joy1_stick_x};
            8'h16: cfg_rdata = {15'd0, run_request};
            default: cfg_rdata = 16'h0000;
        endcase
    end
    assign reg_bus.cfg_rdata      = cfg_rdata;
    assign reg_bus.flashram_rdata = 16'h0000;
    assign reg_bus.dd_rdata       = 16'h0000;
endmodule
