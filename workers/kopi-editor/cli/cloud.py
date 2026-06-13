"""GCloud LLM client: POST flagged paragraphs to the warm Cloud Run service.

Reads BASE_URL + JOB_TOKEN from config (written by `manage.py deploy`). Each
paragraph is sent to the GPU service over HTTPS; the acceptance guard runs
locally (where sentence-transformers is already loaded). The service stays warm
during a session, so after the first (cold-start) request each one is just
generation — paragraphs are sent in parallel with live progress.
"""
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cli import config, ui

_WORKERS = 4
_TIMEOUT = 300  # generous: the first request absorbs the cold start (model load)

# Cloud Run GPU list prices, USD per second (cached 2026-06; verify for your
# region). The deployed service is instance-billed (--no-cpu-throttling) at
# --gpu 1 nvidia-l4 --cpu 4 --memory 16Gi, so while the instance is active we
# pay for all three. See `_run_cost()`.
_L4_GPU_PER_SEC = 0.000233          # nvidia-l4
_VCPU_PER_SEC = 0.0000180           # per vCPU
_MEM_PER_SEC = 0.0000020            # per GiB
_DEPLOY_VCPU = 4
_DEPLOY_MEM_GIB = 16
_COST_PER_SEC = (
    _L4_GPU_PER_SEC
    + _DEPLOY_VCPU * _VCPU_PER_SEC
    + _DEPLOY_MEM_GIB * _MEM_PER_SEC
)


def _run_cost(seconds: float) -> float:
    """Estimated USD for ``seconds`` of active L4 service time (GPU+CPU+memory)."""
    return seconds * _COST_PER_SEC


def _require():
    if not config.base_url():
        raise SystemExit("no service deployed — run `python manage.py deploy` first.")
    if not config.job_token():
        raise SystemExit("no JOB_TOKEN in env.yaml — re-run `python manage.py deploy`.")


def _post_one(text: str, instructions) -> str:
    # Build the full prompt on the client and send it as `messages`; the service
    # just relays to Ollama, so prompt changes need no redeploy.
    from kopi.llm import build_messages
    url = f"{config.base_url().rstrip('/')}/tighten?token={config.job_token()}"
    body = json.dumps({"messages": build_messages(text, instructions)}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())["edited"]


def _edit_all(candidates: list) -> list:
    """Send candidates to the service in parallel, guard locally, shape results
    for step_concision.apply_results.

    A heartbeat prints elapsed time every few seconds so the wait is never
    silent — during the first (cold-start) request no paragraph has completed
    yet, and a static progress bar would look frozen for up to ~90s.
    """
    import threading
    import time
    from kopi.step_concision import edit_with_retry, _get_model

    # Pre-load the embedding model ONCE before the workers start. The guard's
    # cosine check loads sentence-transformers lazily; letting 4 threads race to
    # initialise it throws torch's "Cannot copy out of meta tensor" (concurrent
    # init is not thread-safe). One load up front removes the race.
    try:
        _get_model()
    except Exception:
        pass

    total = len(candidates)
    start = time.time()
    progress = {"done": 0}
    lock = threading.Lock()
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(5):
            with lock:
                d = progress["done"]
            elapsed = int(time.time() - start)
            extra = "  (loading the model on the GPU, up to ~90s)" if d == 0 else ""
            ui.info(f"tightening {d}/{total} done · {elapsed}s elapsed{extra}")

    hb = threading.Thread(target=heartbeat, daemon=True)
    hb.start()

    def work(cand):
        # edit_with_retry POSTs the paragraph, guards it, and on a recoverable
        # rejection re-POSTs once with a softer/corrective instruction.
        try:
            r = {"cand": cand, **edit_with_retry(_post_one, cand["text"], cand.get("instructions"))}
        except Exception as e:
            r = {"cand": cand, "error": f"service error: {e}"}
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
    elapsed = time.time() - start
    ui.ok(f"tightening complete: {total}/{total} · {int(elapsed)}s")
    ui.info(
        f"≈ ${_run_cost(elapsed):.4f} (L4 GPU service, {int(elapsed)}s active; "
        f"list price, excludes post-run idle keep-alive before scale-to-zero)"
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


def tighten(state: dict) -> dict:
    """Route the fattest paragraphs to the service and apply the edits."""
    from kopi.step_concision import get_candidates, apply_results
    _require()
    ui.info("selecting paragraphs to tighten...")
    candidates = get_candidates(state)
    if not candidates:
        ui.info("no paragraphs qualify for tightening")
        return state
    ui.info(f"{len(candidates)} paragraph(s) -> {config.service()} (first request loads the model on the GPU)")
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
        {"index": i, "text": p, "budget": max(1, int(len(p.split()) * 0.2)),
         "focus": [], "fat_index": None, "routing_reason": "smoke (no routing)"}
        for i, p in enumerate(paras)
    ]
    ui.step(f"Cloud smoke test — {len(candidates)} paragraph(s) from {Path(source).name}")
    results = _edit_all(candidates)
    for r in sorted(results, key=lambda r: r["index"]):
        ew = len(r.get("edited", "").split())
        verdict = "ACCEPT" if r.get("accepted") else f"REJECT ({r.get('reason')})"
        ui.info(f"P{r['index']}: -> {ew} words  |  {verdict}")
