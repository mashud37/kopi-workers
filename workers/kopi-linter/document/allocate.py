"""Split a document's requested reduction across its paragraphs, and score the
split against the words the gold editor removed from each one.
"""
from lint import bands

# Where the fitted model is read as wanting a word gone, matching the floor the
# tagged rule proposes from.
FLOOR = 0.5

BASELINE = "length-proportional"


def units(samples: list) -> list:
    """The paragraphs grouped into one unit per document and band, in order.

    Args:
        samples: gold :class:`evidence.load.Sample` records, any split.

    Returns:
        One dict per (document, band) holding its paragraphs, their lengths,
        the words Opus removed from each, and the document's whole reduction.
        A document nobody cut carries a reduction of zero and is dropped, since
        there is nothing to allocate.
    """
    groups = {}
    for sample in samples:
        groups.setdefault((sample.doc, sample.band), []).append(sample)
    out = []
    for name in sorted(groups):
        paragraphs = sorted(groups[name], key=lambda sample: sample.idx)
        gold = []
        for sample in paragraphs:
            gold.append(max(len(sample.original.split()) - len(sample.edit.split()), 0))
        if not sum(gold):
            continue
        out.append({
            "doc": name[0],
            "band": name[1],
            "paragraphs": paragraphs,
            "lengths": [len(sample.original.split()) for sample in paragraphs],
            "gold": gold,
            "reduction": sum(gold),
        })
    return out


def deletable(unit: dict, nlp) -> dict:
    """What the fitted model wants deleted in each paragraph of ``unit``.

    Args:
        unit: one entry from :func:`units`.
        nlp: a loaded spaCy pipeline.

    Returns:
        ``{"words", "mass"}``: how many words score at or above :data:`FLOOR` in
        each paragraph, and the sum of those scores, which is the same evidence
        read as a count and as a confidence.
    """
    from tagging import features, model, weights

    fitted = {"intercept": weights.INTERCEPT, "weights": weights.WEIGHT}
    threshold = bands.band(unit["band"]).threshold("tagged")
    counted, mass = [], []
    for sample in unit["paragraphs"]:
        scores = []
        for token in nlp(sample.original):
            if not token.is_space:
                scores.append(model.score(features.of(token), fitted))
        fired = [score for score in scores if score >= max(threshold, FLOOR)]
        counted.append(float(len(fired)))
        mass.append(sum(fired))
    return {"words": counted, "mass": mass}


def _shared(weights_by_paragraph: list, reduction: int) -> list:
    """The reduction split in proportion to one number per paragraph."""
    total = sum(weights_by_paragraph)
    if not total:
        return [reduction / len(weights_by_paragraph)] * len(weights_by_paragraph)
    return [reduction * weight / total for weight in weights_by_paragraph]


def _proportional(unit: dict) -> list:
    return _shared(unit["lengths"], unit["reduction"])


def _equal(unit: dict) -> list:
    return _shared([1.0] * len(unit["lengths"]), unit["reduction"])


def _model_words(unit: dict) -> list:
    return _shared(unit["words"], unit["reduction"])


def _model_mass(unit: dict) -> list:
    return _shared(unit["mass"], unit["reduction"])


def _blended(unit: dict) -> list:
    """Half the length quota and half the model's, since the two disagree."""
    length = _proportional(unit)
    mass = _model_mass(unit)
    return [(one + other) / 2 for one, other in zip(length, mass)]


def _gold(unit: dict) -> list:
    return [float(cut) for cut in unit["gold"]]


METHODS = {
    "length-proportional": _proportional,
    "equal share": _equal,
    "model words": _model_words,
    "model mass": _model_mass,
    "length and model mass, halved": _blended,
    "gold allocation (anchor)": _gold,
}


def score(unit: dict, quotas: list) -> dict:
    """How much of the gold cut a quota reaches and how much it spends elsewhere.

    Args:
        unit: one entry from :func:`units`.
        quotas: one word budget per paragraph, in the same order.

    Returns:
        ``{"captured", "wasted", "error", "weight"}``. ``captured`` is the share
        of the gold cut a paragraph's budget can pay for, counted as the smaller
        of the two, so a paragraph handed more than Opus took gets no credit for
        the excess. ``wasted`` is the share of the budget landing on paragraphs
        Opus left alone, and ``error`` is the total misallocation over the cut.
    """
    gold = unit["gold"]
    total = sum(gold)
    captured = sum(min(quota, cut) for quota, cut in zip(quotas, gold))
    wasted = sum(quota for quota, cut in zip(quotas, gold) if not cut)
    error = sum(abs(quota - cut) for quota, cut in zip(quotas, gold))
    return {
        "captured": captured / total,
        "wasted": wasted / (sum(quotas) or 1.0),
        "error": error / total,
        "weight": total,
    }


def compare(prepared: list) -> list:
    """Every method scored on the same units, weighted by words removed.

    Args:
        prepared: units from :func:`units`, each already through
            :func:`deletable`.

    Returns:
        One row per method, in :data:`METHODS` order, holding the weighted mean
        of each measure and how many units and words it rests on.
    """
    rows = []
    for name in METHODS:
        weight = 0.0
        totals = {"captured": 0.0, "wasted": 0.0, "error": 0.0}
        for unit in prepared:
            got = score(unit, METHODS[name](unit))
            weight += got["weight"]
            for measure in totals:
                totals[measure] += got[measure] * got["weight"]
        rows.append({
            "method": name,
            "captured": totals["captured"] / weight if weight else 0.0,
            "wasted": totals["wasted"] / weight if weight else 0.0,
            "error": totals["error"] / weight if weight else 0.0,
            "units": len(prepared),
            "words": int(weight),
        })
    return rows
