#!/usr/bin/env python3
"""lvs_cell.py <gds> <cell> <ref.spice> <outdir>: flatten (keeping top labels) then magic+netgen LVS (gf180mcuE)."""
import os, sys, subprocess
import klayout.db as db
gds, cell, ref, out = sys.argv[1:5]
os.makedirs(out, exist_ok=True)
ly = db.Layout(); ly.read(gds); top = ly.cell(cell)
top.flatten(True)
ly.cleanup()
flat = os.path.join(out, cell + "_flat.gds")
ly.write(flat)
os.environ["TECH"] = "/foss/designs/pll_integration_repo/build/tech/gf180mcuE.tech"
here = os.path.dirname(os.path.abspath(__file__))
subprocess.run(["bash", os.path.join(here, "lvs.sh"), flat, cell, ref, out], check=False)
