#!/usr/bin/env python3
"""
Top-level LVS of PLL_COMPACT.

Reference = one instance per macro, each macro's netlist taken from its own (independently verified)
extraction / LVS reference, wired by the intended top-level net map below.
Layout    = PLL_COMPACT flattened, ALL labels removed, then exactly one label per top-level net
            (so magic cannot join nets through same-name labels).
"""
import json
import os
import re
import subprocess
import klayout.db as db
import build_top as BT

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "lvs_top")
VCO_REF = os.path.join(HERE, "vco_lc", "ref_lc.spice")      # vco_lc/make_ref.py
from route_top import chain_label  # noqa: E402
PA_PIN = chain_label("PA_DRAIN")
CODES = {f"fine_code[{i}]": f"FINE_CODE[{i}]" for i in range(8)}
MAP = {
    "prescaler": {"VDD": "VDD", "VSS": "VSS", "CLK_IN": "CORE_CLK", "MC": "MC", "CLK_OUT": "PRESCALED"},
    "divider": {"VDD": "VDD", "VSS": "VSS", "rst_n": "RST_N", "clk_prescaled": "PRESCALED", "clk_feedback": "FB_1M",
                "modulus_33": "MC", **{f"cfg_divider[{i}]": f"CFG[{i}]" for i in range(6)}},
    "pfd": {"VDD": "VDD", "VSS": "VSS", "F_REF": "REF_1M", "F_VCO": "FB_1M", "UPb": "UPB", "DN": "DN"},
    "pump": {"VDD": "VDD", "VSS": "VSS", "UPb": "UPB", "DN": "DN", "IBIAS": "CP_IBIAS", "OUT": "VCTRL"},
    "tx": {"VDD": "VDD", "VSS": "VSS", "clk": "CLK_8M", "rst_n": "RST_N", "uart_rx": "UART_RX", "code_valid": "CODE_VALID",
           "air_bit": "AIR_BIT", "sym_strobe": "SYM_STROBE", **CODES},
    "vco": {"VDD": "VDD_VCO", "VSS": "VSS", "VTUNE": "VTUNE", "TAIL_BIAS": "TAIL_BIAS", "CORE_CLK": "CORE_CLK",
            "RF_DRV1": "RF_DRV1", "VBUF_DOUBLER": "VDD", "VBUF_DIFF": "VDD"},
    "reg": {"VIN": "VDD", "VCTRL": "VCTRL", "VOUT": "VDD_VCO", "VSS": "VSS"},
    "lf": {"VCTRL": "VCTRL", "VSS": "VSS"},
    "chain": {"RF_DRV1": "RF_DRV1", "VDD": "VDD", "VSS": "VSS", "PA_DRAIN": "PA_DRAIN"},
    "bias": {"VDD": "VDD", "VSS": "VSS", "IBIAS": "CP_IBIAS", "TAIL_BIAS": "TAIL_BIAS"},
}
OWN_REF = {"reg": ("VCO_REG_L.spice", "VCO_REG_L"), "lf": ("PLL_LF_L.spice", "PLL_LF_L"),
           "chain": ("RF_CHAIN_PA.spice", "RF_CHAIN_PA"), "bias": ("PLL_BIAS.spice", "PLL_BIAS")}
TX0 = (-340.0, -95.0)
TOP_LABELS = [  # net, layer(l, d), x, y  -- one per net
    ("CORE_CLK", (53, 10), -8.0, 20.0), ("MC", (46, 10), 10.0, 24.26), ("FB_1M", (42, 10), 75.5, 32.10),
    ("VDD_VCO", (53, 10), 5.0, -1.75),
    ("VTUNE", (34, 10), -11.70, 14.18), ("RF_DRV1", (42, 10), -25.0, 5.5), ("REF_1M", (36, 10), 89.11, 32.10),
    ("PA_DRAIN", (46, 10), *PA_PIN),
    ("CFG[0]", (42, 10), 22.28, 39.94), ("CFG[3]", (42, 10), 22.28, 46.66), ("CFG[4]", (42, 10), 22.28, 38.82),
    ("CFG[5]", (42, 10), 73.56, 41.06), ("CFG[1]", (36, 10), 38.84, 68.82), ("CFG[2]", (36, 10), 37.72, 68.82),
    ("CLK_8M", (42, 10), TX0[0] + 0.28, TX0[1] + 283.64), ("UART_RX", (36, 10), TX0[0] + 20.44, TX0[1] + 299.72),
    ("CODE_VALID", (42, 10), TX0[0] + 269.72, TX0[1] + 226.52), ("AIR_BIT", (42, 10), TX0[0] + 269.72, TX0[1] + 167.16),
    ("SYM_STROBE", (42, 10), TX0[0] + 269.72, TX0[1] + 225.40),
] + [(f"FINE_CODE[{i}]", (36, 10), TX0[0] + x, TX0[1] + 0.28) for i, x in
     enumerate((251.16, 262.36, 226.52, 225.40, 227.64, 264.60, 263.48, 239.96))]


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def subckt_ports(path, name):
    txt = re.sub(r"\n\+", " ", open(path).read())
    m = re.search(rf"^\.subckt\s+{re.escape(name)}\s+(.*)$", txt, re.M | re.I)
    return m.group(1).split()


