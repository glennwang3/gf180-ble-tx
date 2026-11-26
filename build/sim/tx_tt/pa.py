#!/usr/bin/env python3
"""Class-C PA check from a full-node deck_tt.py run (on-chip 50u NMOS PA in RF_CHAIN_PA, drain -> pad 1.5 pF ->
bond wire 1.2 nH -> off-chip tank 1.7 nH to VPA 1.5 V / 0.1 pF -> 20 pF DC block -> 100 ohm load).
    python3 pa.py RUN [RUN ...]    prints a table row per run; analysis window = last 200 ns"""
import sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw

print(f"{'run':8s} {'f_RF GHz':>9s} {'Pout dBm':>8s} {'Pout mW':>7s} {'H2 dBc':>7s} {'H3 dBc':>7s} {'Vout pk':>7s} "
      f"{'Vd max':>6s} {'Vd min':>6s} {'I_PA mA':>7s} {'P_PA mW':>7s} {'eta_D %':>7s} {'I3V3 mA':>7s} {'I_VCO':>6s} {'eta_tot %':>9s}")
for run in sys.argv[1:]:
    w = read_raw(f"{run}/wave.raw"); t = w["time"]
    tend = t[-1]; m = t >= tend - 200e-9
    x = (w["v(o1p)"] - w["v(o1n)"])[m]; tt = t[m]
    s = np.where((x[:-1] < 0) & (x[1:] >= 0))[0]
    tc = tt[s] - x[s] / (x[s + 1] - x[s]) * (tt[s + 1] - tt[s])
    frf = 2 * (len(tc) - 1) / (tc[-1] - tc[0])
    # integer number of RF cycles inside the window, uniform resampling
    n = int((tc[-1] - tc[0]) * frf)
    t0 = tc[0]; t1 = t0 + n / frf
    tu = np.linspace(t0, t1, 40 * n, endpoint=False)
    vo = np.interp(tu, t, w["v(out)"])
    vd = np.interp(tu, t, w["v(drain)"])
    def harm(k):
        c = 2 * np.mean(vo * np.exp(-2j * np.pi * k * frf * (tu - t0)))
        return abs(c)
    a1, a2, a3 = harm(1), harm(2), harm(3)
    p1 = a1 ** 2 / 2 / 100
    ipa = -np.mean(np.interp(tu, t, w["i(vpa)"]))
    i33 = -np.mean(np.interp(tu, t, w["i(vmain)"])) - np.mean(np.interp(tu, t, w["i(vch)"]))
    ivco = -np.mean(np.interp(tu, t, w["i(vvco)"]))
    ppa = 1.5 * ipa
    ptot = ppa + 3.3 * i33 + 3.3 * ivco          # VCO supply comes from 3.3 V through the regulator
    print(f"{run:8s} {frf/1e9:9.5f} {10*np.log10(p1/1e-3):8.2f} {p1*1e3:7.2f} {20*np.log10(a2/a1):7.1f} {20*np.log10(a3/a1):7.1f} "
          f"{a1:7.3f} {vd.max():6.2f} {vd.min():6.2f} {ipa*1e3:7.2f} {ppa*1e3:7.2f} {100*p1/ppa:7.1f} {i33*1e3:7.2f} "
          f"{ivco*1e3:6.3f} {100*p1/ptot:9.1f}")
