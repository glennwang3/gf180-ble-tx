import klayout.db as db
import build_top as BT
from route_top import PINS, LAY, MET
ly, top, cells = BT.assemble()
regs = {l: db.Region(top.begin_shapes_rec(ly.layer(*LAY[l]))).merged() for l in MET}
for net, blk, lev, x, y in PINS:
    r = regs[MET[lev]]
    pt = db.Region(db.Box(round(x*1000)-1, round(y*1000)-1, round(x*1000)+1, round(y*1000)+1))
    if not r.interacting(pt).is_empty():
        continue
    near = r.interacting(pt.sized(2500))
    print(f"MISSING {blk}.{net} {MET[lev]} ({x},{y}) near: " + "; ".join(
        f"[{p.bbox().left/1e3:.2f},{p.bbox().bottom/1e3:.2f},{p.bbox().right/1e3:.2f},{p.bbox().top/1e3:.2f}]" for p in list(near.each())[:4]))
print("done")
