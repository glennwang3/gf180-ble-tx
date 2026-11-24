loop filter check on the extracted LOOP_PART (TT): PFD idle, 0.5 uA current step into VCTRL
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
XL VDD_VCO VDD 0 UPB DN IB TB REF FB VCTRL LOOP_PART
Vref REF 0 0
Vfb FB 0 0
XTAIL TD TB 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
RVCO VDD_VCO 0 2700
Iinj VCTRL 0 PULSE(0 0.5u 5u 1n 1n 100u 200u)
BPRE VCTRL 0 I = (time < 2u) ? (v(vctrl)-1.43)/1k : 0
.control
set noaskquit
tran 10n 40u 0 20n
meas tran v0 find v(vctrl) at=4.9u
meas tran v6 find v(vctrl) at=6u
meas tran v10 find v(vctrl) at=10u
meas tran v20 find v(vctrl) at=20u
meas tran v40 find v(vctrl) at=39.9u
quit
.endc
.end
