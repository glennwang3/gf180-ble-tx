import sys
import klayout.db as db
sys.path.insert(0, "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout")
from cut_old import l2n_of, METAL
ly = db.Layout(); ly.read("/foss/designs/pll_compact/layout/vco_lc/Differential_VCO_LC.gds")
top = ly.cell("Differential_VCO_LC")
l2n, L = l2n_of(ly, top)
circ = l2n.netlist().circuit_by_name("Differential_VCO_LC")
names = ["M1", "M2", "M3", "M4", "M5", "MT"]
for net in circ.each_net():
    nm = net.expanded_name()
    if nm.startswith("$"):
        continue
    print("NET", nm)
    for i, lr in enumerate(L["met"]):
        r = l2n.shapes_of_net(net, lr, True).merged()
        if r.is_empty():
            continue
        bx = [p.bbox() for p in r.each()]
        big = sorted(bx, key=lambda b: -b.area())[:6]
        print(f"   {names[i]} {len(bx)}: " + "  ".join(f"[{b.left/1e3:.2f},{b.bottom/1e3:.2f},{b.right/1e3:.2f},{b.top/1e3:.2f}]" for b in big))
