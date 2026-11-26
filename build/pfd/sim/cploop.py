#!/usr/bin/env python3
"""Open-loop LOOP_PART (PLL_TSPFD extraction, linear moscaps): VCTRL held by an ideal source, REF / FB pulses with a fixed
offset.  Prints the charge per period into VCTRL by time window and the quiescent current (between edges).
   python3 cploop.py TAG DELAY_s [VCTRL] [NETLIST] [MODE]     DELAY > 0: FB lags REF.   MODE=idle: no edges at all"""
import os, subprocess, sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw
tag, delay = sys.argv[1], float(sys.argv[2])
vc = float(sys.argv[3]) if len(sys.argv) > 3 else 1.435
net = sys.argv[4] if len(sys.argv) > 4 else "/foss/designs/pll_compact/layout/pex_loop_ts/LOOP_PART_rcpex_ff_lin.spice"
idle = len(sys.argv) > 5 and sys.argv[5] == "idle"
tr = 0.3e-9
pul = lambda td: f"PULSE(0 3.3 {td:.6e} {tr:.3e} {tr:.3e} {0.5e-6 - tr:.6e} 1e-6)"
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                 for x in ("typical", "res_typical", "mimcap_typical", "moscap_typical", "cap_mim"))
deck = f"""cploop {tag}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "{net}"
.temp 27
.options method=gear reltol=1e-3 abstol=1e-14 vntol=1e-6 itl4=100
Vdd VDD 0 3.3
Vref REF 0 {'0' if idle else pul(12e-9 + max(0.0, -delay))}
Vfb FB 0 {'0' if idle else pul(12e-9 + max(0.0, delay))}
XL VDD_VCO VDD 0 UPB DN IB TB REF FB VCTRL LOOP_PART
Vc VCTRL 0 {vc}
RVCO VDD_VCO 0 2700
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
.control
set noaskquit
set num_threads=1
set filetype=binary
save i(vc) v(upb) v(dn) v(vdd_vco) v(ib)
tran 0.1n 6u 0 0.5n
write wave.raw i(vc) v(upb) v(dn) v(vdd_vco) v(ib)
quit
.endc
.end
"""
os.makedirs(tag, exist_ok=True)
open(f"{tag}/t.sp", "w").write(deck)
open(f"{tag}/.spiceinit", "w").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=tag)
w = read_raw(f"{tag}/wave.raw"); t = w["time"]; i = -w["i(vc)"]     # current INTO the VCTRL net from the loop (+ = charging)
res = []
for k in (3, 4, 5):
    a = 12e-9 + k * 1e-6 - 50e-9
    m = (t >= a) & (t < a + 1e-6); tt = t[m] - a; ii = i[m]
    w5 = [(0, 45e-9), (45e-9, 70e-9), (70e-9, 200e-9), (200e-9, 1e-6)]
    res.append([np.trapezoid(ii[(tt >= lo) & (tt < hi)], tt[(tt >= lo) & (tt < hi)]) * 1e15 for lo, hi in w5])
r = np.mean(res, axis=0)
m = (t > 4.4e-6) & (t < 4.9e-6)
print(f"{tag}: delay {delay*1e9:+.1f} ns | Q/period {r.sum():+.3f} fC = pre {r[0]:+.3f} edge(-5..+20ns) {r[1]:+.3f} "
      f"tail(20..150ns) {r[2]:+.3f} rest {r[3]:+.3f} | quiescent {np.median(i[m])*1e12:+.1f} pA | IB {np.median(w['v(ib)'][m]):.3f} V")
