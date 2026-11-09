"""Search without a language model. Optional: not part of the main comparison.

An agent is measured against its baseline, LibreLane's flow untouched. This
file shows what a search without judgement finds on the same budget, for anyone
who wants that reference too. Two policies, both starting from that baseline:

  flat     every run branches from the baseline at placement with a fresh random
           setting for every knob. This is ordinary random search: it ignores
           the stage structure and pays for placement every time.

  staged   a hand-written heuristic that does use the structure. Spend part of
           the budget on placement branches, then branch the best of those at
           the clock tree, then branch the best of those at global routing.

    python -m pd.classical --policy staged --runs 20 --work /tmp/classical

Both policies rank on the same estimated score the agent is shown, with the
same weights, and both follow one rule about trusting it: the first node of a
kind of layout nobody has signed off is signed off straight away, because until
then its estimate cannot be compared with anything (pd/tree.py). What keeps
them honest about the constraints is the candidate screen: --hold-floor and
--power-ceiling say which nodes may be signed off at the end, on in-loop
estimates, and --spare keeps flow runs back for them so that more than one of
them can be: one run fewer than there are candidates waiting, and never more
than --spare. To compare it with an agent, give it the same three numbers the
agent uses.
"""
from __future__ import annotations

import argparse
import functools
import json
import random
from pathlib import Path

from . import stages as S
from .episode import Episode
from .ledger import TOLERANCE, WEIGHTS, parse_weights

HERE = Path(__file__).resolve().parent.parent
say = functools.partial(print, flush=True)     # progress should not sit in a buffer


def _all_knobs(rng: random.Random, bounds) -> dict:
    out = {}
    for name in S.NAMES:
        out.update(S.sample(name, rng, bounds))
    return out


def _room(ep: Episode, spare: int) -> int:
    """Flow runs the search may still spend. A run kept back for the end is
    only kept if a candidate is waiting for it: one of them has the run the
    budget always holds, each of the others needs one of these, up to `spare`."""
    return ep.ledger.search_runs_left - min(spare, max(0, len(ep.waiting()) - 1))


def _meet(ep: Episode, n, log, spare: int) -> None:
    """Evaluate a node at once if it is the first of its kind. One run, and
    every estimate of that kind is corrected from then on."""
    t = ep.tree
    if n.ok and not t.checked(n.id) and n.id in t.can_evaluate() and _room(ep, spare) > 0:
        log(ep.check_line(ep.sign_off(n.id)))


def flat(ep: Episode, rng: random.Random, log=say, spare: int = 0) -> None:
    root = ep.tree.order[0]
    while not ep.hard_stop() and _room(ep, spare) > 0:
        n = ep.branch(root, "PL", _all_knobs(rng, ep.tree.bounds()), note="flat random")
        log(_line(ep, n))
        _meet(ep, n, log, spare)


def staged(ep: Episode, rng: random.Random, log=say, spare: int = 0,
           split=(0.4, 0.35, 0.25)) -> None:
    """Placement first, then clock tree off the best placement, then routing.
    The shares are of every run the search has; what is kept back for evaluations
    comes out of the last stage, which is worth least."""
    total = max(1, ep.ledger.search_runs_left)
    share = [max(1, round(total * f)) for f in split]
    share[0] = max(1, total - share[1] - share[2])
    anchor = ep.tree.order[0]
    for stage, count in zip(S.NAMES, share):
        made = []
        for _ in range(count):
            if _room(ep, spare) <= 0:
                break
            if (anchor, stage) not in ep.options():
                break
            n = ep.branch(anchor, stage, S.sample(stage, rng, ep.tree.bounds()),
                          note=f"staged random at {stage}")
            made.append(n.id)
            log(_line(ep, n))
            _meet(ep, n, log, spare)
        ok = [i for i in made + [anchor] if i in ep.tree.valid()]
        if ok:
            anchor = max(ok, key=ep.tree.est_score)


def _line(ep: Episode, n) -> str:
    return ep.line(n)


POLICIES = {"flat": flat, "staged": staged}


def run(design, work, clock_ns, runs, policy="staged", seed=1, log=say,
        hold_floor: float = 0.0, power_ceiling: float | None = TOLERANCE,
        spare: int = 0, weights: dict | None = None) -> dict:
    log(f"  weights  {weights or WEIGHTS}")
    log(f"  baseline …")
    ep = Episode.start(design, work, clock_ns, max_runs=runs, max_usd=None,
                       hold_floor=hold_floor, power_ceiling=power_ceiling, weights=weights)
    root = ep.tree.nodes[ep.tree.order[0]]
    log(ep.line(root, "(remembered from an earlier run)" if ep.baseline_from_cache else ""))
    POLICIES[policy](ep, random.Random(seed), log, spare)
    log("  signoff …")
    before = len(ep.checks)
    report = ep.finish({"method": f"classical/{policy}", "seed": seed, "spare_runs": spare})
    for rec in ep.checks[before:]:
        log(ep.check_line(rec))
    return report


def cli():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--design", default=str(HERE / "designs" / "ble_tx"))
    p.add_argument("--work", default="/tmp/llm_pd_classical")
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--policy", choices=sorted(POLICIES), default="staged")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--hold-floor", type=float, default=0.0,
                   help="estimated hold slack (ns) a node needs to be a candidate")
    p.add_argument("--power-ceiling", type=float, default=TOLERANCE,
                   help="estimated power over baseline above which a node is not a candidate; "
                        "0 turns the check off")
    p.add_argument("--spare", type=int, default=0,
                   help="flow runs to keep back for candidates waiting to be signed off at "
                        "the end, so that more than one can be; fewer are kept when fewer "
                        "are waiting")
    p.add_argument("--weights", default=None, metavar="T,P,A",
                   help="score weights for timing, power and area, to try a different "
                        "priority; the default is WEIGHTS in pd/ledger.py")
    a = p.parse_args()
    clock = read_clock(a.design)        # the flow reads the same file; never override it here
    rep = run(a.design, a.work, clock, a.runs, a.policy, a.seed,
              hold_floor=a.hold_floor, power_ceiling=a.power_ceiling or None, spare=a.spare,
              weights=parse_weights(a.weights))
    print(json.dumps({k: rep[k] for k in ("score", "final_node", "final_settings",
                                          "evaluations", "search", "cost")}, indent=1))
    from .episode import results_table
    print("  every node, as estimated and as signed off; x base is the ratio to the baseline")
    print(results_table(rep))


def read_clock(design_dir) -> float:
    """CLOCK_PERIOD from a design's config.yaml, without importing a YAML parser."""
    for line in (Path(design_dir) / "config.yaml").read_text().splitlines():
        if line.strip().startswith("CLOCK_PERIOD:"):
            return float(line.split(":", 1)[1].split("#")[0].strip())
    raise ValueError(f"no CLOCK_PERIOD in {design_dir}/config.yaml")


if __name__ == "__main__":
    cli()
