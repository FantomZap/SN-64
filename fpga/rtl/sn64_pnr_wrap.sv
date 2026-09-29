// SPDX-License-Identifier: GPL-3.0-or-later
// Place-and-route feasibility wrapper for sn64_top (not the board top level).
//
// Keeps every real board interface as a pin, ties off the simulation-only
// bootstrap load port, and XOR-reduces the SNES video/audio and status
// outputs into three pins so synthesis cannot remove the PPU/APU logic that
// the eventual A/V block will consume. Used only to measure resources and
// internal timing before the board wrapper (PLLs, DCS, A/V, pin constraints)
// exists; pin locations are left to the placer.
module sn64_pnr_wrap (
    input  wire        clk_25, clk_host, clk_snes, por_n,
    input  wire        n64_reset_n, n64_nmi_n, n64_alel, n64_aleh, n64_read_n, n64_write_n,
    inout  wire [15:0] n64_ad,
    input  wire        n64_cic_clk, n64_si_clk,
    inout  wire        n64_cic_dq,
    output wire        si_scl_oe, si_sda_oe,
    input  wire        si_sda_in,
    output wire        snes_clk_run, region_pal,
    input  wire        host_3v3_ok, fpga_rails_ok, cart_5v_ok, iface_rail_ok, efuse_fault_n, overtemp,
    output wire        cart_5v_enable, iface_rail_enable,
    output wire [23:0] cart_address,
    output wire [7:0]  cart_pa,
    output wire        cart_rd_n, cart_wr_n, cart_prd_n, cart_pwr_n,
    output wire        cart_romsel_n, cart_wramsel_n, cart_refresh, cart_phi2, cart_sysclk,
    output wire [7:0]  cart_data_out,
    input  wire [7:0]  cart_data_in,
    input  wire        cart_irq_n, cart_reset_n_sense,
    output wire        cart_reset_pull, ctl_oe_n, data_oe_n, data_dir,
    output wire        snes_cic_oe_n, snes_cic_clk, snes_cic_slave_reset,
    output wire        snes_cic_data0_o, snes_cic_data0_oe,
    input  wire        snes_cic_data0_i,
    output wire        snes_cic_data1_o, snes_cic_data1_oe,
    input  wire        snes_cic_data1_i,
    output reg         video_keep, audio_keep, status_keep
);
    wire [14:0] rgb; wire hs, vs, hde, vde, dot, hr, fld, il; wire [15:0] al, ar; wire ardy; wire [15:0] st;
    sn64_top #(.ROM_ADDR_BITS(16)) top (
        .clk_25(clk_25), .clk_host(clk_host), .clk_snes(clk_snes), .por_n(por_n),
        .n64_reset_n(n64_reset_n), .n64_nmi_n(n64_nmi_n), .n64_alel(n64_alel), .n64_aleh(n64_aleh),
        .n64_read_n(n64_read_n), .n64_write_n(n64_write_n), .n64_ad(n64_ad),
        .n64_cic_clk(n64_cic_clk), .n64_si_clk(n64_si_clk), .n64_cic_dq(n64_cic_dq),
        .rom_we(1'b0), .rom_waddr(16'd0), .rom_wdata(16'd0),
        .si_scl_oe(si_scl_oe), .si_sda_oe(si_sda_oe), .si_sda_in(si_sda_in),
        .snes_clk_run(snes_clk_run), .region_pal(region_pal),
        .host_3v3_ok(host_3v3_ok), .fpga_rails_ok(fpga_rails_ok), .cart_5v_ok(cart_5v_ok), .iface_rail_ok(iface_rail_ok),
        .efuse_fault_n(efuse_fault_n), .overtemp(overtemp), .cart_5v_enable(cart_5v_enable), .iface_rail_enable(iface_rail_enable),
        .cart_address(cart_address), .cart_pa(cart_pa), .cart_rd_n(cart_rd_n), .cart_wr_n(cart_wr_n),
        .cart_prd_n(cart_prd_n), .cart_pwr_n(cart_pwr_n), .cart_romsel_n(cart_romsel_n), .cart_wramsel_n(cart_wramsel_n),
        .cart_refresh(cart_refresh), .cart_phi2(cart_phi2), .cart_sysclk(cart_sysclk),
        .cart_data_out(cart_data_out), .cart_data_in(cart_data_in), .cart_irq_n(cart_irq_n), .cart_reset_n_sense(cart_reset_n_sense),
        .cart_reset_pull(cart_reset_pull), .ctl_oe_n(ctl_oe_n), .data_oe_n(data_oe_n), .data_dir(data_dir),
        .snes_cic_oe_n(snes_cic_oe_n), .snes_cic_clk(snes_cic_clk), .snes_cic_slave_reset(snes_cic_slave_reset),
        .snes_cic_data0_o(snes_cic_data0_o), .snes_cic_data0_oe(snes_cic_data0_oe), .snes_cic_data0_i(snes_cic_data0_i),
        .snes_cic_data1_o(snes_cic_data1_o), .snes_cic_data1_oe(snes_cic_data1_oe), .snes_cic_data1_i(snes_cic_data1_i),
        .snes_rgb(rgb), .snes_hsync(hs), .snes_vsync(vs), .snes_hde(hde), .snes_vde(vde), .snes_dot_clock(dot),
        .snes_high_res(hr), .snes_field(fld), .snes_interlace(il),
        .snes_audio_left(al), .snes_audio_right(ar), .snes_audio_ready(ardy), .status_word(st));
    always @(posedge clk_snes) begin
        video_keep <= ^{rgb, hs, vs, hde, vde, dot, hr, fld, il};
        audio_keep <= ^{al, ar, ardy};
    end
    always @(posedge clk_25) status_keep <= ^st;
endmodule
