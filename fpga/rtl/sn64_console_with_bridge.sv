// SPDX-License-Identifier: GPL-3.0-or-later
// Console candidate plus physical cartridge bridge: the socket-facing top
// level for simulation and later board integration.
module sn64_console_with_bridge (
    input  wire        clk, reset_n, enable, pal,
    input  wire        bus_permit,
    // Socket side (through translators)
    output wire [23:0] cart_address,
    output wire [7:0]  cart_pa,
    output wire        cart_rd_n, cart_wr_n, cart_prd_n, cart_pwr_n,
    output wire        cart_romsel_n, cart_wramsel_n, cart_refresh, cart_phi2, cart_sysclk,
    output wire [7:0]  cart_data_out,
    input  wire [7:0]  cart_data_in,
    input  wire        cart_irq_n, cart_reset_n_sense,
    output wire        cart_reset_pull_n,
    output wire        ctl_oe_n, data_oe_n, data_dir, contention_guard,
    // Host-side inputs and A/V
    input  wire [1:0]  joy1_di, joy2_di,
    output wire        joy_strobe, joy1_clock, joy2_clock,
    output wire [14:0] rgb,
    output wire        hsync, vsync, hde, vde, dot_clock, high_res, field, interlace,
    output wire [8:0]  video_x, video_y,
    output wire [15:0] audio_left, audio_right,
    output wire        audio_ready
);
    wire [23:0] a; wire [7:0] pa, dout, din;
    wire rd_n, wr_n, prd_n, pwr_n, romsel_n, wramsel_n, refresh, phi2, wram_valid, irq_n;

    sn64_console_candidate console (
        .clk(clk), .reset_n(reset_n), .enable(enable), .pal(pal),
        .cart_data_in(din), .cart_irq_n(irq_n),
        .cart_address(a), .cart_data_out(dout), .cart_peripheral_address(pa),
        .cart_wram_read_valid(wram_valid),
        .cart_rd_n(rd_n), .cart_wr_n(wr_n), .cart_prd_n(prd_n), .cart_pwr_n(pwr_n),
        .cart_romsel_n(romsel_n), .cart_wramsel_n(wramsel_n), .cart_refresh(refresh), .cart_phi2(phi2),
        .joy1_di(joy1_di), .joy2_di(joy2_di), .joy_strobe(joy_strobe), .joy1_clock(joy1_clock), .joy2_clock(joy2_clock),
        .rgb(rgb), .hsync(hsync), .vsync(vsync), .hde(hde), .vde(vde), .dot_clock(dot_clock),
        .high_res(high_res), .field(field), .interlace(interlace), .video_x(video_x), .video_y(video_y),
        .audio_left(audio_left), .audio_right(audio_right), .audio_ready(audio_ready));

    sn64_cart_bridge bridge (
        .clk(clk), .reset_n(reset_n), .bus_permit(bus_permit),
        .core_address(a), .core_pa(pa),
        .core_rd_n(rd_n), .core_wr_n(wr_n), .core_prd_n(prd_n), .core_pwr_n(pwr_n),
        .core_romsel_n(romsel_n), .core_wramsel_n(wramsel_n), .core_refresh(refresh), .core_phi2(phi2),
        .core_data_out(dout), .core_internal_valid(wram_valid), .core_data_in(din), .core_irq_n(irq_n),
        .cart_address(cart_address), .cart_pa(cart_pa),
        .cart_rd_n(cart_rd_n), .cart_wr_n(cart_wr_n), .cart_prd_n(cart_prd_n), .cart_pwr_n(cart_pwr_n),
        .cart_romsel_n(cart_romsel_n), .cart_wramsel_n(cart_wramsel_n), .cart_refresh(cart_refresh),
        .cart_phi2(cart_phi2), .cart_sysclk(cart_sysclk),
        .cart_data_out(cart_data_out), .cart_data_in(cart_data_in),
        .cart_irq_n(cart_irq_n), .cart_reset_n_sense(cart_reset_n_sense), .cart_reset_pull_n(cart_reset_pull_n),
        .ctl_oe_n(ctl_oe_n), .data_oe_n(data_oe_n), .data_dir(data_dir), .contention_guard(contention_guard));
endmodule
