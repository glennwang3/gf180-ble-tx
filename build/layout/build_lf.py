#!/usr/bin/env python3
"""
PLL_LF_L: the A01 loop filter (VCTRL - Rz - LF_RZ - C2 - VSS, C1 VCTRL - VSS) in stacked form.

  C2 (143.8 pF nominal):  a 2x2 group of MIM-B top plates (VSS, MT) over ONE shared M5 bottom plate
                          (LF_RZ, MIMTM.11), and under it rows of abutted cap_nmos_03v3 units
                          (gate = LF_RZ through M2 gate buses + M2..M5 stacks in the plate gaps,
                          S/D = VSS through the U bars, the tap rails and M1 edge rails).
  Rz (440 kOhm nominal):  ppolyf_u_1k, 28 x 15.08 um segments (was the A01 41.3 kOhm; retuned with
                          Icp 2.5 uA for loop phase margin, see ../sim/retune/size.py).
  C1 (1.29 pF):           two cap_nmos_03v3 6 x 27 um units, gate = VCTRL.
  VSS:  M1 edge rails -> M5 islands (>= 1.2 um off the virtual bottom plate) -> MT straps that join
        all top plates; the cell VSS pin is the MT strap.
Writes PLL_LF_L.gds and PLL_LF_L.spice.
"""
import os
import klayout.db as db
from geom import Canvas, um
import pdkcells as P
from acell import RChain, taps_row, boxes, bbox, snap

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "PLL_LF_L"
NU, NR = 26, 7                  # MOS units per row, rows
LC, WC = 6.0, 20.4
GAPC = 3.0                      # gap between top plates (via4 lane)
INS = 1.6                       # top plate inset from the bottom-plate edge
YTAP_CP, YTAP_REG = 130.0, 11.2          # riser taps (cell-local y)
RZ_OHM, RZ_N = 440e3, 28
RZ_SEG = snap((RZ_OHM / RZ_N - 176.1) / 1030.5, 0.01)


def unit_geom(ly, lc, wc):
    c = P.moscap(ly, lc, wc)
    m1 = boxes(ly, c, 34)
    u = max(m1, key=lambda b: b[2] - b[0])
    gp = min(m1, key=lambda b: b[2] - b[0])
    return c, u, gp


def mos_row(cv, c, u, gp, x0, y0, n):
    """abutted units; U left edge at x0, comp bottom at y0.  Returns (gate bus y, U bar y, x span)."""
    pitch = snap(u[2] - u[0] - 1.0)
    xs = [x0 - u[0] + i * pitch for i in range(n)]
    for x in xs:
        cv.place(c, x, y0)
    gx = [x + (gp[0] + gp[2]) / 2 for x in xs]
    yg = y0 + gp[3] - 0.25
    for x in gx:
        cv.pad("m1", x, yg); cv.pad("v1", x, yg, 0.26)
    ybar = y0 + u[1] + 0.5
    ytap = y0 + u[1] - 0.55
    txs = taps_row(cv, "p", xs[0] + u[0] + 0.5, xs[-1] + u[2] - 0.5, ytap, pitch=3.0)
    cv.rect("m1", txs[0] - 0.2, ytap, txs[-1] + 0.2, y0 + u[1] + 0.05)
    return yg, ybar, (xs[0] + u[0], xs[-1] + u[2]), gx