def macro_refs():
    """self-extract the A01 macros (flattened, own labels kept)"""
    refs = {}
    for key in ("prescaler", "divider", "pfd", "pump", "tx"):
        gds, cell = BT.PLACE[key][0], BT.PLACE[key][1]
        d = os.path.join(OUT, "ref_" + key)
        os.makedirs(d, exist_ok=True)
        ly = db.Layout(); ly.read(gds); c = ly.cell(cell)
        keep = []                                   # the macro's own (top-cell) labels only
        for li in ly.layer_indexes():
            for s_ in c.shapes(li).each():
                if s_.is_text():
                    keep.append((li, s_.text.dup()))
        c.flatten(True)
        for li in ly.layer_indexes():
            for s_ in list(c.shapes(li).each()):
                if s_.is_text():
                    c.shapes(li).erase(s_)
        for li, t in keep:
            c.shapes(li).insert(t)
        name = "M_" + key
        c.name = name
        for cc in list(ly.top_cells()):
            if cc.cell_index() != c.cell_index():
                ly.delete_cell_rec(cc.cell_index())
        ly.write(os.path.join(d, name + ".gds"))
        n = sh(f"bash {HERE}/ext.sh {d}/{name}.gds {name} {d}")
        print(f"ref {key}: {n.strip()} devices")
        refs[key] = (os.path.join(d, name + ".spice"), name)
    refs["vco"] = (VCO_REF, "Differential_VCO_LC")
    for k, (f, n) in OWN_REF.items():
        refs[k] = (os.path.join(HERE, f), n)
    return refs


def reference(refs):
    lines = ["* PLL_COMPACT top-level LVS reference"]
    seen = set()
    for key, (f, n) in refs.items():
        if f not in seen:
            lines.append(f".include {f}")
            seen.add(f)
    nets = sorted({l[0] for l in TOP_LABELS} | {"VDD", "VSS", "VCTRL", "PRESCALED", "UPB", "DN", "CP_IBIAS",
                                                 "TAIL_BIAS", "RST_N"})
    lines.append(".subckt PLL_COMPACT " + " ".join(nets))
    for key, (f, n) in refs.items():
        ports = subckt_ports(f, n)
        conn = [MAP[key].get(p, f"{key}_{re.sub(r'[^A-Za-z0-9_]', '_', p)}") for p in ports]
        lines.append(f"X{key} " + " ".join(conn) + f" {n}")
    lines.append(".ends PLL_COMPACT")
    return "\n".join(lines) + "\n", nets


def layout():
    ly = db.Layout(); ly.read(os.path.join(HERE, "PLL_COMPACT.gds"))
    top = ly.cell("PLL_COMPACT")
    top.flatten(True)
    for li in ly.layer_indexes():
        if ly.get_info(li).datatype == 10:
            top.shapes(li).clear()
    land = json.load(open(os.path.join(HERE, "pins.json")))["land"]
    done = set(l[0] for l in TOP_LABELS)
    labels = list(TOP_LABELS)
    for net, blk, x, y in land:
        if net not in done:
            labels.append((net, (53, 10), x, y))
            done.add(net)
    for net, (l, d), x, y in labels:
        top.shapes(ly.layer(l, d)).insert(db.Text(net, db.Trans(round(x * 1000), round(y * 1000))))
    ly.cleanup()
    f = os.path.join(OUT, "PLL_COMPACT_flat.gds")
    ly.write(f)
    return f


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    refs = macro_refs()
    ref, nets = reference(refs)
    open(os.path.join(OUT, "PLL_COMPACT_ref.spice"), "w").write(ref)
    f = layout()
    n = sh(f"bash {HERE}/ext.sh {f} PLL_COMPACT {OUT}")
    print(f"layout: {n.strip()} devices")
    setup = "/foss/pdks/gf180mcuD/libs.tech/netgen/gf180mcuD_setup.tcl"
    sh(f"cd {OUT} && netgen -batch lvs 'PLL_COMPACT.spice PLL_COMPACT' 'PLL_COMPACT_ref.spice PLL_COMPACT' {setup} lvs.report > netgen.log 2>&1")
    print(sh(f"grep -E 'Final result|Circuits match|do not match|Netlists match|Number of devices|Number of nets' {OUT}/lvs.report | tail -6"))
