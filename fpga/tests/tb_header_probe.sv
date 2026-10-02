`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Self-checking bench for sn64_header_probe + sn64_header_probe_mux.
//
// Cartridge models (original test data, no commercial ROM content):
//   LoROM NTSC (US, $01), HiROM PAL (EU, $02), South Korea ($0D, NTSC),
//   corrupted checksum pair (must be rejected), unknown country ($0E),
//   bad map-mode byte, absent cartridge with the bus pulled up, pulled down,
//   and floating (random each ns).
// The ROM is asynchronous: its data is only correct once address, /ROMSEL and
// /RD have been stable for T_ACC_NS (mask ROM 200 ns + two translator hops);
// before that it returns a wrong byte, so sampling too early fails the test.
//
// Checked continuously (1 ns monitor, offset half a ns from clock edges):
//   * D0-D7 never driven by the FPGA (data octet enabled with data_dir = 1),
//   * /WR, /PWR, /PARD, /WRAMSEL never asserted, SYSTEM_CLK/REFRESH/PHI2 low,
//   * no socket output enabled without probe permit or bridge permit,
//   * address >= 50 ns stable before /ROMSEL falls, /RD only inside /ROMSEL,
//     /RD low >= 200 ns, address never changes while a strobe is low,
//     /ROMSEL high >= 100 ns between reads,
//   * dropping permit mid-read releases every output within one clk_25 cycle
//     and the probe reports an aborted, invalid result.
// Mux: stale bridge data-octet state (data_dir = 1, /OE low) must not reach
// the pads while the bridge is not permitted; the bridge passes through when
// it is permitted and wins over a probe request.
//
// Defines: SN64_FAULT_SKIP_CHECKSUM (RTL fault) must make the corrupted-
// checksum case fail. TB_SHORT_ACCESS shortens the read strobe and must fail.
module tb_header_probe;
    reg clk = 0;
    always #20 clk = ~clk;                      // 25 MHz housekeeping clock
    reg reset_n = 0, enable = 0, permit = 0;

`ifdef TB_SHORT_ACCESS
    localparam integer ACCESS = 3;
