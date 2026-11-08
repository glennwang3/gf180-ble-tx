"""The search tree: every implementation tried so far, and how to summarise it.

A node is one run: the settings that produced it, the numbers it reached, and
the saved branch points it offers. Two signals are derived for the navigator, both
one-liners:

  times branched from     keeps the search from grinding on one node
  by stage                branches made, candidates produced, gap to the best

Nodes are ranked on an *estimated score*: the score formula of pd/ledger.py on
each node's post-global-route estimates, as ratios to the baseline's own
estimates. Higher is better, 1.0 is the baseline, which is the root.

An estimate is not the real number, and how far off it is depends on the kind
of layout (stages.kind_of). So the tree learns from every node that is signed
off. For each kind it keeps a *correction*: how far, on the nodes of that kind
that have been signed off, the real ratios sat from the estimated ones. Every
estimate of that kind is multiplied by it. A kind with no signed-off node has
no correction, and its estimates are marked as unchecked: they can be compared
with one another, not with the rest of the tree.

Not every node can be the final answer. The score is zero if the signed-off
result has negative hold slack or too much power, and the search only has
estimates of either. A node is a *candidate* when its estimates meet the 8 MHz
setup gate (ledger.SETUP_FLOOR_NS) and clear a hold floor and a power ceiling; "best" always means best among candidates.

No LLM runs in this file.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import runner, stages as S
from .ledger import TERMS, WEIGHTS, combine, electrical_problems, gate, setup_problems, versus

FANOUT, MARGIN = "MAX_FANOUT_CONSTRAINT", "DESIGN_REPAIR_MAX_SLEW_PCT"


@dataclass
class Node:
    id: str
    parent: str | None
    stage: str | None                  # stage this node was branched at; None for the root
    params: dict                       # full blended configuration on this path
    metrics: dict                      # post-global-route headline numbers
    stage_states: dict                 # stage or END -> snapshot usable for branching
    seconds: float = 0.0
    ok: bool = True
    branched: int = 0                  # how many branches have started here
    digests: dict = field(default_factory=dict)          # stage -> log excerpt
    stage_seconds: dict = field(default_factory=dict)    # where this run's time went
    signoff_metrics: dict = field(default_factory=dict)
    error: str = ""
    log_tail: str = ""                 # end of the failing log; the diagnostician reads this
    note: str = ""                     # diagnosis, or why the navigator chose it
    store: str = ""                    # directory holding this node's snapshots


class Tree:
    def __init__(self, clock_period_ns: float, hold_floor: float = 0.0,
                 power_ceiling: float | None = None, weights: dict | None = None):
        self.clock = clock_period_ns
        self.weights = dict(WEIGHTS if weights is None else weights)   # see pd/ledger.py
        # Which nodes may be the final answer, judged on in-loop estimates. The
        # gate itself is applied at signoff, in ledger.gate(); these two numbers
        # are how much of an estimate the search is willing to trust.
        self.hold_floor = hold_floor            # ns of estimated hold slack a candidate needs
        self.power_ceiling = power_ceiling      # estimated power / baseline's; None: not checked
        self.nodes: dict[str, Node] = {}
        self.order: list[str] = []

    # ---------------------------------------------------------------- building
    def next_id(self) -> str:
        return f"n{len(self.order)}"

    def add(self, parent: str | None, stage: str | None, params: dict, result,
            store: str = "", note: str = "") -> Node:
        """Attach the outcome of a run. `result` is a runner.RunResult."""
        nid = self.next_id()
        n = Node(nid, parent, stage, dict(params), dict(result.metrics),
                 dict(result.stage_states), result.seconds, result.ok,
                 digests=dict(result.digests),
                 stage_seconds=dict(getattr(result, "stage_seconds", {}) or {}),
                 signoff_metrics=dict(result.signoff_metrics),
                 error=result.error, log_tail=result.log_tail, note=note, store=store)
        self.nodes[nid] = n
        self.order.append(nid)
        if parent in self.nodes:
            self.nodes[parent].branched += 1
        return n

    # ---------------------------------------------------------------- reading
    def bounds(self) -> dict:
        """Knob ranges for this design; the density floor follows its utilisation."""
        util = None
        if self.order:
            util = self.nodes[self.order[0]].metrics.get("design__instance__utilization")
        return S.bounds_for(util)

    def ecp(self, nid: str) -> float | None:
        return S.effective_clock_period(self.nodes[nid].metrics, self.clock)

    # ---------------------------------------------------------------- real and estimated
    def baseline(self) -> dict:
        """Signoff numbers of the baseline, the root: what a score is a ratio to."""
        return self.nodes[self.order[0]].signoff_metrics if self.order else {}

    def signed_off(self, nid: str) -> bool:
        return S.setup_ws(self.nodes[nid].signoff_metrics) is not None

    def kind(self, nid: str) -> str:
        return S.kind_of(self.nodes[nid].params)

    def real(self, nid: str) -> dict | None:
        """Each scored quantity of a signed-off node over the baseline's, as
        signoff found it. None for a node that has not been signed off."""
        if not self.signed_off(nid):
            return None
        return versus(self.baseline(), self.nodes[nid].signoff_metrics, self.clock)

    def real_score(self, nid: str) -> float | None:
        """The score of a signed-off node, limits not applied."""
        r = self.real(nid)
        return None if r is None else combine(r, self.weights)

    def problems(self, nid: str) -> list[str]:
        """Why a signed-off node cannot be the answer. Empty means it can."""
        return gate(self.baseline(), self.nodes[nid].signoff_metrics)

    def _raw(self, nid: str) -> dict:
        """Estimate over the baseline's estimate, uncorrected. Both are the
        post-global-route figure, so like is compared with like."""
        if not self.order:
            return {t: None for t in TERMS}
        return versus(self.nodes[self.order[0]].metrics, self.nodes[nid].metrics, self.clock)

    def correction(self, kind: str) -> dict | None:
        """What signoff has shown about estimates of one kind of layout: for
        each scored quantity, real ratio over estimated ratio, as a geometric
        mean over the nodes of that kind that have been signed off. None when
        no node of the kind has been signed off.

        The baseline is signed off but teaches nothing here: both its ratios
        are 1 by definition. It does make its own kind a checked one, with no
        correction until another node of that kind is signed off."""
        logs: dict[str, list[float]] = {t: [] for t in TERMS}
        root = self.order[0] if self.order else None
        for i in self.order:
            if i == root or not (self.nodes[i].ok and self.signed_off(i) and self.kind(i) == kind):
                continue
            raw, real = self._raw(i), self.real(i)
            for t in TERMS:
                if raw[t] and real[t]:
                    logs[t].append(math.log(real[t] / raw[t]))
        if not any(logs.values()):
            same = root is not None and self.signed_off(root) and self.kind(root) == kind
            return {t: 1.0 for t in TERMS} if same else None
        return {t: math.exp(sum(v) / len(v)) if v else 1.0 for t, v in logs.items()}

    def checked(self, nid: str) -> bool:
        """Whether a node's estimate has been corrected: some node of its kind
        has been signed off."""
        return self.correction(self.kind(nid)) is not None

    def vs_baseline(self, nid: str) -> dict:
        """Each scored quantity of a node over the baseline's, estimated: the
        ratio of the two estimates, times the correction of the node's kind if
        it has one."""
        if self.order and nid == self.order[0]:
            return {t: 1.0 for t in TERMS}          # the baseline is 1.0 by definition
        raw, fix = self._raw(nid), self.correction(self.kind(nid)) or {}
        return {t: None if raw[t] is None else raw[t] * fix.get(t, 1.0) for t in TERMS}

    def est_score(self, nid: str) -> float | None:
        """The estimated score of a node: what the search ranks on. Higher is
        better and the baseline is 1.0."""
        return combine(self.vs_baseline(nid), self.weights)

    def kinds(self) -> list[dict]:
        """Every kind of layout in the tree: how many nodes, how many of them
        evaluated, its best node by estimate, and what each signoff of the kind
        showed — the score signoff found over the score the uncorrected estimate
        had given, one number per signed-off node. The correction is their mean,
        so the list says how much there is behind it."""
        out: dict[str, dict] = {}
        root = self.order[0] if self.order else None
        for i in self.scored():
            k = out.setdefault(self.kind(i), {"kind": self.kind(i), "nodes": 0, "evaluated": 0,
                                              "best": None, "signoff_over_estimate": []})
            k["nodes"] += 1
            k["evaluated"] += self.signed_off(i)
            if i != root and self.signed_off(i):
                raw = combine(self._raw(i), self.weights)
                if raw:
                    k["signoff_over_estimate"].append(round(self.real_score(i) / raw, 3))
            if k["best"] is None or self.est_score(i) > self.est_score(k["best"]):
                k["best"] = i
        for k in out.values():
            n = len(k["signoff_over_estimate"])
            k["estimates"] = (
                f"corrected by what {n} evaluation{'s' if n > 1 else ''} of this kind showed"
                + ("; one evaluation is one sample" if n == 1 else "") if n else
                "the baseline's kind; corrected once another node of it is evaluated"
                if k["evaluated"] else
                "unchecked: not comparable with other kinds until one of these nodes is evaluated")
        return list(out.values())

    def scored(self) -> list[str]:
        return [i for i in self.order if self.nodes[i].ok and self.est_score(i) is not None]

    def hold(self, nid: str) -> float | None:
        return S.hold_ws(self.nodes[nid].metrics)

    def power_ratio(self, nid: str) -> float | None:
        """Estimated power of a node over the baseline's."""
        return self.vs_baseline(nid)["power"]

    def area_ratio(self, nid: str) -> float | None:
        """Estimated standard-cell area of a node over the baseline's."""
        return self.vs_baseline(nid)["area"]

    def setting(self, nid: str, key: str) -> float:
        """A repair setting a node was made with; the baseline's where it is unset."""
        return float(self.nodes[nid].params.get(key, S.BY_NAME["PL"].params[key].default))

    def predicted_failure(self, nid: str) -> str | None:
        """Why a node that was not signed off is expected to fail signoff, or None.

        A looser fanout limit leaves more nets unrepaired and a smaller slew margin
        repairs them less, so a node signed off with violations predicts the same for
        any node whose fanout limit is at least as high and whose margin is no
        larger. Only a signoff that fixed what it could counts (it reports
        eco__passes, see runner.signoff): the baseline's own signoff does not upsize
        drivers, so its violations say nothing about a node that will be. This is
        an assumption, not a measurement, and it saves a flow run per use; a node
        that was itself signed off is judged on what signoff found."""
        f, m = self.setting(nid, FANOUT), self.setting(nid, MARGIN)
        for i in self.order:
            if i == nid or not (self.nodes[i].ok and self.signed_off(i)):
                continue
            if "eco__passes" not in (self.nodes[i].signoff_metrics or {}):
                continue
            if not any(w.startswith("max-") for w in self.problems(i)):
                continue
            if self.setting(i, FANOUT) <= f and self.setting(i, MARGIN) >= m:
                return (f"fanout limit {f:g} with slew margin {m:g} is no safer than {i}'s "
                        f"({self.setting(i, FANOUT):g}, {self.setting(i, MARGIN):g}), "
                        "which failed signoff on slew or capacitance violations")
        return None

    def why_not(self, nid: str) -> str | None:
        """Why a scored node is not a candidate for the final answer, or None.
        The baseline always is one: it is what gets submitted if nothing else can be."""
        if self.order and nid == self.order[0]:
            return None
        if self.signed_off(nid):            # what signoff found outranks any estimate
            found = self.problems(nid)
            return ("evaluated and failed: " + "; ".join(found)) if found else None
        h, p = self.hold(nid), self.power_ratio(nid)
        why = ["estimated " + w for w in setup_problems(self.nodes[nid].metrics)]
        predicted = self.predicted_failure(nid)
        if predicted:
            why.append(predicted)
        why += ["estimated " + w for w in electrical_problems(self.nodes[nid].metrics, (S.FOM_CORNER,))]
        if h is not None and h < self.hold_floor:
            why.append(f"estimated hold slack {h:.3f} ns is below the floor of {self.hold_floor:g}")
        if self.power_ceiling is not None and p is not None and p > self.power_ceiling:
            why.append(f"estimated power is {p:.3f}x baseline, above the ceiling of "
                       f"{self.power_ceiling:g}")
        return "; ".join(why) or None

    def valid(self) -> list[str]:
        """Scored nodes that could be the final answer: on the in-loop
        estimates, enough hold slack and not too much power."""
        return [i for i in self.scored() if self.why_not(i) is None]

    def incumbent(self) -> str | None:
        """The candidate with the highest estimated score. A better-looking node
        that breaks hold or the power limit is not a candidate."""
        s = self.valid() or self.scored()
        return max(s, key=lambda i: (self.est_score(i), -self.order.index(i))) if s else None

    def ranked(self) -> list[str]:
        """Candidates, best estimated score first; earlier runs win ties."""
        return sorted(self.valid(), key=lambda i: (-self.est_score(i), self.order.index(i)))

    def row(self, nid: str) -> dict:
        """The numbers of one node, under the names every view uses for them."""
        def r(v, places):
            return None if v is None else round(v, places)
        return {"score_est": r(self.est_score(nid), 4),
                "ecp_ns": r(self.ecp(nid), 4),
                "hold_slack_ns": r(self.hold(nid), 3),
                "power_vs_baseline": r(self.power_ratio(nid), 3),
                "area_vs_baseline": r(self.area_ratio(nid), 3)}

    def real_row(self, nid: str) -> dict | None:
        """What signoff found for a node, under the names row() gives its
        estimates, so the two read against each other field by field."""
        real = self.real(nid)
        if real is None:
            return None
        m = self.nodes[nid].signoff_metrics

        def r(v, places):
            return None if v is None else round(v, places)
        return {"score": r(self.real_score(nid), 4),
                "ecp_ns": r(S.effective_clock_period(m, self.clock), 4),
                "hold_slack_ns": r(S.hold_ws(m), 3),
                "power_vs_baseline": r(real["power"], 3),
                "area_vs_baseline": r(real["area"], 3)}

    def record(self, nid: str) -> dict:
        """Everything known about one node, for the report: each scored quantity
        as an absolute value and as a ratio to the baseline's, as estimated and,
        if the node was signed off, as signoff found it.

        An estimate's absolute values are what was read after global routing. Its
        ratios are the ones the search ranked on: to the baseline's own estimate,
        times the correction of the node's kind as it stood at the end."""
        n = self.nodes[nid]

        def r(v, places):
            return None if v is None else round(v, places)

        def block(m, ratios, score, name):
            return {name: r(score, 4),
                    "ecp_ns": r(S.effective_clock_period(m, self.clock), 4),
                    "ecp_vs_baseline": r(ratios["timing"], 4),
                    "setup_slack_ns": r(S.setup_ws(m), 4),
                    "hold_slack_ns": r(S.hold_ws(m), 4),
                    "power_w": r(m.get(S.POWER_KEY), 5),
                    "power_vs_baseline": r(ratios["power"], 4),
                    "cell_area_um2": r(m.get(S.AREA_KEY), 1),
                    "area_vs_baseline": r(ratios["area"], 4)}

        out = {"id": nid, "made_by_branching_at": n.stage or "baseline", "from": n.parent,
               "settings": n.params, "kind": self.kind(nid), "ok": n.ok,
               "estimate": None, "signoff": None}
        if n.ok and n.metrics and self.est_score(nid) is not None:
            out["estimate"] = block(n.metrics, self.vs_baseline(nid), self.est_score(nid), "score_est")
            out["estimate"]["ratios_corrected_by_signoffs"] = bool(
                nid != self.order[0] and self.correction(self.kind(nid)))
        if n.ok and self.signed_off(nid):
            out["signoff"] = block(n.signoff_metrics, self.real(nid), self.real_score(nid), "score")
            out["signoff"]["passes_the_limits"] = not self.problems(nid)
        return out

    def lineage(self, nid: str | None) -> list[str]:
        out = []
        while nid in self.nodes:
            out.append(nid)
            nid = self.nodes[nid].parent
        return out

    def branchable(self) -> list[tuple[str, str]]:
        """(node, stage) pairs a new branch may start from.

        A node only offers stages after the one it was itself branched at, and
        only while the snapshot is still on disk.
        """
        out = []
        for nid in self.order:
            n = self.nodes[nid]
            if not n.ok:
                continue
            for name in S.after(n.stage):
                p = n.stage_states.get(name)
                if p and os.path.exists(p):
                    out.append((nid, name))
        return out

    def can_evaluate(self) -> list[str]:
        """Nodes the navigator could evaluate now, that is, take through signoff:
        finished, not signed off yet, and with their post-global-route state
        still on disk."""
        out = []
        for nid in self.scored():
            n = self.nodes[nid]
            end = n.stage_states.get(runner.END)
            if not self.signed_off(nid) and not n.error and end and os.path.exists(end):
                out.append(nid)
        return out

    can_sign_off = can_evaluate             # the name before the move was called evaluate

    def digest_for(self, nid: str, stage: str) -> str:
        """How `stage` went on the path leading to `nid`: its own run if it has
        one, otherwise the nearest ancestor that ran that stage."""
        for i in self.lineage(nid):
            d = self.nodes[i].digests.get(stage)
            if d:
                return d
        return ""

    def tried(self, stage: str, limit: int = 6) -> list[dict]:
        """What has already been tried at `stage`, with the result each gave."""
        keys = S.BY_NAME[stage].params
        out = []
        for nid in self.order:
            n = self.nodes[nid]
            if n.stage != stage:
                continue
            row = {"from": n.parent,
                   "params": {k: n.params[k] for k in keys if k in n.params},
                   **self.row(nid), "ok": n.ok}
            if not n.ok:                 # what the diagnostician made of it, if it ran
                row["why_it_failed"] = (n.note or n.error)[:300]
            elif self.signed_off(nid):   # signoff outranks every estimate, so say what it found
                found = self.problems(nid)
                row["signoff"] = ("failed: " + "; ".join(found)) if found else "passed"
            out.append(row)
        return out[-limit:]

    # ---------------------------------------------------------------- signals
    def by_stage(self) -> dict[str, dict]:
        """Per stage: how many branches were made there, how many of them are
        candidates, and how far the best of those is behind the best overall, in
        estimated score. Zero means the best node came from that stage; a stage
        with branches but no candidates has so far only produced results that
        cannot be used."""
        cands = self.valid()
        best = max((self.est_score(i) for i in cands), default=None)
        out = {}
        for s in S.NAMES:
            made = [i for i in self.order if self.nodes[i].stage == s]
            good = [self.est_score(i) for i in cands if self.nodes[i].stage == s]
            out[s] = {"branches": len(made), "candidates": len(good),
                      "best_is_behind_by": round(best - max(good), 4) if good else None}
        return out

    def history(self) -> list[float]:
        """Best-so-far estimated score among candidates after each run, for the
        stop rule, as the tree estimates them now. Starts at 1.0, the baseline.
        It can rise without a new node: signing a node off corrects every
        estimate of its kind."""
        out, best = [], None
        ok = set(self.valid())
        for i in self.order:
            e = self.est_score(i) if i in ok else None
            if e is not None:
                best = e if best is None else max(best, e)
            if best is not None:
                out.append(round(best, 4))
        return out

    # ---------------------------------------------------------------- the view
    def summary(self, top: int = 5) -> dict:
        """What the navigator sees. Compact on purpose: this is most of the token bill."""
        inc = self.incumbent()
        root = self.nodes[self.order[0]] if self.order else None
        options = self.branchable()
        ranked = self.ranked()[:top]
        if root is not None and root.id not in ranked:
            ranked.append(root.id)                  # the reference point is always shown
        broken = [i for i in self.scored() if i not in self.valid()]

        def row(i):
            n = self.nodes[i]
            real = self.real_score(i)
            return {
                "id": i,
                "made_by_branching_at": n.stage or "baseline",
                "from": n.parent,
                **self.row(i),
                "evaluated_score": None if real is None else round(real, 4),
                "times_branched_from": n.branched,
                "can_branch_at": [s for (nid, s) in options if nid == i],
            }

        kinds = self.kinds()
        for k in kinds:                     # the best of every kind is shown, however it ranks
            if k["best"] not in ranked:
                ranked.append(k["best"])
            k["best"] = {"id": k["best"], "score_est": round(self.est_score(k["best"]), 4)}

        failed = [{"id": i, "stage": self.nodes[i].stage, "from": self.nodes[i].parent,
                   "why": (self.nodes[i].note or self.nodes[i].error)[:160]}
                  for i in self.order if not self.nodes[i].ok][-3:]
        return {
            "runs_so_far": len(self.order),
            "best": None if inc is None else {"id": inc,
                                              "score_est": round(self.est_score(inc), 4)},
            "best_nodes": [row(i) for i in ranked],
            "kinds": kinds,
            "can_evaluate": self.can_evaluate(),
            "by_stage": self.by_stage(),
            "not_candidates": [{"id": i, "score_est": round(self.est_score(i), 4),
                                "made_by_branching_at": self.nodes[i].stage,
                                "why": self.why_not(i)} for i in broken[-6:]],
            "recent_failures": failed,
        }

    # ---------------------------------------------------------------- storage
    def prune(self, keep: int = 6) -> int:
        """Drop the snapshots of nodes that are neither good nor on the best path.

        Returns bytes freed. A pruned node stays in the tree as a record; it just
        stops being a place to branch from.
        """
        inc = self.incumbent()
        protect = set(self.lineage(inc)) | set(self.ranked()[:keep])
        protect |= {k["best"] for k in self.kinds()}    # a kind stays open to being evaluated
        if self.order:
            protect.add(self.order[0])
        freed = 0
        for nid in self.order:
            n = self.nodes[nid]
            if nid in protect or not n.stage_states:
                continue
            if n.store:
                freed += runner.drop_snapshots(n.store)
            n.stage_states = {}
        return freed

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(
            {"clock": self.clock, "hold_floor": self.hold_floor,
             "power_ceiling": self.power_ceiling, "weights": self.weights,
             "order": self.order,
             "nodes": {k: asdict(v) for k, v in self.nodes.items()}}, indent=1))

    @classmethod
    def load(cls, path: str | Path) -> "Tree":
        d = json.loads(Path(path).read_text())
        t = cls(d["clock"], d.get("hold_floor", 0.0), d.get("power_ceiling"),
                d.get("weights"))
        t.order = d["order"]
        t.nodes = {k: Node(**v) for k, v in d["nodes"].items()}
        return t
