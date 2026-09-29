// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 FPGA top level (technology-independent).
//
// Clock domains (see docs/design/clock-plan.md):
//   clk_25   25 MHz oscillator: power sequencer, Si5351 start-up, SNES CIC lock
//   clk_host 62.5 MHz (PLL from clk_25), always on: N64 endpoint and N64 CIC
//   clk_snes Si5351 output (NTSC or PAL master), started once at power-on:
//            SNES core, cartridge bridge, controller emulation
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
    parameter        CLK25_HZ = 25_000_000,
    parameter        REGION_TIMEOUT_MS = 300,      // give up waiting for a key CIC
    parameter        SEQ_RESET_HOLD_MS = 20,
    parameter        SEQ_RAIL_TIMEOUT_MS = 50,
    parameter        CIC_LOCK_CLK_DIV = 7,         // 25 MHz / 7 = 3.571 MHz CIC_CLK
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

    // ---------------- Si5351 I2C and SNES clock control ----------------
    output wire        si_scl_oe, si_sda_oe,
    input  wire        si_sda_in,
    output reg         snes_clk_run,               // board: start the SNES master clock domain
    output wire        region_pal,                 // board: 0 = Si5351 CLK0 (NTSC), 1 = CLK1 (PAL)

    // ---------------- Power monitors and enables ----------------
    input  wire        host_3v3_ok, fpga_rails_ok, cart_5v_ok, iface_rail_ok, efuse_fault_n, overtemp,
    output wire        cart_5v_enable, iface_rail_enable,

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
    output wire        snes_cic_clk, snes_cic_slave_reset,
    output wire        snes_cic_data0_o, snes_cic_data0_oe,
    input  wire        snes_cic_data0_i,
    output wire        snes_cic_data1_o, snes_cic_data1_oe,
    input  wire        snes_cic_data1_i,

    // ---------------- SNES video/audio (to the A/V output block) ----------------
    output wire [14:0] snes_rgb,
    output wire        snes_hsync, snes_vsync, snes_hde, snes_vde, snes_dot_clock,
    output wire        snes_high_res, snes_field, snes_interlace,
    output wire [15:0] snes_audio_left, snes_audio_right,
    output wire        snes_audio_ready,

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
    wire run_req_h, soft_reset_h; wire [1:0] region_mode_h;
    wire [15:0] status_h;
    wire n64_cic_invalid_region; wire [3:0] n64_cic_step;
    sn64_n64_endpoint #(.ROM_ADDR_BITS(ROM_ADDR_BITS)) endpoint (
        .clk(clk_host), .reset(!rsthost_n), .cic_cpu_clk(clk_host),
        .n64_reset(n64_reset_n), .n64_nmi(n64_nmi_n),
        .n64_pi_alel(n64_alel), .n64_pi_aleh(n64_aleh), .n64_pi_read(n64_read_n), .n64_pi_write(n64_write_n),
        .n64_pi_ad(n64_ad),
        .rom_we(rom_we), .rom_waddr(rom_waddr), .rom_wdata(rom_wdata),
        .joy1_buttons(joy1_h), .joy2_buttons(joy2_h), .joy1_stick_x(stick_x_h), .joy1_stick_y(stick_y_h),
        .run_request(run_req_h), .soft_reset(soft_reset_h), .region_mode(region_mode_h), .mailbox_seq(seq_h),
        .status_flags(status_h), .build_id(BUILD_ID),
        .n64_cic_clk(n64_cic_clk), .n64_cic_dq(n64_cic_dq), .n64_si_clk(n64_si_clk), .cic_region(region_pal),
        .cic_invalid_region(n64_cic_invalid_region), .cic_step(n64_cic_step),
        .host_reset_event(), .host_nmi_event());

    // =====================================================================
    // Housekeeping domain (clk_25): requests from the host, host reset
    // =====================================================================
    wire [3:0] ctl_25;
    sn64_cdc_word #(.W(4)) x_ctl (.src_clk(clk_host), .src_data({region_mode_h, soft_reset_h, run_req_h}),
                                  .dst_clk(clk_25), .dst_data(ctl_25));
    wire run_req_25 = ctl_25[0], soft_reset_25 = ctl_25[1];
    wire [1:0] region_mode_25 = ctl_25[3:2];
    wire host_reset_n_25, cart_reset_sense_25;
    sn64_sync_bit #(1'b0) s_hreset (.clk(clk_25), .d(n64_reset_n), .q(host_reset_n_25));
    sn64_sync_bit #(1'b0) s_creset (.clk(clk_25), .d(cart_reset_n_sense), .q(cart_reset_sense_25));

    // =====================================================================
    // Si5351 start-up and region latch (clk_25)
    // =====================================================================
    wire clocks_ready, i2c_error;
    wire cic_region_valid, cic_region_pal, cic_key_ok, cic_key_fail;
    sn64_clock_init #(.CLK_HZ(CLK25_HZ)) clock_init (
        .clk(clk_25), .reset_n(rst25_n),
        .scl_oe(si_scl_oe), .sda_oe(si_sda_oe), .sda_in(si_sda_in),
        .region_mode(region_mode_25), .detected_valid(cic_region_valid), .detected_pal(cic_region_pal),
        .snes_clock_stopped(!snes_clk_run), .region_pal(region_pal), .region_change_pending(),
        .clocks_ready(clocks_ready), .i2c_error(i2c_error));

    // =====================================================================
    // Power sequencer (clk_25)
    // =====================================================================
    wire seq_reset_pull, bus_permit, fault_latched; wire [3:0] seq_state; wire [7:0] fault_code;
    reg  release_ok;
    sn64_power_sequencer #(.CLK_HZ(CLK25_HZ), .RESET_HOLD_MS(SEQ_RESET_HOLD_MS), .RAIL_TIMEOUT_MS(SEQ_RAIL_TIMEOUT_MS)) sequencer (
        .clk(clk_25), .reset_n(rst25_n),
        .configured(clocks_ready), .host_3v3_ok(host_3v3_ok), .fpga_rails_ok(fpga_rails_ok),
        .cart_5v_ok(cart_5v_ok), .iface_rail_ok(iface_rail_ok), .efuse_fault_n(efuse_fault_n),
        .overtemp(overtemp), .host_reset_n(host_reset_n_25),
        .run_request(run_req_25), .fault_clear(!run_req_25), .release_ok(release_ok), .hold_reset(soft_reset_25),
        .cart_5v_enable(cart_5v_enable), .iface_rail_enable(iface_rail_enable), .cart_reset_pull(seq_reset_pull),
        .bus_permit(bus_permit), .fault_latched(fault_latched), .state(seq_state), .fault_code(fault_code));

    // =====================================================================
    // SNES CIC lock (clk_25 / CLK_DIV -> CIC_CLK): runs once the cartridge
    // and interface rail are up, before the SNES master clock starts, and
    // reports the key's region.
    // =====================================================================
    wire cic_enable = (seq_state >= 4'd3) && (seq_state <= 4'd4);   // IFACE or RUN
    sn64_snes_cic_lock #(.CLK_DIV(CIC_LOCK_CLK_DIV), .T_PWRUP(CIC_LOCK_T_PWRUP)) snes_cic (
        .clk(clk_25), .reset_n(rst25_n), .enable(cic_enable), .enforce(1'b0),
        .default_pal(1'b0), .seed(4'h0),
        .cic_clk(snes_cic_clk), .slave_reset(snes_cic_slave_reset),
        .data0_o(snes_cic_data0_o), .data0_oe(snes_cic_data0_oe), .data0_i(snes_cic_data0_i),
        .data1_o(snes_cic_data1_o), .data1_oe(snes_cic_data1_oe), .data1_i(snes_cic_data1_i),
        .console_run(), .key_ok(cic_key_ok), .key_fail(cic_key_fail),
        .region_valid(cic_region_valid), .region_pal(cic_region_pal), .rounds_done(), .phase());

    // =====================================================================
    // SNES clock start (once per cartridge power-up) and reset release
    // =====================================================================
    localparam integer REGION_TICKS = CLK25_HZ / 1000 * REGION_TIMEOUT_MS;
    localparam integer SETTLE_TICKS = CLK25_HZ / 1000;               // 1 ms of running clock before release
    reg [31:0] region_timer, settle_timer;
    wire region_decided = (region_mode_25 != 2'd0) || cic_region_valid || cic_key_fail || (region_timer >= REGION_TICKS);
    always @(posedge clk_25) begin
        if (!rst25_n || seq_state == 4'd0 || seq_state >= 4'd5) begin   // OFF, SHUTDOWN, FAULT: clock stops
            snes_clk_run <= 1'b0; release_ok <= 1'b0; region_timer <= 0; settle_timer <= 0;
        end else begin
            if (seq_state == 4'd3 && !snes_clk_run) begin
                region_timer <= region_timer + 1;
                if (clocks_ready && region_decided) snes_clk_run <= 1'b1;
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
    wire core_reset_n;
    sn64_sync_bit #(1'b0) s_core_rst (.clk(clk_snes), .d(cart_reset_n_sense & bus_permit), .q(core_reset_n));

    wire [15:0] joy1_s, joy2_s;
    sn64_cdc_word #(.W(16)) x_joy1 (.src_clk(clk_host), .src_data(joy1_h), .dst_clk(clk_snes), .dst_data(joy1_s));
    sn64_cdc_word #(.W(16)) x_joy2 (.src_clk(clk_host), .src_data(joy2_h), .dst_clk(clk_snes), .dst_data(joy2_s));
    wire [1:0] joy1_di, joy2_di; wire joy_strobe, joy1_clock, joy2_clock;
    sn64_snes_joypad pads (.clk(clk_snes), .joy1_buttons(joy1_s), .joy2_buttons(joy2_s), .pad_present(2'b11),
        .joy_strobe(joy_strobe), .joy1_clock(joy1_clock), .joy2_clock(joy2_clock),
        .joy1_di(joy1_di), .joy2_di(joy2_di));

    wire region_pal_s;
    sn64_sync_bit #(1'b0) s_pal (.clk(clk_snes), .d(region_pal), .q(region_pal_s));
    wire bridge_reset_pull_n;
    sn64_console_with_bridge console (
        .clk(clk_snes), .reset_n(core_reset_n), .enable(1'b1), .pal(region_pal_s), .bus_permit(bridge_permit),
        .cart_address(cart_address), .cart_pa(cart_pa), .cart_rd_n(cart_rd_n), .cart_wr_n(cart_wr_n),
        .cart_prd_n(cart_prd_n), .cart_pwr_n(cart_pwr_n), .cart_romsel_n(cart_romsel_n), .cart_wramsel_n(cart_wramsel_n),
        .cart_refresh(cart_refresh), .cart_phi2(cart_phi2), .cart_sysclk(cart_sysclk),
        .cart_data_out(cart_data_out), .cart_data_in(cart_data_in), .cart_irq_n(cart_irq_n),
        .cart_reset_n_sense(cart_reset_n_sense), .cart_reset_pull_n(bridge_reset_pull_n),
        .ctl_oe_n(ctl_oe_n), .data_oe_n(data_oe_n), .data_dir(data_dir), .contention_guard(),
        .joy1_di(joy1_di), .joy2_di(joy2_di), .joy_strobe(joy_strobe), .joy1_clock(joy1_clock), .joy2_clock(joy2_clock),
        .rgb(snes_rgb), .hsync(snes_hsync), .vsync(snes_vsync), .hde(snes_hde), .vde(snes_vde), .dot_clock(snes_dot_clock),
        .high_res(snes_high_res), .field(snes_field), .interlace(snes_interlace), .video_x(), .video_y(),
        .audio_left(snes_audio_left), .audio_right(snes_audio_right), .audio_ready(snes_audio_ready));

    // Socket /RESET: open-drain pull from the sequencer or the bridge.
    assign cart_reset_pull = seq_reset_pull | !bridge_reset_pull_n;

    // =====================================================================
    // Status word to the N64 mailbox (clk_25 -> clk_host)
    //   [15:8] fault code  [7:4] sequencer state  [3] PAL  [2] SNES key CIC ok
    //   [1] Si5351 locked  [0] SNES clock running
    // =====================================================================
    assign status_word = {fault_code, seq_state, region_pal, cic_key_ok, clocks_ready, snes_clk_run};
    sn64_cdc_word #(.W(16)) x_status (.src_clk(clk_25), .src_data(status_word), .dst_clk(clk_host), .dst_data(status_h));
endmodule
