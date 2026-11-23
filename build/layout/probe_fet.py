import klayout.db as db, pdkcells as P
ly = db.Layout(); ly.dbu = 0.001
for c in (P.nfet(ly, 4, l=1, nf=2), P.pfet(ly, 8, l=1, nf=1), P.nfet(ly, 2, l=0.28, nf=1)):
    b = c.bbox(); print("==", c.name, b.left/1e3, b.bottom/1e3, b.right/1e3, b.top/1e3)
    for li in ly.layer_indexes():
        inf = ly.get_info(li); r = db.Region(c.shapes(li)).merged()
        if not r.is_empty():
            print(f"  {inf.layer}/{inf.datatype}: " + "; ".join(f"[{p.bbox().left/1e3:.3f},{p.bbox().bottom/1e3:.3f},{p.bbox().right/1e3:.3f},{p.bbox().top/1e3:.3f}]" for p in list(r.each())[:10]))
