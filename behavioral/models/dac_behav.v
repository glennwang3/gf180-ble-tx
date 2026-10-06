// Behavioral modulation DAC: 8-bit signed code in, voltage out (zero-order hold).
//
// The code is sampled on each rising clk edge, as a real DAC clocked at the
// modulator sample rate would be. vout = VMID + code * VFS / 2^BITS.
// The voltage is passed as a 64-bit $realtobits value because Icarus has no
// real-valued ports.

`timescale 1ns / 1fs
`default_nettype none

module dac_behav #(
  parameter integer BITS = 8,
  parameter real    VFS  = 1.0,     // full-scale span (V)
  parameter real    VMID = 0.5      // output at code 0 (V)
) (
  input  wire                   clk,
  input  wire signed [BITS-1:0] code,
  output wire [63:0]            vout_bits
);

  real vout = VMID;

  always @(posedge clk) vout <= VMID + $itor(code) * VFS / (2.0 ** BITS);

  assign vout_bits = $realtobits(vout);

endmodule

`default_nettype wire
