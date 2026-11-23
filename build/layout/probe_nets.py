"""probe_nets.py <gds> <cell> name:layer:x:y ... -> net id per probe point (KLayout l2n, flat)"""
import sys
import klayout.db as db
sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of
ly = db.Layout(); ly.read(sys.argv[1]); top = ly.cell(sys.argv[2])
l2n, L = l2n_of(ly, top)
lay = {"m1": L["met"][0], "m2": L["met"][1], "m3": L["met"][2], "m4": L["met"][3], "m5": L["met"][4], "mt": L["met"][5]}
for a in sys.argv[3:]:
    n, l, x, y = a.split(":")
    net = l2n.probe_net(lay[l], db.DPoint(float(x), float(y)))
    print(f"{n:12s} {l} ({x},{y}) -> {net.cluster_id if net is not None else None}")
