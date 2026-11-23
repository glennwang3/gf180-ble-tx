"""
Analog cell helpers for the compact PLL (GF180MCU, klayout.db, coordinates in um).

  Fet      PDK nfet/pfet placed unrotated; gate pads strapped by an M1 bar, multi-strip S/D strapped
           by M2 bars (S near the bottom of the strips, D near the top); exposes router terminals.
  RChain   ppolyf_u_1k resistor as a vertical stack of equal series segments (meander jumpers on M1,
           body taps joined by an M1 rail); exposes its two ends.
  Router   every terminal gets its own M3 column (unique x) that runs to its net's M4 track (unique y);
           via2/via3 at the ends.  Fixed shapes of other nets on M3/M4 are avoided.
  Mim      PDK MIM-B (M5 bottom / MT top) with side tabs so a net track can reach each plate:
           bottom plate -> M5 widening on one side -> via4 to the net's M4 track;
           top plate    -> MT widening on the other side over an M5 island -> via5 + via4 to M4.
"""
import klayout.db as db
from geom import Canvas, um, tap_cell
import pdkcells as P

D = 1e-3


def boxes(ly, cell, layer, dt=0):
    r = db.Region(cell.shapes(ly.layer(layer, dt))).merged()
    return [(p.bbox().left * D, p.bbox().bottom * D, p.bbox().right * D, p.bbox().top * D) for p in r.each()]


def bbox(ly, cell):
    b = cell.bbox()
    return b.left * D, b.bottom * D, b.right * D, b.top * D


def snap(v, g=0.005):
    return round(v / g) * g


class Term:
    def __init__(self, net, xs, y, low, name="", link=None):
        self.net, self.xs, self.y, self.low, self.name, self.link = net, xs, y, low, name, link
        self.x = None


class Fet:
    """kind 'n'/'p', wf = finger width, nf fingers; (x, y) = pcell origin (comp bottom-left ~ (-0.4, 0))"""

    def __init__(self, cv, kind, wf, l, nf, x, y, name, nets, ext_s=2.0, ext_d=2.0):
        ly = cv.ly
        cell = (P.nfet if kind == "n" else P.pfet)(ly, wf, l=l, nf=nf)
        cv.place(cell, x, y)
        self.cv, self.name, self.kind, self.nets = cv, name, kind, nets      # nets = dict(g=, s=, d=)
        self.bb = tuple(v + o for v, o in zip(bbox(ly, cell), (x, y, x, y)))
        comp = boxes(ly, cell, 22)[0]
        self.comp = (comp[0] + x, comp[1] + y, comp[2] + x, comp[3] + y)
        m1 = [(a + x, b + y, c + x, d + y) for a, b, c, d in boxes(ly, cell, 34)]
        strips = sorted([b for b in m1 if b[1] < self.comp[3] and b[3] > self.comp[1]], key=lambda b: b[0])
        pads = [b for b in m1 if b[1] >= self.comp[3] - 1e-6]
        self.strips = strips
        self.s = strips[0::2]
        self.d = strips[1::2]
        # gate bar over all pads, widened to the comp width (it sits above the S/D strips)
        gx0 = min(min(p[0] for p in pads), self.comp[0] + 0.10)
        gx1 = max(max(p[2] for p in pads), self.comp[2] - 0.10)
        gy0, gy1 = min(p[1] for p in pads), max(p[3] for p in pads)
        cv.rect("m1", gx0, gy0, gx1, max(gy1, gy0 + 0.40))
        self.gbar = (gx0, gy0, gx1, max(gy1, gy0 + 0.40))
        sy0, sy1 = strips[0][1], strips[0][3]
        self.ys = sy0 + 0.30
        self.yd = sy1 - 0.30
        self.bars = {}
        for key, grp, yb, ext in (("s", self.s, self.ys, (-ext_s, 0.0)), ("d", self.d, self.yd, (0.0, ext_d))):
            xa = (grp[0][0] + grp[0][2]) / 2
            xb = (grp[-1][0] + grp[-1][2]) / 2
            cv.hline("m2", xa + ext[0], xb + ext[1], yb, w=0.40)
            for g in grp:
                xc = (g[0] + g[2]) / 2
                cv.pad("m1", xc, yb)
                cv.pad("v1", xc, yb, 0.26)
            self.bars[key] = (xa + ext[0], xb + ext[1], yb)

    def terms(self, which="gsd"):
        out = []
        for k in which:
            net = self.nets[k]
            if net is None:
                continue
            if k == "g":
                g = self.gbar
                xs = frange(g[0] + 0.20, g[2] - 0.20)
                out.append(Term(net, xs, (g[1] + g[3]) / 2, "m1", self.name + ".g"))
            else:
                xa, xb, yb = self.bars[k]
                out.append(Term(net, frange(xa, xb), yb, "m2", f"{self.name}.{k}"))
        return out


