#!/usr/bin/env python3
"""
VCO_REG_L: layout of /foss/designs/vco_supply_regulator_3v3 (VCO_REG, pins VIN VCTRL VOUT VSS).

Devices follow the schematic (W/L), wide ones folded into equal fingers (<= 8 um).  The ideal
schematic resistors become ppolyf_u_1k meanders of equal segments with the nominal value; Ccomp
(15 pF) and Cbuf (2.2 pF) are MIM-B plates stacked over the device rows; the space under the plates
holds cap_nmos_03v3 decap on VOUT (the 470 pF test-bench cap is not needed for stability: the
regulator is Miller-compensated - see ../reg_study).  The 192 um pass device sits outside the MIM
with an M5 VOUT bus on the west edge (towards the VCO) and an M1/M2 VIN bus.

Writes VCO_REG_L.gds and VCO_REG_L.spice (LVS reference / post-layout schematic).
"""
import os
import klayout.db as db
from geom import Canvas, um
import pdkcells as P
from acell import Fet, RChain, Router, Mim, MimComb, Term, taps_row, bbox, boxes, snap, frange

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "VCO_REG_L"
RSEG = lambda R, n: snap((R / n - 176.1) / 1030.5, 0.01)

# (name, kind, w_total, l, nf, d, g, s)
NROW = [("MBIAS", "n", 4, 1, 1, "BIAS", "BIAS", "VSS"), ("MPSINK", "n", 3, 1, 1, "PBIAS", "BIAS", "VSS"),
        ("MBTAIL", "n", 3, 1, 1, "BTAIL", "BIAS", "VSS"), ("MBSINK", "n", 7, 1, 1, "BUF", "BIAS", "VSS"),
        ("MBMINUS", "n", 8, 1, 1, "BMIR", "BUF", "BTAIL"), ("MBPLUS", "n", 8, 1, 1, "BGATE", "VCTRL", "BTAIL"),
        ("MNGATE", "n", 24, 0.6, 3, "GATE", "DRIVE", "VSS"), ("MMIR", "n", 12, 1.5, 2, "MIR", "MIR", "VSS"),
        ("MPULL", "n", 12, 1.5, 2, "DRIVE", "MIR", "VSS")]
PROW = [("MPDIODE", "p", 8, 1, 1, "PBIAS", "PBIAS", "VIN"), ("MPGATE", "p", 8, 1, 1, "GATE", "PBIAS", "VIN"),
        ("MTAIL", "p", 16, 1, 2, "TAIL", "PBIAS", "VIN"), ("MPLUS", "p", 12, 1.5, 2, "MIR", "REF", "TAIL"),
        ("MMINUS", "p", 12, 1.5, 2, "DRIVE", "FB", "TAIL"), ("MBMIR", "p", 8, 1, 1, "BMIR", "BMIR", "VIN"),
        ("MBPULL", "p", 8, 1, 1, "BGATE", "BMIR", "VIN"), ("MBOUT", "p", 12, 1, 2, "BUF", "BGATE", "VIN")]
# REF summing node: VOUT = 2 REF = 2 (G_in VCTRL + G_hi VIN) / (G_in + G_hi + G_lo).
# Widened 2026-11-23 for the low-cap VCO: VOUT ~ 1.40 V + 0.65 VCTRL (was 2.85 V + 0.2 VCTRL with 220k / 51.1k),
# so VDD_VCO covers channel 0 from ~1.83 V (FF/-40, VCTRL ~0.65: the NMOS-input VCTRL buffer needs >= ~0.55 V)
# to ~3.19 V (SS/125, VCTRL ~2.75) and the ~3.26 V pass-device ceiling.  RZERO 2.2k -> 6.8k: below ~2.8 V the pass
# device is saturated and the loop crosses over in the MHz range (11 dB peaking at TT with 2.2k); see sim/regwide.
RES = [("RBIAS", "VIN", "BIAS", 100e3, 5), ("RSETIN", "BUF", "REF", 66.9e3, 10), ("RSETHI", "VIN", "REF", 102.6e3, 5),
       ("RSETLO", "REF", "VSS", 47e3, 3), ("RFBHI", "VOUT", "FB", 50e3, 3), ("RFBLO", "FB", "VSS", 50e3, 3),
       ("RBUF", "BGATE", "BCOMP", 4.7e3, 1), ("RZERO", "DRIVE", "COMP", 6.8e3, 1)]
