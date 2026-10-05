"""Send units to Opus through the Anthropic Batch API: `submit` fires a
batch and persists a resumable manifest, `collect` polls it and writes the
gold samples once it ends.
"""
import json
import time

from cli import config, ui
from distil import samples
from teachers import opus


def submit(units: list[dict], kind: str) -> str:
    """Submit an Opus batch for `units`, persist the manifest, return the batch id."""
    cl = opus.client()
    requests = [opus.build_request(f"u{i}", u) for i, u in enumerate(units)]
    ui.step(f"submitting Opus batch: {len(requests)} requests ({kind})")
    batch = opus.submit_batch(cl, requests)

    batches_dir = config.data_dir() / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)
    bdir = batches_dir / batch.id
    bdir.mkdir(parents=True, exist_ok=True)
    with (bdir / "units.jsonl").open("w", encoding="utf-8") as f:
        for i, u in enumerate(units):
            f.write(json.dumps({"custom_id": f"u{i}", **u}, ensure_ascii=False) + "\n")
    (bdir / "meta.json").write_text(
        json.dumps({
            "id": batch.id,
            "kind": kind,
            "submitted": time.time(),
            "status": batch.processing_status,
            "collected": False,
        }),
        encoding="utf-8")
    ui.ok(f"batch {batch.id} submitted ({batch.processing_status})")
    ui.info("Opus runs asynchronously (minutes, up to 24h). Collect when ready:")
    ui.info(f"  python manage.py collect --batch {batch.id}   (or just `collect` for all)")
    return batch.id


def _harvest(cl, bdir) -> bool:
    """Collect one ended batch. Returns True if it was ended and written."""
    meta = json.loads((bdir / "meta.json").read_text(encoding="utf-8"))
    batch = opus.batch_status(cl, meta["id"])
    if batch.processing_status != "ended":
        ui.info(f"{meta['id']}: {batch.processing_status} "
                f"(processing {getattr(batch.request_counts, 'processing', '?')})")
        return False

    units = {}
    for line in (bdir / "units.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            units[record["custom_id"]] = record

    rows, errors = [], 0
    for res in opus.batch_results(cl, meta["id"]):
        u = units.get(res.custom_id)
        if u is None:
            continue
        if res.result.type != "succeeded":
            errors += 1
            continue
        text = "".join(b.text for b in res.result.message.content if b.type == "text").strip()
        rows.append(samples.make(
            {
                "source": "batch",
                "doc": u["doc"],
                "idx": u["idx"],
                "model": config.opus_model(),
                "lang": config.lang(),
            },
            {**u, "original": u["text"]},
            text))

    out = config.data_dir() / "pairs" / f"batch_{meta['id']}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    meta["collected"] = True
    (bdir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    ui.ok(f"collected {len(rows)} Opus samples from {meta['id']}"
          + (f" ({errors} errored)" if errors else "")
          + f" -> {out.relative_to(config.data_dir().parent)}")
    return True


def collect(batch_id: str | None = None, wait: bool = False) -> None:
    """Collect ended batches. With `wait`, poll pending ones until they finish."""
    import editor
    cl = opus.client()
    editor.preload_embedding_model()  # the guard's cosine check, before harvesting

    root = config.data_dir() / "batches"
    targets = []
    if batch_id:
        targets = [root / batch_id]
    if not batch_id and root.exists():
        for d in sorted(root.iterdir()):
            meta = d / "meta.json"
            if meta.exists() and not json.loads(meta.read_text(encoding="utf-8")).get("collected"):
                targets.append(d)
    if not targets or (batch_id and not targets[0].exists()):
        ui.info("no pending batches to collect")
        return

    remaining = list(targets)
    while remaining:
        still = []
        for bdir in remaining:
            meta = bdir / "meta.json"
            if not meta.exists() or json.loads(meta.read_text(encoding="utf-8")).get("collected"):
                continue
            if not _harvest(cl, bdir):
                still.append(bdir)
        if not wait or not still:
            if still:
                ui.info(f"{len(still)} batch(es) still processing, re-run `collect` later")
            break
        time.sleep(30)
        remaining = still
