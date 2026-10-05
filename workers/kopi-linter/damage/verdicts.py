"""Read the hand verdicts on the damage set and turn them into a damage rate
by criterion, by band, by triage class and by deleted word.
"""
import json
from collections import Counter
from pathlib import Path

PATH = Path(__file__).resolve().parent / "verdicts.jsonl"
CRITERIA = ("G1", "G2", "G3")


def load() -> dict:
    """Every verdict on disk, keyed by the edit id the sheet gives it."""
    if not PATH.exists():
        return {}
    judged = {}
    for line in PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        judged[row["id"]] = row
    return judged


def _grouped(seen: list, field: str) -> dict:
    """Edits and damaged edits per value of ``field``."""
    rows = {}
    for item in seen:
        row = rows.setdefault(item[field], {"edits": 0, "damaged": 0})
        row["edits"] += 1
        row["damaged"] += int(item["damaged"])
    return rows


def summarise(sheet: list, judged: dict) -> dict:
    """Damage rates over the paragraphs in ``sheet``, using the verdicts in ``judged``.

    Args:
        sheet: what :func:`damage.sheet.build` returned.
        judged: what :func:`load` returned.

    Returns:
        Counts for the whole set, plus a row per band, per triage class and per
        deleted word, and the ids in the sheet nobody has judged yet. Paragraph
        damage is what `good.md` section 5.5 asks for: a paragraph is damaged
        when any edit in it is.
    """
    seen = []
    paragraphs = {"changed": 0, "damaged": 0}
    broken = Counter()
    unjudged = []
    for row in sheet:
        paragraphs["changed"] += 1
        hurt = False
        for edit in row["edits"]:
            verdict = judged.get(edit["id"])
            if verdict is None:
                unjudged.append(edit["id"])
                continue
            damaged = verdict["verdict"] == "damaged"
            hurt = hurt or damaged
            broken.update(verdict["broken"])
            seen.append({
                "band": row["band"],
                "triage": edit["triage"],
                "word": edit["source"].strip().lower(),
                "damaged": damaged,
            })
        paragraphs["damaged"] += int(hurt)
    return {
        "totals": {
            "edits": len(seen),
            "damaged": sum(1 for item in seen if item["damaged"]),
        },
        "paragraphs": paragraphs,
        "broken": broken,
        "by_band": _grouped(seen, "band"),
        "by_triage": _grouped(seen, "triage"),
        "by_word": _grouped(seen, "word"),
        "unjudged": unjudged,
    }


def worst_words(summary: dict, minimum: int = 2) -> list:
    """Deleted words that damage more than once, worst first."""
    rows = []
    for word, row in summary["by_word"].items():
        if row["damaged"] >= minimum:
            rows.append({"word": word, **row})
    rows.sort(key=lambda row: (-row["damaged"], row["word"]))
    return rows
