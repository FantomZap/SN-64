`timescale 1ns/1fs
// SPDX-License-Identifier: GPL-3.0-or-later
// A real cartridge image through the whole SN64 logic (sn64_top).
//
// tb_system.sv proves the power-on order with a program of a few dozen bytes. This bench plugs
// in a cartridge that holds a real image (a game or a test program) and lets a model of the N64
// do what the boot program does while a game is shown (firmware/bootstrap/src/main.c):
//   * identify the SN64, write a controller image, ask for the cartridge (Play);
//   * once the cartridge runs, every picture: write the controller image and COMMIT, and fetch
//     the picture through the cartridge port in four parts, each as soon as FRAME_STATUS says
//     its lines are finished, at the fast domain-2 timing the program sets (one address latch a
//     line: the 512-byte page of PGS = 7).
// What the N64 would put on the screen is written out as pictures, and the sound as samples.
//
// The cartridge: ROM read through /ROMSEL and /RD as a cartridge board wires it (LoROM: A15 not
// connected; HiROM: A0-A21), battery RAM where the image's kind of board has it, an optional
// key CIC (the model of tb_system.sv). It drives D0-D7 only while it is selected and /RD is low;
// otherwise the bus keeps the last value driven on it, as a real bus does for a moment.
//
// Plusargs:
//   +rom=<file>        the image, without a copier header
//   +hirom             HiROM board (default LoROM)
//   +sram_kb=<n>       battery RAM in KiB (0: none)
//   +ntsc_key +pal_key the cartridge has a key CIC of that region
//   +frames=<n>        pictures to fetch after /RESET is released (default 60)
//   +shot=<k>          write every k-th picture (default 30) and always the last one
//   +out=<prefix>      output files <prefix>-fNNNNN.hex (one RGBA5551 word a line, 256 x 224),
//                      <prefix>-audio.hex (left, right, left, ... 16-bit), <prefix>-sram.hex
//   +pad=<file>        controller 1 script: lines "<from> <to> <hex>": the mailbox image (bit 0 B,
//                      Y, Select, Start, Up, Down, Left, Right, A, X, L, R bit 11) from picture
//                      <from> to picture <to>
// The checks of tb_system.sv that must hold on every clock are kept: no socket drive without
// permission, no SNES clock without cartridge power, no bus contention on D0-D7.
module tb_game;
    // ---------------- Clocks ----------------
    reg clk_25 = 0, clk_host = 0, clk_snes2 = 0;
    wire clk_snes;
    always #20 clk_25 = ~clk_25;                  // 25 MHz
    always #8  clk_host = ~clk_host;              // 62.5 MHz
    wire snes_clk_run;
    // verilator lint_off ZERODLY
    // twice the SNES master as the board's PLLs make it (42.954545 MHz NTSC, 42.564706 MHz PAL),
    // gated by the board (stops low), then the pace divider
    always #(dut.region_pal ? 11.746821 : 11.640212) clk_snes2 = (snes_clk_run || clk_snes2) ? ~clk_snes2 : 1'b0;
    wire [15:0] snes_pace;
    sn64_clock_pace pace (.clk2x(clk_snes2), .clk_host(clk_host), .rate(snes_pace), .clk_snes(clk_snes), .stretching());
    // verilator lint_on ZERODLY
    reg por_n = 0;

    // ---------------- N64 host (PI bus) ----------------
    reg n64_reset_n = 0, alel = 0, aleh = 0, rd_n = 1, wr_n = 1;
    reg host_drive = 0; reg [15:0] host_ad = 0;
    wire [15:0] ad = host_drive ? host_ad : 16'hzzzz;
    wire n64_cic_dq; pullup(n64_cic_dq);

    // ---------------- Power rails ----------------
    wire cart_5v_enable, iface_rail_enable;
    reg cart_5v_ok = 0, iface_rail_ok = 0;
    always @(posedge clk_25) begin
        cart_5v_ok    <= cart_5v_enable;
        iface_rail_ok <= iface_rail_enable & cart_5v_ok;
    end

    // ---------------- SNES cartridge ----------------
    wire [23:0] a; wire [7:0] pa, dout; wire rd_c, wr_c, prd_c, pwr_c, romsel, wramsel, refresh, phi2, sysclk;
    wire ctl_oe_n, data_oe_n, data_dir, cart_reset_pull;
    wire cart_reset_n = !cart_reset_pull;           // open-drain /RESET with pull-up, no cartridge pull
    localparam int ROM_MAX = 1 << 23, SRAM_MAX = 1 << 17;
    reg [7:0] rom  [0:ROM_MAX-1];
    reg [7:0] sram [0:SRAM_MAX-1];
    int rom_bytes = 0, sram_bytes = 0;
    bit hirom = 0;
    // What the cartridge board decodes. LoROM: the ROM answers /ROMSEL; a board with RAM gives the
    // lower half of banks $70-$7D and $F0-$FF to the RAM instead. HiROM: the ROM answers /ROMSEL
    // with A0-A21; the RAM is at $6000-$7FFF of banks $20-$3F and $A0-$BF, where /ROMSEL is high.
    wire lo_ram = !hirom && sram_bytes != 0 && !romsel && a[22:20] == 3'b111 && !a[15];
    wire hi_ram =  hirom && sram_bytes != 0 &&  romsel && a[22:21] == 2'b01 && a[15:13] == 3'b011;
    wire ram_sel = lo_ram || hi_ram;
    wire rom_sel = !romsel && !lo_ram;
    wire [22:0] rom_index = hirom ? {1'b0, a[21:0]} : {1'b0, a[22:16], a[14:0]};
    wire [17:0] hi_ram_index = {a[20:16], a[12:0]};
    wire [18:0] lo_ram_index = {a[19:16], a[14:0]};
    wire [16:0] ram_index = (hirom ? hi_ram_index[16:0] : lo_ram_index[16:0]) & 17'(sram_bytes - 1);
    wire cart_drive = !rd_c && (rom_sel || ram_sel) && !ctl_oe_n && cart_5v_ok;
    reg [7:0] cart_byte;
    always @* begin
        cart_byte = 8'hFF;
        if (ram_sel) cart_byte = sram[ram_index];
        else if (rom_sel && int'(rom_index) < rom_bytes) cart_byte = rom[rom_index];
    end
    // The bus keeps its last driven value while nobody drives it.
    reg [7:0] bus_hold = 8'hFF;
    wire fpga_drives = !data_oe_n && data_dir;
    wire [7:0] bus_in = cart_drive ? cart_byte : bus_hold;
    always @(negedge clk_snes) bus_hold <= cart_drive ? cart_byte : fpga_drives ? dout : bus_hold;
    // RAM write: on the rising edge of /WR, with the address and data of the clock before.
    reg [16:0] ram_index_hold; reg [7:0] d_hold; reg ram_sel_hold = 0;
    integer ram_writes = 0, rom_reads = 0;
    always @(negedge clk_snes) begin ram_index_hold <= ram_index; d_hold <= dout; ram_sel_hold <= ram_sel; end
    always @(posedge wr_c) if (!ctl_oe_n && ram_sel_hold && cart_5v_ok) begin sram[ram_index_hold] = d_hold; ram_writes++; end
    always @(negedge rd_c) if (rom_sel && !ctl_oe_n) rom_reads++;

    `include "snes_key_cic_model.svh"

    // ---------------- Cartridge-audio sigma-delta front end (RC model), silent cartridge ----------------
    localparam real ALPHA = 16.0e-9 / (10.0e3 * 1.0e-9);
    real vnode_l = 0.5, vnode_r = 0.5;
    wire aud_l_fb, aud_r_fb;
    wire aud_l_cmp = 0.5 > vnode_l, aud_r_cmp = 0.5 > vnode_r;
    always @(posedge clk_host) begin
        vnode_l <= vnode_l + ((aud_l_fb ? 1.0 : 0.0) - vnode_l) * ALPHA;
        vnode_r <= vnode_r + ((aud_r_fb ? 1.0 : 0.0) - vnode_r) * ALPHA;
    end

    // ---------------- The SN64 ----------------
    wire [15:0] status_word;
    wire region_pal;
    sn64_top #(.BUILD_ID(16'h5A01), .ROM_ADDR_BITS(4), .REGION_TIMEOUT_MS(20), .SEQ_RESET_HOLD_MS(1),
               .SEQ_RAIL_TIMEOUT_MS(2), .CIC_LOCK_T_PWRUP(200), .PACE_PRESENT(1)) dut (
        .clk_25(clk_25), .clk_host(clk_host), .clk_snes(clk_snes), .por_n(por_n),
        .n64_reset_n(n64_reset_n), .n64_nmi_n(1'b1), .n64_alel(alel), .n64_aleh(aleh), .n64_read_n(rd_n), .n64_write_n(wr_n),
        .n64_ad(ad), .n64_cic_clk(1'b1), .n64_si_clk(1'b0), .n64_cic_dq(n64_cic_dq),
        .rom_we(1'b0), .rom_waddr(4'd0), .rom_wdata(16'd0),
        .pll_locked(1'b1), .monitor_error(1'b0), .snes_clk_run(snes_clk_run), .region_pal(region_pal), .snes_pace(snes_pace),
        .ext_spi_sel_req(1'b0), .ext_spi_sck(1'b0), .ext_spi_cs_n(1'b1), .ext_spi_mosi(1'b0), .ext_spi_miso(), .ext_spi_active(),
        .host_3v3_ok(1'b1), .fpga_rails_ok(1'b1), .cart_5v_ok(cart_5v_ok), .iface_rail_ok(iface_rail_ok),
        .efuse_fault_n(1'b1), .overtemp(1'b0), .cart_5v_enable(cart_5v_enable), .iface_rail_enable(iface_rail_enable),
        .cart_probe_req(), .cart_probe_active(1'b0), .cart_probe_strobe(1'b0), .cart_probe_code(12'd0),
        .cart_address(a), .cart_pa(pa), .cart_rd_n(rd_c), .cart_wr_n(wr_c), .cart_prd_n(prd_c), .cart_pwr_n(pwr_c),
        .cart_romsel_n(romsel), .cart_wramsel_n(wramsel), .cart_refresh(refresh), .cart_phi2(phi2), .cart_sysclk(sysclk),
        .cart_data_out(dout), .cart_data_in(bus_in), .cart_irq_n(1'b1), .cart_reset_n_sense(cart_reset_n),
        .cart_reset_pull(cart_reset_pull), .ctl_oe_n(ctl_oe_n), .data_oe_n(data_oe_n), .data_dir(data_dir),
        .snes_cic_oe_n(), .snes_cic_clk(cic_clk), .snes_cic_slave_reset(cic_srst),
        .snes_cic_data0_o(d0o), .snes_cic_data0_oe(d0oe), .snes_cic_data0_i(line0),
        .snes_cic_data1_o(d1o), .snes_cic_data1_oe(d1oe), .snes_cic_data1_i(line1),
        .aud_l_cmp(aud_l_cmp), .aud_r_cmp(aud_r_cmp), .aud_l_fb(aud_l_fb), .aud_r_fb(aud_r_fb),
        .status_word(status_word));

    // ---------------- Invariants (as tb_system.sv) ----------------
    integer reset_low_clocks = 0; reg off_ok = 0, cart_5v_enable_q = 0;
    always @(posedge clk_25) begin
        // The socket's outputs: never on without cartridge power; at rest (no strobe, no clock, data
        // octet released) while neither the bridge nor the header probe owns them; and never
        // released while the cartridge is powered and out of reset.
        if (!ctl_oe_n && !(cart_5v_ok && iface_rail_ok)) $fatal(1, "socket outputs enabled without cartridge power");
        if (!ctl_oe_n && !dut.bus_permit && !dut.hdr_owns && (!wr_c || !rd_c || !prd_c || !pwr_c || !romsel || sysclk || !data_oe_n))
            $fatal(1, "socket not at rest while nobody owns it");
        if (cart_5v_ok && iface_rail_ok && !cart_reset_pull && ctl_oe_n) $fatal(1, "cartridge out of reset while the socket outputs are released");
        // Taking the 5 V away: /RESET has been low for the hold time (0.9 ms of the 1 ms here).
        if (cart_5v_enable) off_ok <= reset_low_clocks >= 22000;
        reset_low_clocks <= cart_reset_pull ? reset_low_clocks + 1 : 0;
        cart_5v_enable_q <= cart_5v_enable;
        if (cart_5v_enable_q && !cart_5v_enable && !off_ok && !dut.fault_latched) $fatal(1, "cartridge 5 V switched off without /RESET held first");
        if (snes_clk_run && !(cart_5v_ok && iface_rail_ok)) $fatal(1, "SNES clock running without cartridge power");
        if (!snes_clk_run && !cart_reset_pull && cart_5v_ok) $fatal(1, "cartridge /RESET released before the SNES clock runs");
    end
    integer contention = 0;
    always @(negedge clk_snes) if (cart_drive && fpga_drives) begin
        contention++;
        if (contention <= 5) $display("CONTENTION on D0-D7 at %h", a);
    end

    // ---------------- Sound as it reaches the frame window ----------------
    localparam int AUDIO_MAX = 1 << 22;                 // 2 words a sample: about a minute
    reg [15:0] audio [0:AUDIO_MAX-1];
    integer audio_words = 0, audio_nonzero = 0;
    reg mix_ready_q = 0;
    always @(posedge clk_snes) begin
        mix_ready_q <= dut.mix_audio_ready;
        if (dut.mix_audio_ready && !mix_ready_q && audio_words < AUDIO_MAX - 1) begin
            audio[audio_words] = dut.mix_audio_left; audio[audio_words + 1] = dut.mix_audio_right;
            audio_words += 2;
            if (dut.mix_audio_left != 0 || dut.mix_audio_right != 0) audio_nonzero++;
        end
    end

    // ---------------- N64 PI tasks ----------------
    task pi_addr(input [31:0] x); begin
        host_drive = 1; host_ad = x[31:16]; #100 aleh = 1; alel = 1; #300; host_ad = x[15:0]; aleh = 0; #300 alel = 0; #300 host_drive = 0; #100;
    end endtask
    task pi_read(output [15:0] d); begin #100 rd_n = 0; #400 d = ad; #20 rd_n = 1; #300; end endtask
    task pi_write(input [15:0] d); begin #100 host_drive = 1; host_ad = d; #100 wr_n = 0; #400 wr_n = 1; #100 host_drive = 0; #200; end endtask
    task pi_end; begin #100 aleh = 1; alel = 1; #300 aleh = 0; alel = 0; #300; end endtask
    // domain 2 as the boot program sets it (PWD 5, RLS 1): /RD low 6 cycles, high 2 cycles of 16 ns
    task pi_read_fast(output [15:0] d); begin rd_n = 0; #92 d = ad; #4 rd_n = 1; #32; end endtask

    // ---------------- Controller script ----------------
    localparam int PAD_MAX = 256;
    int pad_from [0:PAD_MAX-1], pad_to [0:PAD_MAX-1]; reg [15:0] pad_mask [0:PAD_MAX-1];
    int pad_rows = 0;
    function automatic [15:0] pad_at(input int picture);
        reg [15:0] m;
        m = 16'h0000;
        for (int i = 0; i < pad_rows; i++) if (picture >= pad_from[i] && picture <= pad_to[i]) m |= pad_mask[i];
        return m;
    endfunction

    // ---------------- One picture, fetched as the boot program fetches it ----------------
    reg [15:0] fb [0:256*224-1];
    integer missed = 0, repeated = 0, words_fetched = 0, last_frame0 = -1;
    task automatic fetch_picture(input int picture);
        reg [15:0] fs, w;
        int frame0, first, last;
        real t0;
        pi_addr(32'h1FFF_001E); pi_read(fs); pi_end;
        frame0 = int'(fs[15:8]);
        // one game picture a fetch: a jump of more than one is a picture the console never showed
        if (last_frame0 >= 0) begin
            if (((frame0 - last_frame0 + 256) % 256) > 1) missed++;
            if (frame0 == last_frame0) repeated++;
        end
        last_frame0 = frame0;
        for (int part = 0; part < 4; part++) begin
            first = part * 56; last = first + 55;
            t0 = $realtime;
            forever begin
                pi_addr(32'h1FFF_001E); pi_read(fs); pi_end;
                if (int'(fs[15:8]) != frame0) break;                                // the visible lines are all finished
                if (fs[7:0] != 8'hFF && int'(fs[7:0]) >= last) break;                // these lines are finished
                if ($realtime - t0 > 40.0e6) $fatal(1, "picture %0d part %0d: lines never finished (FRAME_STATUS %h)", picture, part, fs);
                #20000;
            end
            for (int y = first; y <= last; y++) begin
                pi_addr(32'h0800_0000 + y * 512);
                for (int x = 0; x < 256; x++) begin
                    pi_read_fast(w);
                    fb[y * 256 + x] = w;
                    words_fetched++;
                end
                pi_end;
            end
            if (part == 0) begin
                // the controllers after the first part, as the program does: one update and COMMIT a picture
                pi_addr(32'h1FFF_0010); pi_write(pad_at(picture)); pi_write(16'h0000); pi_end;      // JOY1, JOY2
                pi_addr(32'h1FFF_0014); pi_write(16'h0000); pi_write(16'h0001); pi_end;             // STICK, CONTROL: run request
                pi_addr(32'h1FFF_0018); pi_write(16'h0001); pi_write(16'h0000); pi_end;             // COMMIT
            end
        end
    endtask

    string rom_path, out_prefix, pad_path;
    int frames = 60, shot = 30;
    reg [15:0] d0, d1, d2, ph;
    int fd, got, started;
    bit key_present = 0;
    integer lit;
    initial begin
        if (!$value$plusargs("rom=%s", rom_path)) $fatal(1, "give the image with +rom=<file>");
        if (!$value$plusargs("out=%s", out_prefix)) out_prefix = "game";
        void'($value$plusargs("frames=%d", frames));
        void'($value$plusargs("shot=%d", shot));
        void'($value$plusargs("sram_kb=%d", sram_bytes));
        sram_bytes = sram_bytes * 1024;
        hirom = $test$plusargs("hirom");
        key_present = $test$plusargs("pal_key") || $test$plusargs("ntsc_key");
        km_pal = $test$plusargs("pal_key");
        for (int i = 0; i < SRAM_MAX; i++) sram[i] = 8'hFF;                 // a new battery RAM chip reads ones
        fd = $fopen(rom_path, "rb");
        if (fd == 0) $fatal(1, "cannot open %s", rom_path);
        rom_bytes = $fread(rom, fd);
        $fclose(fd);
        if (rom_bytes < 32768) $fatal(1, "%s: only %0d bytes", rom_path, rom_bytes);
        if ($value$plusargs("pad=%s", pad_path)) begin
            fd = $fopen(pad_path, "r");
            if (fd == 0) $fatal(1, "cannot open %s", pad_path);
            while (pad_rows < PAD_MAX) begin
                got = $fscanf(fd, "%d %d %h", pad_from[pad_rows], pad_to[pad_rows], pad_mask[pad_rows]);
                if (got != 3) break;
                pad_rows++;
            end
            $fclose(fd);
        end
        $display("cartridge: %0d bytes, %s, %0d bytes of battery RAM, key CIC %s; %0d pad rows; %0d pictures, one written every %0d",
                 rom_bytes, hirom ? "HiROM" : "LoROM", sram_bytes, key_present ? (km_pal ? "PAL" : "NTSC") : "none", pad_rows, frames, shot);
        if (key_present) fork key_model(); join_none

        repeat (20) @(posedge clk_25); por_n = 1;
        repeat (20) @(posedge clk_25); n64_reset_n = 1;                    // console out of reset
        #2000;
        // The boot program: identify, a neutral controller image, ask for the cartridge.
        pi_addr(32'h1FFF_0000); pi_read(d0); pi_read(d1); pi_end;
        if (d0 !== 16'h534E) $fatal(1, "mailbox identity wrong: %h %h", d0, d1);
        pi_addr(32'h1FFF_0010); pi_write(16'h0000); pi_write(16'h0000); pi_end;
        pi_addr(32'h1FFF_0014); pi_write(16'h0000); pi_write(16'h0001); pi_end;             // CONTROL: run request
        pi_addr(32'h1FFF_0018); pi_write(16'h0001); pi_write(16'h0000); pi_end;             // COMMIT
        wait (snes_clk_run);
        $display("%0.3f ms: SNES clock started, region %s (header probe: valid %0d, country %h; key ok %0d, fail %0d)",
                 $realtime / 1.0e6, region_pal ? "PAL" : "NTSC", dut.hdr_valid, dut.hdr_country, dut.cic_key_ok, dut.cic_key_fail);
        wait (!cart_reset_pull);
        $display("%0.3f ms: cartridge /RESET released", $realtime / 1.0e6);
        // Pictures. On a console the frame lock holds the game a few lines into its picture at
        // the console's vertical interrupt; here each fetch starts when the game starts a picture.
        pi_addr(32'h1FFF_0024); pi_read(ph); pi_end;
        started = int'(ph[15:11]);
        for (int n = 1; n <= frames; n++) begin
            forever begin
                pi_addr(32'h1FFF_0024); pi_read(ph); pi_end;
                if (int'(ph[15:11]) != started && ph[10:0] != 11'h7FF) break;
                #20000;
            end
            started = int'(ph[15:11]);
            fetch_picture(n);
            if (n % shot == 0 || n == frames) begin
                lit = 0;
                for (int i = 0; i < 256 * 224; i++) if (fb[i][15:1] != 15'd0) lit++;
                $writememh($sformatf("%s-f%05d.hex", out_prefix, n), fb);
                $writememh($sformatf("%s-audio.hex", out_prefix), audio, 0, audio_words > 0 ? audio_words - 1 : 0);
                pi_addr(32'h1FFF_0004); pi_read(d0); pi_end;
                $display("%0.1f ms: picture %0d written: %0d of 57344 pixels lit; STATUS %h; %0d ROM reads, %0d RAM writes, %0d sound samples (%0d not silent), %0d pictures missed, %0d fetched twice, %0d bus contentions",
                         $realtime / 1.0e6, n, lit, d0, rom_reads, ram_writes, audio_words / 2, audio_nonzero, missed, repeated, contention);
            end
        end
        if (sram_bytes != 0) $writememh($sformatf("%s-sram.hex", out_prefix), sram, 0, sram_bytes - 1);
        pi_addr(32'h1FFF_0004); pi_read(d0); pi_end;
        pi_addr(32'h1FFF_0020); pi_read(d1); pi_read(d2); pi_end;
        if (contention != 0) $fatal(1, "bus contention on D0-D7 on %0d clocks", contention);
        if (cic_contention != 0) $fatal(1, "CIC data pins driven by lock and key at once");
        if (d0[11:8] !== 4'd4 || !d0[12]) $fatal(1, "STATUS %h: the cartridge is not running at the end", d0);
        $display("DONE: %0d pictures fetched through the cartridge port (%0d words, %0d missed, %0d fetched twice); region %s; VIDEO_MODE %h; STATUS %h; %0d ROM reads; %0d RAM writes; %0d sound samples, %0d not silent; no bus contention",
                 frames, words_fetched, missed, repeated, region_pal ? "PAL" : "NTSC", d2, d0, rom_reads, ram_writes, audio_words / 2, audio_nonzero);
        $finish;
    end
endmodule
