"""Old names in policy.py, prompts.py and views.py, still accepted.

The navigator and the stop agent were called the judge and the critic until
October 2026. Files written against the old names keep working:
each old name stands in for the new one, with a one-line
warning on stderr. The framework imports these three modules from here, so
the names are settled before anything reads them:

    from .compat import policy, prompts, views

Old name in these files            used as
  views.judge_view                  views.navigator_view
  views.critic_view                 views.stop_view
  prompts.JUDGE                     prompts.NAVIGATOR
  prompts.CRITIC                    prompts.STOP_AGENT
  prompts.JudgeDecision             prompts.NavigatorDecision
  ROLE_MODEL["judge"]               ROLE_MODEL["navigator"]
  ROLE_MODEL["critic"]              ROLE_MODEL["stop_agent"]
  STOP_POLICY = "critic"            STOP_POLICY = "agent"

The same goes for the command line: --model judge=ID and --stop-policy critic.
Runs saved under the old names are read through pd/names.py.
"""
from __future__ import annotations

import sys

from pd import names

from . import policy, prompts, views

_SAID: set[str] = set()


def warn(message: str) -> None:
    """One line on stderr, once per message per process."""
    if message not in _SAID:
        _SAID.add(message)
        print(f"  deprecated: {message}", file=sys.stderr, flush=True)


def _adopt(module, old: str, new: str, where: str) -> None:
    if not hasattr(module, new) and hasattr(module, old):
        setattr(module, new, getattr(module, old))
        warn(f"{where} defines {old}; rename it to {new}")


def role(name: str, where: str = "--model") -> str:
    """An agent's role under its current name."""
    new = names.agent(name)
    if new != name:
        warn(f"{where} names the agent {name!r}; it is now {new!r}")
    return new


def role_model(table: dict, where: str = "ROLE_MODEL in agents/policy.py") -> dict:
    """Rename old roles in a ROLE_MODEL table in place, keeping its order. Where
    a table has both names, the new one wins."""
    renamed: dict = {}
    for k, v in table.items():
        new = role(k, where)
        if new not in renamed or new == k:
            renamed[new] = v
    table.clear()
    table.update(renamed)
    return table


def stop_policy(value: str | None, where: str = "--stop-policy") -> str | None:
    new = names.stop_policy(value)
    if new != value:
        warn(f"{where} is {value!r}; it is now {new!r}")
    return new


def adopt(policy=policy, prompts=prompts, views=views) -> None:
    """Settle the names in policy, prompts and views. Safe to call twice."""
    _adopt(views, "judge_view", "navigator_view", "agents/views.py")
    _adopt(views, "critic_view", "stop_view", "agents/views.py")
    _adopt(prompts, "JUDGE", "NAVIGATOR", "agents/prompts.py")
    _adopt(prompts, "CRITIC", "STOP_AGENT", "agents/prompts.py")
    _adopt(prompts, "JudgeDecision", "NavigatorDecision", "agents/prompts.py")
    if isinstance(getattr(policy, "ROLE_MODEL", None), dict):
        role_model(policy.ROLE_MODEL)
    if hasattr(policy, "STOP_POLICY"):
        policy.STOP_POLICY = stop_policy(policy.STOP_POLICY, "STOP_POLICY in agents/policy.py")


adopt()
