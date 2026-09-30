`timescale 1ns/1fs
// SPDX-License-Identifier: GPL-3.0-or-later
// Whole-system power-on simulation of sn64_top.
//
// Models: N64 host on the PI bus, Si5351 I2C slave, cartridge 5 V and
// interface rails that follow their enables, a SNES cartridge (ROM + SRAM
// that drive D0-D7 only while selected and /RD is low), and by default a
// cartridge with NO key CIC. The SNES master clock is generated only while
// sn64_top asserts snes_clk_run.
//
// Plusargs (one build, several runs in evaluate.py):
//   +pal_header / +ntsc_header  ROM header at $00:FFC0 (EU $02 / USA $01, valid checksum pair)
//   +pal_key / +ntsc_key        key CIC in the cartridge: the behavioural D413/F413 (PAL) or
//                               D411/F411 (NTSC) key model of tb_snes_cic_lock.sv, clocked by
//                               the lock's CIC_CLK; a passing key must win over the header
//   +corrupt_key                negative run: one key bit flipped in round 1; the bench still
//                               expects the key's region, so it must FAIL (the header decides)
// Every run also drives the cartridge-audio ADC lines with an I2S master
// (constant L/R words) and checks that the audio reaching the frame window is
// sat16(core DSP sample + ADC word) once the mixer is primed, and that the
// N64 reads REGION_INFO / REGION_SOURCE (0x1A / 0x1C) matching the decision.
//
// Flow checked: N64 reads MAGIC and STATUS -> writes controller image ->
// requests the cartridge -> rails come up with /RESET held -> Si5351 locked
// -> region decided -> SNES clock starts once -> /RESET released -> the SNES
// core runs an original program from the cartridge, writes SRAM, and reads
// the controller image through auto-joypad -> N64 reads STATUS = RUN.
// Invariants every clock: no socket drive before permission, the SNES clock
// never starts before cartridge power, the region never changes while the
// SNES clock runs, /RESET is held until the clock runs, the Si5351 is never
// accessed while the SNES clock runs, and Si5351 CLK2 is powered down with
// its output disabled when the SNES clock starts (no pixel clock: the picture
// goes to the console through the frame window, docs/design/console-video-path.md).
// Clocks: the SNES master follows region_pal (CLK0 NTSC / CLK1 PAL); the core
// has hardware-length lines (long dots restored in prepare_core.py).
module tb_system;
    // ---------------- Clocks ----------------
    reg clk_25=0, clk_host=0, clk_snes=0;
    always #20 clk_25 = ~clk_25;                  // 25 MHz
    always #8  clk_host = ~clk_host;              // 62.5 MHz
    wire snes_clk_run;
    // verilator lint_off ZERODLY
    always #(dut.region_pal ? 23.76 : 23.22892) clk_snes = snes_clk_run ? ~clk_snes : 1'b0;   // Si5351 CLK1 (PAL) / CLK0 (NTSC) master, gated by the board
    // verilator lint_on ZERODLY
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
    reg [7:0] si_regs [0:255]; reg [7:0] si_ptr = 0; integer si_writes = 0;
    initial for (integer i = 0; i < 256; i++) si_regs[i] = 8'h00;
    always @(negedge sda) if (scl) begin
        in_frame=1; bitc=0; addressed=0; have_reg=0; slave_low=0; ack_phase=0; send_phase=0;
        if (snes_clk_run) $fatal(1,"Si5351 accessed while the SNES clock runs");
    end
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
            else if (!have_reg) begin have_reg=1; si_ptr=shift; slave_low=1; ack_phase=1; end
            else begin si_regs[si_ptr]=shift; si_ptr=si_ptr+1; si_writes=si_writes+1; slave_low=1; ack_phase=1; end
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
    // Optional ROM header at $00:FFC0-$00:FFDF (+pal_header: EU $02, +ntsc_header: USA $01;
    // both with a valid checksum pair).
    reg  pal_header = 0, ntsc_header = 0; byte hdr[0:31];
    wire hdr_sel  = (pal_header || ntsc_header) && a >= 24'h00ffc0 && a <= 24'h00ffdf;
    wire cart_sel = (a>=24'h008000 && a<24'h008200) || a==24'h00fffc || a==24'h00fffd || a[23:8]==16'h7000 || hdr_sel;
    wire cart_drive = !rd_c && cart_sel && !ctl_oe_n && cart_5v_ok;
    reg [7:0] cart_byte;
    always @* begin
        cart_byte = 8'hxx;
        if (hdr_sel) cart_byte = hdr[a[4:0]];
        else if (a>=24'h008000 && a<24'h008200) cart_byte = rom[a[8:0]];
        else if (a==24'h00fffc) cart_byte = 8'h00;
        else if (a==24'h00fffd) cart_byte = 8'h80;
        else if (a[23:8]==16'h7000) cart_byte = sram[a[7:0]];
    end
    wire [7:0] bus_in = cart_drive ? cart_byte : 8'hxx;
    reg [23:0] a_hold; reg [7:0] d_hold;
    always @(negedge clk_snes) begin a_hold <= a; d_hold <= dout; end
    always @(posedge wr_c) if (!ctl_oe_n && a_hold[23:8]==16'h7000) sram[a_hold[7:0]] = d_hold;

    // SNES CIC lines: optional key CIC; released lines read low (pull-downs).
    wire cic_clk, cic_srst, d0o, d0oe, d1o, d1oe;
    logic k0_o = 1'b0, k0_oe = 1'b0, k1_o = 1'b0, k1_oe = 1'b0;
    wire line0 = d0oe ? d0o : (k0_oe ? k0_o : 1'b0);
    wire line1 = d1oe ? d1o : (k1_oe ? k1_o : 1'b0);
    integer cic_contention = 0;
    always @(posedge clk_25) if ((d0oe && k0_oe) || (d1oe && k1_oe)) cic_contention++;

    // ---------------- Key CIC model ----------------
    // Copied from the reference model in tb_snes_cic_lock.sv (SN64, GPL-3.0-or-later):
    // the key keeps its own copy of both streams, updates them with a C-style
    // implementation of the published table update (wiki.superfamicom.org/cic),
    // drives its bit on the pin the protocol assigns to the key and counts lock
    // bits that do not match. Timing is in CIC_CLK periods (4 per instruction).
    localparam int CPI        = 4;
    localparam int SEED_FIRST = 630 * CPI;
    localparam int SEED_PER   = 15 * CPI;
    localparam int SEED_HIGH  = 3 * CPI;
    localparam int ROUND1     = 806 * CPI;
    localparam int SLOT       = 93 * CPI;
    localparam int OUT_ON     = 10 * CPI;
    localparam int OUT_OFF    = 16 * CPI;
    localparam int SAMPLE     = 50;
    localparam int LAST_BASE  = 145;
    bit km_pal = 0, km_corrupt = 0;
    int km_mismatch = 0, km_rounds = 0;
    int tbl [0:1][0:15];
    int kt;
    function automatic int tb_mangle(int w);
        int d [0:15];
        int a, x, temp, off, carry, cost;
        for (int i = 0; i < 16; i++) d[i] = tbl[w][i];
        cost = 0;
        a = d[15];
        do begin
            x = a; off = 1; carry = 1;
            a = a + d[off] + carry; d[off] = a & 15; a = d[off]; off++;
            a = a + d[off] + carry; a = (~a) & 15; temp = a; a = d[off]; d[off] = temp & 15; off++;
            a = a + d[off] + carry;
            if (a < 16) begin
                temp = a; a = d[off]; d[off] = temp & 15; off++;
                cost += 78;
            end else begin
                cost += 84;
            end
            a = a + d[off]; d[off] = a & 15; a = d[off]; off++;
            carry = 0;
            a = a + d[off] + carry; temp = a; a = d[off]; d[off] = temp & 15; off++;
            a = a + 8;
            if (a < 16) a = a + d[off] + carry;
            temp = a; a = d[off]; d[off] = temp & 15; off++;
            while (off < 16) begin
                a = a + 1 + d[off]; d[off] = a & 15; a = d[off]; off++;
            end
            a = x + 15;
            if (a > 15) begin a = a & 15; carry = 1; end else carry = 0;
        end while (carry != 0);
        for (int i = 0; i < 16; i++) tbl[w][i] = d[i];
        return cost;
    endfunction
    task automatic advance_to(input int target);
        while (kt < target) begin
            @(posedge cic_clk);
            kt++;
        end
    endtask
    task automatic key_model();
        int lseed [0:15] = '{0, 'hb, 1, 4, 'hf, 4, 'hb, 5, 7, 'hf, 'hd, 6, 1, 'he, 9, 8};
        int kseed [0:15] = '{0, 0, 0, 'ha, 1, 8, 5, 'hf, 1, 1, 'he, 1, 0, 'hd, 'he, 'hc};
        int s, start, dir, slot_start, cost, r, bitv, b;
        k0_oe = 0; k1_oe = 0; k0_o = 0; k1_o = 0;
        @(posedge cic_srst);
        @(negedge cic_srst);
        kt = 0;
        k1_oe = 1; k1_o = 0;                          // seed: key listens on DATA0, drives DATA1 low
        s = 0;
        for (int k = 0; k < 4; k++) begin
            advance_to(SEED_FIRST + k * SEED_PER + SEED_HIGH / 2);
            @(negedge cic_clk);
            b = line0;
            case (k)
                0: s |= b << 3;
                1: s |= b << 0;
                2: s |= b << 1;
                default: s |= b << 2;
            endcase
        end
        advance_to(678 * CPI);
        k1_oe = 0;
        advance_to(692 * CPI);
        k0_oe = 1; k0_o = 0;
        for (int i = 0; i < 16; i++) begin
            tbl[0][i] = lseed[i];
            tbl[1][i] = kseed[i];
        end
        tbl[1][1] = s;
        tbl[1][2] = km_pal ? 6 : 9;
        start = 1; dir = 0; slot_start = ROUND1; r = 0;
        forever begin
            advance_to(slot_start);
            if (dir == 0) begin k0_oe = 1; k0_o = 0; end
            else          begin k1_oe = 1; k1_o = 0; end
            for (int i = start; i < 16; i++) begin
                bitv = tbl[1][i] & 1;
                if (km_corrupt && r == 0 && i == 5) bitv ^= 1;   // +corrupt_key: one wrong key bit in round 1
                advance_to(slot_start + OUT_ON);
                if (dir == 0) k0_o = bitv[0]; else k1_o = bitv[0];
                advance_to(slot_start + SAMPLE);
                @(negedge cic_clk);
                if ((dir == 0 ? line1 : line0) != tbl[0][i][0]) km_mismatch++;
                advance_to(slot_start + OUT_OFF);
                k0_o = 0; k1_o = 0;
                if (i == 15) begin
                    k0_oe = 0; k1_oe = 0;
                end else begin
                    slot_start += SLOT;
                end
            end
            cost = 0;
            for (int m = 0; m < 3; m++) cost += tb_mangle(0);
            for (int m = 0; m < 3; m++) cost += tb_mangle(1);
            slot_start += CPI * (LAST_BASE + cost + ((tbl[1][7] == 0) ? 7 : 5));
            start = (tbl[1][7] == 0) ? 1 : tbl[1][7];
            dir = tbl[1][7] & 1;
            r++;
            km_rounds = r;
        end
    endtask

    // ---------------- Cartridge-audio ADC (I2S master on its own time base) ----------------
    // Philips I2S, 24-bit words in 32-bit slots, BCK = 64 x 32 kHz (488.28125 ns);
    // WS/SD change 20 ns after each BCK falling edge. Constant words:
    // L = $123456 -> $1234, R = $DCBA98 -> $DCBA (negative) after the 24 -> 16 bit shift.
    localparam logic [23:0] ADC_L = 24'h123456, ADC_R = 24'hDCBA98;
    logic adc_bck = 1'b0, adc_lrck = 1'b0, adc_dout = 1'b0;
    initial begin : adc_master
        int j, p, sl;
        j = 0;
        #777;
        forever begin
            #224.140625 adc_bck = 1'b1;                    // rising edge r_j (period 488.28125 ns)
            #244.140625 adc_bck = 1'b0;
            #20;                                           // values the receiver samples at r_(j+1)
            p = (j + 1) % 32; sl = ((j + 1) / 32) % 2;
            adc_lrck = sl[0];
            adc_dout = (p >= 1 && p <= 24) ? (sl[0] ? ADC_R[24 - p] : ADC_L[24 - p]) : 1'b0;
            j++;
        end
    end
    // Audio reaching the frame window: SNES DSP sample alone while the mixer
    // primes, then sat16(DSP + ADC word) on every sample.
    function automatic logic [15:0] sat_add(input logic [15:0] a, input logic [15:0] b);
        int v;
        v = $signed(a) + $signed(b);
        return (v > 32767) ? 16'h7FFF : (v < -32768) ? 16'h8000 : 16'(v);
    endfunction
    integer audio_mixed = 0, audio_priming = 0, audio_bad = 0;
    reg mix_ready_q = 0;
    always @(posedge clk_snes) begin
        mix_ready_q <= dut.mix_audio_ready;
        if (dut.mix_audio_ready && !mix_ready_q) begin
            if (dut.cart_audio_active && dut.mix_audio_left === sat_add(dut.audio_mix.snes_left, ADC_L[23:8])
                                      && dut.mix_audio_right === sat_add(dut.audio_mix.snes_right, ADC_R[23:8]))
                audio_mixed++;
            else if (audio_mixed == 0 && dut.mix_audio_left === dut.audio_mix.snes_left && dut.mix_audio_right === dut.audio_mix.snes_right)
                audio_priming++;
            else begin
                audio_bad++;
                if (audio_bad <= 5) $display("audio at the frame window wrong: %h/%h, DSP %h/%h, active %0d",
                                             dut.mix_audio_left, dut.mix_audio_right, dut.audio_mix.snes_left, dut.audio_mix.snes_right, dut.cart_audio_active);
            end
        end
    end

    wire [15:0] status_word;
    wire region_pal;
    // REGION_TIMEOUT_MS = 20: the key's first round ends after the lock's table
    // update, whose length depends on the stream (8.0 ms after the interface
    // rail was not enough in the first +pal_key run: 800 + 12 + 3224 CIC clocks
    // of start-up, 15 x 372 of slots, then up to 6 table updates of several
    // 78/84-cycle iterations each). No-key runs still decide at key_fail (~1.7 ms).
    sn64_top #(.BUILD_ID(16'h5A01), .ROM_ADDR_BITS(4), .REGION_TIMEOUT_MS(20), .SEQ_RESET_HOLD_MS(1),
               .SEQ_RAIL_TIMEOUT_MS(2), .CIC_LOCK_T_PWRUP(200)) dut (
        .clk_25(clk_25), .clk_host(clk_host), .clk_snes(clk_snes), .por_n(por_n),
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
        .snes_cic_data0_o(d0o), .snes_cic_data0_oe(d0oe), .snes_cic_data0_i(line0),
        .snes_cic_data1_o(d1o), .snes_cic_data1_oe(d1oe), .snes_cic_data1_i(line1),
        .adc_bck(adc_bck), .adc_lrck(adc_lrck), .adc_dout(adc_dout),
        .status_word(status_word));

    // ---------------- Invariants ----------------
    reg run_seen=0, pal_at_start=0;
    always @(posedge clk_25) begin
        if (!ctl_oe_n && !dut.bus_permit && !dut.hdr_owns) $fatal(1,"socket outputs enabled without permission");
        if (dut.hdr_owns && (!wr_c || !pwr_c || !data_oe_n && data_dir || snes_clk_run || !cart_reset_pull))
            $fatal(1,"header probe: write strobe, D-bus drive, running clock or released /RESET");
        if (snes_clk_run && !(cart_5v_ok && iface_rail_ok)) $fatal(1,"SNES clock running without cartridge power");
        if (snes_clk_run && !run_seen) begin
            run_seen=1; pal_at_start=region_pal;
            // Si5351 image at SNES clock start: CLK0 (NTSC, PLLA) and CLK1 (PAL, PLLB) on,
            // CLK2 powered down and disabled (register 3 = 0xFC), MS2 never written.
            if (si_regs[16] !== 8'h4F || si_regs[17] !== 8'h6F || si_regs[18] !== 8'h80 || si_regs[3] !== 8'hFC)
                $fatal(1,"Si5351 clock controls wrong at SNES clock start (16=%h 17=%h 18=%h 3=%h)", si_regs[16], si_regs[17], si_regs[18], si_regs[3]);
            if (si_regs[58] !== 8'h00 || si_regs[61] !== 8'h00 || si_regs[62] !== 8'h00)
                $fatal(1,"Si5351 MultiSynth 2 programmed (no pixel clock exists)");
        end
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

    reg [15:0] d0, d1, d2, f0, f1, f2;
    integer t_start;
    bit key_present = 0, exp_pal = 0; bit [1:0] exp_src = 0;
    string exp_region_s, exp_src_s;
    initial begin
        for (integer i=0;i<512;i++) rom[i]='hea;
        pal_header  = $test$plusargs("pal_header");
        ntsc_header = $test$plusargs("ntsc_header") && !pal_header;
        key_present = $test$plusargs("pal_key") || $test$plusargs("ntsc_key");
        km_pal      = $test$plusargs("pal_key");
        km_corrupt  = $test$plusargs("corrupt_key");     // negative run: the key fails, so it must NOT decide
        exp_pal     = key_present ? km_pal : pal_header;
        exp_src     = key_present ? 2'd1 : (pal_header || ntsc_header) ? 2'd2 : 2'd3;
        exp_region_s = "NTSC"; if (exp_pal) exp_region_s = "PAL";
        exp_src_s = "NTSC default"; if (exp_src == 2'd1) exp_src_s = "key CIC"; else if (exp_src == 2'd2) exp_src_s = "ROM header";
        if (key_present) fork key_model(); join_none
        for (integer i=0;i<32;i++) hdr[i]=8'h20;
        hdr[5'h15]=8'h31; hdr[5'h19]=pal_header ? 8'h02 : 8'h01;       // HiROM fast, Europe (PAL) or USA (NTSC)
        hdr[5'h1C]=8'hA5; hdr[5'h1D]=8'h5A; hdr[5'h1E]=8'h5A; hdr[5'h1F]=8'hA5;  // complement $5AA5, checksum $A55A
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
        $display("%0.3f ms: SNES clock started (region %s, status %h)", $realtime / 1.0e6, region_pal ? "PAL" : "NTSC", status_word);
        $display("header probe: done=%0d valid=%0d pal=%0d country=%h reject=%b", dut.hdr_done, dut.hdr_valid, dut.hdr_pal, dut.hdr_country, dut.hdr_reject);
        $display("key CIC: present=%0d pal=%0d key_ok=%0d key_fail=%0d rounds=%0d mismatches=%0d", key_present, km_pal,
                 dut.cic_key_ok, dut.cic_key_fail, km_rounds, km_mismatch);
        if (!dut.hdr_done) $fatal(1,"region decided before the header probe finished");
        if (region_pal !== exp_pal) $fatal(1,"region %0d, expected %0d (key CIC > ROM header > NTSC default)", region_pal, exp_pal);
        if (key_present && (!dut.cic_key_ok || dut.cic_key_fail || km_mismatch != 0))
            $fatal(1,"key CIC exchange did not pass (ok %0d fail %0d, %0d lock bits wrong)", dut.cic_key_ok, dut.cic_key_fail, km_mismatch);
        wait(!cart_reset_pull);
        $display("%0.3f ms: cartridge /RESET released", $realtime / 1.0e6);
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
        if (d0[7]!==exp_pal || d0[13]!==key_present || d0[14]!==!key_present) $fatal(1,"STATUS region/key bits wrong: %h", d0);
        // N64 reads the region telemetry as the bootstrap does: pairs at 0x18 {COMMIT, REGION_INFO}, 0x1C {REGION_SOURCE, 0}.
        pi_addr(32'h1FFF_0018); pi_read(d1); pi_read(d1); pi_read(d2); pi_end;
        $display("REGION_INFO=%h REGION_SOURCE=%h (source %0d, decided %0d, timeout %0d, PAL %0d)", d1, d2, d2[1:0], d2[2], d2[3], d2[4]);
        if (d2[1:0]!==exp_src || !d2[2] || d2[4]!==exp_pal || d2[15:5]!==11'd0) $fatal(1,"REGION_SOURCE wrong: %h (expected source %0d, PAL %0d)", d2, exp_src, exp_pal);
        if (key_present && d2[3]) $fatal(1,"REGION_SOURCE: key decided but timeout flagged: %h", d2);
        if (!d1[12] || d1[15]) $fatal(1,"REGION_INFO: probe not done or aborted: %h", d1);
        if ((pal_header || ntsc_header) && (d1[13]!==1'b1 || d1[14]!==pal_header || d1[7:0]!==(pal_header ? 8'h02 : 8'h01) || d1[11:8]!==4'b0000))
            $fatal(1,"REGION_INFO does not show the valid %s header: %h", pal_header ? "EU" : "USA", d1);
        if (!(pal_header || ntsc_header) && (d1[13] || d1[11:8]==4'b0000)) $fatal(1,"REGION_INFO: absent header not rejected: %h", d1);
        if (cic_contention != 0) $fatal(1,"CIC data pins driven by lock and key at once (%0d clk_25 cycles)", cic_contention);
        // Console video path: the frame window has completed frames, VIDEO_MODE follows the
        // region, and the first two pixels read back through the PI carry the RGBA5551 alpha bit.
        pi_addr(32'h1FFF_001E); pi_read(f0); pi_read(f1); pi_read(f2); pi_end;
        $display("frame window: FRAME_STATUS=%h AUDIO_WPTR=%h VIDEO_MODE=%h", f0, f1, f2);
        if (f0[15:8] == 8'd0) $fatal(1,"frame window: no SNES frame completed");
        if (f2[3] !== region_pal) $fatal(1,"VIDEO_MODE pal bit %0d does not match the region", f2[3]);
        pi_addr(32'h0800_0000); pi_read(f1); pi_read(f2); pi_end;
        if (f1[0] !== 1'b1 || f2[0] !== 1'b1) $fatal(1,"frame pixels lack the RGBA5551 alpha bit: %h %h", f1, f2);
        // Cartridge audio reached the frame window mixed with the DSP samples.
        $display("audio at the frame window: %0d priming (DSP only), %0d mixed with the ADC words, %0d wrong; slips ovf %0d unf %0d; ADC frame errors %0d; Si5351 writes %0d",
                 audio_priming, audio_mixed, audio_bad, dut.audio_ovf_slips, dut.audio_unf_slips, dut.adc_frame_errors_h, si_writes);
        if (audio_bad != 0 || audio_mixed < 100) $fatal(1,"cartridge audio path: %0d wrong samples, only %0d mixed", audio_bad, audio_mixed);
        $display("PASS: system power-on: N64 mailbox, ordered cartridge power, Si5351 lock, region decided before the SNES clock (%s via %s), reset release, SNES program from cartridge, controller image via auto-joypad, cartridge audio mixed (%0d samples), STATUS=%h REGION_INFO=%h REGION_SOURCE=%h",
                 exp_region_s, exp_src_s, audio_mixed, d0, d1, d2);
        $finish;
    end
    initial begin #400_000_000; $fatal(1,"system test timed out (status %h)", status_word); end
endmodule
