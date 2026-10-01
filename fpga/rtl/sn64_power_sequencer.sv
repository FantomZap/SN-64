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
// States: OFF -> [CART_CHECK -> CHECK_END] -> RESET_ASSERTED -> CART_5V_RAMP ->
// IFACE_RAIL -> RUNNING; any fault or loss of request -> SHUTDOWN (outputs off
// first, then rails) -> OFF.
// Faults latch until `fault_clear` (a deliberate operator/bootstrap action) so
// nothing restarts automatically after a trip.
//
// Cartridge check (PROBE_ENABLE = 1, docs/design/reversed-cartridge-detection.md).
// A cartridge put in back to front has its ground on the socket's 5 V pins and
// its supply on the socket's ground pins, so switching 5 V on would drive the
// switch's whole current limit backwards through its chips. Before the switch
// is enabled the board therefore pushes a small test current into the
// switched-off cartridge rail (sn64_rail_monitor) and reads the rail voltage.
// A reversed cartridge holds the rail at a diode drop; the right way round, or
// an empty socket, lets it rise. The check passes after PROBE_OK_SAMPLES
// consecutive readings at or above PROBE_OK_CODE and fails when that has not
// happened within PROBE_TIMEOUT_MS. /RESET is released during the check
// because its pull-up hangs from the cartridge rail and would load the test
// current. What a failed check does depends on probe_mode, taken when the
// request starts:
//   0 enforce      a failed check latches fault 0x01; 5 V is never applied
//   1 report only  the result is recorded; the cartridge is started anyway
//   2 off          no check (the behaviour before the check existed)
//   3 check only   the result is recorded; 5 V is NOT applied, pass or fail,
//                  and the machine waits in CHECK_HOLD for the request to drop
// The threshold and timeout are assumed values until measured on cartridges.
module sn64_power_sequencer #(
    parameter CLK_HZ = 21_477_272,
    parameter RESET_HOLD_MS = 20,     // cartridge /RESET held after 5 V valid
    parameter RAIL_TIMEOUT_MS = 50,   // max wait for a rail to report valid
    parameter PROBE_ENABLE = 0,       // 1: this build has the cartridge check
    parameter PROBE_TIMEOUT_MS = 4000,        // max wait for the rail to rise under the test current
    parameter [11:0] PROBE_OK_CODE = 12'd269, // rail reading (ADC code) that rules out a reversed cartridge
    parameter PROBE_OK_SAMPLES = 2    // consecutive readings needed
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
    input  wire release_ok,           // region decided and SNES master clock running (tie 1 if unused)
    input  wire hold_reset,           // soft reset while running (N64-menu "reset SNES", like the
                                      // console reset button): pulls /RESET, NEVER removes cartridge power

    // Cartridge check (with PROBE_ENABLE = 0 tie the three probe inputs to 0)
    input  wire [1:0] probe_mode,     // 0 enforce, 1 report only, 2 off, 3 check only
    output reg  probe_req,            // 1 = push the test current and sample the rail
    input  wire probe_active,         // the monitor still owns the rail-sense pin
    input  wire probe_strobe,         // one clock: probe_code is a new rail reading
    input  wire [11:0] probe_code,
    output reg  probe_done,           // a check has finished for the latest request
    output reg  probe_pass,           // ... and the rail rose above the threshold
    output reg  [1:0] probe_mode_q,   // mode the latest request was started with
    output reg  [7:0] probe_level,    // last reading, code/4 saturated

    // Outputs
    output reg  cart_5v_enable,       // eFuse EN (default off)
    output reg  iface_rail_enable,    // switched 3.3 V interface rail
    output reg  cart_reset_pull,      // 1 = pull SNES /RESET low
    output wire bus_permit,           // to sn64_cart_bridge
    output reg  fault_latched,
    output reg  [3:0] state,          // for telemetry
    output reg  [7:0] fault_code      // bitmask of the trip cause(s)
);
    // The numbers are part of the telemetry contract (STATUS bits 11:8) and other blocks compare
    // against them (3..4 = cartridge powered, >= 5 = SNES clock stopped): new states go at the end.
    localparam [3:0] S_OFF=0, S_RESET=1, S_RAMP5=2, S_IFACE=3, S_RUN=4, S_SHUTDOWN=5, S_FAULT=6,
                     S_PROBE=7, S_PROBE_END=8, S_PROBE_HOLD=9;
    localparam [1:0] M_ENFORCE=2'd0, M_REPORT=2'd1, M_OFF=2'd2, M_CHECK_ONLY=2'd3;
    localparam integer RESET_TICKS = CLK_HZ / 1000 * RESET_HOLD_MS;
    localparam integer RAIL_TICKS  = CLK_HZ / 1000 * RAIL_TIMEOUT_MS;
    localparam integer PROBE_TICKS = CLK_HZ / 1000 * PROBE_TIMEOUT_MS;
    localparam [7:0] FAULT_PROBE = 8'h01;   // rail held low under the test current: reversed or shorted cartridge

    wire base_ok  = configured && host_3v3_ok && fpga_rails_ok && efuse_fault_n && !overtemp;
    // Trip conditions observed while a rail is expected to be up
    wire trip_5v    = (state == S_IFACE || state == S_RUN) && !cart_5v_ok;
    wire trip_iface = (state == S_RUN) && !iface_rail_ok;
    wire trip_any   = !base_ok || trip_5v || trip_iface;

    // Hardware permission: pure combinational AND, never latched high.
    assign bus_permit = (state == S_RUN) && base_ok && cart_5v_ok && iface_rail_ok
                        && run_request && host_reset_n && !fault_latched;

    reg [31:0] timer;
    reg [3:0]  probe_ok_count;
    wire [9:0] probe_quarter = probe_code[11:2];
    always @(posedge clk) begin
        if (!reset_n) begin
            state <= S_OFF; timer <= 0;
            cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b1;
            fault_latched <= 1'b0; fault_code <= 8'h0;
            probe_req <= 1'b0; probe_done <= 1'b0; probe_pass <= 1'b0; probe_mode_q <= M_ENFORCE;
            probe_level <= 8'd0; probe_ok_count <= 4'd0;
        end else begin
            // Fault capture has priority over every state transition.
            if (trip_any && state != S_OFF && state != S_FAULT) begin
                fault_latched <= 1'b1;
                fault_code <= {overtemp, !efuse_fault_n, trip_iface, trip_5v, !fpga_rails_ok, !host_3v3_ok, !configured, 1'b0};
                cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b1; probe_req <= 1'b0;
                state <= S_FAULT;
            end else case (state)
                S_OFF: begin
                    cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b1; probe_req <= 1'b0;
                    if (run_request && base_ok && host_reset_n && !fault_latched) begin
                        timer <= 0; probe_ok_count <= 4'd0; probe_mode_q <= probe_mode;
                        probe_done <= 1'b0; probe_pass <= 1'b0;
                        if (PROBE_ENABLE && probe_mode != M_OFF) state <= S_PROBE;
                        else if (probe_mode == M_CHECK_ONLY)     state <= S_PROBE_HOLD;   // no check in this build: still never powers
                        else                                     state <= S_RESET;
                    end
                end
                S_PROBE: begin                      // 5 V off; test current on; /RESET released (its pull-up loads the rail)
                    cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b0; probe_req <= 1'b1;
                    timer <= timer + 1;
                    if (probe_strobe) begin
                        probe_level <= (probe_quarter > 10'd255) ? 8'd255 : probe_quarter[7:0];
                        probe_ok_count <= (probe_code >= PROBE_OK_CODE) ? probe_ok_count + 4'd1 : 4'd0;
                    end
                    if (!run_request || !host_reset_n) begin
                        probe_req <= 1'b0; cart_reset_pull <= 1'b1; state <= S_SHUTDOWN;
                    end else if (probe_ok_count >= PROBE_OK_SAMPLES) begin
                        probe_req <= 1'b0; cart_reset_pull <= 1'b1; probe_done <= 1'b1; probe_pass <= 1'b1;
                        state <= S_PROBE_END; timer <= 0;
                    end else if (timer > PROBE_TICKS) begin
                        probe_req <= 1'b0; cart_reset_pull <= 1'b1; probe_done <= 1'b1; probe_pass <= 1'b0;
`ifdef SN64_FAULT_CHECK_IGNORED               // fault injection: a failed check is not enforced (tb_cart_check must fail)
                        if (1'b0) begin
`else
                        if (probe_mode_q == M_ENFORCE) begin
`endif
                            state <= S_FAULT; fault_latched <= 1'b1; fault_code <= FAULT_PROBE;
                        end else begin
                            state <= S_PROBE_END; timer <= 0;
                        end
                    end
                end
                S_PROBE_END: begin                  // test current off; wait until the monitor measures the rail again
                    cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b1; probe_req <= 1'b0;
                    timer <= timer + 1;
                    if (!run_request || !host_reset_n) state <= S_SHUTDOWN;
                    else if (!probe_active) begin
                        state <= (probe_mode_q == M_CHECK_ONLY) ? S_PROBE_HOLD : S_RESET; timer <= 0;
                    end else if (timer > RAIL_TICKS) begin
                        state <= S_FAULT; fault_latched <= 1'b1; fault_code <= FAULT_PROBE;
                    end
                end
                S_PROBE_HOLD: begin                 // check only: nothing is powered; wait for the request to drop
                    cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b1; probe_req <= 1'b0;
                    if (!run_request || !host_reset_n) state <= S_SHUTDOWN;
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
                S_IFACE: begin                      // hold reset for the settle time and until the
                    timer <= timer + 1;             // region is decided and the SNES clock runs
                    if (timer >= RESET_TICKS && release_ok) begin cart_reset_pull <= 1'b0; state <= S_RUN; end
                end
                S_RUN: begin
                    // A soft reset behaves like the console reset button: /RESET
                    // is held, cartridge 5 V and the interface rail stay on, so a
                    // flashcart keeps its loaded game. Power is only removed by
                    // SHUTDOWN or FAULT. The SNES master clock is never changed
                    // here (region is fixed at power-on; see sn64_clock_init).
                    cart_reset_pull <= hold_reset;
                    if (!run_request || !host_reset_n) state <= S_SHUTDOWN;
                end
                S_SHUTDOWN: begin                   // outputs off (bus_permit already 0), then rails
                    cart_reset_pull <= 1'b1; iface_rail_enable <= 1'b0; cart_5v_enable <= 1'b0; probe_req <= 1'b0;
                    state <= S_OFF;
                end
                S_FAULT: begin
                    cart_5v_enable <= 1'b0; iface_rail_enable <= 1'b0; cart_reset_pull <= 1'b1; probe_req <= 1'b0;
                    if (fault_clear && !run_request) begin fault_latched <= 1'b0; fault_code <= 8'h0; state <= S_OFF; end
                end
                default: state <= S_OFF;
            endcase
        end
    end
endmodule
