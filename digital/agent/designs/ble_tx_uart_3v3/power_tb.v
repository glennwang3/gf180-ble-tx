// Activity for power scoring (pd/activity.py), for ble_tx_uart at 3.3 V: load the demo
// advertising PDU (power_pdu.hex, from model/ble_adv.py) through uart_rx at
// 1 Mbaud (8N1, 8 clocks a bit), set channel 37, start, and dump the block's
// switching from the start byte until 1 ms after the last code of the packet. There is no
// busy pin, so code_valid marks the packet.
//
// Read by the agent flow, not by the cocotb tests. Defines from pd/activity.py:
//   VCD_OUT   where to write the VCD
//   STIM_DIR  this folder
`timescale 1ns / 1ps
`default_nettype none
module power_tb;
  localparam real BIT_NS = 1000.0;   // CLKS_PER_BIT 8 at 8 MHz
  localparam integer GAP_BITS = 24;  // over the RTL's 20-bit frame gap

  reg clk = 1'b0, rst_n = 1'b0, uart_rx = 1'b1;
  wire code_valid, air_bit, sym_strobe;
  wire [7:0] fine_code;
  reg [7:0] pdu [0:38];
  integer i;

  always #62.5 clk = ~clk;   // 8 MHz, one 8 MS/s DAC code per clock

  ble_tx_uart dut (
    .clk(clk), .rst_n(rst_n), .uart_rx(uart_rx),
    .fine_code(fine_code), .code_valid(code_valid),
    .air_bit(air_bit), .sym_strobe(sym_strobe));

  task send_byte(input [7:0] b);
    integer k;
    begin
      uart_rx = 1'b0; #(BIT_NS);                       // start bit
      for (k = 0; k < 8; k = k + 1) begin uart_rx = b[k]; #(BIT_NS); end
      uart_rx = 1'b1; #(BIT_NS);                       // stop bit
    end
  endtask

  task gap;
    #(GAP_BITS * BIT_NS);
  endtask

  initial begin
    $readmemh({`STIM_DIR, "/power_pdu.hex"}, pdu);
    repeat (3) @(negedge clk);
    rst_n = 1'b1;
    #(37.123);                                         // bit edges off the clock grid
    gap;
    send_byte(8'h00);                                  // write PDU from address 0
    for (i = 0; i < pdu[1] + 2; i = i + 1) send_byte(pdu[i]);
    gap;
    send_byte(8'h40 | 8'd37);                          // channel 37
    gap;
    $dumpfile(`VCD_OUT);
    $dumpvars(0, power_tb.dut);
    send_byte(8'h81);                                  // start
    wait (code_valid);
    wait (!code_valid);
    @(negedge clk);
    #(1_000_000);   // + 1 ms idle (uart_rx high): a beacon's average is mostly idle
    $dumpoff;
    $finish;
  end

  initial begin
    #3_000_000;               // 3 ms: loading takes ~0.5 ms, a packet ~0.25 ms
    $display("power_tb: the packet never finished");
    $fatal(1);
  end
endmodule

`default_nettype wire
