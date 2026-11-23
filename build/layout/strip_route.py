import sys, klayout.db as db
ly = db.Layout(); ly.read(sys.argv[1]); top = ly.cell(sys.argv[2]); top.flatten(True)
for l in sys.argv[4].split(","):
    a, b = map(int, l.split("/"))
    top.shapes(ly.layer(a, b)).clear()
ly.write(sys.argv[3])
