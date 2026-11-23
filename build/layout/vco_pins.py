"""Probe v3 VCO nets at the A01 pin points (VCO-local um) and list their upper-metal shapes."""
import sys, klayout.db as db
sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of
ly = db.Layout(); ly.read("/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout/Diff_VCO_XOR_Layout.gds")
top = ly.cell("Differential_VCO_XOR")
l2n, L = l2n_of(ly, top)
PINS = {"VDD_VCO": (0, -3.58, -8.99), "VDD_VCO2": (0, -2.6, -1.85), "VBUF_DIFF": (0, -4.39, 18.90), "VBUF_DOUBLER": (0, -16.83, 7.39),
        "VSS": (0, -24.83, 3.71), "VSS2": (0, -3.74, -6.34), "VTUNE": (0, -11.70, 14.18), "TAIL_BIAS": (0, -1.36, 12.18),
        "RF_OUT": (0, -24.83, 4.79), "CORE_CLK": (0, -7.31, 14.99), "XP": (2, -7.22, -41.13), "XN": (2, -12.72, -41.13), "VDD_RF": (1, -9.97, -37.93)}
seen = {}
for name, (lev, x, y) in PINS.items():
    net = l2n.probe_net(L["met"][lev], db.DPoint(x, y))
    if net is None:
        print(name, "NO NET"); continue
    print(f"== {name}: cluster {net.cluster_id} {'(same as ' + seen[net.cluster_id] + ')' if net.cluster_id in seen else ''}")
    if net.cluster_id in seen: continue
    seen[net.cluster_id] = name
    for nm, lr in zip(["M1", "M2", "M3", "M4", "M5", "MT"], L["met"]):
        reg = l2n.shapes_of_net(net, lr, True).merged()
        bb = reg.bbox()
        if reg.is_empty(): continue
        polys = list(reg.each())
        big = sorted(polys, key=lambda p: -p.area())[:4]
        print(f"  {nm}: {len(polys)} polys bbox [{bb.left/1e3:.2f},{bb.bottom/1e3:.2f},{bb.right/1e3:.2f},{bb.top/1e3:.2f}]  largest: " +
              "; ".join(f"[{p.bbox().left/1e3:.2f},{p.bbox().bottom/1e3:.2f},{p.bbox().right/1e3:.2f},{p.bbox().top/1e3:.2f}]" for p in big))
