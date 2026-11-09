"""Two budgets, the scoring gate, and the score.

Flow runs are the expensive budget: minutes of CPU each, and the thing that
bounds how many searches can share a machine. LLM dollars are nearly free by
comparison, which is why they are attributed per agent — a bloated context shows
up by name rather than as one anonymous total.

The flow-run budget counts every LibreLane launch: the baseline, each branch,
and each signoff, whether the search asked for it or it was made at the end. One run is always held back for signoff, so a search that
uses its whole allowance still ends with a result that can be scored.

The dollar figure is OpenRouter's own `usage.cost`, caught on the way through.
LiteLLM's recomputed estimate is not used: the real charge depends on which
upstream provider served the request, and those differ by up to 14x for one id.

Every model call leaves two records. ledger.json has what it cost: agent, model,
tokens, dollars, seconds. trace.jsonl has what was said: the messages that went
in and the answer that came back, one call per line under the same number.

    python -m pd.ledger WORK          every call of a run, one per line
    python -m pd.ledger WORK 12       what call 12 was sent and what it answered
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import names, stages as S

SIGNOFF_RESERVE = 1       # runs held back so that something can always be signed off at the end
# The dollar check runs between moves, and one move (stage agent plus navigator)
# costs about one run's share of the spend. Stopping only at zero let the last move
# overshoot the cap by 3%, which zeroes the score; stop with this many runs' worth
# of dollars still unspent.
USD_MARGIN = 1.5
MAX_SIGNOFFS = 3          # candidates signed off at the end at most, however many runs are left
TOLERANCE = 1.05          # die area and power may not exceed baseline by more than this

# ----------------------------------------------------------------- the priorities
# The score weighs three things a backend engineer trades against each other,
# each taken as a ratio to the untouched flow (subscript 0):
#
#     score = (ECP0 / ECP)^timing  x  (P0 / P)^power  x  (A0 / A)^area
#
#     ECP   effective clock period: the clock period minus the worst setup slack
#     P     total power
#     A     standard-cell area, fill cells not counted
#
# The three exponents below are the priorities, and they are the only thing to
# change to ask for a different trade. A weight of 0 takes that term out of the
# score, so (1, 0, 0) is timing alone. A weight is the share of a 1 % gain that
# reaches the score: with the weights below, a 1 % gain in area moves the score by
# about 0.9 %, and a 1 % gain in power by about 0.1 %. Each term is a ratio, so the
# score does not depend on units and the untouched flow is 1.0 whatever the weights.
#
# The same formula is used twice: on post-global-route estimates, corrected by
# whatever has been signed off, to rank nodes while the search runs (pd/tree.py),
# and on signoff numbers for the answer.
#
# BLE TX: the modulator runs at a fixed 8 MHz (CLOCK_PERIOD 125 in the design's
# config.yaml), one 8 MS/s DAC code per clock. A faster clock buys nothing, so
# timing carries no weight and is a pass/fail gate instead (SETUP_FLOOR_NS
# below). The die is fixed, so the layout should use as little of it as possible:
# the score is mostly standard-cell area (0.9), with a little weight on power (0.1).
WEIGHTS = {"timing": 0.0, "power": 0.1, "area": 0.9}

# The 8 MHz timing gate. A result passes only when its worst setup slack against
# CLOCK_PERIOD is at least this many ns, both at the scoring corner (tt) and at
# the worst of all corners (ss_125C_4v50 on gf180mcuD). Applied to signoff
# numbers in gate() and to the post-GR estimates when screening candidates
# (pd/tree.py), so a run that misses 8 MHz can never become the answer.
SETUP_FLOOR_NS = 0.0
TERMS = {"timing": "effective clock period", "power": "total power", "area": "cell area"}


def parse_weights(text: str | None) -> dict:
    """'0,0.1,0.9' -> weights for timing, power, area. None gives WEIGHTS."""
    if not text:
        return dict(WEIGHTS)
    parts = [float(x) for x in text.split(",")]
    if len(parts) != 3 or min(parts) < 0 or not any(parts):
        raise ValueError(f"weights are three numbers, timing,power,area, none negative "
                         f"and not all zero; got {text!r}")
    return dict(zip(TERMS, parts))


def versus(baseline: dict, metrics: dict, clock_ns: float) -> dict:
    """Each scored quantity of `metrics` over the baseline's. Below 1 is better."""
    def over(a, b):
        return None if a is None or not b else float(a) / float(b)
    return {"timing": over(S.effective_clock_period(metrics, clock_ns),
                           S.effective_clock_period(baseline, clock_ns)),
            "power": over(metrics.get(S.POWER_KEY), baseline.get(S.POWER_KEY)),
            "area": over(metrics.get(S.AREA_KEY), baseline.get(S.AREA_KEY))}


