"""Cloud Run entrypoint: receives flagged paragraphs via GCS, applies LLM tightening, writes results."""
import json
import re
import sys


def _parse_gs(gs_path: str) -> tuple[str, str]:
    m = re.match(r"gs://([^/]+)/(.+)", gs_path)
    if not m:
        raise ValueError(f"Invalid GCS path: {gs_path}")
    return m.group(1), m.group(2)


def main():
    if len(sys.argv) < 3:
        print("Usage: cloud_llm.py <input_gs_path> <output_gs_path>", file=sys.stderr)
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    try:
        from google.cloud import storage
    except ImportError:
        print("Error: google-cloud-storage not installed.", file=sys.stderr)
        sys.exit(1)

    client = storage.Client()

    in_bucket, in_blob = _parse_gs(input_path)
    payload = json.loads(client.bucket(in_bucket).blob(in_blob).download_as_text())
    paragraphs = payload["paragraphs"]
    gap = int(payload.get("gap", 0))
    print(f"Received {len(paragraphs)} paragraph(s) to process (gap: {gap} words).")

    try:
        import ollama
        ollama.list()
    except Exception as e:
        print(f"Error: Ollama not available: {e}", file=sys.stderr)
        sys.exit(1)

    from kopi.llm import edit_paragraph
    from kopi.step_concision import _accept_edit

    results = []
    words_saved = 0
    for item in paragraphs:
        if gap > 0 and words_saved >= gap:
            print(f"  Gap closed ({words_saved} words saved) — stopping early.")
            break
        print(f"  P{item['index'] + 1} ({len(item['text'].split())} words)...", end=" ", flush=True)
        try:
            edited = edit_paragraph(
                item["text"],
                budget=item.get("budget"),
                focus=item.get("focus"),
                fat_index=item.get("fat_index"),
            )
            ok, reason = _accept_edit(item["text"], edited)
            saved = len(item["text"].split()) - len(edited.split()) if ok else 0
            if ok:
                words_saved += saved
            print("accepted" if ok else f"rejected ({reason})")
            results.append({
                "index": item["index"],
                "accepted": ok,
                "edited": edited if ok else item["text"],
                "reason": reason,
                "saved": saved,
                "fat_index": item.get("fat_index"),
                "routing_reason": item.get("routing_reason"),
            })
        except Exception as e:
            print(f"error: {e}")
            results.append({
                "index": item["index"],
                "accepted": False,
                "edited": item["text"],
                "reason": str(e),
                "saved": 0,
                "fat_index": item.get("fat_index"),
                "routing_reason": item.get("routing_reason"),
            })

    out_bucket, out_blob = _parse_gs(output_path)
    client.bucket(out_bucket).blob(out_blob).upload_from_string(
        json.dumps({"results": results}),
        content_type="application/json",
    )
    accepted = sum(1 for r in results if r["accepted"])
    print(f"\nDone. {accepted}/{len(results)} paragraph(s) accepted. Results at gs://{out_bucket}/{out_blob}")


if __name__ == "__main__":
    main()
