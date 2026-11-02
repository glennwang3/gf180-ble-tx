"""Exercise the diagnostician on failures that really happened.

    python -m agents.diagnose_cases             real model, three calls, well under a cent
    python -m agents.diagnose_cases --offline   plumbing check against the mock
    python -m agents.diagnose_cases --model openrouter/anthropic/claude-opus-5.5
                                                the same cases on another model

In a healthy search the diagnostician rarely fires, which makes its prompt the
hardest one to improve by running the whole loop. This runs it alone on the three
failures recorded in harness/failure_cases.json — each one met while this lab
was being prepared — and prints its answer beside the cause that was eventually
established. None of the three is named by its own error message.

Reading the two side by side is the exercise; nothing here grades the answer.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


async def diagnose(case: dict, model) -> dict:
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from .nodes import make_diagnostician, _as_dict

    agent = make_diagnostician(model)
    runner = InMemoryRunner(agent=agent, app_name="diagnose")
    sess = await runner.session_service.create_session(app_name="diagnose", user_id="ta")
    shown = {k: case[k] for k in ("stage_branched_at", "configuration", "error", "end_of_log")}
    last = ""
    async for ev in runner.run_async(
        user_id="ta", session_id=sess.id,
        new_message=types.Content(role="user", parts=[types.Part(text=json.dumps(shown))]),
    ):
        # A model that reasons before it answers sends that reasoning as a part
        # of its own, marked as a thought, ahead of the answer.
        for part in (ev.content.parts if ev.content and ev.content.parts else []):
            if part.text and not getattr(part, "thought", False):
                last = part.text
    return _as_dict(last)


def _wrap(label: str, text: str) -> str:
    body = textwrap.fill(str(text), width=92, initial_indent="    ", subsequent_indent="    ")
    return f"  {label}\n{body}"


async def main(offline_port: int | None) -> None:
    from pd.ledger import Ledger
    from . import models

    ledger = Ledger(max_flow_runs=0, max_usd=0.25)
    model = models.model_for("diagnostician", ledger, offline_port)
    cases = json.loads((HERE / "harness" / "failure_cases.json").read_text())
    for c in cases:
        print("=" * 96)
        print(f"  CASE  {c['name']}")
        print(_wrap("the error it was given", c["error"] + "  …  " + c["end_of_log"].splitlines()[-1]))
        d = await diagnose(c, model)
        print(_wrap("diagnostician: cause", d.get("cause", "(no answer)")))
        print(_wrap("diagnostician: remedy", d.get("remedy", "")))
        print(_wrap("established cause", c["known_cause"]))
        print(_wrap("what does not fix it", c["what_does_not_fix_it"]))
    print("=" * 96)
    print(f"  {len(cases)} cases, {len(ledger.calls)} model calls, ${ledger.usd:.5f}"
          f"   on {models.policy.ROLE_MODEL['diagnostician']}")


if __name__ == "__main__":
    import logging
    import warnings
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--offline", nargs="?", type=int, const=8801, default=None, metavar="PORT")
    p.add_argument("--model", default=None, metavar="ID",
                   help="the model to diagnose with; the default is the diagnostician's "
                        "entry in ROLE_MODEL, student/policy.py")
    a = p.parse_args()
    if a.model:
        from .compat import policy
        policy.ROLE_MODEL["diagnostician"] = a.model
    warnings.filterwarnings("ignore")
    logging.getLogger().setLevel(logging.ERROR)
    asyncio.run(main(a.offline))
