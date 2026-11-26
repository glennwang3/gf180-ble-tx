#!/usr/bin/env python3
"""Isolate the closed-loop DN-stuck failure.  REF 1 MHz PULSE; V = 1.1 MHz for 30 us then 0.85 MHz for 30 us.
MODE loop : LOOP_PART (pex_loop_ts, the PLL_TSPFD extraction) with VCTRL held at 1.2 V, V as PULSE (tr 0.3 ns)
MODE tanh : standalone TS_PFD, V from the loop's tanh(1000 sin) phase source, tran tmax 2 ns (as the loop deck)
MODE both : LOOP_PART + tanh V + tmax 2 ns
   python3 stuck2.py TAG MODE"""
import os, subprocess, sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw
tag, mode = sys.argv[1], sys.argv[2]
tr = 0.3e-9
pul = lambda f, td: f"PULSE(0 3.3 {td:.4e} {tr:.3e} {tr:.3e} {0.5/f - tr:.6e} {1/f:.6e})"
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                 for x in ("typical", "res_typical", "mimcap_typical", "moscap_typical", "cap_mim"))
loop = mode in ("loop", "both")
tanh = mode in ("tanh", "both")
if tanh:
    vsrc = ("BF FF 0 V = (time < 30u) ? 1.1e6 : 0.85e6\nBPH 0 PH I = v(ff)\nCPH PH 0 1\n"
            "BV V 0 V = 1.65 + 1.65*tanh(1000*sin(6.283185307*v(ph) - 1.0))\n.ic v(ph)=0.3\n")
else:
    vsrc = (f"Va va 0 {pul(1.1e6, 300e-9)}\nVb vb 0 {pul(0.85e6, 30e-6 + 0.5/0.85e6)}\n"
            "Vs sel 0 PWL(0 0 29.999u 0 30u 1)\nBV V 0 V = v(sel) > 0.5 ? v(vb) : v(va)\n")
if loop:
    dut = ('.include "/foss/designs/pll_compact/layout/pex_loop_ts/LOOP_PART_rcpex_ff.spice"\n'
           "XL VDD_VCO v33 0 UPB DN IB TB R V VCTRL LOOP_PART\nVC VCTRL 0 1.2\nRVCO VDD_VCO 0 2700\n"
           "XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u\nVTD TD 0 1.0\n")
    sv = "v(upb) v(dn) v(r) v(v)"; upexpr = "upb"
else:
    dut = ('.include "/foss/designs/pll_compact/pfd/lvs/TS_PFD_rcpex.spice"\n'
           "X1 R V UPB DN v33 0 UP TS_PFD_FLAT\nCU UP 0 10f\nCD DN 0 10f\n")
    sv = "v(upb) v(dn) v(r) v(v)"
deck = f"""stuck2 {tag}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
{dut}
.temp 27
.options method=gear reltol=1e-3 abstol=1e-12 vntol=1e-6 itl4=100
Vdd v33 0 3.3
Vr R 0 {pul(1e6, 12e-9)}
{vsrc}
.control
set noaskquit
set num_threads=1
set filetype=binary
save {sv}
tran {'1n 60u 0 2n' if tanh else '50p 60u 0 1n'}
write wave.raw {sv}
quit
.endc
.end
"""
os.makedirs(tag, exist_ok=True)
open(f"{tag}/t.sp", "w").write(deck)
open(f"{tag}/.spiceinit", "w").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=tag)
w = read_raw(f"{tag}/wave.raw"); t = w["time"]
up = w["v(upb)"] < 1.65; dn = w["v(dn)"] > 1.65
for a in range(0, 60, 5):
    m = (t >= a*1e-6) & (t < (a+5)*1e-6)
    tu = np.trapezoid(up[m].astype(float), t[m]); td = np.trapezoid(dn[m].astype(float), t[m])
    print(f"{tag} {a:3d}-{a+5} us (V {'1.10' if a < 30 else '0.85'} MHz): UP {tu/5e-6*100:5.1f}%  DN {td/5e-6*100:5.1f}%")
