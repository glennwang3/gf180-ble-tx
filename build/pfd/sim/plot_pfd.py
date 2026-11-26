#!/usr/bin/env python3
"""Summary plot of the post-PEX TS_PFD tests (run in sim/)."""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw  # noqa: E402

fig, ax = plt.subplots(3, 2, figsize=(14, 12))
# (0,0) waveforms at 1 MHz, R leads by 20 ns
w = read_raw("lead20/wave.raw"); t = w["time"] * 1e9
m = (t > 1005) & (t < 1045)
a = ax[0, 0]
for k, off, c in (("v(r)", 12, "k"), ("v(v)", 8, "0.4"), ("v(up)", 4, "C3"), ("v(dn)", 0, "C0")):
    a.plot(t[m], w[k][m] + off, color=c, lw=1.2)
    a.text(t[m][0] - 1, off + 1.2, k[2:-1].upper(), ha="right", fontsize=10)
a.set_yticks([]); a.set_xlabel("time [ns]")
a.set_title("1 MHz, R leads V by 20 ns (TT, post-PEX): UP = 20.65 ns, DN = reset pulse 0.64 ns", fontsize=10)
# (0,1) zero phase: both outputs give the minimum (reset) pulse
w = read_raw("zero/wave.raw"); t = w["time"] * 1e9
m = (t > 1011.5) & (t < 1015)
a = ax[0, 1]
for k, c in (("v(r)", "k"), ("v(v)", "0.5"), ("v(up)", "C3"), ("v(dn)", "C0")):
    a.plot(t[m], w[k][m], color=c, lw=1.2, label=k[2:-1].upper(), ls="--" if k in ("v(v)", "v(dn)") else "-")
a.legend(fontsize=8); a.set_xlabel("time [ns]"); a.set_ylabel("V")
a.set_title("Zero phase error: UP and DN both give a 0.68 ns pulse (no dead zone in the PFD itself)", fontsize=10)
# (1,0) fixed-phase points at 1 MHz
pts = {"lag400": -400, "lag20": -20, "lag1": -1, "zero": 0, "lead1": 1, "lead20": 20, "lead400": 400}
a = ax[1, 0]
xs, ys = [], []
for tag, dl in pts.items():
    p = np.loadtxt(f"{tag}/pulses.txt", ndmin=2)
    p = p[p[:, 0] > 1e-6]
    up = p[p[:, 2] > 0, 1].mean(); dn = p[p[:, 2] < 0, 1].mean()
    xs.append(dl); ys.append((up - dn) * 1e9)
a.plot(xs, ys, "o-", color="C2")
a.plot([-400, 400], [-400, 400], "k--", lw=0.6, label="ideal")
a.set_xlabel("R lead over V [ns] (1 MHz)"); a.set_ylabel("UP width - DN width [ns]"); a.legend(); a.grid(alpha=0.3)
a.set_title("Fixed phase offsets at 1 MHz: linear, correct sign", fontsize=10)
# (1,1) / (2,x) phase characteristic from frequency-offset runs
for a, tag, title in ((ax[1, 1], "lf_slow", "1 MHz, V 5 % slow: per-period UP-DN vs phase"),
                      (ax[2, 0], "hf_slow", "100 MHz, V 1 % slow (FZ = 0.6 ns of 10 ns period)"),
                      (ax[2, 1], "hf_fast", "100 MHz, V 1 % fast")):
    c = np.loadtxt(f"{tag}/char.txt", ndmin=2)
    a.plot(c[:, 1], c[:, 2], ".", ms=4, color="C4")
    a.axhline(0, color="k", lw=0.6)
    a.set_xlim(-0.6, 1.1); a.set_ylim(-1.05, 1.05)
    a.set_xlabel("V lag at the R edge [periods]"); a.set_ylabel("avg(UP - DN) over the period")
    a.set_title(title + f" -> mean {c[:, 2].mean():+.2f}", fontsize=10); a.grid(alpha=0.3)
fig.suptitle("TS_PFD (Centurelli et al. Fig. 4, user's TSPC cells) after PEX, TT / 27 C, 10 fF on UP / DN", fontsize=12)
fig.tight_layout()
fig.savefig("pfd_postpex.png", dpi=95)
print("pfd_postpex.png")
