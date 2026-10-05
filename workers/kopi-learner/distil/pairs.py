"""Generate training samples from units via both teachers: the served Qwen
online, Opus online or through the Batch API. Feeds mine, documents, and
generate, the three unit sources.
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import editor
from cli import config, ui

_WORKERS = 4


def _write(records: list[dict], prefix: str):
    out_dir = config.data_dir() / "pairs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ui.ok(f"wrote {len(records)} samples -> {path.relative_to(config.data_dir().parent)}")
    return path


class _Progress:
    """How many units are done so far, shared and updated across worker threads."""

    def __init__(self, total: int):
        self.total = total
        self.done = 0
        self.start = time.time()
        self.lock = threading.Lock()

    def bump(self) -> None:
        with self.lock:
            self.done += 1


def _heartbeat(stop: threading.Event, progress: _Progress, label: str) -> None:
    while not stop.wait(5):
        elapsed = int(time.time() - progress.start)
        ui.info(f"[{progress.done}/{progress.total}] {label} · {elapsed}s elapsed")


def _run_one(unit: dict, fn, fn_args: tuple, progress: _Progress):
    try:
        result = fn(unit, *fn_args)
    except Exception as e:
        result = ("error", e)
    progress.bump()
    return result


def _parallel(units: list[dict], fn, label: str, fn_args: tuple = ()) -> list:
    """Run `fn(unit, *fn_args)` over units in parallel with a live [i/N] heartbeat."""
    progress = _Progress(len(units))
    stop = threading.Event()

    hb = threading.Thread(target=_heartbeat, args=(stop, progress, label), daemon=True)
    hb.start()

    collected = []
    try:
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            futures = [pool.submit(_run_one, u, fn, fn_args, progress) for u in units]
            for fut in as_completed(futures):
                collected.append(fut.result())
    finally:
        stop.set()
        hb.join(timeout=1)
    ui.ok(f"{label} complete: {progress.total} paragraphs · {int(time.time() - progress.start)}s")
    return collected


class _TokenCounter:
    """Running Opus token usage across worker threads, added to under a lock."""

    def __init__(self):
        self.totals = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
        self.lock = threading.Lock()

    def add(self, usage: dict) -> None:
        with self.lock:
            for k in self.totals:
                self.totals[k] += usage[k]


def _opus_sample(unit: dict, cl, tokens: _TokenCounter) -> dict:
    from distil import samples
    from teachers import opus

    result = opus.edit(cl, unit)
    tokens.add(result["usage"])
    return samples.make(
        {
            "source": "online",
            "doc": unit["doc"],
            "idx": unit["idx"],
            "model": config.opus_model(),
            "lang": config.lang(),
        },
        {**unit, "original": unit["text"]},
        result["text"])


def _opus_samples_online(units: list[dict]) -> list[dict]:
    from teachers import opus

    cl = opus.client()
    tokens = _TokenCounter()

    rows = [r for r in _parallel(units, _opus_sample, "Opus (online)", (cl, tokens))
            if not isinstance(r, tuple)]
    totals = tokens.totals
    c = opus.cost(totals)
    in_total = totals["input"] + totals["cache_write"] + totals["cache_read"]
    cost_str = f"≈ ${c:.4f}" if c is not None else "cost n/a"
    ui.info(f"Opus tokens: {in_total:,} in ({totals['cache_read']:,} cached) + "
            f"{totals['output']:,} out  |  {cost_str} ({config.opus_model()})")
    return rows


def _qwen_sample(unit: dict) -> dict:
    from distil import samples
    from teachers import qwen

    text = qwen.edit(unit)
    return samples.make(
        {
            "source": "qwen",
            "doc": unit["doc"],
            "idx": unit["idx"],
            "model": "qwen-served",
            "lang": config.lang(),
        },
        {**unit, "original": unit["text"]},
        text)


def produce(units: list[dict], tag: str, batch: bool) -> None:
    """Run both teachers over `units`. Qwen is always online (served); Opus is
    online, or submitted as a Batch API job when `batch` (collect later)."""
    if not units:
        raise SystemExit("no units to process.")
    from teachers import qwen
    qwen.require()
    editor.preload_embedding_model()  # before threads: guard cosine init is not thread-safe

    ui.step("1/2 served Qwen (rejected side)")

    qwen_rows = [r for r in _parallel(units, _qwen_sample, "Qwen (served)")
                 if not isinstance(r, tuple)]
    _write(qwen_rows, f"{tag}_qwen")

    if batch:
        ui.step("2/2 Opus via Batch API (gold side, 50% cheaper)")
        from distil import batch as batchmod
        batchmod.submit(units, tag)
    else:
        ui.step("2/2 Opus online (gold side)")
        _write(_opus_samples_online(units), f"{tag}_opus")
        ui.info("next: `python manage.py build`")


def mine_to_disk():
    from corpus import bundles
    return _write(bundles.mine(), "mined")


def documents_to_disk(batch: bool):
    from corpus import documents
    ui.step("Document run plan: 1) read input/  2) served Qwen + Opus edits")
    produce(documents.collect(), "docs", batch)


def generate_to_disk(papers: int, max_paragraphs: int, seed: int, batch: bool):
    from corpus import paragraphs
    ui.step("Expansion plan: 1) sample corpus  2) served Qwen + Opus edits")
    produce(paragraphs.collect(papers, max_paragraphs, seed), "gen", batch)
