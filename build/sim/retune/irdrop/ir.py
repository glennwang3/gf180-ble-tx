#!/usr/bin/env python3
"""DC IR-drop map of the post-PEX LOOP_PART (flattened to top level): VCTRL forced, v3-like 1580 ohm load at the
VDD_VCO port.  Prints the node voltages of the VDD and VDD_VCO nets and the pass-device terminals."""
import re, subprocess, sys
PEX = sys.argv[1] if len(sys.argv) > 1 else "/foss/designs/pll_compact/layout/pex_loop/LOOP_PART_rcpex.spice"
VC = sys.argv[2] if len(sys.argv) > 2 else "2.6"
txt = re.sub(r"\n\+", " ", open(PEX).read())
body, ports = [], None
for l in txt.splitlines():
    if l.lower().startswith(".subckt loop_part"):
        ports = l.split()[2:]; continue
    if l.lower().startswith(".ends") or l.startswith("*") or not l.strip():
        continue
    body.append(l)
deck = f"""ir
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
""" + "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}' for x in ("ss", "res_ss", "mimcap_ss", "moscap_ss", "cap_mim")) + f"""
.temp 125
""" + "\n".join(body) + f"""
Vdd VDD 0 3.3
Vss VSS 0 0
Vref REF_1M 0 0
Vfb FB_1M 0 0
XTAIL TD TAIL_BIAS 0 0 nfet_03v3 w=1u l=0.28u
VTD TD 0 1.0
RVCO VDD_VCO 0 1580
Vc VCTRL 0 {VC}
.control
set noaskquit
op
print all > nodes.txt
quit
.endc
.end
"""
open("t.sp", "w").write(deck)
open(".spiceinit", "w").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True)
v = {}
for l in open("nodes.txt"):
    m = re.match(r"\s*(\S+)\s*=\s*(\S+)", l)
    if m:
        try: v[m.group(1).lower()] = float(m.group(2))
        except ValueError: pass
for net in ("vdd", "vdd_vco"):
    ks = sorted((k for k in v if k == net or k.startswith(net + ".")), key=lambda k: v[k])
    print(f"{net}: {len(ks)} nodes, min {v[ks[0]]:.4f} ({ks[0]}) max {v[ks[-1]]:.4f} ({ks[-1]})")
# pass device: the widest pfet(s) with l=0.28 whose drain or source is on VDD_VCO
pf = [l for l in body if l.startswith("X") and "pfet_03v3" in l and "l=0.28u" in l]
passl = [l for l in pf if "vdd_vco" in (l.split()[1] + l.split()[3]).lower()]
print("pass fingers:", len(passl))
for l in passl[:60]:
    d, g, s = l.split()[1:4]
    print(f"  {l.split()[0]:6s} D {d:16s} {v.get(d.lower(), float('nan')):.4f}  G {v.get(g.lower(), float('nan')):.4f}  S {s:16s} {v.get(s.lower(), float('nan')):.4f}")
