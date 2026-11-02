"""YOUR FILE 1 of 2: what each agent is given as its context.    Steps 1, 3 and 5.

The agents do not share a conversation. Each agent receives only what the step
before it returns, so the context of every agent is built here, from the running
search, and sent to the agent as text. Everything in a context is paid for every
time that agent is called, because the model is charged for the text it reads.

Each function below is a short list of assignments. Replace every `None` with
the expression described in the comment above it; each one is a single
expression built from `ep`, the running search (see pd/episode.py). As long as
a function still contains a `None`, it gives its agent everything instead:
every result, every number and every log excerpt. The loop works that way, but
it is expensive, and the few numbers that matter are hard to find.

To see what a context costs after a run, `python -m pd.ledger WORK` lists every
model call with the number of input tokens, and `python -m pd.ledger WORK N`
shows the full text of call N.
"""
from __future__ import annotations

from dataclasses import asdict

from pd import stages as S
from pd.episode import Episode
from pd.tree import Node


def _everything(ep: Episode) -> dict:
    """Every result, with every number and every log excerpt it carries. Each
    function below returns this until all of its lines are filled in."""
    nodes = []
    for nid in ep.tree.order:
        n = asdict(ep.tree.nodes[nid])
        n.pop("stage_states", None)
        n.pop("store", None)
        n["score_est"] = ep.tree.est_score(nid)
        n["effective_clock_period_ns"] = ep.tree.ecp(nid)
        nodes.append(n)
    return {
        "nodes": nodes,
        "budget": ep.budget(),
        "legal_branches": [f"{n}:{s}" for n, s in ep.options()],
        "knobs": S.cheat_sheet(ep.tree.bounds()),
    }


def _unfilled(*parts) -> bool:
    return any(p is None for p in parts)


# ===================================================================== navigator
def navigator_view(ep: Episode) -> dict:
    """The navigator's context, built once per iteration before it chooses a move."""
    # step 1.1: what the score rewards in this run.
    objective = ep.objective()

    # step 1.2: the results of the search so far.
    search_so_far = ep.tree.summary()

    # step 1.3: the two thresholds a result's estimates must meet to be a candidate.
    limits = ep.limits()

    # step 1.4: the budget.
    budget = ep.budget()

    # step 1.5: the branches the navigator may choose, written as "result:stage".
    legal_branches = [f"{n}:{s}" for n, s in ep.options()]

    if _unfilled(objective, search_so_far, limits, budget, legal_branches):
        return _everything(ep)                  # as you received it
    return {
        "objective": objective,
        "search_so_far": search_so_far,
        "limits": limits,
        "budget": budget,
        "legal_branches": legal_branches,
        "stages": {s.name: s.note for s in S.STAGES},   # what each stage is for
    }


# ===================================================================== stage agent
def stage_view(ep: Episode, node_id: str, stage: str, hint: str) -> dict:
    """The stage agent's context. The agent sets the knobs of one stage (PL, CTS
    or GR) for a branch that starts from the result `node_id`; `hint` is the
    navigator's advice for this branch."""
    node = ep.tree.nodes[node_id]

    # step 3.1: the knobs of this stage only, with their legal ranges.
    knobs = S.cheat_sheet(ep.tree.bounds(), only=stage)

    # step 3.2: the values these knobs already have on the result the branch starts from.
    values_on_this_path = {k: node.params.get(k, "flow default") for k in S.BY_NAME[stage].params}

    # step 3.3: what was already tried at this stage, and what each try gave.
    already_tried = ep.tree.tried(stage)

    # step 3.4: the numbers of the result the branch starts from.
    numbers_at_this_node = ep.tree.row(node_id)

    # step 3.5: how this stage went on the way to that result.
    log_of_this_stage = ep.tree.digest_for(node_id, stage)

    if _unfilled(knobs, values_on_this_path, already_tried, numbers_at_this_node,
                 log_of_this_stage):
        return {                                # as you received it
            "stage": stage,
            "resuming_from_node": node_id,
            "hint_from_navigator": hint,
            "knobs": S.cheat_sheet(ep.tree.bounds()),
            "numbers_at_this_node": node.metrics,
            "logs": {s: ep.tree.digest_for(node_id, s) for s in S.NAMES},
            "all_nodes": _everything(ep)["nodes"],
        }
    return {
        "stage": stage,
        "resuming_from_node": node_id,
        "hint_from_navigator": hint,
        "objective": ep.objective(),
        "limits": ep.limits(),
        "knobs": knobs,
        "values_on_this_path": values_on_this_path,
        "already_tried_at_this_stage": already_tried,
        "numbers_at_this_node": numbers_at_this_node,
        "log_of_this_stage_on_this_path": log_of_this_stage,
    }


# ===================================================================== stop agent
def stop_view(ep: Episode) -> dict:
    """The stop agent's context, built once per iteration. The agent answers one
    question, whether to stop or continue, and needs only a few numbers."""
    # step 5.1: the budget, including candidates_waiting_for_evaluation.
    budget = ep.budget()

    # step 5.2: the best estimated score among candidates after each run.
    best_score_est_after_each_run = ep.tree.history()

    # step 5.3: the score at signoff of the best evaluated result.
    best_evaluated_score = round(ep.best_evaluated()[1], 4)

    if _unfilled(budget, best_score_est_after_each_run, best_evaluated_score):
        return _everything(ep)                  # as you received it
    return {
        "budget": budget,
        "best_score_est_after_each_run": best_score_est_after_each_run,
        "best_evaluated_score": best_evaluated_score,
    }


# ===================================================================== diagnostician
def failure_view(ep: Episode, node: Node) -> dict:
    """The diagnostician's context, built only when a flow run fails: the error,
    the settings that caused it, and the end of the log. It is complete; there
    is nothing to change here."""
    return ep.failure_context(node)
