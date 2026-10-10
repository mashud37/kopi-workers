"""Send paragraphs to Claude or to any server that accepts OpenAI's chat format, guard each edit, and report progress and cost.
The edit command calls tighten()."""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cli import config, ui
from kopi import items
from kopi.llm import _build_user_message, _system_for
from kopi.step_concision import (
    _MAX_COMPRESSION,
    _preload_embedding_model,
    apply_results,
    edit_with_retry,
    get_candidates,
)

# ---- Settings ----

BACKEND_LABEL = {
    "anthropic": "Claude",
    "openai-compatible": "the OpenAI-compatible server",
}
WORKERS = 4
MAX_TOKENS = 4096
EFFORT = "low"
HEARTBEAT_SECONDS = 5
LOCAL_HOSTS = [
    "localhost",
    "127.0.0.1",
]
SMOKE_MIN_WORDS = 40
SMOKE_BUDGET_SHARE = 0.2


# ---- Running totals ----

class Tally:
    """What the worker threads share: paragraphs finished, tokens billed, and when editing started."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.done = 0
        self.tokens = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
        self.started = time.monotonic()

    def add_usage(self, usage) -> None:
        with self.lock:
            self.tokens["input"] += usage.input_tokens or 0
            self.tokens["output"] += usage.output_tokens or 0
            self.tokens["cache_write"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
            self.tokens["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0

    def finished_one(self) -> None:
        with self.lock:
            self.done += 1

    def done_count(self) -> int:
        with self.lock:
            return self.done

    def restart_clock(self) -> None:
        self.started = time.monotonic()

    def seconds(self) -> float:
        return time.monotonic() - self.started


# ---- Opening a session ----

def _open_anthropic() -> dict:
    """An Anthropic client on the configured key and model."""
    if not config.get("ANTHROPIC_API_KEY"):
        raise SystemExit("no Anthropic API key: add it on the console's Keys page, or with `python manage.py settings`.")
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic SDK not installed, run: pip install anthropic") from None
    return {
        "client": anthropic.Anthropic(api_key=config.get("ANTHROPIC_API_KEY")),
        "model": config.get("ANTHROPIC_MODEL"),
        "base_url": "",
    }


def _open_server() -> dict:
    """The OpenAI-compatible server's address and model; the client itself is made on the first call."""
    connection = config.llm_connection()
    return {
        "model": connection["model"],
        "base_url": connection["base_url"],
    }


OPENERS = {
    "anthropic": _open_anthropic,
    "openai-compatible": _open_server,
}


def open_session(backend: str) -> dict:
    """Everything one run's calls share: the backend's client or address, the model, and the running totals.

    Raises:
        SystemExit: the backend is unknown or not set up.
    """
    if backend not in OPENERS:
        raise SystemExit(f"no model backend called '{backend}'.")
    workers = WORKERS
    if os.environ.get("KOPI_LLM_WORKERS", "").isdigit():
        workers = int(os.environ["KOPI_LLM_WORKERS"])
    return {
        **OPENERS[backend](),
        "backend": backend,
        "lang": config.get("LANG"),
        "workers": max(1, workers),
        "tally": Tally(),
    }


# ---- One model call ----

def _ask_anthropic(session: dict, text: str, instructions, style: dict) -> str:
    """One Messages API call. The system prompt is the same for every paragraph at one
    intensity, so it is cached: the first call writes it and the rest read it at a tenth of the price."""
    request = {
        "model": session["model"],
        "max_tokens": MAX_TOKENS,
        "system": [{"type": "text", "text": _system_for(session["lang"], style["mode"]), "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": _build_user_message(text, instructions, style["floor"])}],
    }
    if not session["model"].startswith("claude-haiku"):
        request["output_config"] = {"effort": EFFORT}
    response = session["client"].messages.create(**request)
    session["tally"].add_usage(response.usage)
    parts = [block.text for block in response.content if block.type == "text"]
    return "".join(parts).strip()


def _ask_server(session: dict, text: str, instructions, style: dict) -> str:
    """One chat completion on the OpenAI-compatible server."""
    from backends import openai_client
    system = _system_for(session["lang"], style["mode"])
    prompt = _build_user_message(text, instructions, style["floor"])
    return openai_client.complete(system, prompt, MAX_TOKENS)


ASKERS = {
    "anthropic": _ask_anthropic,
    "openai-compatible": _ask_server,
}


def ask(session: dict, text: str, instructions, style: dict) -> str:
    """The model's edit of one paragraph, through the session's backend.

    Args:
        style: the paragraph's `mode` (prompt stance) and `floor` (soft length target).
    """
    return ASKERS[session["backend"]](session, text, instructions, style)


class _Call:
    """One paragraph's call settings, held so a corrective retry asks on the same terms."""

    def __init__(self, session: dict, style: dict) -> None:
        self.session = session
        self.style = style

    def edit(self, text: str, instructions) -> str:
        return ask(self.session, text, instructions, self.style)


# ---- Editing a batch ----

def edit_one(session: dict, cand: dict) -> dict:
    """Edit one candidate paragraph, guarded, with one corrective retry, and announce how it went.

    Returns:
        The row `step_concision.apply_results` reads: `index`, `accepted`, `edited`, `reason`,
        `saved` and `routing_reason`.
    """
    name = f"Paragraph {cand['index'] + 1}"
    items.announce("start", name)
    call = _Call(session, {"mode": cand.get("mode", "firm"), "floor": cand.get("floor")})
    try:
        outcome = edit_with_retry(call.edit, cand["text"], cand.get("instructions"), cand.get("max_compression", _MAX_COMPRESSION))
    except Exception as error:
        outcome = {"accepted": False, "edited": cand["text"], "reason": f"{session['backend']} error: {error}", "saved": 0}
    session["tally"].finished_one()

    if outcome["accepted"]:
        items.announce("ok", name, f"{outcome['saved']} words cut")
    else:
        items.announce("failed", name, outcome["reason"])
    return {
        "index": cand["index"],
        "accepted": outcome["accepted"],
        "edited": outcome["edited"],
        "reason": outcome["reason"],
        "saved": outcome["saved"],
        "routing_reason": cand.get("routing_reason"),
    }


