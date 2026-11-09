"""The rules the search works under: candidate thresholds, stopping rule, models.

  HOLD_FLOOR_NS, POWER_CEILING   which results may be chosen as the final answer
  STOP_POLICY, should_stop       when the search ends
  ROLE_MODEL                     which model each agent uses
  propose                        how possible settings are offered to the stage agent
"""
from __future__ import annotations

import random

from pd import stages as S

# ===================================================================== which results may be the answer
# The final answer must pass signoff: hold slack of at least 0 ns at the typical
# (tt) corner, and total power at most 1.05 times the baseline's; otherwise the
# score is zero. During the search, however, a result is known only through its
# estimates, which are read after global routing and differ from what signoff
# later finds. The two thresholds below therefore decide, from the estimates
# alone, which results are candidates: only a candidate can be chosen as the
# final answer or evaluated at the end of the search.
#
# Both values come from test runs on picorv32, in which each estimate was
# compared with the signoff result of the same layout.
#
# BLE TX: both were calibrated on picorv32, not on ble_tx. After the
# first few ble_tx searches, compare estimate_vs_signoff in report.json and
# retune them. The 8 MHz setup gate lives in pd/ledger.py (SETUP_FLOOR_NS).

# Hold slack at signoff was lower than its estimate, by up to about 0.35 ns; the
# baseline itself shows 0.34 ns after global routing and 0.07 ns at signoff. A
# result therefore needs an estimated hold slack of at least 0.30 ns. This keeps
# out the results most likely to end with a negative hold slack, at the cost of
# also keeping out some that would have passed.
HOLD_FLOOR_NS = 0.30     # estimated hold slack (ns) a candidate needs

# Estimated power, once a result of the same placement mode had been evaluated
# and the estimates adjusted, was within about 0.02 of the signoff value. The
# ceiling is therefore the signoff limit itself: 1.05 times the baseline's power.
POWER_CEILING = 1.05     # estimated power / the baseline's; None would mean "not checked"

# ===================================================================== when the search ends
# After every iteration both the stopping rule below and the stop agent say
# whether to continue. STOP_POLICY chooses which of them is obeyed:
#   "rule"    should_stop() below; the stop agent's answer is only recorded
#   "agent"   the stop agent
#   "either"  whichever says stop first
# The search also always ends when a budget is spent or no branch is left.
STOP_POLICY = "rule"

PATIENCE = 10       # number of runs to wait for an improvement
MIN_GAIN = 0.002    # relative rise in the best estimated score that counts as one
SPARE_RUNS = 2      # the most flow runs kept back for evaluations at the end


def should_stop(best_after_each_run: list[float], budget: dict) -> tuple[bool, str]:
    """Called once per iteration. Returns (stop, reason).

    `best_after_each_run` is the best estimated score among candidates after
    each run, starting with the baseline's 1.0. `budget` is the same budget the
    stop agent receives, including `candidates_waiting_for_evaluation`.

    The rule stops the search for one of two reasons.

    The first is to keep flow runs for the end. When the search stops, the runs
    left over evaluate the best candidates that have not been evaluated, up to
    three, and the best of everything evaluated becomes the answer. The program
    always holds back one run for the first of these candidates. Each further
    candidate needs one more run, so the rule keeps back one run fewer than the
    number of candidates waiting, and never more than SPARE_RUNS. A run kept back
    when no candidate is waiting would simply be wasted, which is why the number
    depends on how many are waiting.

    The second is a search that has stopped improving: the best estimated score
    has not risen by MIN_GAIN over the last PATIENCE runs. PATIENCE is large on
    purpose. The score gains nothing from runs left unused, and a search can
    stay flat for several runs before it finds a better result.
    """
    waiting = budget.get("candidates_waiting_for_evaluation", SPARE_RUNS + 1)
    keep = min(SPARE_RUNS, max(0, waiting - 1))
    if keep and budget["flow_runs_left_for_search"] <= keep:
        return True, (f"keeping {keep} more flow run{'s' if keep > 1 else ''} in hand: "
                      f"{waiting} candidates are waiting for an evaluation")
    h = best_after_each_run
    # While no candidate has beaten the baseline, a flat history means nothing legal
    # has been found yet, not that the search has run out of ideas: it goes on.
    if len(h) > PATIENCE and max(h) > 1.0:
        before, now = h[-PATIENCE - 1], h[-1]
        if before > 0 and (now - before) / before < MIN_GAIN:
            return True, (f"best estimated score moved {before:.4f} -> {now:.4f} "
                          f"over the last {PATIENCE} runs")
    return False, "still improving"


# ===================================================================== which model each agent uses
# Every agent uses the same model. The cost of each agent is reported separately
# in report.json (cost.usd_by_agent). For a single run, one agent's model can be
# changed on the command line with --model ROLE=ID.
MID = "openrouter/anthropic/claude-sonnet-5.5"

ROLE_MODEL = {
    "navigator":     MID,
    "stage_agent":   MID,
    "stop_agent":    MID,
    "diagnostician": MID,
}


# ===================================================================== settings offered to the stage agent
def propose(stage: str, bounds: dict, tried: list[dict], rng: random.Random,
            count: int = 4) -> list[dict]:
    """Possible settings for one stage, offered to the stage agent, which picks
    one of them or adjusts one within its legal range.

    The settings are drawn at random inside the legal ranges. `tried`, the list
    of settings already run at this stage with their results, is not used here;
    the stage agent sees it in its own context instead.
    """
    return [S.sample(stage, rng, bounds) for _ in range(count)]
