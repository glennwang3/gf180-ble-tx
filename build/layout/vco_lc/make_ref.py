#!/usr/bin/env python3
"""LVS reference for Differential_VCO_LC: magic extraction of the delivered cell (stray P/N/B labels removed,
as in build_vco_lc.py) minus the four FETs of the removed 2nd / 3rd doubler inverters."""
import os
import re
import subprocess
import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/foss/designs/Diff_VCO_Second_Layout/low_cap_vco_20261122/delivery/Differential_VCO_low_cap.gds"
ly = db.Layout(); ly.read(SRC)
c = ly.cell("Differential_VCO")
for li in ly.layer_indexes():
    for s in list(c.shapes(li).each()):
        if s.is_text() and s.text.string in ("P", "N", "B"):
            c.shapes(li).erase(s)
os.makedirs(os.path.join(HERE, "ext_orig"), exist_ok=True)
ly.write(os.path.join(HERE, "ext_orig", "orig_nolabel.gds"))
env = dict(os.environ, TECH="/foss/designs/pll_integration_repo/build/tech/gf180mcuE.tech")
subprocess.run(["python3", os.path.join(HERE, "..", "lvs_cell.py"), os.path.join(HERE, "ext_orig", "orig_nolabel.gds"),
                "Differential_VCO", "/dev/null", os.path.join(HERE, "ext_orig")], env=env, capture_output=True)
s = re.sub(r"\n\+", " ", open(os.path.join(HERE, "ext_orig", "Differential_VCO_lvs.spice")).read())
lines = s.splitlines()
# the removed inverters: devices whose drain or gate is RF_DRV2 / RF_OUT
dead = [l.split()[0] for l in lines if l.startswith("X") and ({"RF_DRV2", "RF_OUT"} & set(l.split()[1:4]))]
assert len(dead) == 4, dead
out = []
for l in lines:
    t = l.split()
    if t and t[0] in dead:
        continue
    if l.startswith(".subckt"):
        l = " ".join(p for p in t if p not in ("RF_DRV2", "RF_OUT")).replace("Differential_VCO ", "Differential_VCO_LC ")
    out.append(l)
open(os.path.join(HERE, "ref_lc.spice"), "w").write("\n".join(out) + "\n")
print("removed", dead, "->", sum(1 for l in out if l.startswith(("X", "D"))), "devices")
print([l for l in out if l.startswith(".subckt")][0])
