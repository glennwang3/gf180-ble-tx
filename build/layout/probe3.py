import klayout.db as db, pdkcells as P
ly = db.Layout(); ly.dbu = 0.001
c = P.moscap(ly, 5, 10)
b = c.bbox(); print("==", c.name, b.left/1e3, b.bottom/1e3, b.right/1e3, b.top/1e3)
for li in ly.layer_indexes():
    inf = ly.get_info(li); r = db.Region(c.shapes(li)).merged()
    if not r.is_empty():
        ps = list(r.each())
        print(f"  {inf.layer}/{inf.datatype} n={len(ps)}: " + "; ".join(f"[{p.bbox().left/1e3:.3f},{p.bbox().bottom/1e3:.3f},{p.bbox().right/1e3:.3f},{p.bbox().top/1e3:.3f}]" for p in ps[:6]))
top = ly.create_cell("T"); top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
ly.write("probe_moscap.gds")
