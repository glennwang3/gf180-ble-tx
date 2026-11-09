"""The graph and the command line.

    python -m agents.graph --offline          dry run: fake model, real LibreLane, no spend
    python -m agents.graph --runs 20 --usd 1  the real thing; needs an OpenRouter key

The loop is one routed edge pointing backwards (gate -> navigator_view). That is
how a cycle is written in ADK 2.11 without the deprecated LoopAgent.

    START -> baseline -> navigator_view -> [navigator] -> plan
    plan  -- branch --> [stage agent] -> apply
    plan  -- evaluate -> sign_off ------------> stop_view
    apply -- ok ------------------------------> stop_view
    apply -- refused -------------------------> stop_view
    apply -- failed --> [diagnostician] ------> stop_view
    stop_view -> [stop agent] -> gate -- continue --> navigator_view
                                 gate -- stop ------> finish

Bracketed nodes are the four LLM agents.
"""
from __future__ import annotations

import argparse
import asyncio
import functools
import json
import logging
import sys
import time
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
say = functools.partial(print, flush=True)     # progress should not sit in a buffer


def build(ledger, offline_port: int | None = None):
    from google.adk.workflow import Workflow, Edge, START
    from . import models, nodes as N

    def model(role):
        return models.model_for(role, ledger, offline_port)

    navigator = N.make_navigator(model("navigator"))
    stage_agent = N.make_stage_agent(model("stage_agent"))
    diagnostician = N.make_diagnostician(model("diagnostician"))
    stop_agent = N.make_stop_agent(model("stop_agent"))

    return Workflow(
        name="llm_pd",
        state_schema=N.LoopState,
        max_concurrency=1,              # one LibreLane run at a time
        edges=[
            (START, N.baseline),
            (N.baseline, N.navigator_view),
            (N.navigator_view, navigator),
            (navigator, N.plan),
            Edge(from_node=N.plan, to_node=stage_agent, route="branch"),
            Edge(from_node=N.plan, to_node=N.sign_off, route="evaluate"),
            (N.sign_off, N.stop_view),
            (stage_agent, N.apply),
            Edge(from_node=N.apply, to_node=N.stop_view, route="ok"),
            Edge(from_node=N.apply, to_node=N.stop_view, route="refused"),
            Edge(from_node=N.apply, to_node=diagnostician, route="failed"),
            (diagnostician, N.stop_view),
            (N.stop_view, stop_agent),
            (stop_agent, N.gate),
            Edge(from_node=N.gate, to_node=N.navigator_view, route="continue"),   # the loop
            Edge(from_node=N.gate, to_node=N.finish, route="stop"),
        ],
    )


async def run(design, work, clock_ns, runs=20, usd=1.0, offline_port=None,
              stop_policy=None, seed=0, log=say, weights=None) -> dict:
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from pd import apikey
    from pd.ledger import Ledger, WEIGHTS
    from . import compat, models, nodes as N

    stop_policy = compat.stop_policy(stop_policy)
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(max_flow_runs=runs, max_usd=usd, trace=work / "trace.jsonl")
    ledger.trace.unlink(missing_ok=True)        # a trace is of one run
    N.configure(design=str(Path(design).resolve()), work=str(work), clock_ns=clock_ns,
                ledger=ledger, stop_policy=stop_policy, seed=seed, log=log, weights=weights)
    wf = build(ledger, offline_port)

    log(f"  design  {design}")
    log(f"  work    {work}")
    log(f"  budget  {runs} flow runs (baseline and evaluations included), ${usd:.2f}")
    log(f"  weights {weights or WEIGHTS}")
    log(f"  key     {'offline mock on port %d' % offline_port if offline_port else apikey.masked()}")
    log(f"  models\n{models.describe()}")
    from .compat import policy
    log(f"  candidates need estimated hold slack >= {policy.HOLD_FLOOR_NS:g} ns"
        + (f" and estimated power <= {policy.POWER_CEILING:g}x baseline"
           if policy.POWER_CEILING else "; estimated power is not checked"))
    log("  " + "-" * 70)

    runner = InMemoryRunner(agent=wf, app_name="llm_pd")
    sess = await runner.session_service.create_session(app_name="llm_pd", user_id="ta")
    failure = None
    try:
        async for _ in runner.run_async(
            user_id="ta", session_id=sess.id,
            new_message=types.Content(role="user", parts=[types.Part(text="begin")]),
        ):
            pass
    except Exception as e:                      # a model or network error mid-search
        failure = apikey.scrub(f"{type(e).__name__}: {e}")[:600]
        log(f"  !! the agent loop stopped early: {failure}")

    report_path = work / "report.json"
    ep = N.current_episode()
    if ep is not None and (failure or not report_path.exists()):
        # Whatever happened, evaluate the best thing found so the run still
        # ends with a scored result.
        log("  evaluations at the end (after an early stop) ...")
        from .compat import policy
        ep.finish({"method": "agent", "models": dict(policy.ROLE_MODEL), "aborted": failure})
    return json.loads(report_path.read_text()) if report_path.exists() else {"error": failure}


