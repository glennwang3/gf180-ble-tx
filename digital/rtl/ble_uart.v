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
//   1xxx_xxx1             start
//   11xx_xxe0  [k]        debug UART: e = 1 on, 0 off; an optional next byte in
//                          the same burst sets the sample offset k (0..79)
//   10xx_xxx0             no operation
//
// Debug UART (pin dbg_tx, 8N1 at the same baud rate as uart_rx, idle high): while
// it is on, each packet sends a marker byte 0x80 when the start byte is taken, then
// fine_code (signed, two's complement) at the packet's code indices k, k+80,
// k+160, ..., counted from its first valid code (index 0). One byte takes 10 bit
// times = 80 clocks, so the bytes follow back to back. Codes stay within +-125, so
// 0x80 (-128) only ever marks a packet. Sending the same packet with k = 0..79
// gives every code of the 8 MS/s waveform. k above 79 sends the marker only.
// Off after reset (k = 0); off, dbg_tx stays high and its logic is clock-gated. A
// byte already being sent when it is turned off still finishes.
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
  output wire       start,
  output reg        dbg_en,       // debug UART on
  output reg  [6:0] dbg_k         // its sample offset
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

  // debug UART settings: 11xx_xxe0 sets e; the next data byte of that burst sets k.
  reg  dbg_arg;                // the next data byte is k
  wire set_dbg = is_cmd && sh[7:6] == 2'b11 && !sh[0];
  wire set_k   = is_dat && dbg_arg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      cmd_byte  <= 1'b1;
      pdu_burst <= 1'b0;
      channel   <= 6'd37;
      dbg_arg   <= 1'b0;
    end else begin
      if (gap_done) begin
        cmd_byte  <= 1'b1;
        pdu_burst <= 1'b0;
        dbg_arg   <= 1'b0;
      end
      if (byte_valid) begin
        cmd_byte <= 1'b0;
        dbg_arg  <= set_dbg;
        if (cmd_byte) begin
          pdu_burst <= (sh[7:6] == 2'b00);
          if (sh[7:6] == 2'b01) channel <= sh[5:0];
        end
      end
    end
  end

  wire gclk_dbg;
  ble_clk_gate u_cg_dbg (.clk(clk), .en(set_dbg | set_k), .gclk(gclk_dbg));
  always @(posedge gclk_dbg or negedge rst_n)
    if (!rst_n) begin
      dbg_en <= 1'b0;
      dbg_k  <= 7'd0;
    end else begin
      if (set_dbg) dbg_en <= sh[1];
      if (set_k)   dbg_k  <= sh[6:0];
    end

endmodule

// Debug UART transmitter: a marker, then one fine_code every byte time (see the
// header above). Clocked only while on and a packet or a byte is in progress.
module ble_dbg_tx #(
  parameter integer CLKS_PER_BIT = 8,
  parameter integer CODE_W       = 8
) (
  input  wire              clk,
  input  wire              rst_n,
  input  wire              en,         // from 11xx_xxe0
  input  wire [6:0]        k,          // sample offset
  input  wire              start,      // start byte taken ...
  input  wire              busy,       // ... by an idle ble_tx: a packet begins
  input  wire [CODE_W-1:0] code,       // fine_code
  input  wire              valid,      // code_valid
  output wire              tx
);
  localparam integer CW = (CLKS_PER_BIT > 1) ? $clog2(CLKS_PER_BIT) : 1;
  localparam integer BYTE_CLKS = 10 * CLKS_PER_BIT;          // one 8N1 byte
  localparam integer DIV_LAST_I = CLKS_PER_BIT - 1;
  localparam integer IDX_LAST_I = BYTE_CLKS - 1;
  localparam [CW-1:0] DIV_LAST = DIV_LAST_I[CW-1:0];
  localparam [6:0]    IDX_LAST = IDX_LAST_I[6:0];

  wire mark = en & start & ~busy;    // ble_tx takes this start: packet begins

  reg  [6:0] idx;        // code index modulo BYTE_CLKS
  reg  [7:0] hold;       // next byte to send
  reg        pend;       // hold is waiting
  reg  [9:0] tsh;        // {stop, data LSB..MSB, start}, bit 0 on the pin
  reg  [CW-1:0] tdiv;    // clock within the bit
  reg  [3:0] tbits;      // bits left in this byte, 0 = idle

  wire sample  = en & valid & (idx == k);
  wire active  = (tbits != 4'd0);
  wire last    = active & (tdiv == DIV_LAST) & (tbits == 4'd1);
  wire can_ld  = ~active | last;
  wire load    = can_ld & pend & en;

  wire gclk;
  ble_clk_gate u_cg (.clk(clk), .en((en & (mark | busy | valid | pend)) | active),
                     .gclk(gclk));

  // Control state is reset; the data registers (hold, tsh) are always written
  // before they are used (hold by mark or sample before pend, tsh by load before
  // active), so they have no reset.
  always @(posedge gclk or negedge rst_n) begin
    if (!rst_n) begin
      idx <= 7'd0; pend <= 1'b0; tdiv <= {CW{1'b0}}; tbits <= 4'd0;
    end else begin
      // code index, from the first valid code of the packet
      if (mark)       idx <= 7'd0;
      else if (valid) idx <= (idx == IDX_LAST) ? 7'd0 : idx + 1'b1;

      // queue: the marker, then the samples
      if (mark | sample) pend <= 1'b1;
      else if (load)     pend <= 1'b0;

      // transmitter
      if (load) begin
        tdiv <= {CW{1'b0}}; tbits <= 4'd10;
      end else if (active) begin
        tdiv <= tdiv + 1'b1;
        if (tdiv == DIV_LAST) tbits <= tbits - 1'b1;
      end
    end
  end

  always @(posedge gclk) begin
    if (mark)        hold <= 8'h80;
    else if (sample) hold <= code[CODE_W-1 -: 8];
    if (load)                             tsh <= {1'b1, hold, 1'b0};
    else if (active && tdiv == DIV_LAST)  tsh <= {1'b1, tsh[9:1]};
  end

  assign tx = active ? tsh[0] : 1'b1;
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
  output wire              sym_strobe,

  output wire              dbg_tx       // debug UART: fine_code samples, 8N1, idle high
);

  wire       wr_en, start, busy, dbg_en;
  wire [5:0] wr_addr, channel;
  wire [7:0] wr_data;
  wire [6:0] dbg_k;

  ble_uart #(.CLKS_PER_BIT(CLKS_PER_BIT), .GAP_BITS(GAP_BITS)) u_uart (
    .clk(clk), .rst_n(rst_n), .uart_rx(uart_rx),
    .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data),
    .channel(channel), .start(start),
    .dbg_en(dbg_en), .dbg_k(dbg_k)
  );

  ble_tx #(.SPS(SPS), .CODE_W(CODE_W)) u_tx (
    .clk(clk), .rst_n(rst_n),
    .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data),
    .channel(channel), .start(start),
    .busy(busy),                 // not a pin: the controller times packets
    .fine_code(fine_code), .code_valid(code_valid),
    .air_bit(air_bit), .sym_strobe(sym_strobe)
  );

  ble_dbg_tx #(.CLKS_PER_BIT(CLKS_PER_BIT), .CODE_W(CODE_W)) u_dbg (
    .clk(clk), .rst_n(rst_n), .en(dbg_en), .k(dbg_k),
    .start(start), .busy(busy), .code(fine_code), .valid(code_valid),
    .tx(dbg_tx)
  );

endmodule

`default_nettype wire
