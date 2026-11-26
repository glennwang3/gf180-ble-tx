v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
C {code_shown.sym} -360 -330 0 0 {name=s1 only_toplevel=false value="

.include /foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice
.lib /foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice typical
.lib /foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice mimcap_typical

.control 

tran 1n 32u


**plot v(D0) v(D1)+4 v(D2)+8 v(D3)+12 xlimit 0 2u
**plot v(D3) v(D4)+4 v(D5)+8 v(D6)+12 xlimit 0 16u
**plot v(D6) v(D7)+4

plot v(D0b) v(D1b)+4 v(D2b)+8 v(D3b)+12 xlimit 0 2u
plot v(D3b) v(D4b)+4 v(D5b)+8 v(D6b)+12 xlimit 0 16u
plot v(D6b) v(D7b)+4 

plot v(voutp)
plot v(voutp)-v(voutn)


set wr_singlescale
set wr_vecnames
wrdata dac_output.txt v(voutp)


.endc

"}
