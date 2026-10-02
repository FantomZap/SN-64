// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 pre-boot ROM-header region probe (clk_25 housekeeping domain).
//
// Region fallback for cartridges without a passing key CIC. Before the SNES
// master clock starts (the cartridge is powered, the interface rail is up and
// the cartridge is held in /RESET by the power sequencer), this block briefly
// owns the socket address and strobe outputs and reads the cartridge header
// at CPU $00:FFC0-$00:FFDF. Cartridge mask ROMs are asynchronous, so a read
// needs only address + /ROMSEL + /RD; no SYSTEM_CLK is generated.
//
// Header layout (fullsnes "SNES Cartridge ROM Header"; SNESdev wiki "ROM header"):
//   $FFD5 map mode  001s_mmmm, mmmm in {0,1,2,3,5,A}
//   $FFD9 country   (implies NTSC/PAL, table in country_region below)
//   $FFDC/$FFDD checksum complement (little endian) = checksum XOR $FFFF
//   $FFDE/$FFDF checksum
// The header maps to $00:FFC0 for LoROM, HiROM and ExHiROM (ExHiROM bank $00
// upper half mirrors ROM $40FFxx, where its header lives), so one window is read.
//
// Validation before the result is trusted (header_valid):
//   * the 32 bytes read identically in two passes (rejects a floating bus),
//   * checksum XOR complement == $FFFF,
//   * map-mode byte has bits 7..5 = 001 and a known map mode,
//   * the country code is in the known table (unknown codes -> not valid).
// An invalid or aborted probe reports header_valid = 0; the top level then
// falls back to its NTSC default. Priority (applied in sn64_top, not here):
// forced mode > passing key CIC > valid header > NTSC default.
//
// Safety rules (checked by fpga/tests/tb_header_probe.sv):
//   * D0-D7 are never driven: the data octet is only ever enabled in the
//     cartridge->FPGA direction (the mux below forces data_dir = 0).
//   * Nothing is driven unless `permit` is high. Every output enable and
//     strobe is ANDed with `permit` combinationally, so dropping permit
//     releases the socket immediately (no clock edge needed); the state
//     machine then aborts on the next clk_25 edge and never restarts in the
//     same enable window.
//   * /WR, /PWR, /PARD and /WRAMSEL stay deasserted (the mux drives them high
//     while the probe owns the octet); SYSTEM_CLK, REFRESH and PHI2 stay low.
//   * There is no /RESET output: /RESET stays with the power sequencer.
//
// Timing at 25 MHz (40 ns per cycle), defaults:
//   translators enabled with idle levels ENABLE_CYC (160 ns) before the first
//   address; address valid SETUP_CYC (80 ns) before /ROMSEL falls; /RD falls
//   SEL_CYC (40 ns) after /ROMSEL; /RD low ACCESS_CYC (400 ns); data captured
//   through a two-flop synchroniser, i.e. sampled 320 ns after /RD fell;
//   /RD rises HOLD_CYC (40 ns) before /ROMSEL; both high RELEASE_CYC (120 ns)
//   with the address held, then the next address. 17 cycles per byte,
//   64 reads in about 44 us.
module sn64_header_probe #(
    parameter integer ENABLE_CYC  = 4,
    parameter integer SETUP_CYC   = 2,
    parameter integer SEL_CYC     = 1,
    parameter integer ACCESS_CYC  = 10,
    parameter integer HOLD_CYC    = 1,
    parameter integer RELEASE_CYC = 3,
    parameter [23:0]  HEADER_BASE = 24'h00FFC0   // must be 32-byte aligned
) (
    input  wire        clk,            // clk_25
    input  wire        reset_n,
    input  wire        enable,         // detection window for this cartridge power-up; low clears the result
    input  wire        permit,         // hardware permission to drive the socket; drop = release now

    // Socket side (to sn64_header_probe_mux)
    output wire [23:0] cart_address,
    output wire        cart_romsel_n,
    output wire        cart_rd_n,
    output wire        drive_en,       // 1 = probe owns the address/strobe octets (ctl /OE low)
    output wire        data_listen,    // 1 = data octet enabled, cartridge -> FPGA only
    input  wire [7:0]  cart_data_in,   // asynchronous to clk

    // Result (stable until enable drops)
    output reg         done,           // probe finished (valid, invalid or aborted)
    output reg         header_valid,
    output reg         header_pal,     // meaningful only when header_valid
    output reg  [7:0]  header_country, // raw $FFD9 byte as read (telemetry)
    output reg  [7:0]  header_map,     // raw $FFD5 byte as read (telemetry)
    output reg  [3:0]  reject,         // why not valid: {unstable, checksum pair, map mode, country}
    output reg         aborted         // permit dropped before the probe finished
);
    localparam [3:0] S_IDLE = 4'd0, S_ENABLE = 4'd1, S_SETUP = 4'd2, S_SEL = 4'd3, S_STROBE = 4'd4,
                     S_HOLD = 4'd5, S_RELEASE = 4'd6, S_CHECK = 4'd7, S_DONE = 4'd8;

    localparam [7:0] C_EN  = 8'(ENABLE_CYC - 1), C_SET = 8'(SETUP_CYC - 1), C_SEL = 8'(SEL_CYC - 1),
                     C_ACC = 8'(ACCESS_CYC - 1), C_HLD = 8'(HOLD_CYC - 1), C_REL = 8'(RELEASE_CYC - 1);

    reg [3:0] state;
    reg [7:0] cnt;
    reg [4:0] idx;
    reg       pass;                 // 0 = first read, 1 = verification read
    reg       mismatch;
    reg       own_q, listen_q, romsel_q, rd_q;
    reg [7:0] hdr [0:31];
    reg [7:0] d_s1, d_s2;           // two-flop synchroniser for the asynchronous data bus

    always @(posedge clk) begin
        d_s1 <= cart_data_in;
        d_s2 <= d_s1;
    end

    // Outputs: every enable and strobe gated by permit combinationally.
    assign cart_address  = {HEADER_BASE[23:5], idx};
    assign drive_en      = permit && own_q;
    assign data_listen   = permit && listen_q;
    assign cart_romsel_n = !(permit && romsel_q);
    assign cart_rd_n     = !(permit && rd_q);

    // ------------------------------------------------------------------
    // Country code -> {known, pal}. fullsnes "Country (also implies
    // PAL/NTSC) (FFD9h)": 00 Japan/International NTSC, 01 USA/Canada NTSC,
    // 02-0C Europe/Scandinavia/Finland/Denmark/France/Holland/Spain/Germany/
    // Italy/China-HK/Indonesia PAL (06 France is SECAM, 50 Hz), 0D South
    // Korea NTSC, 0E "Common (?)" unknown, 0F Canada NTSC, 10 Brazil PAL-M
    // (60 Hz, NTSC timing), 11 Australia PAL, 12-14 "Other variation (?)".
    // Unknown codes are not trusted.
    // ------------------------------------------------------------------
    function automatic [1:0] country_region(input [7:0] c);
        case (c)
            8'h00, 8'h01, 8'h0D, 8'h0F, 8'h10:               country_region = 2'b10;  // known, NTSC
            8'h02, 8'h03, 8'h04, 8'h05, 8'h06, 8'h07, 8'h08,
            8'h09, 8'h0A, 8'h0B, 8'h0C, 8'h11:               country_region = 2'b11;  // known, PAL
            default:                                         country_region = 2'b00;  // unknown
        endcase
    endfunction

    wire [7:0]  h_map     = hdr[5'h15];
    wire [7:0]  h_country = hdr[5'h19];
    wire [15:0] h_cmpl    = {hdr[5'h1D], hdr[5'h1C]};
    wire [15:0] h_csum    = {hdr[5'h1F], hdr[5'h1E]};
`ifdef SN64_FAULT_SKIP_CHECKSUM
    // Fault injection for the testbench only: accept any checksum pair.
    // tb_header_probe must then fail on the corrupted-checksum cartridge.
    wire        sum_ok    = 1'b1;
`else
    wire        sum_ok    = ((h_cmpl ^ h_csum) == 16'hFFFF);
`endif
    wire [3:0]  mm        = h_map[3:0];
    wire        map_ok    = (h_map[7:5] == 3'b001) &&
                            (mm == 4'h0 || mm == 4'h1 || mm == 4'h2 || mm == 4'h3 || mm == 4'h5 || mm == 4'hA);
    wire [1:0]  creg      = country_region(h_country);

    wire active = (state != S_IDLE) && (state != S_DONE);

    always @(posedge clk) begin
        if (!reset_n || !enable) begin
            state <= S_IDLE; cnt <= 8'd0; idx <= 5'd0; pass <= 1'b0; mismatch <= 1'b0;
            own_q <= 1'b0; listen_q <= 1'b0; romsel_q <= 1'b0; rd_q <= 1'b0;
            done <= 1'b0; header_valid <= 1'b0; header_pal <= 1'b0;
            header_country <= 8'h00; header_map <= 8'h00; reject <= 4'h0; aborted <= 1'b0;
        end else if (active && !permit) begin
            // Outputs are already released combinationally; record the abort.
            state <= S_DONE;
            own_q <= 1'b0; listen_q <= 1'b0; romsel_q <= 1'b0; rd_q <= 1'b0;
            done <= 1'b1; header_valid <= 1'b0; aborted <= 1'b1;
        end else begin
            case (state)
                S_IDLE: if (permit) begin
                    own_q <= 1'b1;                      // enable octets with idle levels first
                    idx <= 5'd0; pass <= 1'b0; mismatch <= 1'b0;
                    cnt <= C_EN; state <= S_ENABLE;
                end
                S_ENABLE: if (cnt == 0) begin cnt <= C_SET; state <= S_SETUP; end
                          else cnt <= cnt - 8'd1;
                S_SETUP: if (cnt == 0) begin                     // address has been stable
                    romsel_q <= 1'b1; listen_q <= 1'b1;
                    cnt <= C_SEL; state <= S_SEL;
                end else cnt <= cnt - 8'd1;
                S_SEL: if (cnt == 0) begin
                    rd_q <= 1'b1; cnt <= C_ACC; state <= S_STROBE;
                end else cnt <= cnt - 8'd1;
                S_STROBE: if (cnt == 0) begin                    // capture, then end /RD
                    if (!pass) hdr[idx] <= d_s2;
                    else if (hdr[idx] != d_s2) mismatch <= 1'b1;
                    rd_q <= 1'b0; cnt <= C_HLD; state <= S_HOLD;
                end else cnt <= cnt - 8'd1;
                S_HOLD: if (cnt == 0) begin
                    romsel_q <= 1'b0; listen_q <= 1'b0;
                    cnt <= C_REL; state <= S_RELEASE;
                end else cnt <= cnt - 8'd1;
                S_RELEASE: if (cnt == 0) begin                   // both strobes high, address held
                    cnt <= C_SET;
                    if (idx == 5'd31) begin
                        idx <= 5'd0;
                        if (!pass) begin pass <= 1'b1; state <= S_SETUP; end
                        else state <= S_CHECK;
                    end else begin
                        idx <= idx + 5'd1; state <= S_SETUP;
                    end
                end else cnt <= cnt - 8'd1;
                S_CHECK: begin
                    own_q <= 1'b0;                              // release the octets
                    header_map <= h_map; header_country <= h_country;
                    header_valid <= !mismatch && sum_ok && map_ok && creg[1];
                    reject <= {mismatch, !sum_ok, !map_ok, !creg[1]};
                    header_pal <= creg[0];
                    done <= 1'b1; state <= S_DONE;
                end
                default: ;                                      // S_DONE: hold until enable drops
            endcase
        end
    end
endmodule

// ---------------------------------------------------------------------------
// Socket output owner mux (combinational, sits between sn64_console_with_bridge
// and the socket pads in sn64_top).
//
//   * The bridge owns the socket only while `bridge_permit` is high (the same
//     bus_permit & synchronised permit the bridge uses). Its data-octet state
//     is additionally gated here, because the bridge clears drive_q/listen_q
//     only on a clk_snes edge, and that clock may be stopped.
//   * The probe owns the address/strobe octets only while probe_drive_en is
//     high and the bridge is not permitted. The top must also exclude the two
//     by construction (probe permit includes !bus_permit and !snes_clk_run).
//   * While the probe owns: /WR, /PWR, /PARD, /WRAMSEL high, PA = $FF,
//     REFRESH, PHI2 and SYSTEM_CLK low, data_dir = 0 (cartridge -> FPGA).
//   * Otherwise everything is released (/OE high, data_dir 0).
// /RESET is not routed through this mux.
// ---------------------------------------------------------------------------
module sn64_header_probe_mux (
    input  wire        bridge_permit,
    input  wire        idle_drive,       // the cartridge has its 5 V: its pins are held at rest when nobody owns the socket
    // Bridge side
    input  wire [23:0] b_address,
    input  wire [7:0]  b_pa,
    input  wire        b_rd_n, b_wr_n, b_prd_n, b_pwr_n,
    input  wire        b_romsel_n, b_wramsel_n, b_refresh, b_phi2, b_sysclk,
    input  wire        b_ctl_oe_n, b_data_oe_n, b_data_dir,
    // Probe side
    input  wire        p_drive_en, p_data_listen,
    input  wire [23:0] p_address,
    input  wire        p_romsel_n, p_rd_n,
    // Pads
    output wire [23:0] cart_address,
    output wire [7:0]  cart_pa,
    output wire        cart_rd_n, cart_wr_n, cart_prd_n, cart_pwr_n,
    output wire        cart_romsel_n, cart_wramsel_n, cart_refresh, cart_phi2, cart_sysclk,
    output wire        ctl_oe_n, data_oe_n, data_dir,
    output wire        probe_owns
);
    assign probe_owns = p_drive_en && !bridge_permit;
    wire   bridge_owns = bridge_permit;
    // At rest: the cartridge is powered and neither the probe nor the bridge drives its pins (the
    // bridge is not permitted yet, or is held in reset because /RESET is still low at the socket).
    // The address and strobe octets are then driven with every strobe inactive and no clock,
    // instead of being released: a cartridge that is out of reset never sees a loose /WR, and no
    // input of a level shifter floats while its 5 V side has power. The data octet stays released.
    // Found with the board-level run (tb_board_game.sv): /RESET was let go two SNES clocks before
    // the bridge enabled the octets.
`ifdef SN64_FAULT_NO_IDLE_DRIVE               // fault injection: the pins are let go as before (tb_system must fail)
    wire   rest = 1'b0;
`else
    wire   rest = idle_drive && !probe_owns && !(bridge_owns && !b_ctl_oe_n);
`endif
    wire   quiet = probe_owns || rest;        // what the owner does not use is held inactive

    assign cart_address   = probe_owns ? p_address  : rest ? 24'd0 : b_address;
    assign cart_pa        = quiet      ? 8'hFF      : b_pa;
    assign cart_rd_n      = probe_owns ? p_rd_n     : rest ? 1'b1  : b_rd_n;
    assign cart_romsel_n  = probe_owns ? p_romsel_n : rest ? 1'b1  : b_romsel_n;
    assign cart_wr_n      = quiet      ? 1'b1       : b_wr_n;
    assign cart_pwr_n     = quiet      ? 1'b1       : b_pwr_n;
    assign cart_prd_n     = quiet      ? 1'b1       : b_prd_n;
    assign cart_wramsel_n = quiet      ? 1'b1       : b_wramsel_n;
    assign cart_refresh   = quiet      ? 1'b0       : b_refresh;
    assign cart_phi2      = quiet      ? 1'b0       : b_phi2;
    assign cart_sysclk    = quiet      ? 1'b0       : (b_sysclk & bridge_owns);

    assign ctl_oe_n  = quiet       ? 1'b0 :
                       bridge_owns ? b_ctl_oe_n : 1'b1;
    assign data_dir  = quiet       ? 1'b0 :
                       bridge_owns ? b_data_dir : 1'b0;
    assign data_oe_n = probe_owns  ? !(p_data_listen) :
                       rest        ? 1'b1 :
                       bridge_owns ? b_data_oe_n : 1'b1;
endmodule