def combine(ratios: dict, weights: dict | None = None) -> float | None:
    """The weighted product above, from each quantity's ratio to the baseline.
    None if a quantity that carries weight is missing."""
    w = WEIGHTS if weights is None else weights
    out = 1.0
    for term in TERMS:
        if not w.get(term):
            continue
        ratio = ratios.get(term)
        if ratio is None or ratio <= 0:
            return None
        out *= ratio ** -w[term]
    return out


def merit(baseline: dict, metrics: dict, clock_ns: float, weights: dict | None = None) -> float | None:
    """The score of `metrics` against `baseline`, limits not applied."""
    return combine(versus(baseline, metrics, clock_ns), weights)


@dataclass
class Ledger:
    max_flow_runs: int = 20
    max_usd: float | None = 2.00      # None: no language model in this run
    flow_runs: int = 0
    flow_seconds: float = 0.0
    rejected: int = 0                 # proposals refused before any compute was spent
    retries: int = 0                  # model calls repeated after a transient failure
    calls: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)   # stop rule vs stop agent, per iteration
    trace: Path | None = None         # where each call's input and output are appended

    # ------------------------------------------------------------- recording
    def charge_run(self, seconds: float) -> None:
        self.flow_runs += 1
        self.flow_seconds += seconds

    def charge_call(self, agent: str, usd: float | None,
                    gen_id: str | None = None, tokens: dict | None = None,
                    model: str | None = None, served_by: str | None = None,
                    seconds: float | None = None, exchange: dict | None = None) -> None:
        """One model call. `model` is the id that was asked for; `served_by` is
        what the provider says answered, which is how a silent substitution
        would show up. `usd` is OpenRouter's own charge for this one call.
        `exchange` is what was sent and what came back; it goes to the trace."""
        self.calls.append({"n": len(self.calls) + 1, "agent": agent, "model": model,
                           "served_by": served_by, "usd": usd or 0.0, "tokens": tokens,
                           "seconds": None if seconds is None else round(seconds, 2),
                           "gen_id": gen_id})
        if self.trace is not None and exchange is not None:
            line = {"n": len(self.calls), "agent": agent, "model": model, **exchange}
            with open(self.trace, "a") as f:
                f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")

    # ------------------------------------------------------------- questions
    @property
    def usd(self) -> float:
        return round(sum(c["usd"] for c in self.calls), 8)

    @property
    def runs_left(self) -> int:
        return max(0, self.max_flow_runs - self.flow_runs)

    @property
    def search_runs_left(self) -> int:
        """Runs still available to the search, with signoff's share held back."""
        return max(0, self.runs_left - SIGNOFF_RESERVE)

    @property
    def usd_per_run(self) -> float:
        """Language-model dollars spent per flow run so far."""
        return self.usd / self.flow_runs if self.flow_runs else 0.0

    @property
    def usd_left(self) -> float | None:
        if self.max_usd is None:
            return None
        return round(max(0.0, self.max_usd - self.usd), 8)

    def must_stop(self) -> str | None:
        """Why the search has to end now, or None. This overrides any agent."""
        if self.search_runs_left <= 0:
            return "flow-run budget spent (one run is reserved for an evaluation at the end)"
        if self.max_usd is not None and self.usd_left <= USD_MARGIN * self.usd_per_run:
            return "dollar budget spent (what is left would not cover another move)"
        return None

    def overspent(self) -> str | None:
        """A broken budget, which zeroes the score."""
        if self.flow_runs > self.max_flow_runs:
            return f"flow-run budget exceeded ({self.flow_runs} of {self.max_flow_runs})"
        if self.max_usd is not None and self.usd > self.max_usd:
            return f"dollar budget exceeded (${self.usd:.4f} of ${self.max_usd:.2f})"
        return None

    def _tally(self, key: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for c in self.calls:
            e = out.setdefault(c.get(key) or "unrecorded",
                               {"usd": 0.0, "calls": 0, "prompt_tokens": 0,
                                "completion_tokens": 0})
            e["usd"] = round(e["usd"] + c["usd"], 8)
            e["calls"] += 1
            t = c.get("tokens") or {}
            e["prompt_tokens"] += t.get("prompt") or 0
            e["completion_tokens"] += t.get("completion") or 0
        return out

    def by_agent(self) -> dict[str, dict]:
        out = self._tally("agent")
        for agent, e in out.items():
            e["models"] = sorted({c["model"] for c in self.calls
                                  if c["agent"] == agent and c.get("model")})
        return out

    def by_model(self) -> dict[str, dict]:
        return self._tally("model")

    def view(self) -> dict:
        """The budget as an agent is shown it. Numbers only."""
        return {"flow_runs_used": self.flow_runs,
                "flow_runs_left_for_search": self.search_runs_left,
                "usd_used": round(self.usd, 4),
                "usd_left": None if self.usd_left is None else round(self.usd_left, 4)}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({
            "budget": {"max_flow_runs": self.max_flow_runs, "max_usd": self.max_usd},
            "spent": {"flow_runs": self.flow_runs, "usd": self.usd,
                      "rejected_proposals": self.rejected, "model_call_retries": self.retries},
            "flow_seconds": round(self.flow_seconds, 1),
            "by_agent": self.by_agent(),
            "by_model": self.by_model(),
            "decisions": self.decisions,
            "calls": self.calls,
        }, indent=1))


