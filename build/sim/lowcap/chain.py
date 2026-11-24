#!/usr/bin/env python3
"""Low-cap Schottky VCO (delivery PLL_PEX, extracted VCO + prescaler) -> inverter chain -> class-C PA.
Pre-layout check of the RF path before integrating the VCO into PLL_COMPACT.
    python3 chain.py TAG CORNER VDD_VCO VTUNE TAIL TSTOP_ns [CHAIN] [CW_fF]
CHAIN: comma list of n[:p] widths (PMOS default 2x), last stage drives the PA gate; default 2,4,10.
CW_fF: lumped wiring cap on every chain node (default 4 fF).
Writes TAG/wave.raw and prints f_RF, P_out, spurs and DC power.
"""
import os
import subprocess
import sys
import numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw  # noqa: E402

NET = "/foss/designs/Diff_VCO_Second_Layout/low_cap_vco_20261122/delivery/vco_prescaler_rcpex.spice"
CORNERS = {"ss125": ("ss", 125), "tt27": ("typical", 27), "ff-40": ("ff", -40)}
tag, corner, vddvco, vtune, tail, tstop = sys.argv[1:7]
# stage spec n[:p][fRk]: widths in um (PMOS default 2x n); "f20" adds a 20 kohm output->input feedback resistor
chain, fbr, acp = [], [], []
for x in (sys.argv[7] if len(sys.argv) > 7 else "2,4,10").split(","):
    acp.append("c" in x)                           # "c": series coupling cap (env CC fF) in front of the stage
    x = x.replace("c", "")
    if "n" in x:                                   # "1n": NMOS pseudo-resistor feedback, gate at VGN
        x = x.replace("n", "")
        fbr.append(-1.0)
    else:
        x, _, r = x.partition("f")
        fbr.append(float(r) if r else 0.0)
    chain.append(tuple(float(v) for v in x.split(":")) if ":" in x else (float(x), 2 * float(x)))
cw = float(sys.argv[8]) if len(sys.argv) > 8 else 4.0
acc = sys.argv[9] if len(sys.argv) > 9 else ""          # "CC_fF:RF_kohm": AC-couple + self-bias stage 1
lib, temp = CORNERS[corner]
# SCALE env: "X59:3,X114:3,..." scales those devices' w / ad / as / pd / ps in a private netlist copy
if os.environ.get("SCALE"):
    import re as _re
    sc = {p.split(":")[0]: float(p.split(":")[1]) for p in os.environ["SCALE"].split(",")}
    out, nch = [], 0
    for line in open(NET).read().splitlines():
        t = line.split()
        if t and t[0] in sc:
            kk = sc[t[0]]
            line = _re.sub(r"(?<![a-z_])(w|ad|as|pd|ps)=([0-9.]+)([a-z]*)",
                           lambda m: f"{m.group(1)}={float(m.group(2)) * kk:.4g}{m.group(3)}", line)
            nch += 1
        out.append(line)
    print("scaled", nch, "devices")
if os.environ.get("SCALE") or os.environ.get("TAP1"):
    if not os.environ.get("SCALE"):
        out = open(NET).read().splitlines()
    if os.environ.get("TAP1"):
        # drop the cell's 2nd / 3rd output inverters; RF_OUT port = output of the self-biased 1st inverter
        if os.environ["TAP1"] != "keep":
            out = [l for l in out if not (l.split() and l.split()[0] in ("X59", "X114", "X42", "X95"))]
        else:   # keep the cell's inverters; their RF_OUT becomes a private node
            out = [l.replace("RF_OUT", "RF_OUT_OLD") if not l.startswith(".subckt") else l for l in out]
            out.append("")
        i = max(k for k, l in enumerate(out) if l.startswith(".ends"))
        out.insert(i, "RTAP1 a_76968_33670.n1 RF_OUT 1m")
    os.makedirs(tag, exist_ok=True)
    os.makedirs(tag, exist_ok=True)
    open(f"{tag}/net.spice", "w").write(chr(10).join(out) + chr(10))
    NET = os.path.abspath(f"{tag}/net.spice")
libs = "\n".join(f'.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" {x}' for x in
                 (lib, "diode_" + lib, "res_" + lib, "mimcap_" + lib, "moscap_" + lib, "cap_mim"))
