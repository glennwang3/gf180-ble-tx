// Behavioral 2.4 GHz integer-N PLL (proposal Figure 1b), phase-domain model.
//
//   ref -> PFD + charge pump -> loop filter -> VCO -> /N -> PFD
//
// The VCO is not toggled at 2.4 GHz. Every TSTEP the model advances the
// reference and VCO phases (in cycles), finds the exact times of reference and
// divider edges inside the step, and integrates the tri-state PFD / charge
// pump current between them. That keeps edge timing exact without simulating
// a billion events per second.
//
// Loop filter: type-II, 3rd order. C2 from vctrl to ground, in parallel with
// R in series with C1. Defaults give a 100 kHz loop with 60 degrees of phase
// margin at N = 1220 (see behavioral/README.md).
//
// Modulation: the DAC voltage drives a separate VCO input with gain KMOD
// (Hz/V) around VMOD0. GFSK has energy far below the loop bandwidth, so the
// loop is opened while transmitting: assert hold after lock and the charge
// pump stops, leaving vctrl on the filter caps. ILEAK models the leakage that
// then makes the carrier drift.

`timescale 1ns / 1fs
`default_nettype none

module pll_behav #(
  parameter real F_REF  = 2.0e6,     // reference (Hz)
  parameter real REF_PPM = 0.0,      // crystal error (ppm); also writable as ref_ppm
  parameter real F0     = 2.3e9,     // VCO at vctrl = 0 (Hz)
  parameter real KVCO   = 200.0e6,   // tuning gain (Hz/V)
  parameter real KMOD   = 5.12e6,    // modulation gain (Hz/V)
  parameter real VMOD0  = 0.5,       // modulation input with no offset (V)
  parameter real ICP    = 100.0e-6,  // charge pump current (A)
  parameter real R      = 41.29e3,
  parameter real C1     = 143.8e-12,
  parameter real C2     = 11.13e-12,
  parameter real ILEAK  = 0.0,       // leakage out of vctrl (A), positive pulls down; also ileak
  parameter real VMAX   = 1.8,       // vctrl clamp (V)
  parameter real TSTEP  = 1.0,       // update step (ns)
  parameter real LOCK_HZ = 10.0e3,   // lock detect: |f - N*fref| below this ...
  parameter real LOCK_NS = 5000.0    // ... for this long
) (
  input  wire        en,             // 0: reset phases and filter
  input  wire [10:0] n_div,          // integer divide ratio
  input  wire        hold,           // 1: open the loop (charge pump off)
  input  wire [63:0] vmod_bits,      // modulation voltage ($realtobits)
  output wire [63:0] f_vco_bits,     // instantaneous VCO frequency (Hz)
  output wire [63:0] vctrl_bits,
  output reg         locked
);

  real f_ref_act;
  real ref_ppm = REF_PPM;             // writable from the testbench
  real ileak   = ILEAK;
  real ph_ref, ph_vco;                 // cycles since enable
  real vctrl, vc1;                     // loop filter node voltages
  real f_vco, vmod, dt;
  real t_ok;                           // time spent within LOCK_HZ
  integer pfd;                         // +1 up, -1 down, 0 idle

  // One step: edges at fractions a_ref, a_div of the step (or > 1 if none).
  real p_ref0, p_div0, p_vco1, a_ref, a_div, a1, a2, q, i_avg;
  integer e1, e2;

  assign f_vco_bits = $realtobits(f_vco);
  assign vctrl_bits = $realtobits(vctrl);

  initial begin
    dt = TSTEP * 1.0e-9;
    ph_ref = 0.0; ph_vco = 0.0; vctrl = 0.0; vc1 = 0.0;
    f_vco = F0; pfd = 0; locked = 1'b0; t_ok = 0.0;
  end

  // Charge from PFD state s held over a fraction a of the step.
  function real chg(input integer s, input real a);
    chg = s * ICP * a * dt;
  endfunction

  always begin
    #(TSTEP);
    if (!en) begin
      ph_ref = 0.0; ph_vco = 0.0; vctrl = 0.0; vc1 = 0.0;
      pfd = 0; locked = 1'b0; t_ok = 0.0;
      f_vco = F0;
    end else begin
      f_ref_act = F_REF * (1.0 + ref_ppm * 1.0e-6);
      vmod  = $bitstoreal(vmod_bits);
      f_vco = F0 + KVCO * vctrl + KMOD * (vmod - VMOD0);

      p_ref0 = ph_ref;
      p_div0 = ph_vco / n_div;
      ph_ref = ph_ref + f_ref_act * dt;
      ph_vco = ph_vco + f_vco * dt;

      // Fraction of the step at which each edge (integer crossing) happens.
      a_ref = 2.0; a_div = 2.0;
      if ($floor(ph_ref) > $floor(p_ref0))
        a_ref = ($floor(ph_ref) - p_ref0) / (ph_ref - p_ref0);
      if ($floor(ph_vco / n_div) > $floor(p_div0))
        a_div = ($floor(ph_vco / n_div) - p_div0) / (ph_vco / n_div - p_div0);

      // Integrate the charge pump through the edges in time order.
      q = 0.0;
      if (hold) begin
        pfd = 0;
      end else begin
        if (a_ref <= a_div) begin a1 = a_ref; e1 = 1; a2 = a_div; e2 = -1; end
        else                begin a1 = a_div; e1 = -1; a2 = a_ref; e2 = 1; end
        if (a1 <= 1.0) begin
          q = q + chg(pfd, a1);
          pfd = (pfd == -e1) ? 0 : e1;
          if (a2 <= 1.0) begin
            q = q + chg(pfd, a2 - a1);
            pfd = (pfd == -e2) ? 0 : e2;
            q = q + chg(pfd, 1.0 - a2);
          end else begin
            q = q + chg(pfd, 1.0 - a1);
          end
        end else begin
          q = q + chg(pfd, 1.0);
        end
      end

      // Loop filter (forward Euler; dt << R*C2).
      i_avg = q / dt - ileak;
      vc1   = vc1 + (vctrl - vc1) / (R * C1) * dt;
      vctrl = vctrl + (i_avg - (vctrl - vc1) / R) / C2 * dt;
      if (vctrl < 0.0)  vctrl = 0.0;
      if (vctrl > VMAX) vctrl = VMAX;

      // Lock detect on the unmodulated frequency.
      if (!hold) begin
        if ((F0 + KVCO * vctrl - n_div * f_ref_act) < LOCK_HZ &&
            (F0 + KVCO * vctrl - n_div * f_ref_act) > -LOCK_HZ)
          t_ok = t_ok + TSTEP;
        else
          t_ok = 0.0;
        locked = (t_ok >= LOCK_NS);
      end
    end
  end

endmodule

`default_nettype wire
