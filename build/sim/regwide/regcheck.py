#!/usr/bin/env python3
"""Widened VCO_REG_L (layout netlist) + new PLL_BIAS: DC transfer, closed-loop VCTRL->VOUT bandwidth / peaking
at the channel-0 operating point of each corner, and the CP bias current."""
import subprocess
import numpy as np
REG = "/foss/designs/pll_compact/layout/VCO_REG_L.spice"
BIAS = "/foss/designs/pll_compact/layout/PLL_BIAS.spice"
CORN = {"tt27": ("typical", 27), "ss125": ("ss", 125), "ff-40": ("ff", -40), "ss-40": ("ss", -40), "ff125": ("ff", 125)}
# channel-0 VDD_VCO (fscan.py, VTUNE 1.2) and VCO load (~V / I)
OP = {"tt27": (2.345, 2.8e3), "ss125": (3.19, 2.8e3), "ff-40": (1.825, 1.8e3)}


def libs(lib):
    return "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                     for x in (lib, "res_" + lib, "mimcap_" + lib, "moscap_" + lib, "cap_mim"))


def ng(tag, body):
    open(f"{tag}.sp", "w").write(body)
    open(".spiceinit", "w").write("set ngbehavior=hsa\n")
    return subprocess.run(f"ngspice -b {tag}.sp", shell=True, capture_output=True, text=True).stdout


for c, (lib, t) in CORN.items():
    hdr = f'''x
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs(lib)}
.include "{REG}"
.include "{BIAS}"
.temp {t}
Vin VIN 0 3.3
'''
    out = ng(f"dc_{c}", hdr + f"""Vc VCTRL 0 1.5
X1 VIN VCTRL VOUT 0 VCO_REG_L
RL VOUT 0 2.8k
XB VIN 0 IBO TB PLL_BIAS
Vcp IBO IB 0
XCPD IB IB 0 0 nfet_03v3 w=1.12u l=1u
.control
op
print i(vcp) v(tb)
dc Vc 0 3.3 0.1
print v(vout)
.endc
.end
""")
    lines = out.splitlines()
    icp = next(float(l.split("=")[1]) for l in lines if l.strip().startswith("i(vcp)"))
    tb = next(float(l.split("=")[1]) for l in lines if l.strip().startswith("v(tb)"))
    rows = np.array([[float(v) for v in l.split()[1:3]] for l in lines if l[:1].isdigit() and len(l.split()) == 3])
    vc, vo = rows[:, 0], rows[:, 1]
    lin = (vc >= 0.4) & (vc <= 2.4)
    b, a = np.polyfit(vc[lin], vo[lin], 1)
    print(f"{c}: VOUT = {a:.3f} + {b:.3f}*VCTRL (fit 0.4..2.4 V); VOUT(0.3) {np.interp(0.3, vc, vo):.3f}, "
          f"VOUT(2.8) {np.interp(2.8, vc, vo):.3f}, max {vo.max():.3f} V | CP bias {abs(icp)*1e6:.3f} uA, TAIL_BIAS {tb:.3f} V")
    if c in OP:
        v0, rl = OP[c]
        vcop = (v0 - a) / b
        out = ng(f"ac_{c}", hdr + f"""Vc VCTRL 0 dc {vcop:.4f} ac 1
X1 VIN VCTRL VOUT 0 VCO_REG_L
Rl VOUT 0 {rl}
Cl VOUT 0 2p
.control
op
print v(vout)
ac dec 40 10 100meg
let m = db(v(vout))
meas ac dc0 find m at=10
let m3 = m - dc0 + 3
meas ac f3 when m3=0 fall=1
meas ac pk max m
.endc
.end
""")
        g = {k: l.split("=")[1].split()[0] for l in out.splitlines() for k in ("dc0", "f3", "pk", "v(vout)") if l.strip().startswith(k)}
        print(f"   ch0 point VCTRL {vcop:.2f} V -> VOUT {float(g['v(vout)']):.3f} V, load {rl/1e3:.1f}k: "
              f"VCTRL->VOUT gain {10**(float(g['dc0'])/20):.3f}, -3 dB at {float(g['f3'])/1e3:.1f} kHz, "
              f"peaking {float(g['pk']) - float(g['dc0']):.2f} dB")
