#!/usr/bin/env python3
"""
RF_CONV_PA: PA-side CML->CMOS converter (variant E of the converter study), the 4/8 and 10/20
drivers and the 50 um / 0.28 um class-C PA device.

  XP -> CCX (7x7 MIM) -> g0 -> XI0 (1/2, 51.7k ppolyf_u_1k feedback) -> n0 -> CC1 -> g1 -> XI1 (2/4, fb)
     -> n1 -> XID0 (4/8) -> d0 -> XID1 (10/20) -> d1 -> XMPA gate
  XN -> CCD -> gd -> XID (1/2, fb) -> nd           (dummy: equal load on XN)
  XMPA drain = PA_DRAIN (to the pad / off-chip tank), source = VSS (substrate-tap rail under the device)

XP / XN land on M3 at the top edge, x = XP_X / XN_X (aligned with the VCO's XP / XN stubs).
Writes RF_CONV_PA.gds and RF_CONV_PA.spice.
"""
import os
import klayout.db as db
from geom import Canvas, um
import pdkcells as P
from acell import Fet, RChain, Router, Mim, Term, taps_row, bbox, snap, frange

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "RF_CONV_PA"
DEBUG = os.environ.get("DEBUG")
W = 54.0                                   # cell width
XN_X, XP_X = 14.0, 19.5                    # pin x (VCO XN/XP are 5.5 um apart)
RSEG = snap((51.7e3 / 5 - 176.1) / 1030.5, 0.01)

# (name, kind, w_total, l, nf, d, g, s)
NROW = [("XI0N", "n", 1, 0.28, 1, "N0", "G0", "VSS"), ("XIDN", "n", 1, 0.28, 1, "ND", "GD", "VSS"),
        ("XI1N", "n", 2, 0.28, 1, "N1", "G1", "VSS"), ("XID0N", "n", 4, 0.28, 1, "D0", "N1", "VSS"),
        ("XID1N", "n", 10, 0.28, 2, "D1", "D0", "VSS")]
PROW = [("XI0P", "p", 2, 0.28, 1, "N0", "G0", "VDD"), ("XIDP", "p", 2, 0.28, 1, "ND", "GD", "VDD"),
        ("XI1P", "p", 4, 0.28, 1, "N1", "G1", "VDD"), ("XID0P", "p", 8, 0.28, 1, "D0", "N1", "VDD"),
        ("XID1P", "p", 20, 0.28, 2, "D1", "D0", "VDD")]


def place_row(cv, spec, x0, x1, y0):
    cells = [((P.nfet if k == "n" else P.pfet)(cv.ly, w / nf, l=l, nf=nf)) for _, k, w, l, nf, *_ in spec]
    bbs = [bbox(cv.ly, c) for c in cells]
    gap = snap((x1 - x0 - sum(b[2] - b[0] for b in bbs)) / (len(spec) - 1), 0.05)
    out, x = [], x0
    for (name, kind, w, l, nf, d, g, s), b in zip(spec, bbs):
        xo = snap(x - b[0])
        f = Fet(cv, kind, w / nf, l, nf, xo, y0, name, dict(d=d, g=g, s=s), ext_s=1.2, ext_d=1.2)
        f.spec = (w, l, nf, kind)
        out.append(f)
        x = xo + b[2] + gap
    return out