def frange(a, b, step=0.05):
    """grid-aligned points (multiples of step) in [a, b]"""
    import math
    a, b = sorted((a, b))
    k0, k1 = math.ceil(a / step - 1e-6), math.floor(b / step + 1e-6)
    return [snap(k * step) for k in range(k0, k1 + 1)] or [snap((a + b) / 2)]


class RChain:
    """n series ppolyf_u_1k segments (w x ls), horizontal, stacked upward from (x, y) with pitch p.
    Segment i spans x .. x+ls (poly); M1 end pads at x-0.46 and x+ls+0.46; body taps at x-1.55."""

    def __init__(self, cv, n, ls, x, y, name, a, b, w=1.0, p=2.6):
        ly = cv.ly
        cell = P.ppoly_hr(ly, w, ls)
        self.cv, self.name, self.n, self.ls, self.x0, self.p = cv, name, n, ls, x, p
        ends = []
        for i in range(n):
            yi = y + i * p
            cv.place(cell, x, yi)
            ends.append(((x - 0.46, yi + w / 2), (x + ls + 0.46, yi + w / 2)))
        # meander: segment i right -> i+1 right (i even), i left -> i+1 left (i odd)
        for i in range(n - 1):
            side = 1 if i % 2 == 0 else 0
            (xa, ya), (xb, yb) = ends[i][side], ends[i + 1][side]
            cv.rect("m1", xa - 0.19, ya - 0.19, xa + 0.19, yb + 0.19)
        # body taps: M1 rail through all taps (x-1.55)
        if n > 1:
            cv.rect("m1", x - 1.74, y + w / 2 - 0.19, x - 1.36, y + (n - 1) * p + w / 2 + 0.19)
        self.a = (snap(ends[0][0][0]), snap(ends[0][0][1]))
        last_side = 1 if (n - 1) % 2 == 0 else 0
        self.b = (snap(ends[-1][last_side][0]), snap(ends[-1][last_side][1]))
        self.tap = (snap(x - 1.55), snap(y + w / 2))
        self.nets = (a, b)
        self.bb = (x - 1.80, y - 0.40, x + ls + 1.10, y + (n - 1) * p + w + 0.40)
        self.seg = [(f"{name}_{i}", ls, w) for i in range(n)]

    def terms(self, sub="VSS", stub=3.0, tap=True):
        """each end gets an M2 stub (via1 on the end pad) running away from the chain body"""
        out = []
        for (x, y), net, nm in ((self.a, self.nets[0], "a"), (self.b, self.nets[1], "b")):
            left = x < self.x0 + self.ls / 2
            x2 = x - stub if left else x + stub
            self.cv.pad("v1", x, y, 0.26)
            self.cv.hline("m2", x, x2, y, w=0.40)
            out.append(Term(net, frange(x, x2, 0.1), y, "m2", f"{self.name}.{nm}"))
        if tap:
            out.append(Term(sub, [self.tap[0]], snap(self.tap[1] + self.p / 2), "m1", self.name + ".sub"))
        return out

    def spice(self, sub="VSS"):
        nodes = [self.nets[0]] + [f"{self.name}_n{i}" for i in range(1, self.n)] + [self.nets[1]]
        return [f"X{self.name}_{i} {nodes[i]} {nodes[i + 1]} {sub} ppolyf_u_1k r_width={self.seg[i][2]:g}u r_length={self.ls:g}u"
                for i in range(self.n)]