ports = open(NET).read().split(".subckt PLL_PEX", 1)[1].split("\n")[0].split()
cont = open(NET).read().split(".subckt PLL_PEX", 1)[1].split("\n")[1]
if cont.startswith("+"):
    ports += cont[1:].split()
conn = {"VSS": "0", "RF_OUT": "rf_out"}
inv, nodes = [], ["rf_out"]
if acc:
    cc, rf = (float(v) for v in acc.split(":"))
    inv += [f"CCPL rf_out g0 {cc}f", f"RFB g0 c1 {rf}k", f"CWG g0 0 {cw}f"]
    nodes = ["g0"]
for i, (wn, wp) in enumerate(chain if chain[0][0] > 0 and not os.environ.get("CHAIN_PEX") else []):
    a, b = nodes[-1], (f"c{i + 1}" if i < len(chain) - 1 else "d1")
    if acp[i]:
        cc = float(os.environ.get("CC", "20"))
        inv += [f"CCP{i} {a} g{i} {cc}f", f"CBP{i} {a} 0 {cc * 0.02:.3g}f", f"CGW{i} g{i} 0 0.5f"]
        a = f"g{i}"
    jn = f" ad={wn * 0.6:.3g}p as={wn * 0.6:.3g}p pd={2 * wn + 1.2:.3g}u ps={2 * wn + 1.2:.3g}u" if os.environ.get("JCT") else ""
    jp = f" ad={wp * 0.6:.3g}p as={wp * 0.6:.3g}p pd={2 * wp + 1.2:.3g}u ps={2 * wp + 1.2:.3g}u" if os.environ.get("JCT") else ""
    inv.append(f"XN{i} {b} {a} 0 0 nfet_03v3 w={wn}u l=0.28u nf={max(1, int(wn // 5))}{jn}")
    inv.append(f"XP{i} {b} {a} VDD VDD pfet_03v3 w={wp}u l=0.28u nf={max(1, int(wp // 10))}{jp}")
    inv.append(f"CW{i} {b} 0 {cw}f")
    if fbr[i] > 0:
        inv.append(f"RF{i} {b} {a} {fbr[i]}k")
    elif fbr[i] < 0:
        inv.append(f"XPR{i} {b} VGN {a} 0 nfet_03v3 w=0.36u l=0.28u ad=0.2p as=0.2p pd=1.8u ps=1.8u")
    nodes.append(b)
deck = f"""low-cap VCO -> chain {chain} -> class-C PA, {corner}, VDD_VCO {vddvco}, VTUNE {vtune}, tail {tail}
.include "/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice"
{libs}
.include "{NET}"
.temp {temp}
.options method=gear reltol=2e-4 abstol=1e-12 vntol=1e-6 itl4=80 rshunt=1e12
Vmain VDD 0 3.3
Vvco VDD_VCO 0 {vddvco}
Vtn VTUNE 0 {vtune}
Vtail TAIL_BIAS 0 {tail}
Vmode MC 0 3.3
Vgn VGN 0 {os.environ.get("VGN", "2.0")}
Xdut {' '.join(conn.get(p, p) for p in ports)} PLL_PEX
Cdig PRESCALED 0 6f
{f"CRFW rf_out 0 {cw}f" if cw > 0 else ""}
{chr(10).join(inv)}
{"" if chain[0][0] > 0 or os.environ.get("CHAIN_PEX") else "VD1 d1 0 0"}
{"XCH " + " ".join({"PA_DRAIN": "drain", "VDD": "VDD", "VSS": "0", "RF_DRV1": "rf_out", "D1": "d1"}[p] for p in open(os.environ["CHAIN_PEX"]).read().split(".subckt RF_CHAIN_PA_FLAT", 1)[1].split(chr(10))[0].split()) + " RF_CHAIN_PA_FLAT" + chr(10) + '.include "' + os.environ["CHAIN_PEX"] + '"' if os.environ.get("CHAIN_PEX") else "XPA drain d1 0 0 nfet_03v3 w=50u l=0.28u nf=10"}
CPAD drain 0 1.5p
LBW drain bw 1.2n
RBW bw board 0.2
LT board vpa_l 1.70n
RLT vpa_l vpa 0.3
VPA vpa 0 1.5
CT board 0 0.10p
CDC board out 20p
RLOAD out 0 100
.ic V(O1P)=2.2 V(O1N)=1.0
.control
set noaskquit
set num_threads=1
set filetype=binary
save v(o1p) v(o1n) v(rf_out) v(mim_top) v(doubler_k) v(xdut.a_76968_33670) v(xdut.a_76168_33670) {' '.join(f'v({n})' for n in nodes if n != 'rf_out')}{' v(d1) v(xch.a_214_200) v(xch.a_2120_200) v(xch.a_4156_200) v(xch.a_5514_200) v(xch.a_6614_200) v(xch.a_8006_200)' if os.environ.get('CHAIN_PEX') else ''} v(drain) v(out) v(core_clk) v(prescaled) i(vpa) i(vmain) i(vvco)
tran 4p {tstop}n 0 4p
write wave.raw all
quit
.endc
.end
"""
os.makedirs(tag, exist_ok=True)
open(f"{tag}/t.sp", "w", newline="\n").write(deck)
open(f"{tag}/.spiceinit", "w", newline="\n").write("set ngbehavior=hsa\n")
subprocess.run("ngspice -b t.sp > log.txt 2>&1", shell=True, cwd=tag)

