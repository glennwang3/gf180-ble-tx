Rz value
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" res_ss
.include "rz.inc"
V1 VCTRL 0 1
VL LF_RZ 0 0
.control
op
print 1/i(vl)
alter @VSS[dc]=0
.endc
.end
