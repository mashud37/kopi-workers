import argparse
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_INPUT_DIR = _PROJECT_ROOT / "input"
_OUTPUT_DIR = _PROJECT_ROOT / "output"
_CLOUD_CONFIG_PATH = Path.home() / ".config" / "kopi-editor" / "cloud.json"


def _load_cloud_config() -> dict:
    if _CLOUD_CONFIG_PATH.exists():
        try:
            return json.loads(_CLOUD_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _check_requirements(rules_only: bool) -> None:
    missing = []
    for pkg, import_name in [
        ("python-docx", "docx"),
        ("spacy", "spacy"),
        ("sentence-transformers", "sentence_transformers"),
        ("numpy", "numpy"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"Error: missing package(s): {', '.join(missing)}", file=sys.stderr)
        print("Run: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    try:
        import spacy
        spacy.load("en_core_web_sm")
    except OSError:
        print(
            "Warning: spaCy model not found — syntax and redundancy steps will be skipped.\n"
            "To enable: python -m spacy download en_core_web_sm",
            file=sys.stderr,
        )

    if not rules_only:
        try:
            import language_tool_python  # noqa: F401
        except ImportError:
            print(
                "Warning: language-tool-python not installed — proofing step will be skipped.\n"
                "Install with: pip install language-tool-python",
                file=sys.stderr,
            )


def _interactive_review(state: dict) -> None:
    """Ask the user about repeated proofing suggestions in the terminal, one at a time."""
    review_items = state.get("review_items", [])
    if not review_items or not sys.stdin.isatty():
        return

    from kopi.quote_guard import guard, unguard

    print(f"\nProofing review — {len(review_items)} repeated suggestion(s):")
    print("  (decide once, applied globally)\n")

    restored = unguard(state["text"], state["qmap"])
    changed = False

    for n, item in enumerate(review_items, 1):
        if not item["replacements"]:
            continue
        repl = item["replacements"][0]
        paras = ", ".join(item["paras"])
        print(f"  [{n}/{len(review_items)}] '{item['original']}' -> '{repl}'")
        print(f"         {item['count']}x at {paras}")
        print(f"         {item['message']}")
        try:
            ans = input("         Apply everywhere? [y/N/q(uit review)] ").strip().lower()
        except EOFError:
            break
        if ans == "q":
            print("         Skipping remaining suggestions.")
            break
        if ans == "y":
            restored = re.sub(
                r"\b" + re.escape(item["original"]) + r"\b",
                repl,
                restored,
                flags=re.IGNORECASE,
            )
            changed = True
            state["log"].append({
                "step": "Step 10 — Proofing",
                "detail": f"[user] '{item['original']}' -> '{repl}' applied globally ({item['count']}x)",
                "para": None,
            })
        print()

    if changed:
        from kopi.quote_guard import guard
        state["text"], state["qmap"] = guard(restored)
        state["final_text"] = restored


def _llm_route(args) -> str | None:
    """Resolve the LLM backend without prompting. Returns 'local', 'cloud', or None.

    'auto' (the default) uses cloud when it's configured (KOPI_BUCKET or a bucket
    in cloud.json), otherwise local Ollama. Local degrades gracefully to
    deterministic-only if Ollama isn't running (handled in step_concision).
    """
    if args.no_llm or args.rules_only or args.llm == "skip":
        return None
    if args.llm in ("local", "cloud"):
        return args.llm
    # auto
    cfg = _load_cloud_config()
    if os.environ.get("KOPI_BUCKET") or cfg.get("bucket"):
        return "cloud"
    return "local"


def _refresh_final_check(state: dict) -> dict:
    """Re-run the final check after an LLM pass so counts/flags reflect the result."""
    from kopi import step_check
    from kopi.quote_guard import unguard
    state["log"] = [e for e in state["log"] if "Step 12" not in e.get("step", "")]
    state = step_check.run(state)
    state["final_text"] = unguard(state["text"], state["qmap"])
    return state


def _run_llm(state: dict, second_pass: bool = True) -> dict:
    import kopi.llm as llm_mod
    from kopi import step_concision

    print(f"\nRunning LLM concision (local Ollama, model: {llm_mod.DEFAULT_MODEL})...")
    state = step_concision.run(state)

    if second_pass and step_concision.needs_second_pass(state):
        print("  Still short of target — running a second pass on additional paragraphs...")
        state["log"].append({
            "step": "Step 10 — Concision (second pass)",
            "detail": "first pass undershot target — flagging additional paragraphs",
            "para": None,
        })
        state = step_concision.run(state)

    return _refresh_final_check(state)


def _run_cloud_llm(state: dict, second_pass: bool = True) -> dict:
    try:
        from google.cloud import storage
    except ImportError:
        print("Error: google-cloud-storage not installed. Run: pip install google-cloud-storage", file=sys.stderr)
        return state

    import subprocess
    from kopi.step_concision import get_candidates, apply_results, needs_second_pass
    from kopi.quote_guard import word_count

    cloud_cfg = _load_cloud_config()
    bucket_name = os.environ.get("KOPI_BUCKET") or cloud_cfg.get("bucket")
    if not bucket_name:
        print(
            "Error: no cloud config found. Run 'python cloud/setup_cloud.py' to provision Cloud Run,\n"
            "  or set the KOPI_BUCKET environment variable manually.",
            file=sys.stderr,
        )
        return state

    region   = os.environ.get("KOPI_REGION")   or cloud_cfg.get("region",  "europe-west1")
    job_name = os.environ.get("KOPI_LLM_JOB")  or cloud_cfg.get("job",     "kopi-editor-llm")
    baked_model = cloud_cfg.get("model_id", "baked model")

    try:
        client = storage.Client()
    except Exception as e:
        if "DefaultCredentialsError" in type(e).__name__ or "credentials" in str(e).lower():
            print(
                "Error: Google Cloud credentials not found for the Python SDK.\n"
                "  The gcloud CLI and the Python SDK use separate credentials.\n"
                "  Fix: gcloud auth application-default login",
                file=sys.stderr,
            )
        else:
            print(f"Error: could not initialise Google Cloud client: {e}", file=sys.stderr)
        return state

    gcloud = shutil.which("gcloud") or "gcloud"

    def _round(state: dict) -> tuple[dict, bool]:
        """One Cloud Run job round-trip. Returns (state, ran)."""
        candidates = get_candidates(state)
        if not candidates:
            print("No paragraphs qualify for LLM tightening.")
            return state, False

        job_id = uuid.uuid4().hex[:8]
        input_blob = f"jobs/{job_id}/paragraphs.json"
        result_blob = f"jobs/{job_id}/results.json"
        input_gs = f"gs://{bucket_name}/{input_blob}"
        result_gs = f"gs://{bucket_name}/{result_blob}"

        current_words = word_count(state["text"], state["qmap"])
        gap = max(0, current_words - state.get("target", 0))

        client.bucket(bucket_name).blob(input_blob).upload_from_string(
            json.dumps({"paragraphs": candidates, "gap": gap}),
            content_type="application/json",
        )
        print(f"  Uploaded {len(candidates)} paragraph(s) -> {input_gs}")
        print(f"  Submitting Cloud Run job '{job_name}' (model: {baked_model}, region: {region})...")

        try:
            subprocess.run(
                [
                    gcloud, "run", "jobs", "execute", job_name,
                    "--region", region,
                    "--args", f"{input_gs},{result_gs}",
                    "--wait",
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Error: Cloud Run job failed: {e}", file=sys.stderr)
            return state, False
        except FileNotFoundError:
            print("Error: gcloud CLI not found. Install the Google Cloud SDK.", file=sys.stderr)
            return state, False

        results_data = client.bucket(bucket_name).blob(result_blob).download_as_text()
        results = json.loads(results_data)["results"]
        return apply_results(state, results), True

    state, ran = _round(state)
    if ran and second_pass and needs_second_pass(state):
        print("  Still short of target — submitting a second Cloud Run job on additional paragraphs...")
        state["log"].append({
            "step": "Step 10 — Concision (second pass)",
            "detail": "first pass undershot target — flagging additional paragraphs",
            "para": None,
        })
        state, _ = _round(state)
    return state


def _handle_cloud_pipeline(path_str: str, reduction: int, lang: str, no_llm: bool,
                           second_pass: bool = True) -> None:
    """Full pipeline run inside a Cloud Run container (reads/writes via GCS)."""
    try:
        from google.cloud import storage
    except ImportError:
        print("Error: google-cloud-storage not installed.", file=sys.stderr)
        sys.exit(1)

    import tempfile
    m = re.match(r"gs://([^/]+)/(.+)", path_str)
    if not m:
        print(f"Error: invalid GCS path: {path_str}", file=sys.stderr)
        sys.exit(1)
    bucket_name, blob_name = m.group(1), m.group(2)

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        bucket.blob(blob_name).download_to_filename(tmp.name)
        local_path = Path(tmp.name)

    from kopi.extract import extract_docx
    from kopi.pipeline import run_pipeline
    from kopi.output import write_outputs
    from kopi.quote_guard import unguard

    text = extract_docx(local_path)
    original_count = len(text.split())
    target = original_count - reduction
    print(f"Original: {original_count} | Reduction: -{reduction} | Target: {target}")

    state = run_pipeline(text, target, lang)

    if not no_llm:
        from kopi import step_concision, step_check
        state = step_concision.run(state)
        if second_pass and step_concision.needs_second_pass(state):
            print("  Still short of target — running a second pass on additional paragraphs...")
            state["log"].append({
                "step": "Step 10 — Concision (second pass)",
                "detail": "first pass undershot target — flagging additional paragraphs",
                "para": None,
            })
            state = step_concision.run(state)
        state["log"] = [e for e in state["log"] if "Step 12" not in e.get("step", "")]
        state = step_check.run(state)
        state["final_text"] = unguard(state["text"], state["qmap"])

    edited_path, changelog_path = write_outputs(state, local_path)

    stem = Path(blob_name).stem
    for local_file, suffix in [(edited_path, "_edited.md"), (changelog_path, "_changelog.md")]:
        out_blob = bucket.blob(f"{stem}{suffix}")
        out_blob.upload_from_filename(str(local_file))
        print(f"Uploaded: gs://{bucket_name}/{stem}{suffix}")


def _print_summary(state: dict, path: Path, original_count: int, out_dir: Path = None,
                   llm_ran: bool = True) -> None:
    final = state["counts"].get("final", "—")
    final_int = final if isinstance(final, int) else original_count
    removed = original_count - final_int
    pct = (removed / original_count * 100) if original_count else 0
    target = state.get("target", final_int)
    gap = final_int - target
    stem = path.stem
    out_dir = out_dir if out_dir is not None else path.parent

    print(f"\nDone.")
    print(f"  Removed          : {removed} words ({pct:.1f}%)")
    print(f"  Final word count : {final}  (target: {target})")

    if gap <= 0:
        print("  Target met.")
    elif llm_ran:
        print(f"  Still {gap} words over target after LLM tightening.")
    else:
        print(f"  {gap} words over target — run with --llm local or --llm cloud to tighten.")

    print(f"  Edited text      : {out_dir / (stem + '_edited.md')}")
    print(f"  Change log       : {out_dir / (stem + '_changelog.md')}")

    n_flags = len(state.get("flags", []))
    if n_flags:
        print(f"  {n_flags} advisory note(s) in the change log.")


def main():
    parser = argparse.ArgumentParser(
        description="kopi-editor: academic copyeditor for humanities and social sciences"
    )
    parser.add_argument("file", help="Input .docx file (or gs:// path with --cloud-job)")
    parser.add_argument("reduction", type=int, help="Number of words to remove (not target length)")
    parser.add_argument("--lang", default="british", choices=["british", "american"])
    parser.add_argument("--llm", choices=["auto", "local", "cloud", "skip"], default="auto",
                        help="LLM backend: 'auto' (default) = cloud if configured else local; or force local/cloud/skip")
    parser.add_argument("--no-llm", action="store_true", help="Skip the LLM step (same as --llm skip)")
    parser.add_argument("--review", action="store_true",
                        help="Interactively review repeated proofing suggestions (off by default)")
    parser.add_argument("--rules-only", action="store_true", help="Steps 1-8 only — no proofing or LLM")
    parser.add_argument("--evaluate", action="store_true", help="Run Mu & Lim 2022 benchmark")
    parser.add_argument("--cloud-job", action="store_true", help="Full pipeline via GCS (runs inside Cloud Run)")
    parser.add_argument("--no-second-pass", action="store_true",
                        help="Disable the automatic second LLM pass when the first undershoots target")
    args = parser.parse_args()

    if args.cloud_job or args.file.startswith("gs://"):
        _handle_cloud_pipeline(args.file, args.reduction, args.lang, args.no_llm,
                               second_pass=not args.no_second_pass)
        return

    _check_requirements(args.rules_only)

    from kopi.extract import extract_docx
    from kopi.pipeline import run_pipeline
    from kopi.output import write_outputs

    path = Path(args.file)
    if not path.exists() and not path.is_absolute():
        # Allow passing a bare filename that lives in the input/ folder.
        candidate = _INPUT_DIR / args.file
        if candidate.exists():
            path = candidate
    if not path.exists():
        print(f"Error: '{args.file}' not found (looked in '.' and '{_INPUT_DIR}').", file=sys.stderr)
        sys.exit(1)
    if path.suffix.lower() != ".docx":
        print("Error: input must be a .docx file.", file=sys.stderr)
        sys.exit(1)

    out_dir = _OUTPUT_DIR

    print(f"Reading {path.name}...")
    text = extract_docx(path)
    original_count = len(text.split())
    target = original_count - args.reduction

    if target <= 0:
        print(f"Error: reduction {args.reduction} exceeds document length ({original_count} words).", file=sys.stderr)
        sys.exit(1)

    phase = "rules-only" if args.rules_only else "deterministic"
    print(f"Original: {original_count} words | Reduction: -{args.reduction} | Target: {target}")
    print(f"Running phase 1 ({phase}):\n")

    state = run_pipeline(
        text, target, args.lang,
        rules_only=args.rules_only,
        evaluate=args.evaluate,
    )

    # Proofing suggestions are reviewed interactively only when asked for;
    # otherwise they are saved to <name>_review.md for the author to consult.
    if args.review:
        _interactive_review(state)

    # LLM tightening runs automatically (this is what closes the word gap).
    route = _llm_route(args)
    second_pass = not args.no_second_pass
    if route == "cloud":
        cloud_cfg = _load_cloud_config()
        print(f"\nRunning LLM concision (Cloud Run, baked model: {cloud_cfg.get('model_id', 'baked')})...")
        state = _run_cloud_llm(state, second_pass=second_pass)
        state = _refresh_final_check(state)
    elif route == "local":
        state = _run_llm(state, second_pass=second_pass)
    # route is None -> deterministic only

    write_outputs(state, path, out_dir)
    _print_summary(state, path, original_count, out_dir, llm_ran=route is not None)


if __name__ == "__main__":
    main()
