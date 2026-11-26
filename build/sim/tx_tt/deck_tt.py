#!/usr/bin/env python3
"""TT/27 transmit decks for the E03 (low-cap Schottky VCO) RF path, transistor level after PEX:
delivered VCO + prescaler RC-PEX minus the doubler's 2nd / 3rd inverters (= E03 VCO_LC, sim/lowcap/ctt/net.spice)
+ extracted RF_CHAIN_PA + class-C PA network (pad, bond wire, off-chip tank, 100 ohm), as sim/power/rfsplit.py.
VDD_VCO is an ideal source at the TT channel-0 lock value (2.3295 V, sim/lock/tt2_ch0) - the TT regulator starts up
slowly from the DC operating point (VDD_VCO 2.07 -> 2.34 V over ~200 ns), which would swamp a 250 kHz deviation;
the closed-loop run (tx_loop_tt.py) covers the regulator and loop.
    python3 deck_tt.py TAG VTUNE|pwl:FILE TSTOP_ns [lite]
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VDDVCO, TAIL = float(os.environ.get("VDDVCO", "2.3295")), float(os.environ.get("TAIL", "1.686"))
CORNER = os.environ.get("CORNER", "tt27")                 # tt27 | ff-40 | ss125 (TAIL: biasop.py value)
LIB, TEMP = {"tt27": ("typical", 27), "ff-40": ("ff", -40), "ss125": ("ss", 125)}[CORNER]
tag, vt, tstop = sys.argv[1:4]
lite = len(sys.argv) > 4 and sys.argv[4] == "lite"
if vt.startswith("pwl:"):
    vdac = "Vdac DAC 0 PWL(" + " ".join(open(vt[4:]).read().split()) + ")"
else:
    vdac = f"Vdac DAC 0 {vt}"
libs = chr(10).join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}' for x in
                    (LIB, "diode_" + LIB, "res_" + LIB, "mimcap_" + LIB, "moscap_" + LIB, "cap_mim"))
sv = "v(o1p) v(o1n) v(out) v(vtune) i(vmain) i(vch) i(vpa) i(vvco)" + ("" if lite else " v(drain) v(d1) v(core_clk)")
# LPF=1: off-chip 5th-order 0.1 dB Chebyshev low-pass (100 ohm, ripple edge 2.6 GHz) between the DC block and the load
LPF_NET = ("CDC board o0 20p\nCF1 o0 0 0.702p\nLF2 o0 o1 8.39n\nCF3 o1 0 1.209p\nLF4 o1 out 8.39n\nCF5 out 0 0.702p\n"
           if os.environ.get("LPF") == "1" else "CDC board out 20p\n")
deck = f"""E03 {CORNER} transmit, VDD_VCO {VDDVCO} (ideal), VTUNE {vt}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "/foss/designs/pll_compact/sim/lowcap/ctt/net.spice"
.include "/foss/designs/pll_compact/layout/pex_chainc/RF_CHAIN_PA_rcpex.spice"
.temp {TEMP}
.options method=gear reltol=2e-4 abstol=1e-12 vntol=1e-6 itl4=80 rshunt=1e12
Vmain VDD 0 3.3
Vch VDDCH 0 3.3
Vvco VDD_VCO 0 {VDDVCO}
Vtail TAIL_BIAS 0 {TAIL}
Vmode MC 0 3.3
* DAC -> VTUNE: 50 ohm output resistance into the VCO's VTUNE node
{vdac}
Rdac DAC VTUNE 50
Xdut rf_out TAIL_BIAS VTUNE VDD_VCO 0 VDD CORE_CLK PRESCALED MC O1P O1N O2N O3N O4P O4N DOUBLER_K MIM_TOP O2P O3P PLL_PEX
Cdig PRESCALED 0 6f
CRFW rf_out 0 1.5f
XCH drain rf_out d1 0 VDDCH RF_CHAIN_PA_FLAT
CPAD drain 0 1.5p
LBW drain bw 1.2n
RBW bw board 0.2
LT board vpa_l 1.70n
RLT vpa_l vpa 0.3
VPA vpa 0 1.5
CT board 0 0.10p
{LPF_NET}RLOAD out 0 100
.ic V(O1P)=2.2 V(O1N)=1.0
.control
set noaskquit
set num_threads=1
set filetype=binary
save {sv}
tran 4p {tstop}n 0 4p
write wave.raw {sv}
quit
.endc
.end
"""
d = os.path.join(HERE, tag)
os.makedirs(d, exist_ok=True)
open(os.path.join(d, "t.sp"), "w", newline="\n").write(deck)
open(os.path.join(d, ".spiceinit"), "w", newline="\n").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=d)
print(tag, "done")
