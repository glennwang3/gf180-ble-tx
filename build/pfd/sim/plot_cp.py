import sys, glob, re
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw
fig, ax = plt.subplots(1, 2, figsize=(14, 5.2))
a = ax[0]
for c, col, ib in (("tt27", "C2", 0.466), ("ss125", "C0", 0.39), ("ff-40", "C3", 0.573)):
    pts = []
    for d in glob.glob(f"cp_{'tt' if c == 'tt27' else c}_*/wave.raw"):
        dl = float(d.split("_")[-1].split("/")[0])
        w = read_raw(d); t = w["time"]; i = w["i(vout)"]
        q = []
        for k in (1, 2, 3):
            s = 12e-9 + k * 1e-6 - 0.2e-6; m = (t >= s) & (t < s + 1e-6)
            q.append(np.trapezoid(i[m], t[m]))
        pts.append((dl, np.mean(q) * 1e15))
    pts.sort()
    x, y = np.array(pts).T
    a.plot(x, y, "o-", color=col, label=f"{c} (Icp {ib} uA)")
    a.plot(x, ib * x, ":", color=col, lw=0.8)
a.axhline(0, color="k", lw=0.5); a.axvline(0, color="k", lw=0.5)
a.set_xlabel("R lead over V [ns] (1 MHz)"); a.set_ylabel("charge into the loop filter per cycle [fC]")
a.set_title("TS_PFD + A01 charge pump, post-PEX: gain = Icp (dotted = ideal Icp*dt),\n"
            "no dead zone, +2.1 fC offset -> locks with V ~4-5 ns early", fontsize=10)
a.legend(); a.grid(alpha=0.3)
a = ax[1]
for tag, c1, col in (("lf_c1a", "C1 1.29 pF", "C3"), ("lf_c1b", "C1 10 pF", "C2")):
    w = read_raw(f"{tag}/wave.raw"); t = w["time"]; v = w["v(outf)"]
    m = (t > 2.0e-6) & (t < 4.0e-6)
    a.plot((t[m] - 2e-6) * 1e6, (v[m] - np.median(v[m])) * 1e3, color=col, label=c1)
a.set_xlabel("time [us]"); a.set_ylabel("VCTRL - mean [mV]")
a.set_title("VCTRL ripple at lock (TT, real loop filter): 2.4 mV p-p (1.29 pF) / 0.36 mV (10 pF)\n"
            "1 MHz spur estimate -29 dBc / -47 dBc (A01 PFD: +10 dBc)", fontsize=10)
a.legend(); a.grid(alpha=0.3)
fig.tight_layout(); fig.savefig("pfd_cp_postpex.png", dpi=95); print("ok")
