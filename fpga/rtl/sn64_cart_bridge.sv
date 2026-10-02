// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 physical SNES cartridge bridge.
//
// Sits between the console core (sn64_console_candidate) and the 62-contact
// socket translators. Decides, every master clock, which side owns each pin
// group and gates every cartridge-facing output behind a hardware permission.
//
// Ownership rules (see docs/design/cartridge-bridge-implementation.md):
//   * Address, strobes and clocks: console outputs, driven only while
//     `bus_permit` is high; released (translator /OE high) otherwise.
//   * D0-7: driven toward the cartridge during a console write, and while an
//     internal responder (WRAM) answers a read so the byte appears on the
//     shared bus as on a real SNES. Released during external reads and idle.
//     Never driven from an internal CPU-register read (unsupported by
//     evidence; docs/design/bus-electrical-evidence.md).
//   * DMA and HDMA: a read strobe on one side and a write strobe on the other
//     are low together, and whoever answers the read owns D0-7. A copy from
//     the cartridge to the PPU (/RD and /PAWR low) is the cartridge's byte:
//     the octet listens. A copy from a console device to the cartridge (/PARD
//     and /WR low) is the console's byte: the octet drives. Until 2026-10-01
//     every write strobe made the octet drive, so a copy out of the cartridge
//     ROM had two drivers and the PPU received the console's own stale byte;
//     found when the first real program was run (fpga/tests/tb_game.sv).
//   * The data octet is enabled one clock AFTER the strobe it belongs to
//     starts and disabled one clock AFTER the strobe ends (data hold), and
//     every drive<->listen change passes through at least one released clock
//     (46.56 ns, longer than the translator enable/disable time), so no two
//     drivers ever overlap.
//   * /IRQ and /RESET are sensed; the console pulls /RESET low only through
//     an open-drain request, never a push-pull high.
// Translator control is active-low /OE. dir=1 means FPGA->cartridge (B->A).
module sn64_cart_bridge (
    input  wire        clk,            // 21.477 MHz master clock
    input  wire        reset_n,        // console reset (active low)
    input  wire        bus_permit,     // hardware veto AND run request; 0 = release everything

    // From console core
    input  wire [23:0] core_address,
    input  wire [7:0]  core_pa,
    input  wire        core_rd_n, core_wr_n, core_prd_n, core_pwr_n,
    input  wire        core_romsel_n, core_wramsel_n, core_refresh, core_phi2,
    input  wire [7:0]  core_data_out,        // write data / internal responder byte
    input  wire        core_internal_valid,  // internal responder (WRAM) answering a read
    output wire [7:0]  core_data_in,         // byte the core sees
    output wire        core_irq_n,

    // Toward socket (through translators)
    output reg  [23:0] cart_address,
    output reg  [7:0]  cart_pa,
    output reg         cart_rd_n, cart_wr_n, cart_prd_n, cart_pwr_n,
    output reg         cart_romsel_n, cart_wramsel_n, cart_refresh, cart_phi2,
    output wire        cart_sysclk,          // 21.477 MHz to socket pin 1
    output reg  [7:0]  cart_data_out,
    input  wire [7:0]  cart_data_in,
    input  wire        cart_irq_n,
    input  wire        cart_reset_n_sense,   // socket /RESET level (pin 26)
    output wire        cart_reset_pull_n,    // 0 = pull /RESET low (open-drain request)

    // Translator controls
    output wire        ctl_oe_n,     // address/strobe/clock octets: 0 = drive
    output wire        data_oe_n,    // D0-7 octet: 0 = enabled
    output wire        data_dir,     // 1 = FPGA drives cartridge, 0 = cartridge drives FPGA

    // Status
    output wire        contention_guard   // 1 while the data octet is released
);
    wire permit = bus_permit && reset_n;

    // Hold the cartridge in reset whenever the console is reset or the bus is
    // not permitted. The sensed level is available to the core separately.
    assign cart_reset_pull_n = permit;
    assign ctl_oe_n   = !permit;
    assign cart_sysclk = clk & permit;
    assign core_irq_n  = permit ? cart_irq_n : 1'b1;

    // ---------------------------------------------------------------------
    // Console outputs: registered so address, strobes and data change on the
    // same edge with no combinational skew, and hold while released.
    // ---------------------------------------------------------------------
    reg internal_q;   // registered copy of the WRAM source-valid flag
    reg external_q;   // registered copy of "the byte on the bus is not the console's"
    // Who answers a read. /RD names an A-side source: the cartridge, unless WRAM answers. /PARD
    // names a B-side source: a console device at $2100-$2183 (PPU, APU, the WRAM port), or
    // something on the cartridge or expansion side above that.
