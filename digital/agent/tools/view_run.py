"""Replay one run in a browser: what each agent was shown and what it answered.

    python tools/view_run.py WORK              # writes WORK/run.html
    python tools/view_run.py WORK -o page.html
    python tools/view_run.py WORK --note "what a reader should know about this run"

Reads tree.json, report.json, ledger.json and trace.jsonl from a work directory
and writes one self-contained page. On the left, every flow run of the search;
on the right, the selected move in the order the loop executed it: the view
built for the navigator, the navigator's answer, then either the stage agent and
the branch it led to or the signoff the navigator asked for, then the stop agent
and the gate.

A run saved before the judge and the critic were renamed is read through
pd/names.py and shown under the new names.

A run made without a model (pd.classical) has no trace, and the page then shows
the flow runs and the evaluations only.

--fragment leaves out the <html> and <body> wrapper, for a host that supplies
its own.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from pd import names, stages as S             # noqa: E402
from pd.tree import Tree                      # noqa: E402

AGENTS = ("navigator", "stage_agent", "diagnostician", "stop_agent")


def _parsed(text):
    """An agent's input or answer as JSON when it is JSON, else as it came."""
    if not isinstance(text, str):
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text


def _spend(calls: list[dict], cost: dict) -> dict:
    rows = [cost.get(c["n"], {}) for c in calls]
    tok = [r.get("tokens") or {} for r in rows]
    return {"calls": len(calls), "numbers": [c["n"] for c in calls],
            "usd": round(sum(r.get("usd") or 0 for r in rows), 6),
            "tokens_in": sum(t.get("prompt") or 0 for t in tok),
            "tokens_out": sum(t.get("completion") or 0 for t in tok),
            "seconds": round(sum(r.get("seconds") or 0 for r in rows), 1)}


def _shown(call: dict):
    """The one message an agent is handed: the view built for it."""
    for m in call["input"]:
        if m.get("role") == "user":
            return _parsed(m.get("content"))
    return None


def _thought(calls: list[dict]) -> str | None:
    """What a reasoning model reported thinking, over the calls of one step."""
    said = [c["output"]["reasoning"] for c in calls if c["output"].get("reasoning")]
    return "\n\n".join(said) or None


def _answer(call: dict):
    out = call["output"]
    if out.get("tool_calls"):
        return out["tool_calls"][-1]["arguments"]
    return _parsed(out.get("content"))


def _turns(call: dict) -> list[dict]:
    """A tool-using agent's whole exchange, read off its last call: each call
    carries everything said before it."""
    turns, seen_user = [], False
    for m in call["input"] + [dict(call["output"], role="assistant")]:
        if m.get("role") == "user" and not seen_user:
            seen_user = True
            continue
        if not seen_user:
            continue
        if m.get("role") == "tool":
            turns.append({"type": "result", "content": _parsed(m.get("content"))})
            continue
        for tc in m.get("tool_calls") or []:
            turns.append({"type": "call", "name": tc["name"], "arguments": tc["arguments"]})
        if m.get("content"):
            turns.append({"type": "say", "text": m["content"]})
    return turns


def build(work: Path, note: str = "") -> dict:
    tree = Tree.load(work / "tree.json")
    rep = names.load_report(work / "report.json") if (work / "report.json").exists() else {}
    led = names.load_ledger(work / "ledger.json") if (work / "ledger.json").exists() else {}
    tp = work / "trace.jsonl"
    calls = names.load_trace(tp) if tp.exists() else []
    cost = {c.get("n", i): c for i, c in enumerate(led.get("calls", []), 1)}
    hist = tree.history()
    root = tree.nodes[tree.order[0]]

    # Every signoff the run made. A search still running has no report yet, and
    # then the tree is the only record of them.
    checks = rep.get("evaluations")
    if checks is None:
        checks = [{"node": i, "when": "search", "seconds": 0.0, "kind": tree.kind(i),
                   "kind_already_checked": True, "estimate": None, "signoff": tree.real_row(i),
                   "outcome": "evaluated"}
                  for i in tree.order[1:] if tree.signed_off(i)]
    done = {c["node"]: c for c in checks if "seconds" in c}

    nodes = []
    for i, nid in enumerate(tree.order):
        n, par = tree.nodes[nid], tree.nodes.get(tree.nodes[nid].parent)
        row = tree.row(nid) if n.ok and n.metrics else {}
        why = tree.why_not(nid) if row else None
        state = ("baseline" if i == 0 else "refused" if not n.ok and n.seconds == 0
                 else "failed" if not n.ok else "screened" if why else "candidate")
        nodes.append({
            "id": nid, "parent": n.parent, "stage": n.stage, "state": state,
            "kind": tree.kind(nid), "checked": bool(row) and tree.checked(nid),
            "seconds": round(n.seconds, 1), "params": n.params,
            "changed": [k for k, v in n.params.items() if par is None or par.params.get(k) != v],
            **row, "why_not": why, "error": n.error[:600], "note": n.note[:600],
            "best_after": hist[i] if i < len(hist) else None,
            "signoff": tree.real_row(nid) if n.ok else None,
            "outcome": (done.get(nid) or {}).get("outcome"),
        })

    # The order things happened in. A node and a signoff each took one flow run,
    # and a signoff says which run it was, so the two lists merge on that.
    at = {c["after_flow_runs"]: c for c in checks if "after_flow_runs" in c}
    events, run = [], 0
    for nid in tree.order:
        if nid == root.id or tree.nodes[nid].seconds > 0:
            run += 1
        if nid != root.id:
            events.append(("branch", nid, None))
        while run + 1 in at:
            run += 1
            events.append(("evaluate", at[run]["node"], at[run]))
    placed = {id(e[2]) for e in events if e[2] is not None}
    events += [("evaluate", c["node"], c) for c in checks if "seconds" in c and id(c) not in placed]

    # Model calls fall into moves at each navigator call, in the same order.
    groups = []
    for c in calls:
        if c["agent"] == "navigator":
            groups.append({a: [] for a in AGENTS})
        if groups:
            groups[-1][c["agent"]].append(c)
    gates = led.get("decisions", [])

    moves, asked = [], 0
    for kind, nid, check in events:
        if check is not None and check.get("when") == "end":
            continue                                # made by finish(), shown on the last page
        move = {"key": f"m{len(moves) + 1}", "type": kind, "node": nid, "check": check}
        g = groups[asked] if asked < len(groups) else None
        if asked < len(gates):
            move["gate"] = gates[asked]
        asked += 1
        if g:
            if g["navigator"]:
                ans = _answer(g["navigator"][-1])
                move["navigator"] = {"shown": _shown(g["navigator"][-1]), "answer": ans,
                                     "thought": _thought(g["navigator"]),
                                     "spend": _spend(g["navigator"], cost)}
                if isinstance(ans, dict):
                    wanted = names.move(ans.get("action", "branch")) == "evaluate"
                    n = tree.nodes[nid]
                    move["corrected"] = (wanted != (kind == "evaluate")) or (
                        kind == "branch" and (ans.get("node_id"), str(ans.get("stage", "")).upper())
                        != (n.parent, n.stage)) or (kind == "evaluate" and ans.get("node_id") != nid)
            if g["stage_agent"]:
                move["stage_agent"] = {"shown": _shown(g["stage_agent"][-1]),
                                       "turns": _turns(g["stage_agent"][-1]),
                                       "thought": _thought(g["stage_agent"]),
                                       "spend": _spend(g["stage_agent"], cost)}
            for a in ("diagnostician", "stop_agent"):
                if g[a]:
                    move[a] = {"shown": _shown(g[a][-1]), "answer": _answer(g[a][-1]),
                               "thought": _thought(g[a]), "spend": _spend(g[a], cost)}
        moves.append(move)

    def instruction(agent):
        for c in calls:
            if c["agent"] == agent:
                return next((m.get("content") for m in c["input"] if m.get("role") == "system"), None)
        return None

    def absolute(m):
        return {} if not m else {"ecp_ns": round(tree.clock - S.setup_ws(m), 4),
                                 "hold_slack_ns": round(S.hold_ws(m), 3),
                                 "power_w": round(m.get(S.POWER_KEY, 0), 4),
                                 "cell_area_um2": m.get(S.AREA_KEY)}

    kinds = rep.get("kinds")
    if kinds is None:
        kinds = tree.kinds()
        for k in kinds:
            fix = tree.correction(k["kind"])
            k["correction"] = None if fix is None else {x: round(v, 4) for x, v in fix.items()}
    return {
        "work": work.name, "method": rep.get("method", "?"),
        "models": rep.get("models") or {}, "stop_policy": rep.get("stop_policy"),
        "clock_ns": tree.clock, "weights": tree.weights,
        "thresholds": {"hold_floor_ns": tree.hold_floor, "power_ceiling": tree.power_ceiling},
        "score": rep.get("score"), "final_node": rep.get("final_node"),
        "fell_back": rep.get("fell_back_to_baseline"), "cost": rep.get("cost"),
        "checks": checks, "kinds": kinds,
        "baseline": {"estimate": absolute(root.metrics), "signoff": absolute(root.signoff_metrics),
                     "seconds": round(root.seconds, 1), "stage_seconds": root.stage_seconds},
        "nodes": nodes, "moves": moves,
        "instructions": {a: instruction(a) for a in AGENTS},
        "has_trace": bool(calls), "finished": bool(rep), "note": note,
    }


