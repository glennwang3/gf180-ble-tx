#!/usr/bin/env python3
# NOTE: icp = i(vc) is the current SOURCED into VCTRL (UP > 0): a source current flows + -> - through Vc.
# (An earlier version used -i(vc) and reported every sign inverted.)
"""Frequency-detection check of the post-PEX PFD + CP (LOOP_PART, SS/125): VCTRL held at 1.4 V by a source,
REF 1 MHz, FB a fixed 50 %-duty clock at F_FB.  A PFD with frequency detection gives a one-signed average
current; a phase-only detector averages to ~0 over whole beat periods.   python3 fd.py TAG F_FB_HZ T_us"""
import subprocess, sys, os
tag, ffb, T = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                 for x in ("ss", "res_ss", "mimcap_ss", "moscap_ss", "cap_mim"))
deck = f"""fd {tag}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "/foss/designs/pll_compact/layout/pex_loop/LOOP_PART_rcpex.spice"
.temp 125
.options method=gear reltol=1e-3 abstol=1e-12 vntol=1e-6
Vdd VDD 0 3.3
Vref REF 0 PULSE(0 3.3 0 1n 1n 499n 1u)
XL VDD_VCO VDD 0 UPB DN IB TB REF FB VCTRL LOOP_PART
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
RVCO VDD_VCO 0 1580
BFB FB 0 V = 1.65 + 1.65*tanh(30*sin(6.283185307*{ffb}*time - 1.0))
Vc VCTRL 0 1.4
.control
set noaskquit
tran 2n {T}u 0 4n
let icp = i(vc)
meas tran iavg avg icp from=2u to={T}u
wrdata out.txt icp
quit
.endc
.end
"""
os.makedirs(tag, exist_ok=True)
open(f"{tag}/t.sp", "w").write(deck)
open(f"{tag}/.spiceinit", "w").write("set ngbehavior=hsa\n")
out = subprocess.run("ngspice -b t.sp 2>&1", shell=True, cwd=tag, capture_output=True, text=True).stdout
print(tag, [l for l in out.splitlines() if "iavg" in l.lower()])
