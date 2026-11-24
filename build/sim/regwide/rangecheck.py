#!/usr/bin/env python3
"""Widened VCO_REG_L (layout netlist): over VCTRL 0.6 .. 2.8 V at five corners -> VOUT, main-loop REF->VOUT peaking
and -3 dB, VCTRL->VOUT -3 dB (the pole the PLL sees), VCTRL-buffer -3 dB.  Load ~ VCO: 2.8k (1.8k below 2 V)."""
import subprocess
REG = "/foss/designs/pll_compact/layout/VCO_REG_L.spice"
CORN = {"ff-40": ("ff", -40), "ff125": ("ff", 125), "tt27": ("typical", 27), "ss125": ("ss", 125), "ss-40": ("ss", -40)}


def libs(lib):
    return "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                     for x in (lib, "res_" + lib, "mimcap_" + lib, "moscap_" + lib, "cap_mim"))


worst = 0
for c, (lib, t) in CORN.items():
    print(c, flush=True)
    for vc in (0.6, 1.0, 1.45, 1.9, 2.35, 2.8):
        rl = 1.8e3 if 1.40 + 0.65 * vc < 2.0 else 2.8e3
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
.control
op
print v(vout)
ac dec 40 10 300meg
let mr = db(v(vout)/v(x1.ref))
let mv = db(v(vout))
let mb = db(v(x1.buf))
meas ac r0 find mr at=10
meas ac rpk max mr
let r3 = mr - r0 + 3
meas ac rf3 when r3=0 fall=1
meas ac v0 find mv at=10
let v3 = mv - v0 + 3
meas ac vf3 when v3=0 fall=1
meas ac vpk max mv
meas ac b0 find mb at=10
let b3 = mb - b0 + 3
meas ac bf3 when b3=0 fall=1
.endc
.end
'''
        open("rc.sp", "w").write(deck)
        open(".spiceinit", "w").write("set ngbehavior=hsa\n")
        out = subprocess.run("ngspice -b rc.sp", shell=True, capture_output=True, text=True).stdout
        g = {}
        for l in out.splitlines():
            s = l.strip()
            for k in ("v(vout)", "r0", "rpk", "rf3", "v0", "vf3", "vpk", "bf3"):
                if s.startswith(k + " ") or s.startswith(k + "="):
                    g[k] = float(s.split("=")[1].split()[0])
        pk = g["rpk"] - g["r0"]
        worst = max(worst, pk, g["vpk"] - g["v0"])
        print(f"   VCTRL {vc:.2f}: VOUT {g['v(vout)']:.3f} V | main loop -3 dB {g['rf3']/1e3:9.1f} kHz, peaking {pk:5.2f} dB | "
              f"VCTRL->VOUT gain {10**(g['v0']/20):.3f}, -3 dB {g['vf3']/1e3:9.1f} kHz, peaking {g['vpk']-g['v0']:.2f} dB | "
              f"buffer -3 dB {g['bf3']/1e3:8.1f} kHz", flush=True)
print(f"worst peaking {worst:.2f} dB")
