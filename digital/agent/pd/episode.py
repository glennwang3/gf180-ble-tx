"""One optimisation run, as an environment an agent acts on.

An agent, of whatever kind, only ever does five things:

    ep = Episode.start(design, work, clock_ns, max_runs, max_usd)   # runs the baseline
    ep.options()                          # which (node, stage) branches are possible
    ep.branch(node_id, stage, proposal)   # one flow run: a new node, with estimates
    ep.sign_off(node_id)                  # one flow run: evaluate an existing node, for real
    ep.finish()                           # evaluate what is still worth it, score the best

A branch is cheap information: it stops after global routing and what comes back
is an estimate. An evaluation takes one node through signoff (detailed routing,
DRC, LVS). It is the truth about that node, and it also corrects every estimate
of that node's kind (pd/tree.py). The answer is always a node that has been
evaluated.

Everything a prompt might want to show a model comes from the *_context
methods, so what each agent sees is decided in one place. The classical search
in pd/classical.py and the ADK graph in agents/ are both thin layers over this.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import names, runner, stages as S
from .ledger import FALLBACK_TO_BASELINE, MAX_SIGNOFFS, SETUP_FLOOR_NS, Ledger, score
from .runner import END, RunResult
from .tree import Node, Tree


@dataclass
class Episode:
    design_dir: Path
    work: Path
    clock_ns: float
    tree: Tree
    ledger: Ledger
    keep: int = 6                       # how many good nodes keep their snapshots
    freed_bytes: int = 0
    fallbacks: int = 0                  # times the stage agent failed to submit anything
    corrections: int = 0                # times the navigator named a move that does not exist
    baseline_from_cache: bool = False   # the untouched flow was not re-run this time
    checks: list = field(default_factory=list)      # every evaluation: what was believed, what was found
    started: float = field(default_factory=time.monotonic)

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    def start(cls, design_dir, work, clock_ns: float, max_runs: int = 20,
              max_usd: float = 2.0, ledger: Ledger | None = None,
              hold_floor: float = 0.0, power_ceiling: float | None = None,
              weights: dict | None = None, **kw) -> "Episode":
        """Run the untouched flow and make it the root of the search tree.

        `hold_floor` and `power_ceiling` decide which nodes count as candidates
        for the final answer, on in-loop estimates; see Tree.why_not. `weights`
        are the priorities of the score; None takes ledger.WEIGHTS."""
        design_dir, work = Path(design_dir).resolve(), Path(work).resolve()
        work.mkdir(parents=True, exist_ok=True)
        ledger = ledger or Ledger(max_flow_runs=max_runs, max_usd=max_usd)
        tree = Tree(clock_ns, hold_floor, power_ceiling, weights)
        ep = cls(design_dir, work, clock_ns, tree, ledger, **kw)

        store = work / "states" / tree.next_id()
        res = runner.baseline_cached(design_dir, work / "run" / "baseline", store)
        ledger.charge_run(res.seconds)      # charged whether or not it was re-run
        tree.add(None, None, {}, res, store="" if res.shared else str(store),
                 note="untouched flow")
        ep.baseline_from_cache = res.from_cache
        ep.freed_bytes += res.freed_bytes
        ep.save()
        if not res.ok:
            raise RuntimeError(f"the baseline flow failed: {res.error}\n{res.log_tail}")
        return ep

    def save(self) -> None:
        self.tree.save(self.work / "tree.json")
        self.ledger.save(self.work / "ledger.json")

    # ------------------------------------------------------------------ acting
    def options(self) -> list[tuple[str, str]]:
        return self.tree.branchable()

    def branch(self, node_id: str, stage: str, proposal: dict, note: str = "") -> Node:
        """Resume at `stage` from `node_id` with `proposal`. Costs one flow run
        unless the request is refused before anything is launched."""
        tree, led = self.tree, self.ledger
        new_id = tree.next_id()
        store = self.work / "states" / new_id
        parent = tree.nodes.get(node_id)

        if led.must_stop():
            res, params = RunResult(False, 0.0, error=f"rejected before running: {led.must_stop()}"), {}
        elif parent is None or (node_id, stage) not in tree.branchable():
            res = RunResult(False, 0.0, error=(
                f"rejected before running: cannot branch at {stage!r} from {node_id!r}; "
                f"legal choices are {tree.branchable()}"))
            params = dict(parent.params) if parent else {}
        else:
            params = S.blend(parent.params, proposal or {}, stage)
            res = runner.fork(self.design_dir, parent.stage_states[stage], stage, params,
                              self.work / "run" / new_id, store, tree.bounds())

        if res.seconds > 0:
            led.charge_run(res.seconds)
        else:
            led.rejected += 1
        node = tree.add(node_id if parent else None, stage, params, res,
                        store=str(store), note=note)
        self.freed_bytes += res.freed_bytes + tree.prune(self.keep)
        self.save()
        return node

    def sign_off(self, node_id: str, when: str = "search") -> dict:
        """Evaluate one existing node: take it through signoff, that is detailed
        routing, DRC and LVS. Costs one flow run unless it is refused before
        anything is launched.

        What comes back is the truth about that node. It is also evidence about
        every other node of its kind: from here on the tree corrects their
        estimates by what this one showed. `when` is "search" for an evaluation
        the search asked for and "end" for one made by finish()."""
        tree, led = self.tree, self.ledger
        n = tree.nodes.get(node_id)
        if n is None or not n.ok:
            refuse = f"{node_id!r} is not a finished node"
        elif tree.signed_off(node_id):
            refuse = f"{node_id} has already been evaluated"
        elif node_id not in tree.can_evaluate():
            refuse = f"{node_id} can no longer be evaluated; the nodes that can are {tree.can_evaluate()}"
        elif when == "search" and led.must_stop():
            refuse = led.must_stop()
        elif led.flow_runs >= led.max_flow_runs:
            refuse = "no flow run left"
        else:
            refuse = None
        if refuse:
            led.rejected += 1
            return {"node": node_id, "when": when, "outcome": f"refused before running: {refuse}"}

        before, known = tree.row(node_id), tree.checked(node_id)
        res = runner.signoff(self.design_dir, n.stage_states[END], n.params,
                             self.work / "signoff" / node_id)
        led.charge_run(res.seconds)
        rec = {"node": node_id, "when": when, "after_flow_runs": led.flow_runs,
               "seconds": round(res.seconds, 1), "kind": tree.kind(node_id),
               "kind_already_checked": known, "estimate": before}
        if not res.ok:
            n.error, n.log_tail = res.error, res.log_tail       # it will not be offered again
            rec.update(outcome="signoff flow failed", error=res.error[:300])
        else:
            n.signoff_metrics = dict(res.signoff_metrics)
            rec["signoff"] = tree.real_row(node_id)
            problems = tree.problems(node_id)
            if problems:
                rec.update(outcome="failed the limits", problems=problems)
            elif (tree.real_score(node_id) or 0.0) <= 1.0:
                rec.update(outcome="signed off clean, but scores no better than the baseline")
            else:
                rec.update(outcome="passed")
        self.freed_bytes += res.freed_bytes
        self.checks.append(rec)
        self.save()
        return rec

    def line(self, n: Node, extra: str = "") -> str:
        """One line describing a run, for the terminal: what it was, what it
        reached, and whether it can be the final answer."""
        t = self.tree
        e, h, p, a = t.ecp(n.id), t.hold(n.id), t.power_ratio(n.id), t.area_ratio(n.id)
        est, inc = t.est_score(n.id), t.incumbent()
        what = f"{n.stage:3s} from {str(n.parent):4s}" if n.stage else f"{'baseline':13s}"
        out = f"  {n.id:4s} {'ok  ' if n.ok else 'FAIL'} {what} {n.seconds:6.1f}s  "
        if e is None or est is None:
            return out + f"no result   {n.error[:110]}"
        m, e0 = n.metrics, t.ecp(t.order[0])
        watts, um2 = m.get(S.POWER_KEY), m.get(S.AREA_KEY)
        out += (f"score~{est:6.4f}  ECP {e:7.4f} ns"
                + (f" ({t.vs_baseline(n.id)['timing']:.3f}x)" if e0 else "")
                + f"  hold {'-' if h is None else format(h, '.3f')}"
                f"  power {'-' if watts is None else format(watts, '.4f')} W"
                f" ({'-' if p is None else format(p, '.3f')}x)"
                f"  area {'-' if um2 is None else format(um2, '.0f')} um2"
                f" ({'-' if a is None else format(a, '.3f')}x)")
        if not t.checked(n.id):
            out += "   unchecked kind"
        out += "   not a candidate" if t.why_not(n.id) else ""
        if inc is not None and n.stage:
            out += f"   best {t.est_score(inc):.4f} ({inc})"
        return out + (f"   {extra}" if extra else "")

    def check_line(self, rec: dict) -> str:
        """One line describing an evaluation, for the terminal."""
        out = f"  {rec['node']:4s} evaluate {'at the end' if rec['when'] == 'end' else '':10s}"
        if "seconds" not in rec:
            return out + f"         {rec['outcome'][:120]}"
        out += f"{rec['seconds']:6.1f}s  "
        if "signoff" in rec:
            out += (f"score {rec['signoff']['score']:6.4f}  (estimate was "
                    f"{rec['estimate']['score_est']:.4f}"
                    + ("" if rec["kind_already_checked"] else ", of an unchecked kind") + ")  ")
        return out + rec["outcome"]

    # ------------------------------------------------------------------ views
    def limits(self) -> dict:
        """The two thresholds a node's estimates are held to, for showing to an agent.

        The limits that apply at signoff are deliberately not in here. An earlier
        version showed both, and the navigator then held every estimate to the
        signoff limit instead of to its own threshold, however the prompt was
        worded. An agent reasons with whatever number it is shown; this one it
        does not need.
        """
        t = self.tree
        return {
            "apply_to": "the estimates shown for each node",
            "hold_slack_floor_ns": t.hold_floor,
            "power_ceiling_vs_baseline": t.power_ceiling,
            "setup_slack_floor_ns": SETUP_FLOOR_NS,
            "setup_floor_applies_at": [S.FOM_CORNER, "the worst corner"],
            "electrical_violations": "none: no max-slew or max-capacitance violation at "
                                     f"{S.FOM_CORNER} or the slow corner {S.SLOW_CORNER}. "
                                     "The baseline has some at the slow corner",
            "clock_period_ns": t.clock,
        }

    def objective(self) -> dict:
        """What the search is trying to raise, for showing to an agent. The
        weights are read from the run, never written into a prompt: change them
        and an agent that reads this follows."""
        return {
            "maximise": "score = (baseline ECP / ECP)^timing * (baseline power / power)^power"
                        " * (baseline cell area / cell area)^area",
            "weights": self.tree.weights,
            "timing": "pass/fail only: the clock is fixed at 8 MHz; a result whose setup"
                      " slack is below setup_slack_floor_ns in limits can never be the answer",
            "score_est": "this formula on a node's estimates, corrected by what signoff has shown"
                         " for nodes of its kind. 1.0 is the baseline",
        }

    def navigator_context(self) -> dict:
        """For the navigator, the agent that decides where to spend the next run."""
        return {
            "objective": self.objective(),
            "search_so_far": self.tree.summary(),
            "limits": self.limits(),
            "budget": self.budget(),
            "legal_branches": [f"{n}:{s}" for n, s in self.options()],
            "stages": {s.name: s.note for s in S.STAGES},
        }

    def stage_context(self, node_id: str, stage: str, hint: str = "") -> dict:
        """For the agent that picks settings for one stage. Nothing about other stages."""
        tree = self.tree
        n = tree.nodes[node_id]
        bounds = tree.bounds()
        keys = S.BY_NAME[stage].params
        m = n.metrics
        return {
            "stage": stage,
            "resuming_from_node": node_id,
            "hint_from_navigator": hint,
            "objective": self.objective(),
            "knobs": S.cheat_sheet(bounds, only=stage),
            "values_on_this_path": {k: n.params.get(k, "flow default") for k in keys},
            "already_tried_at_this_stage": tree.tried(stage),
            "limits": self.limits(),
            "numbers_at_this_node": {
                **tree.row(node_id),
                "clock_period_target_ns": self.clock_ns,
                "global_route_wirelength_um": m.get("global_route__wirelength"),
                "timing_repair_buffers": m.get("design__instance__count__class:timing_repair_buffer"),
                "clock_buffers": m.get("design__instance__count__class:clock_buffer"),
                "clock_skew_ns": m.get(f"clock__skew__worst_setup__corner:{S.FOM_CORNER}"),
                "total_power_w": m.get("power__total"),
                "utilisation": m.get("design__instance__utilization"),
                "max_slew_violations_tt": m.get(f"design__max_slew_violation__count__corner:{S.FOM_CORNER}"),
                "max_cap_violations_tt": m.get(f"design__max_cap_violation__count__corner:{S.FOM_CORNER}"),
                "max_slew_violations_slow": m.get(f"design__max_slew_violation__count__corner:{S.SLOW_CORNER}"),
                "max_cap_violations_slow": m.get(f"design__max_cap_violation__count__corner:{S.SLOW_CORNER}"),
            },
            "log_of_this_stage_on_this_path": tree.digest_for(node_id, stage),
        }

    def best_evaluated(self) -> tuple[str, float]:
        """The node that would be the answer if the search stopped now, and its
        score: the best signed-off node that passes the limits. The baseline
        is one, so there always is an answer."""
        tree = self.tree
        root = tree.order[0]
        best, top = root, 1.0
        for i in tree.order:
            real = tree.real_score(i) if tree.nodes[i].ok and tree.signed_off(i) else None
            if i != root and real is not None and real > top and not tree.problems(i):
                best, top = i, real
        return best, top

    def waiting(self) -> list[str]:
        """Candidates not yet evaluated whose estimate puts them above the best
        node that has been: what the end of the search would spend its runs on,
        best first."""
        _, target = self.best_evaluated()
        return [i for i in self.tree.ranked()
                if not self.tree.signed_off(i) and self.tree.est_score(i) > target]

    def budget(self) -> dict:
        """The budget as an agent or a stopping rule is shown it, with how many
        candidates are waiting for an evaluation: a run kept back for the end is
        only worth keeping if there is something for it to evaluate."""
        return names.Budget(self.ledger.view(),
                            candidates_waiting_for_evaluation=len(self.waiting()))

    def stop_context(self) -> dict:
        """For the stop agent, which decides whether to stop. Numbers only, no logs."""
        return {
            "budget": self.budget(),
            "best_score_est_after_each_run": self.tree.history(),
            "best_evaluated_score": round(self.best_evaluated()[1], 4),
            "nodes_evaluated": sum(1 for i in self.tree.order if self.tree.signed_off(i)),
            "runs_that_failed": sum(1 for i in self.tree.order if not self.tree.nodes[i].ok),
            "proposals_refused": self.ledger.rejected,
        }

    # The names these two had before the navigator and the stop agent were
    # renamed. A views.py written against the old names still calls them.
    def judge_context(self) -> dict:
        return self.navigator_context()

    def critic_context(self) -> dict:
        return self.stop_context()

    best_signed_off = best_evaluated        # its name before the move was called evaluate

    def failure_context(self, node: Node) -> dict:
        """For the agent that explains a failed run."""
        return {
            "stage_branched_at": node.stage,
            "configuration": node.params,
            "error": node.error,
            "end_of_log": node.log_tail,
        }

    # ------------------------------------------------------------------ hard limits
    def hard_stop(self) -> str | None:
        """A reason the search must end now, or None. These override any agent
        and any stopping rule; whether to stop earlier is the caller's decision."""
        hard = self.ledger.must_stop()
        if hard:
            return hard
        if self.ledger.rejected > 2 * self.ledger.max_flow_runs:
            return "too many refused proposals"
        if not self.options():
            return "no branch point left to resume from"
        return None

    # ------------------------------------------------------------------ the end
    def finish(self, extra: dict | None = None) -> dict:
        """Evaluate what is still worth evaluating, score the best, write the report.

        The answer is the signed-off node with the highest score that passes the
        limits; the baseline is one, so there always is an answer. Before it is
        picked, the runs still in hand go to candidates that have not been
        signed off and whose estimate says they would beat it: best estimate
        first, one flow run each, at most MAX_SIGNOFFS. The estimate decides
        who gets tried, never who wins.
        """
        tree, led = self.tree, self.ledger
        root = tree.order[0]
        _, target = self.best_evaluated()

        def look(nid):                  # two nodes with the same numbers are one node
            return tuple(None if v is None else round(v, 3) for v in tree.row(nid).values())

        # A branch that changed nothing, or next to nothing, leaves a node with
        # its parent's numbers; signing both off spends a run to learn what is
        # already known. Three decimals: a global-routing branch moved power in
        # the fifth and was signed off beside its parent.
        seen = {look(i): i for i in tree.order if tree.nodes[i].ok and tree.signed_off(i)}
        queue = [(i, look(i)) for i in self.waiting()]
        made = 0
        for nid, same in queue:
            if nid not in tree.can_evaluate():
                self.checks.append({"node": nid, "when": "end",
                                    "outcome": "its post-global-route state is no longer stored"})
                continue
            if made >= MAX_SIGNOFFS:
                break
            if same in seen:
                self.checks.append({"node": nid, "when": "end",
                                    "outcome": f"skipped: same estimates as {seen[same]}"})
                continue
            if led.flow_runs >= led.max_flow_runs:
                self.checks.append({"node": nid, "when": "end",
                                    "outcome": "no flow run left to evaluate it"})
                break
            seen[same] = nid
            self.sign_off(nid, when="end")
            made += 1

        final_id, _ = self.best_evaluated()
        tried = [c["node"] for c in self.checks if "signoff" in c]
        if final_id == root and tried and not FALLBACK_TO_BASELINE:
            final_id = max(tried, key=lambda i: tree.real_score(i) or 0.0)
        fell_back = final_id == root and bool(tried or queue)
        for c in self.checks:
            if c.get("node") == final_id and c.get("outcome") == "passed":
                c["outcome"] = "passed — this is the answer"

        # Each signoff leaves its GDS, DEF and netlists behind, about a third of a
        # gigabyte, and the saved branch points are no use once the search is
        # over. Only the answer's layout is worth the disk. (The baseline's
        # branch points live in the cache and are never touched here.)
        for nid in {c["node"] for c in self.checks if "seconds" in c}:
            if nid != final_id:
                self.freed_bytes += runner.drop_snapshots(self.work / "signoff" / f"{nid}_final")
        if not os.environ.get("LLM_PD_KEEP_STATES"):
            for n in tree.nodes.values():
                if n.store:
                    self.freed_bytes += runner.drop_snapshots(n.store)
                    n.stage_states = {}

        result = score(tree.baseline(), tree.nodes[final_id].signoff_metrics, self.clock_ns, led,
                       tree.weights)
        kinds = tree.kinds()
        for k in kinds:
            fix = tree.correction(k["kind"])
            k["correction"] = None if fix is None else {t: round(v, 4) for t, v in fix.items()}
        report = {
            "work": str(self.work),
            "score": result,
            "final_node": final_id,
            "fell_back_to_baseline": fell_back,
            "final_settings": tree.nodes[final_id].params,
            "estimate_vs_signoff": {"estimate": tree.row(final_id),
                                    "signoff": tree.real_row(final_id)},
            "results": [tree.record(i) for i in tree.order],
            "evaluations": self.checks,
            "kinds": kinds,
            "candidate_screen": {"hold_floor_ns": tree.hold_floor,
                                 "power_ceiling": tree.power_ceiling},
            "search": {
                "runs": len(tree.order),
                "failed": sum(1 for i in tree.order if not tree.nodes[i].ok),
                "refused_proposals": led.rejected,
                "evaluations_during_search": sum(1 for c in self.checks
                                              if c["when"] == "search" and "seconds" in c),
                "evaluations_at_the_end": sum(1 for c in self.checks
                                           if c["when"] == "end" and "seconds" in c),
                "nodes_not_candidates": {i: tree.why_not(i) for i in tree.scored()
                                         if tree.why_not(i)},
                "branches_by_stage": {s: sum(1 for i in tree.order if tree.nodes[i].stage == s)
                                      for s in S.NAMES},
                "best_score_est_after_each_run": tree.history(),
            },
            "cost": {
                "flow_runs": led.flow_runs, "flow_run_budget": led.max_flow_runs,
                "flow_minutes": round(led.flow_seconds / 60, 1),
                "usd": led.usd, "usd_budget": led.max_usd,
                "usd_by_agent": led.by_agent(),
                "usd_by_model": led.by_model(),
                "model_call_retries": led.retries,
                "wall_minutes": round((time.monotonic() - self.started) / 60, 1),
                "baseline_from_cache": self.baseline_from_cache,
                "disk_freed_gb": round(self.freed_bytes / 1e9, 2),
            },
            "stage_agent_fallbacks": self.fallbacks,
            "navigator_corrections": self.corrections,
            "stop_decisions": led.decisions,
        }
        if extra:
            report.update(extra)
        self.save()
        (self.work / "report.json").write_text(json.dumps(report, indent=1))
        return report


