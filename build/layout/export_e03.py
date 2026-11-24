#!/usr/bin/env python3
"""
Tapeout export for the Chipathon 2026 shuttle, team E03.

  layout/PLL_COMPACT.gds  ->  tapeout_e03/gds/E03.gds        top cell E03
                          ->  tapeout_e03/spice/E03_lvs.spice + spice/macros/E03_*.spice
                          ->  tapeout_e03/lvs_config.json

Naming:
  * top cell and GDS file: E03 (team code); lvs_config TOP_SOURCE / TOP_LAYOUT = E03.
  * every other cell gets the E03_ prefix (generic PDK cell names such as pfet, nfet$2, via_dev or TAP_SUB would
    otherwise collide with other projects' cells when the shuttle merges the GDS files); the standard cells
    (gf180mcu_fd_sc_*) keep their library names.
  * top-level pins use the info.yaml names and case: vdd, vss, reset_n, clk, Tx, ANT (PAD map below). Each pin
    label gets a small top-cell pad on the same layer, so it attaches in a hierarchical extraction too.
  * a PR_bndry (0/0) rectangle on the top-level bounding box.
The other top-level labels (internal nets, e.g. VCTRL, VTUNE, REF_1M, CFG[*]) are kept as in lvs_top.py.
Checks: python3 export_e03.py check  -> flat extraction of E03.gds vs the reference (netgen).
"""
import os
import re
import shutil
import subprocess
import sys
import json
import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "tapeout_e03")
TEAM = "E03"
STD = "gf180mcu_fd_sc_"
PAD = {"VDD": "vdd", "VSS": "vss", "RST_N": "reset_n", "CLK_8M": "clk", "UART_RX": "Tx", "PA_DRAIN": "ANT"}
sys.path.insert(0, HERE)
import lvs_top as LT  # noqa: E402  (TOP_LABELS, macro reference files)

L = HERE
# reference file, subckt name in it, GDS cell name in PLL_COMPACT.gds
REFS = [
    (f"{L}/lvs_top/ref_prescaler/M_prescaler.spice", "M_prescaler", "32_33_Complete_Prescaler"),
    (f"{L}/lvs_top/ref_divider/M_divider.spice", "M_divider", "ble_feedback_divider"),
    (f"{L}/lvs_top/ref_pfd/M_pfd.spice", "M_pfd", "Phase_Detector_FE"),
    (f"{L}/lvs_top/ref_pump/M_pump.spice", "M_pump", "Charge_Pump_FE"),
    (f"{L}/lvs_top/ref_tx/M_tx.spice", "M_tx", "ble_tx_uart"),
    (f"{L}/vco_lc/ref_lc.spice", "Differential_VCO_LC", "Differential_VCO_LC"),
    (f"{L}/RF_CHAIN_PA.spice", "RF_CHAIN_PA", "RF_CHAIN_PA"),
    (f"{L}/VCO_REG_L.spice", "VCO_REG_L", "VCO_REG_L"),
    (f"{L}/PLL_LF_L.spice", "PLL_LF_L", "PLL_LF_L"),
    (f"{L}/PLL_BIAS.spice", "PLL_BIAS", "PLL_BIAS"),
]


def cname(name):
    return name if name.startswith(STD) else f"{TEAM}_{name}"


def pnet(net):
    return PAD.get(net, net)


def top_labels():
    """the lvs_top.py label set (named top-level nets), pad nets renamed"""
    land = json.load(open(os.path.join(L, "pins.json")))["land"]
    labels, done = [], set()
    for net, ld, x, y in LT.TOP_LABELS:
        labels.append((pnet(net), ld, x, y)); done.add(net)
    for net, blk, x, y in land:
        if net not in done:
            labels.append((pnet(net), (53, 10), x, y)); done.add(net)
    return labels


def export_gds():
    ly = db.Layout(); ly.read(os.path.join(L, "PLL_COMPACT.gds"))
    top = ly.cell("PLL_COMPACT")
    bb = top.bbox()
    for li in ly.layer_indexes():                       # top-cell labels -> the lvs_top set
        sh = top.shapes(li)
        for s in [s for s in sh.each() if s.is_text()]:
            sh.erase(s)
    for net, (l, d), x, y in top_labels():
        top.shapes(ly.layer(l, d)).insert(db.Text(net, db.Trans(round(x * 1000), round(y * 1000))))
        if net in PAD.values():                         # attach: small pad of the label's metal in the top cell
            top.shapes(ly.layer(l, 0)).insert(db.Box(round(x * 1000) - 140, round(y * 1000) - 140,
                                                     round(x * 1000) + 140, round(y * 1000) + 140))
    top.shapes(ly.layer(0, 0)).insert(bb)              # PR_bndry
    for c in list(ly.each_cell()):
        c.name = TEAM if c.cell_index() == top.cell_index() else cname(c.name)
    os.makedirs(os.path.join(OUT, "gds"), exist_ok=True)
    f = os.path.join(OUT, "gds", f"{TEAM}.gds")
    ly.write(f)
    n = sum(1 for _ in ly.each_cell())
    print(f"wrote {f}: top {TEAM}, {n} cells, bbox {bb.left/1e3:.2f},{bb.bottom/1e3:.2f} .. {bb.right/1e3:.2f},{bb.top/1e3:.2f}")


