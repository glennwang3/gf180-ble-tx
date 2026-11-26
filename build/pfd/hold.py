#!/usr/bin/env python3
"""Hold time of the extracted R_FlipFlop: Q=1 first, then D low for a clock, then at the 60 ns clock edge D rises
delta ns after CLK.  Q must read 0 after that edge; the smallest passing delta is the hold time.
    python3 hold.py CELLNETLIST SUBCKT 'pin order with D CLK Q placeholders'"""
import os, subprocess, re
NET = "/foss/designs/pll_compact/tspc_check/lvsRf/R_FlipFlop_lvs.spice"
INST = "X1 d clk 0 n2 n5 qb q v 0 R_FlipFlop"
os.makedirs("/foss/designs/pll_compact/pfd/sim/hold", exist_ok=True)
os.chdir("/foss/designs/pll_compact/pfd/sim/hold")
open(".spiceinit", "w").write("set ngbehavior=hsa\n")
for corner, lib, temp in (("tt27", "typical", 27), ("ss125", "ss", 125), ("ff-40", "ff", -40)):
    row = []
    for dl in (0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0):
        deck = f"""R_FlipFlop hold {corner} {dl}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {lib}
.include "{NET}"
.temp {temp}
Vdd v 0 3.3
Vclk clk 0 PULSE(0 3.3 10n 0.2n 0.2n 10n 50n)
Vd d 0 PWL(0 3.3 30n 3.3 30.2n 0 60n 0 {60 + dl:.2f}n 0 {60.2 + dl:.2f}n 3.3)
Cl q 0 10f
{INST}
.control
tran 5p 75n
meas tran q1 find v(q) at=25n
meas tran q2 find v(q) at=74n
quit
.endc
.end
"""
        open("h.sp", "w").write(deck)
        o = subprocess.run("ngspice -b h.sp", shell=True, capture_output=True, text=True).stdout
        v = dict(re.findall(r"^(q[12])\s*=\s*([-0-9.eE+]+)", o, re.M))
        row.append(f"{dl}ns:Q1={float(v.get('q1', 'nan')):.1f}/Q2={float(v.get('q2', 'nan')):.1f}")
    print(corner, "  ".join(row))
