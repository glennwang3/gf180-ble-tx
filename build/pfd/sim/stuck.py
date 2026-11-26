#!/usr/bin/env python3
"""Standalone post-PEX TS_PFD: V at f1 for T1, then f2 -- does the DN/UP 'stuck' state release?
   python3 stuck.py TAG F1_Hz F2_Hz [T1_us] [T2_us] [TR_s] [corner]"""
import os, subprocess, sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw
tag, f1, f2 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
T1 = float(sys.argv[4]) if len(sys.argv) > 4 else 30
T2 = float(sys.argv[5]) if len(sys.argv) > 5 else 30
tr = float(sys.argv[6]) if len(sys.argv) > 6 else 0.3e-9
lib, temp = {"tt": ("typical", 27), "ss": ("ss", 125), "ff": ("ff", -40)}[sys.argv[7] if len(sys.argv) > 7 else "tt"]
net = "/foss/designs/pll_compact/pfd/lvs/TS_PFD_rcpex.spice"
pul = lambda f, td: f"PULSE(0 3.3 {td:.4e} {tr:.3e} {tr:.3e} {0.5/f - tr:.6e} {1/f:.6e})"
# V: f1 until T1, then f2 starting at the next f1 falling edge region (start f2 low: first edge at T1 + 0.5/f2)
deck = f"""stuck {tag}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {lib}
.include "{net}"
.temp {temp}
.options method=gear reltol=1e-3 abstol=1e-14 vntol=1e-6
Vdd v33 0 3.3
Vr R 0 {pul(1e6, 12e-9)}
Va va 0 {pul(f1, 300e-9)}
Vb vb 0 {pul(f2, T1*1e-6 + 0.5/f2)}
Vs sel 0 PWL(0 0 {T1*1e-6 - 1e-9:.6e} 0 {T1*1e-6:.6e} 1)
BV V 0 V = v(sel) > 0.5 ? v(vb) : v(va)
X1 R V UPBO DN v33 0 UP TS_PFD_FLAT
CU UP 0 10f
CD DN 0 10f
.control
set noaskquit
set num_threads=1
set filetype=binary
save v(up) v(dn) v(r) v(v)
tran 50p {(T1+T2)*1e-6:.6e} 0 1n
write wave.raw v(up) v(dn) v(r) v(v)
quit
.endc
.end
"""
os.makedirs(tag, exist_ok=True)
open(f"{tag}/t.sp", "w").write(deck)
open(f"{tag}/.spiceinit", "w").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=tag)
w = read_raw(f"{tag}/wave.raw"); t = w["time"]
up = w["v(up)"] > 1.65; dn = w["v(dn)"] > 1.65
step = 5
for a in np.arange(0, T1 + T2, step):
    m = (t >= a*1e-6) & (t < (a+step)*1e-6)
    tu = np.trapezoid(up[m].astype(float), t[m]); td = np.trapezoid(dn[m].astype(float), t[m])
    print(f"{tag} {a:4.0f}-{a+step:.0f} us (V {f1/1e6 if a < T1 else f2/1e6:.3f} MHz): UP {tu/step*1e8:5.1f}%  DN {td/step*1e8:5.1f}%")
