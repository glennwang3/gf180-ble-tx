// Full transmit chain: modulator RTL -> DAC -> PLL/VCO -> RF amplifier.
//
// Driven by behavioral/test_tx_chain.py. The digital modulator is the real
// RTL (digital/rtl/ble_tx.v); the analog blocks are behavioral models. Real
// values cross module boundaries as $realtobits so this runs on Icarus.

`timescale 1ns / 1fs
`default_nettype none

module tb_tx_chain #(
  parameter integer SPS      = 2,
  parameter integer DAC_BITS = 8,
  parameter real    REF_PPM  = 0.0,
  parameter real    ILEAK    = 0.0,
  parameter real    VDD_PA   = 0.49
) (
  input  wire       clk,          // modulator / DAC sample clock, SPS MHz
  input  wire       rst_n,
  input  wire       wr_en,
  input  wire [5:0] wr_addr,
  input  wire [7:0] wr_data,
  input  wire [5:0] channel,
  input  wire       start,
  input  wire       pll_en,
  input  wire       pll_hold,
  input  wire       pa_en,
  output wire       busy,
  output wire       code_valid,
  output wire       air_bit,
  output wire       sym_strobe,
  output wire signed [5:0] fine_code,
  output wire       locked,
  output wire [10:0] n_div
);

  // BLE RF channel index -> centre frequency in MHz -> N for the reference.
  // Advertising 37/38/39 sit at 2402/2426/2480; data 0..10 at 2404..2424,
  // data 11..36 at 2428..2478.
  function [11:0] chan_mhz(input [5:0] ch);
    if (ch == 6'd37)      chan_mhz = 12'd2402;
    else if (ch == 6'd38) chan_mhz = 12'd2426;
    else if (ch == 6'd39) chan_mhz = 12'd2480;
    else if (ch <= 6'd10) chan_mhz = 12'd2404 + 2 * ch;
    else                  chan_mhz = 12'd2406 + 2 * ch;
  endfunction

  localparam real F_REF = 2.0e6;
  assign n_div = chan_mhz(channel) / 2;   // 2 MHz reference: N = f / 2 MHz

  ble_tx #(.SPS(SPS)) u_mod (
    .clk(clk), .rst_n(rst_n),
    .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data),
    .channel(channel), .start(start),
    .busy(busy), .fine_code(fine_code), .code_valid(code_valid),
    .air_bit(air_bit), .sym_strobe(sym_strobe)
  );

  // 6-bit fine code (20 kHz/LSB) sign-extended onto the 8-bit DAC. With
  // VFS = 1 V the LSB is 3.906 mV, and KMOD = 20 kHz / 3.906 mV = 5.12 MHz/V.
  wire signed [DAC_BITS-1:0] dac_code = {{(DAC_BITS-6){fine_code[5]}}, fine_code};
  wire [63:0] vmod_bits, f_vco_bits, vctrl_bits, f_rf_bits, pout_bits;

  dac_behav #(.BITS(DAC_BITS), .VFS(1.0), .VMID(0.5)) u_dac (
    .clk(clk), .code(dac_code), .vout_bits(vmod_bits)
  );

  pll_behav #(.F_REF(F_REF), .REF_PPM(REF_PPM), .KMOD(20.0e3 * (2.0 ** DAC_BITS)),
              .VMOD0(0.5), .ILEAK(ILEAK)) u_pll (
    .en(pll_en), .n_div(n_div), .hold(pll_hold), .vmod_bits(vmod_bits),
    .f_vco_bits(f_vco_bits), .vctrl_bits(vctrl_bits), .locked(locked)
  );

  pa_behav #(.VDD_PA(VDD_PA)) u_pa (
    .en(pa_en), .f_in_bits(f_vco_bits), .f_out_bits(f_rf_bits), .pout_w_bits(pout_bits)
  );

  // Real-valued probes for cocotb
  real vmod, f_vco, vctrl, f_rf, pout_w;
  always @* begin
    vmod   = $bitstoreal(vmod_bits);
    f_vco  = $bitstoreal(f_vco_bits);
    vctrl  = $bitstoreal(vctrl_bits);
    f_rf   = $bitstoreal(f_rf_bits);
    pout_w = $bitstoreal(pout_bits);
  end

endmodule

`default_nettype wire
