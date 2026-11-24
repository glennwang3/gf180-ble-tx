#!/usr/bin/env python3
"""(1) Miller-zero resistor RZERO sweep: main loop REF->VOUT peaking / bandwidth at VOUT 1.83 (FF/-40), 2.35 (TT),
3.19 V (SS/125) with REF forced through the setpoint (VCTRL chosen per point); (2) input-buffer bandwidth vs VCTRL
at FF/-40 and SS-40."""
import re
import subprocess
REG = "/foss/designs/pll_compact/layout/VCO_REG_L.spice"
base = open(REG).read()


def libs(lib):
    return "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                     for x in (lib, "res_" + lib, "mimcap_" + lib, "moscap_" + lib, "cap_mim"))


def run(tag, lib, t, vc, rl, rz_len, probe):
    net = re.sub(r"(XRZERO_0 DRIVE COMP VSS ppolyf_u_1k r_width=1u r_length=)[0-9.]+u", rf"\g<1>{rz_len}u", base)
    open(f"{tag}.net", "w").write(net)
    deck = f'''x
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs(lib)}
.include "{tag}.net"
.temp {t}
Vin VIN 0 3.3
Vc VCTRL 0 dc {vc} ac 1
X1 VIN VCTRL VOUT 0 VCO_REG_L
Rl VOUT 0 {rl}
Cl VOUT 0 2p
.control
op
print v(vout)
ac dec 40 10 200meg
let m = db({probe})
meas ac m0 find m at=10
meas ac mpk max m
let m3 = m - m0 + 3
meas ac f3 when m3=0 fall=1
.endc
.end
'''
    open(f"{tag}.sp", "w").write(deck)
    open(".spiceinit", "w").write("set ngbehavior=hsa\n")
    out = subprocess.run(f"ngspice -b {tag}.sp", shell=True, capture_output=True, text=True).stdout
    g = {}
    for l in out.splitlines():
        s = l.strip()
        for k in ("v(vout)", "m0", "mpk", "f3"):
            if s.startswith(k + " ") or s.startswith(k + "="):
                g[k] = float(s.split("=")[1].split()[0])
    return g


PTS = [("ff-40", "ff", -40, 0.40, 1.8e3), ("tt27", "typical", 27, 1.27, 2.8e3), ("ss125", "ss", 125, 2.68, 2.8e3)]
for rz in (2.2e3, 6.8e3, 15e3, 33e3):
    L = round((rz - 176.1) / 1030.5, 2)
    row = []
    for c, lib, t, vc, rl in PTS:
        g = run(f"rz_{c}", lib, t, vc, rl, L, "v(vout)/v(x1.ref)")
        row.append(f"{c} VOUT {g['v(vout)']:.2f}: f3 {g['f3']/1e3:8.1f} kHz pk {g['mpk']-g['m0']:5.2f} dB")
    print(f"RZERO {rz/1e3:4.1f}k | " + " | ".join(row), flush=True)
for c, lib, t in (("ff-40", "ff", -40), ("ss-40", "ss", -40), ("tt27", "typical", 27)):
    row = []
    for vc in (0.4, 0.55, 0.7, 0.85, 1.0):
        g = run(f"bf_{c}", lib, t, vc, 2.8e3, 1.96, "v(x1.buf)/v(vctrl)")
        row.append(f"{vc:.2f} V: {g['f3']/1e3:7.1f} kHz")
    print(f"buffer -3 dB {c}: " + ", ".join(row), flush=True)
