#!/usr/bin/env python3
"""Plot post-PEX PLL lock runs side by side.   python3 plot_lock.py OUT.png CASE [CASE ...]
Columns of CASE/out.txt (ngspice wrdata pairs): vctrl, vdd_vco, f_RF, f_target (or a non-frequency vector in old
runs -> fixed 2.402 GHz target), ..."""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

out, cases = sys.argv[1], sys.argv[2:]
fig, ax = plt.subplots(4, len(cases), figsize=(7.2 * len(cases), 12), sharex="col", squeeze=False)
for j, case in enumerate(cases):
    d = np.loadtxt(case + "/out.txt")
    t, vc, vv, f = d[:, 0] * 1e6, d[:, 1], d[:, 3], d[:, 5]
    ft = d[:, 7] if d[:, 7].mean() > 1e6 else np.full_like(f, 2.402e9)
    tu = np.arange(0, t[-1], 0.02)                       # 1 us moving average removes the PFD-rate ripple
    k = 50
    err = np.interp(tu, t, f - ft)
    ea = np.convolve(err, np.ones(k) / k, mode="same")
    ea[: k // 2] = np.nan                                 # moving-average edges are not valid
    ea[-k // 2:] = np.nan
    a = ax[:, j]
    a[0].plot(t, f / 1e9, lw=0.3, color="0.75", label="instantaneous")
    a[0].plot(tu, (ea + np.interp(tu, t, ft)) / 1e9, lw=1.4, color="C3", label="1 us average")
    a[0].plot(t, ft / 1e9, lw=0.8, color="k", ls="--", label="target")
    a[0].set_ylabel("f_RF [GHz]")
    a[0].yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.3f"))
    a[0].legend(loc="lower right")
    a[1].plot(tu, ea / 1e3, lw=1.2, color="C3")
    a[1].axhspan(-50, 50, color="C2", alpha=0.12, label="+-50 kHz (+-21 ppm)")
    a[1].axhline(0, color="k", lw=0.6)
    a[1].set_ylim(-400, 400)
    a[1].set_ylabel("zoom: f error [kHz]")
    a[1].legend(loc="lower right")
    a[2].plot(t, vc, lw=0.5, color="C0")
    a[2].set_ylabel("VCTRL [V]")
    a[3].plot(t, vv, lw=0.6, color="C2")
    a[3].set_ylabel("VDD_VCO [V]")
    a[3].set_xlabel("time [us]")
    for x in a:
        x.grid(alpha=0.3)
    # settling: segments with a constant target; last time the averaged error leaves +-50 kHz
    tgt = np.interp(tu, t, ft)
    edges = [0] + list(np.where(np.abs(np.diff(tgt)) > 1e5)[0] + 1) + [len(tu)]
    title = []
    for s0, s1 in zip(edges[:-1], edges[1:]):
        seg = slice(s0, s1)
        e = ea[seg]
        bad = np.where(~(np.abs(e) <= 50e3) & ~np.isnan(e))[0]
        tset = tu[seg][bad[-1]] if len(bad) else tu[s0]
        tail = slice(max(s0, s1 - 1500), s1 - k)             # last 30 us of the segment
        settled = len(bad) == 0 or bad[-1] < (s1 - s0) - 250
        msg = (f"{tgt[s0] / 1e9:.3f} GHz: within +-50 kHz from {tset:.0f} us; last 30 us mean {np.nanmean(ea[tail]) / 1e3:+.1f} kHz, "
               f"VCTRL p-p {np.ptp(vc[(t >= tu[tail][0]) & (t <= tu[tail][-1])]) * 1e3:.0f} mV, VDD_VCO p-p {np.ptp(vv[(t >= tu[tail][0]) & (t <= tu[tail][-1])]) * 1e3:.2f} mV, "
               f"VCTRL {np.mean(np.interp(tu[tail], t, vc)):.3f} V, VDD_VCO {np.mean(np.interp(tu[tail], t, vv)):.4f} V"
               if settled else f"{tgt[s0] / 1e9:.3f} GHz: NOT settled (|err| > 50 kHz at {tset:.0f} us)")
        print(case, msg)
        title.append(f"{tgt[s0] / 1e9:.3f} GHz " + (f"locked at {tset:.0f} us" if settled else "not locked"))
    a[0].set_title(f"{case}: " + ", ".join(title), fontsize=10)
import os  # noqa: E402
fig.suptitle(os.environ.get("TITLE", "PLL lock after PEX (PFD, CP, bias, regulator, loop filter + routing RC-extracted; SS / 125 C)\n"
             "Icp 2.5 uA, Rz 440 kOhm, C2 143.6 pF, C1 1.29 pF; behavioral v3 VCO + /N").replace("|", "\n"), fontsize=11)
fig.tight_layout()
fig.savefig(out, dpi=105)
