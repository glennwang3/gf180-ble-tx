#!/usr/bin/env python3
"""Three-state PFD of Centurelli et al. (Fig. 4, 'Robust three-state PFD architecture with enhanced frequency
acquisition capabilities') from the user's fixed cells.  Writes /foss/designs/Tri_State_Phase_Detector/TS_PFD.gds.

  FF1 = SR_FlipFlop  D=3v3  CLK=R  set=SR  reset=RS  Q=UP        FF2 = SR_FlipFlop  D=3v3  CLK=V  set=SV  reset=RS  Q=DN
  FF3 = R_FlipFlop   D=FZR  CLK=R  reset=SR   Q=ER               FF4 = R_FlipFlop   D=FZV  CLK=V  reset=SV   Q=EV
  RS  = 2_Input_And(UP, DN)          FZR = 2_Input_Or(UP, RS)          FZV = 2_Input_Or(DN, RS)
  SR  = 2_Input_And_Inv_Input(A=FZR inverted, B=ER)                    SV  = 2_Input_And_Inv_Input(A=FZV, B=EV)
The dashed FZ-detector reset of Fig. 4 is used, without the pulse generators: FF3.reset = SR, FF4.reset = SV
(without it ER / EV stay high and the set / reset loop rings).
Routing: cells are M1-M4 only; every pin gets a via stack M1 -> MetalTop at an access point (access.py) and the
nets are routed on M5 / MetalTop with the route_top maze router.
"""
import os
import sys
import klayout.db as db

sys.path.insert(0, "/foss/designs/pll_compact/layout")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from route_top import Grid, Draw, LAY, U  # noqa: E402
from access import access  # noqa: E402
import numpy as np  # noqa: E402

D = "/foss/designs/Tri_State_Phase_Detector"
OUT = f"{D}/TS_PFD.gds"
TOP = "TS_PFD"
CELLS = {"SR": ("SR_FlipFlop_fixed.gds", "SR_FlipFlop"), "R": ("R_FlipFlop_fixed.gds", "R_FlipFlop"),
         "AND": ("2_Input_And_fixed.gds", "2_Input_And"), "ANDI": ("2_Input_And_Inv_Input_fixed.gds", "2_Input_And_Inv_Input"),
         "OR": ("2_Input_Or_fixed.gds", "2_Input_Or")}
# instance: (cell key, x, y, mirror in y)   row U at y 0, row D mirrored at y -12
INST = {"FF3": ("R", 2.98, 0.0, False), "SRM": ("ANDI", 21.40, 0.0, False), "FZRG": ("OR", 32.28, 0.0, False),
        "FF1": ("SR", 43.90, 0.0, False),
        "FF4": ("R", 2.98, -14.0, True), "SVM": ("ANDI", 21.40, -14.0, True), "FZVG": ("OR", 32.28, -14.0, True),
        "FF2": ("SR", 43.90, -14.0, True),
        "RSG": ("AND", 62.35, -7.0, False),
        "UPBG": ("ANDI", 75.70, -7.0, False)}          # UPB = NOT UP for the A01 charge pump (B tied high)
CONN = {  # top net: [(instance, pin)]
    "R": [("FF1", "CLK_In"), ("FF3", "CLK_In")],
    "V": [("FF2", "CLK_In"), ("FF4", "CLK_In")],
    "UP": [("FF1", "CLK_Out"), ("RSG", "A"), ("FZRG", "A"), ("UPBG", "A")],
    "UPB": [("UPBG", "Y")],
    "DN": [("FF2", "CLK_Out"), ("RSG", "B"), ("FZVG", "A")],
    "RS": [("RSG", "Y"), ("FF1", "reset"), ("FF2", "reset"), ("FZRG", "B"), ("FZVG", "B")],
    "FZR": [("FZRG", "Y"), ("FF3", "D"), ("SRM", "A")],
    "FZV": [("FZVG", "Y"), ("FF4", "D"), ("SVM", "A")],
    "ER": [("FF3", "CLK_Out"), ("SRM", "B")],
    "EV": [("FF4", "CLK_Out"), ("SVM", "B")],
    "SR": [("SRM", "Y"), ("FF1", "set"), ("FF3", "reset")],      # dashed path of Fig. 4: the set pulse resets the FZ-detector
    "SV": [("SVM", "Y"), ("FF2", "set"), ("FF4", "reset")],
    "3v3": [(i, "3v3") for i in INST] + [("FF1", "D"), ("FF2", "D"), ("UPBG", "B")],
    "vss": [(i, "vss") for i in INST],
}
# external ports: M5 landings just below the cell's bottom edge (faces the divider / charge pump in PLL_TSPFD)
EXT_Y = -26.0
EXT = {"R": (4.0, EXT_Y), "V": (10.0, EXT_Y), "DN": (16.0, EXT_Y), "UPB": (22.0, EXT_Y), "vss": (30.0, EXT_Y),
       "3v3": (38.0, EXT_Y)}