class Router:
    PITCH_X = 0.80
    PITCH_Y = 0.80

    def __init__(self, cv, y_lo, y_hi, x_lo, x_hi, debug=None):
        self.cv = cv
        self.debug = debug          # layout layer index for net-name debug texts
        self.terms = []
        self.block = {"m3": [], "m4": []}          # (rect, net)
        self.used_x = []
        self.track = {}
        self.y_lo, self.y_hi, self.x_lo, self.x_hi = y_lo, y_hi, x_lo, x_hi
        self.fixed_track = {}
        self.track_window = {}
        self.extra_track_x = {}

    def add(self, terms):
        self.terms += terms

    def blockage(self, layer, rect, net=None):
        self.block[layer].append((rect, net))

    def _hit(self, layer, rect, net):
        x0, y0, x1, y1 = rect
        for (a, b, c, d), n in self.block[layer]:
            if n == net and net is not None:
                continue
            if x0 < c + 0.30 and x1 > a - 0.30 and y0 < d + 0.30 and y1 > b - 0.30:
                return True
        return False

    def solve(self, track_hint=None):
        cv = self.cv
        nets = {}
        for t in self.terms:
            nets.setdefault(t.net, []).append(t)
        # ---- tracks: one per net, y close to the mean terminal y, unique slots ----------------------
        slots = [snap(self.y_lo + i * self.PITCH_Y) for i in range(int((self.y_hi - self.y_lo) / self.PITCH_Y) + 1)]
        taken = set()
        for net, y in self.fixed_track.items():
            self.track[net] = y
            taken.add(y)
        order = sorted(nets, key=lambda n: (n not in self.track_window, -len(nets[n])))
        for net in order:
            if net in self.track:
                continue
            ts = nets[net]
            target = (track_hint or {}).get(net, sum(t.y for t in ts) / len(ts))
            win = self.track_window.get(net, (self.y_lo, self.y_hi))
            xs0 = min(min(t.xs) for t in ts)
            xs1 = max(max(t.xs) for t in ts)
            for xe in self.extra_track_x.get(net, []):
                xs0, xs1 = min(xs0, xe), max(xs1, xe)
            cands = [s for s in slots if s not in taken and win[0] <= s <= win[1]
                     and not self._hit("m4", (xs0 - 0.2, s - 0.2, xs1 + 0.2, s + 0.2), net)]
            if not cands:
                raise RuntimeError(f"no track for {net}")
            y = min(cands, key=lambda s: abs(s - target))
            self.track[net] = y
            taken.add(y)
        # ---- columns: unique x, avoid M3 blockages of other nets ------------------------------------
        def yr(t):
            return sorted((t.y, self.track[t.net]))
        pend = list(self.terms)

        def cost(t, x, y0, y1):
            c = 0
            for o in pend:
                if o is t or o.net == t.net:
                    continue
                a, b = yr(o)
                if y0 < b + 0.7 and y1 > a - 0.7 and o.xs[0] - 0.8 < x < o.xs[-1] + 0.8:
                    c += 4.0 / len(o.xs)
            return c + 0.01 * abs(x - (t.xs[0] + t.xs[-1]) / 2)

        for t in sorted(self.terms, key=lambda t: (len(t.xs), -abs(t.y - self.track[t.net]))):
            pend.remove(t)
            y0, y1 = yr(t)
            # tap onto a same-net column that already passes over this terminal
            share = [u for u, a, b, n in self.used_x if n == t.net and a - 1e-6 <= t.y <= b + 1e-6
                     and t.xs[0] - 0.25 <= u <= t.xs[-1] + 0.25 and t.low != "m4"]
            if share:
                t.x = share[0]
                self.used_x.append((t.x, y0, y1, t.net))
                continue
            ok = []
            for x in t.xs:
                if any((n != t.net or abs(x - u) > 1e-6) and abs(x - u) < self.PITCH_X - 1e-6 and y0 < b + 0.7 and y1 > a - 0.7 for u, a, b, n in self.used_x):
                    continue
                if self._hit("m3", (x - 0.2, y0 - 0.2, x + 0.2, y1 + 0.2), t.net):
                    continue
                ok.append(x)
            if not ok:
                near = [(round(u, 2), round(a, 1), round(b, 1), n) for u, a, b, n in self.used_x if t.xs[0] - 1 < u < t.xs[-1] + 1]
                raise RuntimeError(f"no column for {t.name} ({t.net}) xs {t.xs[0]}..{t.xs[-1]} y {t.y:.2f}->{self.track[t.net]:.2f}; used {near}")
            best = min(ok, key=lambda x: cost(t, x, y0, y1))
            t.x = best
            self.used_x.append((best, y0, y1, t.net))
            self.block["m3"].append(((best - 0.2, y0 - 0.2, best + 0.2, y1 + 0.2), t.net))
        # ---- draw -------------------------------------------------------------------------------------
        span = {}
        for t in self.terms:
            yt = self.track[t.net]
            if t.low == "m4":                       # link: starts on the track of net t.link
                cv.pad("m4", t.x, t.y); cv.pad("v3", t.x, t.y, 0.26); cv.pad("m3", t.x, t.y)
                cv.vline("m3", t.x, t.y, yt, w=0.40)
                cv.pad("m3", t.x, yt); cv.pad("v3", t.x, yt, 0.26); cv.pad("m4", t.x, yt)
                for nn in (t.net, t.link):
                    a, b = span.get(nn, (t.x, t.x))
                    span[nn] = (min(a, t.x), max(b, t.x))
                continue
            if t.low == "m1":
                cv.pad("m1", t.x, t.y)
                cv.pad("v1", t.x, t.y, 0.26)
            if t.low != "m3":                       # 'm3' = cell pin: an M3 landing at the cell edge
                cv.pad("m2", t.x, t.y)
                cv.pad("v2", t.x, t.y, 0.26)
            cv.pad("m3", t.x, t.y)
            cv.vline("m3", t.x, t.y, yt, w=0.40)
            cv.pad("m3", t.x, yt)
            cv.pad("v3", t.x, yt, 0.26)
            cv.pad("m4", t.x, yt)
            a, b = span.get(t.net, (t.x, t.x))
            span[t.net] = (min(a, t.x), max(b, t.x))
            if self.debug is not None:
                cv.c.shapes(self.debug[0]).insert(db.Text(t.net, db.Trans(um(t.x), um((t.y + yt) / 2))))
                if t.low != "m4":
                    cv.c.shapes(self.debug[2]).insert(db.Text(t.net, db.Trans(um(t.x), um(t.y))))
        for net, xe in self.extra_track_x.items():
            for x in xe:
                a, b = span.get(net, (x, x))
                span[net] = (min(a, x), max(b, x))
        for net, (a, b) in span.items():
            cv.hline("m4", a, b, self.track[net], w=0.40)
            if self.debug is not None:
                cv.c.shapes(self.debug[1]).insert(db.Text(net, db.Trans(um((a + b) / 2), um(self.track[net]))))
        return self.track


