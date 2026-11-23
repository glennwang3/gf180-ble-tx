#!/usr/bin/env python3
"""
Route PLL_COMPACT (stage 2).

 1. hand routes for the short / critical links (CORE_CLK, MC, FB_1M, XP/XN, VDD_VCO, VCTRL jumper)
 2. pin escapes to MetalTop with the A01 integration router's A* (assemble_layout.Router.access)
 3. a raster M5/MT router joins the escape landings (wide MT for VDD/VSS)
 4. port labels; writes PLL_COMPACT.gds + pins.json
"""
import heapq
import json
import os
import sys
import numpy as np
import klayout.db as db

sys.path.insert(0, "/foss/designs/pll_integration_repo/build")
from assemble_layout import Router                      # noqa: E402
import build_top as BT                                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
U = 1000
LAY = {"m1": (34, 0), "v1": (35, 0), "m2": (36, 0), "v2": (38, 0), "m3": (42, 0), "v3": (40, 0),
       "m4": (46, 0), "v4": (41, 0), "m5": (81, 0), "v5": (82, 0), "mt": (53, 0)}
MET = ["m1", "m2", "m3", "m4", "m5", "mt"]
VIA = ["v1", "v2", "v3", "v4", "v5"]
LBL = {"m1": (34, 10), "m2": (36, 10), "m3": (42, 10), "m4": (46, 10), "m5": (81, 10), "mt": (53, 10)}


class Draw:
    def __init__(self, ly, top):
        self.ly, self.top = ly, top
        self.shapes = []                 # (layer, box_um, net) of everything we draw (for the grid router)

    def rect(self, l, x0, y0, x1, y1, net=None):
        x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1))
        b = db.Box(round(x0 * U / 5) * 5, round(y0 * U / 5) * 5, round(x1 * U / 5) * 5, round(y1 * U / 5) * 5)
        self.top.shapes(self.ly.layer(*LAY[l])).insert(b)
        self.shapes.append((l, (x0, y0, x1, y1), net))

    def wire(self, l, a, b, w, net=None):
        (x0, y0), (x1, y1) = a, b
        self.rect(l, min(x0, x1) - w / 2, min(y0, y1) - w / 2, max(x0, x1) + w / 2, max(y0, y1) + w / 2, net)

    def stack(self, x, y, lo, hi, net=None, pad=0.40):
        i0, i1 = MET.index(lo), MET.index(hi)
        for i in range(i0, i1 + 1):
            p = 0.80 if MET[i] == "mt" else (0.60 if MET[i] == "m5" else pad)
            self.rect(MET[i], x - p / 2, y - p / 2, x + p / 2, y + p / 2, net)
        for i in range(i0, i1):
            self.rect(VIA[i], x - 0.13, y - 0.13, x + 0.13, y + 0.13, net)

    def label(self, l, text, x, y):
        self.top.shapes(self.ly.layer(*LBL[l])).insert(db.Text(text, db.Trans(round(x * U), round(y * U))))


