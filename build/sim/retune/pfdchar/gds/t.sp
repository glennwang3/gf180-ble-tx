pfd char
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" ss
.include "/foss/designs/pll_compact/layout/lvs_top/ref_pfd/M_pfd.spice"
.include "/foss/designs/pll_compact/layout/lvs_top/ref_pump/M_pump.spice"
.temp 125
VDD VDD 0 3.3
IREF 0 CP_IBIAS 2.5u
VREF REF 0 PULSE(0 3.3 0 1n 1n 499n 1u)
VFB FB 0 PULSE(0 3.3 2.5e-07 1n 1n 4.9900e-07 1u)
XPFD VDD 0 REF UP DN FB UPB DNB NDN NUP M_pfd
XPUMP VDD 0 UPB DN CP_IBIAS VCTRL PB M_pump
VC VCTRL 0 1.4
.control
set noaskquit
tran 1n 4u 0 2n
let icp = -i(vc)
meas tran iavg avg icp from=2u to=4u
quit
.endc
.end
