"""STAFF FILE — the plumbing between the four agents. Not for editing.

Eight plain-Python nodes and four LLM agents. The agents' instructions live in
student/prompts.py, what each one is shown in student/views.py, the rule-based
decisions in student/policy.py; this file only moves data between them and the
episode.

Three ADK behaviours shape the code here, each found by running it:

  * A function node chooses its outgoing edge by RETURNING an Event that carries
    the route. Assigning ctx.actions.route is silently ignored and the branch
    simply ends.
  * Nodes do not share a conversation. An agent receives the previous node's
    return value as its input and nothing else, so every agent is preceded by a
    node that builds exactly what it should see.
  * Workflow state is typed and enforced: writing a key that LoopState does not
    declare raises StateSchemaError.
"""
from __future__ import annotations

import json
import random
import re
from typing import Any

from pydantic import BaseModel, Field

from google.adk.agents import LlmAgent
from google.adk.events import Event, EventActions
from google.adk.workflow import node

from pd import names, stages as S
from pd.episode import Episode

from .compat import policy, prompts, views      # the student's three files, old names settled


class LoopState(BaseModel):
    """Small control data only. The tree, the ledger and every design file stay
    on disk in the episode's work directory."""
    iteration: int = 0
    decision: dict[str, Any] = Field(default_factory=dict)
    last_failed: bool = False


# One episode per process. The nodes, the stage agent's tools and the cost
# clients all act on this object.
_EP: Episode | None = None
_CFG: dict = {}
_PENDING: dict = {}          # the branch being prepared in the current iteration


def configure(**cfg) -> None:
    global _EP
    _EP = None
    _CFG.clear()
    _CFG.update(cfg)
    _PENDING.clear()


def episode() -> Episode:
    if _EP is None:
        raise RuntimeError("the baseline node has not run yet")
    return _EP


def current_episode() -> Episode | None:
    return _EP


def _say(msg: str) -> None:
    log = _CFG.get("log")
    if log:
        log(msg)


