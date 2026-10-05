"""Token-guarded proxy in front of a local vLLM server, presenting the same
`/tighten` contract as cloud/serve.py so cli/cloud.py needs no changes.
Relays chat messages with Qwen3 reasoning mode off.
"""
import json
import os
import time
import urllib.request
import urllib.error

from flask import Flask, request, jsonify, abort

# Top-level (not lazy inside the handler) so a packaging slip (kopi/ missing from the
# image) fails at container startup and the build-time import check, never as a 500
# mid-request after a billed generation. citations is pure stdlib; no torch/spaCy here.
from kopi.citations import restore_casing

# Max seconds to wait for vLLM to finish loading on a cold start (scale-to-zero
# means the first request after idle waits through the model load). The client
# timeout is 300 s; stay under it.
_READY_WAIT = 280

app = Flask(__name__)
_TOKEN = os.environ.get("JOB_TOKEN", "")
# FP8 base, NOT AWQ: the `kopi` LoRA was trained against bf16 Qwen3-32B, and bf16-learned
# deltas applied over an AWQ (int4) base drift the logits enough to corrupt token boundaries
# (merged words, doubled morphemes). FP8 stays close to bf16, so the adapter serves cleanly.
_MODEL = os.environ.get("KOPI_MODEL", "Qwen/Qwen3-32B-FP8")
# Served LoRA module names (set by entrypoint_vllm.sh when an adapter is baked).
# A request may target one of these instead of the base; anything else is rejected
# so /tighten can't be used to probe arbitrary model names.
_LORA = {m for m in os.environ.get("KOPI_LORA", "").split(",") if m}
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
    # Default to the base model; a caller may select a baked LoRA module (the tune)
    # for A/B evaluation. Reject any other name rather than relay it to vLLM.
    model = data.get("model") or _MODEL
    if model != _MODEL and model not in _LORA:
        abort(400, f"unknown model {model!r}")
    # Wait through a cold-start model load rather than 503-ing (scale-to-zero).
    deadline = time.time() + _READY_WAIT
    while not _vllm_ready():
        if time.time() > deadline:
            abort(503, "model still loading")
        time.sleep(2)

    # An edit only tightens, so the output never meaningfully exceeds the input; cap
    # max_tokens off the paragraph length (≈1.5 tok/word, doubled for headroom) so a
    # long paragraph isn't silently truncated at a fixed 1024 (which the local guard
    # then misreads as drift), while a short one can't run away. Fall back when the
    # caller sent no paragraph (only messages).
    para_words = len((data.get("paragraph") or "").split())
    max_tokens = min(4096, max(512, para_words * 3)) if para_words else 1024
    # Production samples at 0.1; the A/B eval overrides to temperature 0 (+ a seed) so
    # base and tune are scored on greedy, reproducible decoding rather than one dice roll.
    payload = {
        "model": model,
        "messages": messages,
        "temperature": data.get("temperature", 0.1),
        "max_tokens": max_tokens,
        # Qwen3 defaults to a reasoning mode that emits <think>…</think>; off for editing.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if data.get("seed") is not None:
        payload["seed"] = data["seed"]
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _VLLM + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as e:  # vLLM answered with an error status
        abort(502, f"vllm error: {e.read().decode('utf-8', 'replace')[:300]}")
    except (urllib.error.URLError, OSError) as e:  # unreachable / timed out mid-cold-start
        abort(502, f"vllm unreachable: {e}")
    edited = out["choices"][0]["message"]["content"].strip()
    # Small models lowercase author names inside citations; repair deterministically
    # when the caller sent the original so the served edit needs no client-side fix.
    paragraph = (data.get("paragraph") or "").strip()
    if paragraph:
        edited = restore_casing(paragraph, edited)
    return jsonify({"edited": edited})
