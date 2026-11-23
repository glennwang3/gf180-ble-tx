#!/usr/bin/env python3
"""Top-level connectivity check of PLL_COMPACT.gds: all labels removed, then one probe label per macro pin of
every top-level net; KLayout l2n (metals, vias, contacts; no device channels / wells) -> shorts and opens."""
import sys
import klayout.db as db
sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of
from route_top import PINS
LV = {"m1": 0, "m2": 1, "m3": 2, "m4": 3, "m5": 4, "mt": 5}
EXTRA = [  # net, layer, x, y   (hand-routed links: probe inside both macros)
    ("CORE_CLK", "m5", -7.31, 14.99), ("CORE_CLK", "m2", -6.8, 26.91),
    ("MC", "m2", -4.71, 24.26), ("MC", "m3", 22.10, 24.26),
    ("FB_1M", "m3", 73.70, 32.10), ("FB_1M", "m3", 77.60, 32.10), ("REF_1M", "m2", 88.45, 30.0),
    ("XP", "m3", -7.22, -40.0), ("XP", "m3", -19.02, -44.5), ("XN", "m3", -12.72, -40.0), ("XN", "m3", -12.72, -44.5),
    ("VDD_VCO", "m5", 20.0, -1.75), ("VDD_VCO", "m4", -2.60, -1.85),
    ("VCTRL", "m4", 149.12, -89.47), ("VCTRL", "m3", 152.70, -50.0),
    ("VSS", "mt", 177.0, -50.0),
]
ly = db.Layout(); ly.read(sys.argv[1] if len(sys.argv) > 1 else "PLL_COMPACT.gds")
top = ly.cell("PLL_COMPACT")
import os
if os.environ.get("MACROS_ONLY"):
    for li in ly.layer_indexes():
        top.shapes(li).clear()
top.flatten(True)
for li in ly.layer_indexes():
    if ly.get_info(li).datatype == 10:
        top.shapes(li).clear()
probes = [(n, "m1 m2 m3 m4 m5 mt".split()[lev], x, y) for n, b, lev, x, y in PINS] + EXTRA
l2n, L = l2n_of(ly, top)
groups = {}
for net, lay, x, y in probes:
    n = l2n.probe_net(L["met"][LV[lay]], db.DPoint(x, y))
    if n is None:
        print(f"NO METAL {net} {lay} ({x},{y})"); continue
    groups.setdefault(n.cluster_id, set()).add(net)
    if os.environ.get("SHOW"): print(net, lay, x, y, n.cluster_id)
    groups.setdefault(("pin", net), set()).add(n.cluster_id)
bad = 0
for k, v in groups.items():
    if not (isinstance(k, tuple)) and len(v) > 1:
        print("SHORT", sorted(v)); bad += 1
for k, v in groups.items():
    if isinstance(k, tuple) and len(v) > 1:
        print("OPEN", k[1], len(v), "clusters"); bad += 1
print("nets checked:", len({p[0] for p in probes}), " probes:", len(probes), " problems:", bad)
