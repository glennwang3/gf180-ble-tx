load regulation of the extracted regulator (LOOP_PART), TT
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" res_typical
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" mimcap_typical
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" moscap_typical
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" cap_mim
.include "/foss/designs/pll_compact/layout/pex_loop/LOOP_PART_rcpex.spice"
.temp 27
.options rshunt=1e12
Vdd VDD 0 3.3
XL VDD_VCO VDD 0 UPB DN IB TB REF FB VCTRL LOOP_PART
Vref REF 0 0
Vfb FB 0 0
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
Vc VCTRL 0 1.54
Iload VDD_VCO 0 0.5m
.control
set noaskquit
foreach il 0.3m 0.86m 1.5m 2.5m 4m
  alter Iload dc = $il
  op
  print v(vdd_vco)
end
quit
.endc
.end
