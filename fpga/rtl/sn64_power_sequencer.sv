// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 power-control state machine.
//
// Implements the sequence in docs/design/power-architecture.md ("Sequence and
// closure") and the permission rule in docs/design/physical-cartridge-bridge.md:
//
//   permit = configured && rails_ok && cart_5v_ok && !fault_latched && run_request
//
// A firmware/bootstrap request can never override the hardware inputs: every
// hardware condition is ANDed in combinationally and any loss of one drops
// `bus_permit` and the cartridge enable on the same clock (asynchronous veto
// belongs to the analog fault circuit; this block is the digital half).
//
// States: OFF -> RESET_ASSERTED -> CART_5V_RAMP -> IFACE_RAIL -> RUNNING;
// any fault or loss of request -> SHUTDOWN (outputs off first, then rails) -> OFF.
// Faults latch until `fault_clear` (a deliberate operator/bootstrap action) so
// nothing restarts automatically after a trip.
module sn64_power_sequencer #(
    parameter CLK_HZ = 21_477_272,
    parameter RESET_HOLD_MS = 20,     // cartridge /RESET held after 5 V valid
    parameter RAIL_TIMEOUT_MS = 50    // max wait for a rail to report valid
) (
    input  wire clk, reset_n,

    // Hardware inputs (from monitors / eFuse / configuration logic)
    input  wire configured,           // FPGA configured and safe image running
    input  wire host_3v3_ok,          // host/USB-derived system rails valid
    input  wire fpga_rails_ok,        // core/aux/IO rails valid
    input  wire cart_5v_ok,           // TPS3700-class window monitor on SNES_5V_CART
    input  wire iface_rail_ok,        // switched INTERFACE_3V3 valid
    input  wire efuse_fault_n,        // eFuse /FLT (0 = fault)
    input  wire overtemp,             // board temperature limit exceeded
    input  wire host_reset_n,         // N64/M64 /RESET (0 = host in reset)

    // Requests
    input  wire run_request,          // from the N64 mailbox
    input  wire fault_clear,          // explicit acknowledge

    // Outputs
    output reg  cart_5v_enable,       // eFuse EN (default off)
    output reg  iface_rail_enable,    // switched 3.3 V interface rail
    output reg  cart_reset_pull,      // 1 = pull SNES /RESET low
    output wire bus_permit,           // to sn64_cart_bridge
    output reg  fault_latched,
    output reg  [3:0] state,          // for telemetry
    output reg  [7:0] fault_code      // bitmask of the trip cause(s)
);
    localparam [3:0] S_OFF=0, S_RESET=1, S_RAMP5=2, S_IFACE=3, S_RUN=4, S_SHUTDOWN=5, S_FAULT=6;
    localparam integer RESET_TICKS = CLK_HZ / 1000 * RESET_HOLD_MS;
    localparam integer RAIL_TICKS  = CLK_HZ / 1000 * RAIL_TIMEOUT_MS;

    wire base_ok  = configured && host_3v3_ok && fpga_rails_ok && efuse_fault_n && !overtemp;
    // Trip conditions observed while a rail is expected to be up
    wire trip_5v    = (state == S_IFACE || state == S_RUN) && !cart_5v_ok;
    wire trip_iface = (state == S_RUN) && !iface_rail_ok;
    wire trip_any   = !base_ok || trip_5v || trip_iface;

    // Hardware permission: pure combinational AND, never latched high.
    assign bus_permit = (state == S_RUN) && base_ok && cart_5v_ok && iface_rail_ok
                        && run_request && host_reset_n && !fault_latched;

    reg [31:0] timer;
    always @(posedge clk) begin
        if (!reset_n) begin
            state <= S_OFF; timer <= 0;
            cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b1;
            fault_latched <= 1'b0; fault_code <= 8'h0;
        end else begin
            // Fault capture has priority over every state transition.
            if (trip_any && state != S_OFF && state != S_FAULT) begin
                fault_latched <= 1'b1;
                fault_code <= {overtemp, !efuse_fault_n, trip_iface, trip_5v, !fpga_rails_ok, !host_3v3_ok, !configured, 1'b0};
                cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b1;
                state <= S_FAULT;
            end else case (state)
                S_OFF: begin
                    cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b1;
                    if (run_request && base_ok && host_reset_n && !fault_latched) begin
                        state <= S_RESET; timer <= 0;
                    end
                end
                S_RESET: begin                      // reset asserted, enable 5 V with limited slew (eFuse dVdt)
                    cart_5v_enable <= 1'b1; timer <= timer + 1;
                    if (cart_5v_ok) begin state <= S_RAMP5; timer <= 0; end
                    else if (timer > RAIL_TICKS) begin state <= S_FAULT; fault_latched <= 1'b1; fault_code <= 8'h08; cart_5v_enable <= 1'b0; end
                end
                S_RAMP5: begin                      // 5 V verified; bring up the interface rail
                    iface_rail_enable <= 1'b1; timer <= timer + 1;
                    if (iface_rail_ok) begin state <= S_IFACE; timer <= 0; end
                    else if (timer > RAIL_TICKS) begin state <= S_FAULT; fault_latched <= 1'b1; fault_code <= 8'h10; cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; end
                end
                S_IFACE: begin                      // hold reset for the settle time, then release
                    timer <= timer + 1;
                    if (timer >= RESET_TICKS) begin cart_reset_pull <= 1'b0; state <= S_RUN; end
                end
                S_RUN: begin
                    if (!run_request || !host_reset_n) state <= S_SHUTDOWN;
                end
                S_SHUTDOWN: begin                   // outputs off (bus_permit already 0), then rails
                    cart_reset_pull <= 1'b1; iface_rail_enable <= 1'b0; cart_5v_enable <= 1'b0;
                    state <= S_OFF;
                end
                S_FAULT: begin
                    cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b1;
                    if (fault_clear && !run_request) begin fault_latched <= 1'b0; fault_code <= 8'h0; state <= S_OFF; end
                end
                default: state <= S_OFF;
            endcase
        end
    end
endmodule
