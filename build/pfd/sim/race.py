#!/usr/bin/env python3
"""Post-PEX TS_PFD near lock: is the closed-loop FF DN re-trigger (loop_ff_c1, 237 us) a circuit race or a time-step
artifact?  REF 1 MHz as in the loop deck; V from the loop's tanh(1000 sin) phase source, leading REF by
LEAD + AMP*sin(2 pi FM t) (300 cycles, leads spread over LEAD +- AMP), UPB / DN loaded with 15 fF (CP switch gates +
routing).  Counts cycles where DN re-asserts after the reset (DN high > 100 ns, or a 2nd DN rising edge).
    python3 race.py TAG TMAX [corner] [LEAD_ns] [AMP_ns] [T_us]
env MODE=loop: the PFD inside the extracted LOOP_PART (pex_loop_ts_c1, linear moscaps) with VCTRL held (VCTRL=0.6307,
RVCO=2990: the FF lock values); REUSE=1: analyse an existing TAG/wave.raw without simulating.
"""
import os
import subprocess
import sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw  # noqa: E402

tag, tmax = sys.argv[1], sys.argv[2]
corner = sys.argv[3] if len(sys.argv) > 3 else "ff"
lead = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
amp = float(sys.argv[5]) if len(sys.argv) > 5 else 0.15
T = float(sys.argv[6]) if len(sys.argv) > 6 else 300
lib, temp = {"tt": ("typical", 27), "ss": ("ss", 125), "ff": ("ff", -40)}[corner]
ph0 = 0.159155 + lead * 1e-3                     # V edge where 2 pi ph - 1 = 2 pi k  ->  t = k us - lead
# MODE=loop: the PFD inside the extracted loop partition (routed supplies, real charge pump), VCTRL held at VCTRL
if os.environ.get("MODE") == "loop":
    libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}'
                     for x in (lib, "res_" + lib, "mimcap_" + lib, "moscap_" + lib, "cap_mim"))
    dut = (f'{libs}\n.include "/foss/designs/pll_compact/layout/pex_loop_ts_c1/LOOP_PART_rcpex_ff_lin.spice"\n'
           "XL VDD_VCO v33 0 UPB DN IB TB R V VCTRL LOOP_PART\n"
           f"VC VCTRL 0 {os.environ.get('VCTRL', '0.6307')}\nRVCO VDD_VCO 0 {os.environ.get('RVCO', '2990')}\n"
           "XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u\nVTD TD 0 1.0\n")
else:
    dut = (f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {lib}\n'
           '.include "/foss/designs/pll_compact/pfd/lvs/TS_PFD_rcpex.spice"\n'
           "X1 R V UPB DN v33 0 UP TS_PFD_FLAT\nCUB UPB 0 15f\nCD DN 0 15f\nCU UP 0 5f\n")
deck = f"""race {tag}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{dut}
.temp {temp}
.options method=gear reltol=1e-3 abstol=1e-12 vntol=1e-6 itl4=100
Vdd v33 0 3.3
Vr R 0 PULSE(0 3.3 0 0.3n 0.3n 499n 1u)
BV V 0 V = 1.65 + 1.65*tanh(1000*sin(6.283185307*(1e6*time + {ph0:.7f} + {amp*1e-3:.3e}*sin(6.283185307*61.8e3*time)) - 1.0))
.control
set noaskquit
set num_threads=1
set filetype=binary
save v(dn) v(upb)
tran 0.5n {T}u 0 {tmax}
write wave.raw v(dn) v(upb)
quit
.endc
.end
"""
os.makedirs(tag, exist_ok=True)
open(f"{tag}/t.sp", "w", newline="\n").write(deck)
open(f"{tag}/.spiceinit", "w", newline="\n").write("set ngbehavior=hsa\n")
if not (os.environ.get("REUSE") == "1" and os.path.exists(f"{tag}/wave.raw")):   # REUSE=1: analyse the last run
    subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=tag)
w = read_raw(f"{tag}/wave.raw")
t, dn, upb = w["time"], w["v(dn)"] > 1.65, w["v(upb)"] < 1.65
rise = t[1:][dn[1:] & ~dn[:-1]]
bad = []
for k in range(2, int(T)):                       # cycle k: V edge ~k us - lead, REF edge k us
    m = (t >= (k - 0.5) * 1e-6) & (t < (k + 0.5) * 1e-6)
    hi = np.trapezoid(dn[m].astype(float), t[m])
    nr = np.count_nonzero((rise >= (k - 0.5) * 1e-6) & (rise < (k + 0.5) * 1e-6))
    ld = lead + amp * np.sin(2 * np.pi * 61.8e3 * k * 1e-6)
    if hi > 100e-9 or nr != 1:
        bad.append((k, ld, hi * 1e9, nr))
print(f"{tag} ({corner}, tmax {tmax}, lead {lead - amp:.2f}-{lead + amp:.2f} ns): {len(bad)} bad cycles of {int(T) - 2}")
for k, ld, hi, nr in bad[:12]:
    print(f"   cycle {k}: lead {ld:.4f} ns, DN high {hi:.1f} ns, DN rising edges {nr}")
