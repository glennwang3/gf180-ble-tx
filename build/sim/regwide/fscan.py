#!/usr/bin/env python3
"""f_RF (2 x ring) of the delivered low-cap VCO (extracted PLL_PEX: VCO + prescaler) vs ideal VDD_VCO.
    python3 fscan.py CORNER TAIL VTUNE V1,V2,...   -> prints f_RF per VDD_VCO"""
import os
import subprocess
import sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw  # noqa: E402
NET = "/foss/designs/Diff_VCO_Second_Layout/low_cap_vco_20261122/delivery/vco_prescaler_rcpex.spice"
CORN = {"tt27": ("typical", 27), "ss125": ("ss", 125), "ff-40": ("ff", -40), "ss-40": ("ss", -40),
        "ff125": ("ff", 125), "tt125": ("typical", 125), "tt-40": ("typical", -40)}
corner, tail, vt, vs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split(",")
lib, temp = CORN[corner]
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}' for x in
                 (lib, "diode_" + lib, "res_" + lib, "mimcap_" + lib, "moscap_" + lib, "cap_mim"))
txt = open(NET).read().split(".subckt PLL_PEX", 1)[1].split("\n")
ports = txt[0].split() + (txt[1][1:].split() if txt[1].startswith("+") else [])
for v in vs:
    tag = f"f_{corner}_{v}"
    os.makedirs(tag, exist_ok=True)
    deck = f"""fscan
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "{NET}"
.temp {temp}
.options method=gear reltol=2e-4 abstol=1e-12 vntol=1e-6 itl4=80 rshunt=1e12
Vmain VDD 0 3.3
Vvco VDD_VCO 0 {v}
Vtn VTUNE 0 {vt}
Vtail TAIL_BIAS 0 {tail}
Vmode MC 0 3.3
Xdut {' '.join({'VSS': '0'}.get(p, p) for p in ports)} PLL_PEX
Crf RF_OUT 0 3f
Cdig PRESCALED 0 6f
.ic V(O1P)=2.2 V(O1N)=1.0
.control
set noaskquit
set filetype=binary
save v(o1p) v(o1n)
tran 4p 60n 0 4p
write wave.raw v(o1p) v(o1n)
quit
.endc
.end
"""
    open(f"{tag}/t.sp", "w").write(deck)
    open(f"{tag}/.spiceinit", "w").write("set ngbehavior=hsa\n")
    subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=tag)
    w = read_raw(f"{tag}/wave.raw")
    t = w["time"]; m = t > 25e-9
    x = (w["v(o1p)"] - w["v(o1n)"])[m]; tt = t[m]
    s = np.where((x[:-1] < 0) & (x[1:] >= 0))[0]
    tc = tt[s] - x[s] / (x[s + 1] - x[s]) * (tt[s + 1] - tt[s])
    f = 2 / np.mean(np.diff(tc)) if len(tc) > 3 else float("nan")
    print(f"{corner} VTUNE {vt} tail {tail} VDD_VCO {v}: f_RF {f/1e9:.4f} GHz", flush=True)
