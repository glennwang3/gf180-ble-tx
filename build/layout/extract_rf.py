#!/usr/bin/env python3
"""RC extraction of the PLL_COMPACT RF / supply partition: VCO (+XOR, Schottky path), RF_CONV_PA, prescaler,
VCO_REG_L, PLL_BIAS and ALL top-level routing.  Writes pex_rf/RF_PART_rcpex.spice (subckt RF_PART)."""
import os
import subprocess
import klayout.db as db
import build_top as BT

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, os.environ.get("PEX_OUT", "pex_rf"))
KEEP = tuple(os.environ.get("PEX_KEEP", "vco,conv,prescaler,reg,bias").split(","))
PORTS = [  # name, (layer, dt), x, y
    ("VDD", (53, 10), 146.12, -75.07), ("VSS", (53, 10), 1.68, -79.51), ("VCTRL", (46, 10), 150.9, -89.47),
    ("VDD_VCO", (81, 10), 5.0, -1.75), ("CORE_CLK", (53, 10), -7.31, 20.0), ("PRESCALED", (53, 10), 4.33, 30.58),
    ("MC", (46, 10), 10.0, 24.26), ("PA_DRAIN", (46, 10), -52.80, -74.30), ("D1", (34, 10), -47.20, -73.22),
    ("XP", (42, 10), -19.02, -44.03), ("XN", (42, 10), -12.72, -43.0), ("TAIL_BIAS", (53, 10), 108.2, 19.8),
    ("CP_IBIAS", (53, 10), 108.2, 32.6), ("VTUNE", (34, 10), -12.20, 14.18), ("RF_OUT", (34, 10), -24.83, 4.79),
    ("DOUBLER_K", (34, 10), -8.98, 3.975), ("MIM_TOP", (34, 10), -15.85, 4.25),
    ("O1N", (36, 10), -8.42, -9.25), ("O1P", (36, 10), -11.52, -9.25), ("O2N", (36, 10), -7.72, -12.61),
    ("O2P", (36, 10), -12.22, -12.61), ("O3N", (36, 10), -5.58, -15.97), ("O3P", (36, 10), -14.36, -15.97),
    ("O4N", (36, 10), -4.48, -19.33), ("O4P", (36, 10), -15.46, -19.33),
]

LOOP_PORTS = [("VDD", (53, 10), 146.12, -75.07), ("VSS", (53, 10), 108.2, 15.0), ("VCTRL", (46, 10), 150.9, -89.47),
              ("VDD_VCO", (81, 10), 5.0, -1.75), ("REF_1M", (36, 10), 89.11, 32.10), ("FB_1M", (42, 10), 75.5, 32.10),
              ("UPB", (53, 10), 80.80, 30.47), ("DN", (53, 10), 83.45, 29.52), ("CP_IBIAS", (53, 10), 108.2, 32.6),
              ("TAIL_BIAS", (53, 10), 108.2, 19.8)]
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
    print("subckt line:", [l for l in sp.splitlines() if l.startswith(".subckt")][:1])
    print("devices X:", sum(1 for l in sp.splitlines() if l.startswith("X")), " R:", sum(1 for l in sp.splitlines() if l.startswith("R")),
          " C:", sum(1 for l in sp.splitlines() if l.startswith("C")))


if __name__ == "__main__":
    main()