class Mim:
    """MIM-B w x l at (x, y) (FuseTop lower-left).  Bottom-plate tab on side `bside` ('l'/'r'),
    top-plate tab on side `tside`; each tab is a 2.4 um strip along the plate height."""

    def __init__(self, cv, w, l, x, y, top, bot, bside="r", tside="l", name="C"):
        ly = cv.ly
        cell = P.mim(ly, w, l)
        cv.place(cell, x, y)
        self.cv, self.w, self.l, self.x, self.y, self.top, self.bot, self.name = cv, w, l, x, y, top, bot, name
        # bottom plate (M5) widening
        if bside == "r":
            bx0, bx1 = x + w + 0.6, x + w + 3.0
        else:
            bx0, bx1 = x - 3.0, x - 0.6
        cv.rect("m5", bx0, y - 0.6, bx1, y + l + 0.6)
        self.bx = snap((bx0 + bx1) / 2 + (0.3 if bside == "r" else -0.3))      # via4 column (>=1.2 from fuse)
        # top plate: MT strip from the plate edge outward, M5 island under it (0.6 gap to the plate M5)
        # MIMTM.1: other M5 >= 1.2 um from the virtual plate (FuseTop + 1.06)
        if tside == "l":
            tx0, tx1 = x - 5.6, x + 0.5
            ix0, ix1 = x - 5.6, x - 2.3
        else:
            tx0, tx1 = x + w - 0.5, x + w + 5.6
            ix0, ix1 = x + w + 2.3, x + w + 5.6
        cv.rect("mt", tx0, y + 0.5, tx1, y + l - 0.5)
        cv.rect("m5", ix0, y + 0.5, ix1, y + l - 0.5)
        self.tx = snap((ix0 + ix1) / 2 + (-0.25 if tside == "l" else 0.25))
        # via5 column on the island
        n = int((l - 1.6) / 0.76)
        for i in range(n):
            yy = y + 0.9 + i * 0.76
            cv.pad("v5", self.tx, yy, 0.26)
        self.span = (y + 0.9, y + l - 0.9)
        self.bb = (min(x - 5.6, bx0), y - 0.6, max(x + w + 5.6, bx1), y + l + 0.6)
        self.ix = (ix0, ix1)

    def hook(self, router):
        """ask the router for tracks of both nets inside the plate span; record via4 points"""
        for net, xx in ((self.bot, self.bx), (self.top, self.tx)):
            router.track_window[net] = (max(router.track_window.get(net, (-1e9, 1e9))[0], self.span[0]),
                                        min(router.track_window.get(net, (-1e9, 1e9))[1], self.span[1]))
            router.extra_track_x.setdefault(net, []).append(xx)
        self.router = router

    def finish(self):
        cv = self.cv
        yb, yt = self.router.track[self.bot], self.router.track[self.top]
        cv.pad("m4", self.bx, yb); cv.pad("v4", self.bx, yb, 0.26); cv.pad("m5", self.bx, yb)
        cv.pad("m4", self.tx, yt); cv.pad("v4", self.tx, yt, 0.26)

    def spice(self):
        return f"X{self.name} {self.top} {self.bot} cap_mim_2f0_m5m6_noshield c_width={self.w:g}u c_length={self.l:g}u"


