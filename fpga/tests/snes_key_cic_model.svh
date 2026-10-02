// SPDX-License-Identifier: GPL-3.0-or-later
// The key CIC of a cartridge (D411 NTSC / D413 PAL), as a behavioural model, and the two CIC data
// lines between it and the lock in the FPGA. This is the model of tb_system.sv, word for word
// (itself the reference model of tb_snes_cic_lock.sv), in a file of its own so that another bench
// can include it. The including module provides: cic_clk, cic_srst, d0o, d0oe, d1o, d1oe, clk_25.
// Start it with `fork key_model(); join_none` after setting km_pal.
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
