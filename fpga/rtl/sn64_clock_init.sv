// SPDX-License-Identifier: GPL-3.0-or-later
// Si5351A start-up, SNES region clock selection and per-region HDMI pixel clock.
//
// Programs the Si5351A over I2C from the 25 MHz housekeeping clock so that
// CLK0 = 21.4772727 MHz (NTSC SNES master), CLK1 = 21.28137 MHz (PAL) and
// CLK2 = 27.0197947 MHz (HDMI 480p pixel clock = NTSC master x 39/31, from the
// same PLLA so the HDMI raster is frequency-locked to the SNES frame), all
// from a 25 MHz crystal, then waits for both PLLs to report lock
// (register 0: SYS_INIT and LOL_A/LOL_B clear) before asserting `clocks_ready`.
// Register values are derived in docs/design/clock-plan.md (AN619 formulas).
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
// HDMI pixel clock per region (docs/design/clock-plan.md, "PAL HDMI"): after
// start-up, whenever the latched region differs from the region CLK2 is
// programmed for, and only while the SNES clock is stopped, MultiSynth 2
// (registers 58-65) and CLK2 control (register 18) are rewritten:
//   NTSC: MS2 = 31 + 31/39 from PLLA -> master x 39/31  = 27.0197947 MHz, reg 18 = 0x0F
//   PAL:  MS2 = 31 + 13/27 from PLLB -> master x 108/85 = 27.0398584 MHz, reg 18 = 0x2F
//         (PAL_LINE_MCLK = 1360, the measured SNESTang line; 1364 selects
//          MS2 = 31 + 31/54 -> master x 432/341 = 26.9605626 MHz for a core
//          with hardware-length lines)
// No other register is written after start-up: PLLA/PLLB (26-41), MS0/MS1,
// CLK0/CLK1 control, output enables (3) and PLL reset (177) keep their start-up
// values, so CLK0/CLK1 are never touched. No PLL reset is issued for an MS2
// change (AN619 register 177 resets the PLL itself; the output MultiSynth is a
// divider after the PLL). Every write of the sequence first checks that the
// SNES clock is still stopped; if it is not, the sequence stops, CLK2 is
// marked unprogrammed and the sequence is redone at the next stopped window.
// `pixel_clock_ready` is high only when CLK2 matches the latched region and (while
// the SNES clock is stopped) no change is pending; the top level holds the HDMI
// pixel domain in reset and does not start the SNES clock until it is high.
module sn64_clock_init #(
    parameter CLK_HZ = 25_000_000,
    parameter I2C_HZ = 400_000,
    parameter [6:0] SI5351_ADDR = 7'h60,
    parameter PAL_LINE_MCLK = 1360          // SNES PAL line length in master clocks the HDMI raster locks to (1360 or 1364)
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
    output reg        i2c_error,       // no ACK or lock timeout; latched until reset

    // HDMI pixel clock (Si5351 CLK2)
    output wire       pixel_clock_ready, // CLK2 programmed for region_pal, no change pending
    output reg        pixel_region_pal   // region CLK2 is programmed for (valid when pixel_clock_ready)
);
    // ------------------------------------------------------------------
    // Register table: {register, value}. Written in order, then PLL reset,
    // then outputs enabled. Values from docs/design/clock-plan.md.
    // ------------------------------------------------------------------
    localparam N_WRITES = 45;
    function automatic [15:0] table_entry(input [5:0] i);
        case (i)
            0:  table_entry = {8'd3,   8'hFF};  // disable all outputs while programming
            1:  table_entry = {8'd16,  8'h80};  // CLK0 powered down during setup
            2:  table_entry = {8'd17,  8'h80};  // CLK1
            3:  table_entry = {8'd18,  8'h80};  // CLK2
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
            // MS2: fractional 31 + 31/39 from PLLA (P1=3557 P2=29 P3=39) -> 27.0197947 MHz
            37: table_entry = {8'd58, 8'h00}; 38: table_entry = {8'd59, 8'h27};
            39: table_entry = {8'd60, 8'h00}; 40: table_entry = {8'd61, 8'h0D};
            41: table_entry = {8'd62, 8'hE5}; 42: table_entry = {8'd63, 8'h00};
            43: table_entry = {8'd64, 8'h00}; 44: table_entry = {8'd65, 8'h1D};
            default: table_entry = 16'h0000;
        endcase
    endfunction
    // After the table: reset both PLLs, power up CLK0 (MS0 integer, PLLA,
    // multisynth source, 8 mA), CLK1 (MS1 integer, PLLB) and CLK2 (MS2
    // fractional, PLLA), enable outputs 0-2.
    localparam [15:0] W_PLL_RESET = {8'd177, 8'hA0};
    localparam [15:0] W_CLK0_CTRL = {8'd16,  8'h4F};
    localparam [15:0] W_CLK1_CTRL = {8'd17,  8'h6F};
    localparam [15:0] W_CLK2_CTRL = {8'd18,  8'h0F};
    localparam [15:0] W_OE        = {8'd3,   8'hF8};

    // ------------------------------------------------------------------
    // MultiSynth 2 register sets (AN619 section 4.1.2: P1 = 128a + floor(128b/c) - 512,
    // P2 = 128b - c*floor(128b/c), P3 = c; registers 58-65 layout per AN619).
    // ------------------------------------------------------------------
    localparam [17:0] NTSC_MS2_P1 = 18'd3557;   // 31 + 31/39
    localparam [19:0] NTSC_MS2_P2 = 20'd29;
    localparam [19:0] NTSC_MS2_P3 = 20'd39;
    localparam [17:0] PAL_MS2_P1 = (PAL_LINE_MCLK == 1364) ? 18'd3529 : 18'd3517;  // 31 + 31/54 : 31 + 13/27
    localparam [19:0] PAL_MS2_P2 = (PAL_LINE_MCLK == 1364) ? 20'd26   : 20'd17;
    localparam [19:0] PAL_MS2_P3 = (PAL_LINE_MCLK == 1364) ? 20'd54   : 20'd27;
    localparam [7:0]  NTSC_CLK2_CTRL = 8'h0F;   // powered up, fractional, MS2 from PLLA, MS2 source, 8 mA
    localparam [7:0]  PAL_CLK2_CTRL  = 8'h2F;   // same with MS2_SRC (bit 5) = PLLB
    localparam N_PIX_WRITES = 9;
    generate if (PAL_LINE_MCLK != 1360 && PAL_LINE_MCLK != 1364) begin : bad_pal_line_mclk
        $error("sn64_clock_init: PAL_LINE_MCLK must be 1360 or 1364");
    end endgenerate

    function automatic [15:0] pix_entry(input [3:0] i, input pal);
        reg [17:0] p1; reg [19:0] p2, p3;
        begin
            p1 = pal ? PAL_MS2_P1 : NTSC_MS2_P1;
            p2 = pal ? PAL_MS2_P2 : NTSC_MS2_P2;
            p3 = pal ? PAL_MS2_P3 : NTSC_MS2_P3;
            case (i)
                0: pix_entry = {8'd58, p3[15:8]};
                1: pix_entry = {8'd59, p3[7:0]};
                2: pix_entry = {8'd60, 1'b0, 3'b000, 2'b00, p1[17:16]};   // R2_DIV = 1, MS2_DIVBY4 = 00
                3: pix_entry = {8'd61, p1[15:8]};
                4: pix_entry = {8'd62, p1[7:0]};
                5: pix_entry = {8'd63, p3[19:16], p2[19:16]};
                6: pix_entry = {8'd64, p2[15:8]};
                7: pix_entry = {8'd65, p2[7:0]};
                8: pix_entry = {8'd18, pal ? PAL_CLK2_CTRL : NTSC_CLK2_CTRL};
                default: pix_entry = 16'h0000;
            endcase
        end
    endfunction

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
    // until SYS_INIT (bit 7) and LOL_B/LOL_A (bits 6:5) are clear. Then keep
    // CLK2 programmed for the latched region (Q_READY <-> Q_PIX).
    // ------------------------------------------------------------------
    localparam [3:0] Q_BOOT=0, Q_TABLE=1, Q_PLLRST=2, Q_CLK0=3, Q_CLK1=4, Q_OE=5, Q_POLL=6, Q_READY=7, Q_ERROR=8, Q_CLK2=9, Q_PIX=10;
    reg [3:0] q; reg [5:0] idx; reg waiting; reg [23:0] boot_wait; reg [15:0] polls;
    reg [3:0] pidx; reg pix_target, pix_valid;
    task automatic start_write(input [15:0] w);
        begin bytes[0] <= {SI5351_ADDR,1'b0}; bytes[1] <= w[15:8]; bytes[2] <= w[7:0]; nbytes <= 3; read_mode <= 1'b0; go <= 1'b1; waiting <= 1'b1; end
    endtask
    task automatic start_read_status;
        begin bytes[0] <= {SI5351_ADDR,1'b0}; bytes[1] <= 8'd0; bytes[2] <= {SI5351_ADDR,1'b1}; nbytes <= 3; read_mode <= 1'b1; go <= 1'b1; waiting <= 1'b1; end
    endtask

`ifdef SN64_FAULT_CLK_IGNORE_STOP
    wire may_write_pix = 1'b1;              // negative test: keeps writing after the SNES clock started
`else
    wire may_write_pix = snes_clock_stopped;
`endif

    always @(posedge clk) begin
        go <= 1'b0;
        if (!reset_n) begin
            q <= Q_BOOT; idx <= 0; waiting <= 1'b0; clocks_ready <= 1'b0; i2c_error <= 1'b0;
            boot_wait <= CLK_HZ / 100; polls <= 0;           // 10 ms for the Si5351 power-on
            pidx <= 0; pix_target <= 1'b0; pix_valid <= 1'b0; pixel_region_pal <= 1'b0;
        end else if (waiting) begin
            if (!busy && !go) begin
                waiting <= 1'b0;
                if (nack) begin q <= Q_ERROR; i2c_error <= 1'b1; pix_valid <= 1'b0; end
            end
        end else case (q)
            Q_BOOT:   if (boot_wait == 0) q <= Q_TABLE; else boot_wait <= boot_wait - 1;
            Q_TABLE:  begin start_write(table_entry(idx)); if (idx == N_WRITES-1) q <= Q_PLLRST; else idx <= idx + 1; end
            Q_PLLRST: begin start_write(W_PLL_RESET); q <= Q_CLK0; end
            Q_CLK0:   begin start_write(W_CLK0_CTRL); q <= Q_CLK1; end
            Q_CLK1:   begin start_write(W_CLK1_CTRL); q <= Q_CLK2; end
            Q_CLK2:   begin start_write(W_CLK2_CTRL); q <= Q_OE; end
            Q_OE:     begin start_write(W_OE); q <= Q_POLL; end
            Q_POLL:   if (polls != 0 && (rdata[7:5] == 3'b000)) begin
                          clocks_ready <= 1'b1; q <= Q_READY;
                          pix_valid <= 1'b1; pixel_region_pal <= 1'b0;   // start-up table programs the NTSC MS2
                      end
                      else if (polls == 16'd2000) begin q <= Q_ERROR; i2c_error <= 1'b1; end
                      else begin start_read_status; polls <= polls + 1; end
            Q_READY:  if (snes_clock_stopped && (!pix_valid || pixel_region_pal != region_pal)) begin
                          q <= Q_PIX; pidx <= 0; pix_target <= region_pal; pix_valid <= 1'b0;
                      end
            Q_PIX:    if (!may_write_pix) q <= Q_READY;          // SNES clock started: stop, redo when stopped
                      else begin
                          start_write(pix_entry(pidx, pix_target));
                          if (pidx == 4'(N_PIX_WRITES - 1)) begin
                              q <= Q_READY; pix_valid <= 1'b1; pixel_region_pal <= pix_target;
                          end else pidx <= pidx + 1;
                      end
            Q_ERROR:  clocks_ready <= 1'b0;
            default:  q <= Q_ERROR;
        endcase
    end

    // pix_valid rises when the last write is issued; the transaction is
    // finished once `waiting` clears, so readiness also requires !waiting.
    // While the SNES clock is stopped a pending region change also clears
    // readiness, so the top cannot start the SNES clock on the same edge that
    // latches a new region. While it runs the region is frozen and a pending
    // (menu) change must not blank the HDMI output.
    assign pixel_clock_ready = clocks_ready && pix_valid && q == Q_READY && !waiting
                               && pixel_region_pal == region_pal
                               && !(snes_clock_stopped && region_change_pending);
endmodule
