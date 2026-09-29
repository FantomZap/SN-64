// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 board top level for the Lattice ECP5 (synthesis only).
//
// Adds the clock infrastructure around sn64_top (docs/design/clock-plan.md):
//   * EHXPLLL "host":  25 MHz oscillator -> 62.5 MHz (REF 2, FB 5, OP 10; VCO 625 MHz)
//   * EHXPLLL "tmds":  Si5351 CLK2 27.0198 MHz -> 135.099 MHz (REF 1, FB 5, OP 4; VCO 540.4 MHz)
//   * DCSC (DCSMODE "NEG", glitchless): SEL 01 = Si5351 CLK0 (NTSC), 10 = CLK1
//     (PAL), 00 = output held low. One primitive both picks the region clock and
//     starts/stops the SNES domain (Lattice FPGA-TN-02200 1.3, Table 10.2 and
//     Figure 10.1; both inputs must oscillate, which the Si5351 guarantees once
//     programmed, and snes_clk_run rises only after that).
//   * Bootstrap ROM from the configuration flash (ROM_FROM_FLASH = 1, USRMCLK).
//   * SNES CIC data pads with per-pin SN74LVC1T45 direction control.
// PLL parameters were produced by ecppll (OSS CAD Suite 20260928).
// Pin locations and I/O standards belong in the board constraint file, which
// needs the FPGA sheet of the schematic; fpga/constraints/sn64_trial.lpf is a
// feasibility stand-in.
module sn64_board_top (
    input  wire        osc_25,            // 25 MHz oscillator
    input  wire        si_clk0, si_clk1,  // Si5351 NTSC / PAL SNES masters
    input  wire        si_clk2,           // Si5351 HDMI pixel clock (27.0198 MHz)
    input  wire        board_reset_n,     // supervisor / configuration done

    input  wire        n64_reset_n, n64_nmi_n, n64_alel, n64_aleh, n64_read_n, n64_write_n,
    inout  wire [15:0] n64_ad,
    input  wire        n64_cic_clk, n64_si_clk,
    inout  wire        n64_cic_dq,
    output wire        si_scl_oe, si_sda_oe,
    input  wire        si_sda_in,
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
    inout  wire        cic_data0, cic_data1,            // A side of the SN74LVC1T45s (U215/U216)
    output wire        cic_data0_dir, cic_data1_dir,    // 1 = drive the cartridge (A->B)
    output wire        flash_cs_n,                      // configuration flash CSSPIN (MCLK via USRMCLK)
    inout  wire [3:0]  flash_dq,
    output wire [2:0]  hdmi_tmds,
    output wire        hdmi_tmds_clock,
    output wire        led_status
);
    // ---------------- Host PLL: 25 -> 62.5 MHz ----------------
    wire clk_host, host_locked;
    (* FREQUENCY_PIN_CLKI="25", FREQUENCY_PIN_CLKOP="62.5", ICP_CURRENT="12", LPF_RESISTOR="8", MFG_ENABLE_FILTEROPAMP="1", MFG_GMCREF_SEL="2" *)
    EHXPLLL #(
        .PLLRST_ENA("DISABLED"), .INTFB_WAKE("DISABLED"), .STDBY_ENABLE("DISABLED"), .DPHASE_SOURCE("DISABLED"),
        .OUTDIVIDER_MUXA("DIVA"), .OUTDIVIDER_MUXB("DIVB"), .OUTDIVIDER_MUXC("DIVC"), .OUTDIVIDER_MUXD("DIVD"),
        .CLKI_DIV(2), .CLKOP_ENABLE("ENABLED"), .CLKOP_DIV(10), .CLKOP_CPHASE(4), .CLKOP_FPHASE(0),
        .FEEDBK_PATH("CLKOP"), .CLKFB_DIV(5)
    ) pll_host (
        .RST(1'b0), .STDBY(1'b0), .CLKI(osc_25), .CLKOP(clk_host), .CLKFB(clk_host), .CLKINTFB(),
        .PHASESEL0(1'b0), .PHASESEL1(1'b0), .PHASEDIR(1'b1), .PHASESTEP(1'b1), .PHASELOADREG(1'b1),
        .PLLWAKESYNC(1'b0), .ENCLKOP(1'b0), .LOCK(host_locked));

    // ---------------- TMDS PLL: pixel x5 ----------------
    wire clk_pixel_x5, tmds_locked;
    (* FREQUENCY_PIN_CLKI="27.0198", FREQUENCY_PIN_CLKOP="135.099", ICP_CURRENT="12", LPF_RESISTOR="8", MFG_ENABLE_FILTEROPAMP="1", MFG_GMCREF_SEL="2" *)
    EHXPLLL #(
        .PLLRST_ENA("DISABLED"), .INTFB_WAKE("DISABLED"), .STDBY_ENABLE("DISABLED"), .DPHASE_SOURCE("DISABLED"),
        .OUTDIVIDER_MUXA("DIVA"), .OUTDIVIDER_MUXB("DIVB"), .OUTDIVIDER_MUXC("DIVC"), .OUTDIVIDER_MUXD("DIVD"),
        .CLKI_DIV(1), .CLKOP_ENABLE("ENABLED"), .CLKOP_DIV(4), .CLKOP_CPHASE(2), .CLKOP_FPHASE(0),
        .FEEDBK_PATH("CLKOP"), .CLKFB_DIV(5)
    ) pll_tmds (
        .RST(1'b0), .STDBY(1'b0), .CLKI(si_clk2), .CLKOP(clk_pixel_x5), .CLKFB(clk_pixel_x5), .CLKINTFB(),
        .PHASESEL0(1'b0), .PHASESEL1(1'b0), .PHASEDIR(1'b1), .PHASESTEP(1'b1), .PHASELOADREG(1'b1),
        .PLLWAKESYNC(1'b0), .ENCLKOP(1'b0), .LOCK(tmds_locked));

    // ---------------- SNES master: region select, then run gate ----------------
    // SEL is registered so both bits change on one clk_25 edge. region_pal is
    // frozen while the SNES clock runs (sn64_clock_init), so the only
    // transitions are 00 -> 01/10 at start and back to 00 at stop.
    wire snes_clk_run, region_pal, clk_snes;
    reg  sel_ntsc = 1'b0, sel_pal = 1'b0;
    always @(posedge osc_25) begin
        sel_ntsc <= snes_clk_run & !region_pal;
        sel_pal  <= snes_clk_run &  region_pal;
    end
    DCSC #(.DCSMODE("NEG")) snes_clock (.CLK0(si_clk0), .CLK1(si_clk1), .SEL0(sel_ntsc), .SEL1(sel_pal),
                                        .MODESEL(1'b0), .DCSOUT(clk_snes));

    // ---------------- SNES CIC data pads ----------------
    // SN74LVC1T45 per pin: DIR leads the pad drive by one clk_25 and trails its
    // release by one clk_25 (sn64_cic_pad, tested by tb_cic_pad).
    wire d0_o, d0_oe, d1_o, d1_oe, d0_pad_oe, d1_pad_oe;
    sn64_cic_pad cic_pad0 (.clk(osc_25), .oe(d0_oe), .dir(cic_data0_dir), .pad_oe(d0_pad_oe));
    sn64_cic_pad cic_pad1 (.clk(osc_25), .oe(d1_oe), .dir(cic_data1_dir), .pad_oe(d1_pad_oe));
    assign cic_data0 = d0_pad_oe ? d0_o : 1'bz;
    assign cic_data1 = d1_pad_oe ? d1_o : 1'bz;

    // Power-on reset: board supervisor and host PLL lock. The TMDS PLL locks
    // only after the Si5351 is programmed, so it gates the HDMI domain only.
    wire por_n = board_reset_n & host_locked;

    wire [15:0] status_word;
    sn64_top #(.ROM_FROM_FLASH(1), .FLASH_USE_USRMCLK(1)) top (
        .clk_25(osc_25), .clk_host(clk_host), .clk_snes(clk_snes), .clk_pixel(si_clk2), .clk_pixel_x5(clk_pixel_x5),
        .hdmi_clock_ok(tmds_locked), .por_n(por_n),
        .n64_reset_n(n64_reset_n), .n64_nmi_n(n64_nmi_n), .n64_alel(n64_alel), .n64_aleh(n64_aleh),
        .n64_read_n(n64_read_n), .n64_write_n(n64_write_n), .n64_ad(n64_ad),
        .n64_cic_clk(n64_cic_clk), .n64_si_clk(n64_si_clk), .n64_cic_dq(n64_cic_dq),
        .rom_we(1'b0), .rom_waddr('0), .rom_wdata(16'd0),
        .flash_sck(), .flash_cs_n(flash_cs_n), .flash_dq(flash_dq),
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
        .snes_cic_data0_o(d0_o), .snes_cic_data0_oe(d0_oe), .snes_cic_data0_i(cic_data0),
        .snes_cic_data1_o(d1_o), .snes_cic_data1_oe(d1_oe), .snes_cic_data1_i(cic_data1),
        .hdmi_tmds(hdmi_tmds), .hdmi_tmds_clock(hdmi_tmds_clock), .av_locked(), .status_word(status_word));

    // Status LED: steady when the SNES clock runs, off otherwise (a
    // placeholder for the board's indicator scheme).
    assign led_status = status_word[12];
endmodule
