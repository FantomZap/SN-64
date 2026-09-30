// SN64 v2 USB programmer: full-speed USB device on two FPGA pins running the
// TinyFPGA bootloader protocol (USB CDC serial, SPI-flash bridge; vendor core
// fpga/vendor/tinyfpga-bootloader, Apache-2.0). The host uses `tinyprog` to read,
// erase and write the configuration flash and to request a reboot. This wrapper is
// the vendor top (tinyfpga_bootloader.v) without its LED and without the
// "no host for 16 s -> boot" timer: on the SN64 the same image keeps running
// with the console, so only an explicit boot command reloads the FPGA.
// clk_48mhz: 48 MHz bit clock. clk: 12 MHz logic clock (both from the host PLL).
// SPDX-License-Identifier: GPL-3.0-or-later
module sn64_usb_prog (
    input  wire clk_48mhz,
    input  wire clk,
    input  wire reset,
    // pads (board top adds the tri-state)
    output wire usb_p_tx, usb_n_tx,
    input  wire usb_p_rx, usb_n_rx,
    output wire usb_tx_en,
    // SPI flash bridge (request/ownership resolved in sn64_bootrom_flash)
    output wire spi_cs_n, spi_sck, spi_mosi,
    input  wire spi_miso,
    // one-clock pulse: the host asked for a reboot into the (new) image
    output wire boot_request,
    output wire sof_seen                // a USB host is talking to us
);
    wire [6:0] dev_addr;
    wire [7:0] out_ep_data;
    wire ctrl_out_ep_req, ctrl_out_ep_grant, ctrl_out_ep_data_avail, ctrl_out_ep_setup, ctrl_out_ep_data_get, ctrl_out_ep_stall, ctrl_out_ep_acked;
    wire ctrl_in_ep_req, ctrl_in_ep_grant, ctrl_in_ep_data_free, ctrl_in_ep_data_put, ctrl_in_ep_data_done, ctrl_in_ep_stall, ctrl_in_ep_acked;
    wire [7:0] ctrl_in_ep_data;
    wire ser_out_ep_req, ser_out_ep_grant, ser_out_ep_data_avail, ser_out_ep_setup, ser_out_ep_data_get, ser_out_ep_stall, ser_out_ep_acked;
    wire ser_in_ep_req, ser_in_ep_grant, ser_in_ep_data_free, ser_in_ep_data_put, ser_in_ep_data_done, ser_in_ep_stall, ser_in_ep_acked;
    wire [7:0] ser_in_ep_data;
    wire sof_valid; wire [10:0] frame_index;
    wire nak_in_ep_grant, nak_in_ep_data_free, nak_in_ep_acked;

    usb_serial_ctrl_ep ctrl_ep_inst (
        .clk(clk), .reset(reset), .dev_addr(dev_addr),
        .out_ep_req(ctrl_out_ep_req), .out_ep_grant(ctrl_out_ep_grant), .out_ep_data_avail(ctrl_out_ep_data_avail),
        .out_ep_setup(ctrl_out_ep_setup), .out_ep_data_get(ctrl_out_ep_data_get), .out_ep_data(out_ep_data),
        .out_ep_stall(ctrl_out_ep_stall), .out_ep_acked(ctrl_out_ep_acked),
        .in_ep_req(ctrl_in_ep_req), .in_ep_grant(ctrl_in_ep_grant), .in_ep_data_free(ctrl_in_ep_data_free),
        .in_ep_data_put(ctrl_in_ep_data_put), .in_ep_data(ctrl_in_ep_data), .in_ep_data_done(ctrl_in_ep_data_done),
        .in_ep_stall(ctrl_in_ep_stall), .in_ep_acked(ctrl_in_ep_acked));

    usb_spi_bridge_ep spi_bridge_inst (
        .clk(clk), .reset(reset),
        .out_ep_req(ser_out_ep_req), .out_ep_grant(ser_out_ep_grant), .out_ep_data_avail(ser_out_ep_data_avail),
        .out_ep_setup(ser_out_ep_setup), .out_ep_data_get(ser_out_ep_data_get), .out_ep_data(out_ep_data),
        .out_ep_stall(ser_out_ep_stall), .out_ep_acked(ser_out_ep_acked),
        .in_ep_req(ser_in_ep_req), .in_ep_grant(ser_in_ep_grant), .in_ep_data_free(ser_in_ep_data_free),
        .in_ep_data_put(ser_in_ep_data_put), .in_ep_data(ser_in_ep_data), .in_ep_data_done(ser_in_ep_data_done),
        .in_ep_stall(ser_in_ep_stall), .in_ep_acked(ser_in_ep_acked),
        .spi_cs_b(spi_cs_n), .spi_sck(spi_sck), .spi_mosi(spi_mosi), .spi_miso(spi_miso),
        .boot_to_user_design(boot_request));

    usb_fs_pe #(.NUM_OUT_EPS(5'd2), .NUM_IN_EPS(5'd3)) usb_fs_pe_inst (
        .clk_48mhz(clk_48mhz), .clk(clk), .reset(reset),
        .usb_p_tx(usb_p_tx), .usb_n_tx(usb_n_tx), .usb_p_rx(usb_p_rx), .usb_n_rx(usb_n_rx), .usb_tx_en(usb_tx_en),
        .dev_addr(dev_addr),
        .out_ep_req({ser_out_ep_req, ctrl_out_ep_req}), .out_ep_grant({ser_out_ep_grant, ctrl_out_ep_grant}),
        .out_ep_data_avail({ser_out_ep_data_avail, ctrl_out_ep_data_avail}), .out_ep_setup({ser_out_ep_setup, ctrl_out_ep_setup}),
        .out_ep_data_get({ser_out_ep_data_get, ctrl_out_ep_data_get}), .out_ep_data(out_ep_data),
        .out_ep_stall({ser_out_ep_stall, ctrl_out_ep_stall}), .out_ep_acked({ser_out_ep_acked, ctrl_out_ep_acked}),
        .in_ep_req({1'b0, ser_in_ep_req, ctrl_in_ep_req}), .in_ep_grant({nak_in_ep_grant, ser_in_ep_grant, ctrl_in_ep_grant}),
        .in_ep_data_free({nak_in_ep_data_free, ser_in_ep_data_free, ctrl_in_ep_data_free}),
        .in_ep_data_put({1'b0, ser_in_ep_data_put, ctrl_in_ep_data_put}),
        .in_ep_data({8'b0, ser_in_ep_data[7:0], ctrl_in_ep_data[7:0]}),
        .in_ep_data_done({1'b0, ser_in_ep_data_done, ctrl_in_ep_data_done}),
        .in_ep_stall({1'b0, ser_in_ep_stall, ctrl_in_ep_stall}), .in_ep_acked({nak_in_ep_acked, ser_in_ep_acked, ctrl_in_ep_acked}),
        .sof_valid(sof_valid), .frame_index(frame_index));

    // "host present" = a start-of-frame within the last ~0.5 s (12 MHz clock)
    reg [22:0] sof_timer = '0;
    always @(posedge clk) sof_timer <= (reset || sof_valid) ? '0 : (sof_timer == 23'h7FFFFF ? sof_timer : sof_timer + 1'b1);
    assign sof_seen = (sof_timer != 23'h7FFFFF);
endmodule
