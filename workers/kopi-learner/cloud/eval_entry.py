"""Run inside the CPU eval job container: posts each held-out paragraph to
the served Qwen, base and with the `kopi` LoRA, writing raw edits to GCS
for later scoring.
"""
import json
import os
from pathlib import Path

from cli import ui
from eval import transport


def main() -> None:
    eval_dir = os.environ.get("KOPI_EVAL_DIR")
    if not eval_dir:
        raise SystemExit("KOPI_EVAL_DIR unset, launch via `python manage.py evaluate-cloud`.")
    url, token = os.environ.get("KOPI_QWEN_URL"), os.environ.get("KOPI_QWEN_TOKEN")
    if not url or not token:
        raise SystemExit("KOPI_QWEN_URL / KOPI_QWEN_TOKEN unset: the served vLLM endpoint + token.")
    adapter = os.environ.get("KOPI_ADAPTER", "kopi")

    base = Path(eval_dir) / "eval"
    reqs = [json.loads(line) for line in (base / "requests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    out = base / "edits.jsonl"
    ui.step(f"served A/B over {len(reqs)} held-out paragraphs (base vs '{adapter}')")
    ui.info(f"endpoint {url}, first call absorbs the cold start")

    rows = []
    for i, r in enumerate(reqs, 1):
        ui.info(f"[{i}/{len(reqs)}] {r['doc'][:50]} ({r['mode']})")
        r["base_edit"] = transport.post_edit(r, url, token, None)
        r["tuned_edit"] = transport.post_edit(r, url, token, adapter)
        rows.append(r)
        out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n",
                       encoding="utf-8")
    ui.ok(f"wrote {len(rows)} edits -> {out}, score them with `python manage.py pull-eval`")


if __name__ == "__main__":
    main()