HEAD = r"""<title>Lab 4 Run Replay</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600&display=swap">
<style>
/* Layout: the run as a column of flow runs on the left; on the right, the selected
   iteration read top to bottom in the order the loop executes it. Boxes follow the
   lab's loop diagram: amber outline = an LLM agent answered, solid = plain Python,
   dashed = the code that builds what the next agent is shown. */
:root {
  --bg: #f3f5f8; --surface: #ffffff; --sunk: #eceff4; --ink: #18202c; --muted: #596475;
  --line: #d5dbe4; --agent: #b45309; --agent-soft: #fbf1e1; --good: #0b7a6f; --bad: #b3261e;
  --sel: #e3ebf7;
  --display: "IBM Plex Sans Condensed", "Arial Narrow", "Helvetica Neue", sans-serif;
  --body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #10151b; --surface: #182029; --sunk: #121920; --ink: #e5e9ef; --muted: #96a2b3;
  --line: #2b3542; --agent: #f0a13a; --agent-soft: #2c2212; --good: #4cc9b8; --bad: #f47b72;
  --sel: #20304a; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #10151b; --surface: #182029; --sunk: #121920; --ink: #e5e9ef; --muted: #96a2b3;
  --line: #2b3542; --agent: #f0a13a; --agent-soft: #2c2212; --good: #4cc9b8; --bad: #f47b72;
  --sel: #20304a; color-scheme: dark }

* { box-sizing: border-box }
body { margin: 0; background: var(--bg); color: var(--ink); font: 400 14px/1.5 var(--body) }
.page { max-width: 1320px; margin: 0 auto; padding-inline: 20px; padding-block: 20px 56px;
        display: flex; flex-direction: column; gap: 20px }
button { font: inherit; color: inherit }
:focus-visible { outline: 2px solid var(--agent); outline-offset: 2px }

.top { display: flex; flex-wrap: wrap; gap: 16px 40px; align-items: flex-end;
       justify-content: space-between; border-bottom: 1px solid var(--line); padding-bottom: 16px }
.top > div { min-width: 0 }
.eyebrow { margin: 0 0 6px; font: 500 11px/1.2 var(--display); letter-spacing: .09em;
           text-transform: uppercase; color: var(--muted) }
h1 { margin: 0; font: 600 27px/1.15 var(--display); text-wrap: balance }
.sub { margin: 6px 0 0; color: var(--muted); max-width: 68ch }
.facts { display: flex; flex-wrap: wrap; gap: 12px 26px; margin: 0 }
.facts div { display: flex; flex-direction: column; gap: 3px }
.facts dt { font: 500 10.5px/1.2 var(--display); letter-spacing: .08em; text-transform: uppercase;
            color: var(--muted) }
.facts dd { margin: 0; font: 500 15px/1.2 var(--mono); font-variant-numeric: tabular-nums }
.facts .lead dd { font-size: 26px; font-weight: 500 }

.note { margin: 0; padding: 10px 14px; border: 1px solid var(--agent); border-radius: 6px;
        background: var(--agent-soft); max-width: 100ch }
.cols { display: grid; grid-template-columns: minmax(270px, 330px) minmax(0, 1fr); gap: 26px;
        align-items: start }
.rail { position: sticky; top: calc(env(safe-area-inset-top, 0px) + 12px); min-width: 0;
        display: flex; flex-direction: column; gap: 12px; max-height: calc(100dvh - 24px) }
.chart { margin: 0; background: var(--surface); border: 1px solid var(--line); border-radius: 6px;
         padding: 10px 10px 8px }
.chart svg { display: block; width: 100%; height: auto }
.chart figcaption { margin-top: 6px; font-size: 11.5px; line-height: 1.4; color: var(--muted) }
.chart text { font: 400 9.5px var(--mono); fill: var(--muted) }
.railhead { display: flex; align-items: center; justify-content: space-between; gap: 8px }
.railhead > span { font: 600 11px/1 var(--display); letter-spacing: .09em; text-transform: uppercase;
                   color: var(--muted) }
.seg { display: flex; border: 1px solid var(--line); border-radius: 5px; overflow: hidden }
.seg button { border: 0; background: transparent; padding: 4px 9px; font-size: 12px; cursor: pointer;
              color: var(--muted) }
.seg button[aria-pressed="true"] { background: var(--ink); color: var(--bg) }
.runs { list-style: none; margin: 0; padding: 0; overflow: auto; display: flex;
        flex-direction: column; border: 1px solid var(--line); border-radius: 6px;
        background: var(--surface) }
.runs li + li { border-top: 1px solid var(--line) }
.run { width: 100%; display: grid; grid-template-columns: auto auto 1fr auto; align-items: center;
       gap: 8px; padding: 7px 10px; border: 0; background: transparent; text-align: left;
       cursor: pointer }
.run:hover { background: var(--sunk) }
.run[aria-current="true"] { background: var(--sel) }
.nid { font: 500 13px/1 var(--mono); min-width: 2.6em }
.stg { font: 600 10px/1 var(--display); letter-spacing: .06em; padding: 3px 5px; border-radius: 3px;
       border: 1px solid var(--line); color: var(--muted); min-width: 2.9em; text-align: center }
.what { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden;
        text-overflow: ellipsis; min-width: 0 }
.val { font: 400 12.5px/1 var(--mono); font-variant-numeric: tabular-nums; display: flex;
       align-items: center; gap: 6px }
.dot { width: 9px; height: 9px; border-radius: 50%; flex: none; border: 1.5px solid var(--muted) }
.dot.candidate { background: var(--good); border-color: var(--good) }
.dot.baseline { background: var(--ink); border-color: var(--ink) }
.dot.signed { border-radius: 1px; transform: rotate(45deg); background: var(--surface); border-color: var(--ink) }
.dot.failed, .dot.refused { border-color: var(--bad); background: var(--bad) }
.dot.answer { border-radius: 1px; transform: rotate(45deg); background: var(--agent);
              border-color: var(--agent) }

.detail { min-width: 0; display: flex; flex-direction: column; gap: 14px }
.dhead { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px }
.dhead h2 { margin: 0; font: 600 20px/1.2 var(--display); text-wrap: balance }
.nav { margin-left: auto; display: flex; gap: 6px }
.nav button { border: 1px solid var(--line); background: var(--surface); border-radius: 5px;
              padding: 5px 11px; cursor: pointer; font-size: 13px }
.nav button:disabled { opacity: .4; cursor: default }
.pill { display: inline-block; font: 600 10.5px/1 var(--display); letter-spacing: .07em;
        text-transform: uppercase; padding: 4px 7px; border-radius: 3px; border: 1px solid var(--line);
        color: var(--muted); white-space: nowrap }
.pill.good { color: var(--good); border-color: var(--good) }
.pill.bad { color: var(--bad); border-color: var(--bad) }
.pill.answer { color: var(--bg); background: var(--agent); border-color: var(--agent) }
.lede { margin: 0; color: var(--muted); max-width: 72ch }

.flow { display: flex; flex-direction: column }
.step { background: var(--surface); border: 1.4px solid var(--ink); border-radius: 6px; min-width: 0 }
.step.agent { border: 2px solid var(--agent) }
.step.view { border: 1px dashed var(--muted) }
.step > header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px;
                 padding: 10px 14px 0 }
.step h3 { margin: 0; font: 600 15px/1.25 var(--body) }
.tag { font: 600 10px/1.2 var(--display); letter-spacing: .09em; text-transform: uppercase;
       color: var(--muted) }
.step.agent .tag { color: var(--agent) }
.meta { margin-left: auto; font: 400 11.5px/1.3 var(--mono); color: var(--muted); text-align: right }
.meta b { font-weight: 500; color: var(--ink) }
.body { padding: 8px 14px 14px; display: flex; flex-direction: column; gap: 10px; min-width: 0 }
.body > p { margin: 0; max-width: 78ch }
.cap { font: 600 10.5px/1.2 var(--display); letter-spacing: .08em; text-transform: uppercase;
       color: var(--muted); margin: 0 }
.link { width: 0; height: 20px; margin-left: 30px; border-left: 1.4px solid var(--ink);
        position: relative }
.link::after { content: ""; position: absolute; left: -5.2px; bottom: 0; border: 4.5px solid transparent;
               border-top: 7px solid var(--ink); border-bottom: 0 }

.kv { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 5px 14px; margin: 0 }
.kv dt { font: 400 12px/1.5 var(--mono); color: var(--muted) }
.kv dd { margin: 0; min-width: 0; overflow-wrap: anywhere }
.branch { font: 500 13px/1 var(--mono); padding: 3px 7px; border-radius: 3px;
          background: var(--agent-soft); color: var(--ink) }
.mono { font-family: var(--mono); font-variant-numeric: tabular-nums }
.said { margin: 0; padding: 9px 11px; background: var(--agent-soft); border-radius: 4px; max-width: 80ch }
.turn { display: flex; flex-direction: column; gap: 6px; min-width: 0 }
.turn + .turn { border-top: 1px solid var(--line); padding-top: 10px }
.who { font: 500 12px/1.3 var(--mono); color: var(--muted) }
.who b { color: var(--agent); font-weight: 500 }

.scroll { overflow-x: auto; max-width: 100% }
table.grid { border-collapse: collapse; font: 400 12px/1.4 var(--mono);
             font-variant-numeric: tabular-nums }
.grid th, .grid td { padding: 4px 10px; text-align: left; border-bottom: 1px solid var(--line);
                     white-space: nowrap; vertical-align: top }
.grid th { font: 600 10.5px/1.3 var(--display); letter-spacing: .06em; text-transform: uppercase;
           color: var(--muted) }
.grid td.wrap { white-space: normal; min-width: 22ch; max-width: 60ch; font-family: var(--body) }
.grid tr.hit td { background: var(--agent-soft) }
.grid tr.est td { border-bottom: 0; color: var(--muted) }
.num { text-align: right !important }

.j-obj { display: flex; flex-direction: column; gap: 4px; min-width: 0 }
.j-row { display: flex; flex-wrap: wrap; gap: 2px 10px; align-items: baseline; min-width: 0 }
.j-key { font: 400 12px/1.5 var(--mono); color: var(--muted) }
.j-str { overflow-wrap: anywhere }
.j-num { font: 400 12.5px/1.5 var(--mono); font-variant-numeric: tabular-nums }
.j-null { color: var(--muted); font-style: italic }
.j-list { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 4px }
details.j-block > summary { cursor: pointer; display: flex; gap: 10px; align-items: baseline;
                            list-style-position: outside }
details.j-block > summary::before { content: "+"; font: 500 12px/1 var(--mono); color: var(--muted);
                                    width: 10px; flex: none }
details.j-block[open] > summary::before { content: "\2212" }
details.j-block > summary::-webkit-details-marker { display: none }
.j-hint { font-size: 11.5px; color: var(--muted) }
.j-body { margin: 4px 0 4px 4px; padding-left: 14px; border-left: 1px solid var(--line); min-width: 0 }
pre.j-text, pre.instr { margin: 0; padding: 9px 11px; background: var(--sunk); border-radius: 4px;
                        font: 400 11.5px/1.5 var(--mono); white-space: pre-wrap;
                        overflow-wrap: anywhere; max-height: 340px; overflow: auto }
details.more > summary { cursor: pointer; font-size: 12.5px; color: var(--muted) }
details.more[open] > summary { margin-bottom: 6px }
.formula { font: 400 13px/1.7 var(--mono); margin: 0; overflow-wrap: anywhere }

@media (max-width: 880px) {
  .cols { grid-template-columns: minmax(0, 1fr) }
  .rail { position: static; max-height: none }
  .runs { max-height: 232px }
  .meta { margin-left: 0; text-align: left; flex-basis: 100% }
}
@media (prefers-reduced-motion: no-preference) { .run { transition: background-color .12s } }
</style>
"""

