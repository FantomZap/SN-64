`timescale 1ns/1ps
// SPDX-License-Identifier: GPL-3.0-or-later
// Whole-system power-on simulation of sn64_top.
//
// Models: N64 host on the PI bus, Si5351 I2C slave, cartridge 5 V and
// interface rails that follow their enables, a SNES cartridge (ROM + SRAM
// that drive D0-D7 only while selected and /RD is low), and a cartridge with
// NO key CIC (the lock times out and NTSC is used). The SNES master clock is
// generated only while sn64_top asserts snes_clk_run.
//
// Flow checked: N64 reads MAGIC and STATUS -> writes controller image ->
// requests the cartridge -> rails come up with /RESET held -> Si5351 locked
// -> region decided -> SNES clock starts once -> /RESET released -> the SNES
// core runs an original program from the cartridge, writes SRAM, and reads
// the controller image through auto-joypad -> N64 reads STATUS = RUN.
// Invariants every clock: no socket drive before permission, the SNES clock
// never starts before cartridge power, the region never changes while the
// SNES clock runs, /RESET is held until the clock runs.
module tb_system;
    // ---------------- Clocks ----------------
    reg clk_25=0, clk_host=0, clk_snes=0;
    always #20 clk_25 = ~clk_25;                  // 25 MHz
    always #8  clk_host = ~clk_host;              // 62.5 MHz
    reg clk_pixel=0, clk_pixel_x5=0;
    always #18.505 clk_pixel = ~clk_pixel;        // 27.0198 MHz (Si5351 CLK2)
    always #3.701  clk_pixel_x5 = ~clk_pixel_x5;  // 5x TMDS
    wire snes_clk_run;
    always #23.28 clk_snes = snes_clk_run ? ~clk_snes : 1'b0;   // Si5351 NTSC master, gated by the board
    reg por_n=0;

    // ---------------- N64 host (PI bus) ----------------
    reg n64_reset_n=0, alel=0, aleh=0, rd_n=1, wr_n=1;
    reg host_drive=0; reg [15:0] host_ad=0;
    wire [15:0] ad = host_drive ? host_ad : 16'hzzzz;
    wire n64_cic_dq; pullup(n64_cic_dq);

    // ---------------- Si5351 I2C slave ----------------
    wire scl_oe, sda_oe; reg slave_low=0;
    wire scl = scl_oe ? 1'b0 : 1'b1;
    wire sda = (sda_oe || slave_low) ? 1'b0 : 1'b1;
    integer status_reads=0; reg [7:0] shift, tx; integer bitc=0; reg in_frame=0, addressed=0, is_read=0, have_reg=0, ack_phase=0, send_phase=0;
    always @(negedge sda) if (scl) begin in_frame=1; bitc=0; addressed=0; have_reg=0; slave_low=0; ack_phase=0; send_phase=0; end
    always @(posedge sda) if (scl) begin in_frame=0; slave_low=0; end
    always @(posedge scl) if (in_frame) begin
        if (send_phase) begin bitc=bitc+1; if (bitc==9) begin send_phase=0; bitc=0; end end
        else if (!ack_phase) begin shift={shift[6:0],sda}; bitc=bitc+1; end
    end
    always @(negedge scl) if (in_frame) begin
        if (ack_phase) begin slave_low=0; ack_phase=0; bitc=0;
            if (is_read && addressed && have_reg==0) begin send_phase=1; tx=(status_reads<3)?8'h80:8'h00; status_reads=status_reads+1; slave_low=!tx[7]; end
        end else if (send_phase) begin if (bitc<8) slave_low=!tx[7-bitc]; else slave_low=0; end
        else if (bitc==8) begin
            if (!addressed) begin if (shift[7:1]==7'h60) begin addressed=1; is_read=shift[0]; slave_low=1; ack_phase=1; end end
            else if (!have_reg) begin have_reg=1; slave_low=1; ack_phase=1; end
            else begin slave_low=1; ack_phase=1; end
        end
    end

    // ---------------- Power rails ----------------
    wire cart_5v_enable, iface_rail_enable;
    reg cart_5v_ok=0, iface_rail_ok=0;
    always @(posedge clk_25) begin
        cart_5v_ok    <= cart_5v_enable;
        iface_rail_ok <= iface_rail_enable & cart_5v_ok;
    end

    // ---------------- SNES cartridge ----------------
    wire [23:0] a; wire [7:0] pa, dout; wire rd_c, wr_c, prd_c, pwr_c, romsel, wramsel, refresh, phi2, sysclk;
    wire ctl_oe_n, data_oe_n, data_dir, cart_reset_pull;
    wire cart_reset_n = !cart_reset_pull;           // open-drain /RESET with pull-up, no cartridge pull
    byte rom[0:511]; byte sram[0:255];
    wire cart_sel = (a>=24'h008000 && a<24'h008200) || a==24'h00fffc || a==24'h00fffd || a[23:8]==16'h7000;
    wire cart_drive = !rd_c && cart_sel && !ctl_oe_n && cart_5v_ok;
    reg [7:0] cart_byte;
    always @* begin
        cart_byte = 8'hxx;
        if (a>=24'h008000 && a<24'h008200) cart_byte = rom[a[8:0]];
        else if (a==24'h00fffc) cart_byte = 8'h00;
        else if (a==24'h00fffd) cart_byte = 8'h80;
        else if (a[23:8]==16'h7000) cart_byte = sram[a[7:0]];
    end
    wire [7:0] bus_in = cart_drive ? cart_byte : 8'hxx;
    reg [23:0] a_hold; reg [7:0] d_hold;
    always @(negedge clk_snes) begin a_hold <= a; d_hold <= dout; end
    always @(posedge wr_c) if (!ctl_oe_n && a_hold[23:8]==16'h7000) sram[a_hold[7:0]] = d_hold;

    // SNES CIC lines: no key CIC in this cartridge; released lines read low.
    wire cic_clk, cic_srst, d0o, d0oe, d1o, d1oe;

    wire [15:0] status_word;
    wire region_pal;
    sn64_top #(.BUILD_ID(16'h5A01), .ROM_ADDR_BITS(4), .REGION_TIMEOUT_MS(1), .SEQ_RESET_HOLD_MS(1),
               .SEQ_RAIL_TIMEOUT_MS(2), .CIC_LOCK_T_PWRUP(200)) dut (
        .clk_25(clk_25), .clk_host(clk_host), .clk_snes(clk_snes), .clk_pixel(clk_pixel), .clk_pixel_x5(clk_pixel_x5), .por_n(por_n),
        .n64_reset_n(n64_reset_n), .n64_nmi_n(1'b1), .n64_alel(alel), .n64_aleh(aleh), .n64_read_n(rd_n), .n64_write_n(wr_n),
        .n64_ad(ad), .n64_cic_clk(1'b1), .n64_si_clk(1'b0), .n64_cic_dq(n64_cic_dq),
        .rom_we(1'b0), .rom_waddr(4'd0), .rom_wdata(16'd0),
        .si_scl_oe(scl_oe), .si_sda_oe(sda_oe), .si_sda_in(sda), .snes_clk_run(snes_clk_run), .region_pal(region_pal),
        .host_3v3_ok(1'b1), .fpga_rails_ok(1'b1), .cart_5v_ok(cart_5v_ok), .iface_rail_ok(iface_rail_ok),
        .efuse_fault_n(1'b1), .overtemp(1'b0), .cart_5v_enable(cart_5v_enable), .iface_rail_enable(iface_rail_enable),
        .cart_address(a), .cart_pa(pa), .cart_rd_n(rd_c), .cart_wr_n(wr_c), .cart_prd_n(prd_c), .cart_pwr_n(pwr_c),
        .cart_romsel_n(romsel), .cart_wramsel_n(wramsel), .cart_refresh(refresh), .cart_phi2(phi2), .cart_sysclk(sysclk),
        .cart_data_out(dout), .cart_data_in(bus_in), .cart_irq_n(1'b1), .cart_reset_n_sense(cart_reset_n),
        .cart_reset_pull(cart_reset_pull), .ctl_oe_n(ctl_oe_n), .data_oe_n(data_oe_n), .data_dir(data_dir),
        .snes_cic_oe_n(),.snes_cic_clk(cic_clk), .snes_cic_slave_reset(cic_srst),
        .snes_cic_data0_o(d0o), .snes_cic_data0_oe(d0oe), .snes_cic_data0_i(d0oe & d0o),
        .snes_cic_data1_o(d1o), .snes_cic_data1_oe(d1oe), .snes_cic_data1_i(d1oe & d1o),
        .hdmi_tmds(), .hdmi_tmds_clock(), .av_locked(),
        .status_word(status_word));

    // ---------------- Invariants ----------------
    reg run_seen=0, pal_at_start=0;
    always @(posedge clk_25) begin
        if (!ctl_oe_n && !dut.bus_permit) $fatal(1,"socket outputs enabled without permission");
        if (snes_clk_run && !(cart_5v_ok && iface_rail_ok)) $fatal(1,"SNES clock running without cartridge power");
        if (snes_clk_run && !run_seen) begin run_seen=1; pal_at_start=region_pal; end
        if (snes_clk_run && region_pal !== pal_at_start) $fatal(1,"region changed while the SNES clock runs");
        if (!snes_clk_run && !cart_reset_pull && cart_5v_ok) $fatal(1,"cartridge /RESET released before the SNES clock runs");
    end
    reg cart_drive_d=0;
    always @(negedge clk_snes) if (cart_drive && !data_oe_n && data_dir) $fatal(1,"CONTENTION on D0-D7 at %h", a);

    // ---------------- N64 PI tasks ----------------
    task pi_addr(input [31:0] x); begin
        host_drive=1; host_ad=x[31:16]; #100 aleh=1; alel=1; #300; host_ad=x[15:0]; aleh=0; #300 alel=0; #300 host_drive=0; #100;
    end endtask
    task pi_read(output [15:0] d); begin #100 rd_n=0; #400 d=ad; #20 rd_n=1; #300; end endtask
    task pi_write(input [15:0] d); begin #100 host_drive=1; host_ad=d; #100 wr_n=0; #400 wr_n=1; #100 host_drive=0; #200; end endtask
    task pi_end; begin #100 aleh=1; alel=1; #300 aleh=0; alel=0; #300; end endtask

    // ---------------- Cartridge program ----------------
    integer pc=0;
    task emit(input byte b); rom[pc]=b; pc=pc+1; endtask
    task lda8(input byte b); emit('ha9); emit(b); endtask
    task stal(input logic [23:0] x); emit('h8f); emit(x[7:0]); emit(x[15:8]); emit(x[23:16]); endtask
    task ldal(input logic [23:0] x); emit('haf); emit(x[7:0]); emit(x[15:8]); emit(x[23:16]); endtask

    localparam [15:0] JOY = 16'h0A5B;  // mailbox image: B,Y,Start,Up,Left,A,R... (bit0=B .. bit11=R)
    wire [7:0] exp_4219 = {JOY[0],JOY[1],JOY[2],JOY[3],JOY[4],JOY[5],JOY[6],JOY[7]};
    wire [7:0] exp_4218 = {JOY[8],JOY[9],JOY[10],JOY[11],4'b0000};

    reg [15:0] d0, d1, d2;
    integer t_start;
    initial begin
        for (integer i=0;i<512;i++) rom[i]='hea;
        for (integer i=0;i<256;i++) sram[i]='h00;
        emit('h78); emit('h18); emit('hfb); emit('he2); emit('h30);   // SEI CLC XCE SEP #$30
        lda8('ha5); stal(24'h700000);                                  // proof of life
        lda8('h01); stal(24'h004200);                                  // NMITIMEN: auto-joypad on
        // wait for auto-joypad: loop until HVBJOY ($4212) bit0 rises then falls, twice (one full frame)
        for (integer k=0;k<2;k++) begin
            ldal(24'h004212); emit('h29); emit('h01); emit('hf0); emit('hf8);  // wait busy=1  (LDA/AND/BEQ -8)
            ldal(24'h004212); emit('h29); emit('h01); emit('hd0); emit('hf8);  // wait busy=0  (BNE -8)
        end
        ldal(24'h004218); stal(24'h700010);
        ldal(24'h004219); stal(24'h700011);
        lda8('hc3); stal(24'h7000f0);                                  // end marker
        emit('hdb);                                                    // STP

        repeat(20) @(posedge clk_25); por_n=1;
        repeat(20) @(posedge clk_25); n64_reset_n=1;                   // console out of reset
        #2000;
        // N64 bootstrap behaviour: identify, send controller image, request the cartridge.
        pi_addr(32'h1FFF_0000); pi_read(d0); pi_read(d1); pi_read(d2); pi_end;
        if (d0!==16'h534E || d1!==16'h5A01) $fatal(1,"mailbox identity wrong: %h %h", d0, d1);
        pi_addr(32'h1FFF_0010); pi_write(JOY); pi_end;
        pi_addr(32'h1FFF_0018); pi_write(16'h0000); pi_end;            // COMMIT
        pi_addr(32'h1FFF_0016); pi_write(16'h0001); pi_end;            // CONTROL: run_request (region auto)
        wait(snes_clk_run); t_start=$time;
        $display("%0t ns: SNES clock started (region %s, status %h)", $time, region_pal ? "PAL" : "NTSC", status_word);
        wait(!cart_reset_pull);
        $display("%0t ns: cartridge /RESET released", $time);
        fork
            wait(sram[8'hf0]==8'hc3);
            #80_000_000;
        join_any
        disable fork;
        if (sram[8'hf0]!==8'hc3) $fatal(1,"SNES program did not finish (SRAM0=%h)", sram[0]);
        if (sram[0]!==8'ha5) $fatal(1,"proof-of-life write missing");
        if (sram[8'h11]!==exp_4219 || sram[8'h10]!==exp_4218)
            $fatal(1,"controller image did not reach the SNES: $4219=%h (exp %h) $4218=%h (exp %h)", sram[8'h11], exp_4219, sram[8'h10], exp_4218);
        // N64 reads STATUS: RUN, Si5351 locked, SNES clock running.
        repeat(200) @(posedge clk_host);
        pi_addr(32'h1FFF_0004); pi_read(d0); pi_end;
        if (d0[11:8]!==4'd4 || !d0[12] || !d0[0] || !d0[4] || !d0[6] || d0[5]) $fatal(1,"STATUS wrong: %h", d0);
        $display("PASS: system power-on: N64 mailbox, ordered cartridge power, Si5351 lock, region decided before the SNES clock, reset release, SNES program from cartridge, controller image via auto-joypad, STATUS=%h", d0);
        $finish;
    end
    initial begin #400_000_000; $fatal(1,"system test timed out (status %h)", status_word); end
endmodule
