// SN64 v2 rail and temperature monitor: one TLA2528 8-channel I2C ADC replaces
// the v1 window comparators, temperature switch and USB-C detector.
// Channel plan (hardware/sn64-v2 fpga sheet, AVDD = FPGA_3V3 is the reference,
// 12-bit left-justified data, 0.806 mV/LSB):
//   0 HOST_3V3 /2   1 USB_VBUS /3   2 5V_SYS /3   3 SNES_5V_CART /3
//   4 FPGA_1V1      5 NTC 10k/10k   6 USB CC1     7 USB CC2
// TLA2528 access (TI SBAS925, manual mode, to verify on hardware): single register
// write opcode 0x08 to CHANNEL_SEL (0x11), then an I2C read of two bytes returns
// the conversion of that channel. I2C address 0x10 with ADDR = GND.
// Thresholds are 12-bit codes on the divided inputs (fixed in logic for now;
// telemetry gets the raw codes).
// SPDX-License-Identifier: GPL-3.0-or-later
module sn64_rail_monitor #(
    parameter int CLK_HZ  = 27_000_000,
    parameter int I2C_HZ  = 100_000,
    parameter [6:0] ADDR  = 7'h10
) (
    input  wire clk,
    input  wire rst_n,
    output reg  scl_oe, sda_oe,         // 1 = pull the line low (open drain on the pads)
    input  wire sda_in,
    output reg  host_3v3_ok, sys_5v_ok, cart_5v_ok, core_1v1_ok, overtemp,
    output reg  error,                  // NACK or no scan yet
    output reg  [127:0] codes           // 8 x 16-bit raw readings, channel 0 in bits [15:0]
);
    // ---- thresholds (codes) ----
    localparam [11:0] HOST_MIN = 12'd1800, HOST_MAX = 12'd2296;   // 2.90 .. 3.70 V through /2
    localparam [11:0] SYS5_MIN = 12'd1903, SYS5_MAX = 12'd2234;   // 4.60 .. 5.40 V through /3
    localparam [11:0] CORE_MIN = 12'd1241, CORE_MAX = 12'd1489;   // 1.00 .. 1.20 V direct
    localparam [11:0] NTC_HOT  = 12'd3480;                        // ~70 C with a 10k B3950 NTC over 10k

    // ---- quarter-bit tick ----
    localparam int TICKS = CLK_HZ / (I2C_HZ * 4);
    reg [$clog2(TICKS + 1)-1:0] tdiv = '0;
    wire tick = (tdiv == TICKS - 1);
    always @(posedge clk) tdiv <= (!rst_n || tick) ? '0 : tdiv + 1'b1;

    // ---- byte-level engine: one transaction = start, N bytes (write or read), stop ----
    // Sequence per channel: [W addr][0x08][0x11][ch] stop, [R addr][hi ack][lo nack] stop.
    reg [3:0]  step;          // 0..3 write bytes, 4 restart, 5..7 read bytes, 8 stop/next
    reg [2:0]  chan;
    reg [3:0]  bitc;
    reg [2:0]  phase;         // quarter-bit phase
    reg [7:0]  shreg;
    reg        reading, busy, ack_bad;
    reg [15:0] rx;
    reg [1:0]  sda_s;
    always @(posedge clk) sda_s <= {sda_s[0], sda_in};

    localparam S_IDLE = 0, S_START = 1, S_BIT = 2, S_ACK = 3, S_STOP = 4, S_GAP = 5;
    reg [2:0] st;
    reg [7:0] tx_byte;
    reg       is_read, last_read;

    function automatic [7:0] byte_for(input [3:0] s, input [2:0] ch);
        case (s)
            4'd0: byte_for = {ADDR, 1'b0};
            4'd1: byte_for = 8'h08;          // single register write
            4'd2: byte_for = 8'h11;          // CHANNEL_SEL
            4'd3: byte_for = {5'd0, ch};
            4'd5: byte_for = {ADDR, 1'b1};
            default: byte_for = 8'hFF;       // read phases: release SDA
        endcase
    endfunction

    always @(posedge clk) begin
        if (!rst_n) begin
            st <= S_IDLE; step <= 4'd0; chan <= 3'd0; bitc <= 4'd0; phase <= 3'd0; scl_oe <= 1'b0; sda_oe <= 1'b0;
            host_3v3_ok <= 1'b0; sys_5v_ok <= 1'b0; cart_5v_ok <= 1'b0; core_1v1_ok <= 1'b0; overtemp <= 1'b0;
            error <= 1'b1; codes <= '0; ack_bad <= 1'b0; rx <= 16'd0; is_read <= 1'b0; last_read <= 1'b0; tx_byte <= 8'hFF;
        end else if (tick) begin
            case (st)
                S_IDLE: begin                         // bus idle (both released); begin the write frame
                    step <= 4'd0; ack_bad <= 1'b0; st <= S_START;
                end
                S_START: begin                        // SDA low while SCL high, then SCL low
                    case (phase)
                        3'd0: begin sda_oe <= 1'b1; phase <= 3'd1; end
                        3'd1: begin scl_oe <= 1'b1; phase <= 3'd0; bitc <= 4'd0; st <= S_BIT;
                                    tx_byte <= byte_for(step, chan); is_read <= (step >= 4'd6); last_read <= (step == 4'd7); end
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
                                    else begin step <= (step == 4'd5) ? 4'd6 : step + 4'd1; tx_byte <= byte_for(step + 4'd1, chan);
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
                S_GAP: begin                          // after the write frame: read frame; after the read: evaluate
                    if (ack_bad) begin
                        error <= 1'b1; host_3v3_ok <= 1'b0; sys_5v_ok <= 1'b0; cart_5v_ok <= 1'b0; core_1v1_ok <= 1'b0;
                        chan <= 3'd0; st <= S_IDLE;
                    end else if (step == 4'd3) begin
                        step <= 4'd5; st <= S_START;
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
                        chan <= chan + 3'd1; st <= S_IDLE;
                    end
                end
                default: st <= S_IDLE;
            endcase
        end
    end
endmodule
