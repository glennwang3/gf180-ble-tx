#!/usr/bin/env python3
"""Output power, DC power and waveforms of RF runs from gen_deck_tx.py.
    python3 measure.py OUT.png RUN [RUN ...]
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw  # noqa: E402

T0, DT, RL, VPA, VDD = 150e-9, 1e-12, 100.0, 1.5, 3.3


def crossings(t, x, thr=0.0):
    s = np.where((x[:-1] < thr) & (x[1:] >= thr))[0]
    return t[s] + (thr - x[s]) / (x[s + 1] - x[s]) * (t[s + 1] - t[s])


def tone(t, x, f0):
    """amplitude of the sine at f0 (least squares over a whole number of periods)"""
    n = int((t[-1] - t[0]) * f0)
    m = t <= t[0] + n / f0
    tt, xx = t[m], x[m] - x[m].mean()
    A = np.column_stack([np.cos(2 * np.pi * f0 * tt), np.sin(2 * np.pi * f0 * tt)])
    c = np.linalg.lstsq(A, xx, rcond=None)[0]
    return np.hypot(*c)


def measure(run):
    w = read_raw(run + "/wave.raw")
    t = w["time"]
    tu = np.arange(T0, t[-1], DT)
    u = {k: np.interp(tu, t, w[k]) for k in w if k != "time"}
    tc = crossings(tu, u["v(o1p)"] - u["v(o1n)"])
    frf = 2 / np.mean(np.diff(tc))
    a = {h: tone(tu, u["v(out)"], h * frf) for h in (0.5, 1, 2, 3)}
    pout = a[1] ** 2 / (2 * RL)
    p_pa = -u["i(vpa)"].mean() * VPA
    p_core = -u["i(vmain)"].mean() * VDD
    r = dict(run=run, frf=frf, pout=pout, dbm=10 * np.log10(pout / 1e-3), p_pa=p_pa, p_core=p_core,
             ptot=p_pa + p_core, h2=20 * np.log10(a[2] / a[1]), h3=20 * np.log10(a[3] / a[1]),
             sub=20 * np.log10(a[0.5] / a[1]), vdd_vco=u["v(vdd_vco)"].mean(), vtune=u["v(vtune)"].mean(),
             drain_pk=u["v(drain)"].max() if "v(drain)" in u else np.nan, u=u, tu=tu)
    print(f"{run}: VTUNE {r['vtune']:.3f} V  f_RF {frf/1e9:.5f} GHz  VDD_VCO {r['vdd_vco']:.4f} V | "
          f"P_out {r['dbm']:+.2f} dBm ({pout*1e3:.3f} mW) into {RL:.0f} ohm | 2f {r['h2']:.1f} dBc, 3f {r['h3']:.1f} dBc, "
          f"f/2 {r['sub']:.1f} dBc | DC: PA (1.5 V) {p_pa*1e3:.2f} mW, core 3.3 V {p_core*1e3:.2f} mW "
          f"({-u['i(vmain)'].mean()*1e3:.2f} mA), total {r['ptot']*1e3:.2f} mW | drain eff {100*pout/p_pa:.1f} %, "
          f"overall {100*pout/r['ptot']:.2f} % | drain peak {r['drain_pk']:.2f} V")
    return r


if __name__ == "__main__":
    out, runs = sys.argv[1], sys.argv[2:]
    rs = [measure(r) for r in runs]
    r = rs[0]
    u, tu = r["u"], r["tu"]
    fig = plt.figure(figsize=(12, 10))
    gs = fig.add_gridspec(4, 2, width_ratios=[2.2, 1])
    m = (tu > tu[-1] - 3e-9)
    tt = (tu[m] - tu[m][0]) * 1e9
    first = (("v(xp)", "v(xn)", "VCO XOR output XP / XN [V]") if "v(xp)" in u else
             ("v(rf_drv1)", "v(mim_top)", "doubler: MIM_TOP (grey) / RF_DRV1 [V]"))
    rows = [first, ("v(d1)", None, "PA gate (driver out) [V]"),
            ("v(drain)", None, "PA drain [V]"), ("v(out)", None, "Load (100 ohm) [V]")]
    for i, (k1, k2, lab) in enumerate(rows):
        ax = fig.add_subplot(gs[i, 0])
        ax.plot(tt, u[k1][m], lw=1.1, color=f"C{i}")
        if k2:
            ax.plot(tt, u[k2][m], lw=1.1, color="C7")
        ax.set_ylabel(lab, fontsize=9)
        ax.grid(alpha=0.3)
    ax.set_xlabel("time [ns] (last 3 ns of the run)")
    ax = fig.add_subplot(gs[0:2, 1])
    x = u["v(out)"] - u["v(out)"].mean()
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) / len(x) * 4
    f = np.fft.rfftfreq(len(x), DT)
    pd = 10 * np.log10(np.maximum(X, 1e-12) ** 2 / (2 * RL) / 1e-3)
    ax.plot(f / 1e9, pd, lw=0.8)
    ax.set_xlim(0, 8)
    ax.set_ylim(-90, 10)
    ax.set_xlabel("f [GHz]")
    ax.set_ylabel("load power [dBm] (Hann window)")
    ax.set_title("Load spectrum", fontsize=10)
    ax.grid(alpha=0.3)
    ax = fig.add_subplot(gs[2:4, 1])
    ax.axis("off")
    txt = "\n".join([
        f"f_RF       {r['frf']/1e9:.4f} GHz",
        f"P_out      {r['dbm']:+.2f} dBm  ({r['pout']*1e3:.3f} mW)",
        f"2f / 3f    {r['h2']:.1f} / {r['h3']:.1f} dBc",
        f"f/2 spur   {r['sub']:.1f} dBc",
        "",
        "DC power",
        f"  PA supply 1.5 V   {r['p_pa']*1e3:6.2f} mW",
        f"  core 3.3 V        {r['p_core']*1e3:6.2f} mW",
        f"  total             {r['ptot']*1e3:6.2f} mW",
        f"  drain efficiency  {100*r['pout']/r['p_pa']:.1f} %",
        f"  overall           {100*r['pout']/r['ptot']:.2f} %",
        "",
        "core 3.3 V = VCO (via regulator), doubler,",
        "buffer chain, prescaler, bias",
    ])
    ax.text(0, 1, txt, va="top", family="monospace", fontsize=10)
    fig.suptitle(f"PLL_COMPACT RF output after PEX: {r['run']} (VDD_VCO {r['vdd_vco']:.3f} V, VTUNE {r['vtune']:.2f} V)\n"
                 "VCO + doubler / buffer chain + PA + prescaler + regulator + bias extracted; PA: pad 1.5 pF, bond wire 1.2 nH, "
                 "tank 1.7 nH / 0.1 pF, 100 ohm", fontsize=10)
    fig.tight_layout()
    fig.savefig(out, dpi=105)