def results_table(report: dict) -> str:
    """Every node of a finished search, one line for its estimate and one for its
    signoff if it has one: absolute values, and each as a ratio to the baseline's."""
    head = (f"  {'node':5s}{'':9s}{'score':>7s}{'ECP ns':>10s}{'x base':>8s}{'hold ns':>9s}"
            f"{'power W':>10s}{'x base':>8s}{'cells um2':>11s}{'x base':>8s}")

    def one(nid, what, b, key):
        def f(v, spec):
            return "-" if v is None else format(v, spec)
        return (f"  {nid:5s}{what:9s}{f(b[key], '.4f'):>7s}{f(b['ecp_ns'], '.4f'):>10s}"
                f"{f(b['ecp_vs_baseline'], '.4f'):>8s}{f(b['hold_slack_ns'], '.3f'):>9s}"
                f"{f(b['power_w'], '.4f'):>10s}{f(b['power_vs_baseline'], '.4f'):>8s}"
                f"{f(b['cell_area_um2'], '.0f'):>11s}{f(b['area_vs_baseline'], '.4f'):>8s}")

    lines = [head]
    for r in report.get("results", []):
        if r["estimate"]:
            lines.append(one(r["id"], "estimate", r["estimate"], "score_est"))
        if r["signoff"]:
            lines.append(one("" if r["estimate"] else r["id"], "signoff", r["signoff"], "score")
                         + ("" if r["signoff"]["passes_the_limits"] else "   fails a limit")
                         + ("   <- the answer" if r["id"] == report.get("final_node") else ""))
    return "\n".join(lines)

