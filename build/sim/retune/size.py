#!/usr/bin/env python3
"""Loop retune: PM / fc for Icp (bias mirror ratio of the 10 uA reference) and Rz, C2 kept at 143.6 pF.
Loop: CP -> Z(s) -> regulator (0.2 V/V folded into Kv, single pole fr) -> ring VCO (Kv per V of VCTRL) -> /N."""
import numpy as np
C2, N = 143.6e-12, 1201
def loop(icp, R, C1, kv, fr):
    f = np.logspace(2, 7, 40000); s = 2j * np.pi * f
    Z = (1 + s * R * C2) / (s * (C1 + C2) * (1 + s * R * C2 * C1 / (C1 + C2)))
    H = 1 / (1 + s / (2 * np.pi * fr)) if fr else 1
    L = icp * Z * kv / s / N * H
    i = np.argmin(np.abs(np.abs(L) - 1))
    return f[i] / 1e3, 180 + np.degrees(np.angle(L[i]))
if __name__ == "__main__":
    for icp0 in (2.5e-6, 3.33e-6, 5e-6):
      for R in (220e3, 300e3, 400e3, 440e3, 500e3):
          for C1 in (1.29e-12, 3e-12):
              worst, cells = 999, []
              for k_i in (0.75, 1.0, 1.37):          # bias-mirror corner spread
                  for kv in (50e6, 70e6, 100e6):      # ring Kv per V of VCTRL
                      for fr in (39e3, 84e3):         # regulator pole SS / TT
                          fc, p = loop(icp0 * k_i, R, C1, kv, fr)
                          worst = min(worst, p)
              fcn, pn = loop(icp0, R, C1, 70e6, 39e3)
              fct, pt = loop(icp0, R, C1, 70e6, 84e3)
              print(f"Icp {icp0*1e6:4.2f} uA R {R/1e3:4.0f}k C1 {C1*1e12:4.2f}p | zero {1/(2*np.pi*R*C2)/1e3:4.1f} kHz "
                    f"C1-pole {1/(2*np.pi*R*C1)/1e3:5.0f} kHz | SS: fc {fcn:5.1f} kHz PM {pn:4.1f} | TT: fc {fct:5.1f} PM {pt:4.1f} | worst PM {worst:4.1f}")
