#!/usr/bin/env python3
"""Operating limits for the regulator re-ratio: (1) VCTRL buffer tracking (BUF vs VCTRL) of VCO_REG_L,
(2) charge-pump output compliance (UP-only and DN-only current vs OUT), at tt27 / ss125 / ff-40."""
import subprocess
import numpy as np
CORN = {"tt27": ("typical", 27), "ss125": ("ss", 125), "ff-40": ("ff", -40)}
REG = "/foss/designs/pll_compact/layout/VCO_REG_L.spice"
CP = "/foss/designs/pll_compact/lvs_chipathon/out/macros/Charge_Pump_FE.spice"


def libs(lib):
    return "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                     for x in (lib, "res_" + lib, "mimcap_" + lib, "moscap_" + lib, "cap_mim"))


def run(tag, body):
    open(f"{tag}.sp", "w").write(body)
    open(".spiceinit", "w").write("set ngbehavior=hsa\n")
    out = subprocess.run(f"ngspice -b {tag}.sp", shell=True, capture_output=True, text=True).stdout
    rows = [l.split() for l in out.splitlines() if l[:1].isdigit() and len(l.split()) >= 3]
    return np.array([[float(v) for v in r[1:]] for r in rows])


for c, (lib, t) in CORN.items():
    d = run(f"buf_{c}", f"""buf {c}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs(lib)}
.include "{REG}"
.temp {t}
Vin VIN 0 3.3
Vc VCTRL 0 1.5
X1 VIN VCTRL VOUT 0 VCO_REG_L
RL VOUT 0 2.8k
.control
dc Vc 0 3.3 0.1
print v(vctrl) v(x1.buf) v(vout)
.endc
.end
""")
    vc, buf, vo = d[:, -3], d[:, -2], d[:, -1]      # columns: sweep, v(vctrl), v(buf), v(vout)
    err = np.abs(buf - vc)
    ok = vc[err < 0.02]
    print(f"{c}: BUF tracks VCTRL within 20 mV for VCTRL {ok.min():.1f}..{ok.max():.1f} V; "
          f"BUF at VCTRL 0 / 0.5 / 1.0 = {np.interp(0, vc, buf):.2f} / {np.interp(0.5, vc, buf):.2f} / {np.interp(1.0, vc, buf):.2f}")
    # CP: IBIAS fed with 2.5 uA (as from PLL_BIAS), UP on (UPb low) or DN on
    for mode, upb, dn in (("UP", 0.0, 0.0), ("DN", 3.3, 3.3)):
        d = run(f"cp_{c}_{mode}", f"""cp {c}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs(lib)}
.include "{CP}"
.temp {t}
Vdd VDD 0 3.3
Vu UPB 0 {upb}
Vd DN 0 {dn}
Ib VDD IB 2.5u
XCPD IB IB 0 0 nfet_03v3 w=1.12u l=1u
Vo OUT 0 1.5
X1 VDD 0 UPB DN IB OUT PB Charge_Pump_FE
.control
dc Vo 0 3.3 0.1
print v(out) i(vo)
.endc
.end
""")
        vo, io = d[:, -2], (-d[:, -1] if mode == "UP" else d[:, -1])
        inom = np.interp(1.5, vo, io)
        good = vo[np.abs(io - inom) < 0.1 * abs(inom)]
        print(f"   CP {mode}: {inom*1e6:.2f} uA at 1.5 V; within 10 % for OUT {good.min():.1f}..{good.max():.1f} V")
