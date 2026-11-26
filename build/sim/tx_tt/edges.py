#!/usr/bin/env python3
"""UP / DN edge times and the time-step sizes around them in a closed-loop window (wrdata out.txt rows).
    python3 edges.py win.txt T0_us T1_us"""
import sys
import numpy as np

d = np.loadtxt(sys.argv[1])
t0, t1 = float(sys.argv[2]) * 1e-6, float(sys.argv[3]) * 1e-6
m = (d[:, 0] >= t0) & (d[:, 0] <= t1)
t, dn, upb, f = d[m, 0], d[m, 9], d[m, 11], d[m, 5]


def edges(x, rising):
    b = x > 1.65
    k = np.nonzero((b[1:] & ~b[:-1]) if rising else (~b[1:] & b[:-1]))[0] + 1
    return k


for name, x, r in (("DN rise", dn, True), ("DN fall", dn, False), ("UPB fall (UP on)", upb, False),
                   ("UPB rise (UP off)", upb, True)):
    k = edges(x, r)
    print(name, " ".join(f"{t[i]*1e6:.6f}" for i in k[-8:]))
# step sizes and values around the last few DN rising edges
for i in edges(dn, True)[-3:]:
    print(f"-- DN rise at {t[i]*1e6:.6f} us")
    for j in range(max(i - 4, 0), min(i + 6, len(t))):
        print(f"   t {t[j]*1e9:12.4f} ns  dt {(t[j]-t[j-1])*1e12:8.1f} ps  DN {dn[j]:6.3f}  UPB {upb[j]:6.3f}  f {f[j]/1e9:.5f}")
