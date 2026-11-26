#!/usr/bin/env python3
"""Post-PEX simulation of TS_PFD (lvs/TS_PFD_rcpex.spice).
    python3 pfdsim.py TAG CORNER FR_Hz FV_Hz TSTOP_s [DELAY_s] [CL_fF]
R = square wave at FR, V = square wave at FV (delayed by DELAY: V lags R for DELAY > 0).  UP / DN loaded with CL
(default 10 fF, ~ the A01 charge-pump switch gates).  Writes TAG/wave.raw and TAG/pulses.txt with one row per UP or DN
pulse: (start, width, kind) and prints a summary.
"""
import os
import subprocess
import sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw  # noqa: E402

CORNERS = {"ss125": ("ss", 125), "tt27": ("typical", 27), "ff-40": ("ff", -40)}
tag, corner, fr, fv, tstop = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
delay = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0      # > 0: V lags R
cl = float(sys.argv[7]) if len(sys.argv) > 7 else 10.0
lib, temp = CORNERS[corner]
tr = float(os.environ.get("TR", "0.2e-9"))
pul = lambda f, td: f"PULSE(0 3.3 {td:.6e} {tr:.3e} {tr:.3e} {0.5 / f - tr:.6e} {1 / f:.6e})"
step = min(20e-12, 0.002 / max(fr, fv))
deck = f"""TS_PFD post-PEX {corner} R {fr:.6g} V {fv:.6g} delay {delay:.3g}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {lib}
.include "/foss/designs/pll_compact/pfd/lvs/TS_PFD_rcpex.spice"
.temp {temp}
.options method=gear reltol=1e-3 abstol=1e-12 vntol=1e-6 itl4=100
Vdd v33 0 3.3
* a simultaneous pre-pulse on R and V at 2 ns puts the PFD in its idle state; the test edges start at 12 ns
Vra ra 0 {pul(fr, 12e-9 + max(0.0, -delay))}
Vva va 0 {pul(fv, 12e-9 + max(0.0, delay))}
Vpre pre 0 PULSE(0 3.3 2n {tr:.3e} {tr:.3e} 3n 1)
BR R 0 V = max(v(ra), v(pre))
BV V 0 V = max(v(va), v(pre))
X1 R V UPBO DN v33 0 UP TS_PFD_FLAT
Cu UP 0 {cl}f
Cd DN 0 {cl}f
.control
set noaskquit
set num_threads=1
set filetype=binary
save v(r) v(v) v(up) v(dn) i(vdd)
tran {step:.3e} {tstop:.6e} 0 {step:.3e}
write wave.raw v(r) v(v) v(up) v(dn) i(vdd)
quit
.endc
.end
"""
os.makedirs(tag, exist_ok=True)
open(f"{tag}/t.sp", "w", newline="\n").write(deck)
open(f"{tag}/.spiceinit", "w", newline="\n").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=tag)
w = read_raw(f"{tag}/wave.raw")
t = w["time"]


def edges(x, th=1.65):
    b = x > th
    up = np.where(~b[:-1] & b[1:])[0]; dn = np.where(b[:-1] & ~b[1:])[0]
    f = lambda i: t[i] + (th - x[i]) / (x[i + 1] - x[i]) * (t[i + 1] - t[i])
    return np.array([f(i) for i in up]), np.array([f(i) for i in dn])


rows = []
for name in ("up", "dn"):
    r_, f_ = edges(w[f"v({name})"])
    for a in r_:
        nx = f_[f_ > a]
        if len(nx):
            rows.append((a, nx[0] - a, name))
rows.sort()
np.savetxt(f"{tag}/pulses.txt", [(a, b, 1 if k == "up" else -1) for a, b, k in rows], fmt="%.6e %.6e %d",
           header="start width kind(+1 UP, -1 DN)")
m = t > 0.2 * t[-1]
avg = lambda k: np.trapezoid(w[k][m], t[m]) / (t[m][-1] - t[m][0]) / 3.3
up, dn = avg("v(up)"), avg("v(dn)")
iq = -np.trapezoid(w["i(vdd)"][m], t[m]) / (t[m][-1] - t[m][0])
wu = [b for a, b, k in rows if k == "up" and a > 0.2 * t[-1]]
wd = [b for a, b, k in rows if k == "dn" and a > 0.2 * t[-1]]
print(f"{tag}: {corner} R {fr/1e6:.4g} MHz V {fv/1e6:.4g} MHz delay {delay*1e9:.3g} ns | duty UP {up*100:.2f} % DN {dn*100:.2f} % "
      f"-> UP-DN {100*(up-dn):+.2f} % | UP pulses {len(wu)} (min {min(wu)*1e9 if wu else 0:.2f} / max {max(wu)*1e9 if wu else 0:.2f} ns), "
      f"DN pulses {len(wd)} (min {min(wd)*1e9 if wd else 0:.2f} / max {max(wd)*1e9 if wd else 0:.2f} ns) | I(3v3) {iq*1e6:.1f} uA")
