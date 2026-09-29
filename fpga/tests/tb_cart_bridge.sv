`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Physical-bus model for the cartridge bridge. Unlike the earlier diagnostics
// this testbench models a real shared bus: every participant declares what it
// drives, and the test fails on any overlapping drive (contention), on any
// console output while the bus is not permitted, on a write strobe that ends
// without valid FPGA data, and on wrong data reaching the core or the
// cartridge. Original diagnostic program; no commercial ROM.
module tb_cart_bridge;
    reg clk=0, reset_n=0, permit=0;
    always #23.28 clk=~clk;

    // Socket side
    wire [23:0] a; wire [7:0] pa, fpga_dout; wire rd_n,wr_n,prd_n,pwr_n,romsel_n,wramsel_n,refresh,phi2,sysclk;
    wire ctl_oe_n, data_oe_n, data_dir, guard, reset_pull_n;
    reg  [7:0] cart_drive_byte; reg cart_driving;   // cartridge's own driver
    wire [7:0] bus_to_fpga = cart_driving ? cart_drive_byte : 8'hxx;

    sn64_console_with_bridge dut(.clk(clk),.reset_n(reset_n),.enable(1'b1),.pal(1'b0),.bus_permit(permit),
        .cart_address(a),.cart_pa(pa),.cart_rd_n(rd_n),.cart_wr_n(wr_n),.cart_prd_n(prd_n),.cart_pwr_n(pwr_n),
        .cart_romsel_n(romsel_n),.cart_wramsel_n(wramsel_n),.cart_refresh(refresh),.cart_phi2(phi2),.cart_sysclk(sysclk),
        .cart_data_out(fpga_dout),.cart_data_in(bus_to_fpga),.cart_irq_n(1'b1),.cart_reset_n_sense(1'b1),
        .cart_reset_pull_n(reset_pull_n),.ctl_oe_n(ctl_oe_n),.data_oe_n(data_oe_n),.data_dir(data_dir),.contention_guard(guard),
        .joy1_di(2'b11),.joy2_di(2'b11),.joy_strobe(),.joy1_clock(),.joy2_clock(),
        .rgb(),.hsync(),.vsync(),.hde(),.vde(),.dot_clock(),.high_res(),.field(),.interlace(),
        .video_x(),.video_y(),.audio_left(),.audio_right(),.audio_ready());

    // Diagnostic program helpers (8-bit accumulator throughout)
    byte rom[0:511]; integer pc=0, cycles=0;
    task emit(input byte b); rom[pc]=b; pc=pc+1; endtask
    task lda8(input byte b); emit('ha9); emit(b); endtask
    task sta(input logic [15:0] x); emit('h8d); emit(x[7:0]); emit(x[15:8]); endtask
    task store_reg(input logic [15:0] x,input byte b); lda8(b); sta(x); endtask
    task ldal(input logic [23:0] x); emit('haf); emit(x[7:0]); emit(x[15:8]); emit(x[23:16]); endtask
    task stal(input logic [23:0] x); emit('h8f); emit(x[7:0]); emit(x[15:8]); emit(x[23:16]); endtask

    // Cartridge model: ROM at $00:8000-81FF, vectors, SRAM at $70:0000-$70:00FF.
    // It drives D0-7 ONLY while /RD is low and the address selects it, exactly
    // like a real mask ROM/SRAM with /OE tied to the console strobe.
    byte sram[0:255];
    wire cart_selected = (a>=24'h008000 && a<24'h008200) || a==24'h00fffc || a==24'h00fffd || (a[23:8]==16'h7000);
    always @* begin
        cart_driving = !rd_n && cart_selected && !ctl_oe_n;
        cart_drive_byte = 8'hxx;
        if (a>=24'h008000 && a<24'h008200) cart_drive_byte = rom[a[8:0]];
        else if (a==24'h00fffc) cart_drive_byte = 8'h00;
        else if (a==24'h00fffd) cart_drive_byte = 8'h80;
        else if (a[23:8]==16'h7000) cart_drive_byte = sram[a[7:0]];
    end
    // SRAM latches on the rising edge of /WR. A real SRAM samples the address
    // and data present just BEFORE the edge; the bridge changes address on the
    // same clock edge that raises /WR, so the model samples on the preceding
    // falling clock edge (half a clock earlier), like the physical part.
    reg [23:0] a_hold; reg [7:0] d_hold; reg drv_hold;
    always @(negedge clk) begin a_hold<=a; d_hold<=fpga_dout; drv_hold<=!data_oe_n && data_dir; end
    always @(posedge wr_n) if (a_hold[23:8]==16'h7000 && !ctl_oe_n) begin
        if (!drv_hold) $fatal(1,"Write strobe ended without FPGA driving data: a=%h",a_hold);
        sram[a_hold[7:0]] = d_hold;
    end

    // --- Bus monitor: the physical rules ------------------------------------
    wire fpga_driving_data = !data_oe_n && data_dir;
    wire listening = !data_oe_n && !data_dir;
    always @(negedge clk) begin
        cycles=cycles+1;
        if (cart_driving && fpga_driving_data) $fatal(1,"CONTENTION: cartridge and FPGA both drive D0-7 at a=%h t=%0d",a,cycles);
        if (!permit && !ctl_oe_n) $fatal(1,"Console outputs enabled without permission");
        if (!permit && !data_oe_n) $fatal(1,"Data translator enabled without permission");
        if (!permit && reset_pull_n) $fatal(1,"Cartridge reset released without permission");
        if (!rd_n && !wr_n) $fatal(1,"Read and write strobes both active");
        // While the cartridge is selected for a read, the FPGA must be listening
        // (after the one-clock turnaround) so the core samples real data.
        if (cycles>40000) $fatal(1,"Bridge test timed out at a=%h",a);
    end
    // Every drive<->listen transition must pass through a released clock.
    reg prev_drive=0, prev_listen=0;
    always @(posedge clk) begin
        if (fpga_driving_data && prev_listen) $fatal(1,"Listen->drive without release clock");
        if (listening && prev_drive) $fatal(1,"Drive->listen without release clock");
        prev_drive<=fpga_driving_data; prev_listen<=listening;
    end

    // --- Data checks --------------------------------------------------------
    // The program copies values through the cartridge and WRAM and stores every
    // readback into SRAM $70:0040.. so the bench verifies them, then writes
    // $C3 to $70:00F0 as the end marker.
    integer turnarounds=0;
    always @(posedge clk) if (guard && permit && reset_n) turnarounds=turnarounds+1;
    always @(posedge wr_n) if (a_hold==24'h7000f0 && !ctl_oe_n) begin
        if (sram[8'h10]!==8'h5a || sram[8'h11]!==8'ha5) $fatal(1,"SRAM write wrong: %h %h",sram[8'h10],sram[8'h11]);
        if (sram[8'h40]!==8'h5a || sram[8'h41]!==8'ha5) $fatal(1,"SRAM readback through core wrong: %h %h",sram[8'h40],sram[8'h41]);
        if (sram[8'h42]!==8'h34 || sram[8'h43]!==8'h12) $fatal(1,"WRAM readback wrong: %h %h",sram[8'h42],sram[8'h43]);
        if (sram[8'h20]!==8'h34 || sram[8'h21]!==8'h12) $fatal(1,"DMA WRAM->cartridge wrong: %h %h",sram[8'h20],sram[8'h21]);
        if (sram[8'h44]!==8'h77) $fatal(1,"ROM byte readback wrong: %h",sram[8'h44]);
        if (turnarounds<8) $fatal(1,"Too few bus turnarounds observed: %0d",turnarounds);
        $display("PASS: bridge contention-free; cart ROM/SRAM read+write, WRAM, WRAM->cart DMA, %0d turnarounds, %0d clocks",turnarounds,cycles);
        $finish;
    end

    initial begin
        for(integer i=0;i<512;i=i+1) rom[i]='hea;
        for(integer i=0;i<256;i=i+1) sram[i]='h00;
        rom[9'h1f0]='h77;                             // known ROM byte at $00:81F0
        emit('h78); emit('h18); emit('hfb);           // SEI CLC XCE (native)
        emit('he2); emit('h30);                       // SEP #$30: 8-bit A/X
        lda8('h5a); stal(24'h700010);                 // cartridge SRAM writes
        lda8('ha5); stal(24'h700011);
        ldal(24'h700010); stal(24'h700040);           // read back through the core, store
        ldal(24'h700011); stal(24'h700041);
        lda8('h34); stal(24'h7e0100);                 // WRAM writes
        lda8('h12); stal(24'h7e0101);
        ldal(24'h7e0100); stal(24'h700042);           // WRAM readback to cartridge
        ldal(24'h7e0101); stal(24'h700043);
        ldal(24'h0081f0); stal(24'h700044);           // ROM byte to cartridge
        store_reg(16'h2181,'h00); store_reg(16'h2182,'h01); store_reg(16'h2183,'h00); // WRAM port = $000100
        store_reg(16'h4300,'h80); store_reg(16'h4301,'h80); // B->A, src $2180
        store_reg(16'h4302,'h20); store_reg(16'h4303,'h00); store_reg(16'h4304,'h70); // dest $70:0020
        store_reg(16'h4305,'h02); store_reg(16'h4306,'h00); store_reg(16'h420b,'h01); // 2 bytes, go
        lda8('hc3); stal(24'h7000f0);                 // end marker
        emit('hdb);                                   // STP
        repeat(20) @(negedge clk);
        // Bring-up order: reset held and bus released; permit first, then release reset.
        permit=1; repeat(4) @(negedge clk);
        reset_n=1;
    end
endmodule
