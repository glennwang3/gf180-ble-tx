#!/usr/bin/env python3
"""
PLL_LF_L10: PLL_LF_L (build_lf.py, unchanged) + C1 raised from 1.29 pF to ~10 pF for the 1 MHz reference spur.

  C1X (~8.7 pF):  one row of K MIM-B plates (same width / gaps as C2) ABOVE the filter (cell-local y > Hb):
                  bottom plates (M5) = VCTRL: M5 tabs below the row -> via4 -> M4 strap -> M4 / M3 riser extension
                  of the existing VCTRL riser (x = xv);  top plates (MT) = VSS: MT straps across the row, joined to
                  the filter's VSS MT edge straps by MT columns at both edges.
  Linear (MIM): unlike the MOS C1 units it does not lose capacitance at low VCTRL (FF corner VCTRL ~0.65 V).
Writes PLL_LF_L10.gds and PLL_LF_L10.spice.
"""
import os
import klayout.db as db
import build_lf as B
import pdkcells as P
from geom import Canvas
from acell import snap

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "PLL_LF_L10"
C1X_PF = float(os.environ.get("C1X_PF", "8.71"))      # MIM part; + 1.29 pF MOS C1 = 10 pF
K = 6


def mim_pf(w, h):
    return 1.99e-3 * w * h + 0.2383e-3 * 2 * (w + h)


def build(ly):
    top, info = B.build(ly)
    top.name = NAME
    cv = Canvas(ly, top)
    Hb, Wb, xl, xr, xv, fx, wf = (info[k] for k in ("Hb", "Wb", "xl", "xr", "xv", "fx", "wp"))
    # plate height for the target capacitance (K plates of width wf)
    per = C1X_PF / K
    h = snap((per - 0.2383e-3 * 2 * wf) / (1.99e-3 * wf + 0.2383e-3 * 2), 0.01)
    fy = snap(Hb + 2.6)                                       # FuseTop bottom
    mcell = P.mim(ly, wf, h)
    for x in fx:
        cv.place(mcell, x, fy)
    # bottom-plate tabs (M5, VCTRL) below the row -> via4 row -> M4 strap
    for x in fx:
        cv.rect("m5", x - 0.6, fy - 2.1, x + wf + 0.6, fy - 0.6)
        for k in range(int((wf - 0.6) / 0.9)):
            cv.pad("v4", x + 0.4 + k * 0.9, fy - 1.35, 0.26)
    ys0, ys1 = fy - 1.85, fy - 0.85
    cv.rect("m4", xv - 0.3, ys0, Wb, ys1)
    # VCTRL riser: M3 (x = xv) up from the existing top via (Hb - 0.5) to the strap, via M3 -> M4
    cv.vline("m3", xv, Hb - 0.5, ys0 + 0.5, w=0.40)
    cv.via(xv, ys0 + 0.5, "m3", "m4")
    # VSS: MT straps across the row, MT edge columns joining them to the filter's VSS MT edge straps (top Hb - 0.3)
    yt = fy + h
    for yy in (fy + 2.0, fy + h / 2 - 1.0, fy + h - 4.0):
        cv.rect("mt", xl - 0.5, yy, xr + 0.5, yy + 2.0)
    cv.rect("mt", xl - 0.5, Hb - 1.0, fx[0] + 1.0, fy + h - 2.0)
    cv.rect("mt", fx[-1] + wf - 1.0, Hb - 1.0, xr + 0.5, fy + h - 2.0)
    cmim = K * mim_pf(wf, h)
    cmos1 = 2 * 6 * 27 * 3.983e-3
    b = top.dbbox()
    print(f"{NAME}: C1X {K} plates {wf} x {h} um = {cmim:.2f} pF (MIM) + C1 MOS {cmos1:.2f} pF = {cmim + cmos1:.2f} pF; "
          f"bbox {b.left:.2f},{b.bottom:.2f} .. {b.right:.2f},{b.top:.2f}")
    info.update(c1x_w=wf, c1x_h=h, c1x_n=K)
    return top, info


def netlist(info):
    base = B.netlist(info).replace(f".subckt {B.NAME} ", f".subckt {NAME} ").replace(f".ends {B.NAME}", "")
    add = [f"XC1M{i} VSS VCTRL cap_mim_2f0_m5m6_noshield c_width={info['c1x_w']:g}u c_length={info['c1x_h']:g}u"
           for i in range(info["c1x_n"])]
    return base.rstrip("\n") + "\n" + "\n".join(add) + f"\n.ends {NAME}\n"


if __name__ == "__main__":
    ly = db.Layout(); ly.dbu = 0.001
    top, info = build(ly)
    for cc in list(ly.top_cells()):
        if cc.cell_index() != top.cell_index():
            ly.delete_cell(cc.cell_index())
    ly.write(os.path.join(HERE, NAME + ".gds"))
    open(os.path.join(HERE, NAME + ".spice"), "w", newline="\n").write(netlist(info))
