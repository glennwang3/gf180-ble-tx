#!/usr/bin/env python3
"""
PLL_BIAS: on-chip bias for the charge pump and the VCO buffer tail (see ../bias_study/bias2.py).

  VDD - MPD (4/2 PMOS diode, node PG) - RREF (ppolyf_u_1k 10 x 18.6 um, ~186 kOhm) - VSS   I_ref ~10 uA
  MCP0 + MCP1 (2 x 1.04/5 in series, W/L 0.104 vs 2 for MPD) -> IBIAS : ~0.5 uA into the charge pump's IBIAS diode
                          (was 1.04/2 = 2.5 uA, and 2 x 4/2 = 20 uA before that; cut 5x with the widened
                          regulator gain 0.2 -> 0.6 V/V, see ../sim/regwide/loopsize.py)
  MT (4/2, x1) -> MTD (1.0/5.6 NMOS diode) -> TAIL_BIAS : 1.70 V at TT/27 C/3.3 V (+ ~1 pF cap_nmos)
Writes PLL_BIAS.gds and PLL_BIAS.spice.
"""
import os
import klayout.db as db
from geom import Canvas
import pdkcells as P
from acell import Fet, RChain, Router, Term, taps_row, bbox, snap, frange
from build_reg import decap_row

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "PLL_BIAS"
DEBUG = os.environ.get("DEBUG")
W = 40.0
PROW = [("MPD", "p", 4, 2, 1, "PG", "PG", "VDD"), ("MCP0", "p", 1.04, 5, 1, "CPM", "PG", "VDD"),
        ("MCP1", "p", 1.04, 5, 1, "IBIAS", "PG", "CPM"),
        ("MT", "p", 4, 2, 1, "TAIL_BIAS", "PG", "VDD")]
NROW = [("MTD", "n", 1.0, 5.6, 1, "TAIL_BIAS", "TAIL_BIAS", "VSS")]


def place_row(cv, spec, x0, x1, y0):
    cells = [((P.nfet if k == "n" else P.pfet)(cv.ly, w / nf, l=l, nf=nf)) for _, k, w, l, nf, *_ in spec]
    bbs = [bbox(cv.ly, c) for c in cells]
    gap = snap((x1 - x0 - sum(b[2] - b[0] for b in bbs)) / max(1, len(spec) - 1), 0.05)
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
    # N side: tail diode + decap (y 1 .. 27)
    taps_n = taps_row(cv, "p", 1.0, W - 1.0, 1.2, pitch=3.0)
    nrow = place_row(cv, NROW, 0.8, 7.0, 3.0)
    units, dterms, dbb = decap_row(cv, 10.0, W - 0.5, 5.2, 6.0, 20.0, gate_net="TAIL_BIAS")
    # P row (y ~31 .. 37)
    yp = dbb[3] + 3.0
    prow = place_row(cv, PROW, 1.0, W - 1.0, yp)
    pmax = max(f.bb[3] for f in prow)
    cv.rect("nwell", 0.0, yp - 1.0, W, pmax + 1.6)
    taps_w = taps_row(cv, "n", 1.0, W - 1.0, pmax + 0.9, pitch=3.0)
    # Rref above (10 x 18.6 um)
    rr = RChain(cv, 10, 18.6, 4.0, pmax + 3.4, "RREF", "PG", "VSS")
    ytop = snap(rr.bb[3] + 1.0)
    r = Router(cv, 0.6, ytop - 0.6, 0.0, W, debug=DEBUG and (ly.layer(42, 10), ly.layer(46, 10), ly.layer(36, 10)))
    for f in nrow + prow:
        r.add(f.terms())
    r.add(dterms)
    r.add(rr.terms(stub=2.0, tap=False))
    r.add([Term("VSS", frange(x - 1.2, x + 1.2), 1.2, "m1", "ptap") for x in taps_n[1::4]])
    r.add([Term("VDD", frange(x - 1.2, x + 1.2), pmax + 0.9, "m1", "ntap") for x in taps_w[::4]])
    for net in ("VDD", "VSS", "IBIAS", "TAIL_BIAS"):
        r.extra_track_x.setdefault(net, []).append(0.0)
    trk = r.solve()
    for net in ("VDD", "VSS", "IBIAS", "TAIL_BIAS"):
        cv.label("m4t", net, 0.2, trk[net])
    print("tracks", {k: round(v, 2) for k, v in sorted(trk.items(), key=lambda kv: kv[1])})
    b = top.dbbox()
    print(f"{NAME}: bbox {b.left:.2f},{b.bottom:.2f} .. {b.right:.2f},{b.top:.2f}  ({b.width():.1f} x {b.height():.1f}), "
          f"tail decap {len(units)} units = {len(units) * 6 * 20 * 4.0e-3:.2f} pF")
    return top, nrow + prow, rr, units


def netlist(devs, rr, units):
    L = [f".subckt {NAME} VDD VSS IBIAS TAIL_BIAS"]
    for f in devs:
        w, l, nf, kind = f.spec
        model, body = ("nfet_03v3", "VSS") if kind == "n" else ("pfet_03v3", "VDD")
        for i in range(nf):
            L.append(f"X{f.name}_{i} {f.nets['d']} {f.nets['g']} {f.nets['s']} {body} {model} w={w / nf:g}u l={l:g}u")
    L += rr.spice()
    for i, (lc, wc) in enumerate(units):
        L.append(f"XCT{i} TAIL_BIAS VSS cap_nmos_03v3 c_width={wc:g}u c_length={lc:g}u")
    L.append(f".ends {NAME}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ly = db.Layout(); ly.dbu = 0.001
    top, devs, rr, units = build(ly)
    for c in list(ly.top_cells()):
        if c.cell_index() != top.cell_index():
            ly.delete_cell(c.cell_index())
    ly.write(os.path.join(HERE, NAME + ".gds"))
    open(os.path.join(HERE, NAME + ".spice"), "w", newline="\n").write(netlist(devs, rr, units))
