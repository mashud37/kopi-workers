"""`analyze` — diagnostic report. Runs the deterministic diagnosis, prints a
readability + wordiness + redundancy summary, and writes a full report to
output/<name>_analysis.md."""
from cli import config, ui, common


def run(file):
    path, text, words = common.load_text(file)
    ui.step(f"Analysing {path.name}")
    ui.info(f"{words} words")

    from kopi.pipeline import load_nlp
    from kopi import diagnose, report

    nlp = load_nlp()
    if nlp is None:
        raise SystemExit("spaCy model missing — run `python manage.py update` (downloads en_core_web_sm).")

    print("  [prep] analysing document (local)...", flush=True)
    diag = diagnose.diagnose(text, nlp)

    un = diag["unnecessary"]
    red = diag["redundancy"]
    total = un["savings"] + red["savings"]

    # Readability gauge (● = this document, │ = a good target).
    ui.step("Readability")
    f = diag["readability"]
    if f is not None:
        ui.info(f"harder {report.scale_bar(f, 0, 100, target=60)} easier   "
                f"{f:.0f}/100 · {report.flesch_band(f)}")

    # Wordiness + redundancy as the two reduction levers.
    ui.step("What to edit")
    ui.info(f"wordiness:  {un['hits']} filler phrase(s), ~{un['savings']} words")
    ui.info(f"redundancy: {red['count']} restated sentence(s), ~{red['savings']} words")
    ui.ok(f"~{total} words removable ({(total / words * 100) if words else 0:.0f}% of the document)")

    # Top key terms, so the author can sanity-check their concepts surface.
    terms = report.key_terms(text.split("\n\n"), top=8)
    if terms:
        ui.step("Key terms")
        ui.info(", ".join(t for t, _ in terms))

    report_path = report.write_analysis(diag, text, path.name, config.OUTPUT_DIR)
    ui.ok(f"full report: {report_path}")