def build(ly):
    top = ly.create_cell(NAME)
    cv = Canvas(ly, top)
    # ---------------------------------------------------------------- PA device (right, bottom)
    ypa = 3.0
    pa_cell = P.nfet(ly, 5.0, l=0.28, nf=10)
    pb = bbox(ly, pa_cell)
    xpa = snap(W - 1.0 - pb[2])
    pa = Fet(cv, "n", 5.0, 0.28, 10, xpa, ypa, "XMPA", dict(d="PA_DRAIN", g="D1", s="VSS"), ext_s=0.0, ext_d=0.0)
    pa.spec = (50, 0.28, 10, "n")
    # ---------------------------------------------------------------- inverter rows
    nrow = place_row(cv, NROW, 0.6, pa.bb[0] - 2.5, 3.0)
    prow = place_row(cv, PROW, 0.6, pa.bb[0] - 2.5, 11.0)
    pmax = max(f.bb[3] for f in prow)
    cv.rect("nwell", -0.6, 10.0, pa.bb[0] - 1.6, pmax + 1.6)
    taps_w = taps_row(cv, "n", 1.0, pa.bb[0] - 3.0, pmax + 0.9, pitch=3.0)
    # substrate taps: one row under everything; the PA sources drop straight onto it (wide rail)
    yt = 1.2
    taps_s = taps_row(cv, "p", 1.0, W - 1.0, yt, pitch=3.0)
    cv.rect("m1", pa.comp[0] - 0.3, yt - 0.5, pa.comp[2] + 0.3, yt + 0.5)
    for s in pa.s:
        cv.rect("m1", s[0], yt, s[2], s[1] + 0.1)
    # PA drain: via stacks on every D strip up to an M4 strap, out to the east edge
    for d in pa.d:
        cv.via(snap((d[0] + d[2]) / 2), pa.yd, "m2", "m4")
    y4 = pa.yd
    cv.rect("m4", pa.d[0][0] - 0.3, y4 - 0.9, W + 0.4, y4 + 0.9)
    cv.label("m4t", "PA_DRAIN", W, y4)
    # ---------------------------------------------------------------- resistors (above the P row)
    yr = pmax + 3.2
    chains = {}
    for i, (nm, a, b) in enumerate((("XRF0", "G0", "N0"), ("XRFD", "GD", "ND"), ("XRF1", "G1", "N1"))):
        chains[nm] = RChain(cv, 5, RSEG, (4.0, 23.0, 39.5)[i], yr, nm, a, b)
        t = chains[nm]
        cv.rect("m1", t.tap[0] - 0.19, t.tap[1] - 0.19, t.tap[0] + 0.19, t.tap[1] + 0.19)
    rtop = max(c.bb[3] for c in chains.values())
    # ---------------------------------------------------------------- coupling MIMs (over the rows)
    ym = 11.6                                       # plates over the P row: their tracks sit in the row band
    ccx = Mim(cv, 7.0, 7.0, XP_X + 4.0, ym, top="G0", bot="XP", bside="r", tside="l", name="CCX")
    ccd = Mim(cv, 7.0, 7.0, XN_X - 11.0 + 1.6, ym, top="GD", bot="XN", bside="r", tside="l", name="CCD")
    cc1 = Mim(cv, 7.0, 7.0, ccx.bb[2] + 6.0, ym, top="G1", bot="N0", bside="r", tside="l", name="CC1")
    ytop = snap(max(rtop, max(m.bb[3] for m in (ccx, ccd, cc1))) + 1.0)
    # ---------------------------------------------------------------- routing
    r = Router(cv, 0.6, ytop - 0.6, -0.6, W + 0.5,
               debug=DEBUG and (ly.layer(42, 10), ly.layer(46, 10), ly.layer(36, 10)))
    for f in nrow + prow:
        r.add(f.terms())
    r.add(pa.terms("g"))
    for c in chains.values():
        r.add(c.terms(stub=2.0, tap=False))
    r.add([Term("VSS", frange(x - 1.2, x + 1.2), yt, "m1", "ptap") for x in taps_s[:-4:4]])
    r.add([Term("VDD", frange(x - 1.2, x + 1.2), pmax + 0.9, "m1", "ntap") for x in taps_w[::3]])
    pins = {"XP": Term("XP", frange(XP_X - 2.0, XP_X + 2.0), ytop, "m3", "pinXP"),
            "XN": Term("XN", frange(XN_X - 2.0, XN_X + 2.0), ytop, "m3", "pinXN")}
    r.add(list(pins.values()))
    # PA drain strap (M4) and stacks block other nets
    r.blockage("m4", (pa.d[0][0] - 0.3, y4 - 0.9, W + 0.4, y4 + 0.9), "PA_DRAIN")
    for d in pa.d:
        xc = snap((d[0] + d[2]) / 2)
        r.blockage("m3", (xc - 0.2, pa.yd - 0.2, xc + 0.2, pa.yd + 0.2), "PA_DRAIN")
    for m in (ccx, ccd, cc1):
        m.hook(r)
    for net in ("VDD", "VSS"):
        r.extra_track_x.setdefault(net, []).append(-0.6)
    trk = r.solve()
    for m in (ccx, ccd, cc1):
        m.finish()
    for net in ("VDD", "VSS"):
        cv.label("m4t", net, -0.4, trk[net])
    for net, t in pins.items():
        cv.label("m3t", net, t.x, ytop)
        print("pin", net, t.x, ytop)
    cv.label("m1t", "D1", (pa.gbar[0] + pa.gbar[2]) / 2, (pa.gbar[1] + pa.gbar[3]) / 2)
    print("tracks", {k: round(v, 2) for k, v in sorted(trk.items(), key=lambda kv: kv[1])})
    b = top.dbbox()
    print(f"{NAME}: bbox {b.left:.2f},{b.bottom:.2f} .. {b.right:.2f},{b.top:.2f}  ({b.width():.1f} x {b.height():.1f})")
    return top, nrow + prow + [pa], chains, (ccx, ccd, cc1)


def netlist(devs, chains, mims):
    L = [f".subckt {NAME} XP XN VDD VSS PA_DRAIN D1"]
    for f in devs:
        w, l, nf, kind = f.spec
        model, body = ("nfet_03v3", "VSS") if kind == "n" else ("pfet_03v3", "VDD")
        for i in range(nf):
            L.append(f"X{f.name}_{i} {f.nets['d']} {f.nets['g']} {f.nets['s']} {body} {model} w={w / nf:g}u l={l:g}u")
    for c in chains.values():
        L += c.spice()
    for m in mims:
        L.append(m.spice())
    L.append(f".ends {NAME}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ly = db.Layout(); ly.dbu = 0.001
    top, devs, chains, mims = build(ly)
    for c in list(ly.top_cells()):
        if c.cell_index() != top.cell_index():
            ly.delete_cell(c.cell_index())
    ly.write(os.path.join(HERE, NAME + ".gds"))
    open(os.path.join(HERE, NAME + ".spice"), "w", newline="\n").write(netlist(devs, chains, mims))
