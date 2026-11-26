import sys, numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw
for tag in sys.argv[1:]:
    w = read_raw(f"{tag}/wave.raw"); t = w["time"]; i = w["i(vout)"]
    a = 3.012e-6 - 50e-9; b = a + 1e-6          # one period starting 50 ns before the 4th R/V edges
    m = (t >= a) & (t < b); tt = t[m] - a; ii = i[m]
    win = [(0, 45e-9), (45e-9, 49e-9), (49e-9, 70e-9), (70e-9, 200e-9), (200e-9, 1e-6)]
    out = []
    for lo, hi in win:
        k = (tt >= lo) & (tt < hi)
        out.append(np.trapezoid(ii[k], tt[k]) * 1e15)
    k = tt > 200e-9
    print(f"{tag}: Q total {sum(out):+.3f} fC | windows [-50..-5ns] {out[0]:+.3f} [-5..-1] {out[1]:+.3f} [-1..+20ns] {out[2]:+.3f} "
          f"[20..150ns] {out[3]:+.3f} [150ns..1us] {out[4]:+.3f} | quiescent I {np.median(ii[k])*1e12:+.2f} pA")