# --------------------------------------------------------------------- scoring
# What happens when nothing that was signed off passes and beats the baseline.
# True: the baseline is submitted instead and the run scores 1.0 — nothing was
# gained, but an engineer does not ship something worse than what they started
# with. False: the best failed candidate is the answer and the run scores 0.
FALLBACK_TO_BASELINE = True


def setup_problems(metrics: dict) -> list[str]:
    """Why `metrics` misses the 8 MHz setup gate. Empty means it meets it, and
    SETUP_FLOOR_NS = None turns the gate off (pd/selftest.py does, for the
    framework checks written for a design scored on timing)."""
    floor = SETUP_FLOOR_NS
    if floor is None:
        return []
    out = []
    for label, v in ((S.FOM_CORNER, S.setup_ws(metrics)),
                     ("worst corner", metrics.get(S.WS_WORST_KEY))):
        if v is not None and float(v) < floor:
            out.append(f"setup slack at {label} {float(v):.4f} ns is below {floor:g} ns")
    return out


_KINDS = {"slew": "max-slew", "cap": "max-capacitance"}
CORNERS = (S.FOM_CORNER, S.SLOW_CORNER, S.SLOW_CORNER_MAX)
ELECTRICAL = tuple((f"design__max_{kind}_violation__count__corner:{corner}", f"{label} violations at {corner}")
                   for corner in CORNERS for kind, label in _KINDS.items())


