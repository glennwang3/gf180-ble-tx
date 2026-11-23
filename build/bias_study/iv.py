import subprocess, os
C = {"tt": ("typical", 27), "ss": ("ss", 125), "ff": ("ff", -40)}
for corner, (lib, t) in C.items():
    deck = f"""iv
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {lib}
.temp {t}
Vg g 0 1.7
Vd d 0 1.0
XT d g 0 0 nfet_03v3 w=1u l=0.28u
Vg1 g1 0 1.7
XA g1 g1 0 0 nfet_03v3 w=0.36u l=0.28u
XB g1 g1 0 0 nfet_03v3 w=0.36u l=1u
XC g1 g1 0 0 nfet_03v3 w=0.36u l=2u
XD g1 g1 0 0 nfet_03v3 w=0.36u l=4u
.control
op
print -i(vd) 
print @m.xa.m0[id] @m.xb.m0[id] @m.xc.m0[id] @m.xd.m0[id]
quit
.endc
.end"""
    open("iv.sp", "w").write(deck)
    r = subprocess.run(["ngspice", "-b", "iv.sp"], capture_output=True, text=True)
    print(corner, [l.strip() for l in r.stdout.splitlines() if "=" in l and ("vd" in l or "id" in l)])