GAP = 0.60
DEBUG = os.environ.get("DEBUG")


def fet_cell(ly, kind, wf, l, nf):
    return (P.nfet if kind == "n" else P.pfet)(ly, wf, l=l, nf=nf)


def row(cv, spec, x0, y0, x1=None):
    """place a row left->right, comp bottoms at y0; if x1 is given the devices are spread evenly
    over x0..x1 (room for the router columns); returns the Fet list and the right edge"""
    cells = []
    for name, kind, w, l, nf, d, g, s in spec:
        c = fet_cell(cv.ly, kind, w / nf, l, nf)
        cells.append((c, bbox(cv.ly, c)))
    widths = sum(b[2] - b[0] for _, b in cells)
    gap = GAP if x1 is None else max(GAP, snap((x1 - x0 - widths) / (len(spec) - 1), 0.05))
    out, x = [], x0
    for (name, kind, w, l, nf, d, g, s), (c, b) in zip(spec, cells):
        xo = snap(x - b[0])
        out.append(Fet(cv, kind, w / nf, l, nf, xo, y0, name, dict(d=d, g=g, s=s)))
        out[-1].spec = (w, l, nf, kind)
        x = xo + b[2] + gap
    return out, x - gap


def decap_row(cv, x0, x1, y0, lc, wc, gate_net="VOUT"):
    """abutted cap_nmos_03v3 units (S/D side strips shared) from x0 to x1; returns units, terms"""
    c = P.moscap(cv.ly, lc, wc)
    m1 = boxes(cv.ly, c, 34)
    u = max(m1, key=lambda b: (b[3] - b[1]) * 0 + (b[2] - b[0]))        # U (widest M1)
    gplate = min(m1, key=lambda b: b[2] - b[0])
    pitch = snap(u[2] - u[0] - 1.0)
    n = int((x1 - x0 - (u[2] - u[0])) / pitch) + 1
    xs = [x0 - u[0] + i * pitch for i in range(n)]
    for x in xs:
        cv.place(c, x, y0)
    # gate bus (M2) over the gate-plate extension above the U, via1 on each plate
    yg = y0 + gplate[3] - 0.25
    for x in xs:
        cv.pad("v1", x + (gplate[0] + gplate[2]) / 2, yg, 0.26)
        cv.pad("m1", x + (gplate[0] + gplate[2]) / 2, yg)
    xg0 = xs[0] + (gplate[0] + gplate[2]) / 2
    xg1 = xs[-1] + (gplate[0] + gplate[2]) / 2
    cv.hline("m2", xg0, xg1, yg, w=0.40)
    ybar = y0 + u[1] + 0.5                                              # U bottom bar (VSS)
    # substrate taps just below the U bar (DF.14: every NCOMP within reach of a PCOMP tap)
    ytap = y0 + u[1] - 0.55
    txs = taps_row(cv, "p", xs[0] + u[0] + 0.5, xs[-1] + u[2] - 0.5, ytap, pitch=3.0)
    cv.rect("m1", txs[0] - 0.2, ytap, txs[-1] + 0.2, y0 + u[1] + 0.05)
    terms = [Term(gate_net, frange(xg0, xg1, 0.4), yg, "m2", "decap.g"),
             Term("VSS", frange(xs[0] + u[0] + 0.3, xs[-1] + u[2] - 0.3, 0.4), ybar, "m1", "decap.s")]
    units = [(lc, wc)] * n
    return units, terms, (xs[0] + u[0], y0 + u[1], xs[-1] + u[2], y0 + max(b[3] for b in m1))


