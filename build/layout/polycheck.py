"""polycheck.py <gds> <cell> [alias=..]: per metal layer, merged polygons that contain labels of
different names (direct same-layer shorts)"""
import sys
import klayout.db as db
ly = db.Layout(); ly.read(sys.argv[1]); top = ly.cell(sys.argv[2])
alias = dict(a.split("=") for a in sys.argv[3:])
for l in (34, 36, 42, 46, 81, 53):
    reg = db.Region(top.begin_shapes_rec(ly.layer(l, 0))).merged()
    texts = []
    it = top.begin_shapes_rec(ly.layer(l, 10))
    while not it.at_end():
        s = it.shape()
        if s.is_text():
            texts.append((alias.get(s.text.string, s.text.string), it.trans() * s.text.trans.disp))
        it.next()
    for p in reg.each():
        inside = {n for n, pt in texts if p.inside(pt) or p.bbox().contains(pt) and db.Region(p).interacting(db.Region(db.Box(pt, pt).enlarged(1))).count()}
        if len(inside) > 1:
            b = p.bbox()
            print(f"layer {l}: {sorted(inside)} bbox {b.left/1e3:.2f},{b.bottom/1e3:.2f}..{b.right/1e3:.2f},{b.top/1e3:.2f}")
