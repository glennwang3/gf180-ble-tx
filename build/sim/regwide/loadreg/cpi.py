#!/usr/bin/env python3
"""Average charge-pump current into VCTRL (held at 1.43 V) on the extracted LOOP_PART at TT, for a feedback clock
lagging / leading the 1 MHz reference by 0.4 us."""
import subprocess
for tag, dly in (("fb_lag", 0.4), ("fb_lead", 0.6)):
    deck = f"""cp current {tag}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" res_typical
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" mimcap_typical
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" moscap_typical
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" cap_mim
.include "/foss/designs/pll_compact/layout/pex_loop/LOOP_PART_rcpex.spice"
.temp 27
.options method=gear reltol=1e-3 abstol=1e-12 rshunt=1e12
Vdd VDD 0 3.3
Vref REF 0 PULSE(0 3.3 0 1n 1n 499n 1u)
Vfb FB 0 PULSE(0 3.3 {dly}u 1n 1n 499n 1u)
XL VDD_VCO VDD 0 UPB DN IB TB REF FB VCTRL LOOP_PART
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
RVCO VDD_VCO 0 2700
Vc VCTRL 0 1.43
.control
set noaskquit
tran 2n 14u 0 4n
meas tran iavg avg i(vc) from=4u to=14u
meas tran ipk max i(vc) from=4u to=14u
meas tran imn min i(vc) from=4u to=14u
meas tran dnw avg v(dn) from=4u to=14u
meas tran upw avg v(upb) from=4u to=14u
quit
.endc
.end
"""
    open(f"{tag}.sp", "w").write(deck)
    out = subprocess.run(f"ngspice -b {tag}.sp", shell=True, capture_output=True, text=True).stdout
    vals = {l.split("=")[0].strip(): l.split("=")[1].split()[0] for l in out.splitlines()
            if l.strip().split(" ")[0] in ("iavg", "ipk", "imn", "dnw", "upw") and "=" in l}
    print(tag, vals, flush=True)
