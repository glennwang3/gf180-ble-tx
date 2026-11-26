#!/usr/bin/env python3
"""Per-reference-period average of (UP - DN) from a frequency-offset pfdsim run, against the phase error at the
start of the period (R leads V by phi).  Prints a binned characteristic and writes TAG/char.txt.
    python3 phasechar.py TAG FR FV"""
import sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw  # noqa: E402

tag, fr, fv = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
w = read_raw(f"{tag}/wave.raw")
t = w["time"]


def rise(x):
    b = x > 1.65
    i = np.where(~b[:-1] & b[1:])[0]
    return t[i] + (1.65 - x[i]) / (x[i + 1] - x[i]) * (t[i + 1] - t[i])


tr, tv = rise(w["v(r)"]), rise(w["v(v)"])
tr, tv = tr[tr > 15e-9], tv[tv > 15e-9]
d = (w["v(up)"] > 1.65).astype(float) - (w["v(dn)"] > 1.65).astype(float)
rows = []
for a, b in zip(tr[1:-1], tr[2:]):
    m = (t >= a) & (t < b)
    avg = np.trapezoid(d[m], t[m]) / (b - a)
    # phase: how far the next V edge lags this R edge, as a fraction of the R period, wrapped to (-1, 1)
    nv = tv[tv >= a - 0.5 / fr]
    lag = (nv[0] - a) * fr if len(nv) else np.nan
    rows.append((a, lag, avg))
rows = np.array(rows)
np.savetxt(f"{tag}/char.txt", rows, fmt="%.6e", header="t_R  V-lag/T_R  avg(UP-DN) over the period")
print(f"{tag}: R {fr/1e6:g} MHz V {fv/1e6:g} MHz, {len(rows)} periods, mean UP-DN {rows[:, 2].mean():+.3f} "
      f"(frequency detector: {'UP (raise VCO)' if rows[:, 2].mean() > 0 else 'DN (lower VCO)'})")
bins = np.linspace(-0.5, 1.0, 16)
for lo, hi in zip(bins[:-1], bins[1:]):
    m = (rows[:, 1] >= lo) & (rows[:, 1] < hi)
    if m.any():
        print(f"  V lag {lo:+.2f}..{hi:+.2f} T: UP-DN {rows[m, 2].mean():+.3f} ({m.sum()} periods)")
