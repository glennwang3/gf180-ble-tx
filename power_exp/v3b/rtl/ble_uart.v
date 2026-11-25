// UART front end for ble_tx: one input pin, no clock.
//
// uart_rx carries standard 8N1 serial: idle high, a low start bit, 8 data bits
// LSB first, a high stop bit. Each bit lasts CLKS_PER_BIT clocks; the default
// of 8 gives 1 Mbaud from the 8 MHz (SPS=8) clock. The pin passes through a
// two-flop synchronizer. After the start bit's falling edge the receiver waits
// half a bit, checks the line is still low (otherwise it was a glitch), then
// samples the middle of each data bit and checks the stop bit is high. A byte
// with a low stop bit is dropped. Each start bit resynchronizes, so the sender's
// baud rate may be off by about 3%.
//
// UART has no chip select, so a quiet line marks frames: once uart_rx has been
// idle for GAP_BITS bit times (20 = 2 byte times by default; counted in whole
// bit times, so 19 to 20 of them), the next byte is
// a command. Send each command as one burst, then pause. Commands:
//
//   00aa_aaaa  d0 d1 ...  write PDU bytes from address a (0 = header0,
//                          1 = length, 2.. = payload), address auto-increments
//   01cc_cccc             channel = c (latched by ble_tx at start)
//   1xxx_xxxs             s = 1 pulses start
//
// There is no read path and no busy pin: uart_rx is the only connection to the
// controller. A packet's air time is fixed by its length, (10 + len) x 8 us for
// a PDU with len payload bytes (376 us at the 37-byte maximum), and the first
// code comes 3 symbols (3 us) after the start byte is taken, half a UART bit
// before its stop bit ends. So once the start byte has been sent, wait
// (10 + len) x 8 + 10 us, or 400 us for any packet, before writing the next PDU
// or starting again. A start that arrives while a packet is on air is ignored,
// and a PDU written then can corrupt the packet on air.

