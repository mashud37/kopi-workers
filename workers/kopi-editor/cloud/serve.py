"""Relay client-built chat messages to the warm local Ollama model through a
token-guarded `/tighten` endpoint, with `/healthz` for liveness. The client
builds the prompt and runs the acceptance guard.
"""
import os

from flask import Flask, abort, jsonify, request

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
        edited = resp["message"]["content"].strip()
        paragraph = (data.get("paragraph") or "").strip()
        if paragraph:
            from kopi.citations import restore_casing
            edited = restore_casing(paragraph, edited)
        return jsonify({"edited": edited})

    # Back-compat: build the prompt server-side from a paragraph + instructions.
    paragraph = (data.get("paragraph") or "").strip()
    if not paragraph:
        abort(400, "missing paragraph or messages")
    from kopi.llm import edit_paragraph
    edited = edit_paragraph(paragraph, {"instructions": data.get("instructions")})
    return jsonify({"edited": edited})
