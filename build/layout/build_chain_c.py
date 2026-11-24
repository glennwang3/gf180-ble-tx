#!/usr/bin/env python3
"""
RF_CHAIN_PA (compact): graded self-biased inverter chain from the low-cap VCO doubler (RF_DRV1) to the
class-C PA, hand-placed so that every chain node stays in the 1-2 fF range (the routed version had
6-10 fF per node and failed at SS/125, see sim/lowcap).

Each stage is a column:
    VSS rail (M1 + substrate taps)                          y -0.1 .. 0.3
    NMOS (gate pads on top), S strips dropped to the rail     y 1.0 ..
    middle band: gate bar (M1) N pads <-> P pads at the left; two M2 link tracks (y_a / y_b)
    PMOS (gate pads at the bottom), S strips raised to VDD    y 7.4 ..
    VDD rail (M1 + n-well taps)                              y 13.2
    feedback resistor (ppolyf_u_1k meander) right above      y 15.0 ..
  output: N / P drains -> M2 bars -> M2 column just right of the devices, which runs on up to the
          resistor's top-right end; a short M2 link in the middle band goes to the next stage's gate bar
  input:  gate bar -> M3 riser -> the resistor's bottom-left end
The PA (50 um = 16 x 3.125 um fingers, gate pads on top) sits in the N row after the last stage.
Writes RF_CHAIN_PA.gds / RF_CHAIN_PA.spice (same cell name and pins as build_chain.py).
"""
import math
import os
import klayout.db as db
from geom import Canvas
import pdkcells as P
from acell import RChain, boxes, bbox, snap, taps_row

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "RF_CHAIN_PA"
L = 0.28
# name, n total, nf_n, p total, nf_p, Rf (ohm, 0 = none)
STAGES = [("S1", 1.0, 1, 2.0, 1, 40e3), ("S2", 1.6, 1, 3.2, 1, 30e3), ("S3", 2.5, 1, 5.0, 1, 20e3),
          ("S4", 4.0, 2, 8.0, 2, 12e3), ("S5", 7.0, 3, 14.0, 3, 8e3), ("S6", 12.0, 4, 24.0, 5, 5e3),
          ("S7", 20.0, 7, 40.0, 8, 0)]
PA_NF, PA_WF = 16, 3.125
YN, YP, YV, YR = 1.0, 7.4, 13.2, 15.0          # N comp bottom, P comp bottom, VDD tap row, resistor row
YA, YB = 5.3, 6.0                              # middle-band M2 link tracks (alternate stages)
LMAX = 6.5                                     # max resistor segment length


def rplan(r):
    """odd segment count (top-right end = far end) and segment length for an r-ohm 1 um ppolyf_u_1k chain"""
    n = 1
    while (r / n - 176.1) / 1030.5 > LMAX:
        n += 2
    return n, snap((r / n - 176.1) / 1030.5, 0.01)


class Dev:
    """PDK FET pcell placed at (x, y) (comp bottom-left ~ (-0.4, 0)); gate pads 'top' or 'bottom'"""

    def __init__(self, cv, kind, wf, nf, x, y, gate):
        ly = cv.ly
        cell = (P.nfet if kind == "n" else P.pfet)(ly, wf, l=L, nf=nf, gate=gate)
        cv.place(cell, x, y)
        self.bb = tuple(v + o for v, o in zip(bbox(ly, cell), (x, y, x, y)))
        c = boxes(ly, cell, 22)[0]
        self.comp = (c[0] + x, c[1] + y, c[2] + x, c[3] + y)
        m1 = [(a + x, b + y, cc + x, d + y) for a, b, cc, d in boxes(ly, cell, 34)]
        self.strips = sorted([b for b in m1 if b[1] < self.comp[3] and b[3] > self.comp[1]], key=lambda b: b[0])
        self.pads = sorted([b for b in m1 if not (b[1] < self.comp[3] and b[3] > self.comp[1])], key=lambda b: b[0])
        self.s, self.d = self.strips[0::2], self.strips[1::2]
        self.wf, self.nf = wf, nf


def xc(b):
    return snap((b[0] + b[2]) / 2)


