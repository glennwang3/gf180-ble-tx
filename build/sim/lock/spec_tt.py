#!/usr/bin/env python3
"""RF spectrum of a locked closed-loop run (lock.py CASE/out.txt): phase = 2 pi * integral of (f_RF - f_target),
baseband exp(j*phase) on a 2 ns grid over the last T_WIN us, Hann window.  Shows the 1 MHz reference spurs.
    python3 spec_tt.py OUT.png CASE [T_WIN_us]
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

out, case = sys.argv[1], sys.argv[2]
twin = float(sys.argv[3]) if len(sys.argv) > 3 else 150.0
d = np.loadtxt(case + "/out.txt")
t, vv, f, ft = d[:, 0], d[:, 3], d[:, 5], d[:, 7]
dt = 2e-9
tg = np.arange(t[-1] - twin * 1e-6, t[-1], dt)
df = np.interp(tg, t, f - ft)
ph = 2 * np.pi * np.cumsum(df) * dt
x = np.exp(1j * ph)
w = np.hanning(len(x))
X = np.fft.fftshift(np.fft.fft(x * w))
fr = np.fft.fftshift(np.fft.fftfreq(len(x), dt))
p = 20 * np.log10(np.abs(X) / np.abs(X).max())
k0 = np.argmin(np.abs(fr))
car = p[k0]


def peak(f0):
    m = np.abs(fr - f0) < 30e3
    return p[m].max()


spurs = {n: peak(n * 1e6) for n in (-3, -2, -1, 1, 2, 3)}
vdd = np.interp(tg, t, vv)
print(f"{case}: carrier {car:.1f} dB (total = 0 dB ref), spurs " + ", ".join(f"{n:+d} MHz {s - car:+.1f} dBc" for n, s in spurs.items()))
print(f"VDD_VCO ripple p-p {np.ptp(vdd)*1e3:.2f} mV, f_RF ripple p-p (instantaneous) {np.ptp(df)/1e6:.2f} MHz")
fig, ax = plt.subplots(2, 1, figsize=(11, 8))
a = ax[0]
a.plot(fr / 1e6, p, lw=0.8, color="C3")
for n, s in spurs.items():
    a.annotate(f"{s - car:+.0f} dBc", (n, s), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8)
a.annotate(f"carrier {car:.0f} dB", (0, car), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8)
a.set_xlim(-5, 5)
a.set_ylim(-90, 5)
a.set_xlabel("offset from 2.402 GHz [MHz]")
a.set_ylabel("dB (rel. strongest line)")
a.grid(alpha=0.3)
a.set_title(f"Locked RF spectrum, last {twin:.0f} us of {case} (Hann, {1e3/twin:.1f} kHz bins): the 1 MHz charge-pump ripple "
            "passes the regulator and frequency-modulates the VCO", fontsize=10)
a = ax[1]
z = tg >= tg[-1] - 5e-6
a.plot((tg[z] - tg[-1]) * 1e6, df[z] / 1e6, lw=0.8, color="C3", label="f_RF - 2.402 GHz [MHz]")
a.set_ylabel("f_RF - 2.402 GHz [MHz]", color="C3")
a.set_xlabel("time before end of run [us]")
b = a.twinx()
b.plot((tg[z] - tg[-1]) * 1e6, vdd[z] * 1e3, lw=0.8, color="C2")
b.set_ylabel("VDD_VCO [mV]", color="C2")
a.grid(alpha=0.3)
a.set_title(f"Last 5 us: VDD_VCO ripple {np.ptp(vdd)*1e3:.1f} mV p-p -> f_RF ripple {np.ptp(df)/1e6:.1f} MHz p-p "
            "at the 1 MHz reference rate", fontsize=10)
fig.suptitle("PLL locked at TT / 27 C (post-PEX loop, behavioral low-cap VCO 1.33 GHz/V at RF, channel 0)", fontsize=11)
fig.tight_layout()
fig.savefig(out, dpi=105)