# ------------------------------------------------------------------------------------------------- 1
def hand_routes(d):
    # CORE_CLK: VCO CORE_CLK M5 (via4 at -7.31,14.99) -> via5 -> MT north -> prescaler CLK_IN (M2) through
    # the M5 opening at x -7.0
    d.stack(-7.31, 14.99, "m5", "mt", "CORE_CLK")
    d.wire("mt", (-7.31, 14.99), (-7.31, 26.91), 0.8, "CORE_CLK")
    d.wire("mt", (-7.31, 26.91), (-7.0, 26.91), 0.8, "CORE_CLK")
    d.stack(-7.0, 26.91, "m2", "mt", "CORE_CLK")
    # MC: prescaler MC pad (M2, -4.71 24.26) -> M4 east -> divider modulus_33 (M3, 22.28 24.26)
    d.stack(-4.71, 24.26, "m2", "m4", "MC")
    d.wire("m4", (-4.71, 24.26), (22.28, 24.26), 0.40, "MC")
    d.stack(22.28, 24.26, "m3", "m4", "MC")
    # FB_1M: divider clk_feedback (M3, 73.56 32.10) -> PFD F_VCO (M3, 77.79 32.10)
    d.wire("m3", (73.56, 32.10), (77.79, 32.10), 0.40, "FB_1M")
    # XP / XN: VCO stubs (M3, bottom edge) -> converter pins (M3)
    d.wire("m3", (-12.72, -41.33), (-12.72, -44.03), 0.40, "XN")
    # XP crosses XN on M4 (the converter is mirrored: its XP pin sits west of XN)
    d.wire("m3", (-7.22, -41.33), (-7.22, -42.60), 0.40, "XP")
    d.stack(-7.22, -42.60, "m3", "m4", "XP")
    d.wire("m4", (-7.22, -42.60), (-19.02, -42.60), 0.40, "XP")
    d.stack(-19.02, -42.60, "m3", "m4", "XP")
    d.wire("m3", (-19.02, -42.60), (-19.02, -44.03), 0.40, "XP")
    # VDD_VCO: regulator VOUT M5 strip (west edge x 12.82, y -2.85..-0.65) -> VCO VDD landing (M4 -2.6 -1.85)
    d.rect("m5", -3.0, -2.85, 13.2, -0.65, "VDD_VCO")
    d.stack(-2.60, -1.85, "m4", "m5", "VDD_VCO")
    d.stack(-1.60, -1.85, "m4", "m5", "VDD_VCO")
    # VSS for the VCO prescaler-buffer tail source: its M4 island (x -0.90..4.51, y 0.95..3.66) is grounded only
    # through a substrate tap inside the VCO (the old A01 top metal bridged it) -> M4 link to the VSS landing
    d.wire("m4", (-0.70, 2.00), (-0.70, 0.30), 0.40, "VSS")
    d.wire("m4", (-0.70, 0.30), (-4.50, 0.30), 0.40, "VSS")
    d.wire("m4", (-4.50, 0.30), (-4.50, -6.34), 0.40, "VSS")
    d.wire("m4", (-4.50, -6.34), (-3.74, -6.34), 0.40, "VSS")
    # VCTRL: regulator pin (M4, 149.12 -89.47) -> loop-filter riser tap (M4, 152.70 -89.47)
    d.wire("m4", (149.12, -89.47), (152.70, -89.47), 0.40, "VCTRL")


# ------------------------------------------------------------------------------------------------- 2
# (net, block, level, x, y): pins that need a MetalTop landing.  level 0..5 = M1..MT
PINS = [
    ("PRESCALED", "prescaler", 2, 4.33, 30.58), ("PRESCALED", "divider", 2, 73.56, 51.14),
    ("UPB", "pfd", 0, 80.80, 30.47), ("UPB", "pump", 1, 101.55, 32.57),
    ("DN", "pfd", 1, 83.45, 29.52), ("DN", "pump", 1, 101.83, 26.72),
    ("VCTRL", "pump", 0, 102.60, 30.27), ("VCTRL", "lf", 3, 152.70, 29.33),
    ("CP_IBIAS", "pump", 0, 99.55, 28.86), ("CP_IBIAS", "bias", 3, 108.20, 32.60),
    ("TAIL_BIAS", "bias", 3, 108.20, 19.80), ("TAIL_BIAS", "vco", 4, 5.27, 1.71),
    ("RST_N", "divider", 1, 55.64, 6.34), ("RST_N", "tx", 2, -60.28, -81.28),
    ("VDD", "vco", 4, -5.19, 18.90), ("VDD", "vco", 3, -22.40, 7.39), ("VDD", "vco", 1, 1.20, -37.93),
    ("VDD", "conv", 3, 1.68, -63.51), ("VDD", "prescaler", 3, -0.38, 31.91),
    ("VDD", "divider", 4, 48.0, 18.90), ("VDD", "divider", 4, 48.0, 43.90),
    ("VDD", "pfd", 3, 85.0, 33.50), ("VDD", "pump", 3, 96.0, 34.40), ("VDD", "bias", 3, 108.20, 35.00),
    ("VDD", "reg", 5, 146.12, -75.07), ("VDD", "tx", 4, -195.04, 82.67),
    ("VSS", "vco", 3, -3.74, -6.34), ("VSS", "conv", 3, 1.68, -79.51), ("VSS", "prescaler", 4, 15.0, 33.01),
    ("VSS", "divider", 4, 48.0, 22.20), ("VSS", "divider", 4, 48.0, 47.20),
    ("VSS", "pfd", 4, 85.0, 27.40), ("VSS", "pump", 4, 97.35, 30.0), ("VSS", "bias", 3, 108.20, 15.00),
    ("VSS", "reg", 3, 149.12, -87.07), ("VSS", "tx", 4, -230.0, 85.97),
]


