"""Small geometry helpers for hand-placed GF180MCU layout (klayout.db, dbu = 1 nm).

All coordinates in um.  Via pads are 0.40 x 0.40 (0.26 via + 0.07 enclosure) so that every
landing meets the metal minimum-area rule (0.1444 um^2)."""
import klayout.db as db

L = {"comp": (22, 0), "nwell": (21, 0), "poly": (30, 0), "nplus": (32, 0), "pplus": (31, 0),
     "cont": (33, 0), "m1": (34, 0), "v1": (35, 0), "m2": (36, 0), "v2": (38, 0), "m3": (42, 0),
     "v3": (40, 0), "m4": (46, 0), "v4": (41, 0), "m5": (81, 0), "v5": (82, 0), "mt": (53, 0),
     "m1t": (34, 10), "m2t": (36, 10), "m3t": (42, 10), "m4t": (46, 10), "m5t": (81, 10), "mtt": (53, 10),
     "fusetop": (75, 0), "res": (62, 0), "resmk": (110, 5), "capmk": (117, 5), "dualgate": (55, 0)}
METALS = ["m1", "m2", "m3", "m4", "m5", "mt"]
VIAS = ["v1", "v2", "v3", "v4", "v5"]
PAD = 0.40
VIA = 0.26


def um(v):
    """um -> dbu, snapped to the 5 nm manufacturing grid"""
    return int(round(v * 200)) * 5


class Canvas:
    def __init__(self, layout, cell):
        self.ly, self.c = layout, cell

    def li(self, name):
        return self.ly.layer(*L[name])

    def rect(self, layer, x0, y0, x1, y1):
        x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1))
        self.c.shapes(self.li(layer)).insert(db.Box(um(x0), um(y0), um(x1), um(y1)))

    def hline(self, layer, x0, x1, y, w=0.28):
        """horizontal wire centred on y, extended by w/2 past both ends"""
        x0, x1 = sorted((x0, x1))
        self.rect(layer, x0 - w / 2, y - w / 2, x1 + w / 2, y + w / 2)

    def vline(self, layer, x, y0, y1, w=0.28):
        y0, y1 = sorted((y0, y1))
        self.rect(layer, x - w / 2, y0 - w / 2, x + w / 2, y1 + w / 2)

    def pad(self, layer, x, y, s=PAD):
        self.rect(layer, x - s / 2, y - s / 2, x + s / 2, y + s / 2)

    def via(self, x, y, lo, hi):
        """via stack from metal `lo` up to metal `hi` (names m1..mt) centred at (x, y)"""
        i0, i1 = METALS.index(lo), METALS.index(hi)
        for i in range(i0, i1 + 1):
            self.pad(METALS[i], x, y)
        for i in range(i0, i1):
            self.pad(VIAS[i], x, y, VIA)

    def label(self, layer, text, x, y):
        self.c.shapes(self.li(layer)).insert(db.Text(text, db.Trans(um(x), um(y))))

    def place(self, child, x=0.0, y=0.0, rot=0, mirror=False):
        """rot in {0,1,2,3} x 90 deg; mirror = mirror at the x axis applied first (klayout)"""
        t = db.Trans(rot, mirror, um(x), um(y))
        self.c.insert(db.CellInstArray(child.cell_index(), t))
        return t

    def place_trans(self, child, trans):
        self.c.insert(db.CellInstArray(child.cell_index(), trans))


def tap_cell(layout, name, kind):
    """substrate (kind='p') or n-well (kind='n') tap: 0.48 um COMP, one contact, M1 pad"""
    c = layout.cell(name) or layout.create_cell(name)
    cv = Canvas(layout, c)
    cv.rect("comp", -0.24, -0.24, 0.24, 0.24)
    cv.rect("pplus" if kind == "p" else "nplus", -0.40, -0.40, 0.40, 0.40)
    cv.rect("cont", -0.11, -0.11, 0.11, 0.11)
    cv.rect("m1", -0.20, -0.20, 0.20, 0.20)
    if kind == "n":
        cv.rect("nwell", -0.50, -0.50, 0.50, 0.50)   # magic reads cells one by one: the tap needs its well
    return c
