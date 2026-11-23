schematic regulator DC, SS/125, 1580 ohm load (v3 VCO)
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" res_ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" mimcap_ss
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" moscap_ss
.include "/foss/designs/vco_supply_regulator_3v3/VCO_Regulator_3V3_netlist.spice"
.include "/foss/designs/pll_compact/layout/VCO_REG_L.spice"
.temp 125
Vin VIN 0 3.3
Vc VCTRL 0 1.6
Xs VIN VCTRL VS 0 VCO_REG
Rs VS 0 1580
Xl VIN VCTRL VL 0 VCO_REG_L
Rl VL 0 1580
.control
set noaskquit
dc Vc 1.2 2.6 0.1
print v(vs) v(vl) v(xs.gate) v(xl.gate)
quit
.endc
.end