def electrical_problems(metrics: dict, corners: tuple = CORNERS) -> list[str]:
    """Why `metrics` has slew or capacitance violations at one of `corners`.

    The rule is absolute: none, at the typical and the slow corner. The baseline does
    not meet it (14 slew violations at nom_ss, 30 at max_ss and one capacitance
    violation at signoff), so nothing is compared with it. Signoff is the only place
    the slow corner can be read: after global routing the flow reports about 1284
    slew violations there, against 14 at signoff, so the in-loop estimates are
    screened on the typical corner alone. Fanout violations are not counted: they are
    all clock-tree buffers against the config's own limit. A count that is not
    reported is not checked.
    """
    out = []
    for corner in corners:
        for kind, label in _KINDS.items():
            v = metrics.get(f"design__max_{kind}_violation__count__corner:{corner}")
            if v is not None and float(v) > 0:
                out.append(f"{label} violations at {corner}: {int(float(v))}")
    return out


def gate(baseline: dict, candidate: dict) -> list[str]:
    """Why a signed-off candidate is not acceptable. Empty means it passes.

    Setup timing is a pass/fail check against the 8 MHz clock: SETUP_FLOOR_NS
    at the scoring corner and at the worst corner. Power is both scored and
    limited: the score rewards using less, the limit says how much more is too
    much whatever else was gained.
    """
    reasons: list[str] = []
    if S.setup_ws(candidate) is None:
        return ["no signoff timing reported"]
    reasons += setup_problems(candidate)
    reasons += electrical_problems(candidate)

    for key, label in (("magic__drc_error__count", "Magic DRC errors"),
                       ("design__lvs_error__count", "Netgen LVS errors"),
                       ("antenna__violating__nets", "antenna violations"),
                       ("route__drc_errors", "routing DRC errors")):
        v = candidate.get(key)
        if v is None:
            reasons.append(f"{label}: not reported")
        elif float(v) > 0:
            reasons.append(f"{label}: {int(float(v))}")

    hold = S.hold_ws(candidate)
    if hold is None:
        reasons.append("hold slack: not reported")
    elif hold < 0:
        reasons.append(f"hold violation at {S.FOM_CORNER}: {hold:.4f} ns")

    for key, label in (("design__die__area", "die area"), (S.POWER_KEY, "total power")):
        b, f = baseline.get(key), candidate.get(key)
        if b and f and float(f) > float(b) * TOLERANCE:
            reasons.append(f"{label} is {float(f) / float(b):.4f}x baseline (limit {TOLERANCE})")
    return reasons


def score(baseline: dict, final: dict, clock_ns: float, ledger: Ledger,
          weights: dict | None = None) -> dict:
    """The figure of merit: merit() on signoff numbers, at the tt corner.

    Higher is better; 1.0 is the baseline, the flow as LibreLane ships it. A
    final result that fails the gate, or a run that overran its budget, scores
    zero. `vs_baseline` gives each quantity as final over baseline, so below 1
    is better there, and the score is the product of (1 / ratio)^weight over the
    three that carry a weight.
    """
    w = dict(WEIGHTS if weights is None else weights)
    base_ecp = S.effective_clock_period(baseline, clock_ns)
    fin_ecp = S.effective_clock_period(final, clock_ns)
    reasons = gate(baseline, final)
    over = ledger.overspent()
    if over:
        reasons.append(over)

    vs = versus(baseline, final, clock_ns)
    raw = merit(baseline, final, clock_ns, w)
    if raw is None and not reasons:
        reasons.append("not reported at signoff: " + ", ".join(
            TERMS[t] for t in TERMS if w.get(t) and vs[t] is None))
    ratios = {TERMS[t]: None if vs[t] is None else round(vs[t], 4) for t in TERMS}
    b, f = baseline.get("design__die__area"), final.get("design__die__area")
    if b and f:
        ratios["die area"] = round(float(f) / float(b), 4)

    raw = None if raw is None else round(raw, 5)
    gain_pct = None if raw is None else round((raw - 1.0) * 100, 3)
    return {
        "score": 0.0 if reasons else raw,
        "score_before_gate": raw,
        "weights": w,
        "vs_baseline": ratios,
        "gain_percent": gain_pct,
        "baseline_ecp_ns": None if base_ecp is None else round(base_ecp, 4),
        "final_ecp_ns": None if fin_ecp is None else round(fin_ecp, 4),
        "scoring_corner": S.FOM_CORNER,
        "final_setup_slack_ns": None if S.setup_ws(final) is None else round(S.setup_ws(final), 4),
        "final_hold_slack_ns": None if S.hold_ws(final) is None else round(S.hold_ws(final), 4),
        "final_worst_corner_setup_ns": (None if final.get(S.WS_WORST_KEY) is None
                                        else round(float(final[S.WS_WORST_KEY]), 4)),
        "final_worst_corner_hold_ns": (None if final.get(S.HOLD_WORST_KEY) is None
                                       else round(float(final[S.HOLD_WORST_KEY]), 4)),
        "zeroed_because": reasons,
        "usd_per_percent_gain": (None if not gain_pct or gain_pct <= 0 or not ledger.usd
                                 else round(ledger.usd / gain_pct, 5)),
    }


