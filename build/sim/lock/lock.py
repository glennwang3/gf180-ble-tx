#!/usr/bin/env python3
"""Closed-loop PLL lock after PEX, SS/125 C.
Post-PEX (RC) from the integrated layout: PFD + charge pump + PLL_BIAS + VCO_REG_L + PLL_LF_L + all top routing
(layout/pex_loop/LOOP_PART_rcpex.spice).  Behavioral: the v3 VCO and the /N divider (phase integrator).
VCO model, anchored on the integrated post-layout SS/125 run (README: 2.3981 GHz RF at VDD_VCO 3.1258 V) with the
v3 supply-pushing slope (0.352 GHz/V at the ring, 0.704 GHz/V at RF); 1.58 kOhm supply load (~2 mA).
python3 lock.py CASE T_us [VCTRL0] [N0] [N1 T_HOP_us]   (env PFD_SWAP=1: PFD inputs swapped)     f_RF = 2 N x 1 MHz (N 1201 = ch 0 = 2.402 GHz)
env overrides (defaults = the SS/125 v3 setup above): CORNER=tt27|ss125|ff-40, VCO=F0_ring_Hz,V0,KV_ring_Hz_per_V,
RVCO=ohm.  Low-cap VCO at TT (extracted RF partition, sim/tx/w_tt_*, VTUNE 1.2 V):
CORNER=tt27 VCO=1.199765e9,2.3276,0.664e9 RVCO=2700"""
import os
import subprocess
import sys

case, T = sys.argv[1], float(sys.argv[2])
v0 = sys.argv[3] if len(sys.argv) > 3 else "1.30"
N0 = int(sys.argv[4]) if len(sys.argv) > 4 else 1201
N1 = int(sys.argv[5]) if len(sys.argv) > 5 else N0
THOP = float(sys.argv[6]) if len(sys.argv) > 6 else 1e9
SWAP = os.environ.get("PFD_SWAP") == "1"     # reference -> PFD F_VCO pin, feedback -> F_REF pin
PFD_IN = "FB REF" if SWAP else "REF FB"
F0, V0, KV = (float(x) for x in os.environ.get("VCO", "1.19905e9,3.1258,0.352e9").split(","))  # ring Hz @ V0, ring Hz/V
RVCO = os.environ.get("RVCO", "1580")
LIB, TEMP = {"ss125": ("ss", 125), "tt27": ("typical", 27), "ff-40": ("ff", -40)}[os.environ.get("CORNER", "ss125")]
L = "/foss/designs/pll_compact/layout"
# C2 (LF_RZ) node of the extracted loop: the DC operating point does not set it (the cap_nmos model leaves it near
# 0.47 V, an .ic on the internal node is ignored, and Rz*C2 ~ 63 us >> the 10 us precharge).  So each run gets a
# private copy of LOOP_PART with a precharge source on the C2 net, active for the same 10 us (env C2IC=0: off).
LOOP = f"{L}/pex_loop/LOOP_PART_rcpex.spice"
C2NODE = next(l.split()[1] for l in open(LOOP) if "cap_nmos_03v3" in l and "c_width=20.4u" in l)
C2PRE = os.environ.get("C2IC", "1") == "1"
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                 for x in (LIB, "res_" + LIB, "mimcap_" + LIB, "moscap_" + LIB, "cap_mim"))
deck = f"""PLL lock {case}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "{'loop.spice' if C2PRE else LOOP}"
.temp {TEMP}
.options method=gear reltol=1e-3 abstol=1e-12 vntol=1e-6 itl4=100
Vdd VDD 0 3.3
Vref REF 0 PULSE(0 3.3 0 1n 1n 499n 1u)
XL VDD_VCO VDD 0 UPB DN IB TB {PFD_IN} VCTRL LOOP_PART
* VCO buffer tail gate on TAIL_BIAS
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
* behavioral v3 VCO (supply load + tuning curve) and /N divider (N steps from N0 to N1 at T_HOP)
RVCO VDD_VCO 0 {RVCO}
CVCO VDD_VCO 0 2p
BN NN 0 V = (time < {THOP}u) ? {N0} : {N1}
BF FF 0 V = ({F0} + {KV}*(v(vdd_vco)-{V0}))/v(nn)
BPH 0 PH I = v(ff)
CPH PH 0 1
BFB FB 0 V = 1.65 + 1.65*tanh(30*sin(6.283185307*v(ph) - 1.0))
* precharge VCTRL (and C2 through Rz) to VCTRL0, released at 10 us
BPRE VCTRL 0 I = (time < 10u) ? (v(vctrl)-{v0})/1k : 0
.ic v(ph)=0
.control
set noaskquit
set num_threads=1
save v(vctrl) v(vdd_vco) v(ff) v(nn) v(ib) v(xl.{C2NODE})
tran 2n {T}u 0 4n
let frf = 2*v(nn)*v(ff)
let ftgt = 2e6*v(nn)
wrdata out.txt v(vctrl) v(vdd_vco) frf ftgt v(ib) v(xl.{C2NODE})
quit
.endc
.end
"""
os.makedirs(case, exist_ok=True)
if C2PRE:
    net = open(LOOP).read().splitlines()
    i = max(k for k, l in enumerate(net) if l.startswith(".ends"))
    net.insert(i, f"BPREC2 {C2NODE} VSS I = (time < 10u) ? (v({C2NODE})-v(VSS)-{v0})/1k : 0")
    open(f"{case}/loop.spice", "w").write(chr(10).join(net) + chr(10))
open(f"{case}/t.sp", "w").write(deck)
open(f"{case}/.spiceinit", "w").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=case)
print(case, "done")
