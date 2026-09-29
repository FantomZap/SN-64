// SPDX-License-Identifier: GPL-3.0-or-later
// SN64 register bus for the vendored n64_pi controller. Functionally the same
// as SummerCart64's n64_reg_bus.sv (GPL-3.0) but without the expression
// modports that Verilator does not support; the vendored file is left intact
// and only this copy is compiled. Only the cfg endpoint is used by SN64.
interface n64_reg_bus ();
    logic flashram_select;
    logic dd_select;
    logic cfg_select;

    logic read;
    logic write;
    logic [16:0] address;
    logic [15:0] rdata;
    logic [15:0] wdata;

    logic [15:0] flashram_rdata;
    logic [15:0] dd_rdata;
    logic [15:0] cfg_rdata;

    modport controller (
        output flashram_select, output dd_select, output cfg_select,
        output read, output write, output address, input rdata, output wdata
    );

    always_comb begin
        rdata = 16'd0;
        if (flashram_select) rdata = flashram_rdata;
        if (dd_select)       rdata = dd_rdata;
        if (cfg_select)      rdata = cfg_rdata;
    end
endinterface