def vin_power(cv, mp, yvin_trk):
    """Low-resistance VIN feed for the 2 mA pass device (post-PEX the router-width VIN path dropped ~100 mV).
    2-cut M2..MT stacks on the source strips (where M2..M5 is clear) -> 4.2 um MT strap over the device band
    -> 5.6 um MT bus down the free east column -> M4->MT cut row onto the VIN pin track (top-level VDD lands on MT)."""
    ly, c = cv.ly, cv.c
    reg = {m: db.Region(c.begin_shapes_rec(cv.li(m))) for m in ("m2", "m3", "m4", "m5")}
    y0, y1 = mp.ys - 0.20, mp.ys + 0.80                     # stack column: S bar (ys) .. ys + 0.6
    used = []
    for st in mp.s:
        xc = snap((st[0] + st[2]) / 2)
        box = db.Box(um(xc - 0.20), um(y0), um(xc + 0.20), um(y1))
        clear = True
        for m in ("m3", "m4", "m5"):                          # keep >= 0.32 um from anything already on M3..M5
            if not (reg[m] & db.Region(box.enlarged(um(0.32), um(0.32)))).is_empty():
                clear = False
        if not clear:
            continue
        for m in ("m2", "m3", "m4", "m5"):
            cv.rect(m, xc - 0.20, y0, xc + 0.20, y1)
        for yy in (mp.ys, mp.ys + 0.60):                     # the source strip's own M1 encloses the via1 cuts
            for v in ("v1", "v2", "v3", "v4", "v5"):
                cv.pad(v, xc, yy, 0.26)
        used.append(xc)
    ymt0, ymt1 = mp.ys - 0.38, 100.40
    cv.rect("mt", mp.s[0][0], ymt0, 135.6, ymt1)                           # strap over the device band
    cv.rect("mt", 130.0, yvin_trk - 2.2, 135.6, ymt1)                     # east bus down to the VIN track
    cv.rect("m5", 130.2, yvin_trk - 0.20, 135.4, yvin_trk + 0.20)
    for k in range(8):
        xx = 130.6 + 0.6 * k
        cv.pad("v4", xx, yvin_trk, 0.26)
        cv.pad("v5", xx, yvin_trk, 0.26)
    cv.label("mtt", "VIN", 132.8, yvin_trk)
    print(f"VIN power: {len(used)} source stacks (x {used[0]:.2f} .. {used[-1]:.2f}), MT strap y {ymt0:.2f}..{ymt1}, "
          f"east bus x 130.0..135.6 down to y {yvin_trk - 2.2:.2f}")


