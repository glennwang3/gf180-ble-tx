#!/usr/bin/env python3
"""TT version of sim/tx/plot_tx.py for the E03 low-cap VCO: stitch the transistor-level data windows (data_c*),
demodulate, add the closed-loop run, plot.
    python3 plot_tx_tt.py OUT.png LOOP_CASE|- T_DATA_us
Windows: (data_t_start_us, data_t_end_us) for data_c0.. as launched; sim time SET <-> data window start.
VDD_VCO is ideal in the windows (deck_tt.py), so no supply-drift correction is applied.
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw  # noqa: E402

WIN = [(0.5, 3.7), (3.7, 6.9), (6.9, 10.0)]
import os
DATA = os.environ.get("DATA", "data_c")                 # window dir prefix (dataff_c for FF)
CORNER_TXT = os.environ.get("CORNER_TXT", "TT / 27 C")
VDDVCO_TXT = os.environ.get("VDDVCO_TXT", "2.3295")
WIN = [w_ for i_, w_ in enumerate(WIN) if os.path.exists(f"{DATA}{i_}/wave.raw")]   # windows finished so far
SET = 150e-9
BITS = "01010101"
LEAD = 1.0                                     # us of idle before the first bit
F_CH = 2.402e9
out, loop_case, tdata = sys.argv[1], sys.argv[2], float(sys.argv[3])
codes = np.loadtxt("stim/full_codes.txt")


def crossings(t, x):
    s = np.where((x[:-1] < 0) & (x[1:] >= 0))[0]
    return t[s] - x[s] / (x[s + 1] - x[s]) * (t[s + 1] - t[s])


V, TW, W, GT, GF, PO = [], [], [], [], [], []
for i, (a, b) in enumerate(WIN):
    w = read_raw(f"{DATA}{i}/wave.raw")
    t = w["time"]
    m = t >= SET - 100e-9
    tc = crossings(t[m], (w["v(o1p)"] - w["v(o1n)"])[m])
    ph_c = 2.0 * np.arange(len(tc))                 # RF cycles (RF = 2 x ring)
    tg = np.arange(SET + 0.0625e-6, SET + (b - a) * 1e-6 - 0.0625e-6, 5e-9)
    fg = (np.interp(tg + 62.5e-9, tc, ph_c) - np.interp(tg - 62.5e-9, tc, ph_c)) / 125e-9
    GT.append((tg - SET) * 1e6 + a); GF.append(fg)
    mv = (t >= SET) & (t <= SET + (b - a) * 1e-6)
    V.append(np.column_stack([(t[mv] - SET) * 1e6 + a, w["v(vtune)"][mv]]))
    TW.append((t - SET) * 1e6 + a)
    W.append(w)
    PO.append(np.trapezoid(w["v(out)"][mv] ** 2, t[mv]) / (t[mv][-1] - t[mv][0]) / 100.0)
V = np.vstack(V)
tu, fs = np.concatenate(GT), np.concatenate(GF)
fc = np.mean(fs[(tu > LEAD) & (tu < LEAD + 2 * (len(BITS[:int(tu[-1] - LEAD)]) // 2))])    # carrier = mean over the 0101.. bits
df = fs - fc
tcode, fid = codes[:, 0], codes[:, 2]
cent = LEAD + np.arange(len(BITS)) + 0.5
cent = cent[cent < tu[-1]]
dev_c = np.interp(cent, tu, df)
bits_rx = "".join("1" if x > 0 else "0" for x in dev_c)
BITS_TX = BITS[:len(cent)]
ph = np.cumsum(df) * 0.005e-6 * 360.0
ph -= np.interp(LEAD, tu, ph)
pout = 10 * np.log10(np.mean(PO) / 1e-3)
print(f"carrier {fc/1e9:.6f} GHz ({(fc - F_CH)/1e6:+.2f} MHz from ch 0; the loop removes this offset)")
print("deviation at symbol centres [kHz]:", " ".join(f"{x/1e3:+.0f}" for x in dev_c))
print(f"sent {BITS} -> demodulated {bits_rx}   {'OK' if bits_rx == BITS_TX else 'ERROR'}")
pk1 = np.max(df[(tu > LEAD) & (tu < LEAD + 8)]); pk0 = np.min(df[(tu > LEAD) & (tu < LEAD + 8)])
print(f"peak deviation +{pk1/1e3:.0f} / {pk0/1e3:.0f} kHz (ideal for 0101: +-218 kHz); P_out {pout:+.2f} dBm")

nrow = 7 if loop_case != "-" else 5
fig, ax = plt.subplots(nrow, 1, figsize=(12, 2.3 * nrow + 1.5), sharex=False)
a = ax[0]
a.step(tcode, codes[:, 1], where="post", color="C0", lw=1.2)
for j, bch in enumerate(BITS):
    a.text(LEAD + j + 0.5, 140, bch, ha="center", fontsize=12, fontweight="bold")
a.set_ylim(-150, 175)
a.set_ylabel("fine_code\n(2 kHz/LSB)")
a.set_title("Bits 01010101 (the BLE preamble) -> Gaussian filter (BT 0.5, 8 samples/bit) -> 8-bit code", fontsize=10)
a = ax[1]
a.plot(V[:, 0], V[:, 1] * 1e3, color="0.8", lw=0.5, label="VTUNE node (RF kickback from the varactors)")
vg = np.arange(V[0, 0], V[-1, 0], 0.005)
vi = np.interp(vg, V[:, 0], V[:, 1])
a.plot(vg[12:-12], np.convolve(vi, np.ones(25) / 25, mode="same")[12:-12] * 1e3, color="C1", lw=1.2, label="125 ns average")
a.legend(loc="upper right", fontsize=8)
a.set_ylabel("VTUNE [mV]\n(DAC, inverted)")
a = ax[2]
a.plot(tu, df / 1e3, color="C3", lw=1.4, label="cycle count over 125 ns")
a.step(tcode, fid / 1e3, where="post", color="k", lw=0.8, ls="--", label="requested by the code")
a.plot(cent, dev_c / 1e3, "o", color="C2", ms=6, label=f"symbol centres -> {bits_rx}")
a.set_ylim(-450, 450)
a.axhline(0, color="k", lw=0.5)
a.set_ylabel(f"f_RF - {fc/1e9:.6f} GHz\n[kHz]")
a.legend(loc="upper right", fontsize=8, ncol=3)
a.set_title(f"Transistor-level post-PEX low-cap VCO + doubler + buffer chain + PA ({CORNER_TXT}, VDD_VCO {VDDVCO_TXT} V): "
            "instantaneous RF frequency", fontsize=10)
a = ax[3]
a.plot(tu, ph, color="C4", lw=1.2)
a.set_ylabel("RF phase\ndeviation [deg]")
a.axhline(0, color="k", lw=0.5)
a.set_ylim(-250, 250)
for a in ax[:4]:
    a.set_xlim(0.5, 10)
    a.grid(alpha=0.3)
ax[3].set_xlabel("time [us]")
a = ax[4]
for j, (tc_, lab, col) in enumerate(((LEAD + 0.5, "bit 0 (f low)", "C0"), (LEAD + 1.5, "bit 1 (f high)", "C3"))):
    i = 0 if tc_ < WIN[0][1] else 1
    w, tt = W[i], TW[i]
    m = (tt >= tc_) & (tt <= tc_ + 0.002)
    a.plot((tt[m] - tc_) * 1e3, w["v(out)"][m], color=col, lw=1.2, label=f"PA output (100 ohm load), {lab}")
a.set_xlabel("ns from the symbol centre")
a.set_ylabel("v(out) [V]")
a.legend(loc="upper right", fontsize=8)
a.grid(alpha=0.3)
a.set_title(f"Antenna-side RF at a 0 and a 1 symbol (P_out {pout:+.1f} dBm): +-218 kHz on 2.402 GHz is a 0.009 % period "
            "change - not visible by eye, hence the frequency plot above", fontsize=9)
if loop_case != "-":
    d = np.loadtxt(loop_case + "/out.txt")
    tg = np.arange(d[0, 0], d[-1, 0], 10e-9)
    fl = np.interp(tg, d[:, 0], d[:, 5])
    vl = np.interp(tg, d[:, 0], d[:, 1])
    tl = tg * 1e6 - tdata                              # us from the start of the DAC stream

    def avg(x, n):
        return np.convolve(x, np.ones(n) / n, mode="same")
    f1 = avg(fl, 100)                                  # 1 us = one reference period: removes the 1 MHz CP ripple
    a = ax[5]
    a.plot(tg * 1e6, (f1 - F_CH) / 1e6, color="C3", lw=1)
    a.set_ylim(-20, 20)
    a.set_ylabel("f_RF - 2.402 GHz\n[MHz], 1 us avg", color="C3")
    a.axvspan(tdata + LEAD, tdata + LEAD + len(BITS), color="C2", alpha=0.25, label="01010101 packet")
    a.legend(loc="upper right", fontsize=8)
    b2 = a.twinx()
    b2.plot(tg * 1e6, avg(vl, 100), color="C0", lw=0.8)
    b2.set_ylabel("VCTRL [V]", color="C0")
    a.set_xlabel("time [us]")
    a.grid(alpha=0.3)
    a.set_title("Closed loop, full run: post-PEX PFD / CP / bias / regulator / loop filter, behavioral VCO with the measured "
                f"{CORNER_TXT} VTUNE curve - acquisition, then the packet", fontsize=9)
    a = ax[6]
    z = (tl > -3) & (tl < tl[-1] - 0.5)
    f125 = avg(fl, 13)
    idl = z & ((tl < LEAD - 0.3) | (tl > LEAD + len(BITS) + 1.2))
    p = np.polyfit(tl[idl], f125[idl], 1)
    dz = f125 - np.polyval(p, tl)
    # 1 us periodic reference ripple (CP correction once per reference cycle, passed by the regulator at TT):
    # estimate by folding 30 us of idle before the packet
    pre = (tl > -30) & (tl < LEAD - 0.3)
    q = np.polyfit(tl[pre], f125[pre], 2)
    ph_ = np.mod(tg * 1e6, 1.0)
    bins = np.linspace(0, 1, 101)
    idx = np.clip(np.digitize(ph_, bins) - 1, 0, 99)
    tmpl = np.array([np.mean((f125 - np.polyval(q, tl))[pre & (idx == j)]) for j in range(100)])
    rip = tmpl[idx]
    print(f"reference ripple on f_RF (1 us period, 125 ns avg): {np.ptp(tmpl)/1e3:.0f} kHz p-p")
    a.plot(tl[z], dz[z] / 1e3, color="0.7", lw=0.8, label=f"closed loop, 125 ns avg (incl. {np.ptp(tmpl)/1e3:.0f} kHz p-p ref. ripple)")
    dz = dz - rip
    a.plot(tl[z], dz[z] / 1e3, color="C3", lw=1, label="same, 1 us ripple removed")
    a.step(tcode, fid / 1e3, where="post", color="k", lw=0.8, ls="--", label="requested by the code")
    dc = np.interp(cent, tl, dz)
    rx = "".join("1" if x > 0 else "0" for x in dc)
    a.plot(cent, dc / 1e3, "o", color="C2", ms=6, label=f"symbol centres -> {rx}")
    for j, bch in enumerate(BITS):
        a.text(LEAD + j + 0.5, 330, bch, ha="center", fontsize=11, fontweight="bold")
    a.set_xlim(-3, 13)
    lim = max(450, 1.1 * np.max(np.abs((f125 - np.polyval(p, tl))[z])) / 1e3)
    a.set_ylim(-lim, lim)
    a.axhline(0, color="k", lw=0.5)
    a.grid(alpha=0.3)
    a.legend(loc="lower right", fontsize=7, ncol=2)
    a.set_ylabel("f_RF - carrier [kHz]")
    a.set_xlabel("time from the start of the DAC stream [us]")
    a.set_title(f"Closed loop, packet zoom: carrier {np.polyval(p, LEAD + 4)/1e9:.6f} GHz "
                f"({(np.polyval(p, LEAD + 4) - F_CH)/1e3:+.1f} kHz), drift {p[0]/1e3:+.1f} kHz/us", fontsize=9)
    print(f"closed loop: carrier {np.polyval(p, LEAD + 4)/1e9:.6f} GHz, drift {p[0]/1e3:+.2f} kHz/us, "
          f"symbol centres", " ".join(f"{x/1e3:+.0f}" for x in dc), "->", rx)
fig.suptitle(os.environ.get("PRE", "") + "E03 (low-cap Schottky-doubler VCO) transmitting 01010101 on channel 0 (2.402 GHz), " + CORNER_TXT + ", after PEX",
             fontsize=12)
fig.tight_layout()
fig.savefig(out, dpi=100)
