"""render.py <gds> <png> [cell] [x0 y0 x1 y1 um] [layers comma list]  -> PNG via klayout.lay"""
import sys, klayout.lay as lay, klayout.db as db
gds, png = sys.argv[1], sys.argv[2]
v = lay.LayoutView(); v.set_config("background-color", "#ffffff"); v.set_config("grid-visible", "false")
v.load_layout(gds, True)
v.load_layer_props("/foss/pdks/gf180mcuD/libs.tech/klayout/tech/gf180mcu.lyp")
if len(sys.argv) > 3 and sys.argv[3] != "-":
    cv = v.active_cellview(); cv.cell_name = sys.argv[3]
v.max_hier(); 
if len(sys.argv) > 7:
    v.zoom_box(db.DBox(*map(float, sys.argv[4:8])))
else:
    v.zoom_fit()
if len(sys.argv) > 8:
    keep = set(sys.argv[8].split(","))
    it = v.begin_layers()
    while not it.at_end():
        lp = it.current(); lp.visible = f"{lp.source_layer}/{lp.source_datatype}" in keep; v.set_layer_properties(it, lp); it.next()
v.save_image(png, 1600, 1200)