def build(ly):
    top = ly.create_cell(NAME)
    cv = Canvas(ly, top)
    # ------------------------------------------------------------------ device rows (y 3 .. 27)
    taps_n = taps_row(cv, "p", 1.0, 129.0, 2.0)
    nrow, xr_n = row(cv, NROW, 0.5, 3.4, 130.0)
    yp = 16.0
    prow, xr_p = row(cv, PROW, 0.5, yp, 130.0)
    pmax = max(f.bb[3] for f in prow)
    taps_w = taps_row(cv, "n", 1.0, 129.0, pmax + 0.9)
    cv.rect("nwell", -0.5, yp - 1.0, 131.0, pmax + 1.6)
    devs = nrow + prow
    # ------------------------------------------------------------------ resistors: three columns
    chains = {}
    spec = {r[0]: r for r in RES}
    cols = {4.0: ("RSETIN",), 36.0: ("RBIAS", "RBUF", "RZERO"), 66.0: ("RSETHI", "RSETLO"), 97.0: ("RFBHI", "RFBLO")}
    for rx, names in cols.items():
        y = pmax + 12.0
        for nm in names:
            _, a, b, R, n = spec[nm]
            chains[nm] = RChain(cv, n, RSEG(R, n), rx, y, nm, a, b)
            y = chains[nm].bb[3] + 0.8
        t0, t1 = chains[names[0]].tap, chains[names[-1]].tap
        cv.rect("m1", t0[0] - 0.19, t0[1] - 0.19, t0[0] + 0.19, t1[1] + 0.19 + 2.6 * (chains[names[-1]].n - 1))
    # ------------------------------------------------------------------ decap under the plates
    decaps, dterms = [], []
    res_top = max(c.bb[3] for c in chains.values())
    yd = max(res_top, pmax + 2.5) + 3.3
    while yd + 14 < 88.5:
        units, t, bb = decap_row(cv, 0.5, 131.0, yd, 6.0, 10.0)
        decaps += units
        dterms += t
        yd = bb[3] + 3.4
    # ------------------------------------------------------------------ pass device (top band)
    ypass = 96.0
    pc = fet_cell(ly, "p", 4.0, 0.28, 48)
    pb = bbox(ly, pc)
    xpass = 0.8 - pb[0]
    mp = Fet(cv, "p", 4.0, 0.28, 48, xpass, ypass, "MPASS", dict(d="VOUT", g="GATE", s="VIN"))
    mp.spec = (192, 0.28, 48, "p")
    cv.rect("nwell", mp.bb[0] - 0.2, ypass - 3.2, mp.bb[2] + 0.2, mp.bb[3] + 0.6)
    tw = taps_row(cv, "n", mp.comp[0] + 0.4, mp.comp[2] - 0.4, ypass - 2.4, pitch=3.2)
    # VIN bus below the pass device: S strips extended down to an M1+M2 bus at y ypass-1.2
    yvin = ypass - 1.2
    for s in mp.s:
        cv.rect("m1", s[0], yvin, s[2], s[1] + 0.1)
    cv.rect("m1", mp.s[0][0], yvin - 0.45, mp.s[-1][2], yvin + 0.45)
    # n-taps share the bus row: move them to y ypass-2.4 (separate M1 rail, joined at the ends)
    cv.rect("m2", mp.s[0][0], yvin - 0.45, mp.s[-1][2], yvin + 0.45)
    for s in mp.s[::2]:
        xc = (s[0] + s[2]) / 2
        cv.pad("v1", xc, yvin, 0.26)
    cv.rect("m1", tw[0] - 0.2, ypass - 2.6, tw[0] + 0.2, yvin)                 # tap rail -> VIN bus
    # VOUT: D bar -> via stacks up to an M5 bus over the device, running west
    blocks = []
    for dd in mp.d:
        xc = snap((dd[0] + dd[2]) / 2)
        cv.via(xc, mp.yd, "m2", "m5")
        blocks.append(xc)
    yv5 = mp.yd
    cv.rect("m5", mp.d[0][0] - 0.3, yv5 - 1.0, mp.d[-1][2] + 0.3, yv5 + 1.2)
    cv.rect("m5", -0.5, yv5 - 1.0, mp.d[0][0] + 0.2, yv5 + 1.2)             # VOUT pin strip (west)
    cv.label("m5t", "VOUT", 0.5, yv5)
    # ------------------------------------------------------------------ MIM plates
    # fingers <= 28.7 um wide (MSLOT.1), each with its own bottom plate (MIMTM.11)
    ccomp = MimComb(cv, 3, 28.7, 87.0, 3.0, 3.2, top="GATE", bot="COMP", name="CCOMP")
    cbuf = MimComb(cv, 1, 28.7, 38.5, ccomp.bb[2] + 2.8, 3.2, top="BUF", bot="BCOMP", name="CBUF")
    # ------------------------------------------------------------------ routing
    ymax = max(cbuf.bb[3], mp.bb[3])
    r = Router(cv, 0.6, ymax - 0.6, -0.5, 136.0, debug=DEBUG and (ly.layer(42, 10), ly.layer(46, 10), ly.layer(36, 10)))
    ych = pmax + 2.0                                  # channel between the P row and the resistors
    for f in devs:
        r.add(f.terms())
    r.add(mp.terms("gs"))
    r.add([Term("VOUT", [b], mp.yd, "m2", "MPASS.d") for b in blocks[1:2]])
    firsts = {"RSETIN", "RBIAS", "RSETHI", "RFBHI"}
    upper = []
    for nm, c in chains.items():
        upper += c.terms(tap=nm in firsts)
    upper += dterms
    for t in upper:                                   # supplies above the channel use local tracks
        if t.net in ("VSS", "VIN"):
            t.net += "R"
    r.add(upper)
    r.add([Term("VSS", [x], 2.0, "m1", "ntap") for x in taps_n[::3]])
    r.add([Term("VIN", [x], pmax + 0.9, "m1", "wtap") for x in taps_w[::3]])
    g = lambda v: snap(0.6 + 0.8 * round((v - 0.6) / 0.8))           # router slot grid
    r.fixed_track.update({"VSS": g(yp - 1.8), "VIN": g(pmax + 1.9), "VSSR": g(ych + 8.0), "VINR": g(ych + 7.2)})
    for x0 in (8.0, 60.0, 110.0):
        r.add([Term("VSS", frange(x0, x0 + 6), r.fixed_track["VSSR"], "m4", "link_vss", link="VSSR"),
               Term("VIN", frange(x0 + 8, x0 + 14), r.fixed_track["VINR"], "m4", "link_vin", link="VINR")])
    hint = {n: ych + 3.0 for n in ("BIAS", "REF", "FB", "BUF", "BGATE", "DRIVE", "BCOMP", "COMP")}
    # VOUT stacks block M3/M4 for other nets
    for xc in blocks:
        r.blockage("m3", (xc - 0.2, mp.yd - 0.2, xc + 0.2, mp.yd + 0.2), "VOUT")
        r.blockage("m4", (xc - 0.2, mp.yd - 0.2, xc + 0.2, mp.yd + 0.2), "VOUT")
    ccomp.hook(r)
    cbuf.hook(r)
    # VCTRL / VIN / VSS pins: east edge on M4 tracks
    r.extra_track_x.setdefault("VCTRL", []).append(136.0)
    r.extra_track_x.setdefault("VIN", []).append(136.0)
    r.extra_track_x.setdefault("VSS", []).append(136.0)
    trk = r.solve(track_hint=hint)
    ccomp.finish(); cbuf.finish()
    vin_power(cv, mp, trk["VIN"])
    for net in ("VCTRL", "VIN", "VSS"):
        cv.label("m4t", net, 135.8, trk[net])
    print("tracks", {k: round(v, 2) for k, v in sorted(trk.items(), key=lambda kv: kv[1])})
    b = top.dbbox()
    print(f"{NAME}: bbox {b.left:.2f},{b.bottom:.2f} .. {b.right:.2f},{b.top:.2f}  ({b.width():.1f} x {b.height():.1f})")
    return top, devs + [mp], chains, (ccomp, cbuf), decaps


