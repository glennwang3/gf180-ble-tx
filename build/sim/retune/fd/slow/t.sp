fd slow
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" res_ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" mimcap_ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" moscap_ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" cap_mim
.include "/foss/designs/pll_compact/layout/pex_loop/LOOP_PART_rcpex.spice"
.temp 125
.options method=gear reltol=1e-3 abstol=1e-12 vntol=1e-6
Vdd VDD 0 3.3
Vref REF 0 PULSE(0 3.3 0 1n 1n 499n 1u)
XL VDD_VCO VDD 0 UPB DN IB TB REF FB VCTRL LOOP_PART
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
RVCO VDD_VCO 0 1580
BFB FB 0 V = 1.65 + 1.65*tanh(30*sin(6.283185307*975000.0*time - 1.0))
Vc VCTRL 0 1.4
.control
set noaskquit
tran 2n 82.0u 0 4n
let icp = -i(vc)
meas tran iavg avg icp from=2u to=82.0u
wrdata out.txt icp
quit
.endc
.end
