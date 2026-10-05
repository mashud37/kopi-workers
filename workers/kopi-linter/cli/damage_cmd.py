"""`damage` command: build the hand-judging sheet over the held-out documents
and report the damage rate the recorded verdicts imply.
"""
from damage import sheet as sheet_mod

from . import ui
from .progress import BatchProgress, StepSpinner

SIZE = sheet_mod.SIZE


def _parser():
    sp = StepSpinner("loading spaCy parser")
    sp.start()
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except OSError:
        raise SystemExit("spaCy model missing, run: python -m spacy download en_core_web_sm")
    finally:
        sp.done()


def run(size: int = SIZE) -> None:
    from damage import report, sheet, verdicts

    ui.step("Damage")
    ui.info("plan: load parser, lint the held-out documents, write the judging sheet, "
            "read the verdicts, report the rate")
    nlp = _parser()

    samples = sheet.candidates()
    bar = BatchProgress(len(samples), "linting held-out paragraphs")
    built = sheet.build(samples, nlp, size=size, on_progress=bar.on_item)
    bar.finish()
    edits = sum(len(row["edits"]) for row in built)
    ui.ok(f"{len(built)} changed paragraphs, {edits} edits to judge")

    judged = verdicts.load()
    print(report.write_sheet(built, judged))
    if not judged:
        ui.warn(f"no verdicts yet, judge the sheet and write {verdicts.PATH.name}")
        return

    summary = verdicts.summarise(built, judged)
    paragraphs, totals = summary["paragraphs"], summary["totals"]
    ui.ok(f"{paragraphs['damaged']} of {paragraphs['changed']} paragraphs damaged, "
          f"{totals['damaged']} of {totals['edits']} edits")
    for name in verdicts.CRITERIA:
        ui.info(f"{name}: {summary['broken'][name]} edits")
    if summary["unjudged"]:
        ui.warn(f"{len(summary['unjudged'])} edits have no verdict")
    print(report.write_summary(summary))
