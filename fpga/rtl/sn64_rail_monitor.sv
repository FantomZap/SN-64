// SN64 v2 rail and temperature monitor: one TLA2528 8-channel I2C ADC replaces
// the v1 window comparators, temperature switch and USB-C detector.
// Channel plan (hardware/sn64-v2 fpga sheet, AVDD = FPGA_3V3 is the reference,
// 12-bit left-justified data, 0.806 mV/LSB):
//   0 HOST_3V3 /2   1 USB_VBUS /3   2 5V_SYS /3   3 SNES_5V_CART /3
//   4 FPGA_1V1      5 NTC 10k/10k   6 USB CC1     7 USB CC2
// TLA2528 access (TI SBAS961A, manual mode, to verify on hardware): single register
// write opcode 0x08 to CHANNEL_SEL (0x11), then an I2C read of two bytes returns
// the conversion of that channel. I2C address 0x10: the ADDR pin left open
// (TI SBAS961A table 2; tied straight to ground is not one of its eight settings).
// Thresholds are 12-bit codes on the divided inputs (fixed in logic for now;
// telemetry gets the raw codes).
//
// Cartridge check (docs/design/reversed-cartridge-detection.md). Every TLA2528
// channel can also be a push-pull digital output (SBAS961A table 3: PIN_CFG 0x05,
// GPIO_CFG 0x07, GPO_DRIVE_CFG 0x09, GPO_VALUE 0x0B). While probe_req is high and
// the cartridge 5 V switch is off, channel 3 is turned into an output driving
// AVDD, so the divider's top resistor (R30) feeds a small test current into the
// cartridge rail: (3.3 V - rail) / 20 k, at most 0.165 mA. Every PROBE_GAP
// channel readings the pin goes back to an analog input and the rail is
// measured; its capacitors hold the voltage for the half millisecond that
// takes. The reading comes out on probe_code with a one-clock probe_strobe.
// While probe_active is high channel 3 is not a rail reading and cart_5v_ok is
// held low. PIN_CFG is written back to "all analog" first thing after reset
// and after any I2C error, so an interrupted check cannot leave the pin driving.
// The ports are synchronous to clk (the sequencer runs on the same clock).
// SPDX-License-Identifier: GPL-3.0-or-later
module sn64_rail_monitor #(
    parameter int CLK_HZ  = 27_000_000,
    parameter int I2C_HZ  = 100_000,
    parameter [6:0] ADDR  = 7'h10,
    parameter int PROBE_GAP = 28        // channel readings between two cartridge-check samples (about 20 ms of test current)
) (
    input  wire clk,
    input  wire rst_n,
    output reg  scl_oe, sda_oe,         // 1 = pull the line low (open drain on the pads)
    input  wire sda_in,
    output reg  host_3v3_ok, sys_5v_ok, cart_5v_ok, core_1v1_ok, overtemp,
    output reg  error,                  // NACK or no scan yet
    output reg  [127:0] codes,          // 8 x 16-bit raw readings, channel 0 in bits [15:0]
    // cartridge check
    input  wire probe_req,              // 1 = feed the test current and sample the cartridge rail
    output reg  probe_active,           // channel 3 belongs to the check (cart_5v_ok held low)
    output reg  probe_strobe,           // one clk: probe_code is a new reading of the rail
    output reg  [11:0] probe_code       // rail / 3, 0.806 mV per code
);
    // ---- thresholds (codes) ----
    localparam [11:0] HOST_MIN = 12'd1800, HOST_MAX = 12'd2296;   // 2.90 .. 3.70 V through /2
    localparam [11:0] SYS5_MIN = 12'd1903, SYS5_MAX = 12'd2234;   // 4.60 .. 5.40 V through /3
    localparam [11:0] CORE_MIN = 12'd1241, CORE_MAX = 12'd1489;   // 1.00 .. 1.20 V direct
    localparam [11:0] NTC_HOT  = 12'd3480;                        // ~70 C with a 10k B3950 NTC over 10k

    // ---- TLA2528 registers used ----
    localparam [7:0] REG_PIN_CFG = 8'h05, REG_GPIO_CFG = 8'h07, REG_GPO_DRIVE_CFG = 8'h09,
                     REG_GPO_VALUE = 8'h0B, REG_CHANNEL_SEL = 8'h11;
    localparam [2:0] CART_CH  = 3'd3;                             // SNES_5V_CART divider
    localparam [7:0] CART_BIT = 8'h08;                            // its bit in the per-channel registers

    // ---- quarter-bit tick ----
    localparam int TICKS = CLK_HZ / (I2C_HZ * 4);
    reg [$clog2(TICKS + 1)-1:0] tdiv = '0;
    wire tick = (tdiv == TICKS - 1);
    always @(posedge clk) tdiv <= (!rst_n || tick) ? '0 : tdiv + 1'b1;

    // ---- byte-level engine: one transaction = start, N bytes (write or read), stop ----
    // Register write:  [W addr][0x08][register][value] stop.
    // Channel reading: the same write to CHANNEL_SEL, then [R addr][hi ack][lo nack] stop.
    reg [3:0]  step;          // 0..3 write bytes, 5..7 read bytes
    reg [2:0]  chan;
    reg [3:0]  bitc;
    reg [2:0]  phase;         // quarter-bit phase
    reg        ack_bad;
    reg [15:0] rx;
    reg [1:0]  sda_s;
    always @(posedge clk) sda_s <= {sda_s[0], sda_in};

    localparam S_IDLE = 0, S_START = 1, S_BIT = 2, S_ACK = 3, S_STOP = 4, S_GAP = 5;
    reg [2:0] st;
    reg [7:0] tx_byte, tx_reg, tx_val;
    reg       is_read, last_read;

    // ---- what the next transaction is ----
    localparam [2:0] OP_SCAN = 3'd0,      // read channel `chan`
                     OP_PIN_CLR = 3'd1,   // PIN_CFG = 0: every channel an analog input (test current off)
                     OP_CFG = 3'd2,       // one of the three output-setup registers
                     OP_PIN_SET = 3'd3,   // PIN_CFG = CART_BIT: channel 3 drives AVDD (test current on)
                     OP_PROBE = 3'd4;     // read channel 3 for the cartridge check
    reg [2:0] op;
    reg       pin_dirty;      // PIN_CFG state unknown: write "all analog" before anything else
    reg       need_cfg;       // the output-setup registers must be written before the pin may drive
    reg       inj;            // channel 3 is driving
    reg       sample_pending; // pin just went analog: take the check reading next
    reg [1:0] cfg_left, cfg_idx;
    reg [7:0] gap;            // channel readings since the test current was switched on
    reg [1:0] preq;
    always @(posedge clk) preq <= {preq[0], probe_req};
    wire probe_req_s = preq[1];
    wire [2:0] scan_chan = ((probe_active || probe_req_s) && chan == CART_CH) ? CART_CH + 3'd1 : chan;

    function automatic [7:0] cfg_reg(input [1:0] i);
        case (i)
            2'd0:    cfg_reg = REG_GPO_VALUE;        // output level high ...
            2'd1:    cfg_reg = REG_GPO_DRIVE_CFG;    // ... push-pull ...
            default: cfg_reg = REG_GPIO_CFG;         // ... direction output (no effect until PIN_CFG selects the pin)
        endcase
    endfunction

    function automatic [7:0] byte_for(input [3:0] s, input [7:0] r, input [7:0] v);
        case (s)
            4'd0: byte_for = {ADDR, 1'b0};
            4'd1: byte_for = 8'h08;          // single register write
            4'd2: byte_for = r;
            4'd3: byte_for = v;
            4'd5: byte_for = {ADDR, 1'b1};
            default: byte_for = 8'hFF;       // read phases: release SDA
        endcase
    endfunction

    always @(posedge clk) begin
        probe_strobe <= 1'b0;
        if (!rst_n) begin
            st <= S_IDLE; step <= 4'd0; chan <= 3'd0; bitc <= 4'd0; phase <= 3'd0; scl_oe <= 1'b0; sda_oe <= 1'b0;
            host_3v3_ok <= 1'b0; sys_5v_ok <= 1'b0; cart_5v_ok <= 1'b0; core_1v1_ok <= 1'b0; overtemp <= 1'b0;
            error <= 1'b1; codes <= '0; ack_bad <= 1'b0; rx <= 16'd0; is_read <= 1'b0; last_read <= 1'b0; tx_byte <= 8'hFF;
            tx_reg <= REG_CHANNEL_SEL; tx_val <= 8'd0; op <= OP_SCAN;
            pin_dirty <= 1'b1; need_cfg <= 1'b1; inj <= 1'b0; sample_pending <= 1'b0; cfg_left <= 2'd0; cfg_idx <= 2'd0; gap <= 8'd0;
            probe_active <= 1'b0; probe_code <= 12'd0;
        end else if (tick) begin
            case (st)
                S_IDLE: begin                         // bus idle (both released); choose the next transaction
                    step <= 4'd0; ack_bad <= 1'b0; st <= S_START;
                    if (pin_dirty) begin
                        op <= OP_PIN_CLR; tx_reg <= REG_PIN_CFG; tx_val <= 8'h00;
                    end else if (probe_req_s && need_cfg) begin                   // a check begins: set the output up first
                        probe_active <= 1'b1; need_cfg <= 1'b0; cart_5v_ok <= 1'b0; cfg_left <= 2'd3; cfg_idx <= 2'd0;
                        op <= OP_CFG; tx_reg <= cfg_reg(2'd0); tx_val <= CART_BIT;
                    end else if (cfg_left != 2'd0) begin
                        op <= OP_CFG; tx_reg <= cfg_reg(cfg_idx); tx_val <= CART_BIT;
                    end else if (inj && (!probe_req_s || gap >= PROBE_GAP)) begin   // time to measure, or the check is over
                        op <= OP_PIN_CLR; tx_reg <= REG_PIN_CFG; tx_val <= 8'h00;
                    end else if (sample_pending) begin
                        op <= OP_PROBE; tx_reg <= REG_CHANNEL_SEL; tx_val <= {5'd0, CART_CH};
                    end else if (probe_req_s && !inj) begin
                        op <= OP_PIN_SET; tx_reg <= REG_PIN_CFG; tx_val <= CART_BIT;
                    end else begin
                        if (!probe_req_s) begin probe_active <= 1'b0; need_cfg <= 1'b1; end   // the pin is an analog input again
                        op <= OP_SCAN; tx_reg <= REG_CHANNEL_SEL; tx_val <= {5'd0, scan_chan}; chan <= scan_chan;
                    end
                end
                S_START: begin                        // SDA low while SCL high, then SCL low
                    case (phase)
                        3'd0: begin sda_oe <= 1'b1; phase <= 3'd1; end
                        3'd1: begin scl_oe <= 1'b1; phase <= 3'd0; bitc <= 4'd0; st <= S_BIT;
                                    tx_byte <= byte_for(step, tx_reg, tx_val); is_read <= (step >= 4'd6); last_read <= (step == 4'd7); end
                        default: phase <= 3'd0;
                    endcase
                end
                S_BIT: begin                          // 8 data bits, MSB first, SCL low->high->low per bit
                    case (phase)
                        3'd0: begin sda_oe <= is_read ? 1'b0 : ~tx_byte[7]; phase <= 3'd1; end
                        3'd1: begin scl_oe <= 1'b0; phase <= 3'd2; end
                        3'd2: begin rx <= {rx[14:0], sda_s[1]}; phase <= 3'd3; end            // sample while SCL high
                        3'd3: begin scl_oe <= 1'b1; tx_byte <= {tx_byte[6:0], 1'b1}; phase <= 3'd0;
                                    if (bitc == 4'd7) st <= S_ACK; bitc <= bitc + 4'd1; end
                    endcase
                end
                S_ACK: begin                          // 9th clock: slave ACK on writes, master ACK/NACK on reads
                    case (phase)
                        3'd0: begin sda_oe <= is_read ? ~last_read : 1'b0; phase <= 3'd1; end
                        3'd1: begin scl_oe <= 1'b0; phase <= 3'd2; end
                        3'd2: begin if (!is_read && sda_s[1]) ack_bad <= 1'b1; phase <= 3'd3; end
                        3'd3: begin scl_oe <= 1'b1; sda_oe <= 1'b0; phase <= 3'd0; bitc <= 4'd0;
                                    if (step == 4'd3 || step == 4'd7 || ack_bad) st <= S_STOP;
                                    else begin step <= (step == 4'd5) ? 4'd6 : step + 4'd1; tx_byte <= byte_for(step + 4'd1, tx_reg, tx_val);
                                                is_read <= (step + 4'd1 >= 4'd6); last_read <= (step + 4'd1 == 4'd7); st <= S_BIT; end
                        end
                    endcase
                end
                S_STOP: begin                         // SDA low, SCL high, SDA high
                    case (phase)
                        3'd0: begin sda_oe <= 1'b1; phase <= 3'd1; end
                        3'd1: begin scl_oe <= 1'b0; phase <= 3'd2; end
                        3'd2: begin sda_oe <= 1'b0; phase <= 3'd3; end
                        3'd3: begin phase <= 3'd0; st <= S_GAP; end
                    endcase
                end
                S_GAP: begin                          // after the write frame: read frame or done; after the read: evaluate
                    if (ack_bad) begin
                        error <= 1'b1; host_3v3_ok <= 1'b0; sys_5v_ok <= 1'b0; cart_5v_ok <= 1'b0; core_1v1_ok <= 1'b0;
                        chan <= 3'd0; st <= S_IDLE;
                        // the pin state is unknown now: make it analog first, and set the output up again
                        // before a check continues (probe_active stays up until the pin is known to be analog)
                        pin_dirty <= 1'b1; need_cfg <= 1'b1; inj <= 1'b0; sample_pending <= 1'b0; cfg_left <= 2'd0;
                    end else if (step == 4'd3) begin
                        if (op == OP_SCAN || op == OP_PROBE) begin
                            step <= 4'd5; st <= S_START;
                        end else begin
                            case (op)
                                OP_PIN_CLR: begin
                                    pin_dirty <= 1'b0;
                                    if (inj) begin inj <= 1'b0; sample_pending <= probe_req_s; end
                                end
                                OP_CFG:     begin cfg_left <= cfg_left - 2'd1; cfg_idx <= cfg_idx + 2'd1; end
                                OP_PIN_SET: begin inj <= 1'b1; gap <= 8'd0; end
                                default: ;
                            endcase
                            st <= S_IDLE;
                        end
                    end else if (op == OP_PROBE) begin
                        probe_code <= rx[15:4]; probe_strobe <= 1'b1; sample_pending <= 1'b0;
                        st <= S_IDLE;
                    end else begin
                        codes[chan * 16 +: 16] <= rx;
                        case (chan)
                            3'd0: host_3v3_ok <= (rx[15:4] >= HOST_MIN) && (rx[15:4] <= HOST_MAX);
                            3'd2: sys_5v_ok   <= (rx[15:4] >= SYS5_MIN) && (rx[15:4] <= SYS5_MAX);
                            3'd3: cart_5v_ok  <= (rx[15:4] >= SYS5_MIN) && (rx[15:4] <= SYS5_MAX);
                            3'd4: core_1v1_ok <= (rx[15:4] >= CORE_MIN) && (rx[15:4] <= CORE_MAX);
                            3'd5: overtemp    <= (rx[15:4] >= NTC_HOT);
                            default: ;
                        endcase
                        if (chan == 3'd7) error <= 1'b0;
                        if (inj && gap != 8'hFF) gap <= gap + 8'd1;
                        chan <= chan + 3'd1; st <= S_IDLE;
                    end
                end
                default: st <= S_IDLE;
            endcase
        end
    end
endmodule
