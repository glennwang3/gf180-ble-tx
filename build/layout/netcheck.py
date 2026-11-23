"""netcheck.py <gds> <cell>: KLayout l2n; report nets carrying more than one distinct label (shorts)
and label names split over several nets (opens).  Debug labels VSSR/VINR count as VSS/VIN."""
import sys
import klayout.db as db
sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of
ly = db.Layout(); ly.read(sys.argv[1]); top = ly.cell(sys.argv[2])
alias = dict(a.split("=") for a in sys.argv[3:])
l2n, L = l2n_of(ly, top)
names = {}
for (l, d) in ((34, 10), (36, 10), (42, 10), (46, 10), (81, 10), (53, 10)):
    li = ly.layer(l, d)
    it = top.begin_shapes_rec(li)
    lv = {34: 0, 36: 1, 42: 2, 46: 3, 81: 4, 53: 5}[l]
    while not it.at_end():
        s = it.shape()
        if s.is_text():
            p = it.trans() * s.text.trans.disp
            net = l2n.probe_net(L["met"][lv], db.DPoint(p.x * ly.dbu, p.y * ly.dbu))
            nm = alias.get(s.text.string, s.text.string)
            names.setdefault(net.cluster_id if net is not None else None, []).append((nm, round(p.x * ly.dbu, 2), round(p.y * ly.dbu, 2)))
        it.next()
bad = 0
for cid, lst in names.items():
    distinct = sorted({n for n, _, _ in lst})
    if len(distinct) > 1:
        bad += 1
        print("SHORT", distinct, lst[:12])
per = {}
for cid, lst in names.items():
    for n, x, y in lst:
        per.setdefault(n, set()).add(cid)
for n, cids in per.items():
    if len(cids) > 1:
        print("SPLIT", n, len(cids))
print("shorts:", bad)