def escapes(ly, top, d):
    terms = []
    for net, blk, lev, x, y in PINS:
        terms.append({"block": blk, "pin": net, "net": net,
                      "pins": [{"pin": net, "level": lev, "xy": [round(x * U), round(y * U)]}]})
    r = Router(ly, top, terms)
    fuse = db.Region(top.begin_shapes_rec(ly.layer(75, 0)))
    r.fuse_near = fuse.sized(1200)
    r.mim_bottom = r.native[4].interacting(fuse)
    land = []
    for t in terms:
        net = t["net"]
        p = t["pins"][0]
        path = r.access(p, net, None, 800)
        if path is None:
            raise RuntimeError(f"no escape for {t['block']}.{net} at {p['xy']}")
        for a, b in zip(path, path[1:]):
            z = a[2]
            r.trace(z, net, a, b)
            if z != b[2]:
                r.trace(b[2], net, b, b)
                r.via(z, a)
        x, y, _ = path[-1]
        # record the drawn escape for the grid router as own-net shapes on M5/MT
        for z, (a, b) in ((pp[2], (pp, qq)) for pp, qq in zip(path, path[1:]) if pp[2] == qq[2]):
            if z >= 4:
                w = (520 if z == 4 else 800) / 2
                d.shapes.append(("m5" if z == 4 else "mt", ((min(a[0], b[0]) - w) / U, (min(a[1], b[1]) - w) / U,
                                                           (max(a[0], b[0]) + w) / U, (max(a[1], b[1]) + w) / U), net))
        d.shapes.append(("mt", ((x - 400) / U, (y - 400) / U, (x + 400) / U, (y + 400) / U), net))
        for (px, py, pz) in path:
            if pz == 4:
                d.shapes.append(("m5", ((px - 260) / U, (py - 260) / U, (px + 260) / U, (py + 260) / U), net))
        land.append((net, t["block"], x / U, y / U))
        print(f"escape {t['block']:9s} {net:10s} -> MT ({x / U:.2f},{y / U:.2f})  {len(path)} steps", flush=True)
    return land


