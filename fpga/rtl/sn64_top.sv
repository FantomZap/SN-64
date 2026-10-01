// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 FPGA top level (technology-independent).
//
// Clock domains (see docs/design/clock-plan.md):
//   clk_25   25 MHz oscillator: power sequencer, Si5351 start-up, SNES CIC lock
//   clk_host 62.5 MHz (PLL from clk_25), always on: N64 endpoint and N64 CIC,
//            and the I2S receiver that oversamples the cartridge-audio ADC
//   clk_snes Si5351 output (NTSC or PAL master), started once at power-on:
//            SNES core, cartridge bridge, controller emulation. On the v2 board
//            it comes from sn64_clock_pace, which can slow it by the amount the
//            N64 program writes to PACE (snes_pace here; docs/design/frame-lock.md)
// The board wrapper owns the PLL, the SNES clock select/gate (driven by
// snes_clk_run and region_pal), pads and translator/rail control pins.
//
// Power-on flow: Si5351 programmed -> N64 bootstrap requests the cartridge ->
// cartridge 5 V and interface rail up with /RESET held -> SNES CIC lock
// identifies the key (region) on its own clock -> SNES master clock started
// once at the chosen frequency -> /RESET released -> bus permitted.
// A region is never changed while the SNES clock runs, and a soft reset never
// removes cartridge power (a flashcart keeps its loaded game).
module sn64_top #(
    parameter [15:0] BUILD_ID = 16'h0001,
    parameter        ROM_ADDR_BITS = 16,          // N64 bootstrap window, 16-bit words
    parameter        ROM_FROM_FLASH = 0,          // 1: bootstrap ROM from the configuration flash (docs/design/bootrom-flash.md)
    parameter [23:0] FLASH_OFFSET = 24'h40_0000,  // flash byte address of the bootstrap image
    parameter        FLASH_USE_USRMCLK = 1,       // ECP5 USRMCLK drives MCLK; 0 only for simulation with a flash model
    parameter        CLK25_HZ = 25_000_000,
    parameter        REGION_TIMEOUT_MS = 300,      // give up waiting for a key CIC
    parameter        SEQ_RESET_HOLD_MS = 20,
    parameter        SEQ_RAIL_TIMEOUT_MS = 50,
    parameter        SEQ_PROBE_ENABLE = 0,         // 1: cartridge check before 5 V (needs sn64_rail_monitor on the board)
    parameter        SEQ_PROBE_TIMEOUT_MS = 4000,  // assumed: time for the test current to charge the rail
    parameter [11:0] SEQ_PROBE_OK_CODE = 12'd269,  // assumed: 0.65 V on the rail (code x 3 x 0.806 mV)
    parameter        PACE_PRESENT = 0,             // 1: the board makes clk_snes with sn64_clock_pace (FEATURES bit 0)
    parameter        CIC_LOCK_CLK_DIV = 8,         // 25 MHz / 8 = 3.125 MHz CIC_CLK, 50 % duty (key follows the lock's clock)
    parameter        CIC_LOCK_T_PWRUP = 49605      // lock start-up wait (instruction cycles)
) (
    input  wire        clk_25, clk_host, clk_snes,
    input  wire        por_n,                      // board power-on reset / FPGA configured

    // ---------------- N64 / M64 cartridge edge ----------------
    input  wire        n64_reset_n, n64_nmi_n,
    input  wire        n64_alel, n64_aleh, n64_read_n, n64_write_n,
    inout  wire [15:0] n64_ad,
    input  wire        n64_cic_clk, n64_si_clk,
    inout  wire        n64_cic_dq,

    // ---------------- Bootstrap ROM load (programmer path) ----------------
    input  wire        rom_we,
    input  wire [ROM_ADDR_BITS-1:0] rom_waddr,
    input  wire [15:0] rom_wdata,
    // ---------------- Configuration flash (ROM_FROM_FLASH = 1) ----------------
    output wire        flash_sck,                  // only with FLASH_USE_USRMCLK = 0 (simulation); hardware SCK is MCLK via USRMCLK
    output wire        flash_cs_n,                 // CSSPIN
    inout  wire [3:0]  flash_dq,                   // MOSI/D0, MISO/D1, D2/WP#, D3/HOLD#

    // ---------------- Si5351 I2C and SNES clock control ----------------
    input  wire        ext_spi_sel_req, ext_spi_sck, ext_spi_cs_n, ext_spi_mosi,   // v2 USB programmer
    output wire        ext_spi_miso, ext_spi_active,
    input  wire        pll_locked,                 // board: every PLL locked (v2: no external clock chip)
    input  wire        monitor_error,              // board: telemetry ADC not answering
    output reg         snes_clk_run,               // board: start the SNES master clock domain
    output wire        region_pal,                 // board: 0 = NTSC PLL, 1 = PAL PLL (frozen while the SNES clock runs)
    output wire [15:0] snes_pace,                  // board: PACE for sn64_clock_pace (clk_host domain; 0 = full speed)

    // ---------------- Power monitors and enables ----------------
    input  wire        host_3v3_ok, fpga_rails_ok, cart_5v_ok, iface_rail_ok, efuse_fault_n, overtemp,
    output wire        cart_5v_enable, iface_rail_enable,
    // Cartridge check before 5 V (SEQ_PROBE_ENABLE = 1). Synchronous to clk_25: the board runs
    // sn64_rail_monitor on the same clock. Without the check tie the three inputs to 0.
    output wire        cart_probe_req,
    input  wire        cart_probe_active, cart_probe_strobe,
    input  wire [11:0] cart_probe_code,

    // ---------------- SNES socket (through translators) ----------------
    output wire [23:0] cart_address,
    output wire [7:0]  cart_pa,
    output wire        cart_rd_n, cart_wr_n, cart_prd_n, cart_pwr_n,
    output wire        cart_romsel_n, cart_wramsel_n, cart_refresh, cart_phi2, cart_sysclk,
    output wire [7:0]  cart_data_out,
    input  wire [7:0]  cart_data_in,
    input  wire        cart_irq_n, cart_reset_n_sense,
    output wire        cart_reset_pull,            // 1 = open-drain pull of socket /RESET
    output wire        ctl_oe_n, data_oe_n, data_dir,
    // SNES CIC lines
    output wire        snes_cic_oe_n,              // U206 enable: CIC_CLK, CIC_SLAVE_RESET, SYSTEM_CLK octet
    output wire        snes_cic_clk, snes_cic_slave_reset,
    output wire        snes_cic_data0_o, snes_cic_data0_oe,
    input  wire        snes_cic_data0_i,
    output wire        snes_cic_data1_o, snes_cic_data1_oe,
    input  wire        snes_cic_data1_i,

    // ---------------- Cartridge-audio ADC (I2S master, asynchronous) ----------------
    input  wire        aud_l_cmp, aud_r_cmp,       // cartridge-audio sigma-delta comparators (sn64_sd_adc)
    output wire        aud_l_fb, aud_r_fb,

    // ---------------- Diagnostics ----------------
    output wire [15:0] status_word
);
    // =====================================================================
    // Reset synchronisers
    // =====================================================================
    wire rst25_n, rsthost_n;
    sn64_sync_bit #(1'b0) s_rst25   (.clk(clk_25),   .d(por_n), .q(rst25_n));
    sn64_sync_bit #(1'b0) s_rsthost (.clk(clk_host), .d(por_n), .q(rsthost_n));

    // =====================================================================
    // N64 endpoint (clk_host, always on)
    // =====================================================================
    wire [15:0] joy1_h, joy2_h, seq_h; wire [7:0] stick_x_h, stick_y_h;
    wire run_req_h, soft_reset_h; wire [1:0] region_mode_h, check_mode_h;
    wire [15:0] status_h, fault_h, cart_check_h, region_info_h, region_source_h;
    wire n64_cic_invalid_region; wire [3:0] n64_cic_step;
    // SNES-domain signals the endpoint's frame window consumes (declared here for the synthesis
    // front-end; produced further down by the core, the audio mixer and the reset synchroniser)
    wire core_reset_n, region_pal_s;
    wire [14:0] snes_rgb; wire snes_hde, snes_vde, snes_high_res, snes_interlace; wire [8:0] snes_video_x, snes_video_y;
    wire [15:0] mix_audio_left, mix_audio_right; wire mix_audio_ready;
    sn64_n64_endpoint #(.ROM_ADDR_BITS(ROM_ADDR_BITS), .ROM_FROM_FLASH(ROM_FROM_FLASH),
                        .FLASH_OFFSET(FLASH_OFFSET), .FLASH_USE_USRMCLK(FLASH_USE_USRMCLK)) endpoint (
        .clk(clk_host), .reset(!rsthost_n), .cic_cpu_clk(clk_host),
        .n64_reset(n64_reset_n), .n64_nmi(n64_nmi_n),
        .n64_pi_alel(n64_alel), .n64_pi_aleh(n64_aleh), .n64_pi_read(n64_read_n), .n64_pi_write(n64_write_n),
        .n64_pi_ad(n64_ad),
        .rom_we(rom_we), .rom_waddr(rom_waddr), .rom_wdata(rom_wdata),
        .flash_sck(flash_sck), .flash_cs_n(flash_cs_n), .flash_dq(flash_dq),
        .ext_spi_sel_req(ext_spi_sel_req), .ext_spi_sck(ext_spi_sck), .ext_spi_cs_n(ext_spi_cs_n), .ext_spi_mosi(ext_spi_mosi),
        .ext_spi_miso(ext_spi_miso), .ext_spi_active(ext_spi_active),
        .joy1_buttons(joy1_h), .joy2_buttons(joy2_h), .joy1_stick_x(stick_x_h), .joy1_stick_y(stick_y_h),
        .run_request(run_req_h), .soft_reset(soft_reset_h), .region_mode(region_mode_h), .mailbox_seq(seq_h),
        .cart_check_mode(check_mode_h), .cart_check(cart_check_h), .pace_rate(snes_pace),
        .status_flags(status_h), .fault_flags(fault_h), .build_id(BUILD_ID),
        .features({14'd0, 1'b1, PACE_PRESENT ? 1'b1 : 1'b0}),   // [1] FRAME_PHASE exists, [0] PACE works
        .region_info(region_info_h), .region_source(region_source_h),
        .clk_snes(clk_snes), .rst_snes_n(core_reset_n),
        .video_rgb(snes_rgb), .video_hde(snes_hde), .video_vde(snes_vde), .video_x(snes_video_x), .video_y(snes_video_y),
        .video_high_res(snes_high_res), .video_interlace(snes_interlace), .video_pal(region_pal_s),
        .audio_left(mix_audio_left), .audio_right(mix_audio_right), .audio_ready(mix_audio_ready),
        .n64_cic_clk(n64_cic_clk), .n64_cic_dq(n64_cic_dq), .n64_si_clk(n64_si_clk), .cic_region(region_pal),
        .cic_invalid_region(n64_cic_invalid_region), .cic_step(n64_cic_step),
        .host_reset_event(), .host_nmi_event());

    // =====================================================================
    // Housekeeping domain (clk_25): requests from the host, host reset
    // =====================================================================
    // One word, so the request and the check mode it was written with arrive together.
    wire [5:0] ctl_25;
    sn64_cdc_word #(.W(6)) x_ctl (.src_clk(clk_host), .src_data({check_mode_h, region_mode_h, soft_reset_h, run_req_h}),
                                  .dst_clk(clk_25), .dst_data(ctl_25));
    wire run_req_25 = ctl_25[0], soft_reset_25 = ctl_25[1];
    wire [1:0] region_mode_25 = ctl_25[3:2];
    wire [1:0] check_mode_25 = ctl_25[5:4];
    wire host_reset_n_25, cart_reset_sense_25;
    sn64_sync_bit #(1'b0) s_hreset (.clk(clk_25), .d(n64_reset_n), .q(host_reset_n_25));
    sn64_sync_bit #(1'b0) s_creset (.clk(clk_25), .d(cart_reset_n_sense), .q(cart_reset_sense_25));

    // =====================================================================
    // Clocks ready (v2: PLL lock from the board) and monitor health (clk_25)
    // =====================================================================
    wire clocks_ready, i2c_error;
    sn64_sync_bit #(1'b0) s_pll_lock (.clk(clk_25), .d(pll_locked), .q(clocks_ready));
    sn64_sync_bit #(1'b0) s_mon_err  (.clk(clk_25), .d(monitor_error), .q(i2c_error));
    wire cic_region_valid, cic_region_pal, cic_key_ok, cic_key_fail;
    wire det_valid, det_pal;                     // combined key CIC / ROM header / NTSC-default result

    // =====================================================================
    // Power sequencer (clk_25)
    // =====================================================================
    wire seq_reset_pull, bus_permit, fault_latched; wire [3:0] seq_state; wire [7:0] fault_code;
    wire probe_done, probe_pass; wire [1:0] probe_mode_q; wire [7:0] probe_level;
    reg  release_ok;
    sn64_power_sequencer #(.CLK_HZ(CLK25_HZ), .RESET_HOLD_MS(SEQ_RESET_HOLD_MS), .RAIL_TIMEOUT_MS(SEQ_RAIL_TIMEOUT_MS),
                           .PROBE_ENABLE(SEQ_PROBE_ENABLE), .PROBE_TIMEOUT_MS(SEQ_PROBE_TIMEOUT_MS),
                           .PROBE_OK_CODE(SEQ_PROBE_OK_CODE)) sequencer (
        .clk(clk_25), .reset_n(rst25_n),
        .configured(clocks_ready), .host_3v3_ok(host_3v3_ok), .fpga_rails_ok(fpga_rails_ok),
        .cart_5v_ok(cart_5v_ok), .iface_rail_ok(iface_rail_ok), .efuse_fault_n(efuse_fault_n),
        .overtemp(overtemp), .host_reset_n(host_reset_n_25),
        .run_request(run_req_25), .fault_clear(!run_req_25), .release_ok(release_ok), .hold_reset(soft_reset_25),
        .probe_mode(check_mode_25), .probe_req(cart_probe_req), .probe_active(cart_probe_active),
        .probe_strobe(cart_probe_strobe), .probe_code(cart_probe_code),
        .probe_done(probe_done), .probe_pass(probe_pass), .probe_mode_q(probe_mode_q), .probe_level(probe_level),
        .cart_5v_enable(cart_5v_enable), .iface_rail_enable(iface_rail_enable), .cart_reset_pull(seq_reset_pull),
        .bus_permit(bus_permit), .fault_latched(fault_latched), .state(seq_state), .fault_code(fault_code));

    // =====================================================================
    // SNES CIC lock (clk_25 / CLK_DIV -> CIC_CLK): runs once the cartridge
    // and interface rail are up, before the SNES master clock starts, and
    // reports the key's region.
    // =====================================================================
    wire cic_enable = (seq_state >= 4'd3) && (seq_state <= 4'd4);   // IFACE or RUN
    assign snes_cic_oe_n = !cic_enable;                              // enabled from IFACE, before the SNES clock
    reg [3:0] seed_counter = 4'd0;                                   // stream-select nibble, sampled at key reset
    always @(posedge clk_25) seed_counter <= seed_counter + 4'd1;
    sn64_snes_cic_lock #(.CLK_DIV(CIC_LOCK_CLK_DIV), .T_PWRUP(CIC_LOCK_T_PWRUP)) snes_cic (
        .clk(clk_25), .reset_n(rst25_n), .enable(cic_enable), .enforce(1'b0),
        .default_pal(1'b0), .seed(seed_counter),
        .cic_clk(snes_cic_clk), .slave_reset(snes_cic_slave_reset),
        .data0_o(snes_cic_data0_o), .data0_oe(snes_cic_data0_oe), .data0_i(snes_cic_data0_i),
        .data1_o(snes_cic_data1_o), .data1_oe(snes_cic_data1_oe), .data1_i(snes_cic_data1_i),
        .console_run(), .key_ok(cic_key_ok), .key_fail(cic_key_fail),
        .region_valid(cic_region_valid), .region_pal(cic_region_pal), .rounds_done(), .phase());

    // =====================================================================
    // ROM-header region probe (clk_25): reads $00:FFC0-$00:FFDF through the
    // socket translators before the SNES clock starts, with the cartridge
    // held in /RESET (docs/design/header-region-probe.md). Auto mode only.
    // =====================================================================
    wire hdr_enable = (seq_state >= 4'd3) && (seq_state <= 4'd4) && (region_mode_25 == 2'd0);   // IFACE or RUN
    wire hdr_permit = (seq_state == 4'd3) && !snes_clk_run && !bus_permit && cart_5v_ok && iface_rail_ok
                      && seq_reset_pull;                                // cartridge held in /RESET
    wire hdr_drive_en, hdr_listen, hdr_romsel_n, hdr_rd_n, hdr_owns; wire [23:0] hdr_address;
    wire hdr_done, hdr_valid, hdr_pal, hdr_aborted; wire [7:0] hdr_country, hdr_map; wire [3:0] hdr_reject;
    sn64_header_probe header_probe (
        .clk(clk_25), .reset_n(rst25_n), .enable(hdr_enable), .permit(hdr_permit),
        .cart_address(hdr_address), .cart_romsel_n(hdr_romsel_n), .cart_rd_n(hdr_rd_n),
        .drive_en(hdr_drive_en), .data_listen(hdr_listen), .cart_data_in(cart_data_in),
        .done(hdr_done), .header_valid(hdr_valid), .header_pal(hdr_pal),
        .header_country(hdr_country), .header_map(hdr_map), .reject(hdr_reject), .aborted(hdr_aborted));

    // =====================================================================
    // SNES clock start (once per cartridge power-up) and reset release
    // =====================================================================
    localparam integer REGION_TICKS = CLK25_HZ / 1000 * REGION_TIMEOUT_MS;
    localparam integer SETTLE_TICKS = CLK25_HZ / 1000;               // 1 ms of running clock before release
    reg [31:0] region_timer, settle_timer;
    // Priority: forced mode > passing key CIC > valid ROM header > NTSC default.
    // Without a passing key the decision waits for the header probe; the
    // region timeout bounds both.
    wire region_timeout = (region_timer >= REGION_TICKS);
    wire key_settled    = cic_region_valid || cic_key_fail || region_timeout;
    assign det_valid    = cic_region_valid || (key_settled && (hdr_done || region_timeout));
    assign det_pal      = cic_region_valid ? cic_region_pal : ((hdr_done && hdr_valid) ? hdr_pal : 1'b0);
    wire region_decided = (region_mode_25 != 2'd0) || det_valid;
    // Decision source, same priority as above (REGION_SOURCE[1:0]).
    wire [1:0] region_src = (region_mode_25 != 2'd0)  ? 2'd0 :     // forced by CONTROL
                            cic_region_valid          ? 2'd1 :     // passing key CIC
                            (hdr_done && hdr_valid)   ? 2'd2 :     // valid ROM header
                                                        2'd3;      // NTSC default (no key, no valid header, or timeout)
    // Region telemetry snapshot, taken on the clk_25 edge that starts the SNES
    // clock (the same edge on which sn64_clock_init latches region_pal from
    // the same inputs). Kept until the next cartridge start; before the
    // first decision the header fields are live and `decided` is 0.
    reg        rgn_decided = 1'b0, rgn_timeout = 1'b0, rgn_pal = 1'b0;
    reg [1:0]  rgn_src = 2'd0;
    reg [15:0] rgn_hdr = 16'd0;
    assign region_pal = rgn_pal;                 // latched on the edge that starts the SNES clock
    wire [15:0] hdr_word = {hdr_aborted, hdr_pal, hdr_valid, hdr_done, hdr_reject, hdr_country};
    wire rgn_wanted_pal = (region_mode_25 == 2'd2) ? 1'b1 : (region_mode_25 == 2'd1) ? 1'b0 : det_pal;
    always @(posedge clk_25) begin
        if (!rst25_n || seq_state == 4'd0 || seq_state >= 4'd5) begin   // OFF, SHUTDOWN, FAULT: clock stops
            snes_clk_run <= 1'b0; release_ok <= 1'b0; region_timer <= 0; settle_timer <= 0;
        end else begin
            if (seq_state == 4'd3 && !snes_clk_run) begin
                region_timer <= region_timer + 1;
                if (clocks_ready && region_decided) begin
                    snes_clk_run <= 1'b1;
                    rgn_decided <= 1'b1; rgn_src <= region_src; rgn_timeout <= region_timeout;
                    rgn_pal <= rgn_wanted_pal; rgn_hdr <= hdr_word;
                end
            end
            if (snes_clk_run) begin
                if (settle_timer >= SETTLE_TICKS) release_ok <= 1'b1; else settle_timer <= settle_timer + 1;
            end
        end
    end

    // =====================================================================
    // SNES domain: console core, cartridge bridge, controllers
    // =====================================================================
    // Permission: asynchronous removal (combinational OE release inside the
    // bridge) plus synchronised assertion.
    wire permit_s;
    sn64_sync_bit #(1'b0) s_permit (.clk(clk_snes), .d(bus_permit), .q(permit_s));
    wire bridge_permit = bus_permit & permit_s;
    // Core reset follows the socket /RESET level (our pull or the cartridge's).
    sn64_sync_bit #(1'b0) s_core_rst (.clk(clk_snes), .d(cart_reset_n_sense & bus_permit), .q(core_reset_n));

    wire [15:0] snes_audio_left, snes_audio_right; wire snes_audio_ready;
    wire [15:0] joy1_s, joy2_s;
    sn64_cdc_word #(.W(16)) x_joy1 (.src_clk(clk_host), .src_data(joy1_h), .dst_clk(clk_snes), .dst_data(joy1_s));
    sn64_cdc_word #(.W(16)) x_joy2 (.src_clk(clk_host), .src_data(joy2_h), .dst_clk(clk_snes), .dst_data(joy2_s));
    wire [1:0] joy1_di, joy2_di; wire joy_strobe, joy1_clock, joy2_clock;
    sn64_snes_joypad pads (.clk(clk_snes), .joy1_buttons(joy1_s), .joy2_buttons(joy2_s), .pad_present(2'b11),
        .joy_strobe(joy_strobe), .joy1_clock(joy1_clock), .joy2_clock(joy2_clock),
        .joy1_di(joy1_di), .joy2_di(joy2_di));

    sn64_sync_bit #(1'b0) s_pal (.clk(clk_snes), .d(region_pal), .q(region_pal_s));
    wire bridge_reset_pull_n;
    wire [23:0] br_address; wire [7:0] br_pa;
    wire br_rd_n, br_wr_n, br_prd_n, br_pwr_n, br_romsel_n, br_wramsel_n, br_refresh, br_phi2, br_sysclk;
    wire br_ctl_oe_n, br_data_oe_n, br_data_dir;
    sn64_console_with_bridge console (
        .clk(clk_snes), .reset_n(core_reset_n), .enable(1'b1), .pal(region_pal_s), .bus_permit(bridge_permit),
        .cart_address(br_address), .cart_pa(br_pa), .cart_rd_n(br_rd_n), .cart_wr_n(br_wr_n),
        .cart_prd_n(br_prd_n), .cart_pwr_n(br_pwr_n), .cart_romsel_n(br_romsel_n), .cart_wramsel_n(br_wramsel_n),
        .cart_refresh(br_refresh), .cart_phi2(br_phi2), .cart_sysclk(br_sysclk),
        .cart_data_out(cart_data_out), .cart_data_in(cart_data_in), .cart_irq_n(cart_irq_n),
        .cart_reset_n_sense(cart_reset_n_sense), .cart_reset_pull_n(bridge_reset_pull_n),
        .ctl_oe_n(br_ctl_oe_n), .data_oe_n(br_data_oe_n), .data_dir(br_data_dir), .contention_guard(),
        .joy1_di(joy1_di), .joy2_di(joy2_di), .joy_strobe(joy_strobe), .joy1_clock(joy1_clock), .joy2_clock(joy2_clock),
        .rgb(snes_rgb), .hsync(), .vsync(), .hde(snes_hde), .vde(snes_vde), .dot_clock(),
        .high_res(snes_high_res), .field(), .interlace(snes_interlace), .video_x(snes_video_x), .video_y(snes_video_y),
        .audio_left(snes_audio_left), .audio_right(snes_audio_right), .audio_ready(snes_audio_ready));

    // Socket owner mux: the bridge while bus-permitted, the header probe only
    // before the SNES clock starts, otherwise released. The mux also gates the
    // bridge's data-octet state with bridge_permit (the bridge clears it only
    // on a clk_snes edge, which may never come once the clock is stopped).
    sn64_header_probe_mux socket_mux (
        .bridge_permit(bridge_permit),
        .b_address(br_address), .b_pa(br_pa), .b_rd_n(br_rd_n), .b_wr_n(br_wr_n), .b_prd_n(br_prd_n), .b_pwr_n(br_pwr_n),
        .b_romsel_n(br_romsel_n), .b_wramsel_n(br_wramsel_n), .b_refresh(br_refresh), .b_phi2(br_phi2), .b_sysclk(br_sysclk),
        .b_ctl_oe_n(br_ctl_oe_n), .b_data_oe_n(br_data_oe_n), .b_data_dir(br_data_dir),
        .p_drive_en(hdr_drive_en), .p_data_listen(hdr_listen), .p_address(hdr_address),
        .p_romsel_n(hdr_romsel_n), .p_rd_n(hdr_rd_n),
        .cart_address(cart_address), .cart_pa(cart_pa), .cart_rd_n(cart_rd_n), .cart_wr_n(cart_wr_n),
        .cart_prd_n(cart_prd_n), .cart_pwr_n(cart_pwr_n), .cart_romsel_n(cart_romsel_n), .cart_wramsel_n(cart_wramsel_n),
        .cart_refresh(cart_refresh), .cart_phi2(cart_phi2), .cart_sysclk(cart_sysclk),
        .ctl_oe_n(ctl_oe_n), .data_oe_n(data_oe_n), .data_dir(data_dir), .probe_owns(hdr_owns));

    // =====================================================================
    // Cartridge audio (docs/design/cart-audio-implementation.md): the ADC's
    // I2S lines are oversampled by clk_host (always on, 30x BCK); each stereo
    // frame crosses to clk_snes through the mixer's toggle synchroniser and
    // elastic buffer and is added (saturating) to the core's DSP samples. The
    // mixed stream feeds the endpoint's frame window (audio ring the console
    // reads over the cartridge bus, docs/design/console-video-path.md).
    // =====================================================================
    wire signed [23:0] adc_left_h, adc_right_h;
    wire adc_tog_h, adc_locked_h; wire [15:0] adc_frame_errors_h;
    sn64_sd_adc adc_rx (.clk(clk_host), .rst_n(rsthost_n), .cmp_l(aud_l_cmp), .cmp_r(aud_r_cmp), .fb_l(aud_l_fb), .fb_r(aud_r_fb),
        .left(adc_left_h), .right(adc_right_h), .frame_tog(adc_tog_h), .frame_stb(),
        .locked(adc_locked_h), .frame_errors(adc_frame_errors_h));
    wire [15:0] audio_ovf_slips, audio_unf_slips; wire cart_audio_active;
    sn64_audio_mix audio_mix (.clk(clk_snes), .rst_n(core_reset_n), .cart_enable(1'b1),
        .adc_left(adc_left_h), .adc_right(adc_right_h), .adc_tog(adc_tog_h), .adc_locked(adc_locked_h),
        .snes_left(snes_audio_left), .snes_right(snes_audio_right), .snes_ready(snes_audio_ready),
        .mix_left(mix_audio_left), .mix_right(mix_audio_right), .mix_ready(mix_audio_ready),
        .overflow_slips(audio_ovf_slips), .underflow_slips(audio_unf_slips), .cart_active(cart_audio_active), .fill());

    // Socket /RESET: open-drain pull owned by the power sequencer (held in
    // every state except RUN, and during a soft reset) or whenever the bus is
    // not permitted. The bridge's own reset request is NOT used here: it
    // follows the core reset, which itself follows the socket /RESET level,
    // and combining them deadlocks (found by tb_system).
    // /RESET is pulled whenever the bus is not permitted, except during the cartridge check:
    // the pull-up of /RESET hangs from the cartridge rail and would load the test current.
    assign cart_reset_pull = seq_reset_pull | (!bus_permit & !cart_probe_req);

    // =====================================================================
    // Status and fault words to the N64 mailbox (clk_25 -> clk_host).
    // STATUS layout (shared with firmware/bootstrap/src/sn64_mailbox.h):
    //   [0] configured (PLLs locked)  [1] host+FPGA rails ok  [2] cart 5 V ok
    //   [3] interface rail ok  [4] bus permit  [5] fault latched  [6] run request seen
    //   [7] PAL  [11:8] power sequencer state  [12] SNES clock running
    //   [13] SNES key CIC ok  [14] SNES key CIC fail  [15] telemetry ADC error
    // FAULT: {fault_code, 8'h00}; fault_code bit 0 = cartridge check failed in enforce mode
    // CART_CHECK: [15] done  [14] pass  [13:12] mode used  [8] this build has the check
    //   [7:0] last rail reading (ADC code / 4, saturated: 9.67 mV per count on the rail)
    // =====================================================================
    assign status_word = {i2c_error, cic_key_fail, cic_key_ok, snes_clk_run, seq_state,
                          region_pal, run_req_25, fault_latched, bus_permit,
                          iface_rail_ok, cart_5v_ok, host_3v3_ok & fpga_rails_ok, clocks_ready};
    sn64_cdc_word #(.W(16)) x_status (.src_clk(clk_25), .src_data(status_word), .dst_clk(clk_host), .dst_data(status_h));
    sn64_cdc_word #(.W(16)) x_fault (.src_clk(clk_25), .src_data({fault_code, 8'h00}), .dst_clk(clk_host), .dst_data(fault_h));
    wire [15:0] cart_check_25 = {probe_done, probe_pass, probe_mode_q, 3'd0, SEQ_PROBE_ENABLE ? 1'b1 : 1'b0, probe_level};
    sn64_cdc_word #(.W(16)) x_check (.src_clk(clk_25), .src_data(cart_check_25), .dst_clk(clk_host), .dst_data(cart_check_h));
    // REGION_INFO / REGION_SOURCE (mailbox 0x1A / 0x1C): one 32-bit word so
    // both halves always come from the same snapshot.
    wire [15:0] region_info_25   = rgn_decided ? rgn_hdr : hdr_word;
    wire [15:0] region_source_25 = {11'd0, rgn_pal, rgn_timeout, rgn_decided, rgn_src};
    sn64_cdc_word #(.W(32)) x_region (.src_clk(clk_25), .src_data({region_source_25, region_info_25}),
                                      .dst_clk(clk_host), .dst_data({region_source_h, region_info_h}));
endmodule
