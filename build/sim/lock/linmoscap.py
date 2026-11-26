#!/usr/bin/env python3
"""Copy of an extracted netlist with every cap_nmos_03v3 replaced by a linear capacitor at its inversion value
(3.983 fF/um^2, times the PDK corner factor).  The closed-loop runs need tran tmax 0.5 ns for the TSPC PFD; at that
step the PDK's tanh C(V) moscap model aborts with "timestep too small".  The loop-filter MOS caps sit far above
threshold at lock (VCTRL 0.6-2.8 V), so the linear model matches there.
    python3 linmoscap.py IN.spice OUT.spice "header comment"
"""
import sys

src, dst = sys.argv[1:3]
note = sys.argv[3] if len(sys.argv) > 3 else src
hdr = (f"* {note} with cap_nmos_03v3 replaced by a linear capacitor at its inversion value (3.983 fF/um^2)\n"
       ".subckt cap_nmos_lin 1 2 c_length=1u c_width=1u\n"
       "C1 1 2 {cap_nmos_03v3_corner*c_length*c_width*0.003983}\n"
       ".ends cap_nmos_lin\n")
txt = open(src).read().replace(" cap_nmos_03v3 ", " cap_nmos_lin ")
open(dst, "w", newline="\n").write(hdr + txt)