# ------------------------------------------------------------------------------------------------- 3
class Grid:
    P = 0.75
    SP = {"m5": 0.40, "mt": 0.70}
    W = {"m5": 0.60, "mt": 0.80}
    WW = {"m5": 2.0, "mt": 2.0}           # wide (power)

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = x0, y0
        self.nx = int((x1 - x0) / self.P) + 1
        self.ny = int((y1 - y0) / self.P) + 1
        # blocked counts per layer for normal / wide wires, and per-net own counts
        self.blk = {(l, c): np.zeros((self.nx, self.ny), np.int32) for l in ("m5", "mt") for c in (0, 1)}
        self.own = {}
        self.via_blk = np.zeros((self.nx, self.ny), bool)

    def ij(self, x, y):
        return int(round((x - self.x0) / self.P)), int(round((y - self.y0) / self.P))

    def xy(self, i, j):
        return self.x0 + i * self.P, self.y0 + j * self.P

    def _span(self, a, b, d, n):
        i0 = max(0, int(np.ceil((a - d - (self.x0 if n == 0 else self.y0)) / self.P - 1e-9)))
        i1 = min((self.nx if n == 0 else self.ny) - 1, int(np.floor((b + d - (self.x0 if n == 0 else self.y0)) / self.P + 1e-9)))
        return i0, i1

    def add(self, l, box, net=None, sign=1):
        if l not in ("m5", "mt"):
            return
        x0, y0, x1, y1 = box
        for c in (0, 1):
            d = self.SP[l] + (self.WW[l] if c else self.W[l]) / 2
            i0, i1 = self._span(x0, x1, d, 0)
            j0, j1 = self._span(y0, y1, d, 1)
            if i0 > i1 or j0 > j1:
                continue
            self.blk[(l, c)][i0:i1 + 1, j0:j1 + 1] += sign
            if net is not None:
                key = (net, l, c)
                if key not in self.own:
                    self.own[key] = np.zeros((self.nx, self.ny), np.int32)
                self.own[key][i0:i1 + 1, j0:j1 + 1] += sign

    def own_add(self, l, box, net):
        for c in (0, 1):
            d = self.SP[l] + (self.WW[l] if c else self.W[l]) / 2
            i0, i1 = self._span(box[0], box[2], d, 0); j0, j1 = self._span(box[1], box[3], d, 1)
            key = (net, l, c)
            self.own.setdefault(key, np.zeros((self.nx, self.ny), np.int32))
            self.own[key][i0:i1 + 1, j0:j1 + 1] += 1

    def free(self, net, l, c):
        b = self.blk[(l, c)]
        o = self.own.get((net, l, c))
        return (b == 0) if o is None else (b - o == 0)

    def route(self, net, src, dst, c, win):
        """A* from a set of (i,j,layer) sources to a set of targets; layers 0=m5 1=mt"""
        fr = [self.free(net, "m5", c), self.free(net, "mt", c)]
        vfree = ~self.via_blk
        (wi0, wj0, wi1, wj1) = win
        tgt = set(dst)
        ti = np.array([t[0] for t in dst]); tj = np.array([t[1] for t in dst])
        h = lambda i, j: int(np.min(np.abs(ti - i) + np.abs(tj - j)))
        cost = {}
        prev = {}
        q = []
        for s in src:
            cost[s] = 0
            heapq.heappush(q, (h(s[0], s[1]), 0, s))
        stepc = (3, 2)                      # m5 / mt step cost
        while q:
            _, g, n = heapq.heappop(q)
            if cost.get(n) != g:
                continue
            if n in tgt:
                path = [n]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return path[::-1]
            i, j, k = n
            nb = [(i + 1, j, k), (i - 1, j, k), (i, j + 1, k), (i, j - 1, k), (i, j, 1 - k)]
            for m in nb:
                mi, mj, mk = m
                if not (wi0 <= mi <= wi1 and wj0 <= mj <= wj1):
                    continue
                if not fr[mk][mi, mj] and m not in tgt:
                    continue
                if mk != k:
                    if not (vfree[i, j] and fr[0][i, j] and fr[1][i, j]):
                        continue
                    ng = g + 6
                else:
                    ng = g + stepc[mk]
                if ng < cost.get(m, 1e18):
                    cost[m] = ng
                    prev[m] = n
                    heapq.heappush(q, (ng + 2 * h(mi, mj), ng, m))
        return None


class RouteFail(RuntimeError):
    def __init__(self, net):
        super().__init__(net); self.net = net