ESCAPE = {("OR", "A"): ((-1.655, -0.73, -1.425, -0.33), (-3.60, -0.73), -3.30)}   # A is a 0.23 um M1 strip here; NOR output starts at x -0.97


class Fail(Exception):
    pass


def main(order):
    ly = db.Layout()
    cells = {}
    for k, (f, cn) in CELLS.items():
        ly.read(f"{D}/{f}")
        cells[k] = ly.cell(cn)
    top = ly.create_cell(TOP)
    d = Draw(ly, top)
    acc = {k: access(f"{D}/{f}", cn) for k, (f, cn) in CELLS.items()}
    vias = {}
    for k, (f, cn) in CELLS.items():
        c_ = cells[k]
        vias[k] = {(round(q.bbox().center().x / 5) * 5 / U, round(q.bbox().center().y / 5) * 5 / U)
                   for q in db.Region(c_.begin_shapes_rec(ly.layer(35, 0))).merged().each()}
    trans = {}
    for name, (k, x, y, mir) in INST.items():
        t = db.Trans(0, mir, round(x * U), round(y * U))          # mirror: y -> -y
        top.insert(db.CellInstArray(cells[k].cell_index(), t))
        trans[name] = t
    gp = lambda inst, xy: (lambda p: (p.x / U, p.y / U))(trans[inst] * db.Point(round(xy[0] * U), round(xy[1] * U)))
    # pin points (global) and via stacks M1 -> MT
    land = []
    for net, pins in CONN.items():
        for inst, pin in pins:
            k = INST[inst][0]
            if (k, pin) in ESCAPE:
                box, (ex, ey), sx = ESCAPE[(k, pin)]
                b0 = gp(inst, (box[0], box[1])); b1 = gp(inst, (box[2], box[3]))
                e0 = gp(inst, (ex, ey))
                d.rect("m1", min(b0[0], b1[0], e0[0]), min(b0[1], b1[1]), max(b0[0], b1[0]), max(b0[1], b1[1]), net)
                xs, ys = gp(inst, (sx, (box[1] + box[3]) / 2))
                lo = "m1"
            else:
                xs, ys = gp(inst, acc[k][pin])
                lo = "m2" if acc[k][pin] in vias[k] else "m1"         # on an existing via1: keep the cell's M1 pad
            d.stack(xs, ys, lo, "m5", net)                            # pins land on M5: MetalTop stays free above
            land.append((net, xs, ys))
    for net, (x, y) in EXT.items():                       # boundary ports join their nets in the maze route
        d.rect("m5", x - 0.4, y - 0.4, x + 0.4, y + 0.4, net)
        land.append((net, x, y))
    # maze route on M5 / MT
    b = top.dbbox()
    g = Grid(b.left - 4, b.bottom - 4, b.right + 4, b.top + 4)
    Grid.WW = {"m5": 1.2, "mt": 1.2}
    for l, box, net in d.shapes:
        if l in ("m5", "mt"):
            g.add(l, box, net)
    for l in ("m5", "mt"):                                   # nothing routes below the port row
        g.add(l, (b.left - 4, b.bottom - 4, b.right + 4, EXT_Y - 1.2))
    for net, (x, y) in EXT.items():                          # keep MetalTop over each port free for the top-level stack
        g.add("mt", (x - 0.4, y - 0.4, x + 0.4, y + 0.4), net)
    nets = {}
    for net, x, y in land:
        nets.setdefault(net, []).append((x, y))
    landing = {}
    for net in order:                                       # all pin landings (M5 stubs to the grid) first
        for (x, y) in nets[net]:
            i, j = g.ij(x, y)
            gx, gy = g.xy(i, j)
            d.wire("m5", (x, y), (gx, y), 0.6, net); d.wire("m5", (gx, y), (gx, gy), 0.6, net)
            g.add("m5", (min(x, gx) - 0.3, y - 0.3, max(x, gx) + 0.3, y + 0.3), net)
            g.add("m5", (gx - 0.3, min(y, gy) - 0.3, gx + 0.3, max(y, gy) + 0.3), net)
            landing.setdefault(net, []).append((i, j, 0))
    for net in order:
        c = 1 if net in ("3v3", "vss") else 0
        nodes = landing[net]
        tree = {nodes[0]}
        pin_nodes = [(n[0], n[1]) for n in nodes]
        near = lambda a: any(abs(a[0] - p[0]) * g.P <= 1.5 and abs(a[1] - p[1]) * g.P <= 1.5 for p in pin_nodes)
        total = 0
        for tgt in nodes[1:]:
            if tgt in tree:
                continue
            path = g.route(net, list(tree), [tgt], c, (0, 0, g.nx - 1, g.ny - 1))
            cc = c
            if path is None and c:
                path = g.route(net, list(tree), [tgt], 0, (0, 0, g.nx - 1, g.ny - 1)); cc = 0
            if path is None:
                print(f"route failed: {net} -> {g.xy(tgt[0], tgt[1])}"); ly.write(OUT.replace(".gds", "_fail.gds")); raise Fail(net)
            tree |= set(path)
            total += len(path)
            for a, b_ in zip(path, path[1:]):
                (xa, ya), (xb, yb) = g.xy(a[0], a[1]), g.xy(b_[0], b_[1])
                if a[2] == b_[2]:
                    l = "mt" if a[2] else "m5"
                    w = Grid.W[l] if (not cc or near(a) or near(b_)) else Grid.WW[l]
                    d.wire(l, (xa, ya), (xb, yb), w, net)
                    g.add(l, (min(xa, xb) - w / 2, min(ya, yb) - w / 2, max(xa, xb) + w / 2, max(ya, yb) + w / 2), net)
                else:
                    d.stack(xa, ya, "m5", "mt", net)
                    g.add("m5", (xa - 0.3, ya - 0.3, xa + 0.3, ya + 0.3), net); g.add("mt", (xa - 0.4, ya - 0.4, xa + 0.4, ya + 0.4), net)
        print(f"{net:5s} {len(nodes)} pins ~{total * g.P:.0f} um")
        # close same-net notches
        for l, sp in (("m5", 300), ("mt", 480)):
            r = db.Region()
            for ll, box, nn in d.shapes:
                if ll == l and nn == net:
                    r.insert(db.Box(*[round(v * U) for v in box]))
            r.merge()
            for p in (r.sized(sp // 2 + 5).sized(-(sp // 2 + 5)) - r).each():
                top.shapes(ly.layer(*LAY[l])).insert(p)
    # top labels (MT) at the first landing of each external net
    for net in ("R", "V", "UPB", "DN", "3v3", "vss"):
        d.label("m5", net, *EXT[net])
    d.label("m5", "UP", *nets["UP"][0])
    ly.write(OUT, db.SaveLayoutOptions())
    bb = top.dbbox()
    print(f"wrote {OUT}: {bb.width():.1f} x {bb.height():.1f} um")


if __name__ == "__main__":
    order = ["R", "V", "RS", "UP", "UPB", "DN", "FZR", "FZV", "ER", "EV", "SR", "SV", "vss", "3v3"]
    for attempt in range(int(os.environ.get('TRIES', '60'))):
        try:
            main(order); break
        except Fail as e:
            n = e.args[0]
            order = [n] + [x for x in order if x != n]
            print("retry with order", order)