# ---- measurement ------------------------------------------------------------------------------
w = read_raw(f"{tag}/wave.raw")
t = w["time"]
T0 = float(tstop) * 1e-9 * 0.4
tu = np.arange(T0, t[-1], 1e-12)
u = {k: np.interp(tu, t, w[k]) for k in w if k != "time"}


def cross(x):
    s = np.where((x[:-1] < 0) & (x[1:] >= 0))[0]
    return tu[s] - x[s] / (x[s + 1] - x[s]) * 1e-12


def tone(x, f0):
    n = int((tu[-1] - tu[0]) * f0)
    m = tu <= tu[0] + n / f0
    tt, xx = tu[m], x[m] - x[m].mean()
    A = np.column_stack([np.cos(2 * np.pi * f0 * tt), np.sin(2 * np.pi * f0 * tt)])
    return np.hypot(*np.linalg.lstsq(A, xx, rcond=None)[0])


tc = cross(u["v(o1p)"] - u["v(o1n)"])
fr = 2 / np.mean(np.diff(tc))
a = {h: tone(u["v(out)"], h * fr) for h in (0.5, 1, 1.5, 2, 3)}
pout = a[1] ** 2 / 200
ipa = -u["i(vpa)"].mean(); imain = -u["i(vmain)"].mean(); ivco = -u["i(vvco)"].mean()
g = u["v(d1)"]
gate_f = {h: tone(g, h * fr) for h in (0.5, 1)}
print(f"{tag} VGN {os.environ.get('VGN', '-')} fb{fbr} [{os.environ.get('SCALE', '')}]: VDD_VCO {vddvco} VTUNE {vtune} tail {tail} chain {chain} cw {cw}f | f_RF {fr/1e9:.5f} GHz | "
      f"P_out {10*np.log10(pout/1e-3):+.2f} dBm | f/2 {20*np.log10(a[0.5]/a[1]):.1f} dBc, 3f/2 "
      f"{20*np.log10(a[1.5]/a[1]):.1f}, 2f {20*np.log10(a[2]/a[1]):.1f}, 3f {20*np.log10(a[3]/a[1]):.1f} dBc | "
      f"ac {acc} | PA gate swing {g.min():.2f}..{g.max():.2f} V, gate f/2 {20*np.log10(gate_f[0.5]/gate_f[1]):.1f} dBc | "
      f"RF_OUT {u['v(rf_out)'].min():.2f}..{u['v(rf_out)'].max():.2f} V | "
      f"DC: PA {ipa*1.5e3:.2f} mW, VDD 3.3 {imain*3.3e3:.2f} mW ({imain*1e3:.2f} mA), VCO {ivco*float(vddvco)*1e3:.2f} mW "
      f"({ivco*1e3:.2f} mA) | drain eff {100*pout/ipa/1.5:.1f} %")
