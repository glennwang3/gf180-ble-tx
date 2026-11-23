#!/usr/bin/env python3
"""Regulator load step (2.0 -> 2.4 mA) vs output decap; ringing tells the output-loop margin."""
import os, subprocess, sys, itertools
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
NET = "/foss/designs/vco_supply_regulator_3v3/VCO_Regulator_3V3_netlist.spice"
CORNERS = {"ss": ("ss", 125), "tt": ("typical", 27), "ff": ("ff", -40)}
def deck(corner, cout):
    lib, temp = CORNERS[corner]
    l2 = "typical" if lib == "typical" else lib
    libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}' for x in (lib, "res_" + l2, "mimcap_" + l2))
    return f"""reg step
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "{NET}"
.temp {temp}
Vin VIN 0 3.3
Vc VCTRL 0 1.63
Xr VIN VCTRL VOUT 0 VCO_REG
Resr VOUT DC 0.5
Cout DC 0 {cout}
Rl VOUT 0 1600
Il VOUT 0 PULSE(0 0.4m 20u 20n 20n 20u 100u)
.control
set noaskquit
set num_threads=1
tran 5n 60u
wrdata out.txt v(vout)
quit
.endc
.end
"""
for corner, cout in itertools.product(sys.argv[1].split(","), sys.argv[2].split(",")):
    d = os.path.join(HERE, f"step_{corner}_{cout}"); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, ".spiceinit"), "w").write("set ngbehavior=hsa" + chr(10))
    open(os.path.join(d, "t.spice"), "w").write(deck(corner, cout))
    subprocess.run(["ngspice", "-b", "t.spice"], cwd=d, capture_output=True)
    t, v = np.loadtxt(os.path.join(d, "out.txt")).T
    pre = v[(t > 15e-6) & (t < 20e-6)].mean()
    w = (t > 20e-6) & (t < 40e-6)
    post = v[(t > 35e-6) & (t < 40e-6)].mean()
    dip = v[w].min()
    w2 = (t > 40e-6) & (t < 60e-6)
    over = v[w2].max()
    # ringing: count local extrema of (v - post) exceeding 0.5 mV after the step
    x = v[w] - post
    ext = np.sum((np.abs(x[1:-1]) > 0.5e-3) & (np.sign(x[1:-1] - x[:-2]) != np.sign(x[2:] - x[1:-1])))
    print(f"{corner:3s} Cout {cout:6s} pre {pre:.4f} dip {1e3*(pre-dip):6.1f} mV  post {post:.4f}  release overshoot {1e3*(over-pre):6.1f} mV  extrema>0.5mV {ext}", flush=True)