def build(ly):
    top = ly.create_cell(NAME)
    cv = Canvas(ly, top)
    devs, rchains, cols = [], {}, []
    x_col_prev, res_right_prev, x0 = None, -10.0, 0.6
    gates = []
    for k, (nm, wn, nfn, wp, nfp, rf) in enumerate(STAGES):
        wfn, wfp = wn / nfn, wp / nfp
        # place: device left clear of the previous output column, resistor clear of the previous resistor
        xo = x0 if x_col_prev is None else snap(x_col_prev + 1.5)
        for _ in range(2):
            cn = (P.nfet(ly, wfn, l=L, nf=nfn, gate="top"))
            cp = (P.pfet(ly, wfp, l=L, nf=nfp, gate="bottom"))
            compr = max(boxes(ly, cn, 22)[0][2], boxes(ly, cp, 22)[0][2])
            x_col = snap(xo + compr + 0.70)
            if rf:
                n, ls = rplan(rf)
                x_res = snap(x_col - ls - 0.46)
                need = res_right_prev + 1.0 - (x_res - 1.78)
                if need > 0:
                    xo = snap(xo + need)
                    continue
            break
        dn = Dev(cv, "n", wfn, nfn, xo, YN, "top")
        dp = Dev(cv, "p", wfp, nfp, xo, YP, "bottom")
        devs.append((nm, dn, dp))
        # sources to the rails
        for s in dn.s:
            cv.rect("m1", s[0], 0.25, s[2], s[1] + 0.05)
        for s in dp.s:
            cv.rect("m1", s[0], s[3] - 0.05, s[2], YV - 0.15)
        # drains -> M2 bars -> output column
        ydn, ydp = snap(YN + 0.55), snap(YP + 0.55)
        for grp, yb in ((dn.d, ydn), (dp.d, ydp)):
            for d in grp:
                cv.pad("m1", xc(d), yb); cv.pad("v1", xc(d), yb, 0.26); cv.pad("m2", xc(d), yb)
            cv.hline("m2", xc(grp[0]), x_col, yb, w=0.28)
        # gate: N pad bar, P pad bar, vertical M1 at the left pad
        x_g = min(xc(dn.pads[0]), xc(dp.pads[0]))
        yng = snap((dn.pads[0][1] + dn.pads[0][3]) / 2)
        ypg = snap((dp.pads[0][1] + dp.pads[0][3]) / 2)
        cv.rect("m1", x_g - 0.19, dn.pads[0][1], dn.pads[-1][2], dn.pads[0][3])
        cv.rect("m1", x_g - 0.19, dp.pads[0][1], dp.pads[-1][2], dp.pads[0][3])
        cv.rect("m1", x_g - 0.19, dn.pads[0][1], x_g + 0.19, dp.pads[0][3])
        gates.append((x_g, yng, ypg))
        # output column: N drain bar -> (through the band) -> resistor top-right end (or the band only)
        y_top = ydp
        if rf:
            c = RChain(cv, n, ls, x_res, YR, f"XR{nm}", f"N{k + 1}" if k < len(STAGES) - 1 else "D1",
                       "RF_DRV1" if k == 0 else f"N{k}")
            rchains[nm] = c
            # input: gate bar -> M3 riser -> resistor bottom-left end (a)
            cv.via(x_g, ypg, "m1", "m3")
            cv.vline("m3", x_g, ypg, c.a[1], w=0.28)
            cv.hline("m3", min(x_g, c.a[0]), max(x_g, c.a[0]), c.a[1], w=0.28)
            cv.via(c.a[0], c.a[1], "m1", "m3")
            # output: column up to the top-right end (b)
            assert abs(c.b[0] - x_col) < 0.02, (c.b, x_col)
            cv.via(x_col, c.b[1], "m1", "m2")
            y_top = c.b[1]
            res_right_prev = c.bb[2]
        else:
            res_right_prev = max(res_right_prev, x_col)
        cv.vline("m2", x_col, ydn, y_top, w=0.28)
        cols.append(x_col)
        x_col_prev = x_col
    # PA device in the N row
    xpa = snap(x_col_prev + 1.5)
    pa = Dev(cv, "n", PA_WF, PA_NF, xpa, YN, "top")
    for s in pa.s:
        cv.rect("m1", s[0], 0.25, s[2], s[1] + 0.05)
    x_gpa = xc(pa.pads[0])
    cv.rect("m1", x_gpa - 0.19, pa.pads[0][1], pa.pads[-1][2], pa.pads[0][3])
    gates.append((x_gpa, snap((pa.pads[0][1] + pa.pads[0][3]) / 2), None))
    W = snap(pa.comp[2] + 1.2)
    ypd = snap(YN + 1.55)
    for d in pa.d:
        cv.via(xc(d), ypd, "m1", "m4")
    cv.rect("m4", xc(pa.d[0]) - 0.3, ypd - 0.9, W + 0.4, ypd + 0.9)
    cv.label("m4t", "PA_DRAIN", W, ypd)
    # links: output column k -> gate bar of stage k+1 (or the PA), alternating band tracks
    for k, x_col in enumerate(cols):
        y = YA if k % 2 == 0 else YB
        x_g, yng, ypg = gates[k + 1]
        cv.hline("m2", x_col, x_g, y, w=0.28)
        cv.pad("m2", x_col, y)
        cv.via(x_g, y, "m1", "m2")
        if ypg is None:                               # PA: no P bar; extend its gate M1 up to the link
            cv.rect("m1", x_g - 0.19, yng, x_g + 0.19, y + 0.2)
    # input pin: S1 gate bar, M1 -> M3 at the free track y_a
    xg1 = gates[0][0]
    cv.via(xg1, YA, "m1", "m3")
    cv.label("m3t", "RF_DRV1", xg1, YA)
    cv.label("m1t", "D1", x_gpa, gates[-1][1])
    # rails, taps, n-well
    xr_p = max(d[2].comp[2] for d in devs) + 0.6
    taps_row(cv, "p", 0.4, W - 0.4, 0.1, pitch=2.0)
    cv.rect("m1", 0.0, -0.1, W, 0.3)
    taps_row(cv, "n", 0.4, xr_p, YV, pitch=2.0)
    cv.rect("m1", 0.0, YV - 0.2, xr_p + 0.2, YV + 0.2)
    cv.rect("nwell", -0.3, YP - 0.6, xr_p + 0.7, YV + 0.6)
    # power straps on M4 over both rails (the 0.4 um M1 rails alone are too narrow for ~4 mA + the PA):
    # via stacks every ~1 um, clear of the M2 output columns and the M3 input risers that cross the VDD rail
    cv.rect("m1", 0.0, -0.6, W, 0.3)
    cv.rect("m4", 0.0, -0.3, W, 0.5)
    x = 0.6
    while x < W - 0.4:
        if abs(x - gates[0][0]) >= 1.0:          # the top-level RF_DRV1 M3 link crosses the rail at the S1 gate x
            cv.via(snap(x), 0.1, "m1", "m4")
        x += 1.0
    cv.rect("m4", 0.0, YV - 0.4, xr_p + 0.2, YV + 0.4)
    keep_out = list(cols) + [g[0] for g in gates[:-1]]
    x = 0.6
    while x < xr_p:
        if all(abs(x - c) >= 0.75 for c in keep_out):
            cv.via(snap(x), YV, "m1", "m4")
        x += 0.5 if any(abs(x - c) < 0.75 for c in keep_out) else 1.0
    cv.label("m4t", "VSS", 0.3, 0.1)
    cv.label("m4t", "VDD", 0.3, YV)
    b = top.dbbox()
    print(f"{NAME}: bbox {b.left:.2f},{b.bottom:.2f} .. {b.right:.2f},{b.top:.2f}  ({b.width():.1f} x {b.height():.1f})")
    print("RF_DRV1 pin (M3)", xg1, YA)
    return top, devs, pa, rchains


