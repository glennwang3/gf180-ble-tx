v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N -620 690 -570 690 {lab=voutn}
N -430 670 -380 670 {lab=voutp}
N -470 240 -430 240 {lab=#net1}
N -430 600 -430 670 {lab=voutp}
N -620 580 -620 690 {lab=voutn}
N -620 580 -430 580 {lab=voutn}
C {code_shown.sym} 190 -570 0 0 {name=s1 only_toplevel=false value="

.include /foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice
.lib /foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice typical
.lib /foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice mimcap_typical

** Eight-bit binary input stimulus
** Each input code is held for 125 ns
** The complete 0-to-255 sweep takes 32 us

VD0  D0  0 PULSE(0   3.3 125n 1n 1n 125n 250n)
VD0B D0b 0 PULSE(3.3 0   125n 1n 1n 125n 250n)

VD1  D1  0 PULSE(0   3.3 250n 1n 1n 250n 500n)
VD1B D1b 0 PULSE(3.3 0   250n 1n 1n 250n 500n)

VD2  D2  0 PULSE(0   3.3 500n 1n 1n 500n 1u)
VD2B D2b 0 PULSE(3.3 0   500n 1n 1n 500n 1u)

VD3  D3  0 PULSE(0   3.3 1u 1n 1n 1u 2u)
VD3B D3b 0 PULSE(3.3 0   1u 1n 1n 1u 2u)

VD4  D4  0 PULSE(0   3.3 2u 1n 1n 2u 4u)
VD4B D4b 0 PULSE(3.3 0   2u 1n 1n 2u 4u)

VD5  D5  0 PULSE(0   3.3 4u 1n 1n 4u 8u)
VD5B D5b 0 PULSE(3.3 0   4u 1n 1n 4u 8u)

VD6  D6  0 PULSE(0   3.3 8u 1n 1n 8u 16u)
VD6B D6b 0 PULSE(3.3 0   8u 1n 1n 8u 16u)

VD7  D7  0 PULSE(0   3.3 16u 1n 1n 16u 32u)
VD7B D7b 0 PULSE(3.3 0   16u 1n 1n 16u 32u)

.control 

tran 1n 32u

** Display the binary inputs
**plot v(D0) v(D1) v(D2) v(D3)
**plot v(D4) v(D5) v(D6) v(D7)

plot v(voutp)
plot v(voutp)-v(voutn)


set wr_singlescale
set wr_vecnames
wrdata dac_output.txt v(voutp) v(voutn) v(voutp)-v(voutn)


.endc

"}
C {res.sym} -540 690 1 0 {name=R1
value=150
footprint=1206
device=resistor
m=1}
C {vsource.sym} -510 720 0 0 {name=V1 value=3 savecurrent=false}
C {gnd.sym} -510 750 0 0 {name=l1 lab=0}
C {gnd.sym} -430 220 2 0 {name=l2 lab=0}
C {res.sym} -350 670 1 0 {name=R2
value=150
footprint=1206
device=resistor
m=1}
C {vsource.sym} -320 700 0 0 {name=V2 value=3 savecurrent=false}
C {gnd.sym} -320 730 0 0 {name=l3 lab=0}
C {vsource.sym} -500 240 1 0 {name=V3 value=0.8 savecurrent=false}
C {gnd.sym} -530 240 1 0 {name=l4 lab=0
value=1.2}
C {current_steering_dac.sym} -280 410 2 0 {name=x1}
C {lab_wire.sym} -430 560 0 0 {name=p1 sig_type=std_logic lab=d6}
C {lab_wire.sym} -430 540 0 0 {name=p2 sig_type=std_logic lab=d7b}
C {lab_wire.sym} -430 520 0 0 {name=p3 sig_type=std_logic lab=d3}
C {lab_wire.sym} -430 500 0 0 {name=p4 sig_type=std_logic lab=d5b}
C {lab_wire.sym} -430 480 0 0 {name=p5 sig_type=std_logic lab=d5}
C {lab_wire.sym} -430 460 0 0 {name=p6 sig_type=std_logic lab=d1}
C {lab_wire.sym} -430 440 0 0 {name=p7 sig_type=std_logic lab=d6b}
C {lab_wire.sym} -430 420 0 0 {name=p8 sig_type=std_logic lab=d3b}
C {lab_wire.sym} -430 400 0 0 {name=p9 sig_type=std_logic lab=d7}
C {lab_wire.sym} -430 380 0 0 {name=p10 sig_type=std_logic lab=d2b}
C {lab_wire.sym} -430 360 0 0 {name=p11 sig_type=std_logic lab=d2}
C {lab_wire.sym} -430 340 0 0 {name=p12 sig_type=std_logic lab=d1b}
C {lab_wire.sym} -430 320 0 0 {name=p13 sig_type=std_logic lab=d4}
C {lab_wire.sym} -430 300 0 0 {name=p14 sig_type=std_logic lab=d0b}
C {lab_wire.sym} -430 280 0 0 {name=p15 sig_type=std_logic lab=d0}
C {lab_wire.sym} -430 260 0 0 {name=p16 sig_type=std_logic lab=d4b}
C {lab_wire.sym} -590 690 0 0 {name=p17 sig_type=std_logic lab=voutn}
C {lab_wire.sym} -390 670 0 0 {name=p18 sig_type=std_logic lab=voutp}
