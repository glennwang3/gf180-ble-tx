"""macro_metal.py <gds> <cell> x0 y0 x1 y1 : merged M2..M5/MT polygons inside a window (cell-local um)"""
import sys, klayout.db as db
ly = db.Layout(); ly.read(sys.argv[1]); c = ly.cell(sys.argv[2])
win = db.Region(db.Box(*[round(float(v) * 1000) for v in sys.argv[3:7]]))
for nm, l in (("M2", 36), ("M3", 42), ("M4", 46), ("M5", 81), ("MT", 53), ("V2", 38), ("V3", 40), ("V4", 41)):
    r = (db.Region(c.begin_shapes_rec(ly.layer(l, 0))).merged() & win)
    if not r.is_empty():
        print(nm, "; ".join(f"[{p.bbox().left/1e3:.2f},{p.bbox().bottom/1e3:.2f},{p.bbox().right/1e3:.2f},{p.bbox().top/1e3:.2f}]" for p in r.each()))
