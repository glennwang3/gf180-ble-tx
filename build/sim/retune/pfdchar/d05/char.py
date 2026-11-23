#!/usr/bin/env python3
"""A01 PFD + CP (their CPEX netlists), SS/125, ideal IBIAS, VCTRL held at 1.4 V.  REF 1 MHz; FB = REF delayed by
theta (static).  Prints the average CP output current per theta.   python3 char.py IBIAS_uA DUTY_FB"""
import subprocess, sys
ib, duty = float(sys.argv[1]), float(sys.argv[2])
A = "/foss/designs/pll_integration_repo/PLL/analog"
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}' for x in ("ss",))
rows = []
for k in range(-12, 13):
    th = k / 24.0                         # FB delay in REF periods (positive = FB lags = VCO slow)
    td = (th % 1.0) * 1e-6
    deck = f"""pfd char
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "{A}/phase_detector/Phase_Detector_FE_CPEX.spice"
.include "{A}/charge_pump/Charge_Pump_FE_CPEX.spice"
.temp 125
VDD VDD 0 3.3
IREF 0 CP_IBIAS {ib}u
VREF REF 0 PULSE(0 3.3 0 1n 1n 499n 1u)
VFB FB 0 PULSE(0 3.3 {td} 1n 1n {duty*1e-6 - 1e-9:.4e} 1u)
XPFD VDD 0 REF FB UP DN UPB DNB Phase_Detector_FE_PEX
XPUMP VDD 0 UPB DN CP_IBIAS VCTRL Charge_Pump_FE_PEX
VC VCTRL 0 1.4
.control
set noaskquit
tran 0.5n 6u 0 1n
let icp = -i(vc)
meas tran iavg avg icp from=3u to=6u
quit
.endc
.end
"""
    open("t.sp", "w").write(deck)
    out = subprocess.run("ngspice -b t.sp 2>&1", shell=True, capture_output=True, text=True).stdout
    v = [l for l in out.splitlines() if l.strip().startswith("iavg")]
    i = float(v[0].split("=")[1].split()[0]) if v else float("nan")
    rows.append((th, i))
    print(f"theta {th:+.3f} T  ({th*360:+6.0f} deg): Iavg {i*1e6:+7.3f} uA", flush=True)
