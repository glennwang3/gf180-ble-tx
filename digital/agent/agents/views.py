"""What each agent is given as its context.

The agents do not share a conversation. Each agent receives only what the step
before it returns, so the context of every agent is built here, from the running
search (`ep`, see pd/episode.py), and sent to the agent as text. Everything in a
context is paid for every time that agent is called, because the model is charged
for the text it reads, so each view holds only what its agent decides on.

To see what a context costs after a run, `python -m pd.ledger WORK` lists every
model call with the number of input tokens, and `python -m pd.ledger WORK N`
shows the full text of call N.
"""
from __future__ import annotations

from pd import stages as S
from pd.episode import Episode
from pd.tree import Node


def navigator_view(ep: Episode) -> dict:
    """The navigator's context, built once per iteration before it chooses a move."""
    return {
        "objective": ep.objective(),                    # what the score rewards, with this run's weights
        "search_so_far": ep.tree.summary(),             # the results found so far
        "limits": ep.limits(),                          # what a result's estimates must meet to be a candidate
        "budget": ep.budget(),
        "legal_branches": [f"{n}:{s}" for n, s in ep.options()],     # "result:stage"
        "stages": {s.name: s.note for s in S.STAGES},   # what each stage is for
    }


def stage_view(ep: Episode, node_id: str, stage: str, hint: str) -> dict:
    """The stage agent's context. The agent sets the knobs of one stage (FP, PL,
    CTS or GR) for a branch that starts from the result `node_id`; `hint` is the
    navigator's advice for this branch."""
    node = ep.tree.nodes[node_id]
    width = ep.tree.width(node_id)
    return {
        "stage": stage,
        "resuming_from_node": node_id,
        "hint_from_navigator": hint,
        "objective": ep.objective(),
        "limits": ep.limits(),
        # this stage's knobs and ranges; the density floor follows this node's die width
        "knobs": S.cheat_sheet(ep.tree.bounds(node_id), only=stage),
        "values_on_this_path": {k: node.params.get(k, width if k == S.WIDTH else "flow default")
                                for k in S.BY_NAME[stage].params},
        "already_tried_at_this_stage": ep.tree.tried(stage),
        "numbers_at_this_node": {
            **ep.tree.row(node_id),
            # how full the core starts on this node's die; a floorplan branch changes it
            "starting_utilisation_predicted": (None if ep.tree.facts is None or width is None
                                               else round(ep.tree.facts.utilisation(width), 3)),
        },
        "log_of_this_stage_on_this_path": ep.tree.digest_for(node_id, stage),
    }


def stop_view(ep: Episode) -> dict:
    """The stop agent's context, built once per iteration. The agent answers one
    question, whether to stop or continue, and needs only a few numbers."""
    return {
        "budget": ep.budget(),      # includes candidates_waiting_for_evaluation
        "best_score_est_after_each_run": ep.tree.history(),
        "best_evaluated_score": round(ep.best_evaluated()[1], 4),
    }


def failure_view(ep: Episode, node: Node) -> dict:
    """The diagnostician's context, built only when a flow run fails: the error,
    the settings that caused it, and the end of the log."""
    return ep.failure_context(node)
