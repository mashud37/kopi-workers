"""Score one word against the fitted keep-or-delete weights, and write those
weights out as the generated module the engine reads them from.
"""
import math
from pathlib import Path

FILE = Path(__file__).resolve().parent / "weights.py"

# Beyond this the sigmoid is 0 or 1 to more places than a float carries, and
# `math.exp` overflows somewhere past it.
_LIMIT = 30.0

# Weights are rounded before they are written, so regenerating the module on the
# same corpus produces the same bytes and a real change shows up as a diff.
_PLACES = 6

_PREAMBLE = [
    '"""Fitted keep-or-delete weights induced from the train split of the gold corpus.',
    "Regenerate with ``python manage.py tag``; never edit this file by hand.",
    '"""',
    "",
    "# Each entry is one column of the fitted model: a plain feature name for a number,",
    "# and `feature=value` for a one-hot. A word's score is the intercept plus the",
    "# weight of every column it matches, passed through a sigmoid.",
    "",
]


def _sigmoid(total: float) -> float:
    if total <= -_LIMIT:
        return 0.0
    if total >= _LIMIT:
        return 1.0
    return 1.0 / (1.0 + math.exp(-total))


def score(row: dict, fitted: dict) -> float:
    """How likely the fitted model thinks this word is to be deleted.

    Args:
        row: one word's features, from :func:`tagging.features.of`.
        fitted: ``{"intercept": float, "weights": {column: float}}``.

    Returns:
        A probability in [0, 1]. A string feature matches the one-hot column
        ``name=value`` and contributes its weight once; a number multiplies the
        weight of the column named after it, which is what the vectoriser did
        when the model was fitted.
    """
    total = fitted["intercept"]
    for name, value in row.items():
        if isinstance(value, str):
            total += fitted["weights"].get(f"{name}={value}", 0.0)
        else:
            total += fitted["weights"].get(name, 0.0) * value
    return _sigmoid(total)


def write(intercept: float, weights: dict) -> dict:
    """Write the fitted weights to :data:`FILE` as a generated module.

    Column names are escaped to plain ASCII rather than written as themselves,
    because a lemma column carries whatever character the corpus used and the
    corpus contains em-dashes and curly quotes. Writing them literally puts an
    em-dash in a source file, which the workspace forbids, and makes the file
    depend on the reader's encoding for no gain.

    Returns:
        ``{"path": Path, "columns": int}``.
    """
    lines = list(_PREAMBLE)
    lines.append(f"INTERCEPT = {round(intercept, _PLACES)}")
    lines.append("")
    lines.append("WEIGHT = {")
    for column in sorted(weights):
        lines.append(f"    {ascii(column)}: {round(weights[column], _PLACES)},")
    lines.append("}")
    FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": FILE, "columns": len(weights)}
