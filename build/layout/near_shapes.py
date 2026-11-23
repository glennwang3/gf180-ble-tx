"""near_shapes.py x0 y0 x1 y1 : M1/V1/M2 shapes touching a window, original vs slot VCO"""
import sys
import klayout.db as db
x0, y0, x1, y1 = [round(float(v) * 1000) for v in sys.argv[1:5]]
for f, c in (("../Diff_VCO_2nd_Layout_native_moscaps.gds", "Differential_VCO"), ("Diff_VCO_XOR_slot.gds", "Differential_VCO_XS")):
    ly = db.Layout(); ly.read(f); top = ly.cell(c)
    box = db.Box(x0, y0, x1, y1)
    print(f)
    for lay in [tuple(map(int, x.split("/"))) for x in (sys.argv[5] if len(sys.argv) > 5 else "34/0,35/0,36/0").split(",")]:
        li = ly.layer(*lay)
        it = top.begin_shapes_rec_touching(li, box)
        while not it.at_end():
            s = it.shape()
            if not s.is_text():
                print(" ", lay, it.cell().name, s.polygon.transformed(it.trans()))
            it.next()
