"""Join mined and generated samples by key into SFT (`messages` ending in
Opus) and DPO (`chosen`=Opus, `rejected`=Qwen) datasets, splitting by
document so no paragraph leaks across splits.
"""
import hashlib
import json
import re

import editor
from cli import config, ui

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text or "").strip().lower()


def _prompt_messages(r: dict) -> list[dict]:
    return editor.build_messages(
        r["original"], r.get("instructions"), r.get("lang", "british"), r["mode"], r.get("floor"))


def _write(path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_split(split: str, slots: list[dict], seen_norm: set[str]) -> dict:
    """Build and write the SFT/DPO rows for one split; returns their counts."""
    out = config.data_dir() / "out"
    sft, dpo, test_rows = [], [], []
    for slot in slots:
        opus_r = slot.get("opus")
        qwen_r = slot.get("qwen")
        if not (opus_r and opus_r["accepted"]):
            continue
        key_norm = _norm(opus_r["original"])
        if key_norm in seen_norm:
            continue
        seen_norm.add(key_norm)
        assistant_turn = {"role": "assistant", "content": opus_r["edit"]}
        sft.append({"messages": _prompt_messages(opus_r) + [assistant_turn]})
        if split == "test":
            test_rows.append(opus_r)
        # Only a valid preference pair if both edited the SAME original and actually differ.
        if (qwen_r and _norm(opus_r["original"]) == _norm(qwen_r["original"])
                and _norm(opus_r["edit"]) != _norm(qwen_r["edit"])):
            dpo.append({
                "prompt": _prompt_messages(opus_r),
                "chosen": [{"role": "assistant", "content": opus_r["edit"]}],
                "rejected": [{"role": "assistant", "content": qwen_r["edit"]}],
            })
    if split == "test":
        _write(out / "test.jsonl", test_rows)
    else:
        _write(out / f"sft_{split}.jsonl", sft)
        _write(out / f"dpo_{split}.jsonl", dpo)
    ui.info(f"[{split}] {len(sft)} SFT · {len(dpo)} DPO")
    return {"sft": len(sft), "dpo": len(dpo)}


def build() -> dict:
    cfg = config.settings().get("split", {})
    val, test = float(cfg.get("val", 0.10)), float(cfg.get("test", 0.15))

    ui.step("building datasets from samples")
    pairs_dir = config.data_dir() / "pairs"
    files = sorted(pairs_dir.glob("*.jsonl")) if pairs_dir.exists() else []
    if not files:
        raise SystemExit("no samples found, run `mine` (and optionally `generate`) first.")
    records = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    ui.info(f"{len(records)} samples loaded ("
            + ", ".join(f"{r}={sum(1 for x in records if x['role'] == r)}"
                        for r in ("opus", "qwen", "sonnet", "haiku")) + ")")

    # Group by key for DPO pairing; pick the best (accepted) Opus and any Qwen per key.
    by_key: dict[str, dict[str, dict]] = {}
    for r in records:
        slot = by_key.setdefault(r["key"], {})
        if r["role"] == "opus" and (r["accepted"] or "opus" not in slot):
            slot["opus"] = r
        elif r["role"] == "qwen" and "qwen" not in slot:
            slot["qwen"] = r

    out = config.data_dir() / "out"
    buckets = {"train": [], "val": [], "test": []}
    for key, slot in by_key.items():
        doc = (slot.get("opus") or slot.get("qwen"))["doc"]
        digest = int(hashlib.sha1(doc.encode("utf-8")).hexdigest(), 16) % 10_000 / 10_000
        if digest < test:
            split = "test"
        elif digest < test + val:
            split = "val"
        else:
            split = "train"
        buckets[split].append(slot)

    seen_norm: set[str] = set()
    counts = {}
    for split, slots in buckets.items():
        counts[split] = _build_split(split, slots, seen_norm)

    manifest = {"split": {"val": val, "test": test}, "counts": counts}
    _write(out / "manifest.jsonl", [manifest])
    ui.ok(f"datasets written -> {out.relative_to(config.data_dir().parent)}")
    if counts["test"]["sft"] == 0:
        ui.warn("held-out test is empty, mine/generate more before trusting eval")
    if sum(c["dpo"] for c in counts.values()) == 0:
        ui.warn("no DPO pairs: no paragraph has both an Opus and a Qwen edit. "
                "Run `complete` to fill the missing side, or `generate` (both at once).")
    return manifest
