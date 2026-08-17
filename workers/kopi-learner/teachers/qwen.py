"""The student as deployed: posts to the same served Qwen `/tighten`
endpoint kopi-editor's cloud client uses, returning its edit as `rejected`
so preference data reflects production exactly.
"""
import json
import urllib.request

import editor
from cli import config

_TIMEOUT = 300


def require() -> None:
    if not config.qwen_base_url():
        raise SystemExit("no qwen_base_url, point it at the deployed vLLM service in secrets.yaml.")
    if not config.qwen_token():
        raise SystemExit("no qwen_token: the served vLLM service JOB_TOKEN (secrets.yaml).")


def edit(unit: dict) -> str:
    """The served model's edit of one unit, via the identical production prompt."""
    msgs = editor.build_messages(
        unit["text"], unit.get("instructions"), config.lang(), unit["mode"], unit.get("floor"))
    url = f"{config.qwen_base_url().rstrip('/')}/tighten?token={config.qwen_token()}"
    body = json.dumps({
        "messages": msgs,
        "paragraph": unit["text"],
        "instructions": unit.get("instructions"),
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())["edited"].strip()