def build(ly):
    top = ly.create_cell(NAME)
    cv = Canvas(ly, top)
    c, u, gp = unit_geom(ly, LC, WC)
    pitch = snap(u[2] - u[0] - 1.0)
    rowp = snap(WC + (gp[3] - WC) + (-u[1]) + 1.45)            # row pitch incl. the tap row
    Wb = snap((NU - 1) * pitch + (u[2] - u[0]))
    y0 = -u[1] + 0.95                                            # first comp bottom (tap row above y=0)
    rows = []
    for r in range(NR):
        rows.append(mos_row(cv, c, u, gp, 0.0, y0 + r * rowp, NU))
    Hb = snap(rows[-1][0] + 0.8)
    # ---------------- C2 MIM: K x 2 plates, fuse <= 28.7 um wide (MSLOT.1), own bottom plates ----------
    K = 6
    GY = 5.0                                                     # gap between the two plate rows
    wf = snap((Wb - 2 * INS - (K - 1) * GAPC) / K, 0.01)
    hf = snap((Hb - 2 * INS - GY) / 2, 0.01)
    assert wf <= 28.7
    fx = [snap(INS + i * (wf + GAPC)) for i in range(K)]
    fy = [INS, snap(INS + hf + GY)]
    mcell = P.mim(ly, wf, hf)
    for x in fx:
        for y in fy:
            cv.place(mcell, x, y)
    # bottom-plate tabs into the row gap, via4 rows, M4 strap under them (LF_RZ)
    ygc = INS + hf + GY / 2
    for x in fx:
        cv.rect("m5", x - 0.6, fy[0] + hf + 0.6, x + wf + 0.6, fy[0] + hf + 2.1)
        cv.rect("m5", x - 0.6, fy[1] - 2.1, x + wf + 0.6, fy[1] - 0.6)
        for k in range(int((wf - 0.6) / 0.9)):
            xx = x + 0.4 + k * 0.9
            cv.pad("v4", xx, fy[0] + hf + 1.35, 0.26)
            cv.pad("v4", xx, fy[1] - 1.35, 0.26)
    cv.rect("m4", 0.0, fy[0] + hf + 0.9, Wb, fy[1] - 0.9)
    # x-gap M4 straps (LF_RZ) from bottom to top; gate buses stack M2 -> M4 onto them
    lanes = [snap(fx[i] + wf + GAPC / 2) for i in range(K - 1)]
    for x in lanes:
        cv.rect("m4", x - 0.5, 0.3, x + 0.5, Hb - 0.3)
    for yg, ybar, (xa, xb), gx in rows:
        cv.hline("m2", gx[0], gx[-1], yg, w=0.40)
        for x in lanes:
            cv.via(x, yg, "m2", "m4")
    # ---------------- VSS: U bars -> edge rails (M1) -> M5 islands -> MT straps ----------------------
    xl, xr = -1.6, Wb + 1.6
    for yg, ybar, (xa, xb), gx in rows:
        cv.hline("m1", xl, xr, ybar, w=0.60)
    cv.rect("m1", xl - 0.3, 0.0, xl + 0.3, Hb)
    cv.rect("m1", xr - 0.3, 0.0, xr + 0.3, Hb)
    for x in (xl, xr):
        for yg, ybar, _, _ in rows:
            cv.via(x, ybar, "m1", "m5")
        cv.rect("m5", x - 0.5, 0.3, x + 0.5, Hb - 0.3)                  # island (VSS)
        n5 = int((Hb - 1.2) / 1.0)
        for k in range(n5):
            cv.pad("v5", x, 0.9 + k * 1.0, 0.26)
    cv.rect("mt", xl - 0.5, 0.3, INS + 1.0, Hb - 0.3)
    cv.rect("mt", Wb - INS - 1.0, 0.3, xr + 0.5, Hb - 0.3)
    # MT straps join every top plate (across the x-gaps), three per plate row
    for y in fy:
        for yy in (y + 2.0, y + hf / 2 - 1.0, y + hf - 4.0):
            cv.rect("mt", xl - 0.5, yy, xr + 0.5, yy + 2.0)
    cv.label("mtt", "VSS", xl, Hb / 2)
    cv.label("m4t", "LF_RZ", lanes[0], Hb / 2)
    # ---------------- side strip: Rz + C1 + VCTRL pin --------------------------------------------------
    c1, u1, gp1 = unit_geom(ly, 6.0, 27.0)
    xs0 = -22.0
    c1y0 = Hb - 27.0 - 1.5
    yg1, ybar1, (xa1, xb1), gx1 = mos_row(cv, c1, u1, gp1, xs0, c1y0, 2)
    cv.hline("m2", gx1[0], gx1[-1], yg1, w=0.40)
    cv.hline("m1", xb1, xl, ybar1, w=0.60)                          # C1 U bar -> VSS rail
    rz = RChain(cv, RZ_N, RZ_SEG, xs0 + 2.0, 6.0, "RZ", "VCTRL", "LF_RZ")
    # Rz VCTRL end (left, segment 0) and LF_RZ end (last segment: left side since n-1 odd -> side 0)
    (ax, ay), (bx, by) = rz.a, rz.b
    # LF_RZ end -> M2 -> stack to M4 -> M4 east into the plate at the left lane (x 0.8)
    yrz = by
    cv.pad("v1", bx, by, 0.26); cv.pad("m2", bx, by)
    cv.hline("m2", bx, bx - 1.0, by, w=0.40)
    cv.via(bx - 1.0, by, "m2", "m4")
    cv.hline("m4", bx - 1.0, lanes[0], by, w=0.40)
    # VCTRL end -> M2 west -> M3 riser up to the C1 gate bus and the pin
    xv = xs0 - 2.0
    cv.pad("v1", ax, ay, 0.26); cv.pad("m2", ax, ay)
    cv.hline("m2", ax, xv, ay, w=0.40)
    cv.via(xv, ay, "m2", "m3")
    cv.vline("m3", xv, ay, Hb - 0.5, w=0.40)
    cv.hline("m2", xv, gx1[0], yg1, w=0.40)
    cv.via(xv, yg1, "m2", "m3")
    cv.via(xv, Hb - 0.5, "m3", "m4")
    cv.label("m4t", "VCTRL", xv, Hb - 0.5)
    for yy in (YTAP_CP, YTAP_REG):                     # extra VCTRL taps on the riser (charge pump / regulator)
        cv.via(xv, yy, "m3", "m4")
    # Rz body taps / C1 taps: substrate (VSS) - tie the Rz tap rail to the VSS rail on M1 at its bottom
    cv.hline("m1", rz.tap[0], xl, rz.tap[1] - 0.9, w=0.40)
    cv.rect("m1", rz.tap[0] - 0.19, rz.tap[1] - 1.1, rz.tap[0] + 0.19, rz.tap[1])
    b = top.dbbox()
    nmos = NR * NU
    cmos = nmos * LC * WC * 3.983e-3
    cmim = 2 * K * (1.99e-3 * wf * hf + 0.2383e-3 * 2 * (wf + hf))
    print(f"{NAME}: bbox {b.left:.2f},{b.bottom:.2f} .. {b.right:.2f},{b.top:.2f} ({b.width():.1f} x {b.height():.1f}); "
          f"plates {2 * K} x {wf}x{hf}; C2 = {cmim:.1f} (MIM) + {cmos:.1f} (MOS @1.6V) = {cmim + cmos:.1f} pF")
    return top, dict(nmos=nmos, wp=wf, hp=hf, nplates=2 * K, rz=rz, Hb=Hb, Wb=Wb, xl=xl, xr=xr, xv=xv, fx=fx)


def netlist(info):
    L = [f".subckt {NAME} VCTRL VSS LF_RZ"]
    L += info["rz"].spice()
    for i in range(info["nplates"]):
        L.append(f"XC2M{i} VSS LF_RZ cap_mim_2f0_m5m6_noshield c_width={info['wp']:g}u c_length={info['hp']:g}u")
    for i in range(info["nmos"]):
        L.append(f"XC2N{i} LF_RZ VSS cap_nmos_03v3 c_width={WC:g}u c_length={LC:g}u")
    for i in range(2):
        L.append(f"XC1N{i} VCTRL VSS cap_nmos_03v3 c_width=27u c_length=6u")
    L.append(f".ends {NAME}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ly = db.Layout(); ly.dbu = 0.001
    top, info = build(ly)
    for cc in list(ly.top_cells()):
        if cc.cell_index() != top.cell_index():
            ly.delete_cell(cc.cell_index())
    ly.write(os.path.join(HERE, NAME + ".gds"))
    open(os.path.join(HERE, NAME + ".spice"), "w", newline="\n").write(netlist(info))
