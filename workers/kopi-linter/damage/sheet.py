"""Lay out every edit the linter makes on the held-out documents so a person
can judge it, which is the hand check `good.md` section 5.5 asks for.
"""
from eval.harness import triage
from evidence.load import load_samples
from lint import bands
from lint.run import lint_paragraph

SIZE = 100


def candidates() -> list:
    """The held-out gold paragraphs, in corpus order."""
    return load_samples(roles={"opus"}, split="test")


def _foils() -> dict:
    foils = {}
    for other in load_samples(roles={"qwen"}, split="test"):
        foils[(other.key, other.band)] = other
    return foils


def _rows_for(sample, result, foil: str | None, nlp) -> list:
    rows = []
    for edit in result.applied:
        rows.append({
            "id": f"{sample.key}|{sample.band}|{edit.start}:{edit.end}",
            "rule": edit.rule,
            "family": edit.family,
            "confidence": round(edit.confidence, 3),
            "source": edit.source(sample.original),
            "replacement": edit.replacement,
            "note": edit.note,
            "triage": triage(edit, sample.original, sample.edit, foil, nlp),
        })
    return rows


def build(samples: list, nlp, size: int = SIZE, on_progress=None) -> list:
    """Every changed paragraph, in corpus order, with its edits.

    Args:
        samples: the gold paragraphs to lint, from :func:`candidates`.
        nlp: a loaded spaCy pipeline.
        size: how many changed paragraphs to keep.
        on_progress: called with (index, total, sample).

    Returns:
        One dict per changed paragraph, holding the original, the linted text,
        Opus's edit and one row per applied edit. An edit is identified by its
        paragraph, its band and its character span, so a verdict stays attached
        to what it judged when the paragraph's other edits change.
    """
    foils = _foils()
    sheet = []
    for index, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(index, len(samples), sample)
        if len(sheet) >= size:
            break
        band = bands.band(sample.band) if sample.band in bands.BANDS else bands.band("firm")
        result = lint_paragraph(sample.original, nlp, band)
        if not result.changed:
            continue
        other = foils.get((sample.key, sample.band))
        sheet.append({
            "key": sample.key,
            "doc": sample.doc,
            "band": sample.band,
            "original": sample.original,
            "linted": result.edited,
            "gold": sample.edit,
            "edits": _rows_for(sample, result, other.edit if other else None, nlp),
        })
    return sheet
