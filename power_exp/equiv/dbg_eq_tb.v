// dbg_tx equivalence: the ble_tx_uart of commit 764c940 (o_* modules, first dbg_tx
// version) vs the present RTL, random UART traffic with debug commands. Every
// output, dbg_tx included, is compared on every clock.
// By default the debug setting only changes while no packet is on air: turned on
// mid-packet, neither version defines which codes it samples (the first counted
// the index only while on, the present one takes it from ble_tx's sample phase).
//   MID=1: debug on/off and k also change during packets (expect mismatches).
`timescale 1ns/1ps
`default_nettype none
module dbg_eq_tb;
  parameter integer SPS = 8;
  parameter integer SEED0 = 1;
  parameter integer MID = 0;
  parameter integer SHARE = 1;
  reg clk = 0;
  always #62.5 clk = ~clk;
  integer cyc = 0, errs = 0, upk = 0, nbytes = 0;
  reg ucv_d = 0, txd = 1;
  reg rx = 1; reg urst_n = 0;
  wire ucvA, ucvB, uabA, uabB, ussA, ussB, dA, dB; wire [7:0] ufA, ufB;
  o_ble_tx_uart #(.SPS(SPS)) UA (.clk(clk), .rst_n(urst_n), .uart_rx(rx), .fine_code(ufA),
    .code_valid(ucvA), .air_bit(uabA), .sym_strobe(ussA), .dbg_tx(dA));
  ble_tx_uart #(.SPS(SPS)) UB (.clk(clk), .rst_n(urst_n), .uart_rx(rx), .fine_code(ufB),
    .code_valid(ucvB), .air_bit(uabB), .sym_strobe(ussB), .dbg_tx(dB));
  defparam UB.u_dbg.SHARE_PHASE = SHARE;

`ifdef TRACE
  reg cvd = 0;
  always @(negedge clk) begin
    if (ucvA != cvd) $display("t=%0t valid->%b ph=%0d idx=%0d sym=%0d busy=%b", $time, ucvA, UB.sym_phase, UA.u_dbg.idx, UB.u_dbg.g_split.sym, UA.busy);
    cvd = ucvA;
    if (UA.start) $display("t=%0t START busy=%b en=%b", $time, UA.busy, UA.dbg_en);
    if (!urst_n) $display("t=%0t RESET", $time);
    if (UA.u_uart.byte_valid) $display("t=%0t BYTE %h cmd=%b", $time, UA.u_uart.sh, UA.u_uart.cmd_byte);
  end
  always @(negedge clk) if (UA.u_dbg.sample | UB.u_dbg.sample | UA.u_dbg.mark)
    $display("t=%0t mark=%b sA=%b sB=%b idx=%0d sym=%0d ph=%0d k=%0d v=%b en=%b", $time, UA.u_dbg.mark,
      UA.u_dbg.sample, UB.u_dbg.sample, UA.u_dbg.idx, UB.u_dbg.g_split.sym, UB.sym_phase, UB.dbg_k, ucvA, UB.dbg_en);
`endif
  always @(negedge clk) begin
    cyc = cyc + 1;
    if (ucvA & !ucv_d) upk = upk + 1; ucv_d = ucvA;
    if (txd & !dA) nbytes = nbytes + 1; txd = dA;
    if ({ufA,ucvA,uabA,ussA,dA} !== {ufB,ucvB,uabB,ussB,dB}) begin
      errs = errs + 1;
      if (errs < 10) $display("MISMATCH t=%0t A=%h %b%b%b tx=%b B=%h %b%b%b tx=%b", $time,
        ufA,ucvA,uabA,ussA,dA, ufB,ucvB,uabB,ussB,dB);
    end
  end

  task ubit(input b, input integer clks); begin rx = b; repeat (clks) @(negedge clk); end endtask
  task ubyte(input [7:0] d); integer k; begin
    ubit(0, 8); for (k = 0; k < 8; k = k + 1) ubit(d[k], 8);
    ubit(($urandom % 40) != 0, 8);   // occasional framing error
  end endtask
  task gap; ubit(1, 8 * (18 + $urandom % 6)); endtask
  task dbgcmd; integer r; begin
    if (!MID) while (UA.busy || ucvA) @(negedge clk);   // only between packets
    r = $urandom % 6;
    ubyte({2'b11, 4'($urandom), 1'(r != 0), 1'b0});      // mostly on
    if (r < 4) ubyte(r == 0 ? $urandom : $urandom % 82);   // k (sometimes > 79)
  end endtask
  initial begin : drv_uart
    integer p, m, j, s;
    s = SEED0; j = $urandom(s);
    repeat (3) @(negedge clk); urst_n = 1; gap;
    ubyte(8'h00); for (j = 0; j < 39; j = j + 1) ubyte(j == 1 ? 37 : $urandom); gap;
    for (p = 0; p < 50; p = p + 1) begin
      if ($urandom % 3 == 0) begin dbgcmd; gap; end
      m = $urandom % 12;
      if (m) begin
        ubyte({2'b00, 6'($urandom % 39)});
        for (j = 0; j < m; j = j + 1) ubyte(j == 1 ? $urandom % 40 : $urandom);
        gap;
      end
      if ($urandom % 3 == 0) begin ubyte({2'b01, 6'($urandom)}); gap; end
      j = $urandom % 6;                                     // start (mostly), else a no-op
      ubyte(j ? {1'b1, 6'($urandom), 1'b1} : {2'b10, 5'($urandom), 1'b0});
      if ($urandom % 4 == 0) begin rx = 0; #($urandom % 300) rx = 1; end   // glitch
      if ($urandom % 15 == 0) begin #($urandom % 100000); urst_n = 0; #30 urst_n = 1; end
      if (MID && $urandom % 2) begin
        ubit(1, 8 * ($urandom % 200)); gap; dbgcmd;
        if ($urandom % 2) ubyte({1'b1, 6'($urandom), 1'b1});      // start in the same burst
      end
      ubit(1, 8 * (($urandom % 3 == 0) ? $urandom % 100 : 300 + $urandom % 200));
      gap;
    end
    #1000;
    $display("DONE cycles=%0d packets=%0d dbg_bytes=%0d errors=%0d", cyc, upk, nbytes, errs);
    $finish;
  end
endmodule
