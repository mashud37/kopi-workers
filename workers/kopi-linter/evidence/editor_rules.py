"""Bridge to kopi-editor's existing deterministic rule tables.

Read-only, and used for one purpose: measuring how much of the gold edit corpus
the rules already in production can account for. Everything a table already
covers is a solved case; the point of this repo is the remainder.

kopi-editor is a sibling repo, not an installed package, so its ``kopi`` package
is put on the path here rather than imported normally.
"""
import sys
from functools import lru_cache
from pathlib import Path

EDITOR = Path(__file__).resolve().parents[2] / "kopi-editor"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not EDITOR.exists():
        return {"phrases": {}, "cliches": {}, "words": {}, "tails": []}
    if str(EDITOR) not in sys.path:
        sys.path.insert(0, str(EDITOR))
    from kopi.data_fillers import PHRASE_REPLACEMENTS
    from kopi.data_padding_tails import TAIL_PATTERNS
    from kopi.data_plain import CLICHE_REPLACEMENTS, WORD_SUBSTITUTIONS
    return {
        "phrases": PHRASE_REPLACEMENTS,
        "cliches": CLICHE_REPLACEMENTS,
        "words": WORD_SUBSTITUTIONS,
        "tails": TAIL_PATTERNS,
    }


def available() -> bool:
    return bool(_load()["phrases"])


def table_size() -> dict:
    tables = _load()
    return {name: len(value) for name, value in tables.items()}


def covered_by_table(source: str, target: str) -> str | None:
    """Which existing table, if any, already licenses this substitution.

    Args:
        source: the original span text.
        target: what the editor replaced it with (empty string for a deletion).

    Returns:
        ``"phrases"``, ``"cliches"``, ``"words"``, ``"tails"``, or None when no
        production table would have made this edit.
    """
    tables = _load()
    src = " ".join(source.lower().split()).strip(" ,.;:")
    tgt = " ".join(target.lower().split()).strip(" ,.;:")
    if not src:
        return None
    for name in ("phrases", "cliches", "words"):
        table = tables[name]
        if src in table and (table[src] or "").lower() == tgt:
            return name
    for pattern, _ in tables["tails"]:
        if pattern.fullmatch(src) and not tgt:
            return "tails"
    return None
