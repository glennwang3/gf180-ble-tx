#!/usr/bin/env python3
"""PLL bias block v2 (schematic): resistor-referenced PMOS mirror.
   VDD - MPD (diode, PG) - Rref (ppolyf_u_1k, NR segments) - VSS   -> I_ref = (VDD - VSG)/Rref ~ 10 uA
   MPCP x2 -> 20 uA sourced into the charge-pump IBIAS diode;  MPT x1 -> tail diode (0.36/LT) -> TAIL_BIAS
python3 bias2.py NR LSEG LT"""
import subprocess, sys
NR, LSEG, LT = int(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
WT = sys.argv[4] if len(sys.argv) > 4 else "0.36"
def sub():
    s = [".subckt PLL_BIAS VDD VSS IBIAS TAIL_BIAS",
         "XMPD PG PG VDD VDD pfet_03v3 w=4u l=2u"]
    nodes = ["PG"] + [f"r{i}" for i in range(1, NR)] + ["VSS"]
    s += [f"XR{i} {nodes[i]} {nodes[i+1]} VSS ppolyf_u_1k r_width=1u r_length={LSEG}u" for i in range(NR)]
    s += ["XMCP0 IBIAS PG VDD VDD pfet_03v3 w=4u l=2u", "XMCP1 IBIAS PG VDD VDD pfet_03v3 w=4u l=2u",
          "XMT TAIL_BIAS PG VDD VDD pfet_03v3 w=4u l=2u",
          f"XMTD TAIL_BIAS TAIL_BIAS VSS VSS nfet_03v3 w={WT}u l={LT}u",
          "XCT TAIL_BIAS VSS cap_nmos_03v3 c_width=10u c_length=6u",
          ".ends PLL_BIAS"]
    return "\n".join(s)
C = {"tt27": ("typical", "typical", 27), "ss125": ("ss", "ss", 125), "ff-40": ("ff", "ff", -40),
     "ss-40": ("ss", "ss", -40), "ff125": ("ff", "ff", 125), "tt125": ("typical", "typical", 125), "tt-40": ("typical", "typical", -40),
     "ss/resff125": ("ss", "ff", 125), "ff/resss-40": ("ff", "ss", -40)}
def run(corner, vdd):
    m, r, t = C[corner]
    deck = f"""bias
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {m}
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" res_{r}
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" moscap_{m}
.temp {t}
{sub()}
Vdd VDD 0 {vdd}
X1 VDD 0 IBO TB PLL_BIAS
Vcp IBO IB 0
XCPD IB IB 0 0 nfet_03v3 w=1.12u l=1u
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
Vtd TD 0 1.0
.control
set noaskquit
op
print v(tb)
print i(vcp)
print i(vtd)
print i(vdd)
print v(ib)
quit
.endc
.end"""
    open("b2.sp", "w").write(deck)
    out = subprocess.run(["ngspice", "-b", "b2.sp"], capture_output=True, text=True).stdout
    v = {}
    for l in out.splitlines():
        if " = " in l:
            v[l.split("=")[0].strip()] = float(l.split("=")[1].split()[0])
    return v
print(f"Rref {NR} x {LSEG} um, tail diode 0.36/{LT}")
for corner in C:
    for vdd in ((3.0, 3.3, 3.6) if corner == "tt27" else (3.3,)):
        v = run(corner, vdd)
        print(f"{corner:12s} VDD {vdd}: TAIL_BIAS {v['v(tb)']:.3f} V   I_CP {1e6*v['i(vcp)']:6.2f} uA (IBIAS {v['v(ib)']:.2f} V)"
              f"   I_tail {-1e6*v['i(vtd)']:6.1f} uA   I_bias_block {-1e6*v['i(vdd)'] + 1e6*v['i(vtd)']:5.1f} uA")
