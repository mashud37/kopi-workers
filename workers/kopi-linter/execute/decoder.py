"""Ask a small model served by a local Ollama to rewrite one marked span,
greedily and at a fixed seed. Nothing leaves the machine, because the socket
is localhost.
"""
import json
import urllib.error
import urllib.request

HOST = "http://localhost:11434"
MODEL = "qwen3:4b"

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

_TIMEOUT = 180

_PROMPT = """You are copy-editing academic prose in British English.
Rewrite only the text between << and >>. {instruction}
Reply with the replacement alone, on one line, without quotes or explanation.
Reply with the single word DELETE if the text should simply go.

{left} <<{source}>> {right}
"""


def _post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{HOST}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def prepare(context: dict) -> dict:
    """Check the local Ollama is up and holds the model, provisioning nothing.

    Returns:
        ``{"available": bool, "why": str, "options": dict}``. An unavailable
        backend refuses every task instead of failing the run, so the rest of
        the probe still reports.
    """
    options = dict(GREEDY)
    try:
        _post("/api/show", {"model": MODEL})
    except urllib.error.HTTPError:
        return {"available": False, "options": options,
                "why": f"model missing, run: ollama pull {MODEL}"}
    except (urllib.error.URLError, OSError, ValueError) as problem:
        return {"available": False, "options": options,
                "why": f"no Ollama at {HOST} ({problem})"}
    return {"available": True, "options": options, "why": ""}


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
    move = task["subtype"].replace("-", " ")
    prompt = _PROMPT.format(
        instruction=f"The change an editor makes here is described as: {move}.",
        left=task["left"],
        source=task["source"],
        right=task["right"],
    )
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": state["options"],
    }
    try:
        reply = _post("/api/generate", payload)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return _clean(reply.get("response", ""))
