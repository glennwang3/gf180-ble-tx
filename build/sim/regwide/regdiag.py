#!/usr/bin/env python3
"""Where do the TT peaking / FF slow response come from: VCTRL->BUF (input buffer) vs REF->VOUT (main loop),
plus a 0.2 -> 1.2 mA load step on VOUT, at the channel-0 point of each corner."""
import subprocess
import numpy as np
REG = "/foss/designs/pll_compact/layout/VCO_REG_L.spice"
CORN = {"tt27": ("typical", 27, 1.27, 2.8e3), "ss125": ("ss", 125, 2.68, 2.8e3), "ff-40": ("ff", -40, 0.40, 1.8e3)}


def libs(lib):
    return "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                     for x in (lib, "res_" + lib, "mimcap_" + lib, "moscap_" + lib, "cap_mim"))


for c, (lib, t, vc, rl) in CORN.items():
    deck = f'''x
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs(lib)}
.include "{REG}"
.temp {t}
Vin VIN 0 3.3
Vc VCTRL 0 dc {vc} ac 1
X1 VIN VCTRL VOUT 0 VCO_REG_L
Rl VOUT 0 {rl}
Cl VOUT 0 2p
Ist VOUT 0 PULSE(0 0.3m 2u 10n 10n 4u 20u)
.control
op
print v(vout) v(x1.buf) v(x1.ref) v(x1.gate) v(x1.drive)
ac dec 40 10 100meg
let mb = db(v(x1.buf)/v(vctrl))
let mr = db(v(vout)/v(x1.ref))
meas ac b0 find mb at=10
meas ac bpk max mb
let b3 = mb - b0 + 3
meas ac bf3 when b3=0 fall=1
meas ac r0 find mr at=10
meas ac rpk max mr
let r3 = mr - r0 + 3
meas ac rf3 when r3=0 fall=1
tran 2n 10u
meas tran vpre find v(vout) at=1.9u
meas tran vmin min v(vout) from=2u to=5u
meas tran vend find v(vout) at=5.9u
meas tran vmax max v(vout) from=6u to=10u
.endc
.end
'''
    open(f"dg_{c}.sp", "w").write(deck)
    open(".spiceinit", "w").write("set ngbehavior=hsa\n")
    out = subprocess.run(f"ngspice -b dg_{c}.sp", shell=True, capture_output=True, text=True).stdout
    g = {}
    for l in out.splitlines():
        s = l.strip()
        for k in ("v(vout)", "v(x1.buf)", "v(x1.ref)", "v(x1.gate)", "v(x1.drive)", "b0", "bpk", "bf3", "r0", "rpk", "rf3",
                  "vpre", "vmin", "vend", "vmax"):
            if s.startswith(k + " ") or s.startswith(k + "="):
                g[k] = float(s.split("=")[1].split()[0])
    print(f"{c}: VOUT {g['v(vout)']:.3f} BUF {g['v(x1.buf)']:.3f} REF {g['v(x1.ref)']:.3f} GATE {g['v(x1.gate)']:.3f} "
          f"DRIVE {g['v(x1.drive)']:.3f}")
    print(f"   buffer VCTRL->BUF: -3 dB {g['bf3']/1e3:.1f} kHz, peaking {g['bpk']-g['b0']:.2f} dB | "
          f"main loop REF->VOUT: gain {10**(g['r0']/20):.2f}, -3 dB {g['rf3']/1e3:.1f} kHz, peaking {g['rpk']-g['r0']:.2f} dB")
    print(f"   +0.3 mA load step: {g['vpre']:.4f} -> min {g['vmin']:.4f} -> {g['vend']:.4f} V; release overshoot to {g['vmax']:.4f} V")
