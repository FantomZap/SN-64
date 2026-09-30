// SPDX-License-Identifier: GPL-3.0-or-later
// Si5351A start-up and SNES region clock selection.
//
// Programs the Si5351A over I2C from the 25 MHz housekeeping clock so that
// CLK0 = 21.4772727 MHz (NTSC SNES master) and CLK1 = 21.28137 MHz (PAL),
// both from a 25 MHz crystal, then waits for both PLLs to report lock
// (register 0: SYS_INIT and LOL_A/LOL_B clear) before asserting `clocks_ready`.
// CLK2 is powered down and its output disabled: the SNES picture and sound go
// to the console over the cartridge bus (docs/design/console-video-path.md), so
// the board has no pixel clock. Register values are derived in
// docs/design/clock-plan.md (AN619 formulas).
//
// Region: `region_pal` selects which master clock the SNES domain uses.
// Rule: the SNES master clock starts ONCE, at power-on, already at the chosen
// frequency, and never changes while it runs. Detection (key CIC type, which
// uses its own CIC clock, and the ROM header, which needs no SNES clock) and
// any user override from the N64 menu are latched only while the SNES clock
// is stopped (`snes_clock_stopped`). A menu change therefore takes effect at
// the next cartridge power-up, never live, so a flashcart is never disturbed
// mid-game or mid-launch.
//
// No register is written after start-up: the Si5351 is never touched while
// the SNES clock runs (tb_clock_init counts I2C STARTs after clocks_ready).
module sn64_clock_init #(
    parameter CLK_HZ = 25_000_000,
    parameter I2C_HZ = 400_000,
    parameter [6:0] SI5351_ADDR = 7'h60
) (
    input  wire clk,              // 25 MHz housekeeping clock
    input  wire reset_n,

    // I2C (open drain: drive low or release)
    output wire scl_oe,           // 1 = pull SCL low
    output wire sda_oe,           // 1 = pull SDA low
    input  wire sda_in,

    // Region selection
    input  wire [1:0] region_mode,     // 0 = auto, 1 = force NTSC, 2 = force PAL
    input  wire       detected_valid,  // auto-detection has a result
    input  wire       detected_pal,    // auto-detection result
    input  wire       snes_clock_stopped, // SNES master clock not yet started (power-on detection window)
    output reg        region_pal,      // clock select for the SNES domain (0 = CLK0 NTSC, 1 = CLK1 PAL)
    output wire       region_change_pending,

    output reg        clocks_ready,    // Si5351 configured and both PLLs locked
    output reg        i2c_error        // no ACK or lock timeout; latched until reset
);
    // ------------------------------------------------------------------
    // Register table: {register, value}. Written in order, then PLL reset,
    // then outputs enabled. Values from docs/design/clock-plan.md.
    // ------------------------------------------------------------------
    localparam N_WRITES = 37;
    function automatic [15:0] table_entry(input [5:0] i);
        case (i)
            0:  table_entry = {8'd3,   8'hFF};  // disable all outputs while programming
            1:  table_entry = {8'd16,  8'h80};  // CLK0 powered down during setup
            2:  table_entry = {8'd17,  8'h80};  // CLK1
            3:  table_entry = {8'd18,  8'h80};  // CLK2: stays powered down (no pixel clock)
            4:  table_entry = {8'd183, 8'hD2};  // crystal load 10 pF
            // PLLA (MSNA): 25 MHz x (34 + 4/11) = 859.0909 MHz, P1=3886 P2=6 P3=11
            5:  table_entry = {8'd26, 8'h00}; 6:  table_entry = {8'd27, 8'h0B};
            7:  table_entry = {8'd28, 8'h00}; 8:  table_entry = {8'd29, 8'h0F};
            9:  table_entry = {8'd30, 8'h2E}; 10: table_entry = {8'd31, 8'h00};
            11: table_entry = {8'd32, 8'h00}; 12: table_entry = {8'd33, 8'h06};
            // PLLB (MSNB): 25 MHz x (34 + 3137/62500) = 851.2548 MHz, P1=3846 P2=26536 P3=62500
            13: table_entry = {8'd34, 8'hF4}; 14: table_entry = {8'd35, 8'h24};
            15: table_entry = {8'd36, 8'h00}; 16: table_entry = {8'd37, 8'h0F};
            17: table_entry = {8'd38, 8'h06}; 18: table_entry = {8'd39, 8'h00};
            19: table_entry = {8'd40, 8'h67}; 20: table_entry = {8'd41, 8'hA8};
            // MS0: integer divide by 40 (P1=4608), R0 = 1
            21: table_entry = {8'd42, 8'h00}; 22: table_entry = {8'd43, 8'h01};
            23: table_entry = {8'd44, 8'h00}; 24: table_entry = {8'd45, 8'h12};
            25: table_entry = {8'd46, 8'h00}; 26: table_entry = {8'd47, 8'h00};
            27: table_entry = {8'd48, 8'h00}; 28: table_entry = {8'd49, 8'h00};
            // MS1: integer divide by 40
            29: table_entry = {8'd50, 8'h00}; 30: table_entry = {8'd51, 8'h01};
            31: table_entry = {8'd52, 8'h00}; 32: table_entry = {8'd53, 8'h12};
            33: table_entry = {8'd54, 8'h00}; 34: table_entry = {8'd55, 8'h00};
            35: table_entry = {8'd56, 8'h00}; 36: table_entry = {8'd57, 8'h00};
            default: table_entry = 16'h0000;
        endcase
    endfunction
    // After the table: reset both PLLs, power up CLK0 (MS0 integer, PLLA,
    // multisynth source, 8 mA) and CLK1 (MS1 integer, PLLB), enable outputs
    // 0 and 1 only (register 3: 1 = disabled; CLK2-7 stay disabled).
    localparam [15:0] W_PLL_RESET = {8'd177, 8'hA0};
    localparam [15:0] W_CLK0_CTRL = {8'd16,  8'h4F};
    localparam [15:0] W_CLK1_CTRL = {8'd17,  8'h6F};
    localparam [15:0] W_OE        = {8'd3,   8'hFC};

    // ------------------------------------------------------------------
    // Minimal I2C master: byte-level write and single-register read.
    // ------------------------------------------------------------------
    localparam integer QUARTER = CLK_HZ / I2C_HZ / 4;
    reg [15:0] qcnt; wire tick = (qcnt == 0);
    always @(posedge clk) qcnt <= (!reset_n || tick) ? QUARTER-1 : qcnt - 1;

    reg scl_low, sda_low;
    assign scl_oe = scl_low;
    assign sda_oe = sda_low;

    localparam [4:0] M_IDLE=0, M_START=1, M_BIT=2, M_ACK=3, M_STOP=4, M_RBIT=5, M_RNACK=6, M_DONE=7;
    reg [4:0] mstate; reg [1:0] phase; reg [3:0] bitn;
    reg [7:0] shreg; reg [7:0] rdata; reg nack;
    reg [2:0] nbytes, byte_idx; reg [7:0] bytes [0:2]; reg read_mode, rd_restart;
    reg go, busy;

    // Byte sequence per transaction: write = {ADDR+W, REG, VALUE};
    // read = {ADDR+W, REG} + repeated start + {ADDR+R} + 1 data byte (NACK).
    always @(posedge clk) begin
        if (!reset_n) begin
            mstate <= M_IDLE; scl_low <= 1'b0; sda_low <= 1'b0; busy <= 1'b0; nack <= 1'b0;
        end else if (go && !busy) begin
            busy <= 1'b1; mstate <= M_START; phase <= 0; byte_idx <= 0; nack <= 1'b0; rd_restart <= 1'b0;
        end else if (busy && tick) begin
            case (mstate)
                M_START: case (phase)                     // SDA falls while SCL high
                    0: begin sda_low <= 1'b0; scl_low <= 1'b0; phase <= 1; end
                    1: begin sda_low <= 1'b1; phase <= 2; end
                    2: begin scl_low <= 1'b1; phase <= 3; end
                    3: begin shreg <= bytes[byte_idx]; bitn <= 7; phase <= 0; mstate <= M_BIT; end
                endcase
                M_BIT: case (phase)                       // data changes while SCL low
                    0: begin sda_low <= !shreg[7]; phase <= 1; end
                    1: begin scl_low <= 1'b0; phase <= 2; end
                    2: begin phase <= 3; end
                    3: begin scl_low <= 1'b1; shreg <= {shreg[6:0],1'b0};
                             if (bitn == 0) begin mstate <= M_ACK; phase <= 0; end else bitn <= bitn - 1;
                             phase <= 0; end
                endcase
                M_ACK: case (phase)
                    0: begin sda_low <= 1'b0; phase <= 1; end
                    1: begin scl_low <= 1'b0; phase <= 2; end
                    2: begin if (sda_in) nack <= 1'b1; phase <= 3; end
                    3: begin scl_low <= 1'b1; phase <= 0;
                             if (read_mode && byte_idx == 1 && !rd_restart) begin
                                 rd_restart <= 1'b1; byte_idx <= 2; mstate <= M_START;      // repeated start, ADDR+R
                             end else if (read_mode && rd_restart) begin
                                 bitn <= 7; mstate <= M_RBIT;
                             end else if (byte_idx + 1 == nbytes) mstate <= M_STOP;
                             else begin byte_idx <= byte_idx + 1; shreg <= bytes[byte_idx + 1]; bitn <= 7; mstate <= M_BIT; end
                       end
                endcase
                M_RBIT: case (phase)
                    0: begin sda_low <= 1'b0; phase <= 1; end
                    1: begin scl_low <= 1'b0; phase <= 2; end
                    2: begin rdata <= {rdata[6:0], sda_in}; phase <= 3; end
                    3: begin scl_low <= 1'b1; phase <= 0; if (bitn == 0) mstate <= M_RNACK; else bitn <= bitn - 1; end
                endcase
                M_RNACK: case (phase)                     // master NACK ends the read
                    0: begin sda_low <= 1'b0; phase <= 1; end
                    1: begin scl_low <= 1'b0; phase <= 2; end
                    2: begin phase <= 3; end
                    3: begin scl_low <= 1'b1; phase <= 0; mstate <= M_STOP; end
                endcase
                M_STOP: case (phase)                      // SDA rises while SCL high
                    0: begin sda_low <= 1'b1; phase <= 1; end
                    1: begin scl_low <= 1'b0; phase <= 2; end
                    2: begin sda_low <= 1'b0; phase <= 3; end
                    3: begin mstate <= M_DONE; end
                endcase
                M_DONE: begin busy <= 1'b0; mstate <= M_IDLE; end
                default: mstate <= M_IDLE;
            endcase
        end
    end

    // ------------------------------------------------------------------
    // Region selection: forced mode wins; otherwise the detection result.
    // Only applied while the SNES side is held in reset.
    // ------------------------------------------------------------------
    wire wanted_pal = (region_mode == 2'd2) ? 1'b1 :
                      (region_mode == 2'd1) ? 1'b0 :
                      (detected_valid ? detected_pal : region_pal);
    assign region_change_pending = (wanted_pal != region_pal);
    always @(posedge clk) begin
        if (!reset_n) region_pal <= 1'b0;                  // NTSC until told otherwise
        else if (snes_clock_stopped) region_pal <= wanted_pal;
    end

    // ------------------------------------------------------------------
    // Sequencer: table writes, PLL reset, clock enables, then poll register 0
    // until SYS_INIT (bit 7) and LOL_B/LOL_A (bits 6:5) are clear. After that
    // nothing is ever written again.
    // ------------------------------------------------------------------
    localparam [3:0] Q_BOOT=0, Q_TABLE=1, Q_PLLRST=2, Q_CLK0=3, Q_CLK1=4, Q_OE=5, Q_POLL=6, Q_READY=7, Q_ERROR=8;
    reg [3:0] q; reg [5:0] idx; reg waiting; reg [23:0] boot_wait; reg [15:0] polls;
    task automatic start_write(input [15:0] w);
        begin bytes[0] <= {SI5351_ADDR,1'b0}; bytes[1] <= w[15:8]; bytes[2] <= w[7:0]; nbytes <= 3; read_mode <= 1'b0; go <= 1'b1; waiting <= 1'b1; end
    endtask
    task automatic start_read_status;
        begin bytes[0] <= {SI5351_ADDR,1'b0}; bytes[1] <= 8'd0; bytes[2] <= {SI5351_ADDR,1'b1}; nbytes <= 3; read_mode <= 1'b1; go <= 1'b1; waiting <= 1'b1; end
    endtask

    always @(posedge clk) begin
        go <= 1'b0;
        if (!reset_n) begin
            q <= Q_BOOT; idx <= 0; waiting <= 1'b0; clocks_ready <= 1'b0; i2c_error <= 1'b0;
            boot_wait <= CLK_HZ / 100; polls <= 0;           // 10 ms for the Si5351 power-on
        end else if (waiting) begin
            if (!busy && !go) begin
                waiting <= 1'b0;
                if (nack) begin q <= Q_ERROR; i2c_error <= 1'b1; end
            end
        end else case (q)
            Q_BOOT:   if (boot_wait == 0) q <= Q_TABLE; else boot_wait <= boot_wait - 1;
            Q_TABLE:  begin start_write(table_entry(idx)); if (idx == N_WRITES-1) q <= Q_PLLRST; else idx <= idx + 1; end
            Q_PLLRST: begin start_write(W_PLL_RESET); q <= Q_CLK0; end
            Q_CLK0:   begin start_write(W_CLK0_CTRL); q <= Q_CLK1; end
            Q_CLK1:   begin start_write(W_CLK1_CTRL); q <= Q_OE; end
            Q_OE:     begin start_write(W_OE); q <= Q_POLL; end
            Q_POLL:   if (polls != 0 && (rdata[7:5] == 3'b000)) begin clocks_ready <= 1'b1; q <= Q_READY; end
                      else if (polls == 16'd2000) begin q <= Q_ERROR; i2c_error <= 1'b1; end
                      else begin start_read_status; polls <= polls + 1; end
            Q_READY:  ;
            Q_ERROR:  clocks_ready <= 1'b0;
            default:  q <= Q_ERROR;
        endcase
    end
endmodule
