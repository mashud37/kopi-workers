"""`allocate` command: compare ways of splitting a document's reduction across
its paragraphs against what the gold editor removed from each.
"""
from pathlib import Path

from . import ui
from .progress import BatchProgress, StepSpinner

OUTPUT = Path("output")


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


def _write(rows: list, split: str) -> Path:
    from document import allocate

    OUTPUT.mkdir(exist_ok=True)
    path = OUTPUT / "allocation.md"
    lines = [
        "# Which paragraphs absorb a document's reduction",
        "",
        f"Every method is handed the same document, at one band, and the same total number of "
        f"words to remove, which is what Opus actually removed from it. It only chooses how to "
        f"split that number across the paragraphs, so the size of the cut is held fixed and the "
        f"allocation alone is judged. Measured on the {split} documents, "
        f"{rows[0]['units']} document-and-band units and {rows[0]['words']} removed words.",
        "",
        "`captured` is the share of Opus's cut a paragraph's budget can pay for, counting the "
        "smaller of budget and cut, so nothing is earned by handing a paragraph more than was "
        "taken from it. `wasted` is the share of the whole budget landing on paragraphs Opus "
        "left untouched. `error` is total misallocation over the size of the cut.",
        "",
        f"`{allocate.BASELINE}` is what the engine does today, one band target applied to every "
        "paragraph. `gold allocation` is the anchor: the same split Opus made, which is what a "
        "perfect allocator would produce.",
        "",
        "| Method | Captured | Wasted | Error |",
        "|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['method']} | {row['captured']:.1%} | {row['wasted']:.1%} | "
            f"{row['error']:.2f} |"
        )
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run(split: str = "test") -> None:
    from document import allocate
    from evidence.load import load_samples

    ui.step("Allocate")
    ui.info("plan: group the held-out paragraphs by document and band, score every paragraph "
            "with the fitted model, compare each allocation against Opus's own")
    nlp = _parser()

    prepared = allocate.units(load_samples(roles={"opus"}, split=split))
    if not prepared:
        raise SystemExit("no documents with a gold reduction in this split")
    bar = BatchProgress(len(prepared), "scoring documents")
    for index, unit in enumerate(prepared, 1):
        bar.on_item(index, len(prepared), unit["doc"])
        unit.update(allocate.deletable(unit, nlp))
    bar.finish()

    rows = allocate.compare(prepared)
    for row in rows:
        ui.info(f"{row['method']}: {row['captured']:.1%} captured, {row['wasted']:.1%} wasted")
    ui.ok(f"report written to {_write(rows, split)}")