def netlist(devs, chains, mims, decaps):
    L = [f".subckt {NAME} VIN VCTRL VOUT VSS"]
    for f in devs:
        w, l, nf, kind = f.spec
        model = "nfet_03v3" if kind == "n" else "pfet_03v3"
        body = "VSS" if kind == "n" else "VIN"
        for i in range(nf):
            L.append(f"X{f.name}_{i} {f.nets['d']} {f.nets['g']} {f.nets['s']} {body} {model} w={w / nf:g}u l={l:g}u")
    for c in chains.values():
        L += c.spice()
    for m in mims:
        sp = m.spice()
        L += sp if isinstance(sp, list) else [sp]
    for i, (lc, wc) in enumerate(decaps):
        L.append(f"XCD{i} VOUT VSS cap_nmos_03v3 c_width={wc:g}u c_length={lc:g}u")
    L.append(f".ends {NAME}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ly = db.Layout(); ly.dbu = 0.001
    top, devs, chains, mims, decaps = build(ly)
    for c in list(ly.top_cells()):
        if c.cell_index() != top.cell_index():
            ly.delete_cell(c.cell_index())
    ly.write(os.path.join(HERE, NAME + ".gds"))
    open(os.path.join(HERE, NAME + ".spice"), "w", newline="\n").write(netlist(devs, chains, mims, decaps))
    print("decap units", len(decaps), "->", round(sum(l * w for l, w in decaps) * 4.0e-3, 1), "pF (inversion)")
