import sys, klayout.db as db, klayout.lay as lay
gds, cell, out = sys.argv[1:4]
box = [float(v) for v in sys.argv[4].split(",")] if len(sys.argv) > 4 else None
lv = lay.LayoutView(); lv.load_layout(gds, True)
ly = lv.cellview(0).layout(); lv.cellview(0).cell = ly.cell(cell)
lv.max_hier(); lv.set_config("background-color", "#ffffff"); lv.set_config("grid-visible", "false")
show = {(34, 0): "#bbbbbb", (81, 0): "#d7301f", (53, 0): "#2b83ba", (53, 10): "#000000", (21, 0): "#e8f5d0"}
it = lv.begin_layers()
while not it.at_end():
    lp = it.current(); k = (lp.source_layer, lp.source_datatype)
    lp.visible = k in show
    if k in show:
        c = int(show[k][1:], 16); lp.fill_color = c; lp.frame_color = c; lp.dither_pattern = 1 if k != (53, 0) else 2
        lp.transparent = True
    lv.set_layer_properties(it, lp); it.next()
b = db.DBox(*box) if box else ly.cell(cell).dbbox().enlarged(1, 1)
lv.zoom_box(b); lv.save_image(out, 1800, int(1800 * b.height() / b.width()))
