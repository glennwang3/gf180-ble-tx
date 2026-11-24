import sys
import klayout.db as db
SRC = "/foss/designs/pll_compact/layout/vco_lc/Differential_VCO_LC.gds"
ly = db.Layout(); ly.read(SRC)
top = ly.cell("Differential_VCO_LC")
x0, y0, x1, y1 = (float(v) for v in sys.argv[1:5])
box = db.Box(int(x0 * 1000), int(y0 * 1000), int(x1 * 1000), int(y1 * 1000))
print("instances:", sum(1 for _ in top.each_inst()))
for li in ly.layer_indexes():
    inf = ly.get_info(li)
    if inf.datatype == 10:
        continue
    r = db.Region(top.begin_shapes_rec(li)) & db.Region(box)
    if r.is_empty():
        continue
    polys = list(r.merged().each())
    print(f"L{inf.layer}/{inf.datatype}: {len(polys)}  " + "  ".join(
        f"[{p.bbox().left/1e3:.2f},{p.bbox().bottom/1e3:.2f},{p.bbox().right/1e3:.2f},{p.bbox().top/1e3:.2f}]" for p in polys[:14]))
