// Port equivalence: original RTL (o_* modules) vs a power variant, random stimulus.
// Compares every output of ble_tx (incl. busy) and of ble_tx_uart on every clock.
`timescale 1ns/1ps
`default_nettype none
module eq_tb;
  parameter integer SPS = 8;
  parameter integer SEED0 = 1;
  reg clk = 0, rst_n = 0;
  always #62.5 clk = ~clk;
  integer seed, cyc = 0, errs = 0, pkts = 0, upk = 0, i, n;
  reg ucv_d = 0;

  // ---- ble_tx alone
  reg wr_en = 0, start = 0; reg [5:0] wr_addr = 0, channel = 37; reg [7:0] wr_data = 0;
  wire bA, bB, cvA, cvB, abA, abB, ssA, ssB; wire [7:0] fA, fB;
  o_ble_tx #(.SPS(SPS)) A (.clk(clk), .rst_n(rst_n), .wr_en(wr_en), .wr_addr(wr_addr),
    .wr_data(wr_data), .channel(channel), .start(start), .busy(bA), .fine_code(fA),
    .code_valid(cvA), .air_bit(abA), .sym_strobe(ssA));
  ble_tx #(.SPS(SPS)) B (.clk(clk), .rst_n(rst_n), .wr_en(wr_en), .wr_addr(wr_addr),
    .wr_data(wr_data), .channel(channel), .start(start), .busy(bB), .fine_code(fB),
    .code_valid(cvB), .air_bit(abB), .sym_strobe(ssB));

  // ---- ble_tx_uart
  reg rx = 1; reg urst_n = 0;
  wire ucvA, ucvB, uabA, uabB, ussA, ussB; wire [7:0] ufA, ufB;
  o_ble_tx_uart #(.SPS(SPS)) UA (.clk(clk), .rst_n(urst_n), .uart_rx(rx), .fine_code(ufA),
    .code_valid(ucvA), .air_bit(uabA), .sym_strobe(ussA));
  ble_tx_uart #(.SPS(SPS)) UB (.clk(clk), .rst_n(urst_n), .uart_rx(rx), .fine_code(ufB),
    .code_valid(ucvB), .air_bit(uabB), .sym_strobe(ussB));

  always @(negedge clk) begin
    cyc = cyc + 1;
    if (ucvA & !ucv_d) upk = upk + 1; ucv_d = ucvA;
    if ({bA,fA,cvA,abA,ssA} !== {bB,fB,cvB,abB,ssB}) begin
      errs = errs + 1;
      if (errs < 10) $display("TX MISMATCH t=%0t A=%b %h %b%b%b B=%b %h %b%b%b", $time,
        bA,fA,cvA,abA,ssA, bB,fB,cvB,abB,ssB);
    end
    if ({ufA,ucvA,uabA,ussA} !== {ufB,ucvB,uabB,ussB}) begin
      errs = errs + 1;
      if (errs < 10) $display("UART MISMATCH t=%0t A=%h %b%b%b B=%h %b%b%b", $time,
        ufA,ucvA,uabA,ussA, ufB,ucvB,uabB,ussB);
    end
  end

  // ble_tx driver (changes on negedge)
  initial begin : drv_tx
    integer r;
    seed = SEED0;
    repeat (3) @(negedge clk); rst_n = 1;
    repeat (60) begin
      // write a PDU (sometimes partial, sometimes long length field)
      n = $urandom(seed) % 41;
      for (i = 0; i < n; i = i + 1) begin
        @(negedge clk); wr_en = ($urandom % 8) != 0; wr_addr = ($urandom % 10 == 0) ? $urandom : i;
        wr_data = (i == 1) ? ($urandom % 45) : $urandom;
      end
      @(negedge clk); wr_en = 0; channel = $urandom;
      repeat ($urandom % 5) @(negedge clk);
      start = 1; @(negedge clk); start = 0; pkts = pkts + 1;
      // during the packet: random starts / writes / maybe reset
      repeat ($urandom % (500 * SPS)) begin
        @(negedge clk);
        r = $urandom % 400;
        start = (r == 0);
        wr_en = (r == 1); wr_addr = $urandom; wr_data = $urandom;
        if (r == 2 && ($urandom % 4 == 0)) begin rst_n = 0; #20 rst_n = 1; end
      end
      start = 0; wr_en = 0;
    end
  end

  // UART driver
  task ubit(input b, input integer clks); begin rx = b; repeat (clks) @(negedge clk); end endtask
  task ubyte(input [7:0] d); integer k, w; begin
    w = 8 + (($urandom % 3) == 0 ? (($urandom % 2) ? 0 : 0) : 0);
    ubit(0, 8); for (k = 0; k < 8; k = k + 1) ubit(d[k], 8);
    ubit(($urandom % 30) != 0, 8);   // occasional framing error
  end endtask
  task gap; ubit(1, 8 * (18 + $urandom % 6)); endtask
  initial begin : drv_uart
    integer p, m, j;
    repeat (3) @(negedge clk); urst_n = 1; gap;
    for (p = 0; p < 40; p = p + 1) begin
      m = $urandom % 40;
      ubyte({2'b00, 6'($urandom % 3 == 0 ? $urandom % 40 : 0)});
      for (j = 0; j < m; j = j + 1) ubyte(j == 1 ? $urandom % 40 : $urandom);
      gap;
      if ($urandom % 2) begin ubyte({2'b01, 6'($urandom)}); gap; end
      ubyte({1'b1, 6'($urandom), 1'($urandom % 4 != 0)}); // start (mostly)
      if ($urandom % 3 == 0) begin rx = 0; #($urandom % 300) rx = 1; end   // glitch
      if ($urandom % 10 == 0) begin #($urandom % 100000); urst_n = 0; #30 urst_n = 1; end
      ubit(1, 8 * ($urandom % 450));
      gap;
    end
    #1000;
    $display("DONE cycles=%0d tx_starts=%0d uart_packets_on_air=%0d errors=%0d", cyc, pkts, upk, errs);
    $finish;
  end
endmodule
