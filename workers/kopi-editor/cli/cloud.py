"""Send flagged paragraphs to the deployed Cloud Run GPU service over HTTPS
using BASE_URL and JOB_TOKEN from config. The acceptance guard runs locally
while paragraphs are sent in parallel.
"""
import json
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cli import config, ui

_WORKERS = 4
_TIMEOUT = 300  # generous: the first request absorbs the cold start (model load)

# Cloud Run GPU list prices, USD per GPU-second (cached 2026-06; verify for your
# region). Instance-billed (--no-cpu-throttling): while the instance is active we
# pay GPU + CPU + memory. The shape (GPU type, vCPU, GiB) comes from config so the
# estimate tracks whichever service BASE_URL points at, not a baked-in L4.
_GPU_PER_SEC = {
    "nvidia-l4": 0.000233,
    # RTX PRO 6000 Blackwell: Google has not published a Cloud Run per-second SKU
    # we could verify here; this is a ~4x-L4 estimate (market ~$3/hr GPU) pending
    # confirmation from the console/calculator. Override via KOPI_GPU_PER_SEC.
    "nvidia-rtx-pro-6000": 0.00093,
}
_VCPU_PER_SEC = 0.0000180           # per vCPU
_MEM_PER_SEC = 0.0000020            # per GiB


def _run_cost(seconds: float) -> float:  # lint-style: ignore FN004
    """Estimated USD for ``seconds`` of active service time (GPU+CPU+memory),
    using the configured instance shape."""
    override = os.environ.get("KOPI_GPU_PER_SEC")
    if override:
        gpu_per_sec = float(override)
    else:
        gpu_per_sec = _GPU_PER_SEC.get(config.get("GPU_TYPE"), _GPU_PER_SEC["nvidia-l4"])
    per_sec = gpu_per_sec + int(config.get("CPU")) * _VCPU_PER_SEC + int(config.get("MEMORY")) * _MEM_PER_SEC
    return seconds * per_sec


def _require():
    if not config.get("BASE_URL"):
        raise SystemExit("no service deployed: run `python manage.py deploy` first.")
    if not config.get("JOB_TOKEN"):
        raise SystemExit("no JOB_TOKEN in env.yaml: re-run `python manage.py deploy`.")


