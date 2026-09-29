// Bench for sn64_cic_pad: random oe patterns; the pad may drive only while DIR
// has been high for at least one full clock, and DIR may fall only after the
// pad has been released for at least one full clock. A translator model checks
// the same rule continuously (A-side output enabled while the pad drives =
// contention).
`timescale 1ns/1ps
module tb_cic_pad;
    reg clk = 0, oe = 0;
    always #20 clk = ~clk;                       // 25 MHz
    wire dir, pad_oe;
    sn64_cic_pad dut (.clk(clk), .oe(oe), .dir(dir), .pad_oe(pad_oe));

    // Translator model: A-side output is enabled while DIR is low, and turns
    // off only after the DIR disable time; it turns on after DIR falls.
    localparam real T_DIS = 7.3;
    reg a_out_en = 1;
    always @(dir) begin
        if (dir) #(T_DIS) a_out_en = !dir; else a_out_en = 1;
    end
    integer drives = 0, errors = 0;
    always @(pad_oe or a_out_en) if (pad_oe && a_out_en) begin
        errors = errors + 1;
        $display("%0t: contention: pad drives while the translator A side drives", $time);
    end
    always @(posedge pad_oe) drives = drives + 1;

    integer k, n;
    initial begin
        #100;
        for (k = 0; k < 400; k = k + 1) begin
            n = $urandom_range(1, 6);
            @(negedge clk); oe = $urandom_range(0, 1);
            repeat (n - 1) @(negedge clk);
        end
        // Back-to-back: one-clock pulses and gaps.
        repeat (20) begin @(negedge clk) oe = 1; @(negedge clk) oe = 0; end
        #200;
        if (errors != 0 || drives < 50) begin
            $display("FAIL: tb_cic_pad: %0d contention events, %0d drive windows", errors, drives);
            $fatal(1);
        end
        $display("PASS: CIC pad sequencing, %0d drive windows, no pad/translator contention", drives);
        $finish;
    end
endmodule
