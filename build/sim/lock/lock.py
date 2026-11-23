#!/usr/bin/env python3
"""Closed-loop PLL lock after PEX, SS/125 C.
Post-PEX (RC) from the integrated layout: PFD + charge pump + PLL_BIAS + VCO_REG_L + PLL_LF_L + all top routing
(layout/pex_loop/LOOP_PART_rcpex.spice).  Behavioral: the v3 VCO and the /N divider (phase integrator).
VCO model, anchored on the integrated post-layout SS/125 run (README: 2.3981 GHz RF at VDD_VCO 3.1258 V) with the
v3 supply-pushing slope (0.352 GHz/V at the ring, 0.704 GHz/V at RF); 1.58 kOhm supply load (~2 mA).
python3 lock.py CASE T_us [VCTRL0] [N0] [N1 T_HOP_us]   (env PFD_SWAP=1: PFD inputs swapped)     f_RF = 2 N x 1 MHz (N 1201 = ch 0 = 2.402 GHz)"""
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
F0, V0, KV = 1.19905e9, 3.1258, 0.352e9          # ring Hz at VDD_VCO V0, ring Hz/V
L = "/foss/designs/pll_compact/layout"
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                 for x in ("ss", "res_ss", "mimcap_ss", "moscap_ss", "cap_mim"))
deck = f"""PLL lock {case}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "{L}/pex_loop/LOOP_PART_rcpex.spice"
.temp 125
.options method=gear reltol=1e-3 abstol=1e-12 vntol=1e-6 itl4=100
Vdd VDD 0 3.3
Vref REF 0 PULSE(0 3.3 0 1n 1n 499n 1u)
XL VDD_VCO VDD 0 UPB DN IB TB {PFD_IN} VCTRL LOOP_PART
* VCO buffer tail gate on TAIL_BIAS
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
* behavioral v3 VCO (supply load + tuning curve) and /N divider (N steps from N0 to N1 at T_HOP)
RVCO VDD_VCO 0 1580
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
save v(vctrl) v(vdd_vco) v(ff) v(nn) v(ib)
tran 2n {T}u 0 4n
let frf = 2*v(nn)*v(ff)
let ftgt = 2e6*v(nn)
wrdata out.txt v(vctrl) v(vdd_vco) frf ftgt v(ib)
quit
.endc
.end
"""
os.makedirs(case, exist_ok=True)
open(f"{case}/t.sp", "w").write(deck)
open(f"{case}/.spiceinit", "w").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=case)
print(case, "done")
