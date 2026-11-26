#!/usr/bin/env python3
"""Fixed copy of the user's SR TSPC flip-flop (Tri_State_Phase_Detector.gds, cell SR_FlipFlop).  Original untouched.
Writes /foss/designs/Tri_State_Phase_Detector/SR_FlipFlop_fixed.gds (cell SR_FlipFlop, flattened):
  1. all layers snapped to the 5 nm grid (the transistor cells drew 0.382 um M1 strips at 0.089 / 0.471)
  2. one n-well: the six per-pfet wells merged (horizontal closing) + a strip on top holding an n-tap row
     (NCOMP + NPLUS + contacts + M1) tied to 3v3 by M1 stubs from the 3v3 pads at the top
  3. a p-tap row (PCOMP + PPLUS + contacts) under the nfets, its M1 merged into the vss bar
  4. M1.2a: the four via pads 0.225 um from the neighbouring M1 trimmed by 5 nm on that side
  5. M1 labels (34/10) on every net that has M1, named as in SR_Flipflop.sch
"""
import sys
import klayout.db as db

sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of  # noqa: E402

SRC = "/foss/designs/Tri_State_Phase_Detector/Tri_State_Phase_Detector.gds"
OUT = "/foss/designs/Tri_State_Phase_Detector/SR_FlipFlop_fixed.gds"
U = 1000
B = lambda x0, y0, x1, y1: db.Box(round(x0 * U), round(y0 * U), round(x1 * U), round(y1 * U))
NW, COMP, POLY, PP, NP, CONT, M1, M1L = (21, 0), (22, 0), (30, 0), (31, 0), (32, 0), (33, 0), (34, 0), (34, 10)


def contacts(sh, x0, x1, yc):
    """0.22 contacts at pitch 0.47 centred on row yc between x0 and x1"""
    n = int((x1 - x0 - 0.22 - 0.16) / 0.47) + 1          # >= 0.08 COMP enclosure at the row ends
    ox = round((x0 + (x1 - x0 - (0.22 + (n - 1) * 0.47)) / 2) / 0.005) * 0.005
    for k in range(n):
        x = ox + k * 0.47
        sh.insert(B(x, yc - 0.11, x + 0.22, yc + 0.11))


def main():
    ly = db.Layout(); ly.read(SRC)
    src = ly.cell("SR_FlipFlop")
    out = db.Layout(); out.dbu = ly.dbu
    top = out.create_cell("SR_FlipFlop")
    top.copy_tree(src)                      # copy of the whole hierarchy ...
    top.flatten(-1, True)                   # ... flattened into SR_FlipFlop
    L = lambda l: out.layer(*l)
    # 1. snap everything to the 5 nm grid
    for li in out.layer_indexes():
        sh = top.shapes(li)
        texts = [s.text.dup() for s in sh.each() if s.is_text()]
        r = db.Region(sh).merged().snapped(5, 5)
        sh.clear(); sh.insert(r)
        for t in texts:
            sh.insert(t)
    # 2. n-well: merge (close gaps < 1.8 um horizontally) + top strip; n-tap row
    nw = db.Region(top.shapes(L(NW))).merged()
    wells = sorted((p.bbox() for p in nw.each()), key=lambda b: b.left)
    for a, b in zip(wells, wells[1:]):                      # bridge neighbouring wells over their common y range
        nw.insert(db.Box(a.right, max(a.bottom, b.bottom), b.left, min(a.top, b.top)))
    bb = nw.bbox()
    nw += db.Region(db.Box(bb.left, round(2.30 * U), bb.right, round(4.90 * U)))
    nw.merge()
    top.shapes(L(NW)).clear(); top.shapes(L(NW)).insert(nw)
    xl, xr = bb.left / U + 0.30, bb.right / U - 0.30
    top.shapes(L(COMP)).insert(B(xl, 4.30, xr, 4.66))
    top.shapes(L(NP)).insert(B(xl - 0.18, 4.12, xr + 0.18, 4.84))
    contacts(top.shapes(L(CONT)), xl, xr, 4.48)
    top.shapes(L(M1)).insert(B(xl, 4.31, xr, 4.65))
    for x0, x1 in ((-0.355, 0.535), (2.315, 3.205)):          # 3v3 pads at the top of the two tall pfets
        top.shapes(L(M1)).insert(B(x0, 3.50, x1, 4.40))
    # 3. p-tap row under the nfets; M1 band up into the vss bar (only vss M1 lives below y -1.8)
    m1 = db.Region(top.shapes(L(M1))).merged()
    vss_bar = m1 & db.Region(B(-4.0, -2.2, 12.0, -1.80))
    vb = vss_bar.bbox()
    xl2, xr2 = vb.left / U + 0.05, vb.right / U - 0.05
    top.shapes(L(COMP)).insert(B(xl2, -3.06, xr2, -2.70))
    top.shapes(L(PP)).insert(B(xl2 - 0.18, -3.24, xr2 + 0.18, -2.52))
    contacts(top.shapes(L(CONT)), xl2, xr2, -2.88)
    top.shapes(L(M1)).insert(B(vb.left / U, -3.05, vb.right / U, -1.90))
    # 4. trim the four via pads (5 nm) that sit 0.225 um from the next M1
    trim = [B(-1.80, -1.575, -1.30, -1.565), B(2.01, -1.575, 2.51, -1.565), B(6.01, -1.575, 6.51, -1.565),
            B(6.44, 2.345, 6.94, 2.355)]
    r = db.Region(top.shapes(L(M1))).merged() - db.Region(trim)
    top.shapes(L(M1)).clear(); top.shapes(L(M1)).insert(r)
    # 5. labels: identify the nets by the device terminals found in the extraction, put the text on their M1
    l2n, LL = l2n_of(out, top)
    probes = {  # name: (layer key, point) - magic node coordinates of the extraction (x 0.005 um)
        "set": ("pc", (-3.80, 1.21)), "D": ("pc", (-1.70, -1.37)), "CLK_In": ("pc", (-1.10, 1.27)),
        "reset": ("pc", (1.57, 2.06)), "net8": ("sd", (-3.10, 0.50)), "net3": ("sd", (-1.00, -1.15)),
        "net5": ("sd", (2.27, 1.35)), "CLK_Outb": ("sd", (6.80, -0.35)), "CLK_Out": ("sd", (10.62, 1.20)),
        "3v3": ("sd", (-3.10, 1.90)), "vss": ("sd", (-3.10, -2.05)),
    }
    for name, (k, (x, y)) in probes.items():
        n = l2n.probe_net(LL[k], db.DPoint(x, y))
        if n is None:
            print(f"label {name}: no net at probe"); continue
        r = l2n.shapes_of_net(n, LL["met"][0], True).merged()
        if r.is_empty():
            print(f"label {name}: net has no M1"); continue
        best = max(r.decompose_trapezoids_to_region().each(), key=lambda p: p.area())
        c = best.bbox().center()
        top.shapes(L(M1L)).insert(db.Text(name, db.Trans(c.x, c.y)))
        print(f"label {name:9s} at ({c.x / U:.3f}, {c.y / U:.3f})")
    out.write(OUT)
    print("wrote", OUT, top.dbbox())


if __name__ == "__main__":
    main()
