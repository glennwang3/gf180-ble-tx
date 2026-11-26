#!/usr/bin/env python3
"""f_RF vs VTUNE at TT from the vt_* runs of deck_tt.py -> vtune_curve_tt.txt (VTUNE V, f_RF Hz)."""
import glob
import sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw  # noqa: E402

rows = []
for f in sorted(glob.glob("vt_*/wave.raw")):
    w = read_raw(f)
    t = w["time"]
    m = t >= 25e-9
    x = (w["v(o1p)"] - w["v(o1n)"])[m]
    tt = t[m]
    s = np.where((x[:-1] < 0) & (x[1:] >= 0))[0]
    tc = tt[s] - x[s] / (x[s + 1] - x[s]) * (tt[s + 1] - tt[s])
    frf = 2 * (len(tc) - 1) / (tc[-1] - tc[0])
    rows.append((float(np.mean(w["v(vtune)"][m])), frf))
rows.sort()
np.savetxt("vtune_curve_tt.txt", rows, fmt="%.4f %.0f")
for (v, fr), (v2, f2) in zip(rows, rows[1:] + [rows[-1]]):
    k = (f2 - fr) / (v2 - v) / 1e6 if v2 != v else float("nan")
    print(f"VTUNE {v:.3f}  f_RF {fr/1e9:.6f} GHz   slope to next {k:+.2f} MHz/V")
