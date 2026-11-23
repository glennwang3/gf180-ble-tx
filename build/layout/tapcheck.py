#!/usr/bin/env python3
"""tapcheck.py <gds> <cell> vss_layer x y [vdd...]: metal nets that touch a substrate tap (p+ COMP outside
n-well) but are not metal-connected to the reference VSS net -> grounded only through the substrate."""
import sys, klayout.db as db
sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of
ly = db.Layout(); ly.read(sys.argv[1]); top = ly.cell(sys.argv[2])
top.flatten(True)
l2n, L = l2n_of(ly, top)
ref = l2n.probe_net(L["met"][int(sys.argv[3])], db.DPoint(float(sys.argv[4]), float(sys.argv[5])))
comp = db.Region(top.shapes(ly.layer(22, 0))); pplus = db.Region(top.shapes(ly.layer(31, 0)))
nwell = db.Region(top.shapes(ly.layer(21, 0))); poly = db.Region(top.shapes(ly.layer(30, 0)))
cont = db.Region(top.shapes(ly.layer(33, 0)))
ptap = ((comp & pplus) - nwell - poly).merged()
seen = {}
for p in ptap.each():
    cs = cont & db.Region(p)
    if cs.is_empty():
        continue
    c = cs.bbox().center()
    n = l2n.probe_net(L["cont"], db.DPoint(c.x / 1000, c.y / 1000))
    if n is None or n.cluster_id == ref.cluster_id:
        continue
    seen.setdefault(n.cluster_id, []).append(p.bbox())
print("reference VSS cluster", ref.cluster_id, "  substrate-only ground islands:", len(seen))
for cid, bxs in seen.items():
    b = bxs[0]
    for x in bxs[1:]:
        b = b + x
    print(f"  cluster {cid}: {len(bxs)} taps, bbox [{b.left/1e3:.2f},{b.bottom/1e3:.2f},{b.right/1e3:.2f},{b.top/1e3:.2f}]")