`ifdef SN64_FAULT_DMA_DRIVE
    // Fault injection for the benches only: every write strobe drives, as before 2026-10-01.
    wire source_external = 1'b0;
`else
    wire b_console = core_pa < 8'h84;
    wire source_external = (!core_rd_n && !core_internal_valid) ||
                           (!core_prd_n && !b_console && !core_internal_valid);
`endif
    always @(posedge clk) begin
        if (!permit) begin
            cart_address  <= 24'h0;
            cart_pa       <= 8'hFF;
            cart_rd_n     <= 1'b1; cart_wr_n  <= 1'b1;
            cart_prd_n    <= 1'b1; cart_pwr_n <= 1'b1;
            cart_romsel_n <= 1'b1; cart_wramsel_n <= 1'b1;
            cart_refresh  <= 1'b0; cart_phi2 <= 1'b0;
            cart_data_out <= 8'hFF;
            internal_q    <= 1'b0;
            external_q    <= 1'b0;
        end else begin
            cart_address  <= core_address;
            cart_pa       <= core_pa;
            cart_rd_n     <= core_rd_n;   cart_wr_n  <= core_wr_n;
            cart_prd_n    <= core_prd_n;  cart_pwr_n <= core_pwr_n;
            cart_romsel_n <= core_romsel_n;
            cart_wramsel_n <= core_wramsel_n;
            cart_refresh  <= core_refresh;
            cart_phi2     <= core_phi2;
            cart_data_out <= core_data_out;
            internal_q    <= core_internal_valid;
            external_q    <= source_external;
        end
    end

    // ---------------------------------------------------------------------
    // Data-bus ownership. The socket strobes are one clock behind the core's,
    // so deciding from the core's strobes gives the turnaround a full clock
    // BEFORE the strobe edge reaches the cartridge: write data is stable when
    // /WR falls, and the octet is listening when /RD falls, as on a real 5A22.
    // ---------------------------------------------------------------------
    wire write_next    = permit && (!core_wr_n || !core_pwr_n) && !source_external;
    wire internal_next = permit && core_internal_valid && (!core_rd_n || !core_prd_n);
    wire drive_ahead   = write_next || internal_next;

    // Keep driving until one clock after the socket-side strobe has risen
    // (data hold for the cartridge latch), then release.
    wire write_now    = permit && (!cart_wr_n || !cart_pwr_n) && !external_q;
    wire internal_now = permit && internal_q && (!cart_rd_n || !cart_prd_n);
    reg  hold_q;
    always @(posedge clk) hold_q <= permit && (write_now || internal_now);
    wire drive_req = drive_ahead || write_now || internal_now || hold_q;

    // State applied to the translator. A change of owner always goes through
    // a released clock: listen -> released -> drive, drive -> released -> listen.
    reg drive_q, listen_q;
`ifdef SN64_FAULT_NO_GUARD
    // Fault injection for the testbench only: switch owner with no released
    // clock. The bus monitor must report contention. Never define in synthesis.
    always @(posedge clk) begin
        if (!permit) begin drive_q <= 1'b0; listen_q <= 1'b0; end
        else begin drive_q <= drive_req; listen_q <= !drive_req; end
    end
`else
    always @(posedge clk) begin
        if (!permit) begin
            drive_q <= 1'b0; listen_q <= 1'b0;
        end else if (drive_req) begin
            listen_q <= 1'b0;
            drive_q  <= !listen_q;             // first clock after listening: released
        end else begin
            drive_q  <= 1'b0;
            listen_q <= !drive_q;              // first clock after driving: released
        end
    end
`endif

    // Also gated by permit combinationally: once permission drops the SNES
    // clock may stop, and the registered state would then never clear.
    assign data_dir  = drive_q && permit;
    assign data_oe_n = !(permit && (drive_q || listen_q));
    assign contention_guard = data_oe_n;

    // What the core sees: the cartridge byte while listening; its own byte
    // while driving (a real bus shows the driven byte); all-ones while the
    // octet is released. All-ones is a placeholder for the released clock
    // only; it never stands in for a missing cartridge response during a
    // read window, because the read window is longer than the release.
    assign core_data_in = listen_q ? cart_data_in :
                          drive_q  ? cart_data_out : 8'hFF;
endmodule