`else
    localparam integer ACCESS = 10;
`endif
    localparam integer T_ACC_NS = 214;          // 200 ns mask ROM + 2 x 7 ns translators

    // ---------------- Probe ----------------
    wire [23:0] p_addr; wire p_romsel_n, p_rd_n, p_drive, p_listen;
    wire done, hvalid, hpal, aborted; wire [7:0] country, map; wire [3:0] reject;
    wire [7:0] fpga_d_in;
    sn64_header_probe #(.ACCESS_CYC(ACCESS)) dut (
        .clk(clk), .reset_n(reset_n), .enable(enable), .permit(permit),
        .cart_address(p_addr), .cart_romsel_n(p_romsel_n), .cart_rd_n(p_rd_n),
        .drive_en(p_drive), .data_listen(p_listen), .cart_data_in(fpga_d_in),
        .done(done), .header_valid(hvalid), .header_pal(hpal),
        .header_country(country), .header_map(map), .reject(reject), .aborted(aborted));

    // ---------------- Bridge stand-in (stopped SNES clock, stale state) ----------------
    reg        bridge_permit = 0;
    reg [23:0] b_addr = 24'h7E1234; reg [7:0] b_pa = 8'h21;
    reg b_rd_n = 1, b_wr_n = 0, b_prd_n = 0, b_pwr_n = 0, b_romsel_n = 0, b_wramsel_n = 0;
    reg b_refresh = 1, b_phi2 = 1, b_sysclk = 1;
    reg b_ctl_oe_n = 0, b_data_oe_n = 0, b_data_dir = 1;   // stale "driving" state
    reg idle_drive = 0;                                    // 1: the cartridge is powered, hold its pins at rest

    // ---------------- Pads ----------------
    wire [23:0] a; wire [7:0] pa;
    wire rd_n, wr_n, prd_n, pwr_n, romsel_n, wramsel_n, refresh, phi2, sysclk;
    wire ctl_oe_n, data_oe_n, data_dir, probe_owns;
    sn64_header_probe_mux mux (
        .bridge_permit(bridge_permit), .idle_drive(idle_drive),
        .b_address(b_addr), .b_pa(b_pa), .b_rd_n(b_rd_n), .b_wr_n(b_wr_n), .b_prd_n(b_prd_n), .b_pwr_n(b_pwr_n),
        .b_romsel_n(b_romsel_n), .b_wramsel_n(b_wramsel_n), .b_refresh(b_refresh), .b_phi2(b_phi2), .b_sysclk(b_sysclk),
        .b_ctl_oe_n(b_ctl_oe_n), .b_data_oe_n(b_data_oe_n), .b_data_dir(b_data_dir),
        .p_drive_en(p_drive), .p_data_listen(p_listen), .p_address(p_addr), .p_romsel_n(p_romsel_n), .p_rd_n(p_rd_n),
        .cart_address(a), .cart_pa(pa), .cart_rd_n(rd_n), .cart_wr_n(wr_n), .cart_prd_n(prd_n), .cart_pwr_n(pwr_n),
        .cart_romsel_n(romsel_n), .cart_wramsel_n(wramsel_n), .cart_refresh(refresh), .cart_phi2(phi2), .cart_sysclk(sysclk),
        .ctl_oe_n(ctl_oe_n), .data_oe_n(data_oe_n), .data_dir(data_dir), .probe_owns(probe_owns));

    // ---------------- Cartridge model ----------------
    localparam integer K_ABSENT_FF = 0, K_LOROM_US = 1, K_HIROM_EU = 2, K_CORRUPT = 3, K_ABSENT_00 = 4,
                       K_ABSENT_FLOAT = 5, K_KOREA = 6, K_UNKNOWN_CC = 7, K_BAD_MAP = 8;
    integer kind = K_ABSENT_FF;
    reg     present = 0, lorom = 1;
    reg [7:0] rom [0:131071];                   // 128 KiB
    integer i;

    task automatic fill_rom(input integer seed);
        integer s; s = seed;
        for (i = 0; i < 131072; i = i + 1) rom[i] = 8'((i * 37 + s) ^ (i >> 8));
    endtask
    // Header at ROM offset `base`: title, map, chipset, sizes, country, checksum pair.
    task automatic put_header(input integer base, input [7:0] map_b, input [7:0] cc, input [15:0] csum, input [15:0] cmpl);
        string title; title = "SN64 HEADER PROBE TEST";
        for (i = 0; i < 21; i = i + 1) rom[base + i] = title[i];
        rom[base + 'h15] = map_b; rom[base + 'h16] = 8'h02; rom[base + 'h17] = 8'h09; rom[base + 'h18] = 8'h03;
        rom[base + 'h19] = cc;    rom[base + 'h1A] = 8'h00; rom[base + 'h1B] = 8'h00;
        rom[base + 'h1C] = cmpl[7:0]; rom[base + 'h1D] = cmpl[15:8];
        rom[base + 'h1E] = csum[7:0]; rom[base + 'h1F] = csum[15:8];
    endtask

    // Mapping: LoROM ROM offset = {A22..A16, A14..A0}; HiROM = A21..A0.
    wire [16:0] rom_off = lorom ? {a[17:16], a[14:0]} : a[16:0];
    wire        cart_sees_ctl = !ctl_oe_n;      // translator octets enabled
    wire        cart_drives   = present && cart_sees_ctl && !romsel_n && !rd_n;

    reg  [7:0] a_side = 8'hFF;                  // socket D0-D7
    // FPGA side of the data translator: the socket byte while listening
    // (cartridge -> FPGA), otherwise an unrelated value.
    assign fpga_d_in = (!data_oe_n && !data_dir) ? a_side : 8'hEE;

    // ---------------- 1 ns monitor and ROM timing model ----------------
    reg [23:0] a_prev = 0; reg rs_prev = 1, rd_prev = 1, oe_prev = 1, own_prev = 0;
    integer stable_ns = 0;
    realtime t_addr_chg = 0, t_rs_fall = 0, t_rs_rise = -1000, t_rd_fall = 0;
    integer n_reads = 0, errors = 0, drive_err = 0, strobe_err = 0, permit_err = 0, timing_err = 0;
    realtime min_setup = 1e9, min_rd_low = 1e9, min_gap = 1e9;
    reg seen_rise = 0;

    task automatic err(input string msg);
        errors = errors + 1;
        if (errors <= 10) $display("ERROR @%0t: %s", $realtime, msg);
    endtask

    initial begin
        #0.5;
        forever begin
            // ---- stimulus side: asynchronous ROM ----
            if (a !== a_prev || romsel_n !== rs_prev || rd_n !== rd_prev || ctl_oe_n !== oe_prev) stable_ns = 0;
            else stable_ns = stable_ns + 1;
            if (cart_drives) a_side = (stable_ns >= T_ACC_NS) ? rom[rom_off] : (rom[rom_off] ^ 8'h5A);
            else case (kind)
                K_ABSENT_FF:    a_side = 8'hFF;
                K_ABSENT_00:    a_side = 8'h00;
                default:        a_side = 8'($urandom);   // floating bus
            endcase

            // ---- safety checks ----
            if (!bridge_permit && !data_oe_n && data_dir) begin drive_err++; err("FPGA drives D0-D7 outside bridge ownership"); end
            if (!ctl_oe_n && (!wr_n || !pwr_n)) begin strobe_err++; err("/WR or /PWR asserted"); end
            if (probe_owns && (!wr_n || !pwr_n || !prd_n || !wramsel_n || sysclk || refresh || phi2 || pa != 8'hFF))
                begin strobe_err++; err("probe owner: write/clock/PA outputs not idle"); end
            if (!idle_drive && !permit && !bridge_permit && (!ctl_oe_n || !data_oe_n || !romsel_n && !ctl_oe_n))
                begin permit_err++; err("socket enabled without permit"); end
            if (!idle_drive && !bridge_permit && !probe_owns && (!ctl_oe_n || !data_oe_n))
                begin permit_err++; err("socket enabled with no owner"); end
            if (idle_drive && !bridge_permit && !probe_owns && (ctl_oe_n || !data_oe_n || data_dir || !rd_n || !wr_n || !prd_n || !pwr_n
                                                              || !romsel_n || !wramsel_n || sysclk || refresh || phi2))
                begin permit_err++; err("socket not at rest with idle drive and no owner"); end

            // ---- strobe timing (probe-owned reads) ----
            if (probe_owns && !own_prev) t_addr_chg = $realtime;   // ownership starts: address and idle strobes applied
            else if (probe_owns) begin
                if (a !== a_prev) begin
                    if (!romsel_n || !rd_n || !rs_prev || !rd_prev) begin timing_err++; err("address changed during a strobe"); end
                    t_addr_chg = $realtime;
                end
                if (!rd_n && romsel_n) begin timing_err++; err("/RD low outside /ROMSEL"); end
                if (rs_prev && !romsel_n) begin
                    if ($realtime - t_addr_chg < min_setup) min_setup = $realtime - t_addr_chg;
                    if (seen_rise && ($realtime - t_rs_rise < min_gap)) min_gap = $realtime - t_rs_rise;
                    t_rs_fall = $realtime;
                end
                if (!rs_prev && romsel_n) begin t_rs_rise = $realtime; seen_rise = 1; end
                if (rd_prev && !rd_n) t_rd_fall = $realtime;
                if (!rd_prev && rd_n) begin
                    n_reads++;
                    if ($realtime - t_rd_fall < min_rd_low) min_rd_low = $realtime - t_rd_fall;
                end
            end else if (a !== a_prev) t_addr_chg = $realtime;

            a_prev = a; rs_prev = romsel_n; rd_prev = rd_n; oe_prev = ctl_oe_n; own_prev = probe_owns;
            #1;
        end
    end

    // ---------------- Case runner ----------------
    task automatic setup_cart(input integer k);
        kind = k;
        fill_rom(k * 101 + 7);
        present = !(k == K_ABSENT_FF || k == K_ABSENT_00 || k == K_ABSENT_FLOAT);
        case (k)
            K_LOROM_US:   begin lorom = 1; put_header('h7FC0, 8'h20, 8'h01, 16'h1234, 16'hEDCB); end
            K_HIROM_EU:   begin lorom = 0; put_header('hFFC0, 8'h31, 8'h02, 16'hA55A, 16'h5AA5);
                                // a LoROM-looking decoy where a wrong mapping would read
                                put_header('h7FC0, 8'h20, 8'h01, 16'h0F0F, 16'hF0F0); end
            K_CORRUPT:    begin lorom = 0; put_header('hFFC0, 8'h31, 8'h09, 16'hA55A, 16'h5AA4); end  // one bit off
            K_KOREA:      begin lorom = 1; put_header('h7FC0, 8'h30, 8'h0D, 16'h0000, 16'hFFFF); end
            K_UNKNOWN_CC: begin lorom = 1; put_header('h7FC0, 8'h20, 8'h0E, 16'h4321, 16'hBCDE); end
            K_BAD_MAP:    begin lorom = 0; put_header('hFFC0, 8'h24, 8'h02, 16'h4321, 16'hBCDE); end  // map mode 4 unknown
            default:      lorom = 1;
        endcase
    endtask

    // exp_rej/rej_mask: expected reject reasons {unstable, checksum, map, country} on the masked bits.
    task automatic run_case(input string name, input integer k, input bit exp_valid, input bit exp_pal, input [7:0] exp_cc,
                            input [3:0] exp_rej, input [3:0] rej_mask);
        integer t;
        setup_cart(k);
        @(posedge clk); #3; enable = 1;
        repeat (3) @(posedge clk); #5; permit = 1;
        t = 0;
        while (!done && t < 5000) begin @(posedge clk); t++; end
        #1;
        if (!done) err({name, ": probe did not finish"});
        if (aborted) err({name, ": unexpected abort"});
        if ((reject & rej_mask) !== exp_rej) err($sformatf("%s: reject=%b expected %b (mask %b)", name, reject, exp_rej, rej_mask));
        if (hvalid !== exp_valid) err($sformatf("%s: header_valid=%0d expected %0d (country %h map %h)", name, hvalid, exp_valid, country, map));
        if (exp_valid && hpal !== exp_pal) err($sformatf("%s: header_pal=%0d expected %0d", name, hpal, exp_pal));
        if (exp_valid && country !== exp_cc) err($sformatf("%s: country %h expected %h", name, country, exp_cc));
        if (probe_owns || !ctl_oe_n || !data_oe_n) err({name, ": socket not released after done"});
        $display("  %-26s valid=%0d pal=%0d country=%h map=%h reject=%b (%0d clocks)", name, hvalid, hpal, country, map, reject, t);
        // Next cartridge power-up: window closes, result clears.
        permit = 0; #2; enable = 0;
        repeat (2) @(posedge clk); #1;
        if (done || hvalid) err({name, ": result not cleared when enable dropped"});
    endtask

    realtime t_drop, t_rel;
    integer t_rest;
    initial begin
        $display("tb_header_probe: ACCESS_CYC=%0d, ROM access %0d ns", ACCESS, T_ACC_NS);
        repeat (4) @(posedge clk); reset_n = 1;

        run_case("LoROM US (NTSC)",       K_LOROM_US,     1, 0, 8'h01, 4'b0000, 4'b1111);
        run_case("HiROM EU (PAL)",        K_HIROM_EU,     1, 1, 8'h02, 4'b0000, 4'b1111);
        run_case("South Korea (NTSC)",    K_KOREA,        1, 0, 8'h0D, 4'b0000, 4'b1111);
        run_case("corrupted checksum",    K_CORRUPT,      0, 0, 8'h09, 4'b0100, 4'b1111);
        run_case("unknown country $0E",   K_UNKNOWN_CC,   0, 0, 8'h0E, 4'b0001, 4'b1111);
        run_case("bad map-mode byte",     K_BAD_MAP,      0, 0, 8'h02, 4'b0010, 4'b1111);
        run_case("absent, bus pulled up", K_ABSENT_FF,    0, 0, 8'hFF, 4'b0111, 4'b1111);
        run_case("absent, bus pulled down", K_ABSENT_00,  0, 0, 8'h00, 4'b0110, 4'b1111);
        run_case("absent, bus floating",  K_ABSENT_FLOAT, 0, 0, 8'h00, 4'b1000, 4'b1000);

        // ---- permit without enable: nothing may run or be driven ----
        setup_cart(K_LOROM_US);
        permit = 1; repeat (20) @(posedge clk); #1;
        if (probe_owns || !ctl_oe_n || !data_oe_n || done) err("probe ran or drove with permit but no enable");
        permit = 0; @(posedge clk);

        // ---- permit drop in the middle of a read ----
        @(posedge clk); #3; enable = 1; permit = 1;
        wait (!rd_n); #150;                         // inside a /RD window, between edges
        if (probe_owns !== 1 || rd_n !== 0) err("permit-drop case: not inside a read");
        t_drop = $realtime; permit = 0;
        t_rel = -1;
        for (int n = 0; n < 40; n++) begin
            #1;
            if (t_rel < 0 && ctl_oe_n && data_oe_n && !data_dir && !probe_owns && p_romsel_n && p_rd_n) t_rel = $realtime;
        end
        if (t_rel < 0 || (t_rel - t_drop) > 40.0) err($sformatf("permit drop: release took %0.1f ns", t_rel - t_drop));
        @(posedge clk); #1;
        if (!done || !aborted || hvalid) err("permit drop: expected done+aborted+invalid");
        permit = 1;                                  // permit returns in the same window: no restart
        repeat (50) @(posedge clk);
        if (probe_owns || !ctl_oe_n) err("probe restarted in the same enable window");
        $display("  %-26s released %0.1f ns after drop; aborted=%0d valid=%0d", "permit drop mid-read", t_rel - t_drop, aborted, hvalid);
        permit = 0; enable = 0; repeat (2) @(posedge clk);

        // ---- mux: bridge pass-through and priority ----
        #3;
        if (!ctl_oe_n || !data_oe_n || data_dir) err("mux: stale bridge state reached the pads without bridge permit");
        bridge_permit = 1; b_wr_n = 1; b_pwr_n = 1; b_prd_n = 1; b_wramsel_n = 1; #1;
        if (ctl_oe_n !== b_ctl_oe_n || a !== b_addr || data_dir !== b_data_dir || data_oe_n !== b_data_oe_n || sysclk !== 1)
            err("mux: bridge not passed through while permitted");
        enable = 1; permit = 1; repeat (10) @(posedge clk); #1;   // probe requests while bridge owns
        if (probe_owns || a !== b_addr) err("mux: probe won over a permitted bridge");
        permit = 0; enable = 0; bridge_permit = 0; b_data_dir = 0; #1;
        $display("  %-26s stale bridge state blocked; bridge passes when permitted and wins", "mux ownership");

        // ---- mux: pins at rest while the cartridge is powered and nobody owns the socket ----
        repeat (4) @(posedge clk); #3;
        b_wr_n = 0; b_pwr_n = 0; b_prd_n = 0; b_romsel_n = 0; b_rd_n = 0; b_sysclk = 1; b_ctl_oe_n = 0; b_data_oe_n = 0; b_data_dir = 1;
        idle_drive = 1; #1;                          // stale bridge state behind the mux, no bridge permit
        if (ctl_oe_n !== 0 || wr_n !== 1 || rd_n !== 1 || prd_n !== 1 || pwr_n !== 1 || romsel_n !== 1 || wramsel_n !== 1
            || sysclk !== 0 || phi2 !== 0 || refresh !== 0 || data_oe_n !== 1 || data_dir !== 0 || a !== 24'd0 || pa !== 8'hFF)
            err("mux: pins not at rest with idle drive and no owner");
        bridge_permit = 1; b_ctl_oe_n = 1; #1;       // bridge permitted but still in reset: rest
        if (ctl_oe_n !== 0 || wr_n !== 1 || rd_n !== 1 || romsel_n !== 1 || sysclk !== 0 || data_oe_n !== 1)
            err("mux: pins not at rest while the permitted bridge holds its octets off");
        b_ctl_oe_n = 0; b_wr_n = 1; b_pwr_n = 1; b_prd_n = 1; #1;   // bridge drives: it passes
        if (ctl_oe_n !== 0 || a !== b_addr || rd_n !== b_rd_n || romsel_n !== b_romsel_n || sysclk !== 1 || data_dir !== 1 || data_oe_n !== 0)
            err("mux: a driving bridge not passed through with idle drive on");
        bridge_permit = 0; b_data_dir = 0; #1;
        enable = 1; permit = 1;                      // the probe takes the socket from rest and gives it back to rest
        t_rest = 0;
        while (!probe_owns && t_rest < 200) begin @(posedge clk); t_rest++; end
        if (!probe_owns) err("mux: probe did not take the socket from rest");
        while (!done && t_rest < 5000) begin @(posedge clk); t_rest++; end
        #1;
        if (probe_owns || ctl_oe_n !== 0 || rd_n !== 1 || romsel_n !== 1 || wr_n !== 1 || data_oe_n !== 1)
            err("mux: pins not back at rest after the probe");
        permit = 0; enable = 0; idle_drive = 0; #1;
        if (ctl_oe_n !== 1 || data_oe_n !== 1) err("mux: pins not released when the idle drive ends");
        $display("  %-26s pins at rest with no owner; bridge and probe take and return them", "mux rest drive");

        $display("  reads=%0d  min addr->/ROMSEL %0.0f ns  min /RD low %0.0f ns  min /ROMSEL high gap %0.0f ns",
                 n_reads, min_setup, min_rd_low, min_gap);
        if (min_setup < 50.0)  err($sformatf("address setup %0.0f ns < 50 ns", min_setup));
        if (min_rd_low < 200.0) err($sformatf("/RD low %0.0f ns < 200 ns", min_rd_low));
        if (min_gap < 100.0)   err($sformatf("/ROMSEL release gap %0.0f ns < 100 ns", min_gap));
        if ((drive_err + strobe_err + permit_err + timing_err) != 0)
            err($sformatf("violations: D-drive %0d, strobe %0d, permit %0d, timing %0d", drive_err, strobe_err, permit_err, timing_err));

        if (errors != 0) begin
            $display("FAIL: tb_header_probe %0d error(s)", errors);
            $fatal(1, "tb_header_probe failed");
        end
        $display("PASS: header probe: LoROM US NTSC, HiROM EU PAL, Korea NTSC accepted; corrupt checksum, unknown country, bad map, absent (FF/00/floating) rejected; %0d reads, no D-bus drive, no /WR//PWR, permit release %0.1f ns",
                 n_reads, t_rel - t_drop);
        $finish;
    end

    initial begin #20_000_000; $display("FAIL: timeout"); $fatal(1, "timeout"); end
endmodule
