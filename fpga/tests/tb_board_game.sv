`timescale 1ns/1fs
// SPDX-License-Identifier: GPL-3.0-or-later
// A real cartridge image through the SN64 v2 board as its board file wires it.
//
// tb_game.sv runs a game through the logic (sn64_top) with the cartridge and the N64 joined to
// it signal by signal. Here the logic is the board's real top level (sn64_board_top: the PLLs,
// the supply watcher, the boot ROM in the flash), on its balls in a copy of the
// board: build/board-sim/sn64_board_netlist.sv, which hardware/sn64-v2/tools/make_board_sim.py
// writes from the board file's own connection list, with a model of each part on its pads
// (board_models.sv, ecp5_sim_stubs.sv). The cartridge is plugged into the socket's pins by their
// numbers and the N64 onto the edge fingers by theirs (board_pins.svh, from the connector tables
// that were drawn from other people's working boards). A signal the board takes to the wrong
// pin does not arrive, and the game does not run.
//
// Nothing of the start-up is shortened: the supply watcher's first readings over I2C, the
// cartridge check's test current into the rail's real capacitance, the cartridge switch, the
// reset hold, the key CIC and the header read all take the time they take on the board.
//
// At the end the cartridge is powered off the way the menu does it, and the order is checked:
// /RESET low, then the socket pins released, then the 5 V gone, and no write to the battery RAM.
//
// The cartridge: as in tb_game.sv (ROM through /ROMSEL and /RD, battery RAM where the image's
// kind of board has it, an optional key CIC), but on pins. It lives only while it has its 5 V,
// and its battery RAM takes a write only while /RESET is high, as the cartridge's own guard does.
// The data pins keep their last driven value while nobody drives them.
//
// Plusargs: those of tb_game.sv, and
//   +cartridge=<n>     0 nothing in the socket, 1 a cartridge (default), 2 a cartridge back to
//                      front: the board must refuse it, and the run ends with REFUSED
//   +bootrom=<file>    the boot program image: put into the flash where the logic expects it,
//                      and its first words are read back through the N64's cartridge port
//   +start_ms=<n>      give up if the game has not started after this long (default 3000)
//   +stop_ms=<n>       end the run at this time, whatever it is doing (to measure the speed)
//   +b_off_a=<0|1>     what an always-on level shifter byte puts out while the cartridge's 5 V
//                      is off (board_models.sv); without it the pins are released
`define FPGA board.U1
`define SN64_KEY_ON_PINS
module tb_board_game;
    `include "board_pins.svh"
    // ---------------- The board ----------------
    tri [50:1] j1;
    tri [62:1] j2;
    reg [1:0] cartridge = 2'd1;
    wire cart_rail_on, led, bus_a_conflict, shifter_rule_broken;
    wire [15:0] cart_rail_mv;
    wire [62:1] j2_drive, j2_pull_low;
    sn64_board board (.j1(j1), .j2(j2), .cartridge(cartridge), .cart_rail_on(cart_rail_on), .cart_rail_mv(cart_rail_mv),
                      .j2_drive(j2_drive), .j2_pull_low(j2_pull_low), .bus_a_conflict(bus_a_conflict),
                      .shifter_rule_broken(shifter_rule_broken), .led(led));
    wire tick = `FPGA.osc_27;                       // the board's own 27 MHz: the bench's checks add no events of their own
    always #1_000_000 $fflush();                    // so that the log can be followed while it runs
    int stop_ms = 0;
    initial if ($value$plusargs("stop_ms=%d", stop_ms)) begin
        #(stop_ms * 1.0e6) $display("STOP: %0d ms reached", stop_ms);
        $finish;
    end
    wire clk_snes = `FPGA.clk_snes;                 // the logic's SNES clock, to time the bench's samples
    wire snes_clk_run = `FPGA.snes_clk_run;

    // ---------------- N64 host on the edge fingers ----------------
    reg n64_reset_n = 0, alel = 0, aleh = 0, rd_n = 1, wr_n = 1;
    reg host_drive = 0; reg [15:0] host_ad = 0;
    wire [15:0] ad;
    for (genvar i = 0; i < 16; i++) begin : g_ad
        assign j1[J1_AD[i]] = host_drive ? host_ad[i] : 1'bz;
        assign ad[i] = j1[J1_AD[i]];
    end
    assign j1[J1_RESET] = n64_reset_n;
    assign j1[J1_ALE_L] = alel;
    assign j1[J1_ALE_H] = aleh;
    assign j1[J1_READ] = rd_n;
    assign j1[J1_WRITE] = wr_n;
    assign j1[J1_NMI] = 1'b1;
    assign j1[J1_CIC_CLK] = 1'b1;
    assign j1[J1_PIF_CLK] = 1'b0;

    // ---------------- SNES cartridge in the socket ----------------
    wire powered = cart_rail_on && cartridge == 2'd1;
    wire [23:0] a; wire [7:0] d_pins, board_drives_d;
    for (genvar i = 0; i < 24; i++) begin : g_a
        assign a[i] = j2[J2_A[i]];
    end
    wire rd_c = j2[J2_RD], wr_c = j2[J2_WR], romsel = j2[J2_ROMSEL], cart_reset_n = j2[J2_RESET];
    localparam int ROM_MAX = 1 << 23, SRAM_MAX = 1 << 17;
    reg [7:0] rom  [0:ROM_MAX-1];
    reg [7:0] sram [0:SRAM_MAX-1];
    int rom_bytes = 0, sram_bytes = 0;
    bit hirom = 0;
    // What the cartridge board decodes: see tb_game.sv.
    wire lo_ram = !hirom && sram_bytes != 0 && !romsel && a[22:20] == 3'b111 && !a[15];
    wire hi_ram =  hirom && sram_bytes != 0 &&  romsel && a[22:21] == 2'b01 && a[15:13] == 3'b011;
    wire ram_sel = lo_ram || hi_ram;
    wire rom_sel = !romsel && !lo_ram;
    wire [22:0] rom_index = hirom ? {1'b0, a[21:0]} : {1'b0, a[22:16], a[14:0]};
    wire [17:0] hi_ram_index = {a[20:16], a[12:0]};
    wire [18:0] lo_ram_index = {a[19:16], a[14:0]};
    wire [16:0] ram_index = (hirom ? hi_ram_index[16:0] : lo_ram_index[16:0]) & 17'(sram_bytes - 1);
    wire cart_drive = powered && !rd_c && (rom_sel || ram_sel);
    reg [7:0] cart_byte;
    always @* begin
        cart_byte = 8'hFF;
        if (ram_sel) cart_byte = sram[ram_index];
        else if (rom_sel && int'(rom_index) < rom_bytes) cart_byte = rom[rom_index];
    end
    // The data pins: the cartridge, or else what was last driven on them (while the board does not drive).
    reg [7:0] bus_hold = 8'hFF;
    for (genvar i = 0; i < 8; i++) begin : g_d
        assign board_drives_d[i] = j2_drive[J2_D[i]];
        assign j2[J2_D[i]] = cart_drive ? cart_byte[i] : !board_drives_d[i] ? bus_hold[i] : 1'bz;
        assign d_pins[i] = j2[J2_D[i]];
    end
    wire fpga_drives = |board_drives_d;
    always @(negedge clk_snes) if (cart_drive || fpga_drives) bus_hold <= d_pins;
    // RAM write: on the rising edge of /WR, with the address and data of the clock before; only a
    // cartridge that has its 5 V and is out of reset takes it.
    reg [16:0] ram_index_hold; reg [7:0] d_hold; reg ram_sel_hold = 0;
    integer ram_writes = 0, rom_reads = 0;
    always @(negedge clk_snes) begin ram_index_hold <= ram_index; d_hold <= d_pins; ram_sel_hold <= ram_sel; end
    always @(posedge wr_c) if (powered && cart_reset_n && ram_sel_hold) begin sram[ram_index_hold] = d_hold; ram_writes++; end
    always @(negedge rd_c) if (powered && rom_sel) rom_reads++;

    // The key CIC on its pins.
    wire cic_clk = j2[J2_CIC_CLK], cic_srst = j2[J2_CIC_SLAVE_RESET];
    logic k0_o = 1'b0, k0_oe = 1'b0, k1_o = 1'b0, k1_oe = 1'b0;
    assign j2[J2_CIC_DATA0] = (powered && k0_oe) ? k0_o : 1'bz;
    assign j2[J2_CIC_DATA1] = (powered && k1_oe) ? k1_o : 1'bz;
    wire line0 = j2[J2_CIC_DATA0], line1 = j2[J2_CIC_DATA1];
    `include "snes_key_cic_model.svh"

    // ---------------- Checks on every clock ----------------
    integer contention = 0, cic_contention = 0, a_conflicts = 0, loose = 0;
    reg led_in_game = 0;
    always @(negedge clk_snes) if (cart_drive && fpga_drives) begin
        contention++;
        if (contention <= 5) $display("CONTENTION on D0-D7 at %h", a);
    end
    always @(posedge tick) begin
        if (bus_a_conflict) a_conflicts++;
        // a level shifter byte enabled while its 5 V side has no supply (after the board's own reset)
        if (shifter_rule_broken && $realtime > 1.0e6)
            $fatal(1, "%0.3f ms: a level shifter byte is enabled while its 5 V side has no supply (TI SCAS416Q section 10)", $realtime / 1.0e6);
        // the key drives a 1 while the board's open-drain driver holds the same line low
        if ((powered && k0_oe && k0_o && j2_pull_low[J2_CIC_DATA0]) || (powered && k1_oe && k1_o && j2_pull_low[J2_CIC_DATA1])) cic_contention++;
        // the cartridge has power and is out of reset while nothing drives its control pins
        if (powered && cart_reset_n && !j2_drive[J2_WR]) begin
            loose++;
            if (loose == 1) $display("%0.3f ms: cartridge out of reset while its control pins are not driven", $realtime / 1.0e6);
        end
        if (snes_clk_run && !cart_rail_on) $fatal(1, "SNES clock running without cartridge power");
    end

    // Power-off order: when each thing happened after the N64 side dropped its request.
    real t_off_req = -1.0, t_reset_low = -1.0, t_out_off = -1.0, t_rail_off = -1.0;
    wire ctl_driven = j2_drive[J2_WR];
    always @(negedge cart_reset_n) if (t_off_req >= 0.0 && t_reset_low < 0.0) t_reset_low = $realtime;
    always @(negedge ctl_driven)   if (t_off_req >= 0.0 && t_out_off < 0.0) t_out_off = $realtime;
    always @(negedge cart_rail_on) if (t_off_req >= 0.0 && t_rail_off < 0.0) t_rail_off = $realtime;

    // What the board does on the way to a running game.
    reg [3:0] seq_q = 4'hF; reg rail_q = 0; reg [3:0] seq_now;
    always @(posedge tick) begin
        seq_now = `FPGA.top.seq_state;
        if (seq_now != seq_q) begin
            seq_q <= seq_now;
            $display("%0.3f ms: sequencer %0s; cartridge rail %0d mV", $realtime / 1.0e6,
                     seq_now == 0 ? "OFF" : seq_now == 1 ? "RESET" : seq_now == 2 ? "RAMP5" : seq_now == 3 ? "IFACE" :
                     seq_now == 4 ? "RUN" : seq_now == 5 ? "SHUTDOWN" : seq_now == 6 ? "FAULT" : seq_now == 7 ? "PROBE" :
                     seq_now == 8 ? "PROBE_END" : "PROBE_HOLD", cart_rail_mv);
        end
        if (cart_rail_on != rail_q) begin
            rail_q <= cart_rail_on;
            $display("%0.3f ms: cartridge 5 V %0s", $realtime / 1.0e6, cart_rail_on ? "on" : "off");
        end
    end

    // ---------------- Sound as it reaches the frame window ----------------
    localparam int AUDIO_MAX = 1 << 22;
    reg [15:0] audio [0:AUDIO_MAX-1];
    integer audio_words = 0, audio_nonzero = 0;
    reg mix_ready_q = 0;
    always @(posedge clk_snes) begin
        mix_ready_q <= `FPGA.top.mix_audio_ready;
        if (`FPGA.top.mix_audio_ready && !mix_ready_q && audio_words < AUDIO_MAX - 1) begin
            audio[audio_words] = `FPGA.top.mix_audio_left; audio[audio_words + 1] = `FPGA.top.mix_audio_right;
            audio_words += 2;
            if (`FPGA.top.mix_audio_left != 0 || `FPGA.top.mix_audio_right != 0) audio_nonzero++;
        end
    end

    // ---------------- N64 PI tasks (tb_game.sv) ----------------
    task pi_addr(input [31:0] x); begin
        host_drive = 1; host_ad = x[31:16]; #100 aleh = 1; alel = 1; #300; host_ad = x[15:0]; aleh = 0; #300 alel = 0; #300 host_drive = 0; #100;
    end endtask
    task pi_read(output [15:0] d); begin #100 rd_n = 0; #400 d = ad; #20 rd_n = 1; #300; end endtask
    task pi_write(input [15:0] d); begin #100 host_drive = 1; host_ad = d; #100 wr_n = 0; #400 wr_n = 1; #100 host_drive = 0; #200; end endtask
    task pi_end; begin #100 aleh = 1; alel = 1; #300 aleh = 0; alel = 0; #300; end endtask
    // domain 2 as the boot program sets it (PWD 5, RLS 1): /RD low 6 cycles, high 2 cycles of 16 ns
    task pi_read_fast(output [15:0] d); begin rd_n = 0; #92 d = ad; #4 rd_n = 1; #32; end endtask
    // domain 1 as the console reads a cartridge's ROM (LAT 0x40, PWD 0x12, RLS 3): /RD falls 1040 ns
    // after the address is latched, is low for 304 ns and high for 64 ns
    task pi_read_rom(output [15:0] d); begin rd_n = 0; #300 d = ad; #4 rd_n = 1; #64; end endtask

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
                if (int'(fs[15:8]) != frame0) break;
                if (fs[7:0] != 8'hFF && int'(fs[7:0]) >= last) break;
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
                pi_addr(32'h1FFF_0010); pi_write(pad_at(picture)); pi_write(16'h0000); pi_end;      // JOY1, JOY2
                pi_addr(32'h1FFF_0014); pi_write(16'h0000); pi_write(16'h0001); pi_end;             // STICK, CONTROL: run request
                pi_addr(32'h1FFF_0018); pi_write(16'h0001); pi_write(16'h0000); pi_end;             // COMMIT
            end
        end
    endtask

    localparam int BOOT_MAX = 1 << 18;                 // the boot program's 256 KiB window
    localparam [23:0] FLASH_OFFSET = 24'h40_0000;      // where sn64_top looks for it in the flash
    reg [7:0] boot [0:BOOT_MAX-1];
    string rom_path, out_prefix, pad_path, boot_path;
    int frames = 60, shot = 30, start_ms = 3000, cart_arg = 1;
    reg [15:0] d0, d1, d2, ph, w16, status_end;
    integer writes_before, loose_before;
    int fd, got, started, boot_bytes = 0, boot_bad = 0;
    bit key_present = 0, refused = 0;
    integer lit;
    real t_req;
    initial begin
        if (!$value$plusargs("rom=%s", rom_path)) $fatal(1, "give the image with +rom=<file>");
        if (!$value$plusargs("out=%s", out_prefix)) out_prefix = "game";
        void'($value$plusargs("frames=%d", frames));
        void'($value$plusargs("shot=%d", shot));
        void'($value$plusargs("start_ms=%d", start_ms));
        void'($value$plusargs("cartridge=%d", cart_arg));
        cartridge = cart_arg[1:0];
        void'($value$plusargs("sram_kb=%d", sram_bytes));
        sram_bytes = sram_bytes * 1024;
        hirom = $test$plusargs("hirom");
        key_present = $test$plusargs("pal_key") || $test$plusargs("ntsc_key");
        km_pal = $test$plusargs("pal_key");
        for (int i = 0; i < SRAM_MAX; i++) sram[i] = 8'hFF;
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
        if ($value$plusargs("bootrom=%s", boot_path)) begin
            fd = $fopen(boot_path, "rb");
            if (fd == 0) $fatal(1, "cannot open %s", boot_path);
            boot_bytes = $fread(boot, fd);
            $fclose(fd);
            for (int i = 0; i < boot_bytes; i++) board.flash_poke(FLASH_OFFSET + 24'(i), boot[i]);
        end
        $display("cartridge: %0d bytes, %s, %0d bytes of battery RAM, key CIC %s; %0d pad rows; %0d pictures, one written every %0d; in the socket: %0s; boot program in the flash: %0d bytes",
                 rom_bytes, hirom ? "HiROM" : "LoROM", sram_bytes, key_present ? (km_pal ? "PAL" : "NTSC") : "none", pad_rows, frames, shot,
                 cartridge == 0 ? "nothing" : cartridge == 1 ? "the cartridge" : "the cartridge, back to front", boot_bytes);
        if (key_present && cartridge == 2'd1) fork key_model(); join_none

        #400_000;                                       // the board's supervisor has let go and its PLLs are locked
        n64_reset_n = 1;                                // console out of reset
        #2000;
        // The boot program: identify, a neutral controller image, ask for the cartridge.
        pi_addr(32'h1FFF_0000); pi_read(d0); pi_read(d1); pi_end;
        if (d0 !== 16'h534E) $fatal(1, "mailbox identity wrong: %h %h", d0, d1);
        $display("%0.3f ms: the N64 side reads the SN64's identity through the edge fingers: %h %h", $realtime / 1.0e6, d0, d1);
        if (boot_bytes != 0) begin
            // What the console does first on a real start: read the boot program out of the cartridge.
            pi_addr(32'h1000_0000); #640;
            for (int i = 0; i < 32; i++) begin
                pi_read_rom(w16);
                if (w16 !== {boot[2 * i], boot[2 * i + 1]}) begin
                    boot_bad++;
                    if (boot_bad <= 4) $display("boot program word %0d: read %h, the image has %h", i, w16, {boot[2 * i], boot[2 * i + 1]});
                end
            end
            pi_end;
            pi_addr(32'h1000_0000 + 32'(boot_bytes) - 32'd64); #640;
            for (int i = 0; i < 32; i++) begin
                pi_read_rom(w16);
                if (w16 !== {boot[boot_bytes - 64 + 2 * i], boot[boot_bytes - 64 + 2 * i + 1]}) boot_bad++;
            end
            pi_end;
            if (boot_bad != 0) $fatal(1, "the boot program does not read back from the flash through the cartridge port: %0d of 64 words wrong", boot_bad);
            $display("%0.3f ms: the boot program reads back from the flash through the cartridge port (its first and last 32 words)", $realtime / 1.0e6);
        end
        pi_addr(32'h1FFF_0010); pi_write(16'h0000); pi_write(16'h0000); pi_end;
        pi_addr(32'h1FFF_0014); pi_write(16'h0000); pi_write(16'h0001); pi_end;             // CONTROL: run request
        pi_addr(32'h1FFF_0018); pi_write(16'h0001); pi_write(16'h0000); pi_end;             // COMMIT
        t_req = $realtime;
        $display("%0.3f ms: Play asked for", $realtime / 1.0e6);
        // The program polls STATUS until the cartridge runs or the board says no.
        forever begin
            pi_addr(32'h1FFF_0004); pi_read(d0); pi_end;
            if (d0[11:8] == 4'd4 && d0[12]) break;
            // bit 15 is up until the converter has answered once; if it still is after 40 ms it never will
            if (d0[15] && $realtime - t_req > 40.0e6)
                $fatal(1, "STATUS %h: the supply converter does not answer on its I2C address; the board never powers a cartridge", d0);
            if (d0[11:8] == 4'd6) begin
                pi_addr(32'h1FFF_0008); pi_read(d1); pi_read(d2); pi_end;                   // FAULT, CART_CHECK
                if (cartridge == 2'd2 && !cart_rail_on && d1[8]) begin
                    $display("REFUSED: the board did not give the cartridge its 5 V: STATUS %h, FAULT %h (cartridge check failed), CART_CHECK %h (last reading about %0d mV); rail %0d mV; %0.0f ms after Play",
                             d0, d1, d2, int'(d2[7:0]) * 967 / 100, cart_rail_mv, ($realtime - t_req) / 1.0e6);
                    refused = 1;
                    break;
                end
                $fatal(1, "the board went to FAULT: STATUS %h, FAULT %h, CART_CHECK %h; rail %0d mV", d0, d1, d2, cart_rail_mv);
            end
            if ($realtime - t_req > start_ms * 1.0e6) $fatal(1, "the game has not started %0d ms after Play: STATUS %h; rail %0d mV", start_ms, d0, cart_rail_mv);
            #1_000_000;
        end
        if (!refused) begin                             // a refused cartridge ends the run here
        if (cartridge == 2'd2) $fatal(1, "a cartridge that is in back to front was given its 5 V");
        $display("%0.3f ms: the cartridge runs, %0.0f ms after Play: region %s (header: valid %0d, country %h; key ok %0d, fail %0d)",
                 $realtime / 1.0e6, ($realtime - t_req) / 1.0e6, `FPGA.region_pal ? "PAL" : "NTSC", `FPGA.top.hdr_valid, `FPGA.top.hdr_country,
                 `FPGA.top.cic_key_ok, `FPGA.top.cic_key_fail);
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
        status_end = d0;
        led_in_game = led;
        // "Power off cartridge", as the menu does it: the request is dropped. The board must put
        // the cartridge into reset before it lets go of its pins, and both before the 5 V goes.
        writes_before = ram_writes; loose_before = loose;
        t_off_req = $realtime;
        pi_addr(32'h1FFF_0014); pi_write(16'h0000); pi_write(16'h0000); pi_end;             // CONTROL: no run request
        pi_addr(32'h1FFF_0018); pi_write(16'h0001); pi_write(16'h0000); pi_end;             // COMMIT
        forever begin
            pi_addr(32'h1FFF_0004); pi_read(d0); pi_end;
            if (d0[11:8] == 4'd0 && !cart_rail_on) break;
            if ($realtime - t_off_req > 200.0e6) $fatal(1, "the cartridge is not off 200 ms after the request: STATUS %h; rail %0d mV", d0, cart_rail_mv);
            #100_000;
        end
        #2_000_000;
        $display("OFF: after the request: /RESET low at %0.1f us, socket outputs released at %0.1f us, 5 V below 4.5 V at %0.1f us; %0d RAM writes and %0d loose-pin checks on the way down; rail %0d mV; STATUS %h",
                 (t_reset_low - t_off_req) / 1.0e3, (t_out_off - t_off_req) / 1.0e3, (t_rail_off - t_off_req) / 1.0e3,
                 ram_writes - writes_before, loose - loose_before, cart_rail_mv, d0);
        if (t_reset_low < 0.0 || t_out_off < 0.0 || t_rail_off < 0.0) $fatal(1, "power-off: something did not happen");
        if (t_reset_low > t_out_off) $fatal(1, "power-off: the socket outputs were released before /RESET was low");
        if (t_out_off > t_rail_off) $fatal(1, "power-off: the 5 V went before the socket outputs were released");
        if (ram_writes != writes_before) $fatal(1, "power-off: the battery RAM was written on the way down");
        d0 = status_end;
        if (contention != 0) $fatal(1, "bus contention on D0-D7 at the socket on %0d clocks", contention);
        if (a_conflicts != 0) $fatal(1, "the FPGA and a level shifter drove the same data line on %0d clocks", a_conflicts);
        if (cic_contention != 0) $fatal(1, "a CIC data pin driven high by the key while the board held it low");
        if (loose != 0) $fatal(1, "the cartridge was out of reset while its control pins were not driven, on %0d clocks", loose);
        if (!led_in_game) $fatal(1, "the status LED was dark while the game ran");
        if (d0[11:8] !== 4'd4 || !d0[12]) $fatal(1, "STATUS %h: the cartridge is not running at the end", d0);
        $display("BOARD: status LED %0s in the game and %0s after power-off; no level shifter byte enabled without its 5 V supply; cartridge never out of reset with loose control pins; key CIC rounds %0d, mismatches %0d",
                 led_in_game ? "lit" : "dark", led ? "lit" : "dark", km_rounds, km_mismatch);
        $display("DONE: %0d pictures fetched through the cartridge port (%0d words, %0d missed, %0d fetched twice); region %s; VIDEO_MODE %h; STATUS %h; %0d ROM reads; %0d RAM writes; %0d sound samples, %0d not silent; no bus contention",
                 frames, words_fetched, missed, repeated, `FPGA.region_pal ? "PAL" : "NTSC", d2, d0, rom_reads, ram_writes, audio_words / 2, audio_nonzero);
        end
        $finish;
    end
endmodule
