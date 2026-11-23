pfd char
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" ss
.include "/foss/designs/pll_integration_repo/PLL/analog/phase_detector/Phase_Detector_FE_CPEX.spice"
.include "/foss/designs/pll_integration_repo/PLL/analog/charge_pump/Charge_Pump_FE_CPEX.spice"
.temp 125
VDD VDD 0 3.3
IREF 0 CP_IBIAS 2.5u
VREF REF 0 PULSE(0 3.3 0 1n 1n 499n 1u)
VFB FB 0 PULSE(0 3.3 5.833333333333332e-07 1n 1n 4.9000e-08 1u)
XPFD VDD 0 REF FB UP DN UPB DNB Phase_Detector_FE_PEX
XPUMP VDD 0 UPB DN CP_IBIAS VCTRL Charge_Pump_FE_PEX
VC VCTRL 0 1.4
.control
set noaskquit
tran 0.5n 6u 0 1n
let icp = -i(vc)
meas tran iavg avg icp from=3u to=6u
quit
.endc
.end
