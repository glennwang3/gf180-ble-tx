// Activity windows for power on a post-layout ble_tx_uart netlist (power_exp).
// One VCD per run, chosen by WIN:
//   WIN_LOAD  write command + 39-byte PDU (len 37) + channel command, with gaps,
//             i.e. the controller's UART load before a beacon
//   WIN_TX    from the start byte to the last code of the packet (~380 us)
//   WIN_IDLE  400 us after the packet, uart_rx idle-high, nothing happening
// Defines: VCD_OUT. Prints the window's start/end times.
`timescale 1ns / 1ps
`default_nettype none
module pw_tb;
  localparam real BIT_NS = 1000.0;   // 1 Mbaud: CLKS_PER_BIT 8 at 8 MHz
  localparam integer GAP_BITS = 24;  // over the RTL's 20-bit frame gap

  reg clk = 1'b0, rst_n = 1'b0, uart_rx = 1'b1;
  wire code_valid, air_bit, sym_strobe;
  wire [7:0] fine_code;
  reg [7:0] pdu [0:38];
  integer i;
  real t0;

  always #62.5 clk = ~clk;

  ble_tx_uart dut (
    .clk(clk), .rst_n(rst_n), .uart_rx(uart_rx),
    .fine_code(fine_code), .code_valid(code_valid),
    .air_bit(air_bit), .sym_strobe(sym_strobe));

  task send_byte(input [7:0] b);
    integer k;
    begin
      uart_rx = 1'b0; #(BIT_NS);
      for (k = 0; k < 8; k = k + 1) begin uart_rx = b[k]; #(BIT_NS); end
      uart_rx = 1'b1; #(BIT_NS);
    end
  endtask
  task gap; #(GAP_BITS * BIT_NS); endtask
  task dump_on; begin $dumpfile(`VCD_OUT); $dumpvars(0, pw_tb.dut); t0 = $realtime; end endtask
  task dump_off; begin
    $dumpoff;
    $display("WINDOW_NS %0.3f %0.3f %0.3f", t0, $realtime, $realtime - t0);
  end endtask

  // ADV_NONCONN_IND, 37-byte payload: AdvA + flags + 26-char complete local name
  initial begin
    pdu[0] = 8'h42; pdu[1] = 8'd37;
    pdu[2] = 8'h01; pdu[3] = 8'h00; pdu[4] = 8'h18; pdu[5] = 8'hee; pdu[6] = 8'hff; pdu[7] = 8'hc0;
    pdu[8] = 8'h02; pdu[9] = 8'h01; pdu[10] = 8'h06;
    pdu[11] = 8'h1b; pdu[12] = 8'h09;
    for (i = 0; i < 26; i = i + 1) pdu[13 + i] = "A" + i;
  end

  initial begin
    repeat (3) @(negedge clk);
    rst_n = 1'b1;
    #(37.123);                                         // bit edges off the clock grid
    gap;
`ifdef WIN_LOAD
    dump_on;
`endif
    send_byte(8'h00);                                  // write PDU from address 0
    for (i = 0; i < 39; i = i + 1) send_byte(pdu[i]);
    gap;
    send_byte(8'h40 | 8'd37);                          // channel 37
    gap;
`ifdef WIN_LOAD
    dump_off; $finish;
`endif
`ifdef WIN_TX
    dump_on;
`endif
    send_byte(8'h81);                                  // start
    wait (code_valid);
    wait (!code_valid);
    @(negedge clk);
`ifdef WIN_TX
    dump_off; $finish;
`endif
    repeat (16) @(negedge clk);                        // outputs settled
`ifdef WIN_IDLE
    dump_on;
    #(400_000);
    dump_off; $finish;
`endif
    $finish;
  end

  initial begin
    #5_000_000;
    $display("pw_tb: timeout");
    $fatal(1);
  end
endmodule
`default_nettype wire
