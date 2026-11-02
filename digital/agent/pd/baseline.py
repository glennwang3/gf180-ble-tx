"""Run LibreLane's flow on a design with no setting touched, and print the result.

    python -m pd.baseline                              # ble_tx
    python -m pd.baseline --design designs/spm

This is the baseline every search is measured against: the root n0 of the
search tree, which scores exactly 1.0. It is run once per design and
remembered under ~/.cache/llm_pd, so every search started afterwards begins at
once. No language model is called and nothing is spent.

The table puts the numbers a search reads after global routing, the estimates,
next to the numbers signoff finds for the same layout. The difference between
the two columns is the reason the search has an evaluate move.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import stages as S
from .classical import read_clock
from .episode import Episode
from .ledger import gate

HERE = Path(__file__).resolve().parent.parent


def table(ep: Episode) -> str:
    t = ep.tree
    root = t.order[0]
    est, real = t.nodes[root].metrics, t.nodes[root].signoff_metrics

    def f(v, spec, unit=""):
        return "-" if v is None else format(v, spec) + unit

    rows = [
        ("effective clock period", S.effective_clock_period(est, t.clock),
         S.effective_clock_period(real, t.clock), "8.4f", " ns"),
        ("worst setup slack, tt", S.setup_ws(est), S.setup_ws(real), "+8.4f", " ns"),
        ("worst hold slack, tt", S.hold_ws(est), S.hold_ws(real), "+8.4f", " ns"),
        ("total power", est.get(S.POWER_KEY), real.get(S.POWER_KEY), "8.4f", " W"),
        ("standard-cell area", est.get(S.AREA_KEY), real.get(S.AREA_KEY), "8.0f", " um2"),
    ]
    out = [f"  {'':24s}{'after global routing':>22s}{'at signoff':>16s}"]
    for name, a, b, spec, unit in rows:
        out.append(f"  {name:24s}{f(a, spec, unit):>22s}{f(b, spec, unit):>16s}")
    checks = " / ".join(f(real.get(k), ".0f") for k in
                        ("magic__drc_error__count", "design__lvs_error__count",
                         "antenna__violating__nets"))
    out.append(f"  {'DRC / LVS / antenna':24s}{'not checked':>22s}{checks:>16s}")
    problems = gate(real, real)
    out.append("  limits at signoff: " + ("all met" if not problems else "; ".join(problems))
               + "  (setup slack is not a limit: it enters the score)")
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--design", default=str(HERE / "designs" / "ble_tx"))
    p.add_argument("--work", default="runs/baseline",
                   help="where the run's tree.json and ledger.json are written")
    a = p.parse_args()

    clock = read_clock(a.design)
    print(f"  baseline of {Path(a.design).name} at a {clock:g} ns clock "
          f"(a few minutes the first time) ...", flush=True)
    ep = Episode.start(a.design, a.work, clock, max_runs=1, max_usd=None)
    root = ep.tree.nodes[ep.tree.order[0]]
    print(f"  {'remembered from an earlier run' if ep.baseline_from_cache else f'ran in {root.seconds:.0f} s'}")
    print(table(ep))
    (Path(a.work) / "baseline.json").write_text(json.dumps(
        {"design": Path(a.design).name, "clock_ns": clock,
         "after_global_routing": root.metrics, "at_signoff": root.signoff_metrics}, indent=1))


if __name__ == "__main__":
    main()