# --------------------------------------------------------------------- reading one back
def show(work: str | Path) -> str:
    """Every model call of a finished or running search, one per line. A run
    saved under the old agent names is shown under the new ones (pd/names.py)."""
    work = Path(work)
    d = names.load_ledger(work / "ledger.json")
    rp = work / "report.json"
    roles = (names.load_report(rp).get("models") or {}) if rp.exists() else {}
    lines = ["    #  agent          model                                    in tok  out tok        usd     s",
             "  " + "-" * 92]
    for i, c in enumerate(d["calls"], 1):
        t = c.get("tokens") or {}
        model = c.get("model") or roles.get(c["agent"]) or "unrecorded"
        sec = c.get("seconds")
        lines.append(f"  {c.get('n', i):3d}  {c['agent']:14s} {model.removeprefix('openrouter/'):38s} "
                     f"{t.get('prompt') or 0:8d} {t.get('completion') or 0:8d} "
                     f"{c['usd']:10.6f} {'' if sec is None else format(sec, '5.1f')}")
    lines.append("  " + "-" * 92)
    for title, key in (("by agent", "by_agent"), ("by model", "by_model")):
        for name, e in (d.get(key) or {}).items():
            lines.append(f"  {title:8s}  {name.removeprefix('openrouter/'):40s} {e['prompt_tokens']:8d} "
                         f"{e['completion_tokens']:8d} {e['usd']:10.6f}   {e['calls']} calls")
    lines.append(f"  total     {len(d['calls'])} calls, ${d['spent']['usd']:.6f}"
                 f" of ${d['budget']['max_usd']}" if d["budget"]["max_usd"] is not None
                 else f"  total     {len(d['calls'])} calls")
    return "\n".join(lines)


def show_call(work: str | Path, n: int) -> str:
    """What one model call was sent and what it answered, from trace.jsonl."""
    path = Path(work) / "trace.jsonl"
    if not path.exists():
        return f"no trace.jsonl in {work}: the run was made without a model, or before traces were kept"
    for c in names.load_trace(path):
        if c["n"] != n:
            continue
        out = [f"call {n}: {c['agent']} on {c.get('model')}, after {c.get('runs_so_far')} flow runs"]
        for m in c.get("input", []):
            out.append(f"\n--- in: {m.get('role')} " + "-" * 60)
            if m.get("content"):
                out.append(str(m["content"]))
            for tc in m.get("tool_calls") or []:
                out.append(f"[called {tc['name']}] {json.dumps(tc['arguments'])}")
        if c.get("tools"):
            out.append(f"\n--- tools on offer: {', '.join(c['tools'])}")
        out.append("\n--- out " + "-" * 66)
        if c["output"].get("content"):
            out.append(str(c["output"]["content"]))
        for tc in c["output"].get("tool_calls") or []:
            out.append(f"[calls {tc['name']}] {json.dumps(tc['arguments'], indent=1)}")
        return "\n".join(out)
    return f"no call {n} in {path}"


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[2].isdigit():
        print(show_call(sys.argv[1], int(sys.argv[2])))
    elif len(sys.argv) == 2:
        print(show(sys.argv[1]))
    else:
        raise SystemExit("usage: python -m pd.ledger <work directory> [call number]")
