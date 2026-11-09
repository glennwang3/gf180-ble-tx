"""A stand-in for OpenRouter, for developing the agent loop without spending.

    python harness/mock_openrouter.py            # listens on 127.0.0.1:8801
    python -m agents.graph --offline             # the graph, pointed at it

It answers each of the four agents in the shape that agent expects, so the whole
graph runs: real LibreLane, fake model. The "decisions" are deliberately dumb:
the navigator walks the legal branches in order and evaluates a node every third
move if it is shown one it may, the stage agent submits the first candidate it
is offered, the stop agent never stops. So an offline run is a plumbing test and
a random-search baseline, not evidence about any prompt.

Which agent is calling is inferred from the request's shape (its tools and its
answer schema), not from prompt wording, so it keeps working while you rewrite
the prompts. Every reply carries a `usage.cost`, the field OpenRouter really
returns, so the cost ledger is exercised too.

Set MOCK_FAIL_EVERY=N to have every Nth request answered with a 503, which is
how the retry in agents/models.py is exercised without waiting for a real outage.
Set MOCK_EVALUATE_AS=signoff to have the navigator name its second move by its
old name, which the plumbing still accepts.

No dependencies beyond the standard library.
"""
from __future__ import annotations

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("MOCK_PORT", 8801))
FAIL_EVERY = int(os.environ.get("MOCK_FAIL_EVERY", 0))    # every Nth request gets a 503
EVALUATE_AS = os.environ.get("MOCK_EVALUATE_AS", "evaluate")
COST_PER_CALL = 0.0001
STATE = {"n": 0, "seen": []}


def _text(messages) -> str:
    out = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            c = " ".join(str(p.get("text", "")) for p in c if isinstance(p, dict))
        out.append(str(c or ""))
    return "\n".join(out)


def _schema_keys(req) -> set[str]:
    """Property names of the structured answer this request asks for, if any."""
    rf = req.get("response_format") or {}
    js = rf.get("json_schema") or {}
    props = (js.get("schema") or {}).get("properties") or rf.get("properties") or {}
    keys = set(props)
    for t in req.get("tools") or []:
        f = t.get("function", {})
        if f.get("name") == "set_model_response":
            keys |= set((f.get("parameters") or {}).get("properties") or {})
    return keys


def _tool_names(req) -> set[str]:
    return {t.get("function", {}).get("name") for t in (req.get("tools") or [])}


def _reply(n, content=None, tool=None):
    msg = {"role": "assistant", "content": content}
    finish = "stop"
    if tool:
        name, args = tool
        msg["tool_calls"] = [{"id": f"call_{n}", "type": "function",
                              "function": {"name": name, "arguments": json.dumps(args)}}]
        finish = "tool_calls"
    return {
        "id": f"gen-mock-{n}", "object": "chat.completion", "created": int(time.time()),
        "model": "mock", "choices": [{"index": 0, "finish_reason": finish, "message": msg}],
        "usage": {"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230,
                  "cost": COST_PER_CALL, "cost_details": {"upstream_inference_cost": 0}},
    }


def _structured(req, n, payload: dict):
    """Answer in whichever of the two ways ADK asked for a structured reply."""
    if "set_model_response" in _tool_names(req):
        return _reply(n, tool=("set_model_response", payload))
    return _reply(n, content=json.dumps(payload))


def answer(req: dict, n: int) -> dict:
    msgs = req.get("messages") or []
    text = _text(msgs)
    tools = _tool_names(req)
    keys = _schema_keys(req)

    # ---- stage agent: propose, then submit the first candidate, then one sentence
    if "submit_action" in tools:
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        stage = (re.findall(r"""['"]stage['"]\s*:\s*['"](PL|CTS|GR)['"]""", text) or ["CTS"])[0]
        if not tool_msgs:
            return _reply(n, tool=("propose_candidates", {"stage": stage, "count": 3}))
        if len(tool_msgs) == 1:
            try:
                cands = json.loads(tool_msgs[0].get("content") or "{}").get("candidates") or []
            except (json.JSONDecodeError, AttributeError):
                cands = []
            if not cands:
                m = re.search(r"\{[^{}]*\}", str(tool_msgs[0].get("content")))
                cands = [json.loads(m.group(0).replace("'", '"').replace("True", "true")
                                    .replace("False", "false"))] if m else [{}]
            return _reply(n, tool=("submit_action", {
                "stage": stage, "parameters": cands[0],
                "rationale": "offline mock: first candidate offered"}))
        return _reply(n, content="Submitted the first candidate (offline mock).")

    # ---- navigator: walk the legal branches in order; every third move, an evaluation
    if "node_id" in keys:
        legal = re.findall(r"(n\d+):(PL|CTS|GR)", text)
        runs = int((re.findall(r"""['"]runs_so_far['"]\s*:\s*(\d+)""", text) or ["1"])[0])
        offered = re.search(r"""['"]can_(?:evaluate|sign_off)['"]\s*:\s*\[([^\]]*)\]""", text)
        ready = re.findall(r"n\d+", offered.group(1)) if offered else []
        STATE["navigator"] = STATE.get("navigator", 0) + 1
        if ready and STATE["navigator"] % 3 == 0:
            return _structured(req, n, {"action": EVALUATE_AS, "node_id": ready[0], "stage": "",
                                        "hint": "", "reason": "offline mock: every third move"})
        if legal:
            node, stage = legal[(runs - 1) % len(legal)]
        else:
            node, stage = "n0", "PL"
        return _structured(req, n, {"action": "branch", "node_id": node, "stage": stage,
                                    "hint": "offline mock: no guidance",
                                    "reason": "offline mock: next legal branch in order"})

    # ---- stop agent: never stops; the rule and the hard limits end an offline run
    if "stop" in keys:
        return _structured(req, n, {"stop": False, "reason": "offline mock: always continue"})

    # ---- diagnostician
    if "cause" in keys:
        return _structured(req, n, {"cause": "offline mock: not diagnosed",
                                    "evidence": "none", "remedy": "avoid this branch"})

    return _reply(n, content="offline mock: no role recognised for this request")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            req = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            req = {}
        STATE["n"] += 1
        n = STATE["n"]
        if FAIL_EVERY and n % FAIL_EVERY == 0:      # a provider having a bad moment
            out = b'{"error": {"message": "mock: overloaded", "code": 503}}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return
        msgs = req.get("messages") or []
        STATE["seen"].append({
            "n": n, "tools": sorted(t for t in _tool_names(req) if t),
            "schema_keys": sorted(_schema_keys(req)),
            "has_response_format": "response_format" in req,
            "n_messages": len(msgs),
            "prompt_chars": len(_text(msgs)),
        })
        STATE["seen"] = STATE["seen"][-200:]
        out = json.dumps(answer(req, n)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):                       # GET /__calls shows what arrived
        out = json.dumps(STATE).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"mock OpenRouter on http://127.0.0.1:{PORT}  (Ctrl-C to stop)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
