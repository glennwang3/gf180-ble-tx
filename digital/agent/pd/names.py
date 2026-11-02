"""Names that changed, and how a run saved under the old ones is read.

In October 2026 the loop's names were brought in line with the course slides:

  * two agents were renamed: the judge is now the navigator, and the critic is
    now the stop agent;
  * the navigator's second move, which takes a node through signoff, was called
    "signoff" and is now "evaluate". The checks themselves are still signoff,
    and every name that describes them (the sign_off node, signoff_metrics, the
    "signoff" block of a result) is unchanged.

Runs saved before that (report.json, ledger.json, trace.jsonl) still carry the
old names. Every tool that reads a saved run loads it through this module, which
renames the old keys in memory as the run is read. Nothing on disk is rewritten.

    from pd import names
    rep = names.load_report(work / "report.json")
    led = names.load_ledger(work / "ledger.json")
    calls = names.load_trace(work / "trace.jsonl")
"""
from __future__ import annotations

import json
from pathlib import Path

AGENT_ALIASES = {"judge": "navigator", "critic": "stop_agent"}
STOP_POLICY_ALIASES = {"critic": "agent"}

MOVE_ALIASES = {"signoff": "evaluate", "sign_off": "evaluate", "sign off": "evaluate",
                "sign-off": "evaluate"}

REPORT_KEYS = {"judge_corrections": "navigator_corrections", "signoff_attempts": "evaluations"}
SEARCH_KEYS = {"signoffs_during_search": "evaluations_during_search",
               "signoffs_at_the_end": "evaluations_at_the_end"}
KIND_KEYS = {"signed_off": "evaluated"}
DECISION_KEYS = {"critic_says_stop": "stop_agent_says_stop", "critic_reason": "stop_agent_reason"}
BUDGET_KEYS = {"candidates_waiting_for_signoff": "candidates_waiting_for_evaluation"}


def agent(name: str) -> str:
    """The current name of an agent, given its current or its old name."""
    return AGENT_ALIASES.get(name, name)


def stop_policy(value: str | None) -> str | None:
    """The current name of a stop policy value: "critic" is now "agent"."""
    return STOP_POLICY_ALIASES.get(value, value)


def move(action) -> str:
    """The navigator's move under its current name: "branch" or "evaluate".
    Anything else comes back lower-cased and stripped, for the caller to refuse."""
    a = str(action or "").lower().strip()
    return MOVE_ALIASES.get(a, a)


class Budget(dict):
    """The budget as a stopping rule is given it. A policy.py written before the
    rename reads candidates_waiting_for_signoff; that key still answers, with the
    value of its new name. It is not a key of its own, so it is not shown to any
    agent the budget is sent to."""

    def _new(self, key):
        return BUDGET_KEYS.get(key, key)

    def __missing__(self, key):
        if key in BUDGET_KEYS:
            return self[BUDGET_KEYS[key]]
        raise KeyError(key)

    def get(self, key, default=None):
        return super().get(self._new(key), default)

    def __contains__(self, key):
        return super().__contains__(self._new(key))


def rename_keys(d: dict | None, keys: dict[str, str]) -> dict | None:
    """Rename old keys of `d` in place. A key already present under its new
    name wins, and the old one is then dropped."""
    if isinstance(d, dict):
        for old, new in keys.items():
            if old in d:
                value = d.pop(old)
                d.setdefault(new, value)
    return d


def agents_as_keys(d: dict | None) -> dict | None:
    """A dict keyed by agent name, with old agent names renamed."""
    return rename_keys(d, AGENT_ALIASES)


def decision(d: dict) -> dict:
    """One entry of stop_decisions (report) or decisions (ledger)."""
    return rename_keys(d, DECISION_KEYS)


def call(c: dict) -> dict:
    """One ledger call or one trace line."""
    if isinstance(c, dict) and "agent" in c:
        c["agent"] = agent(c["agent"])
    return c


def report(rep: dict) -> dict:
    """A report.json, with old keys and values renamed."""
    rename_keys(rep, REPORT_KEYS)
    rename_keys(rep.get("search"), SEARCH_KEYS)
    for k in rep.get("kinds") or []:
        rename_keys(k, KIND_KEYS)
    for d in rep.get("stop_decisions") or []:
        decision(d)
    agents_as_keys((rep.get("cost") or {}).get("usd_by_agent"))
    agents_as_keys(rep.get("models"))
    if "stop_policy" in rep:
        rep["stop_policy"] = stop_policy(rep["stop_policy"])
    return rep


def ledger(led: dict) -> dict:
    """A ledger.json, with old agent names and decision keys renamed."""
    for c in led.get("calls") or []:
        call(c)
    for d in led.get("decisions") or []:
        decision(d)
    agents_as_keys(led.get("by_agent"))
    return led


def load_report(path: str | Path) -> dict:
    return report(json.loads(Path(path).read_text()))


def load_ledger(path: str | Path) -> dict:
    return ledger(json.loads(Path(path).read_text()))


def load_trace(path: str | Path) -> list[dict]:
    return [call(json.loads(line)) for line in Path(path).read_text().splitlines() if line.strip()]
