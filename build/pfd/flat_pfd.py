"""flatten TS_PFD with the sub-cell labels removed (they would join nets across instances) -> TS_PFD_flat.gds"""
import klayout.db as db
ly = db.Layout(); ly.read("/foss/designs/Tri_State_Phase_Detector/TS_PFD.gds")
top = ly.cell("TS_PFD")
for c in ly.each_cell():
    if c.cell_index() == top.cell_index():
        continue
    for li in ly.layer_indexes():
        sh = c.shapes(li)
        for s in [s for s in sh.each() if s.is_text()]:
            sh.erase(s)
top.flatten(-1, True)
ly.write("/foss/designs/pll_compact/pfd/TS_PFD_flat.gds")
print("flat written")
