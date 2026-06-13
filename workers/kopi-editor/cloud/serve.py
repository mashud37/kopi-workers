"""Cloud Run service — token-guarded HTTP wrapper over the paragraph editor.

POST /tighten?token=...  {messages: [...]}            -> {edited}   (preferred)
POST /tighten?token=...  {paragraph, instructions}    -> {edited}   (back-compat)
GET  /healthz            liveness probe

The client builds the full prompt (system + user) and sends it as ``messages``;
this service just relays them to the warm Ollama model. Keeping the prompt on the
client means prompt changes need no redeploy. Ollama runs in the same container
with the model baked in, so it stays warm while the instance is up. The
acceptance guard runs on the *client*; the token guards the endpoint.
"""
import os

from flask import Flask, request, jsonify, abort

app = Flask(__name__)
_TOKEN = os.environ.get("JOB_TOKEN", "")
_MODEL = os.environ.get("KOPI_MODEL", "qwen2.5:7b")


@app.get("/healthz")
def healthz():
    return "ok"


@app.post("/tighten")
def tighten():
    if not _TOKEN or request.args.get("token") != _TOKEN:
        abort(403)
    data = request.get_json(force=True, silent=True) or {}

    messages = data.get("messages")
    if messages:
        import ollama
        resp = ollama.chat(
            model=_MODEL, messages=messages,
            options={"temperature": 0.1}, keep_alive="10m",
        )
        return jsonify({"edited": resp["message"]["content"].strip()})

    # Back-compat: build the prompt server-side from a paragraph + instructions.
    paragraph = (data.get("paragraph") or "").strip()
    if not paragraph:
        abort(400, "missing paragraph or messages")
    from kopi.llm import edit_paragraph
    return jsonify({"edited": edit_paragraph(paragraph, instructions=data.get("instructions"))})