`default_nettype none

module ble_uart #(
  parameter integer CLKS_PER_BIT = 8,
  parameter integer GAP_BITS     = 20
) (
  input  wire       clk,
  input  wire       rst_n,
  input  wire       uart_rx,

  // to ble_tx
  output wire       wr_en,
  output wire [5:0] wr_addr,
  output wire [7:0] wr_data,
  output reg  [5:0] channel,
  output wire       start
);

  // Area notes: wr_en, wr_addr, wr_data and start are not registered again here.
  // The received byte stays in sh until the next start bit (at least one bit
  // time), so ble_tx takes it straight from sh in the byte_valid cycle. The frame
  // gap counts bit times, using cnt as the prescaler while the line is idle.
  // sh, nbit and addr are always written before they are read, so they have no reset.

  localparam integer CW = $clog2(CLKS_PER_BIT);
  localparam integer GW = $clog2(GAP_BITS + 1);
  localparam integer CNT_LAST_I = CLKS_PER_BIT - 1;
  localparam integer CNT_HALF_I = CLKS_PER_BIT / 2 - 1;
  localparam [CW-1:0] CNT_LAST = CNT_LAST_I[CW-1:0];     // a full bit
  localparam [CW-1:0] CNT_HALF = CNT_HALF_I[CW-1:0];     // to the middle of the start bit
  localparam [GW-1:0] GAP_END  = GAP_BITS[GW-1:0];
  localparam [CW-1:0] CNT_ONE  = 1;

  // ------------------------------------------------------- synchronizer
  reg [1:0] rx_s;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) rx_s <= 2'b11;
    else        rx_s <= {rx_s[0], uart_rx};
  wire rx = rx_s[1];

  // ------------------------------------------------------- byte receiver
  localparam [1:0] R_IDLE = 2'd0, R_START = 2'd1, R_DATA = 2'd2, R_STOP = 2'd3;

  reg [1:0]    rstate;
  reg [CW-1:0] cnt;            // clocks left in this bit; free-runs while idle
  reg          byte_valid;     // one-cycle pulse, byte in sh
  reg [2:0]    nbit;
  reg [7:0]    sh;

  wire cnt_zero = (cnt == {CW{1'b0}});

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rstate     <= R_IDLE;
      cnt        <= {CW{1'b0}};
      byte_valid <= 1'b0;
    end else begin
      byte_valid <= 1'b0;
      case (rstate)
        R_IDLE:
          if (!rx) begin
            cnt    <= CNT_HALF;
            rstate <= R_START;
          end else
            cnt <= cnt_zero ? CNT_LAST : cnt - CNT_ONE;   // bit-time ticks for the gap
        R_START:
          if (cnt_zero) begin
            cnt    <= CNT_LAST;
            rstate <= rx ? R_IDLE : R_DATA;   // high again: a glitch, not a start bit
          end else
            cnt <= cnt - CNT_ONE;
        R_DATA:
          if (cnt_zero) begin
            cnt <= CNT_LAST;
            if (nbit == 3'd7) rstate <= R_STOP;
          end else
            cnt <= cnt - CNT_ONE;
        R_STOP:
          if (cnt_zero) begin
            byte_valid <= rx;                 // low stop bit: framing error, drop
            rstate     <= R_IDLE;
          end else
            cnt <= cnt - CNT_ONE;
      endcase
    end
  end

  // Data path, no reset: nbit is cleared by every start bit before it is used,
  // and sh is only read in the byte_valid cycle after 8 data bits.
  // Clock-gated (power): clocked only in the cycles that write them.
  wire gclk_sh;
  ble_clk_gate u_cg_sh (.clk(clk), .en((rstate == R_START) | (rstate == R_DATA & cnt_zero)),
                        .gclk(gclk_sh));
  always @(posedge gclk_sh) begin
    if (rstate == R_START)
      nbit <= 3'd0;
    else begin                                // R_DATA && cnt_zero
      sh   <= {rx, sh[7:1]};                  // LSB first
      nbit <= nbit + 1'b1;
    end
  end

  // ------------------------------------------------------- frame gap
  // Counts idle bit times up to GAP_BITS; any activity clears it.
  reg [GW-1:0] gap;
  wire         gap_done = (gap == GAP_END);
  always @(posedge clk or negedge rst_n)
    if (!rst_n)                        gap <= GAP_END;    // first byte is a command
    else if (!rx || rstate != R_IDLE)  gap <= {GW{1'b0}};
    else if (cnt_zero && !gap_done)    gap <= gap + 1'b1;

  // ------------------------------------------------------- command decode
  reg       cmd_byte;          // next byte is a command
  reg       pdu_burst;         // data bytes go to the PDU buffer
  reg [5:0] addr;              // set by every write command before use

  wire is_cmd = byte_valid &&  cmd_byte;
  wire is_dat = byte_valid && !cmd_byte;

  assign wr_en   = is_dat && pdu_burst;
  assign wr_addr = addr;
  assign wr_data = sh;
  assign start   = is_cmd && sh[7] && sh[0];

  wire set_addr = is_cmd && sh[7:6] == 2'b00;
  wire gclk_addr;
  ble_clk_gate u_cg_addr (.clk(clk), .en(set_addr | wr_en), .gclk(gclk_addr));
  always @(posedge gclk_addr)
    if (set_addr) addr <= sh[5:0];
    else          addr <= addr + 1'b1;      // wr_en

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      cmd_byte  <= 1'b1;
      pdu_burst <= 1'b0;
      channel   <= 6'd37;
    end else begin
      if (gap_done) begin
        cmd_byte  <= 1'b1;
        pdu_burst <= 1'b0;
      end
      if (byte_valid) begin
        cmd_byte <= 1'b0;
        if (cmd_byte) begin
          pdu_burst <= (sh[7:6] == 2'b00);
          if (sh[7:6] == 2'b01) channel <= sh[5:0];
        end
      end
    end
  end

endmodule

// ble_tx with the UART front end: the chip-level digital block.
module ble_tx_uart #(
  parameter integer SPS          = 8,
  parameter integer CODE_W       = 8,
  parameter integer CLKS_PER_BIT = 8,
  parameter integer GAP_BITS     = 20
) (
  input  wire              clk,
  input  wire              rst_n,
  input  wire              uart_rx,

  output wire signed [CODE_W-1:0] fine_code,
  output wire              code_valid,
  output wire              air_bit,
  output wire              sym_strobe
);

  wire       wr_en, start;
  wire [5:0] wr_addr, channel;
  wire [7:0] wr_data;

  ble_uart #(.CLKS_PER_BIT(CLKS_PER_BIT), .GAP_BITS(GAP_BITS)) u_uart (
    .clk(clk), .rst_n(rst_n), .uart_rx(uart_rx),
    .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data),
    .channel(channel), .start(start)
  );

  ble_tx #(.SPS(SPS), .CODE_W(CODE_W)) u_tx (
    .clk(clk), .rst_n(rst_n),
    .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data),
    .channel(channel), .start(start),
    /* verilator lint_off PINCONNECTEMPTY */
    .busy(),                     // not a pin: the controller times packets
    /* verilator lint_on PINCONNECTEMPTY */
    .fine_code(fine_code), .code_valid(code_valid),
    .air_bit(air_bit), .sym_strobe(sym_strobe)
  );

endmodule

`default_nettype wire
