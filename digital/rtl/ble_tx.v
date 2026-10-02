// BLE 1M PHY advertising modulator.
//
// Load the PDU (2-byte header + payload) through the byte write port, set
// channel, pulse start. The block sends preamble, access address, then the
// whitened PDU and CRC24, and outputs one Gaussian-filtered DCO fine code per
// clock. With SPS clocks per 1 us symbol the clock is SPS MHz (2 MHz -> SPS=2).
//
// Matches model/ble_adv.py bit for bit:
//   air_bit  == air_bits(pdu, channel)
//   fine_code == fine_codes(frequency_trajectory(bits, SPS), STEP_HZ)
// fine_code for the first air bit appears 2 symbols + 1 clock after start.

`default_nettype none

module ble_tx #(
  parameter integer SPS     = 2,           // samples (clocks) per symbol: 2 or 16
  parameter integer CODE_W  = 6,           // signed fine code width
  parameter [31:0]  ACCESS_ADDRESS = 32'h8E89BED6,
  parameter [23:0]  CRC_INIT       = 24'h555555
) (
  input  wire              clk,
  input  wire              rst_n,

  // PDU buffer write port: byte 0 = header0, byte 1 = length, then payload
  input  wire              wr_en,
  input  wire [5:0]        wr_addr,
  input  wire [7:0]        wr_data,

  input  wire [5:0]        channel,        // 37, 38 or 39 for advertising
  input  wire              start,          // pulse; ignored while busy

  output wire              busy,
  output reg  signed [CODE_W-1:0] fine_code,
  output reg               code_valid,     // fine_code belongs to the packet
  output reg               air_bit,        // raw air bit of the centre symbol
  output reg               sym_strobe      // first sample of each symbol
);

  localparam integer PDU_MAX = 39;         // 2 + 37 byte legacy advertising PDU
  localparam integer PW      = (SPS > 1) ? $clog2(SPS) : 1;
  localparam [7:0]   PREAMBLE = ACCESS_ADDRESS[0] ? 8'h55 : 8'hAA;

  // ---------------------------------------------------------------- buffer
  reg [7:0] pdu [0:PDU_MAX-1];
  always @(posedge clk) begin
    if (wr_en && {26'd0, wr_addr} < PDU_MAX) pdu[wr_addr] <= wr_data;
  end

  wire [5:0] payload_len = (pdu[1][5:0] > 6'd37) ? 6'd37 : pdu[1][5:0];
  wire [8:0] pdu_bits    = {payload_len + 6'd2, 3'b000};

  // ---------------------------------------------------------- bit sequencer
  localparam [2:0] S_IDLE = 3'd0, S_PRE = 3'd1, S_AA = 3'd2,
                   S_PDU  = 3'd3, S_CRC = 3'd4, S_TAIL = 3'd5;

  reg  [2:0]  state;
  reg  [8:0]  bit_idx;      // bit index within the current field
  reg  [23:0] crc;          // reflected LFSR, as in the model
  reg  [6:0]  wht;          // whitening LFSR, bit 0 is the output tap
  reg  [PW-1:0] phase;
  reg  [9:0]  win;          // 5 symbols {valid, bit}: [9:8] = n-2 ... [1:0] = n+2
  reg  [1:0]  tail_cnt;
  integer k;

  wire [7:0] cur_byte = pdu[bit_idx[8:3]];
  wire       pdu_bit  = cur_byte[bit_idx[2:0]];

  // Next air bit and its validity, for the symbol entering the window
  reg nxt_valid, nxt_bit;
  always @* begin
    nxt_valid = 1'b1;
    case (state)
      S_PRE:   nxt_bit = PREAMBLE[bit_idx[2:0]];
      S_AA:    nxt_bit = ACCESS_ADDRESS[bit_idx[4:0]];
      S_PDU:   nxt_bit = pdu_bit ^ wht[0];
      S_CRC:   nxt_bit = crc[0] ^ wht[0];
      default: begin nxt_valid = 1'b0; nxt_bit = 1'b0; end
    endcase
  end

  wire [31:0] phase32 = {{(32-PW){1'b0}}, phase};
  wire last_phase = (phase32 == SPS - 1);
  assign busy = (state != S_IDLE);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state    <= S_IDLE;
      bit_idx  <= 9'd0;
      crc      <= 24'd0;
      wht      <= 7'd0;
      phase    <= {PW{1'b0}};
      win      <= 10'd0;
      tail_cnt <= 2'd0;
    end else if (state == S_IDLE) begin
      if (start) begin
        state    <= S_PRE;
        bit_idx  <= 9'd0;
        for (k = 0; k < 24; k = k + 1) crc[k] <= CRC_INIT[23-k];
        wht      <= {1'b1, channel};
        phase    <= {PW{1'b0}};
        win      <= 10'd0;
        tail_cnt <= 2'd0;
      end
    end else begin
      phase <= last_phase ? {PW{1'b0}} : phase + 1'b1;
      if (last_phase) begin
        win <= {win[7:0], nxt_valid, nxt_bit};
        bit_idx <= bit_idx + 1'b1;
        if (state == S_PDU || state == S_CRC)
          wht <= {wht[0], wht[6:4], wht[3] ^ wht[0], wht[2:1]};
        case (state)
          S_PRE: if (bit_idx == 9'd7) begin state <= S_AA; bit_idx <= 9'd0; end
          S_AA:  if (bit_idx == 9'd31) begin state <= S_PDU; bit_idx <= 9'd0; end
          S_PDU: begin
            crc <= (pdu_bit ^ crc[0]) ? ({1'b1, crc[23:1]} ^ 24'h5A6000) : {1'b0, crc[23:1]};
            if (bit_idx == pdu_bits - 1'b1) begin state <= S_CRC; bit_idx <= 9'd0; end
          end
          S_CRC: begin
            crc <= {1'b0, crc[23:1]};
            if (bit_idx == 9'd23) state <= S_TAIL;
          end
          S_TAIL: begin
            // last bit reaches the centre after 2 shifts, then leaves the window
            tail_cnt <= tail_cnt + 1'b1;
            if (tail_cnt == 2'd2) state <= S_IDLE;
          end
          default: ;
        endcase
      end
    end
  end

  // ------------------------------------------------------- Gaussian filter
  // Phases in the first half of the symbol see n-2..n+1, the second half n-1..n+2.
  wire [7:0] lut_win = (phase32 < SPS / 2) ? win[9:2] : win[7:0];
  wire signed [CODE_W-1:0] lut_code;

  generate
    if (SPS == 2) begin : g_lut
      ble_gauss_lut_sps2 u_lut (.phase(phase), .win(lut_win), .code(lut_code));
    end else if (SPS == 16) begin : g_lut
      ble_gauss_lut_sps16 u_lut (.phase(phase), .win(lut_win), .code(lut_code));
    end else begin : g_lut_bad
      // regenerate ble_gauss_lut.v with gen_gauss_lut.py --sps <SPS>
      initial begin $display("ble_tx: no Gaussian LUT for SPS=%0d", SPS); $finish; end
    end
  endgenerate

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      fine_code  <= {CODE_W{1'b0}};
      code_valid <= 1'b0;
      air_bit    <= 1'b0;
      sym_strobe <= 1'b0;
    end else begin
      fine_code  <= busy ? lut_code : {CODE_W{1'b0}};
      code_valid <= busy & win[5];
      air_bit    <= win[4];
      sym_strobe <= busy & win[5] & (phase == {PW{1'b0}});
    end
  end

endmodule

`default_nettype wire
