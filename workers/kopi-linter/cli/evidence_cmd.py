"""`evidence` command: mine the gold edit corpus into a transformation report."""
import time

from . import ui
from .progress import BatchProgress, StepSpinner

_ROLES = [
    ("opus", "Opus edits only (the gold standard the linter chases)"),
    ("qwen", "Served Qwen edits only (what the cheap model does)"),
    ("all", "Every editor in the corpus"),
]


def _pick_role() -> str | None:
    choice = ui.menu("Editor", _ROLES)
    return _ROLES[choice][0] if choice is not None else None


def _load_corpus(role: str):
    from evidence import editor_rules
    from evidence.load import corpus_stats, load_samples

    sp = StepSpinner("loading corpus")
    sp.start()
    try:
        samples = load_samples(roles=None if role == "all" else {role})
        stats = corpus_stats(samples)
    finally:
        sp.done()
    if not samples:
        raise SystemExit(f"no {role} edits found in the kopi-learner corpus")
    ui.ok(f"{stats['samples']} edits, {stats['paragraphs']} paragraphs, "
          f"{stats['documents']} documents")
    ui.info("bands: " + ", ".join(f"{k} {v}" for k, v in sorted(stats["by_band"].items())))
    if editor_rules.available():
        ui.info(f"kopi-editor tables loaded: {sum(editor_rules.table_size().values())} "
                "existing rules")
    else:
        ui.warn("kopi-editor not found, coverage will read as zero")
    return samples


def _load_parser():
    sp = StepSpinner("loading spaCy parser")
    sp.start()
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing, run: python -m spacy download en_core_web_sm")
    finally:
        sp.done()


def _classify(samples, nlp):
    from evidence import taxonomy
    from evidence.align import align

    started = time.perf_counter()
    bar = BatchProgress(len(samples), "aligning + classifying")
    tally = taxonomy.tally(samples, nlp, align, on_progress=lambda i, n, s: bar.advance())
    bar.finish()
    return tally, time.perf_counter() - started


def run(role: str | None = None, limit: int | None = None) -> None:
    ui.step("Evidence")
    ui.info("plan: load corpus, load parser, align sentences, classify spans, write report")

    role = role or _pick_role()
    if role is None:
        return

    samples = _load_corpus(role)
    nlp = _load_parser()
    work = samples[:limit] if limit else samples
    tally, elapsed = _classify(work, nlp)

    from evidence import report
    sp = StepSpinner("writing report")
    # A truncated pass is a spot check, so it gets its own filename: it must never
    # overwrite the full report the documents cite.
    stem = f"evidence_{role}_first{limit}" if limit else f"evidence_{role}"
    sp.start()
    try:
        path = report.write(tally, work, role, elapsed, stem=stem)
    finally:
        sp.done()

    spans = sum(tally.families.values())
    covered = sum(tally.covered.values())
    ui.ok(f"{spans} transformations classified from {len(work)} edits in {elapsed:.0f}s")
    ui.ok(f"existing rule tables cover {covered} of them "
          f"({100.0 * covered / spans if spans else 0:.1f}%)")
    print(path)
