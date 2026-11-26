#!/usr/bin/env python3
"""Pin access points for the fixed TSPC / gate cells: for every labelled net, a point on its M1 where a
0.4 um M1 pad fits inside the net's own M1 and a via stack M1 -> M5 does not come near other-net M2..M4.
    access(gds, cell) -> {net: (x, y)} in cell coordinates (um)
"""
import sys
import klayout.db as db

sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of  # noqa: E402

U = 1000


def access(gds, cell, prefer=None):
    ly = db.Layout(); ly.read(gds)
    c = ly.cell(cell)
    l2n, L = l2n_of(ly, c)
    labels = {}
    for s in c.shapes(ly.layer(34, 10)).each():
        if s.is_text():
            labels[s.text.string] = db.Point(s.text.x, s.text.y)
    out, okr = {}, {}
    for name, p in labels.items():
        net = l2n.probe_net(L["met"][0], p)
        if net is None:
            continue
        own1 = l2n.shapes_of_net(net, L["met"][0], True).merged()
        inner = own1.sized(-100)                                    # centre on the net's own M1 (>= 0.1 inside)
        all1 = db.Region(c.begin_shapes_rec(ly.layer(34, 0))).merged()
        bad = (all1 - own1).sized(200 + 240)                        # 0.4 pad may overhang, >= 0.24 from other M1
        v1 = db.Region(c.begin_shapes_rec(ly.layer(35, 0))).merged()
        bad += v1.sized(130 + 260)                                  # new via1 >= 0.26 from existing via1
        for k in (1, 2, 3):                                         # other-net M2..M4, with pad + spacing halo
            allk = db.Region(c.begin_shapes_rec(ly.layer(*[(36, 0), (42, 0), (46, 0)][k - 1]))).merged()
            ownk = l2n.shapes_of_net(net, L["met"][k], True)
            bad += (allk - ownk).sized(200 + 320)
        ok = (inner - bad).merged()
        if ok.is_empty():
            bad_up = db.Region()                                    # other-net M2..M4 halos only
            for k in (1, 2, 3):
                allk = db.Region(c.begin_shapes_rec(ly.layer(*[(36, 0), (42, 0), (46, 0)][k - 1]))).merged()
                bad_up += (allk - l2n.shapes_of_net(net, L["met"][k], True)).sized(200 + 320)
            dot = lambda q: db.Region(db.Box(q.x - 1, q.y - 1, q.x + 1, q.y + 1))
            own_v1 = [q.bbox().center() for q in (v1 & own1).each() if q.bbox().width() == 260 and q.bbox().height() == 260
                      and bad_up.interacting(dot(q.bbox().center())).is_empty()]
            if own_v1:                                              # stack exactly on an existing via1 of the net
                q = min(own_v1, key=lambda q: (q.x - p.x) ** 2 + (q.y - p.y) ** 2)
                out[name] = (q.x / U, q.y / U); okr[name] = db.Region(db.Box(q.x - 1, q.y - 1, q.x + 1, q.y + 1))
                print(f"{cell}.{name}: on existing via1 at {out[name]}", file=sys.stderr); continue
            print(f"{cell}.{name}: NO via-stack access", file=sys.stderr); continue
        # candidate: point of ok closest to the label (or to a preferred side)
        tgt = p if not prefer or name not in prefer else db.Point(*[round(v * U) for v in prefer[name]])
        best, bd = None, 1e18
        for poly in ok.each():
            for t in poly.decompose_trapezoids():
                b = t.bbox()
                x = min(max(tgt.x, b.left), b.right); y = min(max(tgt.y, b.bottom), b.top)
                x, y = round(x / 5) * 5, round(y / 5) * 5
                if not ok.interacting(db.Region(db.Box(x - 1, y - 1, x + 1, y + 1))).is_empty():
                    d = (x - tgt.x) ** 2 + (y - tgt.y) ** 2
                    if d < bd:
                        best, bd = (x / U, y / U), d
        out[name] = best
        okr[name] = ok
    # supply rails run the full cell width: put their stacks as far as possible from every signal access point
    sig = [v for k, v in out.items() if k not in ("3v3", "vss")]
    for name in ("3v3", "vss"):
        if name not in okr:
            continue
        best, bd = out[name], -1
        for poly in okr[name].each():
            for t in poly.decompose_trapezoids():
                b = t.bbox()
                for x in range(b.left, b.right + 1, 50):
                    for y in range(b.bottom, b.top + 1, 50):
                        if okr[name].interacting(db.Region(db.Box(x - 1, y - 1, x + 1, y + 1))).is_empty():
                            continue
                        dmin = min(((x / U - sx) ** 2 + (y / U - sy) ** 2) ** 0.5 for sx, sy in sig) if sig else 0
                        if dmin > bd:
                            best, bd = (round(x / 5) * 5 / U, round(y / 5) * 5 / U), dmin
        out[name] = best
    return out


if __name__ == "__main__":
    for gds, cell in [(a.split(":")[0], a.split(":")[1]) for a in sys.argv[1:]]:
        print(cell, access(gds, cell))
