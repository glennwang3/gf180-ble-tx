"""Model handles, with the real cost of every call recorded against its agent.

Two things ADK does not do for you, both measured on this install:

  * It drops the cost. `usage_metadata` on an ADK event has token counts and
    nothing else, and `litellm.success_callback` never fires because ADK uses
    the async path. The working seam is `LiteLLMClient`, which ADK exposes as an
    injectable field.

  * It will not pick a provider. Every request here carries tools or a schema,
    and OpenRouter's Auto Exacto re-orders providers by quality instead of price
    on those — so two runs with identical token counts can be billed differently.
    `sort: price` turns that off; `require_parameters` keeps a request off any
    endpoint that would silently ignore `tools`.

Streaming stays off: the cost field only survives the non-streaming path.

The same seam is where the trace is taken: this client sees the exact messages
each agent is sent and the exact answer it gives, tool calls included, which is
more than any node downstream of the agent is handed.
"""
from __future__ import annotations

import asyncio
import json
import time

import litellm
from google.adk.models.lite_llm import LiteLlm, LiteLLMClient

from pd import apikey
from pd.ledger import Ledger

from .compat import policy      # policy.py, old role names settled

API_BASE = "https://openrouter.ai/api/v1"

# LiteLLM prints a red "Provider List: ..." banner every time it cannot price a
# model id it does not know (the offline mock's, for one). Cost here comes from
# OpenRouter's own figure, so that lookup failing is of no consequence.
litellm.suppress_debug_info = True

PROVIDER_POLICY = {
    "sort": "price",
    "require_parameters": True,
}


# A search is an hour of flow runs strung together by model calls, and one call
# in a few hundred comes back broken for reasons that have nothing to do with the
# request: a connection dropped mid-answer, a provider briefly overloaded. Those
# are tried again. A request the server understood and refused — a bad key, a
# malformed body — is not: trying again would only fail the same way.
RETRYABLE = (litellm.APIError, litellm.APIConnectionError, litellm.Timeout,
             litellm.InternalServerError, litellm.ServiceUnavailableError,
             litellm.RateLimitError)
BACKOFF_S = (2, 8, 30)          # waits between attempts; one more attempt than waits


def _plain(x):
    """A message or a tool call as plain JSON, whatever object the SDK used."""
    if hasattr(x, "model_dump"):
        x = x.model_dump(exclude_none=True)
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items() if v is not None}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


def _calls(tool_calls) -> list[dict]:
    """Tool calls as name and arguments, with the arguments parsed."""
    out = []
    for tc in _plain(tool_calls or []):
        fn = tc.get("function") or {}
        args = fn.get("arguments")
        try:
            args = json.loads(args) if isinstance(args, str) else args
        except json.JSONDecodeError:
            pass
        out.append({"name": fn.get("name"), "arguments": args})
    return out


def _text(content) -> str | None:
    """Message content as text: a string, or the text parts of a list."""
    if isinstance(content, list):
        return "\n".join(str(p.get("text", p)) if isinstance(p, dict) else str(p) for p in content)
    return content


def _exchange(messages, tools, resp) -> dict:
    """What one call was sent and what came back, for the trace."""
    from . import nodes
    ep = nodes.current_episode()
    sent = []
    for m in _plain(messages or []):
        row = {"role": m.get("role"), "content": _text(m.get("content"))}
        if m.get("tool_calls"):
            row["tool_calls"] = _calls(m["tool_calls"])
        sent.append({k: v for k, v in row.items() if v is not None})
    try:
        msg = resp.choices[0].message
        out = {"content": _text(getattr(msg, "content", None)),
               "tool_calls": _calls(getattr(msg, "tool_calls", None))}
        thought = getattr(msg, "reasoning_content", None)
        if thought:                     # what a reasoning model says it thought, when it says
            out["reasoning"] = _text(thought)
    except (AttributeError, IndexError):
        out = {"content": None, "tool_calls": []}
    names = [(t.get("function") or {}).get("name") for t in _plain(tools or [])]
    return json.loads(apikey.scrub(json.dumps(
        {"runs_so_far": len(ep.tree.order) if ep else 0,
         "input": sent, "tools": [n for n in names if n], "output": out},
        ensure_ascii=False, default=str)))


class CostTrackingClient(LiteLLMClient):
    """Records OpenRouter's own per-call charge against the agent that made it,
    and tries a call again when the failure was the network's rather than ours."""

    def __init__(self, ledger: Ledger, role: str):
        super().__init__()
        self._ledger = ledger
        self._role = role

    async def acompletion(self, model, messages, tools, **kwargs):
        t0 = time.monotonic()
        for wait in (*BACKOFF_S, None):
            try:
                resp = await super().acompletion(model, messages, tools, **kwargs)
                break
            except RETRYABLE:
                if wait is None:
                    raise
                self._ledger.retries += 1
                await asyncio.sleep(wait)
        hidden = getattr(resp, "_hidden_params", {}) or {}
        usage = getattr(resp, "usage", None)
        served = "/".join(str(x) for x in (getattr(resp, "provider", None),
                                           getattr(resp, "model", None)) if x) or None
        self._ledger.charge_call(
            agent=self._role,
            usd=hidden.get("response_cost"),
            gen_id=getattr(resp, "id", None),     # reconciles against /api/v1/generation
            tokens={"prompt": getattr(usage, "prompt_tokens", None),
                    "completion": getattr(usage, "completion_tokens", None)},
            model=model,                          # what was asked for
            served_by=served,                     # what the provider says answered
            seconds=time.monotonic() - t0,
            exchange=_exchange(messages, tools, resp) if self._ledger.trace else None,
        )
        return resp


def model_for(role: str, ledger: Ledger, offline_port: int | None = None) -> LiteLlm:
    """The model used by the agent `role`. Every call is recorded, with its
    cost, under the agent's name.

    With `offline_port` set, the calls go to the fake model in
    harness/mock_openrouter.py instead, which needs no key and costs nothing.
    """
    name = policy.ROLE_MODEL[role]
    if offline_port:
        return LiteLlm(model=name, api_key="sk-mock",
                       api_base=f"http://127.0.0.1:{offline_port}/api/v1",
                       llm_client=CostTrackingClient(ledger, role))
    return LiteLlm(model=name, api_key=apikey.load(), api_base=API_BASE,
                   llm_client=CostTrackingClient(ledger, role),
                   extra_body={"provider": PROVIDER_POLICY})


def describe() -> str:
    return "\n".join(f"    {role:14s} {model}" for role, model in policy.ROLE_MODEL.items())
