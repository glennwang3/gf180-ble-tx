"""Collect layout + power figures of power_exp variants into results.json / a table.

    python3 power_exp/collect.py v0:run_w300g v1:run_w300g ...
"""
import json, re, sys
from pathlib import Path
H = Path(__file__).resolve().parent
CORNERS = [f"{rc}_{p}" for p in ("tt_025C_3v30", "ss_125C_3v00", "ff_n40C_3v60")
           for rc in ("nom", "min", "max")]


def total(f):
    for line in f.read_text().splitlines():
        if line.startswith("Total"):
            return float(line.split()[4])


def window_us(f):
    m = re.search(r"WINDOW_NS \S+ \S+ (\S+)", f.read_text())
    return float(m[1]) / 1000 if m else None


def one(v, run):
    fin = H / v / run / "baseline_signoff_final"
    m = json.loads((fin / "metrics.json").read_text())
    nl = (fin / "nl" / "ble_tx_uart.nl.v").read_text()
    r = {"variant": v, "run": run,
         "drc_magic": m.get("magic__drc_error__count"), "drc_route": m.get("route__drc_errors"),
         "lvs": m.get("design__lvs_error__count"), "antenna": m.get("antenna__violating__nets"),
         "xor": m.get("design__xor_difference__count"),
         "die": m.get("design__die__bbox"), "die_area": m.get("design__die__area"),
         "stdcell_area": m.get("design__instance__area__stdcell"),
         "util": m.get("design__instance__utilization"),
         "cells": m.get("design__instance__count__stdcell", m.get("design__instance__count")),
         "icg": m.get("design__instance__count__class:clock_gate_cell"),
         "icg_in_netlist": len(re.findall(r"__icgtp_\d+\s", nl)),
         "seq_cells": m.get("design__instance__count__class:sequential_cell"),
         "clock_buffers": m.get("design__instance__count__class:clock_buffer"),
         "setup_ws": {c: m.get(f"timing__setup__ws__corner:{c}") for c in CORNERS},
         "hold_ws": {c: m.get(f"timing__hold__ws__corner:{c}") for c in CORNERS},
         "slew_viol": {c: m.get(f"design__max_slew_violation__count__corner:{c}") for c in CORNERS},
         "cap_viol": {c: m.get(f"design__max_cap_violation__count__corner:{c}") for c in CORNERS},
         "fanout_viol": m.get("design__max_fanout_violation__count"),
         "ir_drop_worst_V": m.get("ir__drop__worst"),
         }
    up = fin / "upsized_drivers.txt"
    r["upsized_drivers"] = len([l for l in up.read_text().splitlines() if l.strip()]) if up.exists() else 0
    p = H / v / f"power_{run}"
    if p.is_dir():
        r["power_mW"] = {k: total(p / f"{k}.txt") * 1e3 for k in ("default", "tx", "idle", "load")}
        r["window_us"] = {k: window_us(p / f"sim_{k}.txt") for k in ("tx", "idle", "load")}
        P, t = r["power_mW"], r["window_us"]
        for T_ms in (100, 20):
            T = T_ms * 1000.0
            e = P["tx"] * t["tx"] + P["load"] * t["load"] + P["idle"] * (T - t["tx"] - t["load"])
            r[f"avg_uW_{T_ms}ms"] = e / T * 1e3
            e0 = P["tx"] * t["tx"] + P["idle"] * (T - t["tx"])
            r[f"avg_noload_uW_{T_ms}ms"] = e0 / T * 1e3
    return r


if __name__ == "__main__":
    rows = [one(*a.split(":")) for a in sys.argv[1:]]
    (H / "results.json").write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(json.dumps(r))
