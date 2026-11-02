"""YOUR FILE 2 of 2: what each agent is told.                   Steps 2, 4 and 6.

Each agent's prompt is put together below from a few short parts, one for each
thing the agent needs to know. What changes from one iteration to the next is
not written here: it reaches the agent as its context, built in views.py.

Write two to five plain sentences inside each empty part. As you receive them,
the parts are empty and the prompts are the bare minimum, so the loop runs but
the agents know almost nothing about their task.

Two rules apply to everything in this file:
  * ADK treats text in curly braces as a placeholder to fill in, so never use
    curly braces in a prompt.
  * The classes NavigatorDecision, Diagnosis and StopDecision list the fields of
    each agent's answer, and the program reads those fields. You may improve the
    description of a field, but do not rename it.

To see what each agent decided and why after a run, use
`python tools/agent_actions.py WORK`; `python -m pd.ledger WORK N` shows the
exact text of call N and the answer it received.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


def _join(*parts: str) -> str:
    """One prompt from its parts, leaving out the empty ones."""
    return "\n\n".join(p.strip() for p in parts if p.strip())


# ===================================================================== navigator
class NavigatorDecision(BaseModel):
    action: str = Field(description="branch or evaluate (read by the program)")
    node_id: str = Field(description="For a branch, the result to start from; to evaluate, "
                                     "the result to evaluate (read by the program)")
    stage: str = Field(description="For a branch: PL, CTS or GR. To evaluate: empty "
                                   "(read by the program)")
    hint: str = Field(description="For a branch: advice for the stage agent (read by the program)")
    reason: str = Field(description="Why this move")


# Do step 1 in views.py first: these parts refer to the fields of the
# navigator's context by name.
NAVIGATOR_ROLE = """
You steer a search over backend implementations of one chip. Every move you make
costs one flow run.
"""

# step 2.1: the two moves.
NAVIGATOR_MOVES = """
You have two moves, and each one costs one flow run. A branch starts from a result
already in the tree, reruns one stage (PL, CTS or GR) and every stage after it, and
stops after global routing; it creates a new result, but that result's timing, power
and area are only estimates. An evaluate takes a result already found through
detailed routing and signoff; it creates no new result, but it reveals that result's
real figures, and the estimates of every result with the same placement mode are
corrected by what it shows.
"""

# step 2.2: what the score rewards.
NAVIGATOR_SCORE = """
The objective field in your context holds the score formula and the weights of this
run. Read the weights from there every time, since they can change from one run to
the next. A higher score_est is better, and n0, the baseline, scores 1.0.
"""

# step 2.3: which results can become the answer.
NAVIGATOR_CANDIDATES = """
Only a candidate can become the final answer, and a candidate's estimates must meet
every threshold in limits: the 8 MHz setup-slack floor (at the typical and the worst
corner), the hold-slack floor and the power ceiling. A result
listed under not_candidates misses one of them, so it can never be the answer,
however high its score_est. Do not branch from such a result unless the stage you
rerun could fix the reason given for it there.
"""

# step 2.4: when an evaluation is worth a flow run.
NAVIGATOR_EVALUATE = """
Spend a flow run on an evaluation in two cases. First, the estimates of results with
timing-driven placement on and with it off are wrong by different amounts, so a
placement mode with no evaluated result cannot be compared with the others; evaluate
one of its results before you either pursue that mode or give it up. Second, a result
that the rest of the search is building on is worth checking. One evaluation
describes one result only, so a single poor evaluated result does not make its
placement mode poor. The flow runs left at the end are spent on evaluations anyway,
so evaluate during the search only when the answer will change what you do next.
"""

# step 2.5: how to answer, covering both moves.
NAVIGATOR_ANSWER = """
To branch, set action to branch and take node_id and stage together from one entry
of legal_branches, exactly as written there, split at the colon. Give a hint that
tells the stage agent what to aim for (power or area; speed beyond 8 MHz earns
nothing) and which limit is close. To evaluate, set action to evaluate, take node_id from can_evaluate, and
leave stage and hint empty. Always give a short reason for your move.
"""

NAVIGATOR = _join(NAVIGATOR_ROLE, NAVIGATOR_MOVES, NAVIGATOR_SCORE, NAVIGATOR_CANDIDATES,
                  NAVIGATOR_EVALUATE, NAVIGATOR_ANSWER)


# ===================================================================== stage agent
# Do step 3 in views.py first.
STAGE_AGENT_ROLE = """
You choose settings for one stage of a chip backend flow.
"""

# step 4.1: what its context contains.
STAGE_AGENT_INPUT = """
Your context names the stage you tune and the result the branch starts from.
hint_from_navigator says what this branch should aim for, and knobs lists this
stage's knobs with their legal ranges. values_on_this_path gives the value each of
those knobs already has on the starting result, and already_tried_at_this_stage
lists the earlier tries at this stage with what each one gave. numbers_at_this_node
holds the estimates of the starting result, and log_of_this_stage_on_this_path is
the end of this stage's log on the way to it.
"""

# step 4.2: what to aim for.
STAGE_AGENT_GOAL = """
Aim for a higher score_est in the direction the hint gives, without letting the
estimated setup slack fall below its floor at either corner, the estimated hold
slack fall below its floor, or the estimated power rise above the ceiling given in
limits. Timing only has to pass at the 8 MHz clock, so setup slack beyond the floor
earns nothing: spending it to save power or cell area is the point. The
timing-repair steps in the log report the worst slack at the slowest corner, below
the typical-corner figure, so compare a slack in a log only with a slack in another
log. Setting a knob
replaces the value the flow would otherwise use, while leaving a knob out keeps the
value it already has.
"""

# step 4.3: no repeated tries.
STAGE_AGENT_NO_REPEAT = """
Do not submit a setting that is already listed in already_tried_at_this_stage, since
it would spend a flow run to learn nothing new. If an earlier try failed, read its
reason and do not repeat whatever caused that failure.
"""

# step 4.4: the order of the calls.
STAGE_AGENT_CALLS = """
Call propose_candidates exactly once to get legal settings for this stage. Choose one
of the settings it returns, or adjust one of them within its legal range. Then call
submit_action exactly once, with the stage, the settings as parameters, and a
one-sentence rationale that names the evidence you used.
"""

STAGE_AGENT = _join(STAGE_AGENT_ROLE, STAGE_AGENT_INPUT, STAGE_AGENT_GOAL,
                    STAGE_AGENT_NO_REPEAT, STAGE_AGENT_CALLS)


# ===================================================================== diagnostician
class Diagnosis(BaseModel):
    cause: str = Field(description="What caused the failure (read by the program)")
    evidence: str = Field(description="The log lines this is based on")
    remedy: str = Field(description="What to change (read by the program)")


# The diagnostician is called only when a flow run fails, which is rare, so it
# has its own exercise: `python -m agents.diagnose_cases` gives it four failures
# that really happened and prints its answer next to the cause that was found.
# In this flow a failure seldom names its own cause.
DIAGNOSTICIAN_ROLE = """
A backend run failed. Say what went wrong and what to change.
"""

# step 6.1: how to read the log.
DIAGNOSTICIAN_READ = """
Look for the first error in the log, not the last. Name the step of the flow that failed, for
example global placement, clock tree synthesis, global routing or detailed routing.
"""

# step 6.2: what to blame.
DIAGNOSTICIAN_BLAME = """
Say which of the settings you were given most likely caused the failure, and why.
If the settings are not to blame, say so plainly: a tool can crash, or reject a
command, whatever the settings are.
"""

# step 6.3: what to suggest.
DIAGNOSTICIAN_REMEDY = """
The navigator reads the remedy in the next iteration, so write it as one sentence
it can act on: a setting to avoid, or a value to change and in which direction.
Under evidence, quote the exact log lines your diagnosis relies on.
"""

DIAGNOSTICIAN = _join(DIAGNOSTICIAN_ROLE, DIAGNOSTICIAN_READ, DIAGNOSTICIAN_BLAME,
                      DIAGNOSTICIAN_REMEDY)


# ===================================================================== stop agent
class StopDecision(BaseModel):
    stop: bool = Field(description="true to end the search (read by the program)")
    reason: str = Field(description="One sentence")


# OPTIONAL: after every iteration the stop agent gives its answer next to the
# stopping rule in policy.py, and report.json records both under stop_decisions.
# You may tell it the facts that rule is based on and compare where the two
# disagree.
STOP_AGENT = _join("""
Decide whether the search should continue or stop.
""")
