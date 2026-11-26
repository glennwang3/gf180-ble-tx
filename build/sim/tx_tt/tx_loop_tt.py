#!/usr/bin/env python3
"""Closed-loop PLL transmitting a GFSK bit pattern, TT/27, channel 0 (2.402 GHz), E03 low-cap VCO.
Post-PEX (RC): PFD + CP + PLL_BIAS + VCO_REG_L + PLL_LF_L + routing (layout/pex_loop), as sim/lock/lock.py (incl. the
in-netlist C2 precharge, released at 10 us).  Behavioral: VCO and /N.  The VCO uses the TT lock-run anchor
(lock.py: ring 1.199765 GHz at VDD_VCO 2.3276 V, 0.664 GHz/V, 2.7 kOhm supply load) plus the VTUNE curve measured
at transistor level (vtune_curve_tt.txt, offset taken at VTUNE = VB).  The DAC drives VTUNE from gfsk.py's PWL,
started at T_DATA.
    python3 tx_loop_tt.py CASE T_us T_DATA_us VCTRL0 VB VTFILE PWLFILE
"""
import os
import subprocess
import sys
import numpy as np

case, T, TD, v0, VB, vtf, pwl = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4], float(sys.argv[5]), \
    sys.argv[6], sys.argv[7]
F0, V0, KV = (float(x) for x in os.environ.get("VCO", "1.199765e9,2.3276,0.664e9").split(","))   # ring Hz @ V0, ring Hz/V (TT default)
CORNER = os.environ.get("CORNER", "tt27")
LIB, TEMP = {"tt27": ("typical", 27), "ff-40": ("ff", -40), "ss125": ("ss", 125)}[CORNER]
vt = np.loadtxt(vtf)
vt = vt[np.argsort(vt[:, 0])]
fb = np.interp(VB, vt[:, 0], vt[:, 1])
tab = ", ".join(f"{a:.4f}, {(b - fb) / 2:.1f}" for a, b in vt)   # ring-frequency offset vs VTUNE
pts = np.loadtxt(pwl)
pts[:, 0] += TD * 1e-6
pw = " ".join(f"{a:.6e} {b:.6f}" for a, b in np.vstack([[0, pts[0, 1]], pts]))
L = "/foss/designs/pll_compact/layout"
LOOP = os.environ.get("LOOPNET", f"{L}/pex_loop/LOOP_PART_rcpex.spice")   # LOOPNET: e.g. pex_loop_ts (TS_PFD)
C2NODE = next(l.split()[1] for l in open(LOOP) if "cap_nmos" in l and "c_width=20.4u" in l)
libs = chr(10).join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                    for x in (LIB, "res_" + LIB, "mimcap_" + LIB, "moscap_" + LIB, "cap_mim"))
deck = f"""PLL transmit {case}, {CORNER}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "loop.spice"
.temp {TEMP}
.options method=gear reltol={os.environ.get("RELTOL", "1e-3")} abstol=1e-12 vntol=1e-6 itl4=100{" rshunt=" + os.environ.get("RSHUNT", "1e12") if os.environ.get("UIC") == "1" else ""}
Vdd VDD 0 3.3
Vref REF 0 PULSE(0 3.3 0 {os.environ.get("REFTR", "1n")} {os.environ.get("REFTR", "1n")} 499n 1u)
XL VDD_VCO VDD 0 UPB DN IB TB REF FB VCTRL LOOP_PART
{("CC1X VCTRL 0 " + os.environ["C1X"] + "  $ extra C1 (ripple cap), ideal") if os.environ.get("C1X") else "* C1 as laid out"}
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
RVCO VDD_VCO 0 {os.environ.get("RVCO", "2700")}
CVCO VDD_VCO 0 2p
* DAC -> VTUNE (50 ohm + 0.1 pF)
Vdac DAC 0 PWL({pw})
Rdac DAC VTUNE 50
Cvt VTUNE 0 0.1p
BF FF 0 V = ({F0} + {KV}*(v(vdd_vco)-{V0}) + pwl(v(vtune), {tab}))/1201
BPH 0 PH I = v(ff)
CPH PH 0 1
BFB FB 0 V = 1.65 + 1.65*tanh({os.environ.get("FBSHARP", "30")}*sin(6.283185307*v(ph) - 1.0))
BPRE VCTRL 0 I = (time < 10u) ? (v(vctrl)-{v0})/1k : 0
.ic v(ph)=0
.control
set noaskquit
set num_threads=1
save v(vctrl) v(vdd_vco) v(ff) v(vtune) v(dn) v(upb)
tran {os.environ.get("TSTEP", "2n")} {T}u 0 {os.environ.get("TMAX", "4n")}{" uic" if os.environ.get("UIC") == "1" else ""}
let frf = 2*1201*v(ff)
wrdata out.txt v(vctrl) v(vdd_vco) frf v(vtune) v(dn) v(upb)
quit
.endc
.end
"""
os.makedirs(case, exist_ok=True)
net = open(LOOP).read().splitlines()
i = max(k for k, l in enumerate(net) if l.startswith(".ends"))
net.insert(i, f"BPREC2 {C2NODE} 0 I = (time < 10u) ? (v({C2NODE})-{v0})/10k : 0")   # global ground, 10k (see lock.py)
open(f"{case}/loop.spice", "w", newline="\n").write(chr(10).join(net) + chr(10))
open(f"{case}/t.sp", "w", newline="\n").write(deck)
open(f"{case}/.spiceinit", "w", newline="\n").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=case)
print(case, "done")
