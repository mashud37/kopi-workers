"""Run the deterministic diagnosis and print a readability, wordiness, and redundancy
summary, writing the full report into a new folder for this run.
"""
from cli import common, ui


def run(file):
    from kopi import diagnose, report
    from kopi.pipeline import load_nlp
    from kopi.progress import StepSpinner

    path = common.resolve_docx(file)
    ui.step(f"Analysing {path.name}")

    sp = StepSpinner("loading document")
    sp.start()
    try:
        loaded = common.load_text(file)
        path, text, words = loaded["path"], loaded["text"], loaded["words"]
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
        raise SystemExit("spaCy's English model could not be downloaded: check the internet connection and run again.")

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

    report_path = report.write_analysis(diag, text, path.name, common.run_folder(path, "analyze"))
    ui.ok(f"full report: {report_path}")
