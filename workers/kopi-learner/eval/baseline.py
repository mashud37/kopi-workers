"""Score whether the tuned adapter beats the prompt-only base on held-out
paragraphs, both served by the same Qwen endpoint, on meaning closeness to
Opus, word-delta, and guard pass rate.
"""
import json

import editor
from cli import config, ui
from eval import transport


def _load_test() -> list[dict]:
    path = config.data_dir() / "out" / "test.jsonl"
    if not path.exists():
        raise SystemExit("no held-out test set, run `build` first (data/out/test.jsonl).")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _require_endpoint() -> None:
    if not config.qwen_base_url():
        raise SystemExit("no qwen_base_url, point kopi-editor at the deployed vLLM service first.")
    if not config.qwen_token():
        raise SystemExit("no qwen_token: the served vLLM service JOB_TOKEN (kopi-editor env.yaml).")


def build_requests(records: list[dict]) -> list[dict]:
    """Attach each record's exact production [system, user] messages, so the POST loop
    (here or in the cloud job) carries everything it needs and never imports editor."""
    out = []
    for r in records:
        msgs = editor.build_messages(r["original"], r.get("instructions"),
                                     r.get("lang", "british"), r["mode"], r.get("floor"))
        out.append({**r, "messages": msgs})
    return out


def _score(records: list[dict], edits: list[str]) -> dict:
    cos, dwords, passed = [], [], 0
    for r, edit in zip(records, edits):
        gold = r["edit"]
        cos.append(editor.cosine(edit, gold))
        dwords.append(abs(len(edit.split()) - len(gold.split())))
        if editor.guard_verdict(r["original"], edit, r["max_compression"])["accepted"]:
            passed += 1
    n = max(len(records), 1)
    return {"cos_to_opus": sum(cos) / n, "dwords_to_opus": sum(dwords) / n,
            "guard_pass": passed / n}


def _report(base_m: dict, tuned_m: dict) -> dict:
    ui.step("results (held-out test, Opus is the gold target)")
    ui.info(f"{'metric':<16}{'base(prompt)':>14}{'tuned':>10}")
    for k, better_low in [("cos_to_opus", False), ("dwords_to_opus", True), ("guard_pass", False)]:
        win = (tuned_m[k] < base_m[k]) if better_low else (tuned_m[k] > base_m[k])
        flag = " ✓" if win else ""
        ui.info(f"{k:<16}{base_m[k]:>14.3f}{tuned_m[k]:>10.3f}{flag}")
    verdict = ("tune beats base on closeness to Opus"
               if tuned_m["cos_to_opus"] > base_m["cos_to_opus"]
               and tuned_m["dwords_to_opus"] <= base_m["dwords_to_opus"]
               else "tune does NOT clearly beat the prompt: stay on the prompt (learning.md §3.1)")
    ui.ok(verdict)
    return {"base": base_m, "tuned": tuned_m}


def _edits_path():
    return config.data_dir() / "eval" / "local.jsonl"


def score_edits(rows: list[dict]) -> dict:
    """Score already-collected edits (base_edit/tuned_edit per row), used by
    `pull-eval` to grade the cloud job's output locally, scored identically to `run`."""
    editor.preload_embedding_model()
    base_m = _score(rows, [r["base_edit"] for r in rows])
    tuned_m = _score(rows, [r["tuned_edit"] for r in rows])
    return _report(base_m, tuned_m)


def score_saved() -> dict:
    """Re-grade the last local run's saved edits, no inference, no GPU. Lets a metric
    change (new scorer in `_score`) be re-run for free instead of re-POSTing every edit."""
    path = _edits_path()
    if not path.exists():
        raise SystemExit(f"no saved local edits at {path}, run `evaluate` once to produce them.")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ui.info(f"re-scoring {len(rows)} saved edits from {path} (no inference)")
    return score_edits(rows)


def run(adapter: str = "kopi") -> dict:
    _require_endpoint()
    reqs = build_requests(_load_test())
    ui.step(f"baseline eval on {len(reqs)} held-out paragraphs (served base vs '{adapter}')")
    ui.info(f"endpoint {config.qwen_base_url()}, first call absorbs the cold start")
    editor.preload_embedding_model()

    url, token = config.qwen_base_url(), config.qwen_token()
    out = _edits_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    # Persist after every paragraph (like the cloud job) so a stopped run keeps its work
    # and the edits stay re-scorable: inference is the only expensive thing, never repeat it.
    for i, r in enumerate(reqs, 1):
        ui.info(f"[{i}/{len(reqs)}] {r['doc'][:50]} ({r['mode']})")
        r["base_edit"] = transport.post_edit(r, url, token, None)   # adapter OFF == prompt-only base
        r["tuned_edit"] = transport.post_edit(r, url, token, adapter)  # adapter ON == the tune
        rows.append(r)
        out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n",
                       encoding="utf-8")
    ui.ok(f"saved {len(rows)} edits -> {out}, re-score for free with `evaluate --rescore`")

    return score_edits(rows)
