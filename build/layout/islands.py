import sys, klayout.db as db
sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of
gds, cell = sys.argv[1], sys.argv[2]
x0, y0, x1, y1 = map(float, sys.argv[3:7])
ly = db.Layout(); ly.read(gds); top = ly.cell(cell)
l2n, L = l2n_of(ly, top)
ref = l2n.probe_net(L["met"][3], db.DPoint(-3.74, -6.34))
print("VSS_LAND cluster", ref.cluster_id)
win = db.Region(db.Box(*[round(v * 1000) for v in (x0, y0, x1, y1)]))
for lv, nm in ((0, "M1"), (1, "M2")):
    reg = db.Region(top.begin_shapes_rec(ly.layer(*((34, 0), (36, 0))[lv]))).merged() & win
    for p in reg.each():
        c = p.bbox().center()
        n = l2n.probe_net(L["met"][lv], db.DPoint(c.x / 1000, c.y / 1000))
        b = p.bbox()
        print(nm, f"[{b.left/1e3:.2f},{b.bottom/1e3:.2f},{b.right/1e3:.2f},{b.top/1e3:.2f}]", n.cluster_id if n is not None else None, n.expanded_name() if n is not None else "")
