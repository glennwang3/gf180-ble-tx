"""Every action the agents took in one search, and what it cost.

    python tools/agent_actions.py WORK > agent_actions.md

Reads WORK/report.json, ledger.json, trace.jsonl and tree.json. One section per
iteration: what the navigator chose and why, what the stage agent proposed and
picked, what the flow run reached, what the stop agent and the stopping rule said, and the
dollars, tokens and seconds of every model call; then the evaluations made at the end,
and the cost broken down by agent and by model. Markdown on stdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_trials import rows as trial_rows      # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pd import names                               # noqa: E402


def parsed(out: dict):
    text = out.get("content")
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return text


def money(x: float) -> str:
    return f"${x:.5f}"


def main(work: Path) -> None:
    rep = names.load_report(work / "report.json")       # old agent names read as new
    led = names.load_ledger(work / "ledger.json")
    trace = {c["n"]: c for c in names.load_trace(work / "trace.jsonl")}
    cost = {c["n"]: c for c in led["calls"]}
    trials = list(trial_rows(work))
    by_run = {int(r["flow_run"]): r for r in trials}
    decisions = led.get("decisions", [])
    s, c, q = rep["score"], rep["cost"], rep["search"]

    def call_line(n):
        if n not in cost:            # traced, but the run stopped before the ledger was saved
            return f"call {n}, {trace[n]['agent']}: not in the ledger; the run stopped during it"
        k = cost[n]
        return (f"call {n}, {k['agent']}, {k['model'].split('/')[-1]}: {k['tokens']['prompt']} in / "
                f"{k['tokens']['completion']} out tokens, {money(k['usd'])}, {k['seconds']:.1f} s")

    def trial_line(r):
        f = lambda v, p: "-" if v in (None, "") else format(float(v), p)
        what = "score" if r["move"].startswith("evaluate") else "estimated score"
        return (f"{what} {f(r['score'], '.4f')}; ECP {f(r['ecp_ns'], '.3f')} ns "
                f"({f(r['ecp_vs_baseline'], '.3f')}×), hold {f(r['hold_slack_ns'], '.3f')} ns, "
                f"power {f(r['power_w'], '.4f')} W ({f(r['power_vs_baseline'], '.3f')}×), "
                f"cell area {f(r['cell_area_um2'], '.0f')} µm² ({f(r['area_vs_baseline'], '.3f')}×)"
                + (f" — estimate just before was {float(r['estimate_before_signoff']):.4f}"
                   if r.get("estimate_before_signoff") else "")
                + f" — {r['outcome']}")

    out = [f"# Agent actions and cost: {work.name}", ""]
    out += [f"Score **{s['score']}** under weights {s['weights']}; answer {rep['final_node']}, "
            f"ECP {s['baseline_ecp_ns']} → {s['final_ecp_ns']} ns. "
            f"{c['flow_runs']} of {c['flow_run_budget']} flow runs, {c['flow_minutes']:.1f} flow-minutes, "
            f"{len(led['calls'])} model calls, {money(c['usd'])} of ${c['usd_budget']}.", ""]
    b = by_run.get(1)
    if b:
        out += [f"Flow run 1, the baseline (LibreLane's flow untouched): {trial_line(b)}.", ""]

    # group the calls into iterations: each starts at a navigator call
    order = sorted(trace)
    iters, cur = [], None
    for n in order:
        a = trace[n]["agent"]
        if a == "navigator" or cur is None:
            cur = []
            iters.append(cur)
        cur.append(n)
    run = 1
    for i, calls in enumerate(iters, 1):
        run += 1
        out += [f"## Iteration {i} — flow run {run}", ""]
        r = by_run.get(run)
        result_shown = False
        for n in calls:
            t, a = trace[n], trace[n]["agent"]
            o = parsed(t["output"])
            if a == "stop_agent" and r and not result_shown:
                out += [f"**Flow run {run}** ({r['move']}, {r['node']}): {trial_line(r)}", ""]
                result_shown = True
            if a == "navigator" and isinstance(o, dict):
                move = (f"evaluate {o.get('node_id')}" if names.move(o.get("action")) == "evaluate"
                        else f"branch {o.get('node_id')}:{o.get('stage')}")
                out += [f"**Navigator** → {move}", "", f"> {o.get('reason', '')}", ""]
                if o.get("hint"):
                    out += [f"Hint to the stage agent: *{o['hint']}*", ""]
            elif a == "stage_agent":
                for tc in t["output"].get("tool_calls") or []:
                    if tc["name"] == "propose_candidates":
                        out += [f"**Stage agent** asks the proposer for {tc['arguments'].get('count')} "
                                f"legal settings at {tc['arguments'].get('stage')}.", ""]
                    elif tc["name"] == "submit_action":
                        args = tc["arguments"]
                        out += [f"**Stage agent** submits `{json.dumps(args.get('parameters'))}`", "",
                                f"> {args.get('rationale', '')}", ""]
            elif a == "diagnostician":
                out += [f"**Diagnostician**: {o}", ""]
            elif a == "stop_agent" and isinstance(o, dict):
                out += [f"**Stop agent** → {'stop' if o.get('stop') else 'continue'}: {o.get('reason', '')}", ""]
            out += [f"<sub>{call_line(n)}</sub>", ""]
        if r and not result_shown:
            out += [f"**Flow run {run}** ({r['move']}, {r['node']}): {trial_line(r)}", ""]
        if i - 1 < len(decisions):
            d = decisions[i - 1]
            out += [f"Stopping rule: {'stop' if d['rule_says_stop'] else 'continue'}"
                    + (f"; hard limit: {d['hard_limit']}" if d.get("hard_limit") else "")
                    + f" → search {'stops' if d['stopped'] else 'continues'}.", ""]
    end = [r for r in trials if r["move"] == "evaluate (end)"]
    if end:
        out += ["## Signoffs at the end (no model calls)", ""]
        for r in end:
            out += [f"- Flow run {r['flow_run']}, {r['node']}: {trial_line(r)}"]
        out += [""]

    out += ["## Cost", "", "| agent | calls | tokens in | tokens out | dollars | seconds |", "| --- | --- | --- | --- | --- | --- |"]
    tot = [0, 0, 0, 0.0, 0.0]
    for agent in ("navigator", "stage_agent", "diagnostician", "stop_agent"):
        ks = [k for k in led["calls"] if k["agent"] == agent]
        if not ks:
            continue
        row = [len(ks), sum(k["tokens"]["prompt"] for k in ks), sum(k["tokens"]["completion"] for k in ks),
               sum(k["usd"] for k in ks), sum(k["seconds"] for k in ks)]
        tot = [a + b for a, b in zip(tot, row)]
        out.append(f"| {agent} | {row[0]} | {row[1]} | {row[2]} | {money(row[3])} | {row[4]:.0f} |")
    out.append(f"| **all** | {tot[0]} | {tot[1]} | {tot[2]} | **{money(tot[3])}** | {tot[4]:.0f} |")
    gain = (s["score"] - 1) * 100
    out += ["", f"Models: {', '.join(sorted({k['model'] for k in led['calls']}))}. "
            f"Flow: {c['flow_runs']} runs, {c['flow_minutes']:.1f} minutes of LibreLane; "
            f"model calls took {tot[4] / 60:.1f} minutes in all. "
            + (f"Dollars per percent of score gained: {money(tot[3] / gain)}." if gain > 0 else ""), ""]
    print("\n".join(out))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