def summarise(rep: dict) -> str:
    if "score" not in rep:
        return json.dumps(rep, indent=1)
    from pd import names
    from pd.episode import results_table
    rep = names.report(rep)
    s, c, q = rep["score"], rep["cost"], rep["search"]
    lines = [
        "  " + "=" * 70,
        f"  score               {s['score']}"
        + (f"   (zeroed: {'; '.join(s['zeroed_because'])})" if s["zeroed_because"] else ""),
        f"  weights             {s['weights']}",
        f"  vs baseline         {s['vs_baseline']}   (below 1 is better)",
        f"  ECP at signoff      {s['baseline_ecp_ns']} -> {s['final_ecp_ns']} ns"
        f"   setup slack {s['final_setup_slack_ns']} ns   final node {rep['final_node']}"
        + ("   (fell back to the baseline)" if rep.get("fell_back_to_baseline") else ""),
        f"  hold at signoff     {s['final_hold_slack_ns']} ns at tt"
        f"   (worst corner {s['final_worst_corner_hold_ns']})",
        "  every node, as estimated and as signed off; x base is the ratio to the baseline",
        results_table(rep),
        f"  runs                {q['runs']} ({q['failed']} failed, {q['refused_proposals']} refused)"
        f"   by stage {q['branches_by_stage']}",
        f"  evaluations         {q['evaluations_during_search']} during the search, "
        f"{q['evaluations_at_the_end']} at the end",
        f"  cost                {c['flow_runs']}/{c['flow_run_budget']} flow runs, "
        f"{c['flow_minutes']} flow-min, {c['wall_minutes']} wall-min, ${c['usd']:.4f}",
    ]
    roles = rep.get("models") or {}
    for a, v in (c.get("usd_by_agent") or {}).items():
        model = ", ".join(v.get("models") or [roles.get(a, "")]).replace("openrouter/", "")
        lines.append(f"    {a:14s} ${v['usd']:.5f}  {v['calls']:3d} calls  "
                     f"{v['prompt_tokens']:7d} in / {v['completion_tokens']:6d} out tokens   {model}")
    if c.get("model_call_retries"):
        lines.append(f"    {c['model_call_retries']} model call(s) were retried after a transient failure")
    lines.append(f"  every call          python -m pd.ledger {rep.get('work', '<work>')}"
                 f"   (add a call number to read what it was sent and what it answered)")
    if rep.get("stage_agent_fallbacks") or rep.get("navigator_corrections"):
        lines.append(f"  agent slips         {rep.get('stage_agent_fallbacks', 0)} stage-agent fallbacks, "
                     f"{rep.get('navigator_corrections', 0)} navigator corrections")
    return "\n".join(lines)


def cli():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--design", default=str(HERE / "designs" / "ble_tx"))
    p.add_argument("--work", default="/tmp/llm_pd_agent")
    p.add_argument("--runs", type=int, default=20,
                   help="flow-run budget, baseline and evaluations included")
    p.add_argument("--usd", type=float, default=1.00, help="dollar budget for model calls")
    p.add_argument("--stop-policy", choices=("rule", "agent", "either", "critic"), default=None,
                   metavar="{rule,agent,either}",
                   help="override policy.STOP_POLICY (the old value critic still means agent)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--weights", default=None, metavar="T,P,D,A",
                   help="score weights for timing, power, die area and cell area, to try a "
                        "different priority (three numbers: timing, power, cell area); "
                        "the default is WEIGHTS in pd/ledger.py")
    p.add_argument("--model", action="append", default=[], metavar="ROLE=ID",
                   help="give one agent another model for this run, for example "
                        "navigator=openrouter/anthropic/claude-opus-5.5; repeat for several. "
                        "The default is ROLE_MODEL in agents/policy.py")
    p.add_argument("--offline", nargs="?", type=int, const=8801, default=None, metavar="PORT",
                   help="use harness/mock_openrouter.py on PORT (default 8801)")
    p.add_argument("--patience", type=int, default=None, metavar="N",
                   help="override PATIENCE in agents/policy.py for this run, if the policy has "
                        "one: runs without a gain before the stopping rule ends the search. "
                        "For long runs that should use their whole budget")
    a = p.parse_args()

    from .compat import policy, role
    if a.patience is not None:
        if hasattr(policy, "PATIENCE"):
            policy.PATIENCE = a.patience
        else:
            print("  --patience ignored: agents/policy.py has no PATIENCE", flush=True)
    for item in a.model:
        who, _, name = item.partition("=")
        who = role(who)
        if who not in policy.ROLE_MODEL or not name:
            raise SystemExit(f"--model takes ROLE=ID with ROLE one of {', '.join(policy.ROLE_MODEL)}; "
                             f"got {item!r}")
        policy.ROLE_MODEL[who] = name

    warnings.filterwarnings("ignore")
    logging.getLogger().setLevel(logging.ERROR)
    from pd.classical import read_clock
    clock = read_clock(a.design)        # the flow reads the same file; never override it here

    t0 = time.monotonic()
    from pd.ledger import parse_weights
    rep = asyncio.run(run(a.design, a.work, clock, a.runs, a.usd, a.offline,
                          a.stop_policy, a.seed, weights=parse_weights(a.weights)))
    print(summarise(rep))
    print(f"  report  {Path(a.work).resolve() / 'report.json'}   ({(time.monotonic() - t0) / 60:.1f} min)")
    return 0 if "score" in rep else 1


if __name__ == "__main__":
    sys.exit(cli())
