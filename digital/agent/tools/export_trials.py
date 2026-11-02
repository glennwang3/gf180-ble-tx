"""Every trial of one or more searches, one row each, in the order the flow runs
were spent: the baseline, every branch and every signoff.

    python tools/export_trials.py WORK [WORK ...] -o trials.csv
    python tools/export_trials.py --backfill WORK     add the `results` table to an
                                                      older report.json that lacks it

Each row gives the settings that made the node, and its effective clock period,
setup and hold slack, power and cell area both as absolute values and as ratios to
the baseline: for a branch, as estimated after global routing and corrected only by
the evaluations made before it, so the row is what the search saw at that moment; for
a signoff, as signoff found. `score_est_at_end` is the same branch's estimate as
corrected by every signoff of the search.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pd import names              # noqa: E402  old agent names read as new
from pd.tree import Tree          # noqa: E402

FIELDS = ["ecp_ns", "ecp_vs_baseline", "setup_slack_ns", "hold_slack_ns", "power_w",
          "power_vs_baseline", "cell_area_um2", "area_vs_baseline"]


def rows(work: Path):
    rep = names.load_report(work / "report.json")
    tree = Tree.load(work / "tree.json")
    rec = {i: tree.record(i) for i in tree.order}
    checks = {a["after_flow_runs"]: a for a in rep.get("evaluations", []) if "seconds" in a}
    made_by, signed_at = timing(rep, tree)
    nodes = iter(tree.order)
    for k in range(1, rep["cost"]["flow_runs"] + 1):
        at_end, candidate = None, None
        if k in checks:
            a = checks[k]
            nid, move = a["node"], "evaluate (" + a["when"] + ")"
            r, block, est = rec[nid], rec[nid]["signoff"] or {}, a.get("estimate") or {}
            score = block.get("score")
            outcome = a["outcome"]
            believed = est.get("score_est")
        else:
            nid = next(nodes, None)
            if nid is None:
                break
            r = rec[nid]
            move = "baseline" if r["made_by_branching_at"] == "baseline" else "branch " + r["made_by_branching_at"]
            then = as_it_stood(tree, k, made_by, signed_at)
            block = then.record(nid)["estimate"] or {}
            candidate = then.why_not(nid) is None if r["estimate"] else None
            score = block.get("score_est")
            at_end = (r["estimate"] or {}).get("score_est")
            outcome = "ok" if r["ok"] else "failed: " + (tree.nodes[nid].error or "")[:120]
            believed = None
        yield {"run": work.name, "flow_run": k, "move": move, "node": nid, "from": r["from"],
               "kind": r["kind"], "settings": json.dumps(r["settings"], sort_keys=True),
               "score": score, "score_est_at_end": at_end, "estimate_before_signoff": believed,
               **{f: block.get(f) for f in FIELDS}, "candidate_then": candidate,
               "outcome": outcome,
               "answer": nid == rep.get("final_node") and move.startswith("evaluate")}


def as_it_stood(tree: Tree, k: int, made_by: dict, signed_at: dict) -> Tree:
    """The tree after flow run k: only the nodes made by then, only the evaluations
    made by then, so every estimate carries the corrections it had at that moment."""
    then = copy.deepcopy(tree)
    then.order = [i for i in then.order if made_by.get(i, 0) <= k]
    for i, n in then.nodes.items():
        if i != tree.order[0] and signed_at.get(i, 10 ** 9) > k:
            n.signoff_metrics = {}
    return then


def believed(work: Path) -> list[float]:
    """After each flow run, the best estimated score among the candidates of the
    tree as it stood then: what the search believed it had."""
    rep = names.load_report(work / "report.json")
    tree = Tree.load(work / "tree.json")
    made_by, signed_at = timing(rep, tree)
    out = []
    for k in range(1, rep["cost"]["flow_runs"] + 1):
        then = as_it_stood(tree, k, made_by, signed_at)
        s = [then.est_score(i) for i in then.valid()]
        out.append(max([1.0] + [x for x in s if x is not None]))
    return out


def timing(rep: dict, tree: Tree) -> tuple[dict, dict]:
    """The flow run at which each node was made, and at which each was signed off."""
    checks = {a["after_flow_runs"]: a for a in rep.get("evaluations", []) if "seconds" in a}
    made_by, nodes = {}, iter(tree.order)
    for k in range(1, rep["cost"]["flow_runs"] + 1):
        if k not in checks:
            nid = next(nodes, None)
            if nid is None:
                break
            made_by[nid] = k
    return made_by, {a["node"]: a["after_flow_runs"] for a in checks.values()}


def backfill(work: Path) -> None:
    rep = names.load_report(work / "report.json")
    tree = Tree.load(work / "tree.json")
    rep["results"] = [tree.record(i) for i in tree.order]
    (work / "report.json").write_text(json.dumps(rep, indent=1))
    print(f"added results for {len(rep['results'])} nodes to {work / 'report.json'}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("work", nargs="+")
    p.add_argument("-o", "--out", default="trials.csv")
    p.add_argument("--backfill", action="store_true")
    a = p.parse_args()
    if a.backfill:
        for w in a.work:
            backfill(Path(w))
        return
    out = [row for w in a.work for row in rows(Path(w))]
    with open(a.out, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(out[0]))
        wr.writeheader()
        wr.writerows(out)
    print(f"wrote {len(out)} rows to {a.out}")


if __name__ == "__main__":
    main()
