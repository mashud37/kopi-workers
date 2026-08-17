"""Rerun the acceptance guard on saved base and tuned eval edits, bucketing
rejections by reason and mode to show which failures the tune fixed versus
introduced, with no new inference.
"""
import json
from collections import Counter

import editor
from cli import config, ui

_CATEGORIES = ["empty", "expanded", "over-compressed", "citation", "numeric", "meaning-drift"]


def _category(reason: str) -> str:
    """Collapse a guard reason (which carries instance numbers/citations) to a bucket."""
    for c in _CATEGORIES:
        if reason.startswith(c) or c.split("-")[0] in reason:
            return c
    return "other"


def _verdict(row: dict, edit: str) -> dict:
    return editor.guard_verdict(row["original"], edit, float(row["max_compression"]))


def _bucket_table(title: str, by_cat: Counter, total: int) -> None:
    ui.info(title)
    for cat in _CATEGORIES + ["other"]:
        if by_cat.get(cat):
            ui.info(f"    {cat:<16}{by_cat[cat]:>4}  ({by_cat[cat] / total:.1%})")


def _score_rows(rows: list[dict]) -> dict:
    """Recompute the guard verdict for each saved row; tally failures, base-to-tuned
    transitions, and word-count deltas against the gold edit."""
    base_fail, tuned_fail = Counter(), Counter()
    by_mode = Counter()       # tuned failures per mode
    fixed = regressed = both = 0
    worst_dwords = []
    rejects = []

    for r in rows:
        bv, tv = _verdict(r, r["base_edit"]), _verdict(r, r["tuned_edit"])
        if not bv["accepted"]:
            base_fail[_category(bv["reason"])] += 1
        if not tv["accepted"]:
            tuned_fail[_category(tv["reason"])] += 1
            by_mode[r.get("mode", "?")] += 1
            rejects.append({
                "key": r.get("key"),
                "mode": r.get("mode"),
                "reason": tv["reason"],
                "tuned_edit": r["tuned_edit"],
            })
        if bv["accepted"] and not tv["accepted"]:
            regressed += 1
        if not bv["accepted"] and tv["accepted"]:
            fixed += 1
        if not bv["accepted"] and not tv["accepted"]:
            both += 1
        gold_w, tuned_w = len(r["edit"].split()), len(r["tuned_edit"].split())
        worst_dwords.append((abs(tuned_w - gold_w), r.get("key"), r.get("mode"), gold_w, tuned_w))

    return {
        "base_fail": base_fail,
        "tuned_fail": tuned_fail,
        "by_mode": by_mode,
        "fixed": fixed,
        "regressed": regressed,
        "both": both,
        "worst_dwords": worst_dwords,
        "rejects": rejects,
    }


def run() -> dict:
    path = config.data_dir() / "eval" / "local.jsonl"
    if not path.exists():
        raise SystemExit(f"no saved edits at {path}, run `evaluate` once first.")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    editor.preload_embedding_model()
    n = len(rows)
    ui.step(f"failure analysis on {n} saved held-out edits (guard recomputed, no inference)")

    scores = _score_rows(rows)
    base_fail, tuned_fail, by_mode = scores["base_fail"], scores["tuned_fail"], scores["by_mode"]
    fixed, regressed, both = scores["fixed"], scores["regressed"], scores["both"]
    worst_dwords, rejects = scores["worst_dwords"], scores["rejects"]

    ui.info(f"guard pass: base {1 - sum(base_fail.values()) / n:.3f}  "
            f"tuned {1 - sum(tuned_fail.values()) / n:.3f}")
    _bucket_table("tuned rejections by reason:", tuned_fail, n)
    _bucket_table("base rejections by reason (for contrast):", base_fail, n)

    ui.info("tuned rejections by mode:")
    for mode, c in by_mode.most_common():
        ui.info(f"    {mode:<16}{c:>4}")

    ui.info(f"base→tuned transitions:  fixed {fixed}   regressed {regressed}   "
            f"both-fail {both}")

    worst_dwords.sort(reverse=True)
    ui.info("worst over/under-cutting vs Opus (|tuned-gold| words):")
    for d, key, mode, gw, tw in worst_dwords[:8]:
        ui.info(f"    {key:<22} {mode:<8} gold {gw:>3}w  tuned {tw:>3}w  (Δ{d})")

    out = config.data_dir() / "eval" / "failures.jsonl"
    out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rejects) + "\n",
                   encoding="utf-8")
    ui.ok(f"{len(rejects)} tuned rejections written to {out} for inspection")
    return {
        "base_fail": dict(base_fail),
        "tuned_fail": dict(tuned_fail),
        "fixed": fixed,
        "regressed": regressed,
        "both": both,
    }
