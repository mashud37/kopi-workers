"""Rewrite one marked span with a small instruct model, greedily and at a fixed
seed. Two transports: the served vLLM this workspace deploys, or a local Ollama.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

TRANSPORTS = ("served", "local")
DEFAULT_TRANSPORT = "served"

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:4b"

# Greedy, seeded and length-capped, so two runs over the same span produce the
# same bytes. `manage.py execute --reproduce` asserts that rather than trusting
# it, and runs a sampling decoder as the control that has to fail.
GREEDY = {
    "temperature": 0.0,
    "top_k": 1,
    "top_p": 1.0,
    "seed": 0,
    "num_predict": 64,
    "num_ctx": 2048,
}

_TIMEOUT = 300

_SECRETS = Path(__file__).resolve().parents[1] / "secrets.yaml"
_EDITOR_DATA = Path(os.environ["KOPI_DATA"]) / "kopi-editor" if os.environ.get("KOPI_DATA") else Path(__file__).resolve().parents[2] / "kopi-editor"
_EDITOR_ENV = _EDITOR_DATA / "env.yaml"

_SYSTEM = "You are copy-editing academic prose in British English."

_TASK = """Rewrite only the text between << and >>. {instruction}
Reply with the replacement alone, on one line, without quotes or explanation.
Reply with the single word DELETE if the text should simply go.

{left} <<{source}>> {right}"""


def _post(url: str, payload: dict) -> dict | None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _from_file(path: Path, url_key: str, token_key: str) -> dict:
    if not path.exists():
        return {}
    import yaml

    values = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {"base_url": values.get(url_key) or "", "token": values.get(token_key) or ""}


def _credentials() -> dict:
    """The served service URL and token: environment, then this repo, then kopi-editor.

    kopi-editor's `env.yaml` is read last because its `manage.py deploy` is what
    writes the token, and a second copy of a secret on disk is a second thing to
    leak. Setting the two environment variables overrides both files.
    """
    sources = [
        {
            "base_url": os.environ.get("KOPI_BASE_URL", ""),
            "token": os.environ.get("KOPI_JOB_TOKEN", ""),
        },
        _from_file(_SECRETS, "base_url", "job_token"),
        _from_file(_EDITOR_ENV, "BASE_URL", "JOB_TOKEN"),
    ]
    for source in sources:
        if source.get("base_url") and source.get("token"):
            return source
    return {"base_url": "", "token": ""}


def _prepare_served() -> dict:
    # Deliberately not health-checked. The service scales to zero, so a request
    # made only to validate the URL starts a GPU instance and bills for it.
    found = _credentials()
    if not found["base_url"] or not found["token"]:
        return {
            "available": False,
            "transport": "served",
            "why": "no served endpoint: set KOPI_BASE_URL and KOPI_JOB_TOKEN, or fill "
                   "secrets.yaml (see secrets.example.yaml)",
        }
    return {
        "available": True,
        "transport": "served",
        "why": "",
        "base_url": found["base_url"],
        "token": found["token"],
        "options": {"temperature": 0, "seed": 0},
    }


def _prepare_local() -> dict:
    unavailable = {"available": False, "transport": "local", "options": dict(GREEDY)}
    try:
        _ = urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=5).read()
    except urllib.error.HTTPError:
        return {**unavailable, "why": f"Ollama answered an error at {OLLAMA_HOST}"}
    except (urllib.error.URLError, OSError, ValueError) as problem:
        return {**unavailable, "why": f"no Ollama at {OLLAMA_HOST} ({problem})"}
    return {"available": True, "transport": "local", "why": "", "options": dict(GREEDY)}


def prepare(context: dict) -> dict:
    """Resolve one transport, provisioning nothing and starting no instance.

    Args:
        context: ``{"transport": "served" | "local"}``; anything else is ignored.

    Returns:
        ``{"available", "transport", "why", "options", ...}``. An unavailable
        backend refuses every task instead of failing the run, so the rest of the
        probe still reports.
    """
    transport = context.get("transport") or DEFAULT_TRANSPORT
    if transport == "local":
        return _prepare_local()
    return _prepare_served()


def _messages(task: dict) -> list:
    """The one exchange the model is given: no paragraph, only the marked span."""
    move = task["subtype"].replace("-", " ")
    body = _TASK.format(
        instruction=f"The change an editor makes here is described as: {move}.",
        left=task["left"],
        source=task["source"],
        right=task["right"],
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": body},
    ]


def _clean(reply: str) -> str:
    """The answer alone: reasoning block, span markers and quoting removed."""
    text = reply.split("</think>", 1)[-1].strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    answer = lines[0].replace("<<", "").replace(">>", "").strip()
    answer = answer.strip('"').strip("'").strip()
    return "" if answer.upper() == "DELETE" else answer


def execute(task: dict, state: dict) -> str | None:
    """The model's replacement for the marked span, or ``None`` when unavailable.

    The model is told what kind of change belongs here and never told where to
    look for one, which is the division of labour the whole tier rests on: the
    deterministic layer allocates, the small model executes.
    """
    if not state["available"]:
        return None
    messages = _messages(task)
    if state["transport"] == "local":
        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": state["options"],
        }
        answer = _post(f"{OLLAMA_HOST}/api/chat", payload)
        reply = (answer or {}).get("message", {}).get("content", "")
    else:
        url = f"{state['base_url'].rstrip('/')}/tighten?token={state['token']}"
        answer = _post(url, {"messages": messages, **state["options"]})
        reply = (answer or {}).get("edited", "")
    return None if answer is None else _clean(reply)
