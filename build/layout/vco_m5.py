import klayout.db as db
ly = db.Layout(); ly.read("/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout/Diff_VCO_XOR_Layout.gds")
top = ly.cell("Differential_VCO_XOR")
for (l, d) in ((81, 0), (53, 0), (75, 0), (82, 0), (41, 0)):
    r = db.Region(top.begin_shapes_rec(ly.layer(l, d))).merged()
    print(f"{l}/{d}:", "; ".join(f"[{p.bbox().left/1e3:.2f},{p.bbox().bottom/1e3:.2f},{p.bbox().right/1e3:.2f},{p.bbox().top/1e3:.2f}]" for p in r.each()))
