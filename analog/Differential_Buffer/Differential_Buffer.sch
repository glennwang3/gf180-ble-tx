v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 90 -60 90 -30 {lab=#net1}
N -120 -60 -120 -30 {lab=#net2}
N -120 -90 90 -90 {lab=3v3}
N -120 -170 -120 -120 {lab=3v3}
N -120 -170 90 -170 {lab=3v3}
N 90 -170 90 -120 {lab=3v3}
N -180 -90 -160 -90 {lab=#net2}
N -180 -90 -180 -50 {lab=#net2}
N -180 -50 -120 -50 {lab=#net2}
N 130 -90 150 -90 {lab=#net2}
N 150 -90 150 -50 {lab=#net2}
N -120 -50 150 -50 {lab=#net2}
N -120 0 90 -0 {lab=vss}
N -120 30 -120 70 {lab=#net3}
N 90 30 90 70 {lab=#net3}
N -10 0 -10 70 {lab=vss}
N -180 -0 -160 0 {lab=diff_in+}
N 130 0 160 0 {lab=diff_in-}
N 320 -60 320 -30 {lab=out}
N 260 -90 280 -90 {lab=#net1}
N 260 -90 260 -50 {lab=#net1}
N 260 0 280 0 {lab=#net1}
N 260 -50 260 0 {lab=#net1}
N 320 -90 360 -90 {lab=3v3}
N 360 -170 360 -90 {lab=3v3}
N 90 -170 360 -170 {lab=3v3}
N 320 -170 320 -120 {lab=3v3}
N 320 -0 360 0 {lab=#net3}
N 360 0 360 70 {lab=#net3}
N 90 70 360 70 {lab=#net3}
N 320 30 320 70 {lab=#net3}
N 90 -40 260 -40 {lab=#net1}
N 320 -40 370 -40 {lab=out}
N -120 70 -120 80 {lab=#net3}
N -120 80 -30 80 {lab=#net3}
N -30 80 90 80 {lab=#net3}
N 90 70 90 80 {lab=#net3}
N -10 70 -10 110 {lab=vss}
N -30 110 -10 110 {lab=vss}
N -10 110 -10 160 {lab=vss}
N -30 160 -10 160 {lab=vss}
N -30 140 -30 160 {lab=vss}
N -140 160 -30 160 {lab=vss}
N -120 110 -70 110 {lab=Tail_Bias}
N -20 -170 -20 -90 {lab=3v3}
C {symbols/nfet_03v3.sym} 110 0 0 1 {name=M1
L=0.28u
W=1u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} -140 0 0 0 {name=M2
L=0.28u
W=1u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/pfet_03v3.sym} -140 -90 0 0 {name=M4
L=0.28u
W=2u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=pfet_03v3
spiceprefix=X
}
C {symbols/pfet_03v3.sym} 110 -90 0 1 {name=M5
L=0.28u
W=2u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=pfet_03v3
spiceprefix=X
}
C {iopin.sym} -120 -170 0 1 {name=p1 lab=3v3}
C {iopin.sym} -140 160 0 1 {name=p2 lab=vss}
C {iopin.sym} -180 0 0 1 {name=p3 lab="diff_in+"}
C {iopin.sym} 160 0 0 0 {name=p4 lab="diff_in-"}
C {symbols/nfet_03v3.sym} 300 0 0 0 {name=M6
L=0.28u
W=1u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/pfet_03v3.sym} 300 -90 0 0 {name=M7
L=0.28u
W=2u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=pfet_03v3
spiceprefix=X
}
C {iopin.sym} 370 -40 0 0 {name=p5 lab=out}
C {symbols/nfet_03v3.sym} -50 110 0 0 {name=M8
L=0.28u
W=1u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {iopin.sym} -120 110 0 1 {name=p6 lab="Tail_Bias"}