def _as_dict(x: Any) -> dict:
    """An agent's answer as a dict, whether ADK hands over a dict, a model
    object or JSON text (sometimes wrapped in a code fence)."""
    if isinstance(x, dict):
        return x
    if hasattr(x, "model_dump"):
        return x.model_dump()
    if isinstance(x, str):
        m = re.search(r"\{.*\}", x, re.S)
        if m:
            try:
                v = json.loads(m.group(0))
                return v if isinstance(v, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


# ------------------------------------------------------------------ 1 · baseline
@node(name="baseline")
async def baseline(ctx) -> dict:
    """Run the untouched flow. It becomes the root of the tree and the reference
    every later result is scored against."""
    global _EP
    _say("  baseline …")
    _EP = Episode.start(_CFG["design"], _CFG["work"], _CFG["clock_ns"],
                        ledger=_CFG["ledger"], keep=_CFG.get("keep", 6),
                        hold_floor=policy.HOLD_FLOOR_NS, power_ceiling=policy.POWER_CEILING,
                        weights=_CFG.get("weights"))
    root = _EP.tree.nodes[_EP.tree.order[0]]
    _say(_EP.line(root, "(remembered from an earlier run)" if _EP.baseline_from_cache else ""))
    return {"baseline_ecp_ns": _EP.tree.ecp(root.id)}


# ------------------------------------------------------------------ 2 · view for the navigator
@node(name="navigator_view")
async def navigator_view(ctx) -> dict:
    return views.navigator_view(episode())


# ------------------------------------------------------------------ 3 · navigator
def make_navigator(model) -> LlmAgent:
    return LlmAgent(model=model, name="navigator", instruction=prompts.NAVIGATOR,
                    output_schema=prompts.NavigatorDecision)      # fixed answer fields, no tools


# ------------------------------------------------------------------ 4 · plan
def _default_branch(ep: Episode) -> tuple[str | None, str | None]:
    """Where to go when the navigator names a branch that does not exist: the first
    legal branch on the best node, else any legal branch."""
    options = ep.options()
    inc = ep.tree.incumbent()
    for n, s in options:
        if n == inc:
            return n, s
    return options[0] if options else (None, None)


@node(name="plan")
async def plan(ctx, node_input: Any = None) -> Event:
    """Check the navigator's move is a legal one, then send it down the right path:
    a branch to the stage agent, with the view built for it; an evaluation
    straight to the flow, which takes the node through signoff.

    An illegal move is corrected here rather than discovered after a run, and
    the correction is recorded so it shows up in the report.
    """
    ep = episode()
    raw = _as_dict(node_input)
    nid = raw.get("node_id")
    stage = str(raw.get("stage", "")).upper().strip()
    # "evaluate", or "signoff", its name before the rename (pd/names.py)
    wants_evaluate = names.move(raw.get("action", "branch")) == "evaluate"
    reason = str(raw.get("reason", ""))[:500]
    _PENDING.clear()

    if wants_evaluate and nid in ep.tree.can_evaluate() and not ep.ledger.must_stop():
        decision = {"action": "evaluate", "node_id": nid, "corrected": False, "reason": reason}
        _PENDING.update(node_id=nid, reason=reason)
        ctx.actions.state_delta.update({"decision": decision})
        _say(f"       navigator -> evaluate {nid}   {reason[:100]}")
        return Event(author="plan", actions=EventActions(route="evaluate"), output={"evaluate": nid})

    corrected = wants_evaluate or (nid, stage) not in ep.options()
    if corrected:
        nid, stage = _default_branch(ep)
        ep.corrections += 1
    decision = {"action": "branch", "node_id": nid, "stage": stage, "corrected": corrected,
                "hint": str(raw.get("hint", ""))[:500], "reason": reason}
    _PENDING.update(node_id=nid, stage=stage, reason=reason, proposals=0)
    ctx.actions.state_delta.update({"decision": decision})
    _say(f"       navigator -> {nid}:{stage}" + ("  (corrected: not a legal move)" if corrected else "")
         + f"   {reason[:90]}")
    view = {"error": "no legal branch is available"} if nid is None else \
        views.stage_view(ep, nid, stage, decision["hint"])
    return Event(author="plan", actions=EventActions(route="branch"), output=view)


@node(name="sign_off")
async def sign_off(ctx) -> dict:
    """Spend one flow run on the truth about a node the search already has."""
    ep = episode()
    rec = ep.sign_off(_PENDING.get("node_id"))
    it = int(ctx.state.get("iteration", 0)) + 1
    ctx.actions.state_delta.update({"iteration": it, "last_failed": False})
    _say(ep.check_line(rec))
    return {"node": rec["node"], "outcome": rec["outcome"]}


# ------------------------------------------------------------------ 5 · stage agent and its tools
def propose_candidates(stage: str, count: int = 4) -> dict:
    """Return a few legal settings for one stage.

    Args:
      stage: PL, CTS or GR.
      count: how many settings to return, at most 6.
    """
    ep = episode()
    stage = str(stage).upper().strip()
    if stage not in S.BY_NAME:
        return {"error": f"unknown stage {stage!r}", "valid_stages": list(S.NAMES)}
    _PENDING["proposals"] = _PENDING.get("proposals", 0) + 1
    rng = random.Random(len(ep.tree.order) * 131 + _PENDING["proposals"]
                        + _CFG.get("seed", 0) * 7919)
    n = max(1, min(int(count or 4), 6))
    return {"stage": stage,
            "candidates": policy.propose(stage, ep.tree.bounds(),
                                         ep.tree.tried(stage, limit=50), rng, n)}


def submit_action(stage: str, parameters: dict, rationale: str) -> dict:
    """Commit to one setting for the stage you were asked to tune. Call once.

    Args:
      stage: the stage you were asked to tune.
      parameters: knob name to value, every value inside its legal range.
      rationale: what in the log or the numbers led to this choice.
    """
    ep = episode()
    stage = str(stage).upper().strip()
    want = _PENDING.get("stage")
    if stage != want:
        return {"accepted": False, "problems": [f"you were asked to tune {want}, not {stage}"]}
    bounds = ep.tree.bounds()
    params = S.coerce(parameters or {}, bounds)
    mine = S.BY_NAME[stage].params
    problems = [f"{k} is not a {stage} knob" for k in params if k not in mine]
    problems += S.validate({k: v for k, v in params.items() if k in mine}, bounds)
    if not params:
        problems.append("no parameters given")
    if problems:
        return {"accepted": False, "problems": problems,
                "legal_ranges": S.cheat_sheet(bounds, only=stage)}
    _PENDING["parameters"] = params
    _PENDING["rationale"] = str(rationale)[:400]
    return {"accepted": True, "submitted": params}


def make_stage_agent(model) -> LlmAgent:
    return LlmAgent(model=model, name="stage_agent", instruction=prompts.STAGE_AGENT,
                    tools=[propose_candidates, submit_action])   # tools, no fixed answer fields


# ------------------------------------------------------------------ 6 · apply
@node(name="apply")
async def apply(ctx) -> Event:
    """Spend one flow run on what the stage agent submitted."""
    ep = episode()
    nid, stage = _PENDING.get("node_id"), _PENDING.get("stage")
    params, why = _PENDING.get("parameters"), _PENDING.get("rationale", "")
    if params is None and nid is not None:
        # The agent talked instead of calling submit_action. Keep the iteration
        # useful, and count it: a high number means the prompt needs work.
        ep.fallbacks += 1
        params = S.sample(stage, random.Random(len(ep.tree.order)), ep.tree.bounds())
        why = "stage agent submitted nothing; a sampled setting was used"

    n = ep.branch(nid, stage, params or {}, note=why)
    it = int(ctx.state.get("iteration", 0)) + 1
    ctx.actions.state_delta.update({"iteration": it, "last_failed": not n.ok})

    e = ep.tree.est_score(n.id)
    mine = {k: v for k, v in (params or {}).items() if stage in S.BY_NAME and k in S.BY_NAME[stage].params}
    _say(ep.line(n, json.dumps(mine)))

    if n.ok:
        return Event(author="apply", actions=EventActions(route="ok"),
                     output={"node": n.id, "score_est": e})
    if n.seconds == 0:
        # Refused before anything ran; the reason is exact, no diagnosis needed.
        return Event(author="apply", actions=EventActions(route="refused"),
                     output={"node": n.id, "refused": n.error})
    return Event(author="apply", actions=EventActions(route="failed"),
                 output=views.failure_view(ep, n))


# ------------------------------------------------------------------ 7 · diagnostician
def make_diagnostician(model) -> LlmAgent:
    return LlmAgent(model=model, name="diagnostician", instruction=prompts.DIAGNOSTICIAN,
                    output_schema=prompts.Diagnosis)


# ------------------------------------------------------------------ 8 · view for the stop agent
@node(name="stop_view")
async def stop_view(ctx, node_input: Any = None) -> dict:
    """Build the stop agent's numbers. If this iteration went through the
    diagnostician, file its finding on the failed node first, so the navigator
    reads it next time round."""
    ep = episode()
    d = _as_dict(node_input)
    if d.get("cause") and ep.tree.order:
        last = ep.tree.nodes[ep.tree.order[-1]]
        if not last.ok:
            last.note = f"{d.get('cause', '')} Remedy: {d.get('remedy', '')}"[:500]
            ep.save()
            _say(f"       diagnosis: {last.note[:150]}")
    return views.stop_view(ep)


# ------------------------------------------------------------------ 9 · stop agent
def make_stop_agent(model) -> LlmAgent:
    return LlmAgent(model=model, name="stop_agent", instruction=prompts.STOP_AGENT,
                    output_schema=prompts.StopDecision)


# ------------------------------------------------------------------ 10 · gate
@node(name="gate")
async def gate(ctx, node_input: Any = None) -> Event:
    """Decide continue or stop, and record what the rule and the stop agent each said.

    Hard limits always win: no agent talks its way past a spent budget. Beyond
    that, policy.STOP_POLICY chooses whose judgement counts.
    """
    ep = episode()
    d = _as_dict(node_input)
    agent_stop = bool(d["stop"]) if "stop" in d else None
    rule_stop, rule_why = policy.should_stop(ep.tree.history(), ep.budget())
    hard = ep.hard_stop()

    pol = _CFG.get("stop_policy") or policy.STOP_POLICY
    if hard:
        stop, why = True, hard
    elif pol == "agent":
        stop, why = bool(agent_stop), f"stop agent: {d.get('reason', '')}"
    elif pol == "either":
        stop = rule_stop or bool(agent_stop)
        why = f"rule: {rule_why}" if rule_stop else f"stop agent: {d.get('reason', '')}"
    else:
        stop, why = rule_stop, f"rule: {rule_why}"

    hist = ep.tree.history()
    ep.ledger.decisions.append({
        "after_run": len(ep.tree.order) - 1,
        "best_score_est": hist[-1] if hist else None,
        "rule_says_stop": rule_stop, "stop_agent_says_stop": agent_stop,
        "stop_agent_reason": str(d.get("reason", ""))[:200],
        "hard_limit": hard, "stopped": stop,
    })
    ep.save()
    if stop:
        _say(f"       stop: {why[:140]}")
    return Event(author="gate", actions=EventActions(route="stop" if stop else "continue"),
                 output={"stop": stop, "why": why})


# ------------------------------------------------------------------ 11 · the last evaluations and the score
@node(name="finish")
async def finish(ctx) -> dict:
    """Evaluate what is still worth evaluating, then score the best of
    everything that has been."""
    ep = episode()
    _say("  evaluations at the end ...")
    before = len(ep.checks)
    rep = ep.finish({"method": "agent", "models": dict(policy.ROLE_MODEL),
                     "stop_policy": _CFG.get("stop_policy") or policy.STOP_POLICY})
    for rec in ep.checks[before:]:
        _say(ep.check_line(rec))
    return {"score": rep["score"]["score"], "final_node": rep["final_node"]}
