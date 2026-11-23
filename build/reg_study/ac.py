#!/usr/bin/env python3
"""Regulator (VCO_REG, schematic) closed-loop VCTRL->VOUT response and DC point with a v3-like load."""
import os, subprocess, sys, itertools
HERE = os.path.dirname(os.path.abspath(__file__))
NET = "/foss/designs/vco_supply_regulator_3v3/VCO_Regulator_3V3_netlist.spice"
CORNERS = {"ss": ("ss", 125), "tt": ("typical", 27), "ff": ("ff", -40)}
def deck(corner, cout, rload, vctrl):
    lib, temp = CORNERS[corner]
    libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                     for x in (lib, "res_" + ("typical" if lib == "typical" else lib), "mimcap_" + ("typical" if lib=="typical" else lib)))
    return f"""reg ac
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "{NET}"
.temp {temp}
Vin VIN 0 3.3
Vc VCTRL 0 dc {vctrl} ac 1
Xr VIN VCTRL VOUT 0 VCO_REG
Resr VOUT DC 0.5
Cout DC 0 {cout}
Rl VOUT 0 {rload}
Cl VOUT 0 2p
.control
set noaskquit
op
let vo = v(vout)
let ig = v(xr.gate)
print vo ig
ac dec 40 10 100meg
let m = db(v(vout))
meas ac dc0 find m at=10
let m3 = m - dc0 + 3
meas ac f3 when m3=0 fall=1
let ph = 180/pi*cph(v(vout))
meas ac peak max m
quit
.endc
.end
"""
if __name__ == "__main__":
    out = []
    for corner, cout in itertools.product(sys.argv[1].split(","), sys.argv[2].split(",")):
        for vctrl in (1.63,):
            tag = f"{corner}_{cout}"
            d = os.path.join(HERE, tag); os.makedirs(d, exist_ok=True); open(os.path.join(d, ".spiceinit"), "w").write("set ngbehavior=hsa" + chr(10))
            open(os.path.join(d, "t.spice"), "w").write(deck(corner, cout, 1600, vctrl))
            r = subprocess.run(["ngspice", "-b", "t.spice"], cwd=d, capture_output=True, text=True)
            keep = [l for l in r.stdout.splitlines() if any(k in l for k in ("vo =", "ig =", "dc0", "f3", "peak"))]
            print(tag, " | ".join(x.strip() for x in keep), flush=True)
