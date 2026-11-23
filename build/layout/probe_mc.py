import klayout.db as db, pdkcells as P
from acell import boxes, bbox
ly = db.Layout(); ly.dbu = 0.001
for lc, wc in ((6, 20), (6, 27)):
    c = P.moscap(ly, lc, wc)
    print(c.name, "bbox", bbox(ly, c))
    for lay in (22, 30, 34, 166, 32):
        print("  ", lay, boxes(ly, c, lay, 5 if lay == 166 else 0)[:3])
