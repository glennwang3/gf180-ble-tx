#!/usr/bin/env python3
"""PLL bias block (schematic): beta-multiplier reference + PMOS mirrors -> 20 uA into CP IBIAS and a
diode-generated 1.7 V TAIL_BIAS.  python3 bias.py [Rs_seg_len] -> DC table over corners + startup."""
import subprocess, sys, os
LS = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0     # Rs: 3 x LS um ppolyf_u_1k segments
NT = sys.argv[2] if len(sys.argv) > 2 else "1"
LT = sys.argv[3] if len(sys.argv) > 3 else "2"             # tail diode units (0.36/2 each, parallel)
SUB = f"""
.subckt PLL_BIAS VDD VSS IBIAS TAIL_BIAS
* reference: MN1 diode (1x), MN2 (4x) + Rs, PMOS 1:1
XMPA NG PG VDD VDD pfet_03v3 w=4u l=2u
XMPB PG PG VDD VDD pfet_03v3 w=4u l=2u
XMN1 NG NG VSS VSS nfet_03v3 w=2u l=2u
XMN2_0 PG NG RS VSS nfet_03v3 w=2u l=2u
XMN2_1 PG NG RS VSS nfet_03v3 w=2u l=2u
XMN2_2 PG NG RS VSS nfet_03v3 w=2u l=2u
XMN2_3 PG NG RS VSS nfet_03v3 w=2u l=2u
XRS0 RS r1 VSS ppolyf_u_1k r_width=1u r_length={LS}u
XRS1 r1 r2 VSS ppolyf_u_1k r_width=1u r_length={LS}u
XRS2 r2 VSS VSS ppolyf_u_1k r_width=1u r_length={LS}u
* start-up
XMS1 X VSS VDD VDD pfet_03v3 w=0.36u l=6u
XMS2 X NG VSS VSS nfet_03v3 w=2u l=1u
XMS3 PG X VSS VSS nfet_03v3 w=0.36u l=1u
* outputs
XMCP0 IBIAS PG VDD VDD pfet_03v3 w=4u l=2u
XMCP1 IBIAS PG VDD VDD pfet_03v3 w=4u l=2u
XMT TAIL_BIAS PG VDD VDD pfet_03v3 w=4u l=2u
""" + "".join(f"XMTD{i} TAIL_BIAS TAIL_BIAS VSS VSS nfet_03v3 w=0.36u l=2u\n" for i in range(int(NT))) + """XCT TAIL_BIAS VSS cap_nmos_03v3 c_width=10u c_length=6u
.ends PLL_BIAS
"""
C = {"tt27": ("typical", 27), "ss125": ("ss", 125), "ff-40": ("ff", -40), "ss-40": ("ss", -40), "ff125": ("ff", 125), "tt125": ("typical", 125)}
def run(corner, vdd, tran=False):
    lib, t = C[corner]
    l2 = lib
    deck = f"""bias
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {lib}
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" res_{l2}
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" moscap_{l2}
.temp {t}
{SUB}
Vdd VDD 0 {'PWL(0 0 10u ' + str(vdd) + ')' if tran else vdd}
X1 VDD 0 IBO TB PLL_BIAS
Vcp IBO IB 0
* charge-pump IBIAS input: diode NMOS 1.12/1
XCPD IB IB 0 0 nfet_03v3 w=1.12u l=1u
Vm IB2 0 0
* VCO tail device at TAIL_BIAS
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
Vtd TD 0 1.0
.control
set noaskquit
{'tran 50n 60u' if tran else 'op'}
{'meas tran tbf find v(tb) at=59u' if tran else ''}
{'meas tran icp find i(vdd) at=59u' if tran else ''}
{'' if tran else 'print v(tb)'}
{'' if tran else 'print i(vcp)'}
{'' if tran else 'print i(vtd)'}
{'' if tran else 'print i(vdd)'}
{'' if tran else 'print v(x1.ng)'}
{'' if tran else 'print v(x1.pg)'}
{'' if tran else 'print v(x1.x)'}
quit
.endc
.end"""
    open("b.sp", "w").write(deck)
    r = subprocess.run(["ngspice", "-b", "b.sp"], capture_output=True, text=True)
    vals = {}
    for l in r.stdout.splitlines():
        if "=" in l:
            k, v = l.split("=")[0].strip(), l.split("=")[1].split()[0]
            vals[k] = v
    return vals
if __name__ == "__main__":
    print(f"Rs = 3 x {LS} um, tail diodes {NT}")
    for corner in C:
        for vdd in (3.3,) if corner != "tt27" else (3.0, 3.3, 3.6):
            v = run(corner, vdd)
            g = lambda k: float(v.get(k, "nan"))
            print(f"{corner:6s} VDD {vdd}: TAIL_BIAS {g('v(tb)'):.3f} V  I_CP {1e6*g('i(vcp)'):6.2f} uA  I_tail(1u/0.28) {-1e6*g('i(vtd)'):6.1f} uA"
                  f"  I_VDD {-1e6*g('i(vdd)'):6.1f} uA  NG {g('v(x1.ng)'):.2f} PG {g('v(x1.pg)'):.2f} X {g('v(x1.x)'):.2f}")
    for corner in ("tt27", "ss125", "ff-40"):
        v = run(corner, 3.3, tran=True)
        print("startup", corner, v.get("tbf"))