def _heartbeat(session: dict, total: int, stop: threading.Event) -> None:
    """Print the count every few seconds, so a long wait never looks stalled."""
    while not stop.wait(HEARTBEAT_SECONDS):
        done = session["tally"].done_count()
        elapsed = int(session["tally"].seconds())
        line = f"editing {done}/{total} done · {elapsed}s elapsed"
        if config.is_own_cloud(session["base_url"]) and done == 0:
            line += "  (loading the model on the GPU, up to ~90s)"
        ui.info(line)


def cost_line(session: dict) -> str:
    """What the run cost at list price: by tokens for Claude, by active seconds for your own Cloud Run service."""
    if session["backend"] == "openai-compatible" and any(host in session["base_url"] for host in LOCAL_HOSTS):
        return "no charge: the model runs on this machine"
    if config.is_own_cloud(session["base_url"]):
        seconds = session["tally"].seconds()
        gpu = config.GPU_PRICE_PER_SECOND.get(config.get("GPU_TYPE"), config.GPU_PRICE_PER_SECOND["nvidia-l4"])
        if os.environ.get("KOPI_GPU_PER_SEC"):
            gpu = float(os.environ["KOPI_GPU_PER_SEC"])
        per_second = gpu + int(config.get("CPU")) * config.VCPU_PRICE_PER_SECOND + int(config.get("MEMORY")) * config.MEMORY_PRICE_PER_SECOND
        return (f"≈ ${seconds * per_second:.4f} ({config.get('GPU_TYPE')} service, {int(seconds)}s active; "
                f"list price, excludes the idle keep-alive before scale-to-zero)")
    if session["backend"] == "openai-compatible":
        return f"billed by {session['base_url']} at its own prices"

    tokens = session["tally"].tokens
    tokens_in = tokens["input"] + tokens["cache_write"] + tokens["cache_read"]
    counts = f"tokens: {tokens_in:,} in ({tokens['cache_read']:,} cached) + {tokens['output']:,} out"
    rates = config.ANTHROPIC_PRICES.get(session["model"])
    if rates is None:
        return f"{counts}  |  cost n/a (unpriced model {session['model']})"
    dollars = (
        tokens["input"] * rates[0]
        + tokens["cache_write"] * rates[0] * config.CACHE_WRITE_FACTOR
        + tokens["cache_read"] * rates[0] * config.CACHE_READ_FACTOR
        + tokens["output"] * rates[1]
    ) / 1_000_000
    return f"{counts}  |  ≈ ${dollars:.4f} ({session['model']})"


def edit_all(session: dict, candidates: list) -> list:
    """Edit every candidate in parallel and return one result row each, printing progress and the cost."""
    _preload_embedding_model()
    session["tally"].restart_clock()
    total = len(candidates)
    items.announce("total", total)
    stop = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat, args=(session, total, stop), daemon=True)
    heartbeat.start()

    results = []
    try:
        with ThreadPoolExecutor(max_workers=session["workers"]) as pool:
            futures = [pool.submit(edit_one, session, cand) for cand in candidates]
            for future in as_completed(futures):
                results.append(future.result())
    finally:
        stop.set()
        heartbeat.join(timeout=1)

    elapsed = int(session["tally"].seconds())
    ui.ok(f"editing complete: {total}/{total} · {elapsed}s")
    ui.info(cost_line(session))
    return results


# ---- Entry points ----

def tighten(state: dict, backend: str, candidates: list | None = None) -> dict:
    """Edit the document's paragraphs on one backend and fold the accepted edits back in.

    Pass explicit ``candidates`` for a targeted top-up pass; otherwise every eligible
    paragraph is selected at the run's intensity.
    """
    session = open_session(backend)
    if candidates is None:
        ui.info("selecting paragraphs to tighten...")
        candidates = get_candidates(state)
    if not candidates:
        ui.info("no paragraphs qualify for tightening")
        return state
    ui.info(f"{len(candidates)} paragraph(s) -> {BACKEND_LABEL[backend]} ({session['model']})")
    return apply_results(state, edit_all(session, candidates))


def smoke(backend: str, source: str, count: str) -> None:
    """Send paragraphs from a text file straight to a backend, skipping the diagnosis.

    Args:
        count: how many paragraphs, as a whole number, or "all".
    """
    session = open_session(backend)
    text = Path(source).read_text(encoding="utf-8")
    paragraphs = [part for part in text.split("\n\n") if len(part.split()) >= SMOKE_MIN_WORDS]
    if count != "all":
        paragraphs = paragraphs[: int(count)]
    candidates = []
    for index, paragraph in enumerate(paragraphs):
        candidates.append({
            "index": index,
            "text": paragraph,
            "budget": max(1, int(len(paragraph.split()) * SMOKE_BUDGET_SHARE)),
            "routing_reason": "smoke (no routing)",
        })
    ui.step(f"Smoke test: {len(candidates)} paragraph(s) from {Path(source).name} -> {BACKEND_LABEL[backend]}")
    results = edit_all(session, candidates)
    for result in sorted(results, key=lambda row: row["index"]):
        words = len(result["edited"].split())
        verdict = "ACCEPT" if result["accepted"] else f"REJECT ({result['reason']})"
        ui.info(f"P{result['index']}: -> {words} words  |  {verdict}")