def netlist(devs, pa, rchains):
    out = [f".subckt {NAME} RF_DRV1 VDD VSS PA_DRAIN D1"]
    for k, (nm, dn, dp) in enumerate(devs):
        gi = "RF_DRV1" if k == 0 else f"N{k}"
        do = f"N{k + 1}" if k < len(devs) - 1 else "D1"
        for i in range(dn.nf):
            out.append(f"X{nm}N_{i} {do} {gi} VSS VSS nfet_03v3 w={dn.wf:g}u l={L:g}u")
        for i in range(dp.nf):
            out.append(f"X{nm}P_{i} {do} {gi} VDD VDD pfet_03v3 w={dp.wf:g}u l={L:g}u")
    for i in range(pa.nf):
        out.append(f"XMPA_{i} PA_DRAIN D1 VSS VSS nfet_03v3 w={pa.wf:g}u l={L:g}u")
    for c in rchains.values():
        out += c.spice()
    out.append(f".ends {NAME}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ly = db.Layout(); ly.dbu = 0.001
    top, devs, pa, rchains = build(ly)
    for c in list(ly.top_cells()):
        if c.cell_index() != top.cell_index():
            ly.delete_cell(c.cell_index())
    ly.write(os.path.join(HERE, NAME + ".gds"))
    open(os.path.join(HERE, NAME + ".spice"), "w", newline="\n").write(netlist(devs, pa, rchains))
    for nm, c in rchains.items():
        print(nm, c.nets, len(c.seg), "x", c.seg[0][1], "um")
