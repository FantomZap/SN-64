// SPDX-License-Identifier: GPL-3.0-or-later
// Resource/simulation candidate, not board-ready gateware. Physical bus output
// enables, cartridge power, CIC, clocks, host and digital A/V are separate work.
module sn64_console_candidate (
    input wire clk, reset_n, enable, pal,
    input wire [7:0] cart_data_in,
    input wire cart_irq_n,
    output wire [23:0] cart_address,
    output wire [7:0] cart_data_out, cart_peripheral_address,
    output wire cart_wram_read_valid,
    output wire cart_rd_n, cart_wr_n, cart_prd_n, cart_pwr_n,
    output wire cart_romsel_n, cart_wramsel_n, cart_refresh, cart_phi2,
    input wire [1:0] joy1_di, joy2_di,
    output wire joy_strobe, joy1_clock, joy2_clock,
    output wire [14:0] rgb,
    output wire hsync, vsync, hde, vde, dot_clock, high_res, field, interlace,
    output wire [8:0] video_x, video_y,
    output wire [15:0] audio_left, audio_right,
    output wire audio_ready
);
    wire [16:0] wa;
    wire [7:0] wd,wq;
    wire wce_n,wwe_n,woe_n;
    wire [7:0] legacy_cart_data;
    // WRAM shares the physical data bus with the cartridge. Upstream DO
    // otherwise retains the previous CPU byte until the read cycle ends.
    // This source-valid flag is NOT a complete socket/translator output enable.
    assign cart_wram_read_valid = reset_n && enable && !wce_n && !woe_n;
    assign cart_data_out = cart_wram_read_valid ? wq : legacy_cart_data;
    wire [15:0] va,vb,aa;
    wire [7:0] vad,vbd,vaq,vbq,ad,aq;
    wire vaw_n,vbw_n,ace_n,awe_n;
    sn64_sync_ram #(.ADDR_BITS(17)) wram(clk,~wce_n & ~wwe_n,wa,wd,wq);
    sn64_sync_ram #(.ADDR_BITS(15)) vram_low(clk,~vaw_n,va[14:0],vad,vaq);
    sn64_sync_ram #(.ADDR_BITS(15)) vram_high(clk,~vbw_n,vb[14:0],vbd,vbq);
    sn64_sync_ram #(.ADDR_BITS(16)) aram(clk,~ace_n & ~awe_n,aa,ad,aq);
    SNES console (
        .MCLK(clk),.RST_N(reset_n),.ENABLE(enable),.PAL(pal),
        .BLEND(1'b0),.DIS_SHORTLINE(1'b0),
        .CA(),.RAW_CA(cart_address),.CPURD_N(cart_rd_n),.CPUWR_N(cart_wr_n),.PHI2(cart_phi2),
        .CPURD_CYC_N(),.DOT_CLK_CE(),
        .PA(cart_peripheral_address),.PARD_N(cart_prd_n),.PAWR_N(cart_pwr_n),
        .DI(cart_data_in),.DO(legacy_cart_data),.IRQ_N(cart_irq_n),
        .RAMSEL_N(cart_wramsel_n),.ROMSEL_N(cart_romsel_n),
        .SYSCLKF_CE(),.SYSCLKR_CE(),.SNES_REFRESH(cart_refresh),
        .WRAM_ADDR(wa),.WRAM_D(wd),.WRAM_Q(wq),.WRAM_CE_N(wce_n),
        .WRAM_OE_N(woe_n),.WRAM_WE_N(wwe_n),.WRAM_RD_N(),
        .VRAM_ADDRA(va),.VRAM_ADDRB(vb),.VRAM_DAI(vaq),.VRAM_DBI(vbq),
        .VRAM_DAO(vad),.VRAM_DBO(vbd),.VRAM_WRA_N(vaw_n),.VRAM_WRB_N(vbw_n),.VRAM_RD_N(),
        .ARAM_ADDR(aa),.ARAM_D(ad),.ARAM_Q(aq),.ARAM_CE_N(ace_n),.ARAM_OE_N(),.ARAM_WE_N(awe_n),
        .HIGH_RES(high_res),.FIELD_OUT(field),.INTERLACE(interlace),.V224_MODE(),.DOTCLK(dot_clock),
        .RGB_OUT(rgb),.HDE(hde),.VDE(vde),.HSYNC(hsync),.VSYNC(vsync),.X_OUT(video_x),.Y_OUT(video_y),
        .JOY1_DI(joy1_di),.JOY2_DI(joy2_di),.JOY_STRB(joy_strobe),.JOY1_CLK(joy1_clock),.JOY2_CLK(joy2_clock),
        .AUDIO_L(audio_left),.AUDIO_R(audio_right),.AUDIO_READY(audio_ready),.AUDIO_EN(1'b1),
        .DBG_SEL(8'd0),.DBG_REG(8'd0),.DBG_REG_WR(1'b0),.DBG_DAT_IN(8'd0),.DBG_DAT_OUT(),.DBG_BREAK()
    );
endmodule

// One clock of read latency. No reset/initialization loop: these map to BRAM,
// and software sees real power-up memory contents rather than a synthetic ROM.
module sn64_sync_ram #(parameter ADDR_BITS=8) (
    input wire clk, we,
    input wire [ADDR_BITS-1:0] address,
    input wire [7:0] data,
    output reg [7:0] q
);
    reg [7:0] memory [0:(1<<ADDR_BITS)-1];
    always @(posedge clk) begin
        q <= memory[address];
        if (we) memory[address] <= data;
    end
endmodule
