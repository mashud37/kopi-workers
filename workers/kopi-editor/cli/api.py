"""Edit paragraphs through the Anthropic Messages API when `LLM: api` is set,
instead of the self-hosted GPU service. Uses the same prompt and acceptance
guard as the other backends.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cli import config, ui

_WORKERS = 4
_MAX_TOKENS = 4096
_EFFORT = "low"
_HEARTBEAT_SECONDS = 5

# Published Anthropic list prices, USD per 1M tokens (input, output). Cached
# 2026-10; update if rates change. Prompt-cache writes bill at 1.25x the input
# rate, reads at 0.10x (applied in _cost()).
_PRICING = {
    "claude-fable-5-1":  (10.0, 50.0),
    "claude-opus-5-5":   (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-fable-5":    (10.0, 50.0),
    "claude-opus-4-8":   (5.0, 25.0),
    "claude-opus-4-7":   (5.0, 25.0),
    "claude-opus-4-6":   (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5":  (1.0, 5.0),
}


def _cost(model: str, totals: dict) -> float | None:
    """USD for the accumulated token totals, or None if the model isn't priced."""
    rates = _PRICING.get(model)
    if not rates:
        return None
    in_rate, out_rate = rates
    return (
        totals["input"] * in_rate
        + totals["cache_write"] * in_rate * 1.25
        + totals["cache_read"] * in_rate * 0.10
        + totals["output"] * out_rate
    ) / 1_000_000


def _require():
    if not config.get("ANTHROPIC_API_KEY"):
        raise SystemExit("no Anthropic API key: set it with `python manage.py settings`.")


def _edit_one(client, text: str, instructions, style: dict) -> dict:
    """One API call, returning the edited `text` and the call's `usage`.

    The system prompt is identical for every paragraph at the same intensity, so
    it is marked cacheable: the first call per (lang, mode) writes it and the rest
    read it at 0.10x input price, a large saving when tightening a whole document.
    """
    from kopi.llm import _system_for, _build_user_message

    system = _system_for(style["lang"], style["mode"])
    request = {
        "model": style["model"],
        "max_tokens": _MAX_TOKENS,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user",
                      "content": _build_user_message(text, instructions, style["floor"])}],
    }
    if not style["model"].startswith("claude-haiku"):
        request["output_config"] = {"effort": _EFFORT}
    resp = client.messages.create(**request)
    out = "".join(b.text for b in resp.content if b.type == "text").strip()
    return {"text": out, "usage": resp.usage}


class _Tally:
    """What the worker threads share: how many paragraphs are done, and the token bill."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self.started = time.time()
        self.tokens = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
        self.guard = threading.Lock()

    def add_usage(self, usage) -> None:
        with self.guard:
            self.tokens["input"] += getattr(usage, "input_tokens", 0) or 0
            self.tokens["output"] += getattr(usage, "output_tokens", 0) or 0
            self.tokens["cache_write"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
            self.tokens["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0

    def finished_one(self) -> None:
        with self.guard:
            self.done += 1

    def elapsed(self) -> int:
        return int(time.time() - self.started)

    def line(self) -> str:
        with self.guard:
            done = self.done
        return f"editing {done}/{self.total} done · {self.elapsed()}s elapsed"


class _ApiCall:
    """One paragraph's call settings, held so a corrective retry asks on the same terms."""

    def __init__(self, client, style: dict, tally: _Tally) -> None:
        self.client = client
        self.style = style
        self.tally = tally

    def edit(self, text: str, instructions) -> str:
        answer = _edit_one(self.client, text, instructions, self.style)
        self.tally.add_usage(answer["usage"])  # counted for a corrective retry too
        return answer["text"]


def _beat(tally: _Tally, stop) -> None:
    """Report progress every few seconds so a long API run never looks stalled."""
    while not stop.wait(_HEARTBEAT_SECONDS):
        ui.info(tally.line())


def _work(cand: dict, session: dict) -> dict:
    """Edit one candidate through the API, guarded, with one corrective retry.

    `edit_with_retry` calls the API, guards locally, and on a recoverable
    rejection re-prompts once with a softer instruction. The paragraph's
    intensity (mode, floor, ceiling) comes from the candidate.
    """
    from kopi.step_concision import edit_with_retry, _MAX_COMPRESSION

    caller = _ApiCall(session["client"], {
        "model": session["model"],
        "lang": session["lang"],
        "mode": cand.get("mode", "firm"),
        "floor": cand.get("floor"),
    }, session["tally"])
    try:
        outcome = {"cand": cand, **edit_with_retry(
            caller.edit, cand["text"], cand.get("instructions"),
            cand.get("max_compression", _MAX_COMPRESSION))}
    except Exception as error:
        outcome = {"cand": cand, "error": f"api error: {error}"}
    session["tally"].finished_one()
    return outcome


