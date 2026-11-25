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
//
// Area notes. The code index modulo one byte time (80 at SPS = 8) is not counted
// here: its low bits are ble_tx's sample phase, so only the symbol index modulo
// 10 is (k = 8 x symbol + sample, and k > 79 has symbol >= 10, which never
// matches). Other SPS / CLKS_PER_BIT combinations count the index directly. The
// marker 0x80 and the samples share one holding byte; the shift register shifts
// in zeros and is idle when empty, so no bit counter is needed. Each register
// group has its own clock gate instead of hold muxes.
module ble_dbg_tx #(
  parameter integer SPS          = 8,
  parameter integer CLKS_PER_BIT = 8,
  parameter integer CODE_W       = 8,
  parameter integer SHARE_PHASE  = 1,     // 0: count the index here (for tests)
  parameter integer PW           = (SPS > 1) ? $clog2(SPS) : 1
) (
  input  wire              clk,
  input  wire              rst_n,
  input  wire              en,         // from 11xx_xxe0
  input  wire [6:0]        k,          // sample offset
  input  wire              start,      // start byte taken ...
  input  wire              busy,       // ... by an idle ble_tx: a packet begins
  input  wire [CODE_W-1:0] code,       // fine_code
  input  wire              valid,      // code_valid
  input  wire [PW-1:0]     phase,      // ble_tx sym_phase: code is sample phase - 1
  output wire              tx
);
  localparam integer CW = (CLKS_PER_BIT > 1) ? $clog2(CLKS_PER_BIT) : 1;
  localparam integer BYTE_CLKS = 10 * CLKS_PER_BIT;          // one 8N1 byte
  localparam integer DIV_LAST_I = CLKS_PER_BIT - 1;
  localparam [CW-1:0] DIV_LAST = DIV_LAST_I[CW-1:0];
  localparam integer NSYM = BYTE_CLKS / SPS;                 // symbols per byte time
  // the phase split works for a power-of-two SPS that divides the byte time
  localparam SPLIT = (SHARE_PHASE != 0) && (SPS > 1) && ((1 << PW) == SPS) && (NSYM * SPS == BYTE_CLKS)
                     && (NSYM <= (128 >> PW));

  wire mark = en & start & ~busy;    // ble_tx takes this start: packet begins

  // ------------------------------------------- code index == k
  wire hit;                          // the code on fine_code now has index k (mod BYTE_CLKS)
  generate
    if (SPLIT) begin : g_split
      localparam integer SW = (NSYM > 1) ? $clog2(NSYM) : 1;
      localparam [SW-1:0] SYM_LAST = NSYM - 1;
      localparam [PW-1:0] PH_ONE = 1;
      reg  [SW-1:0] sym;             // symbol index modulo NSYM, from the first valid code
      // the code now is the last of its symbol when phase has wrapped to 0
      wire gclk_sym;
      ble_clk_gate u_cg_sym (.clk(clk), .en(mark | (en & valid & (phase == {PW{1'b0}}))),
                             .gclk(gclk_sym));
      always @(posedge gclk_sym or negedge rst_n)
        if (!rst_n)                sym <= {SW{1'b0}};
        else if (mark)             sym <= {SW{1'b0}};
        else if (sym == SYM_LAST)  sym <= {SW{1'b0}};
        else                       sym <= sym + 1'b1;
      wire [7-PW:0] ks = {1'b0, k[6:PW]};
      assign hit = (ks == {{(8-PW-SW){1'b0}}, sym}) & (phase == k[PW-1:0] + PH_ONE);
    end else begin : g_idx
      localparam integer IDX_LAST_I = BYTE_CLKS - 1;
      localparam [6:0] IDX_LAST = IDX_LAST_I[6:0];
      reg [6:0] idx;                 // code index modulo BYTE_CLKS
      wire gclk_idx;
      ble_clk_gate u_cg_idx (.clk(clk), .en(mark | (en & valid)), .gclk(gclk_idx));
      always @(posedge gclk_idx or negedge rst_n)
        if (!rst_n)                idx <= 7'd0;
        else if (mark)             idx <= 7'd0;
        else                       idx <= (idx == IDX_LAST) ? 7'd0 : idx + 1'b1;
      assign hit = (idx == k);
    end
  endgenerate

  wire sample = en & valid & hit;

  // MEASUREMENT ONLY: marker 0x80 after the samples. A sample goes straight into
  // the shift register (the previous byte ends in that very cycle); the marker is
  // queued when the packet's codes end (valid falls) and sent from a constant.
  reg  valid_q;
  reg  [9:0]    tsh;
  reg  [CW-1:0] tdiv;
  reg           pend;      // marker waiting
  wire active  = |tsh;
  wire bit_end = (tdiv == DIV_LAST);
  wire last    = (tsh == 10'd1) & bit_end;
  wire can_ld  = ~active | last;
  wire endp    = en & valid_q & ~valid;
  wire ld_mark = can_ld & pend & en & ~sample;
  wire load    = (can_ld & sample) | ld_mark;

  wire gclk_sh;
  ble_clk_gate u_cg_sh (.clk(clk), .en(load | (active & bit_end)), .gclk(gclk_sh));
  always @(posedge gclk_sh or negedge rst_n)
    if (!rst_n)     tsh <= 10'd0;
    else if (load)  tsh <= {1'b1, ld_mark ? 8'h80 : code[CODE_W-1 -: 8], 1'b0};
    else            tsh <= {1'b0, tsh[9:1]};

  wire gclk_c;
  ble_clk_gate u_cg_c (.clk(clk), .en(en & (valid | valid_q) | pend | load | active), .gclk(gclk_c));
  always @(posedge gclk_c)
    tdiv <= (load | bit_end) ? {CW{1'b0}} : tdiv + 1'b1;
  always @(posedge gclk_c or negedge rst_n)
    if (!rst_n) begin pend <= 1'b0; valid_q <= 1'b0; end
    else begin
      valid_q <= valid;
      if (endp)         pend <= 1'b1;
      else if (ld_mark) pend <= 1'b0;
    end

  assign tx = tsh[0] | ~active;
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
  wire [((SPS > 1) ? $clog2(SPS) : 1)-1:0] sym_phase;

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
    .air_bit(air_bit), .sym_strobe(sym_strobe), .sym_phase(sym_phase)
  );

  ble_dbg_tx #(.SPS(SPS), .CLKS_PER_BIT(CLKS_PER_BIT), .CODE_W(CODE_W)) u_dbg (
    .clk(clk), .rst_n(rst_n), .en(dbg_en), .k(dbg_k),
    .start(start), .busy(busy), .code(fine_code), .valid(code_valid),
    .phase(sym_phase), .tx(dbg_tx)
  );

endmodule

`default_nettype wire
