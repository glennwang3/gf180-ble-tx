"""Checks that need no EDA tool, no model and no key. Seconds to run.

    python -m pd.selftest          logic only
    python -m pd.selftest --env    also check the tools, the key and the Python packages

Run it after any edit. It exercises the tree, the budget, the scoring gate and
the knob rules with made-up numbers, so a slip in the plumbing is caught before
five minutes of LibreLane are spent finding it.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from . import ledger as L, stages as S
from .ledger import Ledger, merit, parse_weights, score
from .runner import END, RunResult
from .tree import Tree

_FAILED = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        _FAILED.append(name)


TIMING_ONLY = {"timing": 1.0, "power": 0.0, "area": 0.0}
EVEN = {"timing": 1.0, "power": 0.5, "area": 0.5}      # fixed here, whatever ledger.WEIGHTS says


def _res(ws, states=(), ok=True, seconds=10.0, power=0.10, area=1.0e6, cells=3.0e5, **sign):
    m = {S.WS_KEY: ws, S.HOLD_KEY: sign.get("hold", 0.3), S.POWER_KEY: power,
         S.AREA_KEY: cells, "design__die__area": area,
         "design__instance__utilization": 0.34}
    return RunResult(ok, seconds, m if ok else {}, dict(sign.get("signoff", {})),
                     {s: s for s in states})


def logic() -> None:
    print("knobs")
    b = S.bounds_for(0.34)
    check("every knob belongs to exactly one stage",
          sum(len(s.params) for s in S.STAGES) == len(S.ALLOWED_KEYS))
    check("density floor follows utilisation", b["PL_TARGET_DENSITY_PCT"].lo == 39)
    check("a check switch is not a tunable key",
          bool(S.validate({"ERROR_ON_MAGIC_DRC": False}, b)))
    check("out-of-range value is refused", bool(S.validate({"GRT_ADJUSTMENT": 0.9}, b)))
    check("a switch refuses a number", bool(S.validate({"PL_TIMING_DRIVEN": 1}, b)))
    check("a number knob refuses true/false", bool(S.validate({"GRT_ADJUSTMENT": True}, b)))
    check("a whole-number knob refuses a fraction",
          bool(S.validate({"MAX_FANOUT_CONSTRAINT": 6.5}, b))
          and not S.validate({"MAX_FANOUT_CONSTRAINT": 6}, b))
    check("type slips are repaired, values are not moved",
          S.coerce({"CTS_SINK_CLUSTERING_MAX_DIAMETER": 170.0, "PL_TIMING_DRIVEN": "true",
                    "GRT_ADJUSTMENT": 0.9}, b)
          == {"CTS_SINK_CLUSTERING_MAX_DIAMETER": 170, "PL_TIMING_DRIVEN": True,
              "GRT_ADJUSTMENT": 0.9})
    check("the kind of a layout is where its switches stand, unset meaning the default",
          S.kind_of({}) == S.kind_of({"PL_TIMING_DRIVEN": False, "GRT_ADJUSTMENT": 0.2})
          != S.kind_of({"PL_TIMING_DRIVEN": True}))
    check("a knob of a step the flow does not run is not offered",
          "GRT_RESIZER_HOLD_SLACK_MARGIN" not in S.ALLOWED_KEYS)
    mixed = S.blend({"PL_TARGET_DENSITY_PCT": 50},
                    {"PL_TARGET_DENSITY_PCT": 70, "GRT_ADJUSTMENT": 0.2}, "CTS")
    check("a CTS branch cannot change a placement knob",
          mixed == {"PL_TARGET_DENSITY_PCT": 50, "GRT_ADJUSTMENT": 0.2})
    check("a CTS node can only seed a GR branch", S.after("CTS") == ("GR",))
    check("the repair knobs take values inside their range",
          not S.validate({"MAX_FANOUT_CONSTRAINT": 8, "DESIGN_REPAIR_MAX_SLEW_PCT": 10.0}, b))
    check("the repair knobs refuse values outside it",
          bool(S.validate({"MAX_FANOUT_CONSTRAINT": 2}, b))
          and bool(S.validate({"DESIGN_REPAIR_MAX_SLEW_PCT": 90.0}, b)))
    check("a CTS branch cannot change a repair knob of placement",
          S.blend({"MAX_FANOUT_CONSTRAINT": 8}, {"MAX_FANOUT_CONSTRAINT": 16}, "CTS")
          == {"MAX_FANOUT_CONSTRAINT": 8})

    print("tree")
    tmp = Path(tempfile.mkdtemp(prefix="llm_pd_selftest_"))
    try:
        def snaps(stages):
            out = {}
            for s in stages:
                p = tmp / f"{len(list(tmp.iterdir()))}_{s}.json"
                p.write_text("{}")
                out[s] = str(p)
            return out

        t = Tree(40.0, weights=TIMING_ONLY)
        r0 = _res(-0.5); r0.stage_states = snaps(["PL", "CTS", "GR"])
        t.add(None, None, {}, r0)
        r1 = _res(0.3); r1.stage_states = snaps(["CTS", "GR", END])
        t.add("n0", "PL", {"PL_TARGET_DENSITY_PCT": 55}, r1)
        r2 = _res(0.1); r2.stage_states = snaps(["GR", END])
        t.add("n1", "CTS", {}, r2)
        t.add("n0", "CTS", {}, RunResult(False, 5.0, error="boom"))
        check("incumbent is the highest estimated score", t.incumbent() == "n1")
        check("the baseline's estimated score is exactly 1", t.est_score("n0") == 1.0)
        r4 = _res(2.0, hold=-0.05); r4.stage_states = snaps(["GR", END])
        t.add("n0", "CTS", {}, r4)
        check("a faster node with broken hold is not the incumbent", t.incumbent() == "n1")
        check("and the tree says why", "hold" in (t.why_not("n4") or ""))
        r5 = _res(1.5, power=0.12); r5.stage_states = snaps(["GR", END])
        t.add("n1", "CTS", {}, r5)
        check("with no power ceiling a power-hungry node can be the incumbent",
              t.incumbent() == "n5")
        t.power_ceiling = 1.10
        check("with a ceiling it cannot", t.incumbent() == "n1" and "power" in t.why_not("n5"))
        t.hold_floor = 0.2
        check("a hold floor above zero screens on the estimate",
              "n2" in t.valid() and t.hold("n2") >= 0.2)
        t.hold_floor = 0.5
        check("however high the floor, the baseline stays a candidate", t.valid() == ["n0"])
        t.hold_floor = 0.0
        check("history is best-so-far and rises",
              t.history()[:4] == [1.0, round(40.5 / 39.7, 4), round(40.5 / 39.7, 4),
                                  round(40.5 / 39.7, 4)])
        opts = t.branchable()
        check("a node offers only later stages",
              ("n1", "PL") not in opts and ("n1", "CTS") in opts and ("n2", "GR") in opts)
        check("a failed node offers nothing", not any(n == "n3" for n, _ in opts))
        check("END is never offered as a branch", not any(s == END for _, s in opts))
        s = t.summary()
        check("summary names the best node", s["best"]["id"] == "n1")
        check("a stage nobody branched at shows no branches",
              s["by_stage"]["GR"] == {"branches": 0, "candidates": 0, "best_is_behind_by": None})
        check("a stage that only produced unusable results says so",
              s["by_stage"]["CTS"]["branches"] == 4 and s["by_stage"]["CTS"]["candidates"] == 1)
        check("summary lists non-candidates with the reason",
              {x["id"] for x in s["not_candidates"]} == {"n4", "n5"})
        check("round trip through disk",
              Tree.load(_save(t, tmp)).summary() == s)

        print("score weights")
        w = Tree(40.0, weights=EVEN)
        w.add(None, None, {}, _res(-0.5))
        w.add("n0", "PL", {}, _res(1.4, cells=3.6e5))        # fast, 20 % more cell area
        w.add("n0", "PL", {}, _res(0.3))                     # slower, no more area
        check("with area weighted, speed bought with cells can lose", w.incumbent() == "n2")
        w.weights = TIMING_ONLY
        check("with timing alone it wins", w.incumbent() == "n1")
        w.weights = EVEN
        check("the estimated score is the formula",
              abs(w.est_score("n1") - (40.5 / 38.6) * (3.0e5 / 3.6e5) ** 0.5) < 1e-9)
        check("weights survive the round trip", Tree.load(_save(w, tmp)).weights == EVEN)

        print("kinds and what a signoff teaches")
        # Estimates of the "on" kind run slow and hungry next to their signoff;
        # the baseline's own estimate runs fast. Nothing tells the tree so until
        # one of them is signed off.
        on = {"PL_TIMING_DRIVEN": True}
        k = Tree(13.0, weights=EVEN)
        base = _res(1.5, power=0.20, cells=3.0e5, states=("PL",))
        base.signoff_metrics = {S.WS_KEY: -0.5, S.HOLD_KEY: 0.1, S.POWER_KEY: 0.30, S.AREA_KEY: 3.0e5}
        k.add(None, None, {}, base)
        k.add("n0", "PL", dict(on), _res(2.0, power=0.21, cells=3.3e5))
        k.add("n0", "PL", dict(on, PL_TARGET_DENSITY_PCT=60), _res(2.2, power=0.20, cells=3.3e5))
        k.add("n0", "PL", {"PL_TARGET_DENSITY_PCT": 60}, _res(1.6, power=0.20, cells=3.0e5))
        raw1 = (11.5 / 11.0) * (0.20 / 0.21) ** 0.5 * (3.0e5 / 3.3e5) ** 0.5
        check("before any signoff a kind's estimate is the raw one",
              abs(k.est_score("n1") - raw1) < 1e-9 and raw1 < 1.0 and not k.checked("n1"))
        check("the baseline's kind is checked from the start", k.checked("n3") and k.checked("n0"))
        check("an unchecked kind is reported as such, with its best node",
              [x["best"] for x in k.kinds() if not x["evaluated"]] == ["n2"])
        k.nodes["n1"].signoff_metrics = {S.WS_KEY: 1.9, S.HOLD_KEY: 0.2, S.POWER_KEY: 0.30,
                                         S.AREA_KEY: 3.3e5}
        real1 = (13.5 / 11.1) * (3.0e5 / 3.3e5) ** 0.5
        check("a signed-off node has a real score", abs(k.real_score("n1") - real1) < 1e-9)
        check("and its estimate, corrected by itself, now equals it",
              abs(k.est_score("n1") - real1) < 1e-9 and k.checked("n2"))
        want2 = real1 * (11.0 / 10.8) * (0.21 / 0.20) ** 0.5
        check("every other node of that kind is corrected by what it showed",
              abs(k.est_score("n2") - want2) < 1e-9 and want2 > real1 > 1.0)
        check("nodes of another kind are left alone",
              abs(k.est_score("n3") - 11.5 / 11.4) < 1e-9)
        seen = {x["kind"]: x for x in k.kinds()}
        check("a kind shows what each of its evaluations found against the raw estimate",
              seen["PL_TIMING_DRIVEN on"]["signoff_over_estimate"] == [round(real1 / raw1, 3)]
              and "one sample" in seen["PL_TIMING_DRIVEN on"]["estimates"])
        check("the baseline is not counted as evidence about its own kind",
              seen["PL_TIMING_DRIVEN off"]["signoff_over_estimate"] == [])
        check("the baseline is 1.0 whatever is learned", k.est_score("n0") == 1.0)
        check("what was learned survives the round trip",
              abs(Tree.load(_save(k, tmp)).est_score("n2") - want2) < 1e-12)
        k.nodes["n1"].signoff_metrics[S.HOLD_KEY] = -0.01
        check("a node that failed at signoff is not a candidate, whatever its estimate",
              "evaluated and failed" in (k.why_not("n1") or ""))
        check("weights are read as timing,power,die,area",
              parse_weights("1,0.5,0.2,0") == {"timing": 1.0, "power": 0.5, "die": 0.2, "area": 0.0})
        check("three weights are timing,power,area, with die area unscored",
              parse_weights("1,0.5,0") == {"timing": 1.0, "power": 0.5, "die": 0.0, "area": 0.0})
        try:
            parse_weights("0,0,0")
            check("all-zero weights are refused", False)
        except ValueError:
            check("all-zero weights are refused", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("budget and score")
    led = Ledger(max_flow_runs=5, max_usd=0.10)
    for _ in range(4):
        led.charge_run(10)
    check("one run is held back for signoff", led.search_runs_left == 0 and led.runs_left == 1)
    check("the search must stop, the score is not zeroed",
          led.must_stop() is not None and led.overspent() is None)
    led.charge_call("navigator", 0.03); led.charge_call("stage_agent", 0.05)
    check("cost is attributed per agent",
          led.by_agent()["navigator"]["usd"] == 0.03 and led.usd == 0.08)

    base = {S.WS_KEY: -0.5, S.HOLD_KEY: 0.2, "design__die__area": 1e6, S.POWER_KEY: 0.10,
            S.AREA_KEY: 3.0e5,
            "magic__drc_error__count": 0, "design__lvs_error__count": 0,
            "antenna__violating__nets": 0, "route__drc_errors": 0}
    good = dict(base, **{S.WS_KEY: 0.3})
    check("a clean faster result scores above 1",
          score(base, good, 40.0, led, EVEN)["score"] == round(40.5 / 39.7, 5))
    check("the untouched flow scores exactly 1 under any weights",
          score(base, base, 40.0, led, EVEN)["score"] == 1.0
          and merit(base, base, 40.0, {"timing": 0.3, "power": 2.0, "area": 1.0}) == 1.0)
    lean = dict(good, **{S.POWER_KEY: 0.09, S.AREA_KEY: 3.3e5})
    check("power and area enter the score by their weights",
          score(base, lean, 40.0, led, EVEN)["score"]
          == round((40.5 / 39.7) * (0.10 / 0.09) ** 0.5 * (3.0e5 / 3.3e5) ** 0.5, 5))
    check("timing-only weights give the clock-period ratio alone",
          score(base, lean, 40.0, led, TIMING_ONLY)["score"] == round(40.5 / 39.7, 5))
    check("the report says what each quantity did",
          score(base, lean, 40.0, led, EVEN)["vs_baseline"]
          == {"effective clock period": round(39.7 / 40.5, 4), "total power": 0.9,
              "cell area": 1.1, "die area": 1.0})
    check("a weighted quantity that is not reported zeroes the score",
          score(base, {k: v for k, v in good.items() if k != S.AREA_KEY},
                40.0, led, EVEN)["score"] == 0.0)
    check("a DRC error zeroes the score",
          score(base, dict(good, magic__drc_error__count=2), 40.0, led)["score"] == 0.0)
    check("power over the tolerance zeroes the score, however fast",
          score(base, dict(good, **{S.WS_KEY: 5.0, S.POWER_KEY: 0.106}), 40.0, led)["score"] == 0.0)
    check("die area over the tolerance zeroes the score",
          score(base, dict(good, design__die__area=1.2e6), 40.0, led)["score"] == 0.0)
    check("a hold violation zeroes the score",
          score(base, dict(good, **{S.HOLD_KEY: -0.01}), 40.0, led)["score"] == 0.0)
    check("a missing check counts as a failure",
          score(base, {k: v for k, v in good.items() if k != "design__lvs_error__count"},
                40.0, led)["score"] == 0.0)
    led.charge_run(10); led.charge_run(10)
    check("overrunning the flow budget zeroes the score",
          score(base, good, 40.0, led)["score"] == 0.0)
    check("a run with no model has no dollar limit",
          Ledger(max_flow_runs=3, max_usd=None).must_stop() is None)
    ld = Ledger(max_flow_runs=20, max_usd=1.00)
    for _ in range(10):
        ld.charge_run(10)
    ld.charge_call("stage_agent", 0.85)                   # $0.085 a run, $0.15 left
    check("the search goes on while the dollars left cover another move", ld.must_stop() is None)
    ld.charge_call("stage_agent", 0.05)                   # $0.09 a run, $0.10 left
    check("and stops before the last move could overshoot the cap",
          "dollar" in (ld.must_stop() or "") and ld.overspent() is None)


def renames() -> None:
    """The judge became the navigator and the critic the stop agent, and the
    move called signoff became evaluate. Runs saved before that, and policy/prompts/views
    files written before it, must still be read."""
    from types import SimpleNamespace
    from . import names
    print("old names")
    tmp = Path(tempfile.mkdtemp(prefix="llm_pd_names_"))
    try:
        (tmp / "report.json").write_text(json.dumps({
            "judge_corrections": 2, "stop_policy": "critic",
            "models": {"judge": "m1", "critic": "m2"},
            "cost": {"usd_by_agent": {"judge": {"usd": 0.1}, "critic": {"usd": 0.2}}},
            "stop_decisions": [{"critic_says_stop": True, "critic_reason": "flat"}],
            "signoff_attempts": [{"node": "n3", "when": "search", "signoff": {"score": 1.1}}],
            "search": {"signoffs_during_search": 1, "signoffs_at_the_end": 2},
            "kinds": [{"kind": "k", "signed_off": 2, "signoff_over_estimate": [1.02]}]}))
        (tmp / "ledger.json").write_text(json.dumps({
            "calls": [{"n": 1, "agent": "judge", "usd": 0.1}, {"n": 2, "agent": "critic", "usd": 0.2}],
            "decisions": [{"critic_says_stop": False, "critic_reason": ""}],
            "by_agent": {"judge": {"usd": 0.1}}}))
        (tmp / "trace.jsonl").write_text('{"n": 1, "agent": "judge"}\n{"n": 2, "agent": "critic"}\n')
        rep = names.load_report(tmp / "report.json")
        check("an old report reads under the new names",
              rep.get("navigator_corrections") == 2 and rep["stop_policy"] == "agent"
              and set(rep["models"]) == {"navigator", "stop_agent"}
              and set(rep["cost"]["usd_by_agent"]) == {"navigator", "stop_agent"}
              and rep["stop_decisions"][0] == {"stop_agent_says_stop": True,
                                               "stop_agent_reason": "flat"}
              and rep["evaluations"][0]["signoff"] == {"score": 1.1}
              and rep["search"] == {"evaluations_during_search": 1, "evaluations_at_the_end": 2}
              and rep["kinds"][0] == {"kind": "k", "evaluated": 2, "signoff_over_estimate": [1.02]},
              json.dumps(rep))
        check("the move is evaluate, and its old name means the same",
              [names.move(a) for a in ("evaluate", "signoff", " Sign_Off ", "sign off", "branch")]
              == ["evaluate", "evaluate", "evaluate", "evaluate", "branch"])
        led = names.load_ledger(tmp / "ledger.json")
        check("an old ledger and trace read under the new names",
              [c["agent"] for c in led["calls"]] == ["navigator", "stop_agent"]
              and "stop_agent_says_stop" in led["decisions"][0] and "navigator" in led["by_agent"]
              and [c["agent"] for c in names.load_trace(tmp / "trace.jsonl")]
              == ["navigator", "stop_agent"])
        before = (tmp / "report.json").read_text()
        names.load_report(tmp / "report.json")
        check("reading an old run leaves its files as they were",
              (tmp / "report.json").read_text() == before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    try:
        from agents import compat
    except ImportError as e:            # pydantic missing: outside the venv
        check("policy, prompts and views with the old names are accepted", False, f"{e}")
        return
    policy = SimpleNamespace(ROLE_MODEL={"judge": "a", "stage_agent": "b", "critic": "c"},
                             STOP_POLICY="critic")
    prompts = SimpleNamespace(JUDGE="j", CRITIC="c", JudgeDecision=dict)
    views = SimpleNamespace(judge_view=len, critic_view=str)
    import contextlib
    import io
    said = io.StringIO()
    with contextlib.redirect_stderr(said):
        compat.adopt(policy, prompts, views)
    check("each old name is warned about, in one line",
          len(said.getvalue().splitlines()) == 8
          and all(line.startswith("  deprecated: ") for line in said.getvalue().splitlines()),
          said.getvalue())
    check("policy, prompts and views with the old names are accepted",
          list(policy.ROLE_MODEL) == ["navigator", "stage_agent", "stop_agent"]
          and policy.STOP_POLICY == "agent"
          and prompts.NAVIGATOR == "j" and prompts.STOP_AGENT == "c"
          and prompts.NavigatorDecision is dict
          and views.navigator_view is len and views.stop_view is str)
    new = SimpleNamespace(ROLE_MODEL={"judge": "old", "navigator": "new"}, STOP_POLICY="rule")
    with contextlib.redirect_stderr(io.StringIO()):
        compat.adopt(new, SimpleNamespace(), SimpleNamespace())
    check("where both names are given, the new one wins",
          new.ROLE_MODEL == {"navigator": "new"} and new.STOP_POLICY == "rule")


def digest() -> None:
    """What a stage agent reads has to be the part of a log that differs from
    run to run, not the part that is the same every time."""
    from . import runner
    print("log digest")
    log = "\n".join(
        ["Reading design at '/tmp/x/y.odb'…", "[INFO] Setting timing derate to: 5%",
         "+ repair_timing -verbose -setup -setup_margin 0.05000000000000000277 -max_buffer_percent 50",
         "[INFO RSZ-0094] Found 814 endpoints with setup violations.",
         "   Iter   | Resized |    WNS   | Viol"]
        + [f"   {i:5d} |    {i:4d} |  {-25 + i / 10:7.3f} |  814" for i in range(0, 300, 10)]
        + ["[WARNING RSZ-0062] Unable to repair all setup violations.",
           "Cell type report:                       Count       Area",
           "  Tap cell                               6227   27339.02",
           "  Total                                 16914  374070.86"])
    out = runner._boil(log)
    rows = [l for l in out if runner._ROW.match(l)]
    check("an iteration table is cut to its first and last row",
          len(rows) == 2 and rows[0].split("|")[0].strip() == "0"
          and rows[1].split("|")[0].strip() == "290")
    check("what the tool concluded is kept", any("RSZ-0062" in l for l in out)
          and any("814 endpoints" in l for l in out))
    check("boilerplate and the cell census are dropped",
          not any(("Tap cell" in l) or ("Reading" in l) or ("Setting" in l) for l in out))
    check("a float is not printed to fifty places", any("-setup_margin 0.0500 " in l for l in out))


def signoff() -> None:
    """How the answer is chosen, with the flow replaced by canned numbers."""
    from . import episode as E
    from .ledger import MAX_SIGNOFFS
    print("signoff")
    tmp = Path(tempfile.mkdtemp(prefix="llm_pd_selftest_"))
    real = E.runner.signoff
    clean = {"magic__drc_error__count": 0, "design__lvs_error__count": 0,
             "antenna__violating__nets": 0, "route__drc_errors": 0, "design__die__area": 1e6}
    base = dict(clean, **{S.WS_KEY: -0.5, S.HOLD_KEY: 0.07, S.POWER_KEY: 0.30, S.AREA_KEY: 3.0e5})

    def at_signoff(ws, power=0.30, hold=0.10, cells=3.0e5):
        return dict(clean, **{S.WS_KEY: ws, S.HOLD_KEY: hold, S.POWER_KEY: power,
                              S.AREA_KEY: cells})

    spread = ((2.6, 0.210), (2.5, 0.211), (2.4, 0.212), (2.3, 0.213), (2.2, 0.214))
    twins = ((2.6, 0.210), (2.6, 0.210), (2.4, 0.212), (2.3, 0.213), (2.2, 0.214))

    def episode(runs_left: int, results: dict, estimates=spread, params=None):
        t = Tree(13.0, hold_floor=0.20, power_ceiling=1.20, weights=EVEN)
        est = {S.WS_KEY: 1.5, S.HOLD_KEY: 0.34, S.POWER_KEY: 0.20, S.AREA_KEY: 2.9e5}
        t.add(None, None, {}, RunResult(True, 100.0, est, dict(base)))
        for ws, power in estimates:          # n1 .. n5, best estimate first
            end = tmp / f"end{len(t.order)}.json"
            end.write_text("{}")
            t.add("n0", "PL", dict(params or {}), RunResult(
                True, 10.0, {S.WS_KEY: ws, S.HOLD_KEY: 0.37, S.POWER_KEY: power,
                             S.AREA_KEY: 2.9e5},
                {}, {END: str(end)}))
        led = Ledger(max_flow_runs=20, max_usd=None)
        led.flow_runs = 20 - runs_left
        E.runner.signoff = lambda design, end, params, run_dir, keep="final": RunResult(
            True, 50.0, results[Path(run_dir).name], results[Path(run_dir).name])
        return E.Episode(tmp, tmp, 13.0, t, led)

    def run(runs_left: int, results: dict, estimates=spread) -> dict:
        return episode(runs_left, results, estimates).finish()

    def made(rep, when=None):
        return [a["node"] for a in rep["evaluations"]
                if "seconds" in a and when in (None, a["when"])]

    try:
        rep = run(1, {"n1": at_signoff(2.0, power=0.33)})
        check("one run left and the candidate fails: the baseline is the answer",
              rep["final_node"] == "n0" and rep["fell_back_to_baseline"]
              and rep["score"]["score"] == 1.0)
        rep = run(3, {"n1": at_signoff(2.0, power=0.33), "n2": at_signoff(1.8),
                      "n3": at_signoff(1.9)})
        check("the answer is the best at signoff, not the best estimate",
              rep["final_node"] == "n3" and not rep["fell_back_to_baseline"])
        rep = run(3, {"n1": at_signoff(2.0, power=0.33), "n2": at_signoff(2.0, cells=3.9e5),
                      "n3": at_signoff(1.8)})
        check("and best means the score: the faster layout loses if its cells cost more",
              rep["final_node"] == "n3"
              and rep["score"]["score"] == round(13.5 / 11.2, 5))
        rep = run(3, {"n1": at_signoff(-0.4, cells=3.9e5), "n2": at_signoff(-0.6),
                      "n3": at_signoff(-0.7)})
        check("clean evaluations that score no better than the baseline are not the answer",
              rep["final_node"] == "n0" and rep["fell_back_to_baseline"])
        every = {f"n{i}": at_signoff(2.0 - i / 10) for i in range(1, 6)}
        rep = run(9, every)
        check("however many runs are left, the evaluations made at the end are capped",
              made(rep) == ["n1", "n2", "n3"] and rep["cost"]["flow_runs"] == 11 + MAX_SIGNOFFS)
        rep = run(9, every, twins)
        check("a node with the same estimates as one already tried is skipped",
              made(rep) == ["n1", "n3", "n4"]
              and any("skipped" in a["outcome"] for a in rep["evaluations"]))
        check("every attempt records the estimate next to what signoff found",
              all(set(a["estimate"]) - {"score_est"} == set(a["signoff"]) - {"score"}
                  for a in rep["evaluations"] if "seconds" in a))

        print("evaluation during the search")
        ep = episode(9, every)
        check("the budget says how many candidates are waiting for an evaluation",
              ep.budget()["candidates_waiting_for_evaluation"] == len(ep.waiting()) == 5
              and ep.budget()["flow_runs_left_for_search"] == ep.ledger.search_runs_left)
        old = ep.budget()
        check("a stopping rule written for the old key still reads it, and no agent sees it",
              old["candidates_waiting_for_signoff"] == old.get("candidates_waiting_for_signoff") == 5
              and "candidates_waiting_for_signoff" in old
              and "candidates_waiting_for_signoff" not in json.dumps(old))
        rec = ep.sign_off("n4")
        check("and a signed-off node, with all it now puts behind it, stops waiting",
              "n4" not in ep.waiting() and 0 < len(ep.waiting()) < 5)
        check("a search may evaluate a node whenever it has a run to spend",
              rec["outcome"] == "passed" and rec["when"] == "search"
              and ep.ledger.flow_runs == 12 and ep.tree.signed_off("n4"))
        check("it then knows what it would hand in if it stopped",
              ep.best_evaluated() == ("n4", 13.5 / 11.4))
        again = ep.sign_off("n4")
        check("signing the same node off twice is refused before anything runs",
              "refused" in again["outcome"] and ep.ledger.flow_runs == 12)
        rep = ep.finish()
        check("the end does not repeat it, and only tries what the estimate puts above it",
              made(rep, "search") == ["n4"] and made(rep, "end") == ["n1", "n2", "n3"]
              and rep["final_node"] == "n1"
              and rep["search"]["evaluations_during_search"] == 1)

        # A kind whose raw estimate says "worse than the baseline" and whose
        # signoff says "much better": nothing but a signoff during the search
        # can find that out.
        slow = ((1.2, 0.215), (1.3, 0.215), (1.25, 0.215), (1.1, 0.215), (1.0, 0.215))
        truth = {f"n{i}": at_signoff(2.0 + i / 10) for i in range(1, 6)}
        rep = episode(9, truth, slow, {"PL_TIMING_DRIVEN": True}).finish()
        check("left to its estimates, a search hands in the baseline",
              rep["final_node"] == "n0" and made(rep) == [] and not rep["fell_back_to_baseline"])
        ep = episode(9, truth, slow, {"PL_TIMING_DRIVEN": True})
        before = ep.tree.est_score("n2")
        rec = ep.sign_off("n1")
        check("one signoff of that kind corrects the rest of it",
              before < 1.0 < ep.tree.est_score("n2") and not rec["kind_already_checked"])
        rep = ep.finish()
        check("and the search then finds what was there all along",
              rep["final_node"] in ("n2", "n3", "n1") and rep["score"]["score"] > 1.2
              and [k for k in rep["kinds"] if k["kind"].endswith("on")][0]["correction"]["timing"] < 1)
    finally:
        E.runner.signoff = real
        shutil.rmtree(tmp, ignore_errors=True)


def cache() -> None:
    """The remembered baseline: the fingerprint follows the design's files, and
    a stored entry is returned without anything being run."""
    import json
    from . import runner
    print("baseline cache")
    tmp = Path(tempfile.mkdtemp(prefix="llm_pd_selftest_"))
    saved = {k: os.environ.get(k) for k in ("LLM_PD_CACHE", "LLM_PD_NO_CACHE")}
    try:
        design = tmp / "toy"
        (design / "src").mkdir(parents=True)
        (design / "config.yaml").write_text("CLOCK_PERIOD: 10\n")
        (design / "src" / "toy.v").write_text("module toy; endmodule\n")
        k1 = runner.baseline_key(design)
        check("the fingerprint is stable", runner.baseline_key(design) == k1)
        (design / "config.yaml").write_text("CLOCK_PERIOD: 9\n")
        k2 = runner.baseline_key(design)
        check("a changed config is a different baseline", k2 != k1)
        check("the same design run with an override is remembered apart",
              runner.baseline_key(design, {"CLOCK_PERIOD": 8}) != k2)

        os.environ["LLM_PD_CACHE"] = str(tmp / "cache")
        os.environ.pop("LLM_PD_NO_CACHE", None)
        home = tmp / "cache" / "baseline" / f"toy-{k2}"
        home.mkdir(parents=True)
        snap = home / "PL.json"
        snap.write_text("{}")
        (home / "result.json").write_text(json.dumps({
            "seconds": 123.0, "metrics": {S.WS_KEY: 1.0}, "signoff_metrics": {S.WS_KEY: -0.5},
            "stage_states": {"PL": str(snap)}, "digests": {}}))
        r = runner.baseline_cached(design, tmp / "run", tmp / "store")
        check("a stored baseline is returned without running anything",
              r.ok and r.from_cache and r.shared and r.seconds == 123.0)
        check("nothing was launched for it", not (tmp / "run").exists())
        lock = tmp / "cache" / "baseline" / "x.building"
        check("one process builds an entry at a time",
              runner._claim(lock) and not runner._claim(lock))
        (lock / "pid").write_text("999999999")
        check("a claim left by a dead process is taken over", runner._claim(lock))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)


def _save(tree: Tree, tmp: Path) -> Path:
    p = tmp / "tree.json"
    tree.save(p)
    return p


def gate_8mhz() -> None:
    """The BLE TX scoring: power and area only, setup slack as a pass/fail gate."""
    print("8 MHz gate")
    led = Ledger(max_flow_runs=20, max_usd=None)
    clean = {"magic__drc_error__count": 0, "design__lvs_error__count": 0,
             "antenna__violating__nets": 0, "route__drc_errors": 0}
    base = {S.WS_KEY: 90.0, S.WS_WORST_KEY: 60.0, S.HOLD_KEY: 0.2, "design__die__area": 1e6,
            S.POWER_KEY: 0.010, S.AREA_KEY: 5.0e4, **clean}
    check("timing carries no weight by default", L.WEIGHTS["timing"] == 0.0)
    lean = dict(base, **{S.WS_KEY: 70.0, S.POWER_KEY: 0.009, S.AREA_KEY: 4.5e4})
    check("a slower layout that still meets 8 MHz scores on power and area alone",
          score(base, lean, 125.0, led)["score"]
          == round((0.010 / 0.009) ** L.WEIGHTS["power"]
                   * (5.0e4 / 4.5e4) ** L.WEIGHTS["area"], 5))
    check("negative setup slack at tt fails the gate",
          score(base, dict(lean, **{S.WS_KEY: -0.1}), 125.0, led)["score"] == 0.0)
    check("negative setup slack at the worst corner fails the gate",
          score(base, dict(lean, **{S.WS_WORST_KEY: -0.1}), 125.0, led)["score"] == 0.0)
    t = Tree(125.0, hold_floor=0.0, power_ceiling=1.05)
    t.add(None, None, {}, RunResult(True, 1.0, base, {}))
    t.add("n0", "PL", {}, RunResult(True, 1.0, dict(lean, **{S.WS_WORST_KEY: -0.2}), {}))
    t.add("n0", "PL", {}, RunResult(True, 1.0, lean, {}))
    check("an estimate that misses 8 MHz is not a candidate",
          "setup slack" in (t.why_not("n1") or "") and t.why_not("n2") is None)

    # Loosening the repair saves area by leaving violations behind, and the baseline
    # already has some at the slow corner, so the rule is none, at the typical and slow corners.
    tt_s, tt_c, ss_s, ss_c, mx_s, mx_c = (key for key, _ in L.ELECTRICAL)
    clean = dict(lean, **{k: 0 for k, _ in L.ELECTRICAL})
    dirty = dict(base, **{ss_s: 14, mx_s: 30, mx_c: 1})          # the baseline at signoff
    check("a result with no slew or capacitance violations passes the gate",
          L.gate(dirty, clean) == [])
    check("a slow-corner slew violation fails it, even if the baseline had more",
          any("max-slew" in r and "max_ss" in r for r in L.gate(dirty, dict(clean, **{mx_s: 2}))))
    check("a typical-corner capacitance violation fails it",
          any("max-capacitance" in r for r in L.gate(dirty, dict(clean, **{tt_c: 1}))))
    check("the baseline itself does not meet the rule", bool(L.electrical_problems(dirty)))
    check("counts that are not reported are not checked", L.gate(base, lean) == [])
    te = Tree(125.0, hold_floor=0.0, power_ceiling=1.05)
    te.add(None, None, {}, RunResult(True, 1.0, dirty, {}))
    te.add("n0", "PL", {}, RunResult(True, 1.0, dict(clean, **{tt_c: 2}), {}))
    te.add("n0", "PL", {}, RunResult(True, 1.0, clean, {}))
    te.add("n0", "PL", {}, RunResult(True, 1.0, dict(clean, **{ss_s: 1284}), {}))
    check("an estimate with typical-corner violations is not a candidate",
          "max-capacitance" in (te.why_not("n1") or "") and te.why_not("n2") is None)
    check("an estimate's slow-corner count is ignored, because only signoff reads it",
          te.why_not("n3") is None)

    # A failure at one fanout limit and slew margin predicts failure at a limit at least as
    # high with a margin no larger, because the estimates cannot see the violations that
    # signoff finds. Only a signoff that upsized drivers counts (it reports eco__passes):
    # the baseline's own signoff does not, so its violations predict nothing.
    fo, mg = "MAX_FANOUT_CONSTRAINT", "DESIGN_REPAIR_MAX_SLEW_PCT"
    tf = Tree(125.0, hold_floor=0.0, power_ceiling=1.05)
    tf.add(None, None, {}, RunResult(True, 1.0, dirty, {}))
    tf.nodes["n0"].signoff_metrics = dirty
    for params in ({fo: 8, mg: 50}, {fo: 10, mg: 50}, {fo: 8, mg: 40}, {fo: 6, mg: 50},
                   {fo: 8, mg: 55}, {fo: 4, mg: 30}, {fo: 4, mg: 45}, {}):
        tf.add("n0", "PL", params, RunResult(True, 1.0, clean, {}))
    tf.nodes["n1"].signoff_metrics = dict(lean, **{mx_s: 85, "eco__passes": 3})   # (8, 50) failed
    check("signoff outcomes reach the stage agent through tried()",
          "failed" in next(r for r in tf.tried("PL", limit=20)
                           if r["params"] == {fo: 8, mg: 50}).get("signoff", ""))
    check("a looser fanout limit at the same margin is predicted to fail",
          "no safer" in (tf.why_not("n2") or ""))
    check("the same fanout limit with a smaller margin is predicted to fail",
          "no safer" in (tf.why_not("n3") or ""))
    check("a tighter fanout limit, or a larger margin, is not predicted to fail",
          tf.why_not("n4") is None and tf.why_not("n5") is None)
    check("the baseline's signoff, which fixes nothing, predicts nothing",
          tf.why_not("n6") is None and tf.why_not("n8") is None and tf.why_not("n7") is None)
    tf.nodes["n4"].signoff_metrics = dict(lean, **{mx_s: 2})            # (6, 50), no fix run
    tf.add("n0", "PL", {fo: 6, mg: 45}, RunResult(True, 1.0, clean, {}))  # n9
    check("nor does any other signoff without the fix",
          "no safer" not in (tf.why_not("n9") or ""))

    from agents import policy as P
    flat = [1.0] * (P.PATIENCE + 3)
    check("a search that has found nothing legal is not stopped as stalled",
          not P.should_stop(flat, {"flow_runs_left_for_search": 10,
                                   "candidates_waiting_for_evaluation": 3})[0])
    check("a search that found something and then went flat is",
          P.should_stop([1.0, 1.2] + [1.2] * (P.PATIENCE + 1),
                        {"flow_runs_left_for_search": 10,
                         "candidates_waiting_for_evaluation": 3})[0])


def environment() -> None:
    print("environment")
    from . import runner, apikey
    runner._ensure_path()
    for tool in ("librelane", "openroad", "sta", "yosys", "verilator", "magic", "netgen", "klayout"):
        check(f"{tool} on PATH", shutil.which(tool) is not None)
    sta = shutil.which("sta") or ""
    check("the sta that matches LibreLane comes first", "openroad-librelane" in os.path.realpath(sta),
          f"found {sta}")
    check("PDK gf180mcuD is installed", Path("/foss/pdks/gf180mcuD/libs.ref").is_dir())
    try:
        import librelane
        check("librelane imports", True)
    except Exception as e:                                   # noqa: BLE001
        check("librelane imports", False, str(e))
    try:
        import google.adk, litellm                           # noqa: F401
        from google.adk.workflow import Workflow             # noqa: F401
        check("google-adk with Workflow, and litellm", True)
    except Exception as e:                                   # noqa: BLE001
        check("google-adk with Workflow, and litellm", False,
              f"{e} — use the venv: ./venv/bin/python -m pd.selftest --env")
    print(f"  key   {apikey.source()}  {apikey.masked() if apikey.load(required=False) else ''}")


def floorplan() -> None:
    """The die-width knob: its range, how it reaches LibreLane, where it may branch."""
    print("floorplan")
    from . import runner
    from .episode import Episode
    facts = S.FloorplanFacts(die_w=1400, die_h=300, core_w=1386.56, core_h=266.56,
                             cells=54487.0, tap_share=0.0291)
    check("the baseline's width predicts the baseline's utilisation",
          abs(facts.utilisation(1400) - (54487 / (1386.56 * 266.56) + 0.0291)) < 1e-9)
    lo = facts.narrowest()
    check("the narrowest width is where the density floor reaches its cap",
          S.density_floor(facts.utilisation(lo)) <= S.DENSITY_FLOOR_CAP
          and facts.utilisation(lo) + S.DENSITY_FLOOR_STEP / 100 <= S.DENSITY_FLOOR_CAP / 100
          and facts.utilisation(lo - 1) + S.DENSITY_FLOOR_STEP / 100 > S.DENSITY_FLOOR_CAP / 100)
    b = S.bounds_for(facts=facts, width=400)
    check("the width runs from that floor to the baseline's",
          (b[S.WIDTH].lo, b[S.WIDTH].hi) == (lo, 1400) and bool(S.validate({S.WIDTH: lo - 1}, b)))
    check("the density floor follows the width",
          b[S.DENSITY].lo == S.density_floor(facts.utilisation(400))
          > S.bounds_for(facts=facts)[S.DENSITY].lo)
    check("the width reaches LibreLane as DIE_AREA at the config's height",
          S.to_librelane({S.WIDTH: 330, "GRT_ADJUSTMENT": 0.2}, 300.0)
          == {"GRT_ADJUSTMENT": 0.2, "DIE_AREA": "0 0 330 300"})
    check("without a width the settings pass through", S.to_librelane({"A": 1}, 300.0) == {"A": 1})
    check("the die height is read from config.yaml",
          runner.die_height(Path(__file__).parents[1] / "designs" / "ble_tx") == 300.0)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        def snaps(stages):
            out = {}
            for s in stages:
                p = tmp / f"{len(list(tmp.iterdir()))}_{s}.json"
                p.write_text("{}")
                out[s] = str(p)
            return out

        t = Tree(125.0)
        r0 = _res(5.0); r0.stage_states = snaps(["FP", "PL", "CTS", "GR"])
        t.add(None, None, {}, r0)
        t.facts = facts
        r1 = _res(5.0); r1.stage_states = snaps(["GR", END])
        t.add("n0", "CTS", {}, r1)
        r2 = _res(5.0); r2.stage_states = snaps(["PL", "CTS", "GR", END])
        t.add("n0", "FP", {S.WIDTH: 400}, r2)
        opts = t.branchable()
        check("the floorplan is offered from every finished node",
              {("n0", "FP"), ("n1", "FP"), ("n2", "FP")} <= set(opts)
              and sum(1 for o in opts if o == ("n0", "FP")) == 1)
        check("a floorplan branch resumes from the baseline's netlist",
              t.state_for("n1", "FP") == r0.stage_states["FP"])
        check("a node's width is its own setting, else the baseline's",
              (t.width("n2"), t.width("n1")) == (400.0, 1400.0))
        check("a node's density floor follows its width",
              t.bounds("n2")[S.DENSITY].lo == S.density_floor(facts.utilisation(400)))
        check("a floorplan branch keeps the node's settings for later stages",
              S.blend({"MAX_FANOUT_CONSTRAINT": 9}, {S.WIDTH: 350}, "FP")
              == {"MAX_FANOUT_CONSTRAINT": 9, S.WIDTH: 350})
        check("the floorplan facts survive the round trip", Tree.load(_save(t, tmp)).facts == facts)

        ep = Episode(tmp, tmp, 125.0, t, Ledger())
        p = {S.WIDTH: 330, S.DENSITY: 50}
        ep._raise_density(p)
        check("a floorplan branch raises a density below the new width's floor",
              p[S.DENSITY] == S.density_floor(facts.utilisation(330)))
        p = {S.WIDTH: 1000, S.DENSITY: 70}
        ep._raise_density(p)
        check("and never lowers one", p[S.DENSITY] == 70)


if __name__ == "__main__":
    gate_8mhz()
    # The framework checks below were written for a design scored on
    # timing with a baseline that misses its clock: run them with that
    # setup handling (no gate) so they keep testing the plumbing.
    L.SETUP_FLOOR_NS = None
    logic()
    floorplan()
    signoff()
    digest()
    cache()
    renames()
    if "--env" in sys.argv:
        environment()
    print()
    if _FAILED:
        print(f"  {len(_FAILED)} check(s) failed: {', '.join(_FAILED)}")
        sys.exit(1)
    print("  all checks passed")
