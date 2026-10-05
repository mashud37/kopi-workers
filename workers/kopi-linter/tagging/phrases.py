"""Induce what to write in place of a deleted span, as a closed table keyed on
the span's own text, and write it out as the module the engine reads.
"""
from collections import Counter, defaultdict
from pathlib import Path

from tagging import vocabulary

FILE = Path(__file__).resolve().parent / "replacements.py"

# How often a span must have been rewritten the same way before the table will
# repeat it, and how much of that span's gold behaviour that one phrase has to
# account for. Both are read off the operating table in `constraints.md` C21:
# at these two numbers the table writes on 317 held-out spans and writes exactly
# what Opus wrote on 80.8% of them.
MINIMUM_SUPPORT = 2
MINIMUM_PURITY = 0.6

_PREAMBLE = [
    '"""Phrases the gold editor wrote in place of a deleted span, induced from the',
    "train split. Regenerate with ``python manage.py tag``; never edit this file by hand.",
    '"""',
    "",
    "# Each entry maps the lower-cased text of a span the linter wants to delete to",
    "# what the gold editor wrote there instead. Deleting outright is the absent case.",
    "",
]


def _spans_of(sample, nlp) -> list:
    """Every span the gold deleted, with the phrase written in its place.

    A run of ``DELETE`` tags is one span, and the phrase sits on its first word,
    which is the tagging scheme's way of saying "replace these words with this".
    """
    out = []
    run, phrase = [], ""
    for tag in vocabulary.tags_for(sample, nlp):
        if tag["base"] == "DELETE":
            if tag["phrase"] and run:
                out.append({"text": " ".join(run), "phrase": phrase})
                run = []
            if tag["phrase"]:
                phrase = tag["phrase"]
            run.append(tag["word"])
        else:
            if run:
                out.append({"text": " ".join(run), "phrase": phrase})
            run, phrase = [], ""
    if run:
        out.append({"text": " ".join(run), "phrase": phrase})
    return out


def counts(samples, nlp, on_progress=None) -> dict:
    """What the gold did to each deleted span, as ``{text: Counter(phrase)}``."""
    table = defaultdict(Counter)
    total = len(samples)
    for index, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(index, total, sample)
        try:
            spans = _spans_of(sample, nlp)
        except Exception:
            continue
        for span in spans:
            table[span["text"].lower()][span["phrase"]] += 1
    return table


def table_from(seen: dict, support: int = MINIMUM_SUPPORT,
               purity: float = MINIMUM_PURITY) -> dict:
    """The spans one phrase is common and dominant enough to write for."""
    written = {}
    for text, phrases in seen.items():
        phrase, times = phrases.most_common(1)[0]
        if not phrase or times < support:
            continue
        if times / sum(phrases.values()) < purity:
            continue
        written[text] = phrase
    return written


def agreement(written: dict, held_out: dict) -> dict:
    """How often the table writes what the gold wrote, on held-out spans.

    Args:
        written: the table, from :func:`table_from`.
        held_out: held-out spans, from :func:`counts`.

    Returns:
        ``{"fired", "exact", "share"}`` over the held-out spans the table has an
        entry for, which is the only population it can be wrong about.
    """
    fired = exact = 0
    for text, phrases in held_out.items():
        phrase = written.get(text)
        if phrase is None:
            continue
        for gold, times in phrases.items():
            fired += times
            exact += times * int(gold.lower() == phrase.lower())
    return {"fired": fired, "exact": exact, "share": exact / fired if fired else 0.0}


def write(written: dict) -> dict:
    """Write the table to :data:`FILE` as a generated module."""
    lines = list(_PREAMBLE)
    lines.append("PHRASE = {")
    for text in sorted(written):
        lines.append(f"    {ascii(text)}: {ascii(written[text])},")
    lines.append("}")
    FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": FILE, "entries": len(written)}