def grid_route(ly, top, d, land, order=None):
    g = Grid(-340.0, -110.0, 375.0, 212.0)
    # obstacles: every existing M5 / MT shape (flattened); MIM keep-outs
    for l in ("m5", "mt"):
        reg = db.Region(top.begin_shapes_rec(ly.layer(*LAY[l])))
        for p in reg.each():
            b = p.bbox()
            g.add(l, (b.left / U, b.bottom / U, b.right / U, b.top / U))
    fuse = db.Region(top.begin_shapes_rec(ly.layer(75, 0))).merged()
    for p in fuse.each():
        b = p.bbox()
        bx = (b.left / U, b.bottom / U, b.right / U, b.top / U)
        g.add("m5", (bx[0] - 2.3, bx[1] - 2.3, bx[2] + 2.3, bx[3] + 2.3))          # MIMTM.1 (1.06 + 1.2)
        i0, i1 = g._span(bx[0], bx[2], 1.6, 0); j0, j1 = g._span(bx[1], bx[3], 1.6, 1)
        g.via_blk[i0:i1 + 1, j0:j1 + 1] = True
    # own-net shapes (hand routes + escapes) were drawn into the layout already: register them as owned
    for l, box, net in d.shapes:
        if net is not None and l in ("m5", "mt"):
            for c in (0, 1):
                d_ = g.SP[l] + (g.WW[l] if c else g.W[l]) / 2
                i0, i1 = g._span(box[0], box[2], d_, 0); j0, j1 = g._span(box[1], box[3], d_, 1)
                key = (net, l, c)
                g.own.setdefault(key, np.zeros((g.nx, g.ny), np.int32))
                g.own[key][i0:i1 + 1, j0:j1 + 1] += 1
    # LF VSS MetalTop strap (west edge of the loop-filter plates) is a VSS pin
    lf_vss = (BT.PLACE["lf"][4] - 2.1, BT.PLACE["lf"][5] + 0.3, BT.PLACE["lf"][4] + 2.6, BT.PLACE["lf"][5] + 169.19)
    g.own_add("mt", lf_vss, "VSS")
    nets = {}
    for net, blk, x, y in land:
        nets.setdefault(net, []).append((x, y))
    order = order or ([n for n in nets if n not in ("VSS", "VDD")] + ["VSS", "VDD"])
    for net in order:
        pts = nets[net]
        c = 1 if net in ("VSS", "VDD") else 0
        w = g.WW["mt"] if c else g.W["mt"]
        wm5 = g.WW["m5"] if c else g.W["m5"]
        # snap landings to grid nodes with an MT stub
        nodes = []
        for (x, y) in pts:
            i, j = g.ij(x, y)
            gx, gy = g.xy(i, j)
            d.wire("mt", (x, y), (gx, y), 0.8, net); d.wire("mt", (gx, y), (gx, gy), 0.8, net)
            g.add("mt", (min(x, gx) - 0.4, y - 0.4, max(x, gx) + 0.4, y + 0.4), net)
            g.add("mt", (gx - 0.4, min(y, gy) - 0.4, gx + 0.4, max(y, gy) + 0.4), net)
            nodes.append((i, j, 1))
        if net == "VSS":
            i, j = g.ij((lf_vss[0] + lf_vss[2]) / 2, 0.0)
            nodes.append((i, j, 1))
        tree = {nodes[0]}
        drawn = []
        pin_nodes = [(n[0], n[1]) for n in nodes]
        near_pin = lambda a: any(abs(a[0] - p[0]) * g.P <= 3.0 and abs(a[1] - p[1]) * g.P <= 3.0 for p in pin_nodes)
        for tgt in nodes[1:]:
            allx = [n[0] for n in tree] + [tgt[0]]; ally = [n[1] for n in tree] + [tgt[1]]
            m = int(30 / g.P)
            win = (max(0, min(allx) - m), max(0, min(ally) - m), min(g.nx - 1, max(allx) + m), min(g.ny - 1, max(ally) + m))
            path = g.route(net, list(tree), [tgt], c, win)
            cc = c
            if path is None and c == 1:                    # tight last leg: normal width
                path = g.route(net, list(tree), [tgt], 0, win)
                cc = 0
            if path is None:
                print(f"grid route failed: {net} -> {g.xy(tgt[0], tgt[1])}", flush=True)
                raise RouteFail(net)
            tree |= set(path)
            drawn.append((path, cc))
            w = g.WW["mt"] if cc else g.W["mt"]
            wm5 = g.WW["m5"] if cc else g.W["m5"]
            # register as own + obstacle immediately
            for a, b in zip(path, path[1:]):
                if a[2] == b[2]:
                    l = "mt" if a[2] else "m5"
                    ww = w if a[2] else wm5
                    if cc and (near_pin(a) or near_pin(b)):
                        ww = g.W[l]
                    (xa, ya), (xb, yb) = g.xy(a[0], a[1]), g.xy(b[0], b[1])
                    box = (min(xa, xb) - ww / 2, min(ya, yb) - ww / 2, max(xa, xb) + ww / 2, max(ya, yb) + ww / 2)
                    g.add(l, box, net)
        # draw
        for path, cc in drawn:
            w = g.WW["mt"] if cc else g.W["mt"]
            wm5 = g.WW["m5"] if cc else g.W["m5"]
            for a, b in zip(path, path[1:]):
                (xa, ya), (xb, yb) = g.xy(a[0], a[1]), g.xy(b[0], b[1])
                narrow = cc and (near_pin(a) or near_pin(b))
                if a[2] == b[2]:
                    l = "mt" if a[2] else "m5"
                    d.wire(l, (xa, ya), (xb, yb), g.W[l] if narrow else (w if a[2] else wm5), net)
                else:
                    d.stack(xa, ya, "m5", "mt")
                    if cc and not narrow:
                        for dx, dy in ((-0.5, -0.5), (0.5, -0.5), (-0.5, 0.5), (0.5, 0.5)):
                            d.rect("v5", xa + dx - 0.13, ya + dy - 0.13, xa + dx + 0.13, ya + dy + 0.13)
                        d.rect("m5", xa - 1.0, ya - 1.0, xa + 1.0, ya + 1.0); d.rect("mt", xa - 1.0, ya - 1.0, xa + 1.0, ya + 1.0)
        # close same-net gaps (< spacing) on M5/MT: morphological closing of the net's own shapes
        for l, sp in (("m5", 300), ("mt", 480)):
            own = db.Region()
            for ll, box, nn in d.shapes:
                if ll == l and nn == net:
                    own.insert(db.Box(*[round(v * U) for v in box]))
            own.merge()
            fill = own.sized(sp // 2 + 5).sized(-(sp // 2 + 5)) - own
            for p in fill.each():
                top.shapes(ly.layer(*LAY[l])).insert(p)
        L = sum(len(p) for p, _ in drawn) * g.P
        print(f"grid {net:10s} {len(pts)} pins  ~{L:.0f} um", flush=True)


# ------------------------------------------------------------------------------------------------- 4
PORTS = [  # (name, layer, x, y)  labels at the pin metal
    ("VTUNE", "m1", -12.20, 14.18), ("RF_OUT", "m1", -24.83, 4.79), ("REF_1M", "m2", 89.11, 32.10),
    ("PA_DRAIN", "m4", -52.80, -74.30), ("XP", "m3", -19.02, -44.03), ("XN", "m3", -12.72, -44.03),
    ("CORE_CLK", "mt", -7.31, 20.0), ("VDD_VCO", "m5", 5.0, -1.75), ("MC", "m4", 10.0, 24.26),
    ("FB_1M", "m3", 75.5, 32.10),
    ("CFG[0]", "m3", 22.28, 39.94), ("CFG[3]", "m3", 22.28, 46.66), ("CFG[4]", "m3", 22.28, 38.82),
    ("CFG[5]", "m3", 73.56, 41.06), ("CFG[1]", "m2", 38.84, 68.82), ("CFG[2]", "m2", 37.72, 68.82),
]


def main():
    order = ["UPB", "DN", "CP_IBIAS", "VCTRL", "PRESCALED", "TAIL_BIAS", "RST_N", "VSS", "VDD"]
    for attempt in range(12):
        ly, top, cells = BT.assemble()
        d = Draw(ly, top)
        hand_routes(d)
        land = escapes(ly, top, d) if attempt == 0 else escapes_quiet(ly, top, d)
        try:
            grid_route(ly, top, d, land, order)
            break
        except RouteFail as e:
            order.remove(e.net)
            order.insert(0, e.net)
            print("retry with order", order, flush=True)
    else:
        raise SystemExit("routing failed")
    for name, l, x, y in PORTS:
        d.label(l, name, x, y)
    for net, blk, x, y in land:
        d.label("mt", net, x, y)
    ly.write(os.path.join(HERE, "PLL_COMPACT.gds"))
    json.dump({"land": land, "order": order}, open(os.path.join(HERE, "pins.json"), "w"), indent=1)
    b = top.dbbox()
    print(f"wrote PLL_COMPACT.gds  bbox {b.left:.2f},{b.bottom:.2f} .. {b.right:.2f},{b.top:.2f}")


def escapes_quiet(ly, top, d):
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        return escapes(ly, top, d)


if __name__ == "__main__":
    main()
