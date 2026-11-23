import sys, klayout.db as db
sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of
ly = db.Layout(); ly.read(sys.argv[1]); top = ly.cell(sys.argv[2])
l2n, L = l2n_of(ly, top)
net = l2n.probe_net(L["met"][int(sys.argv[3])], db.DPoint(float(sys.argv[4]), float(sys.argv[5])))
print("net", net.cluster_id, net.expanded_name())
for nm, lr in zip(["M1", "M2", "M3", "M4", "M5", "MT"], L["met"]):
    r = l2n.shapes_of_net(net, lr, True).merged()
    if not r.is_empty():
        print(nm, "; ".join(f"[{p.bbox().left/1e3:.2f},{p.bbox().bottom/1e3:.2f},{p.bbox().right/1e3:.2f},{p.bbox().top/1e3:.2f}]" for p in list(r.each())[:8]))
for nm, lr in (("sd", L["sd"]),):
    r = l2n.shapes_of_net(net, lr, True).merged()
    print("diffusion pieces:", r.count(), "; ".join(f"[{p.bbox().left/1e3:.2f},{p.bbox().bottom/1e3:.2f},{p.bbox().right/1e3:.2f},{p.bbox().top/1e3:.2f}]" for p in list(r.each())[:6]))
