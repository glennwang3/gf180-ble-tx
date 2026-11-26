#!/usr/bin/env python3
"""Post-PEX TS_PFD + A01 charge pump (Charge_Pump_FE_CPEX): net charge per reference period vs phase error.
UP -> inverter (0.56 / 1.12 um, L 0.28) -> UPb; DN direct.  IBIAS = 0.47 uA ideal (PLL_BIAS TT value); OUT held at
VCTRL by an ideal source (channel-0 point of the corner), so the charge per cycle is the integral of its current.
    python3 cpsim.py TAG CORNER DELAY_s [IBIAS_A] [VCTRL_V] [NETLIST]
Prints Q per cycle (fC, + = charge into the loop filter = UP) for periods 2..4 and the UP / DN pulse widths.
"""
import os
import subprocess
import sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw  # noqa: E402

CORNERS = {"ss125": ("ss", 125, 2.75, 0.39e-6), "tt27": ("typical", 27, 1.435, 0.466e-6), "ff-40": ("ff", -40, 0.65, 0.573e-6)}
tag, corner, delay = sys.argv[1], sys.argv[2], float(sys.argv[3])
lib, temp, vc, ib = CORNERS[corner]
ib = float(sys.argv[4]) if len(sys.argv) > 4 else ib
vc = float(sys.argv[5]) if len(sys.argv) > 5 else vc
net = sys.argv[6] if len(sys.argv) > 6 else "/foss/designs/pll_compact/pfd/lvs/TS_PFD_rcpex.spice"
fr, tr = 1e6, 0.2e-9
C1 = os.environ.get("LF")          # loop-filter mode: OUT drives Rz 440k + C2 143.6p in parallel with C1 (value in F)
NL = chr(10)
lf = (NL.join([f"Vout OUT OUTF 0", f"C1 OUTF 0 {C1}", "Rz OUTF NZ 440k", "C2 NZ 0 143.6p",
               f".ic v(OUTF)={vc} v(NZ)={vc}", ""]) if C1 else f"Vout OUT 0 {vc}" + NL)
pul = lambda td: f"PULSE(0 3.3 {td:.6e} {tr:.3e} {tr:.3e} {0.5 / fr - tr:.6e} {1 / fr:.6e})"
deck = f"""TS_PFD + charge pump {corner} delay {delay:.3g}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {lib}
.include "{net}"
.include "/foss/designs/pll_integration_repo/PLL/analog/charge_pump/Charge_Pump_FE_CPEX.spice"
.temp {temp}
.options method=gear reltol=1e-3 abstol=1e-14 vntol=1e-6 itl4=100
Vdd v33 0 3.3
Vra ra 0 {pul(12e-9 + max(0.0, -delay))}
Vva va 0 {pul(12e-9 + max(0.0, delay))}
Vpre pre 0 PULSE(0 3.3 2n {tr:.3e} {tr:.3e} 3n 1)
BR R 0 V = max(v(ra), v(pre))
BV V 0 V = max(v(va), v(pre))
X1 R V UPBO DN v33 0 UP TS_PFD_FLAT
XIP UPB UP v33 v33 pfet_03v3 w=1.12u l=0.28u
XIN UPB UP 0 0 nfet_03v3 w=0.56u l=0.28u
Iib v33 IBIAS {ib}
XCP v33 0 UPB DN IBIAS OUT Charge_Pump_FE_PEX
{lf}.control
set noaskquit
set num_threads=1
set filetype=binary
save v(up) v(dn) v(upb) i(vout) v(r) v(v) v(outf)
tran 5p 4.6u 0 20p
write wave.raw v(up) v(dn) v(upb) i(vout) v(r) v(v) {'v(outf)' if C1 else ''}
quit
.endc
.end
"""
os.makedirs(tag, exist_ok=True)
open(f"{tag}/t.sp", "w", newline="\n").write(deck)
open(f"{tag}/.spiceinit", "w", newline="\n").write("set ngbehavior=hsa\n")
if not os.environ.get("REUSE"):
    subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=tag)
w = read_raw(f"{tag}/wave.raw")
t = w["time"]
i_in = w["i(vout)"]                  # current the pump sources into OUT (+ terminal of Vout): + = UP / charging
q = []
for k in (1, 2, 3):                  # periods starting 5 ns before each test R/V edge pair
    a = 12e-9 + k / fr - 0.2e-6; b = a + 1 / fr
    m = (t >= a) & (t < b)
    q.append(np.trapezoid(i_in[m], t[m]))
up = w["v(up)"] > 1.65; dn = w["v(dn)"] > 1.65
m = t > 1e-6
wu = np.trapezoid(up[m].astype(float), t[m]) / 3.6
wd = np.trapezoid(dn[m].astype(float), t[m]) / 3.6
if C1:
    vo = w["v(outf)"]
    m = (t > 2.2e-6) & (t < 4.2e-6)
    print(f"  VCTRL ripple (C1 {C1}): p-p {np.ptp(vo[m])*1e3:.3f} mV, drift {(vo[m][-1]-vo[m][0])*1e3:+.3f} mV / 2 us")
print(f"{tag}: {corner} delay {delay*1e9:+.2f} ns (V lags R for +) | Q per cycle {np.mean(q)*1e15:+.3f} fC "
      f"(spread {np.ptp(q)*1e15:.3f}) | ideal Icp*dt {ib*delay*1e15:+.3f} fC | UP {wu*1e9:.2f} ns DN {wd*1e9:.2f} ns")
