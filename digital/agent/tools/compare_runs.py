"""Put several runs side by side.

    python tools/compare_runs.py /tmp/classical /tmp/agent [more work dirs ...]
    python tools/compare_runs.py --md  ...        # the same as a Markdown table
    python tools/compare_runs.py --weights 1,1,1 ...   # what if the priorities were these

Reads report.json and tree.json from each work directory. Useful for
comparing two versions of the agent.

--weights T,P,A adds a column: the score each run's answer would get under
those weights for timing, power and area. It re-scores the answer the run
already chose. It does not say what the run would have found had it been
searching under those weights, which could be a different layout.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from pd import names                           # noqa: E402
from pd.ledger import TERMS, parse_weights      # noqa: E402


def rescore(s: dict, weights: dict) -> float | None:
    """The answer's score under other weights, from the ratios in its report."""
    if s["zeroed_because"]:
        return 0.0
    out = 1.0
    for term, label in TERMS.items():
        ratio = (s.get("vs_baseline") or {}).get(label)
        if not weights[term]:
            continue
        if not ratio:
            return None
        out *= ratio ** -weights[term]
    return round(out, 5)


def load(work: Path, weights: dict | None = None) -> dict | None:
    rp, tp = work / "report.json", work / "tree.json"
    if not rp.exists():
        return None
    rep = names.load_report(rp)                 # a run saved under the old agent names too
    tree = json.loads(tp.read_text()) if tp.exists() else {"order": [], "nodes": {}}
    by_stage: dict[str, list[float]] = {}
    for nid in tree["order"]:
        n = tree["nodes"][nid]
        if n["ok"] and n["stage"]:
            by_stage.setdefault(n["stage"], []).append(n["seconds"])
    inside = (tree["nodes"].get("n0") or {}).get("stage_seconds") or {}
    s, c, q = rep["score"], rep["cost"], rep["search"]
    root = tree["nodes"].get("n0", {})
    made = [a for a in rep.get("evaluations", []) if "seconds" in a]
    good = [a for a in made if str(a.get("outcome", "")).startswith(("passed", "accepted"))]
    b = q["branches_by_stage"]
    vs = s.get("vs_baseline") or {}
    return {
        "what_if": None if weights is None else rescore(s, weights),
        "weights": "/".join(f"{v:g}" for v in (s.get("weights") or {}).values()) or "timing only",
        "vs": " / ".join("-" if vs.get(k) is None else f"{vs[k]:.3f}" for k in TERMS.values()),
        "branches": "/".join(str(b.get(k, 0)) for k in ("FP", "PL", "CTS", "GR")),
        "evaluations": f"{len(good)} of {len(made)}",
        "name": work.name,
        "method": rep.get("method", "?"),
        "score": s["score"],
        "ecp": f"{s['baseline_ecp_ns']} -> {s['final_ecp_ns']}",
        "slack": s.get("final_setup_slack_ns"),
        "hold": s.get("final_hold_slack_ns"),
        "final": rep["final_node"] + (" (fell back)" if rep.get("fell_back_to_baseline") else ""),
        "early": q.get("evaluations_during_search", "-"),
        "runs": f"{c['flow_runs']}/{c['flow_run_budget']}",
        "failed": q["failed"],
        "by_stage": q["branches_by_stage"],
        "flow_min": c["flow_minutes"],
        "wall_min": c["wall_minutes"],
        "usd": c["usd"],
        "baseline_s": root.get("seconds"),
        "baseline_parts": inside,
        "cached": c.get("baseline_from_cache", False),
        "stage_s": {k: round(statistics.mean(v), 1) for k, v in by_stage.items()},
        "zeroed": "; ".join(s["zeroed_because"]),
        "slips": (rep.get("stage_agent_fallbacks", 0), rep.get("navigator_corrections", 0)),
    }


COLS = [("name", "run"), ("method", "method"), ("score", "score"), ("weights", "weights t/p/a"),
        ("vs", "ECP / power / cell area vs baseline"), ("ecp", "ECP ns (signoff)"),
        ("slack", "setup slack"), ("hold", "hold slack"), ("final", "answer"),
        ("branches", "branches FP/PL/CTS/GR"), ("early", "evaluations in search"),
        ("evaluations", "evaluations passed"),
        ("runs", "flow runs"), ("failed", "failed"), ("flow_min", "flow min"), ("usd", "$")]


def main(argv: list[str]) -> None:
    md = "--md" in argv
    weights = None
    if "--weights" in argv:
        i = argv.index("--weights")
        weights = parse_weights(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    rows = [r for r in (load(Path(a), weights) for a in argv if not a.startswith("--")) if r]
    if not rows:
        raise SystemExit("no report.json found in the given directories")
    cols = list(COLS)
    if weights is not None:
        cols.insert(3, ("what_if", "score at " + "/".join(f"{v:g}" for v in weights.values())))
    table = [[h for _, h in cols]] + [[str(r[k]) for k, _ in cols] for r in rows]
    if md:
        print("| " + " | ".join(table[0]) + " |")
        print("|" + "|".join(" --- " for _ in cols) + "|")
        for t in table[1:]:
            print("| " + " | ".join(t) + " |")
    else:
        w = [max(len(t[i]) for t in table) for i in range(len(cols))]
        for j, t in enumerate(table):
            print("  " + "  ".join(c.ljust(w[i]) for i, c in enumerate(t)))
            if j == 0:
                print("  " + "  ".join("-" * x for x in w))
    print()
    for r in rows:
        extra = f"  {r['name']}: branches {r['by_stage']}, mean seconds per branch {r['stage_s']}, " \
                f"baseline {r['baseline_s']:.0f}s" if r["baseline_s"] else f"  {r['name']}"
        if r["cached"]:
            extra += " (remembered, not re-run)"
        if r["baseline_parts"]:
            extra += f"\n      where the baseline's time went: {r['baseline_parts']}"
        if r["zeroed"]:
            extra += f"\n      zeroed because: {r['zeroed']}"
        if any(r["slips"]):
            extra += f"\n      agent slips: {r['slips'][0]} stage-agent fallbacks, {r['slips'][1]} navigator corrections"
        print(extra)


if __name__ == "__main__":
    main(sys.argv[1:])
