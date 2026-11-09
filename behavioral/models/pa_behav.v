// Behavioral switching RF amplifier (inverter / class D style).
//
// A switching stage driven by the VCO swings rail to rail, so its output
// power is set by its supply and load, not by the input:
//   fundamental peak  Vp = 2 * VDD_PA / pi
//   power into RL     P  = Vp^2 / (2 * RL) * EFF_MATCH
// VDD_PA = 0.49 V into 50 ohm gives 0.97 mW (-0.12 dBm), inside BLE power class 3.
// The output ramps over T_RAMP after en rises to avoid a spectral splash.

`timescale 1ns / 1fs
`default_nettype none

module pa_behav #(
  parameter real VDD_PA    = 0.49,    // amplifier supply (V)
  parameter real RL        = 50.0,    // load seen through the match (ohm)
  parameter real EFF_MATCH = 1.0,     // matching network power transfer (0..1)
  parameter real T_RAMP    = 2000.0,  // ramp time (ns)
  parameter real TSTEP     = 10.0     // ramp update step (ns)
) (
  input  wire        en,
  input  wire [63:0] f_in_bits,       // carrier from the VCO (Hz), passed through
  output wire [63:0] f_out_bits,
  output wire [63:0] pout_w_bits      // output power (W)
);

  localparam real PI = 3.141592653589793;
  real vdd_pa = VDD_PA;               // writable from the testbench
  real p_full, ramp, pout;

  initial begin
    ramp = 0.0;
    pout = 0.0;
  end

  always begin
    #(TSTEP);
    if (en) ramp = (ramp + TSTEP / T_RAMP > 1.0) ? 1.0 : ramp + TSTEP / T_RAMP;
    else    ramp = 0.0;
    p_full = (2.0 * vdd_pa / PI) ** 2 / (2.0 * RL) * EFF_MATCH;
    pout = p_full * ramp * ramp;  // amplitude ramps linearly
  end

  assign f_out_bits  = f_in_bits;
  assign pout_w_bits = $realtobits(pout);

endmodule

`default_nettype wire
