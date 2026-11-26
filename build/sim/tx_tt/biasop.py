#!/usr/bin/env python3
"""DC operating point of the extracted LOOP_PART (PLL_TSPFD_C1) per corner: TAIL_BIAS, CP_IBIAS node, 3.3 V current.
VCTRL held at the corner's channel-0 value.   python3 biasop.py CORNER VCTRL"""
import os, subprocess, sys
corner, vc = sys.argv[1], sys.argv[2]
lib, temp = {"tt27": ("typical", 27), "ff-40": ("ff", -40), "ss125": ("ss", 125)}[corner]
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                 for x in (lib, "res_" + lib, "mimcap_" + lib, "moscap_" + lib, "cap_mim"))
d = f"op_{corner}"
os.makedirs(d, exist_ok=True)
open(f"{d}/t.sp", "w").write(f"""bias op {corner}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "/foss/designs/pll_compact/layout/pex_loop_ts_c1/LOOP_PART_rcpex_ff.spice"
.temp {temp}
Vdd VDD 0 3.3
Vref REF 0 0
Vfb FB 0 0
XL VDD_VCO VDD 0 UPB DN IB TB REF FB VCTRL LOOP_PART
Vc VCTRL 0 {vc}
RVCO VDD_VCO 0 2700
.control
op
print v(tb) v(ib) v(vdd_vco) i(vdd) i(vc)
quit
.endc
.end
""")
open(f"{d}/.spiceinit", "w").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp 2>&1 | grep -E '^v\(|^i\(|= ' | tail -6", shell=True, cwd=d)
