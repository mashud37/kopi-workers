"""`analyze` — diagnostic report. Runs the deterministic diagnosis, prints a
readability + wordiness + redundancy summary, and writes a full report to
output/<name>_analysis.md."""
from cli import config, ui, common


def run(file):
    from kopi.pipeline import load_nlp
    from kopi import diagnose, report
    from kopi.progress import StepSpinner

    path = common.resolve_docx(file)
    ui.step(f"Analysing {path.name}")

    sp = StepSpinner("loading document")
    sp.start()
    try:
        path, text, words = common.load_text(file)
    finally:
        sp.done()
    ui.info(f"{words} words")

    sp = StepSpinner("loading spaCy model")
    sp.start()
    try:
        nlp = load_nlp()
    finally:
        sp.done()
    if nlp is None:
        raise SystemExit("spaCy model missing — run `python manage.py update` (downloads en_core_web_sm).")

    sp = StepSpinner("analysing document")
    sp.start()
    try:
        diag = diagnose.diagnose(text, nlp)
    finally:
        sp.done()

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
