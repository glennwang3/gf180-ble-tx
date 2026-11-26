#!/usr/bin/env python3
"""Fixed copy of the user's R TSPC flip-flop (Tri_State_Phase_Detector.gds, cell R_FlipFlop).  Original untouched.
Writes /foss/designs/Tri_State_Phase_Detector/R_FlipFlop_fixed.gds (cell R_FlipFlop, flattened):
  1. everything snapped to the 5 nm grid
  2. supplies (missing in the original: 4 separate 3v3 source nets, 5 separate vss source nets):
     3v3 M1 rail on an n-tap row along the top, M1 stubs up from the four pfet source pads;
     vss M1 rail on a p-tap row along the bottom, M1 stubs down from the five nfet source pads
  3. one n-well: the four pfet wells bridged + a top strip holding the n-tap row
  4. M1 labels named as in R_Flipflop.sch
"""
import sys
import klayout.db as db

sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of  # noqa: E402

SRC = "/foss/designs/Tri_State_Phase_Detector/Tri_State_Phase_Detector.gds"
OUT = "/foss/designs/Tri_State_Phase_Detector/R_FlipFlop_fixed.gds"
CELL = "R_FlipFlop"
U = 1000
B = lambda x0, y0, x1, y1: db.Box(round(x0 * U), round(y0 * U), round(x1 * U), round(y1 * U))
NW, COMP, PP, NP, CONT, M1, M1L = (21, 0), (22, 0), (31, 0), (32, 0), (33, 0), (34, 0), (34, 10)
VDD_PADS = [(-1.475, 2.66), (1.175, 2.66), (5.765, 1.86), (8.525, 1.46)]          # (x left, top) of 0.89 wide pads
VSS_PADS = [(-1.211, -2.20), (1.349, -3.00), (3.679, -2.20), (5.989, -3.00), (8.509, -2.60)]   # (x left, bottom), 0.38 wide


def contacts(sh, x0, x1, yc):
    n = int((x1 - x0 - 0.22 - 0.16) / 0.47) + 1
    ox = round((x0 + (x1 - x0 - (0.22 + (n - 1) * 0.47)) / 2) / 0.005) * 0.005
    for k in range(n):
        x = ox + k * 0.47
        sh.insert(B(x, yc - 0.11, x + 0.22, yc + 0.11))


def main():
    ly = db.Layout(); ly.read(SRC)
    out = db.Layout(); out.dbu = ly.dbu
    top = out.create_cell(CELL)
    top.copy_tree(ly.cell(CELL))
    top.flatten(-1, True)
    L = lambda l: out.layer(*l)
    for li in out.layer_indexes():                                # 1. grid
        sh = top.shapes(li)
        texts = [s.text.dup() for s in sh.each() if s.is_text()]
        r = db.Region(sh).merged().snapped(5, 5)
        sh.clear(); sh.insert(r)
        for t in texts:
            sh.insert(t)
    # 3. n-well
    nw = db.Region(top.shapes(L(NW))).merged()
    wells = sorted((p.bbox() for p in nw.each()), key=lambda b: b.left)
    for a, b in zip(wells, wells[1:]):
        nw.insert(db.Box(a.right, max(a.bottom, b.bottom), b.left, min(a.top, b.top)))
    bb = nw.bbox()
    nw += db.Region(db.Box(bb.left, round(1.90 * U), bb.right, round(4.05 * U)))
    nw.merge()
    top.shapes(L(NW)).clear(); top.shapes(L(NW)).insert(nw)
    # 2a. 3v3 rail + n-tap row (inside the well top strip)
    xl, xr = bb.left / U + 0.30, bb.right / U - 0.30
    top.shapes(L(COMP)).insert(B(xl, 3.45, xr, 3.81))
    top.shapes(L(NP)).insert(B(xl - 0.18, 3.27, xr + 0.18, 3.99))
    contacts(top.shapes(L(CONT)), xl, xr, 3.63)
    top.shapes(L(M1)).insert(B(xl, 3.46, xr, 3.80))
    for x, ytop in VDD_PADS:
        top.shapes(L(M1)).insert(B(x, ytop - 0.10, x + 0.89, 3.50))
    # 2b. vss rail + p-tap row
    xl2, xr2 = -2.80, 9.70
    top.shapes(L(COMP)).insert(B(xl2, -4.08, xr2, -3.72))
    top.shapes(L(PP)).insert(B(xl2 - 0.18, -4.26, xr2 + 0.18, -3.19))
    contacts(top.shapes(L(CONT)), xl2, xr2, -3.90)
    top.shapes(L(M1)).insert(B(xl2, -4.07, xr2, -3.73))
    for x, ybot in VSS_PADS:
        top.shapes(L(M1)).insert(B(x, -3.80, x + 0.38, ybot + 0.10))
    r = db.Region(top.shapes(L(M1))).merged().snapped(5, 5)
    top.shapes(L(M1)).clear(); top.shapes(L(M1)).insert(r)
    # 4. labels
    l2n, LL = l2n_of(out, top)
    probes = {"D": ("pc", (-2.20, 1.90)), "CLK_In": ("pc", (-2.20, 1.10)), "reset": ("pc", (0.45, 1.10)),
              "net2": ("sd", (-1.50, 0.40)), "net5": ("sd", (1.15, 0.40)), "CLK_Outb": ("sd", (5.75, 0.40)),
              "CLK_Out": ("sd", (8.50, 0.00)), "3v3": ("sd", (-0.60, 3.63)), "vss": ("sd", (0.00, -3.90))}
    for name, (k, (x, y)) in probes.items():
        n = l2n.probe_net(LL[k], db.DPoint(x, y))
        if n is None:
            print(f"label {name}: no net at probe"); continue
        rr = l2n.shapes_of_net(n, LL["met"][0], True).merged()
        if rr.is_empty():
            print(f"label {name}: net has no M1"); continue
        best = max(rr.decompose_trapezoids_to_region().each(), key=lambda p: p.area())
        c = best.bbox().center()
        top.shapes(L(M1L)).insert(db.Text(name, db.Trans(c.x, c.y)))
        print(f"label {name:9s} at ({c.x / U:.3f}, {c.y / U:.3f})")
    out.write(OUT)
    print("wrote", OUT, top.dbbox())


if __name__ == "__main__":
    main()