def taps_row(cv, kind, x0, x1, y, pitch=4.0):
    """row of substrate (p) / n-well (n) taps joined by an M1 rail; returns the tap x list"""
    tap = cv.ly.cell("TAP_SUB" if kind == "p" else "TAP_NW") or tap_cell(cv.ly, "TAP_SUB" if kind == "p" else "TAP_NW", kind)
    xs = []
    x = x0
    while x <= x1 + 1e-6:
        cv.place(tap, x, y)
        xs.append(snap(x))
        x += pitch
    cv.rect("m1", xs[0] - 0.2, y - 0.2, xs[-1] + 0.2, y + 0.2)
    return xs


class MimComb:
    """n MIM-B fingers (fuse wf x l, wf <= 28.7 um so the M5 bottom plate needs no slotting, MSLOT.1),
    fuse gap 3.0 um (MIMTM.1).  Each finger keeps its own bottom plate (MIMTM.11):
      bottom (M5): a tab under each finger (y-2.6 .. y-0.6); the router's track for `bot` runs under the
                   tabs (window y-2.2 .. y-1.0) and gets a via4 in every tab;
      top (MT):    an MT strip joins the fingers above them and covers an M5 island (y+l+2.3 .. y+l+4.3,
                   >= 1.2 um off the virtual plates) with via5s; the `top` track runs under the island."""
    GAP = 3.0

    def __init__(self, cv, n, wf, l, x, y, top, bot, name="C"):
        self.cv, self.n, self.wf, self.l, self.x, self.y, self.top, self.bot, self.name = cv, n, wf, l, x, y, top, bot, name
        cell = P.mim(cv.ly, wf, l)
        self.fx = [snap(x + i * (wf + self.GAP)) for i in range(n)]
        for fx in self.fx:
            cv.place(cell, fx, y)
            cv.rect("m5", fx - 0.6, y - 2.6, fx + wf + 0.6, y - 0.6)
        x1 = self.fx[-1] + wf
        cv.rect("mt", x - 0.5, y + l - 1.0, x1 + 0.5, y + l + 4.5)
        cv.rect("m5", x, y + l + 2.3, x1, y + l + 4.3)
        self.ix = [snap(fx + wf / 2) for fx in self.fx]
        for fx in self.fx:
            k = int((wf - 1.0) / 1.0)
            for i in range(k):
                for yy in (y + l + 2.9, y + l + 3.7):
                    cv.pad("v5", fx + 0.7 + i * 1.0, yy, 0.26)
        self.bb = (x - 0.6, y - 2.6, x1 + 0.6, y + l + 4.5)

    def hook(self, router):
        def win(net, a, b):
            w = router.track_window.get(net, (-1e9, 1e9))
            router.track_window[net] = (max(w[0], a), min(w[1], b))
        win(self.bot, self.y - 2.2, self.y - 1.0)
        win(self.top, self.y + self.l + 2.7, self.y + self.l + 3.9)
        router.extra_track_x.setdefault(self.bot, []).extend([self.ix[0], self.ix[-1]])
        router.extra_track_x.setdefault(self.top, []).extend([self.ix[0], self.ix[-1]])
        self.router = router

    def finish(self):
        cv = self.cv
        yb, yt = self.router.track[self.bot], self.router.track[self.top]
        for xx in self.ix:
            cv.pad("m4", xx, yb); cv.pad("v4", xx, yb, 0.26); cv.pad("m5", xx, yb)
            cv.pad("m4", xx, yt); cv.pad("v4", xx, yt, 0.26)

    def spice(self):
        return [f"X{self.name}_{i} {self.top} {self.bot} cap_mim_2f0_m5m6_noshield c_width={self.wf:g}u c_length={self.l:g}u"
                for i in range(self.n)]
