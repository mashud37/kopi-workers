"""Fill the missing model side of a mined paragraph, running whichever of
Qwen or Opus is absent, so a DPO pair exists. Targets only the gaps mining
left.
"""
import json
import time

import editor
from cli import config, ui
from distil import samples


def _load_existing() -> dict[str, dict[str, dict]]:  # lint-style: ignore FN004
    pairs_dir = config.data_dir() / "pairs"
    by_key: dict[str, dict[str, dict]] = {}
    for f in sorted(pairs_dir.glob("*.jsonl")) if pairs_dir.exists() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            by_key.setdefault(r["key"], {})[r["role"]] = r
    return by_key


def _unit(r: dict) -> dict:
    return {
        "text": r["original"],
        "instructions": r.get("instructions"),
        "mode": r["mode"],
        "floor": r.get("floor"),
        "max_compression": r["max_compression"],
        "index": r["idx"],
        "paper": r["doc"],
    }


def _opus_unit(r: dict) -> dict:  # lint-style: ignore FN004
    return {
        "doc": r["doc"],
        "idx": r["idx"],
        "text": r["original"],
        "instructions": r.get("instructions"),
        "mode": r["mode"],
        "floor": r.get("floor"),
        "max_compression": r["max_compression"],
    }


def _fill_from_qwen(rows_needed: list[dict]) -> list[dict]:
    from teachers import qwen
    qwen.require()
    ui.step(f"running served Qwen on {len(rows_needed)} Opus-only paragraphs")
    rows = []
    for i, r in enumerate(rows_needed, 1):
        ui.info(f"[{i}/{len(rows_needed)}] {r['doc'][:50]}")
        try:
            text = qwen.edit(_unit(r))
            rows.append(samples.make(
                {
                    "source": "completed",
                    "doc": r["doc"],
                    "idx": r["idx"],
                    "model": "qwen-served",
                    "lang": config.lang(),
                },
                r,
                text))
        except Exception as e:
            ui.warn(f"qwen failed: {e}")
    return rows


def _fill_from_opus(rows_needed: list[dict]) -> list[dict]:
    from teachers import opus
    cl = opus.client()
    ui.step(f"running Opus on {len(rows_needed)} Qwen-only paragraphs")
    rows = []
    for i, r in enumerate(rows_needed, 1):
        ui.info(f"[{i}/{len(rows_needed)}] {r['doc'][:50]}")
        try:
            result = opus.edit(cl, _unit(r))
            rows.append(samples.make(
                {
                    "source": "completed",
                    "doc": r["doc"],
                    "idx": r["idx"],
                    "model": config.opus_model(),
                    "lang": config.lang(),
                },
                r,
                result["text"]))
        except Exception as e:
            ui.warn(f"opus failed: {e}")
    return rows


def run(fill: str = "both", limit: int | None = None, batch: bool = False) -> None:
    """Generate the missing side. `fill` in {qwen, opus, both}; `batch` sends the
    Opus side through the Batch API (collect later) instead of online."""
    by_key = _load_existing()
    if not by_key:
        raise SystemExit("nothing mined yet, run `mine` first.")

    need_qwen = [s["opus"] for s in by_key.values() if "opus" in s and "qwen" not in s]
    need_opus = [s["qwen"] for s in by_key.values() if "qwen" in s and "opus" not in s]
    if fill == "qwen":
        need_opus = []
    elif fill == "opus":
        need_qwen = []
    if limit:
        need_qwen, need_opus = need_qwen[:limit], need_opus[:limit]

    ui.step(f"completing pairs: {len(need_qwen)} need Qwen, {len(need_opus)} need Opus")
    editor.preload_embedding_model()
    rows = []

    if need_opus and batch:
        from distil import batch as batchmod
        batchmod.submit([_opus_unit(r) for r in need_opus], "complete")
        need_opus = []  # gold side comes later via `collect`

    if need_qwen:
        rows += _fill_from_qwen(need_qwen)

    if need_opus:
        rows += _fill_from_opus(need_opus)

    if not rows:
        ui.ok("nothing to complete: every mined paragraph already has both sides")
        return
    out_dir = config.data_dir() / "pairs"
    path = out_dir / f"completed_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    ui.ok(f"wrote {len(rows)} completed samples -> {path.relative_to(config.data_dir().parent)}")
