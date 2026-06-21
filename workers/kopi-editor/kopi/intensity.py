"""Editing intensity derived from the requested word reduction.

The requested reduction sets HOW HARD to edit, not just a figure for the report.
A ratio ``r = reduction / original_words`` selects a band, and the band fixes two
things that used to be hard-coded constants disconnected from the request:

* the acceptance guard's per-paragraph compression ceiling (``max_compression``);
* the prompt stance — whether the model may drop a sentence (``allow_drop``) and
  how firmly it is told to cut (the ``mode`` name, which selects the system block).

With no reduction requested the band is ``clarity``: plain-language edits only,
every sentence preserved, length barely moved. That is what stops an over-eager
model from gutting a manuscript nobody asked to shorten. A large request lands in
``aggressive``: the guard opens up and the prompt authorises real structural
concision. The ratio framing makes "500 words" mean *more* on a short manuscript
than on a long one — exactly how a copy editor reads it.

Thresholds are deliberately simple constants; tune them here, not per call.
"""

# Band table for a requested reduction, ordered by increasing aggressiveness.
# (name, r_upper, max_compression, allow_drop) where r_upper is the inclusive
# upper bound of the band. ``clarity`` is the special r == 0 (no request) case.
_BANDS = [
    ("light", 0.05, 0.18, False),
    ("firm", 0.12, 0.35, False),
    ("aggressive", 1.00, 0.55, True),
]

# No reduction requested: a clarity pass, not a reduction. The 6% ceiling lets a
# genuine plain-language tightening through while rejecting (and re-prompting) the
# half-paragraph cuts a small model makes when left unchecked.
_CLARITY = {"mode": "clarity", "max_compression": 0.06, "allow_drop": False, "frac": 0.0}


def plan(reduction: int, original_words: int) -> dict:
    """The document editing plan for a requested reduction.

    Args:
        reduction: words the user asked to remove (0 / None = clarity pass).
        original_words: length of the document being edited.

    Returns:
        ``{mode, max_compression, allow_drop, frac}`` — ``frac`` is the per-paragraph
        target fraction to shed (0 in clarity mode); ``max_compression`` is the guard
        ceiling for every paragraph this run.
    """
    if not reduction or original_words <= 0:
        return dict(_CLARITY)
    r = reduction / original_words
    name, _, max_comp, allow = _BANDS[-1]
    for cand_name, r_upper, cand_comp, cand_allow in _BANDS:
        if r <= r_upper:
            name, max_comp, allow = cand_name, cand_comp, cand_allow
            break
    return {
        "mode": name,
        "max_compression": max_comp,
        "allow_drop": allow,
        "frac": min(r, max_comp),
    }


def paragraph_floor(words: int, frac: float) -> int:
    """Soft per-paragraph word floor told to the model (keep about this many)."""
    return round(words * (1 - frac))


def describe(plan_: dict, reduction: int) -> str:
    """One-line summary of the chosen intensity for the run log / UI."""
    if plan_["mode"] == "clarity":
        return "clarity (no reduction requested — plain-language edits only)"
    pct = int(round(plan_["max_compression"] * 100))
    drop = "may drop redundant sentences" if plan_["allow_drop"] else "keeps every sentence"
    return f"{plan_['mode']} (target -{reduction}, up to {pct}%/paragraph, {drop})"
