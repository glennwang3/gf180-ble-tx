#!/usr/bin/env python3
"""Build the PLL_COMPACT LVS reference for the repo's root lvs_config.json.

One file per macro, subckt renamed to the macro's GDS cell name, plus a top netlist without .include lines
(the chipathon LVS flow reads every file listed in LVS_SPICE_FILES). Then run netgen against the full-chip
extraction in layout/lvs_top to check the reference is complete.
    python3 gen_ref.py OUT_DIR
"""
import os
import re
import subprocess
import sys

L = "/foss/designs/pll_compact/layout"
VCO = "/foss/designs/Diff_VCO_Second_Layout/vco_xor_layout/lvs_vco/VCO_XOR_LVS_lvs.spice"
# source file, subckt name in it -> GDS cell name in PLL_COMPACT.gds
SRC = [
    (f"{L}/lvs_top/ref_prescaler/M_prescaler.spice", "M_prescaler", "32_33_Complete_Prescaler"),
    (f"{L}/lvs_top/ref_divider/M_divider.spice", "M_divider", "ble_feedback_divider"),
    (f"{L}/lvs_top/ref_pfd/M_pfd.spice", "M_pfd", "Phase_Detector_FE"),
    (f"{L}/lvs_top/ref_pump/M_pump.spice", "M_pump", "Charge_Pump_FE"),
    (f"{L}/lvs_top/ref_tx/M_tx.spice", "M_tx", "ble_tx_uart"),
    (VCO, "VCO_XOR_LVS", "Differential_VCO_XOR"),
    (f"{L}/VCO_REG_L.spice", "VCO_REG_L", "VCO_REG_L"),
    (f"{L}/PLL_LF_L.spice", "PLL_LF_L", "PLL_LF_L"),
    (f"{L}/RF_CONV_PA.spice", "RF_CONV_PA", "RF_CONV_PA"),
    (f"{L}/PLL_BIAS.spice", "PLL_BIAS", "PLL_BIAS"),
]


def rename(txt, old, new):
    txt = re.sub(rf"^(\.subckt\s+){re.escape(old)}(\s)", rf"\g<1>{new}\2", txt, flags=re.M | re.I)
    txt = re.sub(rf"^(\.ends\s+){re.escape(old)}\s*$", rf"\g<1>{new}", txt, flags=re.M | re.I)
    return txt


def main(out):
    os.makedirs(os.path.join(out, "macros"), exist_ok=True)
    names = {}
    files = []
    for path, old, new in SRC:
        txt = open(path).read()
        assert re.search(rf"^\.subckt\s+{re.escape(old)}\s", txt, re.M | re.I), (path, old)
        assert not re.search(r"^\.(include|lib)\b", txt, re.M | re.I), path
        names[old] = new
        f = os.path.join(out, "macros", new + ".spice")
        open(f, "w").write(f"* {new}: LVS reference (from {os.path.basename(path)}, subckt {old} renamed)\n"
                           + rename(txt, old, new))
        files.append(f)
    top = open(f"{L}/lvs_top/PLL_COMPACT_ref.spice").read()
    top = "\n".join(l for l in top.splitlines() if not l.lower().startswith(".include"))
    for old, new in names.items():
        top = re.sub(rf"\s{re.escape(old)}\s*$", f" {new}", top, flags=re.M)
    top = top.replace("* PLL_COMPACT top-level LVS reference",
                      "* PLL_COMPACT top-level LVS reference. The macro subckts are in macros/*.spice;\n"
                      "* lvs_config.json lists every file in LVS_SPICE_FILES.")
    ftop = os.path.join(out, "PLL_COMPACT_lvs.spice")
    open(ftop, "w").write(top + "\n")
    # check: one deck = all files concatenated, vs the full-chip flat extraction
    chk = os.path.join(out, "check")
    os.makedirs(chk, exist_ok=True)
    deck = os.path.join(chk, "ref_all.spice")
    with open(deck, "w") as d:
        for f in files + [ftop]:
            d.write(open(f).read() + "\n")
    setup = "/foss/pdks/gf180mcuD/libs.tech/netgen/gf180mcuD_setup.tcl"
    subprocess.run(f"cd {chk} && netgen -batch lvs '{L}/lvs_top/PLL_COMPACT.spice PLL_COMPACT' "
                   f"'{deck} PLL_COMPACT' {setup} lvs.report > netgen.log 2>&1", shell=True)
    print(subprocess.run(f"grep -E 'Final result|do not match|Number of devices|Number of nets' {chk}/lvs.report | tail -5",
                         shell=True, capture_output=True, text=True).stdout)


if __name__ == "__main__":
    main(sys.argv[1])
