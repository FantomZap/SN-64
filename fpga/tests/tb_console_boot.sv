`timescale 1ns/1ps
// Original diagnostic, no commercial ROM. Observations are at core ports.
module tb_console_boot;
    reg clk=0;
    always #23.28 clk=~clk;
    reg reset_n=0;
    wire [23:0] address;
    wire [7:0] data_out, peripheral_address;
    reg [7:0] data_in;
    wire rd_n,wr_n,phi2,prd_n,pwr_n;
    integer cycles=0, phi2_edges=0;
    reg [7:0] observed=0;
    reg peripheral_seen=0, mirror_seen=0;
    reg pal=0, corrupt_read=0;
    byte rom[0:511];
    integer pc=0;
    task emit(input byte b); rom[pc]=b; pc=pc+1; endtask
    task lda8(input byte b); emit('ha9); emit(b); endtask
    task sta(input logic [15:0] a); emit('h8d); emit(a[7:0]); emit(a[15:8]); endtask
    task store_reg(input logic [15:0] a,input byte b); lda8(b); sta(a); endtask
    task longop(input byte opcode,input logic [23:0] a);
        emit(opcode); emit(a[7:0]); emit(a[15:8]); emit(a[23:16]);
    endtask
    sn64_console_candidate dut(.clk(clk),.reset_n(reset_n),.enable(1'b1),.pal(pal),
        .cart_address(address),.cart_data_in(data_in),.cart_data_out(data_out),
        .cart_peripheral_address(peripheral_address),.cart_prd_n(prd_n),.cart_pwr_n(pwr_n),
        .cart_rd_n(rd_n),.cart_wr_n(wr_n),.cart_irq_n(1'b1),.cart_phi2(phi2),
        .cart_romsel_n(),.cart_wramsel_n(),.cart_refresh(),
        .joy1_di(2'b11),.joy2_di(2'b11),.joy_strobe(),.joy1_clock(),.joy2_clock(),
        .rgb(),.hsync(),.vsync(),.hde(),.vde(),.dot_clock(),.high_res(),.field(),.interlace(),
        .video_x(),.video_y(),.audio_left(),.audio_right(),.audio_ready());

    initial begin
        pal=$test$plusargs("pal");
        corrupt_read=$test$plusargs("corrupt_read");
        for(integer i=0;i<512;i=i+1) rom[i]='hea;
        emit('h78); emit('h18); emit('hfb); // SEI, CLC, XCE: native mode
        emit('hc2); emit('h30); // REP #$30: 16-bit A/X
        emit('ha9); emit('h5a); emit('ha5); longop('h8f,24'h700000);
        emit('ha9); emit('h34); emit('h12); longop('h8f,24'h7e0000);
        longop('haf,24'h7e0000); longop('h8f,24'h700002); // WRAM readback
        emit('he2); emit('h20); // 8-bit accumulator for mirrored WRAM write
        store_reg(16'h0010,8'h3c); // physical bus must retain $00:0010
        emit('hc2); emit('h20);
        longop('haf,24'h700010); longop('h8f,24'h700004); // external readback
        emit('he2); emit('h20); // SEP #$20: 8-bit A
        store_reg(16'h2141,8'h96); // visible B-bus write
        store_reg(16'h2181,8'h30); // WRAM port address = $00030
        store_reg(16'h2182,8'h00); store_reg(16'h2183,8'h00);
        store_reg(16'h4300,8'h00); // DMA0: A->B, increment, single register
        store_reg(16'h4301,8'h80); // B target $2180 (WRAM data port)
        store_reg(16'h4302,8'h10); store_reg(16'h4303,8'h00);
        store_reg(16'h4304,8'h70); // A source $700010
        store_reg(16'h4305,8'h02); store_reg(16'h4306,8'h00); // two bytes
        store_reg(16'h420b,8'h01); // start DMA0
        emit('hc2); emit('h20); // 16-bit A
        longop('haf,24'h7e0030); longop('h8f,24'h700006); // DMA WRAM readback
        emit('hdb); // STP after reporting
        repeat(20) @(negedge clk);
        reset_n=1;
    end
    // Full CPU address values for the diagnostic; cartridge owns ROM mapping.
    always @* begin
        data_in=8'hea;
        if(address>=24'h008000 && address<24'h008200) data_in=rom[address[8:0]];
        case(address)
            24'h00fffc: data_in=8'h00;
            24'h00fffd: data_in=8'h80;
            24'h700010: data_in=corrupt_read ? 8'h00 : 8'hef;
            24'h700011: data_in=8'hbe;
            default: ;
        endcase
    end
    always @(posedge phi2) if(reset_n) phi2_edges=phi2_edges+1;
    always @(negedge clk) begin
        cycles=cycles+1;
        if(reset_n && !pwr_n && peripheral_address==8'h41) begin
            if(data_out!==8'h96) $fatal(1,"B-bus data mismatch");
            peripheral_seen=1;
        end
        if(reset_n && !wr_n) begin
            if(data_out==8'h3c) begin
                if(address!==24'h000010) $fatal(1,"WRAM mirror address changed on cartridge bus: %h",address);
                mirror_seen=1;
            end
            case(address)
                24'h700000: begin if(data_out!==8'h5a) $fatal(1,"external low byte"); observed[0]=1; end
                24'h700001: begin if(data_out!==8'ha5) $fatal(1,"external high byte"); observed[1]=1; end
                24'h700002: begin if(data_out!==8'h34) $fatal(1,"WRAM low readback"); observed[2]=1; end
                24'h700003: begin if(data_out!==8'h12) $fatal(1,"WRAM high readback"); observed[3]=1; end
                24'h700004: begin if(data_out!==8'hef) $fatal(1,"cartridge low readback"); observed[4]=1; end
                24'h700005: begin if(data_out!==8'hbe) $fatal(1,"cartridge high readback"); observed[5]=1; end
                24'h700006: begin if(data_out!==8'hef) $fatal(1,"DMA low readback"); observed[6]=1; end
                24'h700007: begin if(data_out!==8'hbe) $fatal(1,"DMA high readback"); observed[7]=1; end
                default: ;
            endcase
        end
        if (&observed) begin
            if(!peripheral_seen || !mirror_seen || phi2_edges<20) $fatal(1,"Missing peripheral/mirror write or PHI2 clock");
            $display("PASS: reset/native CPU, cartridge R/W, WRAM, B-bus, DMA, PHI2; PAL flag=%0d; %0d clocks",pal,cycles);
            $finish;
        end
        if(cycles>20000) $fatal(1,"CPU boot timed out: address=%h writes=%b",address,observed);
    end
endmodule
