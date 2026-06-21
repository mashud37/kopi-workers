"""Anthropic API LLM backend — an alternative to the self-hosted GPU service.

Set ``LLM: api`` in env.yaml (or via ``manage.py settings``) with an
ANTHROPIC_API_KEY. Reuses the same paragraph prompt as the local/cloud paths;
the acceptance guard runs locally. No GPU, no cold start — each paragraph is a
sub-second Messages API call, sent in parallel with live progress.

Uses the official ``anthropic`` SDK (the workspace standard, per pepa-sum and
the claude-api policy), imported lazily so it isn't required unless LLM=api.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cli import config, ui

_WORKERS = 4
_MAX_TOKENS = 1024

# Published Anthropic list prices, USD per 1M tokens (input, output). Cached
# 2026-06; update if rates change. Prompt-cache writes bill at 1.25x the input
# rate, reads at 0.10x — applied in _cost().
_PRICING = {
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
    if not config.anthropic_api_key():
        raise SystemExit("no Anthropic API key — set it with `python manage.py settings`.")


def _client():
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic SDK not installed — run: pip install anthropic")
    return anthropic.Anthropic(api_key=config.anthropic_api_key())


def _edit_one(client, model: str, text: str, instructions, lang: str = "british",
              mode: str = "firm", floor: int | None = None) -> tuple[str, object]:
    # The system prompt is identical for every paragraph at the same intensity, so
    # mark it cacheable: the first call per (lang, mode) writes it, the rest read it
    # at 0.10x input price — a large saving when tightening a whole document.
    from kopi.llm import _system_for, _build_user_message
    resp = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=[{"type": "text", "text": _system_for(lang, mode), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": _build_user_message(text, instructions, floor)}],
    )
    out = "".join(b.text for b in resp.content if b.type == "text").strip()
    return out, resp.usage


def _edit_all(candidates: list) -> list:
    """Send candidates to Anthropic in parallel, guard locally, shape results for
    step_concision.apply_results. A heartbeat keeps the wait visible."""
    from kopi.step_concision import edit_with_retry, _get_model, _MAX_COMPRESSION as _DEFAULT_MAX_COMPRESSION

    # Pre-load the embedding model ONCE before the workers start, so the parallel
    # guard checks don't race to initialise sentence-transformers (concurrent
    # torch init throws "Cannot copy out of meta tensor").
    from kopi.progress import StepSpinner
    sp = StepSpinner("loading embedding model")
    sp.start()
    try:
        _get_model()
    except Exception:
        pass
    finally:
        sp.done()

    client = _client()
    model = config.anthropic_model()
    lang = config.lang()
    total = len(candidates)
    start = time.time()
    progress = {"done": 0}
    tokens = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    lock = threading.Lock()
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(5):
            with lock:
                d = progress["done"]
            ui.info(f"editing {d}/{total} done · {int(time.time() - start)}s elapsed")

    hb = threading.Thread(target=heartbeat, daemon=True)
    hb.start()

    def _make_edit_fn(mode, floor):
        def _edit_fn(text, instructions):
            edited, usage = _edit_one(client, model, text, instructions, lang, mode, floor)
            with lock:  # count tokens for every call, including a corrective retry
                tokens["input"] += getattr(usage, "input_tokens", 0) or 0
                tokens["output"] += getattr(usage, "output_tokens", 0) or 0
                tokens["cache_write"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
                tokens["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0
            return edited
        return _edit_fn

    def work(cand):
        # edit_with_retry calls the API, guards locally, and on a recoverable
        # rejection re-prompts once with a softer/corrective instruction. The
        # paragraph's intensity (mode/floor/ceiling) comes from the candidate.
        edit_fn = _make_edit_fn(cand.get("mode", "firm"), cand.get("floor"))
        try:
            r = {"cand": cand, **edit_with_retry(
                edit_fn, cand["text"], cand.get("instructions"),
                cand.get("max_compression", _DEFAULT_MAX_COMPRESSION))}
        except Exception as e:
            r = {"cand": cand, "error": f"api error: {e}"}
        with lock:
            progress["done"] += 1
        return r

    collected = []
    try:
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            futures = [pool.submit(work, c) for c in candidates]
            for fut in as_completed(futures):
                collected.append(fut.result())
    finally:
        stop.set()
        hb.join(timeout=1)
    ui.ok(f"editing complete: {total}/{total} · {int(time.time() - start)}s")

    in_total = tokens["input"] + tokens["cache_write"] + tokens["cache_read"]
    cost = _cost(model, tokens)
    cost_str = f"≈ ${cost:.4f}" if cost is not None else "cost n/a (unpriced model)"
    ui.info(
        f"tokens: {in_total:,} in ({tokens['cache_read']:,} cached) + "
        f"{tokens['output']:,} out  |  {cost_str} ({model})"
    )

    results = []
    for r in collected:
        cand = r["cand"]
        results.append({
            "index": cand["index"],
            "accepted": False if r.get("error") else r["accepted"],
            "edited": cand["text"] if r.get("error") else r["edited"],
            "reason": r["error"] if r.get("error") else r["reason"],
            "saved": 0 if r.get("error") else r["saved"],
            "routing_reason": cand.get("routing_reason"),
        })
    return results


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
    ui.info(f"{len(candidates)} paragraph(s) -> Anthropic {config.anthropic_model()}")
    return apply_results(state, _edit_all(candidates))


def smoke(source, n):
    """Send n paragraphs from a text file straight to the API, bypassing routing.

    A diagnostic that exercises the API path end-to-end without the spaCy
    candidate selection — `n` is an integer or "all".
    """
    _require()
    text = Path(source).read_text(encoding="utf-8")
    paras = [p for p in text.split("\n\n") if len(p.split()) >= 40]
    if n != "all":
        paras = paras[:int(n)]
    candidates = [
        {"index": i, "text": p, "budget": max(1, int(len(p.split()) * 0.2)),
         "focus": [], "fat_index": None, "routing_reason": "smoke (no routing)"}
        for i, p in enumerate(paras)
    ]
    ui.step(f"API smoke test — {len(candidates)} paragraph(s) via {config.anthropic_model()}")
    results = _edit_all(candidates)
    for r in sorted(results, key=lambda r: r["index"]):
        ew = len(r.get("edited", "").split())
        verdict = "ACCEPT" if r.get("accepted") else f"REJECT ({r.get('reason')})"
        ui.info(f"P{r['index']}: -> {ew} words  |  {verdict}")