BODY = r"""<div class="page">
  <header class="top">
    <div>
      <p class="eyebrow">Lab 4 &middot; agent loop over a LibreLane backend flow</p>
      <h1 id="title"></h1>
      <p class="sub" id="subtitle"></p>
    </div>
    <dl class="facts" id="facts"></dl>
  </header>
  <p class="note" id="note" hidden></p>
  <div class="cols">
    <nav class="rail" aria-label="Flow runs of this search">
      <figure class="chart">
        <svg id="chart" viewBox="0 0 320 140" role="img"
             aria-label="Estimated score of each flow run, the best candidate so far, and the score at signoff of the results that were evaluated"></svg>
        <figcaption>Dots: estimated score of each flow run. Line: best candidate so far.
          Hollow dots: not a candidate, or of a kind no evaluation has checked. Diamonds: the same
          node at signoff. Dashed: the baseline, 1.0.</figcaption>
      </figure>
      <div class="railhead">
        <span>Flow runs</span>
        <div class="seg" role="group" aria-label="Order of the list">
          <button type="button" id="by-time" aria-pressed="true">in order</button>
          <button type="button" id="by-tree" aria-pressed="false">as a tree</button>
        </div>
      </div>
      <ol class="runs" id="runs"></ol>
    </nav>
    <main class="detail" id="detail"></main>
  </div>
</div>
<script type="application/json" id="run-data">/*DATA*/</script>
<script>
(function () {
  "use strict";
  var RUN = JSON.parse(document.getElementById("run-data").textContent);
  var NODE = {}, MOVE = {}, MADE = {};
  RUN.nodes.forEach(function (n) { NODE[n.id] = n; });
  RUN.moves.forEach(function (m) { MOVE[m.key] = m; if (m.type === "branch") MADE[m.node] = m.key; });
  var ROOT = RUN.nodes[0].id;
  MADE[ROOT] = ROOT;
  var EVALUATE = ["evaluate", "signoff", "sign_off", "sign off", "sign-off"];   /* the move, and its old names */
  var OBEYED = { rule: "the stopping rule", agent: "the stop agent",
                 either: "either, whichever says stop first" };   /* STOP_POLICY, as recorded */
  var KEYS = [ROOT].concat(RUN.moves.map(function (m) { return m.key; }), ["end"]);
  var order = "time", sel = null;

  function el(tag, attrs) {
    var e = document.createElement(tag), k;
    for (k in (attrs || {})) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    var kids = Array.prototype.slice.call(arguments, 2);
    (function add(list) {             /* its own index: it calls itself for a nested list */
      for (var i = 0; i < list.length; i++) {
        var kid = list[i];
        if (kid == null || kid === false) continue;
        if (Array.isArray(kid)) { add(kid); continue; }
        e.appendChild(kid.nodeType ? kid : document.createTextNode(String(kid)));
      }
    })(kids);
    return e;
  }
  function sv(tag, attrs) {
    var e = document.createElementNS("http://www.w3.org/2000/svg", tag), k;
    for (k in (attrs || {})) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    for (var i = 2; i < arguments.length; i++) if (arguments[i] != null) e.appendChild(arguments[i]);
    return e;
  }
  function fx(v, d) { return v == null ? "–" : Number(v).toFixed(d); }
  function usd(v) { return v == null ? "–" : "$" + Number(v).toFixed(v < 0.01 ? 4 : 3); }
  function isPrim(v) { return v === null || typeof v !== "object"; }
  function longText(v) { return typeof v === "string" && (v.indexOf("\n") >= 0 || v.length > 140); }

  /* ---------------------------------------------------------- generic data viewer */
  function inline(v) {
    if (isPrim(v)) return v === null ? "–" : String(v);
    if (Array.isArray(v)) return v.map(inline).join(", ");
    return Object.keys(v).map(function (k) { return k + "=" + inline(v[k]); }).join(", ");
  }
  function flatRows(a) {
    return a.length > 0 && a.every(function (r) {
      return r && typeof r === "object" && !Array.isArray(r) && Object.keys(r).every(function (k) {
        return isPrim(r[k]) ? !longText(r[k]) || r[k].length < 320 : JSON.stringify(r[k]).length < 260;
      });
    });
  }
  function grid(rows, mark) {
    var cols = [];
    rows.forEach(function (r) { Object.keys(r).forEach(function (k) { if (cols.indexOf(k) < 0) cols.push(k); }); });
    return el("div", { "class": "scroll" }, el("table", { "class": "grid" },
      el("thead", null, el("tr", null, cols.map(function (c) { return el("th", null, c.replace(/_/g, " ")); }))),
      el("tbody", null, rows.map(function (r, i) {
        return el("tr", { "class": mark && mark(r, i) ? "hit" : null }, cols.map(function (c) {
          var v = r[c], text = c in r ? inline(v) : "";
          return el("td", { "class": typeof v === "number" ? "num" : text.length > 44 ? "wrap" : null }, text);
        }));
      }))));
  }
  function prim(v) {
    if (v === null) return el("span", { "class": "j-null" }, "none");
    if (typeof v === "string") return longText(v) ? el("pre", { "class": "j-text" }, v) : el("span", { "class": "j-str" }, v);
    return el("span", { "class": "j-num" }, String(v));
  }
  function hint(x) {
    if (typeof x === "string") return x.length + " characters";
    if (Array.isArray(x)) return x.length + (x.length === 1 ? " item" : " items");
    return Object.keys(x).length + " fields";
  }
  function small(x) {           /* a handful of short values: one line, not a block */
    if (isPrim(x) || Array.isArray(x)) return false;
    var keys = Object.keys(x);
    return keys.length > 0 && keys.length <= 5 && keys.every(function (k) { return isPrim(x[k]) && !longText(x[k]) && String(x[k]).length < 40; });
  }
  function uniform(x) {         /* an object whose values are all small objects: a table keyed by name */
    var keys = Object.keys(x);
    return keys.length > 1 && keys.every(function (k) { return small(x[k]); });
  }
  function view(v, depth) {
    if (isPrim(v)) return prim(v);
    if (Array.isArray(v)) {
      if (!v.length) return el("span", { "class": "j-null" }, "none");
      if (v.every(isPrim) && JSON.stringify(v).length < 200) return el("span", { "class": "j-num" }, v.join("  ·  "));
      if (flatRows(v)) return grid(v);
      return el("ol", { "class": "j-list" }, v.map(function (x) { return el("li", null, view(x, depth + 1)); }));
    }
    var keys = Object.keys(v);
    if (!keys.length) return el("span", { "class": "j-null" }, "empty");
    if (uniform(v)) return grid(keys.map(function (k) {
      var row = { "": k };
      Object.keys(v[k]).forEach(function (f) { row[f] = v[k][f]; });
      return row;
    }));
    return el("div", { "class": "j-obj" }, keys.map(function (k) {
      var x = v[k];
      if (isPrim(x) && !longText(x)) return el("div", { "class": "j-row" }, el("span", { "class": "j-key" }, k), prim(x));
      if (Array.isArray(x) && x.every(isPrim) && JSON.stringify(x).length < 200)
        return el("div", { "class": "j-row" }, el("span", { "class": "j-key" }, k), view(x, depth + 1));
      if (small(x)) return el("div", { "class": "j-row" }, el("span", { "class": "j-key" }, k),
        el("span", { "class": "j-num" }, Object.keys(x).map(function (f) { return f + " " + inline(x[f]); }).join("  \u00b7  ")));
      var rows = (Array.isArray(x) && flatRows(x)) || (!Array.isArray(x) && !isPrim(x) && uniform(x));
      return el("details", { "class": "j-block", open: !longText(x) && (depth < 1 || (rows && depth < 3)) },
        el("summary", null, el("span", { "class": "j-key" }, k), el("span", { "class": "j-hint" }, hint(x))),
        el("div", { "class": "j-body" }, view(x, depth + 1)));
    }));
  }

  /* ---------------------------------------------------------- pieces of a step */
  function step(kind, name, tag, meta, body) {
    return el("section", { "class": "step " + kind },
      el("header", null, el("h3", null, name), el("span", { "class": "tag" }, tag),
        meta ? el("span", { "class": "meta" }, meta) : null),
      el("div", { "class": "body" }, body));
  }
  function spend(s, file) {
    var out = [el("b", null, file)];
    if (s) out.push("  ·  " + s.calls + (s.calls === 1 ? " call" : " calls") + "  ·  " +
      s.tokens_in + " in / " + s.tokens_out + " out tokens  ·  " + usd(s.usd) + "  ·  " + fx(s.seconds, 1) + " s");
    return out;
  }
  function instruction(agent) {
    var t = RUN.instructions[agent];
    return t ? el("details", { "class": "more" }, el("summary", null, "The instruction this agent works under (" + t.length + " characters, the same on every call)"),
      el("pre", { "class": "instr" }, t)) : null;
  }
  function thought(step) {
    return step && step.thought ? el("details", { "class": "more" }, el("summary", null, "What the model reported thinking before it answered"),
      el("pre", { "class": "instr" }, step.thought)) : null;
  }
  function statePill(n) {
    if (n.id === RUN.final_node && RUN.finished) return el("span", { "class": "pill answer" }, "the answer");
    if (n.state === "candidate") return el("span", { "class": "pill good" }, "candidate");
    if (n.state === "screened") return el("span", { "class": "pill" }, "not a candidate");
    if (n.state === "failed") return el("span", { "class": "pill bad" }, "flow failed");
    if (n.state === "refused") return el("span", { "class": "pill bad" }, "refused before running");
    return el("span", { "class": "pill" }, "baseline");
  }
  function numbers(rows) {     /* rows: [label, {score, ecp_ns, hold_slack_ns, power_vs_baseline, area_vs_baseline}, class] */
    return el("div", { "class": "scroll" }, el("table", { "class": "grid" },
      el("thead", null, el("tr", null, ["", "score", "ECP ns", "hold slack ns", "power × baseline", "cell area × baseline"].map(function (h, i) {
        return el("th", { "class": i ? "num" : null }, h); }))),
      el("tbody", null, rows.map(function (r) {
        var v = r[1] || {}, s = v.score != null ? v.score : v.score_est;
        return el("tr", { "class": r[2] || null }, el("td", null, r[0]), el("td", { "class": "num" }, fx(s, 4)),
          el("td", { "class": "num" }, fx(v.ecp_ns, 3)), el("td", { "class": "num" }, fx(v.hold_slack_ns, 3)),
          el("td", { "class": "num" }, fx(v.power_vs_baseline, 3)), el("td", { "class": "num" }, fx(v.area_vs_baseline, 3)));
      }))));
  }

  /* ---------------------------------------------------------- the kinds of page */
  function baselinePage() {
    var b = RUN.baseline, n = RUN.nodes[0];
    function row(label, m, score) {
      return el("tr", null, el("td", null, label), el("td", { "class": "num" }, score == null ? "" : fx(score, 4)),
        el("td", { "class": "num" }, fx(m.ecp_ns, 3)),
        el("td", { "class": "num" }, fx(m.hold_slack_ns, 3)), el("td", { "class": "num" }, fx(m.power_w, 4)),
        el("td", { "class": "num" }, m.cell_area_um2 == null ? "–" : Math.round(m.cell_area_um2)));
    }
    return [
      el("p", { "class": "lede" }, "The flow as LibreLane ships it, with no knob touched. It is the root of the search tree and the reference every score is a ratio to, and it is the one node that is signed off before the search starts."),
      el("div", { "class": "flow" }, step("code", "baseline", "plain Python · one full flow run", [fx(n.seconds, 0) + " s"], [
        el("div", { "class": "scroll" }, el("table", { "class": "grid" },
          el("thead", null, el("tr", null, ["", "score", "ECP ns", "hold slack ns", "power W", "cell area µm²"].map(function (h, i) { return el("th", { "class": i ? "num" : null }, h); }))),
          el("tbody", null, row("at signoff", b.signoff, 1), row("estimate, after global routing", b.estimate, null)))),
        el("p", null, "Every branch is stopped after global routing, so a search only ever sees numbers like the second row. The first row is what detailed routing and signoff make of the same layout, and a search gets one of those for a node only by spending a flow run on it."),
        Object.keys(b.stage_seconds || {}).length ? el("p", { "class": "mono" }, "seconds by part of the flow:  " + inline(b.stage_seconds)) : null
      ]))
    ];
  }

  function agentSteps(m, parts) {       /* the steps every move starts and ends with */
    function push(s) { if (parts.length) parts.push(el("div", { "class": "link" })); parts.push(s); }
    return {
      navigator: function () {
        if (!m.navigator) return;
        push(step("view", "navigator_view", "plain Python · builds what the navigator is shown", [el("b", null, "views.py")],
          [view(m.navigator.shown, 0)]));
        var a = m.navigator.answer || {}, off = EVALUATE.indexOf(String(a.action || "branch").toLowerCase().trim()) >= 0;
        push(step("agent", "navigator", "LLM agent · where to spend this run", spend(m.navigator.spend, "prompts.py"), [
          typeof a === "object" ? el("dl", { "class": "kv" },
            el("dt", null, "move"), el("dd", null, el("span", { "class": "branch" }, off ? "evaluate " + a.node_id : "branch " + a.node_id + ":" + a.stage)),
            el("dt", null, "reason"), el("dd", null, a.reason || "–"),
            off ? null : [el("dt", null, "hint"), el("dd", null, a.hint || "–")]) : el("p", { "class": "said" }, String(a)),
          thought(m.navigator), instruction("navigator")]));
      },
      push: push,
      closing: function () {
        if (m.diagnostician) {
          var d = m.diagnostician.answer || {};
          push(step("agent", "diagnostician", "LLM agent · only when a run fails", spend(m.diagnostician.spend, "prompts.py"), [
            el("details", { "class": "more" }, el("summary", null, "What it was shown"), view(m.diagnostician.shown, 1)),
            typeof d === "object" ? el("dl", { "class": "kv" }, el("dt", null, "cause"), el("dd", null, d.cause || "–"),
              el("dt", null, "evidence"), el("dd", null, d.evidence || "–"), el("dt", null, "remedy"), el("dd", null, d.remedy || "–"))
              : el("p", { "class": "said" }, String(d)),
            thought(m.diagnostician), instruction("diagnostician")]));
        }
        if (m.stop_agent) {
          push(step("view", "stop_view", "plain Python · builds what the stop agent is shown", [el("b", null, "views.py")], [view(m.stop_agent.shown, 0)]));
          var c = m.stop_agent.answer || {};
          push(step("agent", "stop agent", "LLM agent · continue or stop", spend(m.stop_agent.spend, "prompts.py"), [
            typeof c === "object" ? el("dl", { "class": "kv" },
              el("dt", null, "says"), el("dd", null, el("span", { "class": "pill" + (c.stop ? " bad" : " good") }, c.stop ? "stop" : "continue")),
              el("dt", null, "reason"), el("dd", null, c.reason || "–")) : el("p", { "class": "said" }, String(c)),
            thought(m.stop_agent), instruction("stop_agent")]));
        }
        if (m.gate) {
          var g = m.gate;
          push(step("code", "gate", "plain Python · who is obeyed", [el("b", null, "policy.py")], [
            el("dl", { "class": "kv" },
              el("dt", null, "stopping rule"), el("dd", null, g.rule_says_stop ? "stop" : "continue"),
              el("dt", null, "stop agent"), el("dd", null, g.stop_agent_says_stop == null ? "not asked" : g.stop_agent_says_stop ? "stop" : "continue"),
              el("dt", null, "hard limit"), el("dd", null, g.hard_limit || "none reached"),
              el("dt", null, "obeyed"), el("dd", null, OBEYED[RUN.stop_policy] || RUN.stop_policy || "not recorded"),
              el("dt", null, "outcome"), el("dd", null, el("span", { "class": "pill" + (g.stopped ? " bad" : " good") }, g.stopped ? "stop, go to the end" : "continue")))]));
        }
      }
    };
  }
  function ledeFor(m) {
    return m.navigator ? "One pass round the loop, in the order it ran. Dashed boxes are the code that builds an agent's input, amber boxes are the agent's answer, solid boxes are plain Python."
      : "This search ran without a model, so there is no agent to show: only the flow run and what it found.";
  }

  function branchPage(m) {
    var n = NODE[m.node], par = NODE[n.parent], parts = [], S = agentSteps(m, parts);
    S.navigator();
    if (m.stage_agent) {
      S.push(step("view", "plan", "plain Python · checks the move, builds what the stage agent is shown", [el("b", null, "views.py")], [
        el("p", null, m.corrected ? "The navigator named a move that does not exist. It was replaced with a branch at " + n.parent + ":" + n.stage + " and the slip was counted."
          : n.parent + ":" + n.stage + " is a legal branch."),
        view(m.stage_agent.shown, 0)]));
      S.push(step("agent", "stage agent", "LLM agent · which settings", spend(m.stage_agent.spend, "prompts.py · policy.py"), [
        m.stage_agent.turns.map(function (t) {
          if (t.type === "call") {
            var args = t.arguments || {}, isSubmit = t.name === "submit_action";
            return el("div", { "class": "turn" }, el("div", { "class": "who" }, el("b", null, "agent"), " calls " + t.name +
              (isSubmit ? "" : "(" + inline(args) + ")")),
              isSubmit ? [grid([args.parameters || {}]), args.rationale ? el("p", { "class": "said" }, args.rationale) : null] : null);
          }
          if (t.type === "result") {
            var c = t.content, rows = c && c.candidates;
            return el("div", { "class": "turn" }, el("div", { "class": "who" }, "tool returns"),
              rows ? grid(rows) : view(c, 1));
          }
          return el("div", { "class": "turn" }, el("div", { "class": "who" }, el("b", null, "agent"), " says"), el("p", { "class": "said" }, t.text));
        }),
        thought(m.stage_agent), instruction("stage_agent")]));
    }
    var settings = Object.keys(n.params).map(function (k) {
      return { knob: k, value: n.params[k], "on this path": n.changed.indexOf(k) >= 0 ? "set by this run" : "kept from " + n.parent };
    });
    var rows = [];
    if (par && par.score_est != null) rows.push(["where it started: " + par.id, par, "est"]);
    if (n.score_est != null) rows.push(["this run: " + n.id + ", estimate as it stands now", n]);
    if (n.signoff && n.id !== ROOT) rows.push([n.id + " at signoff, later", n.signoff]);
    S.push(step("code", "apply", "plain Python · one flow run, " + (n.stage || "") + " onward, stopped after global routing", [fx(n.seconds, 0) + " s"], [
      settings.length ? grid(settings, function (r) { return r["on this path"] === "set by this run"; })
        : el("p", null, "No knob set: every setting is the flow's own."),
      rows.length ? numbers(rows) : null,
      n.score_est != null ? el("p", null, "Kind of layout: " + n.kind + ". " + (n.checked
        ? "A node of this kind has been evaluated, so the estimate above carries the correction that showed."
        : "No node of this kind was ever evaluated, so the estimate above is uncorrected and cannot be compared with other kinds.")) : null,
      n.why_not ? el("p", null, "Not a candidate: " + n.why_not + ".") : null,
      n.error ? el("pre", { "class": "j-text" }, n.error) : null,
      n.note && n.state !== "candidate" && n.state !== "screened" ? el("p", null, n.note) : null,
      n.best_after != null ? el("p", { "class": "mono" }, "best candidate after this run, as estimated now: " + fx(n.best_after, 4)) : null
    ]));
    S.closing();
    return [el("p", { "class": "lede" }, ledeFor(m)), el("div", { "class": "flow" }, parts)];
  }

  function checkRows(c) {
    var rows = [];
    if (c.estimate) rows.push(["what the search believed", c.estimate, "est"]);
    if (c.signoff) rows.push(["what signoff found", c.signoff]);
    return rows;
  }
  function evaluateMovePage(m) {
    var c = m.check || {}, parts = [], S = agentSteps(m, parts);
    S.navigator();
    if (m.navigator) S.push(step("view", "plan", "plain Python · checks the move", null, [
      el("p", null, m.corrected ? "The navigator's move was not a legal one and was replaced." : m.node + " may be evaluated: it is finished, has not been evaluated, and its state after global routing is still stored.")]));
    S.push(step("code", "sign_off", "plain Python · one flow run: detailed routing, DRC, LVS", [fx(c.seconds, 0) + " s"], [
      checkRows(c).length ? numbers(checkRows(c)) : null,
      el("p", null, el("span", { "class": "pill" + (/^passed/.test(c.outcome || "") ? " good" : " bad") }, c.outcome || ""),
        c.problems ? "  " + c.problems.join("; ") : ""),
      el("p", null, "Kind of layout: " + (c.kind || NODE[m.node].kind) + ". " + (c.kind_already_checked
        ? "A node of this kind had been evaluated before, so this one adds to what is known about its estimates."
        : "This was the first node of its kind to be evaluated. Until now its estimate could not be compared with anything else in the tree; from here on every estimate of this kind is corrected by what this run showed."))
    ]));
    S.closing();
    return [el("p", { "class": "lede" }, ledeFor(m)), el("div", { "class": "flow" }, parts)];
  }

  function endPage() {
    if (!RUN.finished) return [el("p", { "class": "lede" }, "This search had not finished when the page was made, so there is no answer and no score yet.")];
    var rows = [], s = RUN.score || {}, w = s.weights || RUN.weights, vs = s.vs_baseline || {};
    RUN.checks.forEach(function (a) {
      var when = a.when === "end" ? "at the end" : "during the search";
      if (a.estimate) rows.push(el("tr", { "class": "est" }, el("td", null, a.node), el("td", null, when), el("td", null, "estimate"),
        el("td", { "class": "num" }, fx(a.estimate.score_est, 4)), el("td", { "class": "num" }, fx(a.estimate.ecp_ns, 3)),
        el("td", { "class": "num" }, fx(a.estimate.hold_slack_ns, 3)), el("td", { "class": "num" }, fx(a.estimate.power_vs_baseline, 3)),
        el("td", { "class": "num" }, fx(a.estimate.area_vs_baseline, 3)), el("td", null, "")));
      var so = a.signoff || {};
      rows.push(el("tr", { "class": a.node === RUN.final_node ? "hit" : null }, el("td", null, a.estimate ? "" : a.node), el("td", null, a.estimate ? "" : when),
        el("td", null, a.signoff ? "signoff" : ""),
        el("td", { "class": "num" }, fx(so.score, 4)), el("td", { "class": "num" }, fx(so.ecp_ns, 3)),
        el("td", { "class": "num" }, fx(so.hold_slack_ns, 3)), el("td", { "class": "num" }, fx(so.power_vs_baseline, 3)),
        el("td", { "class": "num" }, fx(so.area_vs_baseline, 3)),
        el("td", { "class": "wrap" }, a.outcome + (a.problems ? ": " + a.problems.join("; ") : ""))));
    });
    var terms = [["timing", "effective clock period"], ["power", "total power"], ["area", "cell area"]];
    var formula = terms.filter(function (t) { return w && w[t[0]]; }).map(function (t) {
      return "(1 / " + fx(vs[t[1]], 4) + ")^" + w[t[0]];
    }).join("  ×  ");
    var kinds = (RUN.kinds || []).map(function (k) {
      var c = k.correction;
      return { kind: k.kind, nodes: k.nodes, evaluated: k.evaluated,
        "real over estimated: clock period": c ? c.timing : "unchecked", power: c ? c.power : "", "cell area": c ? c.area : "" };
    });
    return [
      el("p", { "class": "lede" }, "The answer is the best node that has been evaluated and passes the limits. When the search stops, the flow runs still in hand go to candidates that have not been evaluated and whose estimate puts them above it: best first, one run each, at most three."),
      el("div", { "class": "flow" },
        step("code", "finish", "plain Python · every evaluation of this run", [el("b", null, "policy.py"), "  ·  which results may be put forward"], [
          rows.length ? el("div", { "class": "scroll" }, el("table", { "class": "grid" },
            el("thead", null, el("tr", null, ["node", "made", "", "score", "ECP ns", "hold slack ns", "power ×", "cell area ×", "outcome"].map(function (h, i) {
              return el("th", { "class": i > 2 && i < 8 ? "num" : null }, h); }))),
            el("tbody", null, rows)))
            : el("p", null, "Nothing was evaluated: no estimate put any node above the baseline."),
          RUN.fell_back ? el("p", null, "Nothing that was evaluated passed and beat the baseline, so the baseline is the answer and the score is 1.") : null,
          kinds.length > 1 || (kinds[0] && kinds[0].evaluated > 1) ? [el("p", { "class": "cap" }, "What the evaluations showed about each kind of layout"), grid(kinds)] : null]),
        el("div", { "class": "link" }),
        step("code", "score", "plain Python · the figure of merit", [el("b", null, "pd/ledger.py")], [
          el("p", { "class": "formula" }, "score = (ECP₀ / ECP)^timing × (P₀ / P)^power × (A₀ / A)^area"),
          formula ? el("p", { "class": "formula" }, "      = " + formula + "  =  " + fx(s.score_before_gate, 4)) : null,
          el("dl", { "class": "kv" },
            el("dt", null, "answer"), el("dd", null, RUN.final_node),
            el("dt", null, "score"), el("dd", { "class": "mono" }, fx(s.score, 4) + (s.zeroed_because && s.zeroed_because.length ? "   zeroed: " + s.zeroed_because.join("; ") : "")),
            el("dt", null, "setup slack"), el("dd", { "class": "mono" }, fx(s.final_setup_slack_ns, 3) + " ns at the tt corner"),
            el("dt", null, "hold slack"), el("dd", { "class": "mono" }, fx(s.final_hold_slack_ns, 3) + " ns at the tt corner"))]))
    ];
  }

  /* ---------------------------------------------------------- rail, chart, selection */
  function railRow(key, id, tag, what, value, dotClass, title, depth) {
    return el("li", null, el("button", { type: "button", "class": "run", "data-key": key,
      "aria-current": sel === key ? "true" : null, style: depth ? "padding-left:" + (10 + 16 * depth) + "px" : null,
      onclick: function () { select(key); } },
      el("span", { "class": "nid" }, id), el("span", { "class": "stg" }, tag),
      el("span", { "class": "what" }, what),
      el("span", { "class": "val" }, value == null ? "" : fx(value, 4),
        dotClass ? el("span", { "class": "dot " + dotClass, title: title || dotClass }) : null)));
  }
  function nodeRow(n, key, depth) {
    var answer = RUN.finished && n.id === RUN.final_node;
    return railRow(key, n.id, n.stage || "base", n.parent ? "from " + n.parent : "untouched flow", n.score_est,
      answer ? "answer" : n.state, answer ? "the answer" : n.state, depth);
  }
  function drawRail() {
    var ol = document.getElementById("runs");
    ol.textContent = "";
    if (order === "time") {
      ol.appendChild(nodeRow(NODE[ROOT], ROOT, 0));
      RUN.moves.forEach(function (m) {
        if (m.type === "branch") { ol.appendChild(nodeRow(NODE[m.node], m.key, 0)); return; }
        var so = (m.check || {}).signoff;
        ol.appendChild(railRow(m.key, m.node, "sign", "evaluated", so ? so.score : null, "signed", (m.check || {}).outcome, 0));
      });
    } else {
      (function walk(id, depth) {
        ol.appendChild(nodeRow(NODE[id], MADE[id], depth));
        RUN.nodes.forEach(function (n) { if (n.parent === id) walk(n.id, depth + 1); });
      })(ROOT, 0);
    }
    ol.appendChild(railRow("end", "end", "sign", "the answer and its score", RUN.finished && RUN.score ? RUN.score.score : null, null, null, 0));
  }
  function drawChart() {
    var svg = document.getElementById("chart"), W = 320, H = 140, L = 34, R = 10, T = 10, B = 20;
    svg.textContent = "";
    var vals = [1];
    RUN.nodes.forEach(function (n) {
      if (n.score_est != null) vals.push(n.score_est);
      if (n.signoff && n.signoff.score != null) vals.push(n.signoff.score);
    });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi - lo) * 0.1 || 0.01;
    lo -= pad; hi += pad;
    var last = Math.max(1, RUN.nodes.length - 1);
    function X(i) { return L + i * (W - L - R) / last; }
    function Y(v) { return T + (hi - v) * (H - T - B) / (hi - lo); }
    var stepSize = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5].filter(function (s) { return (hi - lo) / s <= 5; })[0] || 1;
    for (var t = Math.ceil(lo / stepSize) * stepSize; t <= hi + 1e-9; t += stepSize) {
      svg.appendChild(sv("line", { x1: L, x2: W - R, y1: Y(t), y2: Y(t), stroke: "var(--line)", "stroke-width": 1 }));
      var lab = sv("text", { x: L - 5, y: Y(t) + 3, "text-anchor": "end" });
      lab.textContent = t.toFixed(stepSize < 0.01 ? 3 : 2);
      svg.appendChild(lab);
    }
    svg.appendChild(sv("line", { x1: L, x2: W - R, y1: Y(1), y2: Y(1), stroke: "var(--muted)", "stroke-width": 1, "stroke-dasharray": "3 3" }));
    [0, last].forEach(function (i) {
      var lab = sv("text", { x: X(i), y: H - 6, "text-anchor": i ? "end" : "start" });
      lab.textContent = i ? RUN.nodes[i].id : "baseline";
      svg.appendChild(lab);
    });
    var d = "";
    RUN.nodes.forEach(function (n, i) {
      if (n.best_after == null) return;
      d += d ? " H" + X(i).toFixed(1) + " V" + Y(n.best_after).toFixed(1) : "M" + X(i).toFixed(1) + "," + Y(n.best_after).toFixed(1);
    });
    if (d) svg.appendChild(sv("path", { d: d, fill: "none", stroke: "var(--good)", "stroke-width": 1.4, opacity: .75 }));
    var chosen = sel && MOVE[sel] ? MOVE[sel].node : sel;
    RUN.nodes.forEach(function (n, i) {
      var x = X(i), g = sv("g", { style: "cursor:pointer" }), title = sv("title");
      title.textContent = n.id + (n.score_est == null ? " – " + n.state : "  estimate " + n.score_est.toFixed(4) + (n.checked ? "" : " (unchecked kind)"));
      g.appendChild(title);
      if (n.score_est == null) {
        var y0 = H - B - 3;
        g.appendChild(sv("path", { d: "M" + (x - 3) + "," + (y0 - 3) + " l6,6 m0,-6 l-6,6", stroke: "var(--bad)", "stroke-width": 1.5, fill: "none" }));
        g.appendChild(sv("circle", { cx: x, cy: y0, r: 8, fill: "transparent" }));
      } else {
        var y = Y(n.score_est);
        if (n.signoff && n.signoff.score != null && n.id !== ROOT) {
          var ys = Y(n.signoff.score), answer = RUN.finished && n.id === RUN.final_node;
          g.appendChild(sv("line", { x1: x, x2: x, y1: y, y2: ys, stroke: "var(--muted)", "stroke-width": 1 }));
          g.appendChild(sv("path", { d: "M" + x + "," + (ys - 5) + " l5,5 l-5,5 l-5,-5 z", fill: answer ? "var(--agent)" : "var(--surface)",
            stroke: answer ? "var(--agent)" : "var(--ink)", "stroke-width": 1.3 }));
        }
        if (chosen === n.id) g.appendChild(sv("circle", { cx: x, cy: y, r: 7.5, fill: "none", stroke: "var(--agent)", "stroke-width": 1.6 }));
        g.appendChild(sv("circle", { cx: x, cy: y, r: 3.6, "stroke-width": 1.4,
          fill: n.state === "candidate" && n.checked ? "var(--good)" : n.state === "baseline" ? "var(--ink)" : "var(--surface)",
          stroke: n.state === "candidate" ? "var(--good)" : n.state === "baseline" ? "var(--ink)" : "var(--muted)" }));
        g.appendChild(sv("circle", { cx: x, cy: y, r: 9, fill: "transparent" }));
      }
      g.addEventListener("click", function () { select(MADE[n.id] || ROOT); });
      svg.appendChild(g);
    });
  }
  function drawDetail() {
    var main = document.getElementById("detail"), i = KEYS.indexOf(sel), m = MOVE[sel], head, body;
    if (sel === "end") { head = [el("h2", null, "The answer and its score")]; body = endPage(); }
    else if (sel === ROOT) { head = [el("h2", null, ROOT + " · the baseline"), statePill(NODE[ROOT])]; body = baselinePage(); }
    else if (m.type === "evaluate") {
      var so = (m.check || {}).signoff;
      head = [el("h2", null, "Move " + i + " · evaluate " + m.node), so ? el("span", { "class": "mono" }, "score " + fx(so.score, 4)) : null];
      body = evaluateMovePage(m);
    } else {
      var n = NODE[m.node];
      head = [el("h2", null, "Move " + i + " · " + n.id + " · " + n.stage + " from " + n.parent), statePill(n),
        n.score_est != null ? el("span", { "class": "mono" }, "estimated score " + fx(n.score_est, 4) + (n.checked ? "" : ", unchecked kind")) : null];
      body = branchPage(m);
    }
    main.textContent = "";
    main.appendChild(el("div", { "class": "dhead" }, head, el("div", { "class": "nav" },
      el("button", { type: "button", id: "prev", disabled: i <= 0, onclick: function () { select(KEYS[i - 1]); } }, "← earlier"),
      el("button", { type: "button", id: "next", disabled: i >= KEYS.length - 1, onclick: function () { select(KEYS[i + 1]); } }, "later →"))));
    body.forEach(function (b) { if (b) main.appendChild(b); });
  }
  function select(key, quiet) {
    if (KEYS.indexOf(key) < 0) key = MADE[key] || (KEYS.length > 2 ? KEYS[1] : KEYS[0]);
    sel = key;
    drawRail(); drawChart(); drawDetail();
    if (!quiet) {
      try { history.replaceState(null, "", "#" + key); } catch (e) { /* a sandboxed frame may refuse */ }
      var cur = document.querySelector('.run[aria-current="true"]');
      if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "nearest" });
    }
  }

  /* ---------------------------------------------------------- header */
  (function header() {
    var s = RUN.score || {}, c = RUN.cost || {}, w = s.weights || RUN.weights || {}, vs = s.vs_baseline || {};
    var branches = RUN.moves.filter(function (m) { return m.type === "branch"; }).length;
    var offs = RUN.checks.filter(function (k) { return k.seconds != null; }).length;
    document.getElementById("title").textContent = RUN.work + " · " + (RUN.method === "agent" ? "four-agent search" : RUN.method + " search");
    var models = Object.keys(RUN.models).map(function (k) { return RUN.models[k]; })
      .filter(function (m, i, a) { return a.indexOf(m) === i; }).map(function (m) { return m.replace("openrouter/", ""); });
    document.getElementById("subtitle").textContent =
      branches + " branches and " + offs + " evaluations from the baseline, n0, at a " + RUN.clock_ns + " ns clock" +
      (models.length ? ", every agent on " + models.join(", ") : ", no language model") +
      ". A result is a candidate when its estimated hold slack is at least " + RUN.thresholds.hold_floor_ns + " ns" +
      (RUN.thresholds.power_ceiling ? " and its estimated power at most " + RUN.thresholds.power_ceiling + " × the baseline's." : "; power is not screened.");
    var facts = [["score", RUN.finished ? fx(s.score, 4) : "running", "lead"],
      ["weights timing / power / area", [w.timing, w.power, w.area].join(" / ")],
      ["ECP · power · cell area vs baseline", [fx(vs["effective clock period"], 3), fx(vs["total power"], 3), fx(vs["cell area"], 3)].join(" · ")],
      ["answer", RUN.finished ? RUN.final_node + (RUN.fell_back ? " (fell back)" : "") : "\u2013"],
      ["flow runs", c.flow_runs == null ? RUN.nodes.length + " so far" : c.flow_runs + " of " + c.flow_run_budget],
      ["model cost", c.usd == null || RUN.method !== "agent" ? "none" : usd(c.usd)]];
    if (RUN.note) { var nt = document.getElementById("note"); nt.textContent = RUN.note; nt.hidden = false; }
    var dl = document.getElementById("facts");
    facts.forEach(function (f) { dl.appendChild(el("div", { "class": f[2] || null }, el("dt", null, f[0]), el("dd", null, f[1]))); });
  })();

  document.getElementById("by-time").addEventListener("click", function () { setOrder("time"); });
  document.getElementById("by-tree").addEventListener("click", function () { setOrder("tree"); });
  function setOrder(o) {
    order = o;
    document.getElementById("by-time").setAttribute("aria-pressed", o === "time");
    document.getElementById("by-tree").setAttribute("aria-pressed", o === "tree");
    drawRail();
  }
  document.addEventListener("keydown", function (e) {
    if (e.target.closest && e.target.closest("input, textarea, select")) return;
    var i = KEYS.indexOf(sel);
    if (e.key === "ArrowLeft" && i > 0) select(KEYS[i - 1]);
    if (e.key === "ArrowRight" && i < KEYS.length - 1) select(KEYS[i + 1]);
  });
  select((location.hash || "").slice(1), true);
})();
</script>
"""


def render(data: dict, fragment: bool = False) -> str:
    body = BODY.replace("/*DATA*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    if fragment:
        return HEAD + body
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            + HEAD + "</head>\n<body>\n" + body + "</body>\n</html>\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work", help="the work directory of a finished or running search")
    ap.add_argument("-o", "--out", default=None, help="where to write the page (default WORK/run.html)")
    ap.add_argument("--fragment", action="store_true", help="omit the <html> and <body> wrapper")
    ap.add_argument("--note", default="", help="a sentence shown at the top of the page")
    a = ap.parse_args()
    work = Path(a.work).resolve()
    out = Path(a.out) if a.out else work / "run.html"
    out.write_text(render(build(work, a.note), a.fragment))
    print(f"  wrote {out}  ({out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
