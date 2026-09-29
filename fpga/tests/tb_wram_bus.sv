`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Cartridge-observable WRAM data, before the CPU's end-of-cycle MDR update.
module tb_wram_bus;
    reg clk=0, reset_n=0, enable=1, run_clk=1, data_tests_done=0;
    always #23.28 if(run_clk) clk=~clk;
    wire [23:0] address;
    wire [7:0] data_out, pa;
    reg [7:0] data_in;
    wire rd_n,wr_n,prd_n,pwr_n,wsel_n,wram_valid;
    byte rom[0:511];
    integer pc=0, cycles=0, port_reads=0;
    reg old_prd_n=1;
    reg [3:0] reads_seen=0;
    reg [1:0] dma_seen=0;
    task emit(input byte b); rom[pc]=b; pc=pc+1; endtask
    task lda8(input byte b); emit('ha9); emit(b); endtask
    task sta(input logic [15:0] a); emit('h8d); emit(a[7:0]); emit(a[15:8]); endtask
    task store_reg(input logic [15:0] a,input byte b); lda8(b); sta(a); endtask
    task longop(input byte opcode,input logic [23:0] a);
        emit(opcode); emit(a[7:0]); emit(a[15:8]); emit(a[23:16]);
    endtask
    sn64_console_candidate dut(.clk(clk),.reset_n(reset_n),.enable(enable),.pal(1'b0),
        .cart_address(address),.cart_data_in(data_in),.cart_data_out(data_out),
        .cart_peripheral_address(pa),.cart_prd_n(prd_n),.cart_pwr_n(pwr_n),
        .cart_rd_n(rd_n),.cart_wr_n(wr_n),.cart_irq_n(1'b1),.cart_phi2(),
        .cart_romsel_n(),.cart_wramsel_n(wsel_n),.cart_refresh(),.cart_wram_read_valid(wram_valid),
        .joy1_di(2'b11),.joy2_di(2'b11),.joy_strobe(),.joy1_clock(),.joy2_clock(),
        .rgb(),.hsync(),.vsync(),.hde(),.vde(),.dot_clock(),.high_res(),.field(),.interlace(),
        .video_x(),.video_y(),.audio_left(),.audio_right(),.audio_ready());
    initial begin
        for(integer i=0;i<512;i=i+1) rom[i]='hea;
        emit('h78); emit('h18); emit('hfb); // SEI, CLC, XCE
        lda8('ha5); longop('h8f,24'h7e0010);
        lda8('h5a); longop('h8f,24'h7e0011);
        longop('haf,24'h7e0010); longop('haf,24'h7e0011);
        longop('haf,24'h000010); longop('haf,24'h800011);
        store_reg(16'h2181,'h10); store_reg(16'h2182,0); store_reg(16'h2183,0);
        longop('haf,24'h002180); longop('haf,24'h002180); // CPU WRAM-port reads
        store_reg(16'h2181,'h10); // rewind port for B->A DMA
        store_reg(16'h4300,'h80); store_reg(16'h4301,'h80);
        store_reg(16'h4302,'h20); store_reg(16'h4303,0); store_reg(16'h4304,'h70);
        store_reg(16'h4305,2); store_reg(16'h4306,0); store_reg(16'h420b,1);
        emit('hdb);
        repeat(20) @(negedge clk);
        reset_n=1;
        wait(wram_valid);
        @(negedge clk);
        run_clk=0;
        #5 enable=0;
        #5 if(wram_valid) $fatal(1,"Paused WRAM falsely valid with stopped clock");
        #50 enable=1;
        #5 if(!wram_valid) $fatal(1,"WRAM source did not resume");
        run_clk=1;
        wait(data_tests_done);
        run_clk=0;
        #5 reset_n=0;
        #5 if(wram_valid) $fatal(1,"Reset WRAM falsely valid with stopped clock");
        $display("PASS: active-cycle WRAM data, both mirrors, WRAM-port reads, B-to-A DMA, pause/reset source validity (%0d clocks)",cycles);
        $finish;
    end
    always @* begin
        data_in=8'hff; // no cartridge response for internal memory
        if(address>=24'h008000 && address<24'h008200) data_in=rom[address[8:0]];
        if(address==24'h00fffc) data_in=0;
        if(address==24'h00fffd) data_in='h80;
    end
    always @(negedge clk) begin
        cycles=cycles+1;
        if(reset_n && enable && !rd_n && !wsel_n) begin
            if(!wram_valid) $fatal(1,"Selected WRAM read missing source-valid flag");
            case(address)
                24'h7e0010: begin if(data_out!==8'ha5) $fatal(1,"Direct WRAM read exposes stale data: %h",data_out); reads_seen[0]=1; end
                24'h7e0011: begin if(data_out!==8'h5a) $fatal(1,"Second WRAM byte mismatch"); reads_seen[1]=1; end
                24'h000010: begin if(data_out!==8'ha5) $fatal(1,"Low mirror read mismatch"); reads_seen[2]=1; end
                24'h800011: begin if(data_out!==8'h5a) $fatal(1,"High mirror read mismatch"); reads_seen[3]=1; end
                default: ;
            endcase
        end
        if(reset_n && !prd_n && old_prd_n && pa==8'h80 && wsel_n) begin
            if(!wram_valid) $fatal(1,"WRAM-port read missing source-valid flag");
            if(data_out !== ((port_reads%2)==0 ? 8'ha5 : 8'h5a)) $fatal(1,"WRAM port byte mismatch");
            port_reads=port_reads+1;
        end
        if(reset_n && !wr_n && address==24'h700020) begin
            if(data_out!==8'ha5) $fatal(1,"B-to-A DMA first byte mismatch");
            dma_seen[0]=1;
        end
        if(reset_n && !wr_n && address==24'h700021) begin
            if(data_out!==8'h5a) $fatal(1,"B-to-A DMA second byte mismatch");
            dma_seen[1]=1;
        end
        old_prd_n=prd_n;
        if((&reads_seen) && (&dma_seen) && port_reads==4) begin
            data_tests_done=1;
        end
        if(cycles>20000) $fatal(1,"WRAM bus test timed out: reads=%b DMA=%b port=%0d",reads_seen,dma_seen,port_reads);
    end
endmodule
