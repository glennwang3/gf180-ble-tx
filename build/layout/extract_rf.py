#!/usr/bin/env python3
"""RC extraction of the PLL_COMPACT RF / supply partition: low-cap Schottky VCO, RF_CHAIN_PA, prescaler,
VCO_REG_L, PLL_BIAS and ALL top-level routing.  Writes pex_rf/RF_PART_rcpex.spice (subckt RF_PART)."""
import os
import subprocess
import klayout.db as db
import json
import build_top as BT
from route_top import chain_label

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, os.environ.get("PEX_OUT", "pex_rf"))
KEEP = tuple(os.environ.get("PEX_KEEP", "vco,chain,prescaler,reg,bias").split(","))
_land = json.load(open(os.path.join(HERE, "pins.json")))["land"]
VSS_CHAIN = next((x, y) for n, b, x, y in _land if n == "VSS" and b == "chain")
CPI_BIAS = next((x, y) for n, b, x, y in _land if n == "CP_IBIAS" and b == "bias")      # MT escape landings
TB_BIAS = next((x, y) for n, b, x, y in _land if n == "TAIL_BIAS" and b == "bias")
PORTS = [  # name, (layer, dt), x, y
    ("VDD", (53, 10), 146.12, -75.07), ("VSS", (53, 10), *VSS_CHAIN), ("VCTRL", (46, 10), 150.9, -89.47),
    ("VDD_VCO", (53, 10), 5.0, -1.75), ("CORE_CLK", (53, 10), -8.0, 20.0), ("PRESCALED", (53, 10), 4.33, 30.58),
    ("MC", (46, 10), 10.0, 24.26), ("PA_DRAIN", (46, 10), *chain_label("PA_DRAIN")), ("D1", (34, 10), *chain_label("D1")),
    ("RF_DRV1", (42, 10), -25.0, 5.5), ("TAIL_BIAS", (53, 10), *TB_BIAS),
    ("CP_IBIAS", (53, 10), *CPI_BIAS), ("VTUNE", (34, 10), -11.70, 14.18),
    ("DOUBLER_K", (34, 10), -8.98, 3.975), ("MIM_TOP", (34, 10), -15.85, 4.25),
    ("O1P", (34, 10), -3.47, 6.31), ("O1N", (34, 10), -3.79, 4.84), ("O2N", (34, 10), 3.33, -5.31),
    ("O2P", (36, 10), 0.3, 6.85), ("O3N", (34, 10), 3.33, 4.69), ("O3P", (36, 10), -0.44, -5.85),
    ("O4N", (34, 10), -3.47, -3.69), ("O4P", (34, 10), -3.79, -5.16),
]

LOOP_PORTS = [("VDD", (53, 10), 146.12, -75.07), ("VSS", (53, 10), 108.2, 15.0), ("VCTRL", (46, 10), 150.9, -89.47),
              ("VDD_VCO", (53, 10), 5.0, -1.75), ("REF_1M", (36, 10), 89.11, 32.10), ("FB_1M", (42, 10), 75.5, 32.10),
              ("UPB", (53, 10), 80.80, 30.47), ("DN", (53, 10), 83.45, 29.52), ("CP_IBIAS", (53, 10), *CPI_BIAS),
              ("TAIL_BIAS", (53, 10), *TB_BIAS)]
if os.environ.get("PEX_LOOP"):
    PORTS = LOOP_PORTS


def main():
    os.makedirs(OUT, exist_ok=True)
    ly = db.Layout(); ly.read(os.path.join(HERE, "PLL_COMPACT.gds"))
    top = ly.cell("PLL_COMPACT")
    keep_cells = {BT.PLACE[k][1] for k in KEEP}
    for inst in list(top.each_inst()):
        if inst.cell.name.split("$")[0] not in keep_cells:
            inst.delete()
    top.flatten(True)
    for li in ly.layer_indexes():
        if ly.get_info(li).datatype == 10:
            top.shapes(li).clear()
    for name, (l, d), x, y in PORTS:
        top.shapes(ly.layer(l, d)).insert(db.Text(name, db.Trans(round(x * 1000), round(y * 1000))))
    top.name = os.environ.get("PEX_CELL", "RF_PART")
    CELL = top.name
    ly.cleanup()
    gds = os.path.join(OUT, CELL + ".gds")
    ly.write(gds)
    rc = os.path.join(OUT, "magicrc_e")
    open(rc, "w").write("crashbackups stop\ntech load {/foss/designs/pll_integration_repo/build/tech/gf180mcuE.tech}\n"
                        "scalegrid 1 10\ndrc off\n")
    tcl = f"""gds read {gds}
load {CELL}
select top cell
extract do resistance
extract all
ext2sim labels on
ext2sim
extresist tolerance 1
extresist all
ext2spice lvs
ext2spice cthresh 0.01
ext2spice extresist on
ext2spice -o {CELL}_rcpex.spice
quit -noprompt
"""
    open(os.path.join(OUT, "ext.tcl"), "w").write(tcl)
    subprocess.run(f"cd {OUT} && magic -dnull -noconsole -rcfile magicrc_e ext.tcl > magic.log 2>&1", shell=True)
    sp = open(os.path.join(OUT, CELL + "_rcpex.spice")).read()
    if os.environ.get("PEX_LOOP"):
        # sim/lock/*.py and sim/tx/tx_loop.py instantiate LOOP_PART by position: keep the port order fixed
        import re
        hdr = ".subckt LOOP_PART VDD_VCO VDD VSS UPB DN CP_IBIAS TAIL_BIAS REF_1M FB_1M VCTRL"
        m = re.search(r"^\.subckt LOOP_PART [^\n]*", sp, re.M)
        assert set(m.group(0).split()[2:]) == set(hdr.split()[2:]), m.group(0)
        sp = sp.replace(m.group(0), hdr, 1)
        open(os.path.join(OUT, CELL + "_rcpex.spice"), "w").write(sp)
    print("subckt line:", [l for l in sp.splitlines() if l.startswith(".subckt")][:1])
    print("devices X:", sum(1 for l in sp.splitlines() if l.startswith("X")), " R:", sum(1 for l in sp.splitlines() if l.startswith("R")),
          " C:", sum(1 for l in sp.splitlines() if l.startswith("C")))


if __name__ == "__main__":
    main()
