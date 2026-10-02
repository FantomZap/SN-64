`timescale 1ns/1fs
// SPDX-License-Identifier: GPL-3.0-or-later
// Models of the parts on the SN64 v2 board, by pin number, for the board-level simulation
// (hardware/sn64-v2/tools/make_board_sim.py writes the list that connects them as the board
// file does; fpga/tests/tb_board_game.sv plugs a cartridge and an N64 into it).
//
// Behaviour only: no voltages on the logic pins, no delays. Pin numbers and what each pin does
// are from the makers' data sheets; the board supplies only which net is on which pad. A part
// whose supply is off drives nothing.
//
// How the simulator resolves a net with several drivers (Verilator): the enabled drivers are
// ORed, and a pull acts only while no driver is enabled. A resistor to something that can be low
// is therefore written as a pull-up plus a driver of 0: any real driver of 1 wins, as it does
// against a resistor.

// ---------------- Resistors that pull ----------------
module bm_pullup   (inout wire p); pullup (p);   endmodule
module bm_pulldown (inout wire p); pulldown (p); endmodule
// To a supply that is switched: up while it is on, to 0 V while it is off.
module bm_pull_rail (inout wire p, input wire on);
    pullup (p);
    assign p = on ? 1'bz : 1'b0;
endmodule
// To a pin that only ever drives (an FPGA output): to that pin's level.
module bm_pull_to (inout wire p, input wire level);
    pullup (p);
    assign p = level ? 1'bz : 1'b0;
endmodule

// ---------------- SN74ALVC164245, 48 pins ----------------
// Two bytes between the A side (VCCA, 2.5 or 3.3 V) and the B side (VCCB, 3.3 or 5 V).
// DIR high: A to B. /OE low: on. DIR and /OE belong to the A side's supply. Pin numbers as in
// TI SCAS416 (DGG package).
// With VCCB off the B side drives nothing. What an enabled B-to-A byte then puts on its A pins
// is not stated in the data sheet: by default the model releases them; +b_off_a=0 or +b_off_a=1
// makes it drive that level, to show the logic takes either.
module bm_sn74alvc164245 (
    inout wire p1,  p2,  p3,  p5,  p6,  p8,  p9,  p11, p12, p13, p14, p16, p17, p19, p20, p22, p23, p24,
    inout wire p25, p26, p27, p29, p30, p32, p33, p35, p36, p37, p38, p40, p41, p43, p44, p46, p47, p48,
    input wire vcca_on, vccb_on
);
    wire dir1 = p1, oe1_n = p48, dir2 = p24, oe2_n = p25;
    wire on = vcca_on & vccb_on;
    wire ab1 = on & !oe1_n & dir1, ba1 = on & !oe1_n & !dir1;      // byte 1 drives its B pins / its A pins
    wire ab2 = on & !oe2_n & dir2, ba2 = on & !oe2_n & !dir2;
    // TI SCAS416Q section 10: /OE is to be high while a supply is missing. A byte that is enabled
    // while the B side has no supply breaks that rule; the board netlist collects these.
    wire rule_broken = vcca_on & !vccb_on & (!oe1_n | !oe2_n);
    integer b_off_a = -1;
    initial if (!$value$plusargs("b_off_a=%d", b_off_a)) b_off_a = -1;
    wire lv = (b_off_a == 1);
    wire un1 = vcca_on & !vccb_on & !oe1_n & !dir1 & (b_off_a >= 0);
    wire un2 = vcca_on & !vccb_on & !oe2_n & !dir2 & (b_off_a >= 0);
    // byte 1: A1..A8 = 47 46 44 43 41 40 38 37, B1..B8 = 2 3 5 6 8 9 11 12
    assign p2  = ab1 ? p47 : 1'bz;  assign p47 = ba1 ? p2  : un1 ? lv : 1'bz;
    assign p3  = ab1 ? p46 : 1'bz;  assign p46 = ba1 ? p3  : un1 ? lv : 1'bz;
    assign p5  = ab1 ? p44 : 1'bz;  assign p44 = ba1 ? p5  : un1 ? lv : 1'bz;
    assign p6  = ab1 ? p43 : 1'bz;  assign p43 = ba1 ? p6  : un1 ? lv : 1'bz;
    assign p8  = ab1 ? p41 : 1'bz;  assign p41 = ba1 ? p8  : un1 ? lv : 1'bz;
    assign p9  = ab1 ? p40 : 1'bz;  assign p40 = ba1 ? p9  : un1 ? lv : 1'bz;
    assign p11 = ab1 ? p38 : 1'bz;  assign p38 = ba1 ? p11 : un1 ? lv : 1'bz;
    assign p12 = ab1 ? p37 : 1'bz;  assign p37 = ba1 ? p12 : un1 ? lv : 1'bz;
    // byte 2: A1..A8 = 36 35 33 32 30 29 27 26, B1..B8 = 13 14 16 17 19 20 22 23
    assign p13 = ab2 ? p36 : 1'bz;  assign p36 = ba2 ? p13 : un2 ? lv : 1'bz;
    assign p14 = ab2 ? p35 : 1'bz;  assign p35 = ba2 ? p14 : un2 ? lv : 1'bz;
    assign p16 = ab2 ? p33 : 1'bz;  assign p33 = ba2 ? p16 : un2 ? lv : 1'bz;
    assign p17 = ab2 ? p32 : 1'bz;  assign p32 = ba2 ? p17 : un2 ? lv : 1'bz;
    assign p19 = ab2 ? p30 : 1'bz;  assign p30 = ba2 ? p19 : un2 ? lv : 1'bz;
    assign p20 = ab2 ? p29 : 1'bz;  assign p29 = ba2 ? p20 : un2 ? lv : 1'bz;
    assign p22 = ab2 ? p27 : 1'bz;  assign p27 = ba2 ? p22 : un2 ? lv : 1'bz;
    assign p23 = ab2 ? p26 : 1'bz;  assign p26 = ba2 ? p23 : un2 ? lv : 1'bz;
endmodule

// ---------------- SN74LVC07A, 14 pins ----------------
// Six buffers with open-drain outputs (TI SCAS595, PW package): inputs 1 3 5 9 11 13, outputs
// 2 4 6 8 10 12. A low input pulls its output low; a high input releases it.
module bm_sn74lvc07a (
    inout wire p1, p2, p3, p4, p5, p6, p8, p9, p10, p11, p12, p13,
    input wire vcc_on
);
    wire y2 = vcc_on & !p1, y4 = vcc_on & !p3, y6 = vcc_on & !p5;      // this output is pulling low
    wire y8 = vcc_on & !p9, y10 = vcc_on & !p11, y12 = vcc_on & !p13;
    assign p2  = y2  ? 1'b0 : 1'bz;
    assign p4  = y4  ? 1'b0 : 1'bz;
    assign p6  = y6  ? 1'b0 : 1'bz;
    assign p8  = y8  ? 1'b0 : 1'bz;
    assign p10 = y10 ? 1'b0 : 1'bz;
    assign p12 = y12 ? 1'b0 : 1'bz;
endmodule

// ---------------- 27 MHz oscillator, four pads: 1 enable, 2 ground, 3 output, 4 supply ----------------
module bm_osc_27mhz (
    inout wire p1, p3
);
    reg clk = 1'b0;
    always #18.518518 clk = ~clk;
    assign p3 = p1 ? clk : 1'bz;
endmodule

// ---------------- TPS3808 supervisor ----------------
// /RESET (pin 1, open drain) is held low until the supply has been good for a while, then
// released to the board's pull-up.
module bm_tps3808 (
    inout wire p1
);
    reg hold = 1'b1;
    initial #200_000 hold = 1'b0;          // 0.2 ms here; the part's own delay is 20 ms
    assign p1 = hold ? 1'b0 : 1'bz;
endmodule

// ---------------- W25Q128 flash, SOIC-8 ----------------
// 1 /CS, 2 DO (IO1), 3 /WP (IO2), 5 DI (IO0), 6 CLK, 7 /HOLD (IO3).
// The memory and the read protocol are tb_qspi_flash_model's (tb_bootrom_flash.sv).
module bm_w25q128 (
    inout wire p1, p2, p3, p5, p6, p7
);
    tb_qspi_flash_model #(.ADDR_BITS(24)) chip (.sck(p6), .cs_n(p1), .dq({p7, p3, p2, p5}));
endmodule

// ---------------- The cartridge supply ----------------
// TPS2553 switch (SOT-23-6: 1 IN, 2 GND, 3 EN, 4 /FAULT, 5 ILIM, 6 OUT), the rail it feeds, and
// the TLA2528 converter that watches the board's supplies (WQFN-16: inputs AIN0 to AIN7 on pins
// 15, 16, 1, 2, 3, 4, 5, 6; 13 SCL, 14 SDA). An input pin can be made an output: that is how the
// cartridge check feeds its test current into the rail through the rail's own divider.
// The converter's I2C side and the rail are the models of tb_cart_check.sv.
//   V_Pn       what the board puts on input pin n, in volts; a negative value marks the pin that
//              carries the switched rail's divider (R_TOP from the rail, R_BOT to ground)
//   g_load     conductance from the rail to ground through pull-ups whose line is held low
//   cartridge  0 nothing in the socket, 1 a cartridge the right way round, 2 back to front
module bm_cart_rail #(
    parameter real C_BOARD = 54.4e-6, parameter real C_CART = 22.0e-6,
    parameter real R_TOP = 20.0e3, parameter real R_BOT = 10.0e3,
    parameter real V_P15 = 0.0, parameter real V_P16 = 0.0, parameter real V_P1 = 0.0, parameter real V_P2 = 0.0,
    parameter real V_P3 = 0.0, parameter real V_P4 = 0.0, parameter real V_P5 = 0.0, parameter real V_P6 = 0.0,
    // The I2C address the board's wiring of the ADDR pin gives (TI SBAS961A table 2): 16 (0x10) with
    // the pin open. -1: a wiring the table does not list, and the model answers at no address.
    parameter int  I2C_ADDR = 16
) (
    input  wire       en,                  // TPS2553 pin 3
    inout  wire       fault_n,             // TPS2553 pin 4 (open drain)
    inout  wire       scl, sda,            // TLA2528 pins 13, 14
    input  real       g_load,
    input  wire [1:0] cartridge,
    output wire       rail_on,             // the cartridge has its 5 V
    output wire [15:0] rail_mv             // the rail in millivolts, for the bench's log
);
    localparam int RAIL_CH = (V_P15 < 0.0) ? 0 : (V_P16 < 0.0) ? 1 : (V_P1 < 0.0) ? 2 : (V_P2 < 0.0) ? 3 :
                             (V_P3 < 0.0) ? 4 : (V_P4 < 0.0) ? 5 : (V_P5 < 0.0) ? 6 : (V_P6 < 0.0) ? 7 : 8;
    initial if (RAIL_CH == 8) $fatal(1, "bm_cart_rail: no converter input carries the cartridge rail");
    real v_rail;
    // ---------------- TLA2528 ----------------
    reg [7:0] r_pin_cfg = 0, r_gpio_cfg = 0, r_gpo_drive = 0, r_gpo_value = 0, r_chan = 0;
    wire pin_hi = r_pin_cfg[RAIL_CH[2:0]] & r_gpio_cfg[RAIL_CH[2:0]] & r_gpo_drive[RAIL_CH[2:0]] & r_gpo_value[RAIL_CH[2:0]];
    wire pin_lo = r_pin_cfg[RAIL_CH[2:0]] & r_gpio_cfg[RAIL_CH[2:0]] & ~r_gpo_value[RAIL_CH[2:0]];
    localparam real AVDD = 3.3;
    initial v_rail = 0.0;
    function automatic [11:0] convert(input [2:0] ch);
        real v; integer c;
        begin
            if (int'(ch) == RAIL_CH) v = pin_hi ? AVDD : pin_lo ? 0.0 : v_rail * R_BOT / (R_TOP + R_BOT);
            else case (ch)
                3'd0: v = V_P15;
                3'd1: v = V_P16;
                3'd2: v = V_P1;
                3'd3: v = V_P2;
                3'd4: v = V_P3;
                3'd5: v = V_P4;
                3'd6: v = V_P5;
                default: v = V_P6;
            endcase
            c = $rtoi(v / AVDD * 4096.0);
            if (c > 4095) c = 4095;
            if (c < 0) c = 0;
            convert = c[11:0];
        end
    endfunction
    reg        slave_sda_oe = 0;
    reg        started = 0, addressed = 0, reading = 0, master_nack = 0;
    integer    bc = 0, nbyte = 0, conversions = 0;
    reg [7:0]  sh = 0, opcode = 0, regaddr = 0;
    reg [15:0] conv = 0;
    assign sda = slave_sda_oe ? 1'b0 : 1'bz;
    always @(negedge sda) if (scl) begin       // START
        started = 1; bc = 0; nbyte = 0; addressed = 0; reading = 0; master_nack = 0; slave_sda_oe <= 1'b0;
    end
    always @(posedge sda) if (scl) begin       // STOP
        started = 0; slave_sda_oe <= 1'b0;
    end
    always @(posedge scl) if (started) begin
        if (bc < 8) begin
            if (!(addressed && reading && nbyte > 0)) sh = {sh[6:0], sda};
            bc = bc + 1;
        end else begin
            if (addressed && reading && nbyte > 0) master_nack = sda;
            bc = 9;
        end
    end
    always @(negedge scl) if (started) begin
        if (bc == 8) begin
            if (addressed && reading && nbyte > 0) slave_sda_oe <= 1'b0;
            else begin
                if (nbyte == 0) begin
                    addressed = (I2C_ADDR >= 0) && (int'(sh[7:1]) == I2C_ADDR);
                    reading = sh[0];
                    if (addressed && reading) begin conv = {convert(r_chan[2:0]), 4'b0000}; conversions = conversions + 1; end
                end else if (addressed) begin
                    case (nbyte)
                        1: opcode = sh;
                        2: regaddr = sh;
                        3: if (opcode == 8'h08) case (regaddr)
                               8'h05: r_pin_cfg = sh;
                               8'h07: r_gpio_cfg = sh;
                               8'h09: r_gpo_drive = sh;
                               8'h0B: r_gpo_value = sh;
                               8'h11: r_chan = sh;
                               default: ;
                           endcase
                        default: ;
                    endcase
                end
                slave_sda_oe <= addressed;
            end
        end else if (bc == 9) begin
            bc = 0; nbyte = nbyte + 1;
            if (addressed && reading && !master_nack) begin slave_sda_oe <= ~conv[15]; conv = {conv[14:0], 1'b1}; end
            else slave_sda_oe <= 1'b0;
        end else if (addressed && reading && nbyte > 0) begin
            slave_sda_oe <= ~conv[15]; conv = {conv[14:0], 1'b1};
        end
    end

    // ---------------- the rail, 1 us steps ----------------
    localparam real DT = 1.0e-6;
    localparam real V5 = 5.0, I_LIM = 1.036;                        // switch: its current limit until the rail is at 5 V
    localparam real VON = 0.8, R_GOOD = 150.0;                      // cartridge the right way round
    localparam real IS = 5.0e-12, NVT = 1.05 * 0.02585, RS = 2.0;   // cartridge back to front
    real    i_div, i_load, i_sw, i_cart, i_d, g, c_tot;
    integer lim_us = 0, off_us = 0;
    reg     fault = 1'b0;
    initial begin i_cart = 0.0; i_d = 0.0; end
    always #1000 begin
        i_div = pin_hi ? (AVDD - v_rail) / R_TOP : pin_lo ? -v_rail / R_TOP : -v_rail / (R_TOP + R_BOT);
        i_load = -v_rail * g_load;
        i_sw = (en && v_rail < V5) ? I_LIM : 0.0;
        case (cartridge)
            2'd1: i_cart = (v_rail > VON) ? (v_rail - VON) / R_GOOD : 0.0;
            2'd2: begin                        // v = n Vt ln(i/Is + 1) + i Rs, solved for i
                if (i_d < 1.0e-13) i_d = 1.0e-13;
                for (int k = 0; k < 12; k++) begin
                    g = NVT * $ln(i_d / IS + 1.0) + i_d * RS - v_rail;
                    i_d = i_d - g / (NVT / (i_d + IS) + RS);
                    if (i_d < 0.0) i_d = 0.0;
                end
                i_cart = i_d;
            end
            default: i_cart = 0.0;
        endcase
        c_tot = C_BOARD + (cartridge != 2'd0 ? C_CART : 0.0);
        v_rail = v_rail + (i_div + i_load + i_sw - i_cart) * DT / c_tot;
        if (v_rail < 0.0) v_rail = 0.0;
        if (en && v_rail > V5) v_rail = V5;
        lim_us = (en && v_rail < V5 - 0.25) ? lim_us + 1 : 0;      // cannot reach 5 V: in current limit
        off_us = en ? 0 : off_us + 1;
        if (lim_us >= 7500) fault <= 1'b1;
        else if (off_us >= 7500) fault <= 1'b0;
    end
    assign fault_n = fault ? 1'b0 : 1'bz;
    assign rail_on = v_rail > 4.5;
    assign rail_mv = 16'($rtoi(v_rail * 1000.0));
endmodule

// ---------------- Cartridge sound input: one channel of the 1-bit converter's network ----------------
// The FPGA compares two pins. One carries the reference (the bias the sound rides on); the other
// the feedback output through a resistor, smoothed by a capacitor. FB_ON_COMP says the smoothed
// node is on the pair's complement pin, as the board file has it. The node moves towards the
// feedback level with the time constant TAU_NS; it is worked out once per period of the clock
// the FPGA samples the comparison with (the model of tb_game.sv, with the exact share of the way
// covered in one period). A silent cartridge: the reference is the bias alone.
module bm_sd_input #(
    parameter real TAU_NS = 10000.0, parameter real VDD = 3.3, parameter real V_REF = 1.65,
    parameter bit  FB_ON_COMP = 1'b1
) (
    input  wire clk,                       // the clock the FPGA samples the comparison with
    input  wire fb,
    output wire cmp
);
    real v = 0.0, t_last = -1.0, share = 0.0;
    always @(posedge clk) begin
        if (t_last >= 0.0 && share == 0.0) share = 1.0 - $exp(-($realtime - t_last) / TAU_NS);
        t_last = $realtime;
        v <= v + ((fb ? VDD : 0.0) - v) * share;
    end
    wire above = v > V_REF;                // the smoothed node is above the reference
    assign cmp = FB_ON_COMP ? !above : above;
endmodule
