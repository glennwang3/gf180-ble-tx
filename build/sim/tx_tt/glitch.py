#!/usr/bin/env python3
"""Per-reference-cycle view of a closed-loop run window: UP / DN pulse widths, VCTRL, f_RF.
    awk '$1>=T0 && $1<=T1' CASE/out.txt > win.txt; python3 glitch.py win.txt T0_us T1_us
wrdata columns: t vctrl t vdd_vco t frf t vtune t dn t upb"""
import sys
import numpy as np

d = np.loadtxt(sys.argv[1])
t0, t1 = float(sys.argv[2]), float(sys.argv[3])
t, vc, vv, f, vt, dn, upb = d[:, 0], d[:, 1], d[:, 3], d[:, 5], d[:, 7], d[:, 9], d[:, 11]
up = upb < 1.65
dnb = dn > 1.65
for a in np.arange(t0, t1, 1.0):
    m = (t >= a * 1e-6) & (t < (a + 1) * 1e-6)
    if m.sum() < 3:
        continue
    tu = np.trapezoid(up[m].astype(float), t[m])
    td = np.trapezoid(dnb[m].astype(float), t[m])
    both = np.trapezoid((up[m] & dnb[m]).astype(float), t[m])
    print(f"{a:7.1f} us: UP {tu*1e9:7.2f} ns  DN {td*1e9:7.2f} ns  both {both*1e9:6.2f} ns  "
          f"VCTRL {vc[m][-1]:.4f}  VDD_VCO {vv[m][-1]:.4f}  f_RF {f[m].mean()/1e9:.5f} GHz  "
          f"DN max {dn[m].max():.2f} UPB min {upb[m].min():.2f}")
