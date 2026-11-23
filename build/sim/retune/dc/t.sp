VCTRL -> VDD_VCO, post-PEX LOOP_PART, SS/125
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" res_ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" mimcap_ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" moscap_ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" cap_mim
.include "/foss/designs/pll_compact/layout/pex_loop/LOOP_PART_rcpex.spice"
.temp 125
Vdd VDD 0 3.3
Vref REF 0 0
Vfb FB 0 0
XL VDD_VCO VDD 0 UPB DN IB TB REF FB VCTRL LOOP_PART
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
RVCO VDD_VCO 0 1580
Vc VCTRL 0 1.6
.control
set noaskquit
dc Vc 1.2 2.6 0.1
print v(vdd_vco) v(ib) v(tb) i(vdd)
quit
.endc
.end