def rename_subckt(txt, old, new):
    txt = re.sub(rf"^(\.subckt\s+){re.escape(old)}(\s)", rf"\g<1>{new}\2", txt, flags=re.M | re.I)
    txt = re.sub(rf"^(\.ends)(\s+{re.escape(old)})?\s*$", rf"\g<1> {new}", txt, flags=re.M | re.I)
    return txt


def export_spice():
    os.makedirs(os.path.join(OUT, "spice", "macros"), exist_ok=True)
    files, model = [], {}
    for path, old, cell in REFS:
        txt = open(path).read()
        assert re.search(rf"^\.subckt\s+{re.escape(old)}\s", txt, re.M | re.I), (path, old)
        assert not re.search(r"^\.(include|lib)\b", txt, re.M | re.I), path
        new = cname(cell)
        model[old] = new
        f = os.path.join(OUT, "spice", "macros", new + ".spice")
        open(f, "w").write(f"* {new}: LVS reference of GDS cell {new} (from {os.path.basename(path)}, subckt {old})\n"
                           + rename_subckt(txt, old, new))
        files.append(f)
    top = open(os.path.join(L, "lvs_top", "PLL_COMPACT_ref.spice")).read()
    lines = [l for l in top.splitlines() if not l.lower().startswith(".include")]
    out = []
    for l in lines:
        if l.startswith(".subckt PLL_COMPACT") or l.startswith("X") or l.startswith("+"):
            for a, b in PAD.items():
                l = re.sub(rf"(?<![\w\[\]]){re.escape(a)}(?![\w\[\]])", b, l)
            if l.startswith("X"):
                t = l.split()
                t[-1] = model.get(t[-1], t[-1])
                l = " ".join(t)
            l = l.replace(".subckt PLL_COMPACT ", f".subckt {TEAM} ")
        if l.startswith(".ends"):
            l = f".ends {TEAM}"
        out.append(l)
    out[0] = (f"* {TEAM} top-level LVS reference (PLL_COMPACT renamed for the tapeout; pads: "
              + ", ".join(f"{a}->{b}" for a, b in PAD.items()) + ").\n* Macro subckts: macros/*.spice, "
              "all listed in lvs_config.json LVS_SPICE_FILES.")
    ftop = os.path.join(OUT, "spice", f"{TEAM}_lvs.spice")
    open(ftop, "w").write("\n".join(out) + "\n")
    cfg = {
        "STD_CELL_LIBRARY": "gf180mcu_fd_sc_mcu7t5v0",
        "INCLUDE_CONFIGS": ["$LVS_ROOT/tech/$PDK/lvs_config.base.json"],
        "TOP_SOURCE": TEAM,
        "TOP_LAYOUT": "$TOP_SOURCE",
        "EXTRACT_FLATGLOB": [""], "EXTRACT_ABSTRACT": [""], "LVS_FLATTEN": [""], "LVS_NOFLATTEN": [""], "LVS_IGNORE": [""],
        "LVS_SPICE_FILES": [f"$UPRJ_ROOT/build/spice/macros/{os.path.basename(f)}" for f in sorted(files)]
                           + [f"$UPRJ_ROOT/build/spice/{TEAM}_lvs.spice"],
        "LVS_VERILOG_FILES": [""],
        "LAYOUT_FILE": "$UPRJ_ROOT/build/gds/$TOP_LAYOUT.gds",
    }
    open(os.path.join(OUT, "lvs_config.json"), "w", newline="\n").write(json.dumps(cfg, indent="\t") + "\n")
    print(f"wrote {len(files)} macro references, {ftop}, lvs_config.json")
    return files, ftop


def check(files, ftop):
    """flat extraction of E03.gds (top-cell labels only, as lvs_top.py does) vs the reference"""
    chk = os.path.join(OUT, "check")
    os.makedirs(chk, exist_ok=True)
    ly = db.Layout(); ly.read(os.path.join(OUT, "gds", f"{TEAM}.gds"))
    top = ly.cell(TEAM)
    keep = [(li, s.text.dup()) for li in ly.layer_indexes() for s in top.shapes(li).each() if s.is_text()]
    top.flatten(True)
    for li in ly.layer_indexes():
        sh = top.shapes(li)
        for s in [s for s in sh.each() if s.is_text()]:
            sh.erase(s)
    for li, t in keep:
        top.shapes(li).insert(t)
    ly.cleanup()
    flat = os.path.join(chk, f"{TEAM}_flat.gds")
    ly.write(flat)
    n = subprocess.run(f"bash {L}/ext.sh {flat} {TEAM} {chk}", shell=True, capture_output=True, text=True).stdout
    print("layout devices:", n.strip())
    deck = os.path.join(chk, "ref_all.spice")
    with open(deck, "w") as d:
        for f in files + [ftop]:
            d.write(open(f).read() + "\n")
    setup = "/foss/pdks/gf180mcuD/libs.tech/netgen/gf180mcuD_setup.tcl"
    subprocess.run(f"cd {chk} && netgen -batch lvs '{TEAM}.spice {TEAM}' '{deck} {TEAM}' {setup} lvs.report "
                   f"> netgen.log 2>&1", shell=True)
    print(subprocess.run(f"grep -E 'Final result|do not match|Number of devices|Number of nets|Cell pin lists' "
                         f"{chk}/lvs.report | tail -6", shell=True, capture_output=True, text=True).stdout)


if __name__ == "__main__":
    export_gds()
    files, ftop = export_spice()
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check(files, ftop)
