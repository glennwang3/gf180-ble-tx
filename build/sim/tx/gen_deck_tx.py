#!/usr/bin/env python3
"""Post-layout RF deck (pex_rf/RF_PART_rcpex.spice, re-extracted after the VIN fix) for output power and data.
Same partition and PA network as sim/gen_deck_top.py, with VTUNE either constant or a PWL file.
    python3 gen_deck_tx.py TAG CORNER VCTRL VTUNE|pwl:FILE TSTOP_ns [full|lite]
'lite' saves only what the long data run needs (RF, load, VTUNE, VDD_VCO, supply currents).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NET = "/foss/designs/pll_compact/layout/pex_rf/RF_PART_rcpex.spice"
CORNERS = {"ss125": ("ss", 125), "tt27": ("typical", 27), "ff-40": ("ff", -40)}
tag, corner, vctrl, vt, tstop = sys.argv[1:6]
mode = sys.argv[6] if len(sys.argv) > 6 else "full"
lib, temp = CORNERS[corner]
ports = re.search(r"^\.subckt RF_PART (.*?)\n(?!\+)", re.sub(r"\n\+", " ", open(
    NET.replace("/foss/designs", os.path.join(HERE, "..", "..", ".."))).read()), re.M | re.S).group(1).split()
conn = {"VSS": "0", "XP": "xp", "XN": "xn", "D1": "d1", "PA_DRAIN": "drain"}
d = os.path.join(HERE, tag)
os.makedirs(d, exist_ok=True)
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}' for x in
                 (lib, "diode_" + lib, "res_" + lib, "mimcap_" + lib, "moscap_" + lib, "cap_mim"))
if vt.startswith("pwl:"):
    pts = open(vt[4:]).read().split()
    vdac = "Vdac DAC 0 PWL(" + " ".join(pts) + ")"
else:
    vdac = f"Vdac DAC 0 {vt}"
LC = "RF_DRV1" in ports                          # low-cap Schottky VCO + RF_CHAIN_PA partition
if mode == "full":
    saves = ("v(o1p) v(o1n) " + ("v(mim_top) v(rf_drv1) " if LC else "v(xp) v(xn) v(rf_out) ") +
             "v(d1) v(drain) v(out) v(vtune) v(dac) v(vdd_vco) v(tail_bias) v(core_clk) v(prescaled) i(vpa) i(vmain)")
else:
    saves = "v(o1p) v(o1n) v(out) v(vtune) v(dac) v(vdd_vco) i(vpa) i(vmain)"
deck = f"""PLL_COMPACT RF partition (post VIN fix), {corner}, VCTRL {vctrl} V, VTUNE {vt}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "{NET}"
.temp {temp}
.options method=gear reltol=0.0002 abstol=1e-12 vntol=1e-6 itl4=80 rshunt=1e12
Vmain VDD 0 3.3
Xdut {' '.join(conn.get(p, p) for p in ports)} RF_PART
Vct VCTRL 0 {vctrl}
{vdac}
* DAC output resistance + VTUNE filter pole (about 30 MHz)
Rdac DAC VTUNE 50
{"" if LC else "Crf RF_OUT 0 3f"}
Cdigital PRESCALED 0 6f
Vmode MC 0 3.3
XCPD CP_IBIAS CP_IBIAS 0 0 nfet_03v3 w=1.12u l=1u
* class-C PA output network (pad, bond wire, off-chip tank), as in sim/gen_deck_top.py
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
save {saves}
tran 4p {tstop}n 0 4p
write wave.raw {saves}
quit
.endc
.end
"""
open(os.path.join(d, "test.spice"), "w", newline="\n").write(deck)
open(os.path.join(d, ".spiceinit"), "w", newline="\n").write("set ngbehavior=hsa\n")
print(d)
