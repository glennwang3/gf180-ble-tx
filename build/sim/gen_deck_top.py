#!/usr/bin/env python3
"""
Post-layout deck for the integrated PLL_COMPACT RF / supply partition (pex_rf/RF_PART_rcpex.spice):
v3 VCO + XOR + converter/PA + prescaler + regulator + bias block, all extracted with their top-level routing.
  * VDD_VCO comes from the extracted regulator (VCTRL held at a fixed value - the loop is open here)
  * TAIL_BIAS comes from the extracted bias mirror (the charge pump's IBIAS diode is its load)
  * PA drain -> pad / bond wire / off-chip tank (R_L = 100 ohm, VPA = 1.5 V), as in the earlier runs
    python3 gen_deck_top.py CORNER VCTRL [MC_SEED]      (CORNER: ss125 | tt27 | ff-40)
"""
import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
NET = "/foss/designs/pll_compact/layout/pex_rf/RF_PART_rcpex.spice"
CORNERS = {"ss125": ("ss", 125), "tt27": ("typical", 27), "ff-40": ("ff", -40)}
corner, vctrl = sys.argv[1], sys.argv[2]
seed = sys.argv[3] if len(sys.argv) > 3 else None
lib, temp = CORNERS[corner]
l2 = lib
ports = re.search(r"^\.subckt RF_PART (.*?)\n(?!\+)", re.sub(r"\n\+", " ", open(
    NET.replace("/foss/designs", os.path.join(HERE, "..", ".."))).read()), re.M | re.S).group(1).split()
conn = {"VSS": "0", "XP": "xp", "XN": "xn", "D1": "d1", "PA_DRAIN": "drain"}
tag = f"run_{corner}_vc{vctrl}" + (f"_mc{seed}" if seed else "") + "_RL100_VPA1.5"
d = os.path.join(HERE, tag)
os.makedirs(d, exist_ok=True)
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}' for x in
                 (lib, "diode_" + l2, "res_" + l2, "mimcap_" + l2, "moscap_" + l2, "cap_mim"))
saves = ("v(o1p) v(o1n) v(o2p) v(o2n) v(o3p) v(o3n) v(o4p) v(o4n) v(xp) v(xn) v(d1) v(drain) v(out) v(rf_out) "
         "v(vdd_vco) v(tail_bias) v(cp_ibias) v(core_clk) v(prescaled) i(vpa) i(vmain) i(vct)")
deck = f"""PLL_COMPACT RF/supply partition, {corner}, VCTRL {vctrl} V{', MC seed ' + seed if seed else ''}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "{NET}"
{'.param sw_stat_mismatch=1' if seed else ''}
.temp {temp}
.options method=gear reltol=0.0002 abstol=1e-12 vntol=1e-6 itl4=80 rshunt=1e12
Vmain VDD 0 3.3
Xdut {' '.join(conn.get(p, p) for p in ports)} RF_PART
Vct VCTRL 0 {vctrl}
Vdac DAC 0 PWL(0 .48402 15n .48402 75n 0.54)
Rdac DAC VTUNE 50
Crf RF_OUT 0 3f
Cdigital PRESCALED 0 6f
Vmode MC 0 3.3
* charge-pump IBIAS input (diode NMOS 1.12/1) as the bias block's load
XCPD CP_IBIAS CP_IBIAS 0 0 nfet_03v3 w=1.12u l=1u
* class-C PA output network (pad, bond wire, off-chip tank)
CPAD drain 0 1.5p
LBW drain bw 1.2n
RBW bw board 0.2
LT board vpa_l 1.70n
RLT vpa_l vpa 0.3
VPA vpa 0 1.5
CT board 0 0.10p
CDC board out 20p
RLOAD out 0 100
.ic V(O1P)=1.65181346 V(O1N)=1.07347852 V(O2P)=2.96487776 V(O2N)=0.78705923
.ic V(O3P)=0.171662657 V(O3N)=3.0913842 V(O4P)=2.85100618 V(O4N)=0.0936726558
.control
set noaskquit
set num_threads=1
set filetype=binary
{('setseed ' + seed + chr(10) + 'mc_source') if seed else ''}
save {saves}
tran 4p 277n 0 4p
write wave.raw {saves}
quit
.endc
.end
"""
open(os.path.join(d, "test.spice"), "w", newline="\n").write(deck)
open(os.path.join(d, ".spiceinit"), "w", newline="\n").write("set ngbehavior=hsa\n")
open(os.path.join(d, "gate_node.txt"), "w").write("d1\n")
print(d)
