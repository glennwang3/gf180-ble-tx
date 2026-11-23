"""near.py <gds> <cell> x0 y0 x1 y1 [layers]: shapes touching a window (um)"""
import sys
import klayout.db as db
gds, cell = sys.argv[1], sys.argv[2]
x0, y0, x1, y1 = [round(float(v) * 1000) for v in sys.argv[3:7]]
ly = db.Layout(); ly.read(gds); top = ly.cell(cell)
box = db.Box(x0, y0, x1, y1)
lays = [tuple(map(int, x.split("/"))) for x in sys.argv[7].split(",")] if len(sys.argv) > 7 else \
       [(ly.get_info(li).layer, ly.get_info(li).datatype) for li in ly.layer_indexes()]
for lay in lays:
    li = ly.layer(*lay)
    it = top.begin_shapes_rec_touching(li, box)
    while not it.at_end():
        s = it.shape()
        if not s.is_text():
            print(" ", lay, it.cell().name, s.polygon.transformed(it.trans()))
        it.next()