def _post_one(text: str, instructions, mode: str = "firm", floor: int | None = None) -> str:
    # Send BOTH shapes so the client works against either service version:
    #  - `messages`: the new relay service uses the client-built prompt (no
    #    redeploy needed for future prompt changes);
    #  - `paragraph`/`instructions`: an older deployed service that builds the
    #    prompt itself still works (with its baked prompt) until it is redeployed.
    from kopi.llm import build_messages
    base = config.get("BASE_URL").rstrip("/")
    url = f"{base}/tighten?token={config.get('JOB_TOKEN')}"
    body = json.dumps({
        "messages": build_messages(text, instructions, config.get("LANG"), mode, floor),
        "paragraph": text,
        "instructions": instructions,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())["edited"]


class _PostRequest:
    """A callable that remembers one candidate's mode and floor, so
    ``edit_with_retry`` can call it as ``edit_fn(text, instructions)``."""

    def __init__(self, mode, floor):
        self.mode = mode
        self.floor = floor

    def __call__(self, text, instructions):
        return _post_one(text, instructions, self.mode, self.floor)


class _Progress:
    """A thread-safe done-count shared between the worker pool and the heartbeat."""

    def __init__(self):
        self._lock = threading.Lock()
        self._done = 0

    def increment(self):
        with self._lock:
            self._done += 1

    def read(self):
        with self._lock:
            return self._done


def _heartbeat(hb_state):
    """Print elapsed time every few seconds so the wait is never silent:
    during the first (cold-start) request no paragraph has completed yet, and
    a static progress bar would look frozen for up to ~90s."""
    while not hb_state["stop"].wait(5):
        done = hb_state["progress"].read()
        elapsed = int(time.time() - hb_state["start"])
        extra = "  (loading the model on the GPU, up to ~90s)" if done == 0 else ""
        ui.info(f"tightening {done}/{hb_state['total']} done · {elapsed}s elapsed{extra}")


def _work(cand, progress):
    # edit_with_retry POSTs the paragraph, guards it, and on a recoverable
    # rejection re-POSTs once with a softer/corrective instruction. The
    # paragraph's intensity (mode/floor/ceiling) comes from the candidate.
    from kopi.step_concision import edit_with_retry, _MAX_COMPRESSION as _DEFAULT_MAX_COMPRESSION
    mode, floor = cand.get("mode", "firm"), cand.get("floor")
    try:
        edit_fn = _PostRequest(mode, floor)
        result = edit_with_retry(
            edit_fn, cand["text"], cand.get("instructions"),
            cand.get("max_compression", _DEFAULT_MAX_COMPRESSION))
        r = {"cand": cand, **result}
    except Exception as e:
        r = {"cand": cand, "error": f"service error: {e}"}
    progress.increment()
    return r


def _shape_result(r):
    cand = r["cand"]
    return {
        "index": cand["index"],
        "accepted": False if r.get("error") else r["accepted"],
        "edited": cand["text"] if r.get("error") else r["edited"],
        "reason": r["error"] if r.get("error") else r["reason"],
        "saved": 0 if r.get("error") else r["saved"],
        "routing_reason": cand.get("routing_reason"),
    }


def _edit_all(candidates: list) -> list:
    """Send candidates to the service in parallel, guard locally, shape results
    for step_concision.apply_results."""
    from kopi.step_concision import _get_model

    # Pre-load the embedding model ONCE before the workers start. The guard's
    # cosine check loads sentence-transformers lazily; letting 4 threads race to
    # initialise it throws torch's "Cannot copy out of meta tensor" (concurrent
    # init is not thread-safe). One load up front removes the race.
    from kopi.progress import StepSpinner
    sp = StepSpinner("loading embedding model")
    sp.start()
    try:
        _get_model()
    except Exception:
        pass
    finally:
        sp.done()

    total = len(candidates)
    start = time.time()
    progress = _Progress()
    stop = threading.Event()

    hb_state = {"stop": stop, "progress": progress, "total": total, "start": start}
    hb = threading.Thread(target=_heartbeat, args=(hb_state,), daemon=True)
    hb.start()

    collected = []
    try:
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            futures = [pool.submit(_work, c, progress) for c in candidates]
            for fut in as_completed(futures):
                collected.append(fut.result())
    finally:
        stop.set()
        hb.join(timeout=1)
    elapsed = time.time() - start
    ui.ok(f"tightening complete: {total}/{total} · {int(elapsed)}s")
    ui.info(
        f"≈ ${_run_cost(elapsed):.4f} ({config.get('GPU_TYPE')} service, {int(elapsed)}s active; "
        f"list price, excludes post-run idle keep-alive before scale-to-zero)"
    )

    return [_shape_result(r) for r in collected]


def tighten(state: dict, candidates: list | None = None) -> dict:
    """Send paragraphs to the service and apply the edits.

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
    ui.info(f"{len(candidates)} paragraph(s) -> {config.get('SERVICE')} (first request loads the model on the GPU)")
    results = _edit_all(candidates)
    return apply_results(state, results)


def smoke(source, n):
    """Send n paragraphs from a text file straight to the service, bypassing routing."""
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
    ui.step(f"Cloud smoke test: {len(candidates)} paragraph(s) from {Path(source).name}")
    results = _edit_all(candidates)
    for r in sorted(results, key=lambda r: r["index"]):
        ew = len(r.get("edited", "").split())
        verdict = "ACCEPT" if r.get("accepted") else f"REJECT ({r.get('reason')})"
        ui.info(f"P{r['index']}: -> {ew} words  |  {verdict}")