def _preload_guard_model() -> None:
    """Load the embedding model before the workers start.

    The parallel guard checks would otherwise race to initialise
    sentence-transformers, and concurrent torch init throws "Cannot copy out of
    meta tensor".
    """
    from kopi.step_concision import _get_model
    from kopi.progress import StepSpinner

    sp = StepSpinner("loading embedding model")
    sp.start()
    try:
        _get_model()
    except Exception:
        pass
    finally:
        sp.done()


def _open_client():
    """An Anthropic client on the configured key."""
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic SDK not installed, run: pip install anthropic")
    return anthropic.Anthropic(api_key=config.get("ANTHROPIC_API_KEY"))


def _report_cost(model: str, tokens: dict) -> None:
    """Print what the run spent, or say so when the model has no published price."""
    in_total = tokens["input"] + tokens["cache_write"] + tokens["cache_read"]
    cost = _cost(model, tokens)
    cost_str = f"≈ ${cost:.4f}" if cost is not None else "cost n/a (unpriced model)"
    ui.info(
        f"tokens: {in_total:,} in ({tokens['cache_read']:,} cached) + "
        f"{tokens['output']:,} out  |  {cost_str} ({model})"
    )


def _shape_results(collected: list) -> list:
    """Turn each finished call into the row `step_concision.apply_results` expects."""
    results = []
    for r in collected:
        cand = r["cand"]
        failed = r.get("error")
        results.append({
            "index": cand["index"],
            "accepted": False if failed else r["accepted"],
            "edited": cand["text"] if failed else r["edited"],
            "reason": failed if failed else r["reason"],
            "saved": 0 if failed else r["saved"],
            "routing_reason": cand.get("routing_reason"),
        })
    return results


def _edit_all(candidates: list) -> list:
    """Send candidates to Anthropic in parallel, guard locally, shape the results.

    A heartbeat thread keeps the wait visible while the workers run.
    """
    _preload_guard_model()
    session = {
        "client": _open_client(),
        "model": config.get("ANTHROPIC_MODEL"),
        "lang": config.get("LANG"),
        "tally": _Tally(len(candidates)),
    }
    tally = session["tally"]

    stop = threading.Event()
    heartbeat = threading.Thread(target=_beat, args=(tally, stop), daemon=True)
    heartbeat.start()

    collected = []
    try:
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            futures = [pool.submit(_work, cand, session) for cand in candidates]
            for fut in as_completed(futures):
                collected.append(fut.result())
    finally:
        stop.set()
        heartbeat.join(timeout=1)

    ui.ok(f"editing complete: {tally.total}/{tally.total} · {tally.elapsed()}s")
    _report_cost(session["model"], tally.tokens)
    return _shape_results(collected)


def tighten(state: dict, candidates: list | None = None) -> dict:
    """Send paragraphs to the Anthropic API and apply the edits.

    Pass explicit ``candidates`` for a targeted top-up pass; otherwise every
    eligible paragraph is selected at the run's intensity.
    """
    from kopi.step_concision import get_candidates, apply_results
    _require()
    if candidates is None:
        ui.info("selecting paragraphs to tighten...")
        candidates = get_candidates(state)
    if not candidates:
        ui.info("no paragraphs qualify for tightening")
        return state
    ui.info(f"{len(candidates)} paragraph(s) -> Anthropic {config.get('ANTHROPIC_MODEL')}")
    return apply_results(state, _edit_all(candidates))


def smoke(source, n):
    """Send n paragraphs from a text file straight to the API, bypassing routing.

    A diagnostic that exercises the API path end-to-end without the spaCy
    candidate selection: `n` is an integer or "all".
    """
    _require()
    text = Path(source).read_text(encoding="utf-8")
    paras = [p for p in text.split("\n\n") if len(p.split()) >= 40]
    if n != "all":
        paras = paras[:int(n)]
    candidates = [
        {
            "index": i,
            "text": p,
            "budget": max(1, int(len(p.split()) * 0.2)),
            "focus": [],
            "fat_index": None,
            "routing_reason": "smoke (no routing)",
        }
        for i, p in enumerate(paras)
    ]
    ui.step(f"API smoke test: {len(candidates)} paragraph(s) via {config.get('ANTHROPIC_MODEL')}")
    results = _edit_all(candidates)
    for r in sorted(results, key=lambda r: r["index"]):
        ew = len(r.get("edited", "").split())
        verdict = "ACCEPT" if r.get("accepted") else f"REJECT ({r.get('reason')})"
        ui.info(f"P{r['index']}: -> {ew} words  |  {verdict}")
