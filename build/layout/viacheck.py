"""viacheck.py <gds> <cell> <vialayer> <lo_metal> <hi_metal> [alias..]: vias joining differently-labelled polygons"""
import sys
import klayout.db as db
ly = db.Layout(); ly.read(sys.argv[1]); top = ly.cell(sys.argv[2])
vl, lo, hi = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
alias = dict(a.split("=") for a in sys.argv[6:])
def named(l):
    reg = db.Region(top.begin_shapes_rec(ly.layer(l, 0))).merged()
    texts = []
    it = top.begin_shapes_rec(ly.layer(l, 10))
    while not it.at_end():
        s = it.shape()
        if s.is_text():
            texts.append((alias.get(s.text.string, s.text.string), it.trans() * s.text.trans.disp))
        it.next()
    out = []
    for p in reg.each():
        r = db.Region(p)
        ns = {n for n, pt in texts if not r.interacting(db.Region(db.Box(pt, pt).enlarged(1))).is_empty()}
        out.append((r, ns))
    return out
L, H = named(lo), named(hi)
vias = db.Region(top.begin_shapes_rec(ly.layer(vl, 0))).merged()
n = 0
for v in vias.each():
    rv = db.Region(v)
    a = set().union(*[ns for r, ns in L if not r.interacting(rv).is_empty()])
    b = set().union(*[ns for r, ns in H if not r.interacting(rv).is_empty()])
    if a and b and a != b:
        c = v.bbox().center()
        print(f"via {vl} at ({c.x/1e3:.2f},{c.y/1e3:.2f}): lower {sorted(a)} upper {sorted(b)}")
        n += 1
print("mismatched vias:", n)
