"""Cloud Run service — token-guarded proxy in front of a local vLLM server.

POST /tighten?token=...  {messages: [...]}  -> {edited}
GET  /healthz            liveness probe (binds immediately, see below)

This presents the **same `/tighten` contract** as cloud/serve.py (the Ollama
service), so the existing client (`cli/cloud.py`) talks to it unchanged — only
BASE_URL/JOB_TOKEN differ. It relays the client-built chat messages to a local
vLLM OpenAI server (127.0.0.1:8001) with Qwen3's reasoning mode **off**
(`enable_thinking: false`), so the output is the edited paragraph, not a
`<think>` trace.

`/healthz` returns OK the moment the proxy is up — it does NOT wait for vLLM — so
Cloud Run's ~240 s startup probe passes while vLLM loads the model in the
background; `/tighten` returns 503 until vLLM's own /health is ready.
"""
import json
import os
import time
import urllib.request
import urllib.error

from flask import Flask, request, jsonify, abort

# Max seconds to wait for vLLM to finish loading on a cold start (scale-to-zero
# means the first request after idle waits through the model load). The client
# timeout is 300 s; stay under it.
_READY_WAIT = 280

app = Flask(__name__)
_TOKEN = os.environ.get("JOB_TOKEN", "")
_MODEL = os.environ.get("KOPI_MODEL", "Qwen/Qwen3-14B-AWQ")
_VLLM = "http://127.0.0.1:8001"


def _vllm_ready() -> bool:
    try:
        with urllib.request.urlopen(_VLLM + "/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


@app.get("/healthz")
def healthz():
    return "ok"


@app.post("/tighten")
def tighten():
    if not _TOKEN or request.args.get("token") != _TOKEN:
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    messages = data.get("messages")
    if not messages:
        abort(400, "missing messages")
    # Wait through a cold-start model load rather than 503-ing (scale-to-zero).
    deadline = time.time() + _READY_WAIT
    while not _vllm_ready():
        if time.time() > deadline:
            abort(503, "model still loading")
        time.sleep(2)

    body = json.dumps({
        "model": _MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1024,
        # Qwen3 defaults to a reasoning mode that emits <think>…</think>; off for editing.
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    req = urllib.request.Request(
        _VLLM + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        abort(502, f"vllm error: {e.read().decode('utf-8', 'replace')[:300]}")
    edited = out["choices"][0]["message"]["content"].strip()
    return jsonify({"edited": edited})
