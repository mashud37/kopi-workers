"""Fit a keep-or-delete decision over every source word and score it on the
held-out documents, which is the licence question asked one token at a time.
"""
from tagging import features, vocabulary

# What the engine needs is precision, not accuracy: an edit made wrongly costs
# closure twice over. These are the operating points the band dial would sit on.
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)

# The threshold every ablation is compared at, chosen because it is where the
# full feature set closes most.
OPERATING = 0.6

_SEED = 0
_EVERYTHING = "everything"

# High enough that the solver stops because it has converged rather than because
# it ran out. A capped fit under-weights the poorly scaled features unevenly,
# which is exactly the thing the ablation below is trying to measure.
_MAX_ITERATIONS = 5000


def dataset(samples, nlp, held_out: set, on_progress=None) -> dict:
    """Feature dictionaries and delete labels for every word, split by document.

    Args:
        samples: gold :class:`evidence.load.Sample` records.
        nlp: a loaded spaCy pipeline.
        held_out: document names in the test split.
        on_progress: called with (index, total, sample).

    Returns:
        ``{"train": {"rows", "labels"}, "test": {"rows", "labels"}}``.
    """
    from eval.closure import distance

    out = {
        "train": {"rows": [], "labels": []},
        "test": {"rows": [], "labels": []},
        "gap": 0,
    }
    total = len(samples)
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, total, sample)
        try:
            tagged = vocabulary.tags_for(sample, nlp)
        except Exception:
            continue
        side = out["test" if sample.doc in held_out else "train"]
        if sample.doc in held_out:
            out["gap"] += distance(sample.original.split(), sample.edit.split())
        for tag in tagged:
            if tag["token"] is None:
                continue
            side["rows"].append(features.of(tag["token"]))
            side["labels"].append(int(tag["base"] == "DELETE"))
    return out


def _operating_points(labels, scores, gap: int) -> list:
    """Precision, recall and projected closure at each threshold the band could use.

    Closure is projected rather than measured: one deleted word is counted as one
    word-edit operation, so a right deletion gains one and a wrong one loses one.
    That ignores the repair a deletion forces on its neighbours and the guard that
    can reject the paragraph, both of which only cost, so the figure is an upper
    bound on what wiring this into the engine would give.
    """
    points = []
    deletes = sum(labels)
    for threshold in THRESHOLDS:
        fired = sum(1 for score in scores if score >= threshold)
        hit = sum(1 for label, score in zip(labels, scores) if score >= threshold and label)
        points.append({
            "threshold": threshold,
            "fired": fired,
            "precision": hit / fired if fired else 0.0,
            "recall": hit / deletes if deletes else 0.0,
            "share": fired / len(labels) if labels else 0.0,
            "closure": (hit - (fired - hit)) / gap if gap else 0.0,
        })
    return points


def _encoded(data: dict) -> dict:
    """Both splits as sparse matrices sharing one column set.

    Vectorised once and re-used by every ablation, because the feature
    dictionaries are the largest thing in memory and copying them per variant
    would cost more than the fits do.
    """
    from sklearn.feature_extraction import DictVectorizer

    encoder = DictVectorizer(sparse=True)
    train = encoder.fit_transform(data["train"]["rows"])
    test = encoder.transform(data["test"]["rows"])
    return {"train": train, "test": test, "names": list(encoder.feature_names_)}


def _feature_of(column: str) -> str:
    """Which feature a vectorised column came from.

    ``DictVectorizer`` names a numeric column after its feature and a one-hot
    column ``feature=value``, so the feature is whatever stands before the first
    ``=``.
    """
    return column.split("=")[0]


def _variants(names: list) -> list:
    """The full column set, then each feature group removed, then each on its own."""
    everything = set()
    for column in names:
        everything.add(_feature_of(column))
    out = [{"label": _EVERYTHING, "keep": everything}]
    for group, members in features.GROUPS.items():
        out.append({"label": f"without {group}", "keep": everything - set(members)})
    for group, members in features.GROUPS.items():
        out.append({"label": f"{group} only", "keep": everything & set(members)})
    return out


def _fit_one(encoded: dict, data: dict, keep: set) -> dict:
    """Fit on the kept features alone and score every threshold on held-out words."""
    from sklearn.linear_model import LogisticRegression

    columns = []
    for index, column in enumerate(encoded["names"]):
        if _feature_of(column) in keep:
            columns.append(index)
    model = LogisticRegression(max_iter=_MAX_ITERATIONS, random_state=_SEED)
    model.fit(encoded["train"][:, columns], data["train"]["labels"])
    scores = model.predict_proba(encoded["test"][:, columns])[:, 1]
    return {
        "points": _operating_points(data["test"]["labels"], scores, data["gap"]),
        "columns": [encoded["names"][index] for index in columns],
        "intercept": float(model.intercept_[0]),
        "weights": [float(weight) for weight in model.coef_[0]],
    }


def _headline(fitted: dict) -> dict:
    """One ablation row: the operating point, and the best closure any threshold reaches."""
    chosen = fitted["points"][0]
    for point in fitted["points"]:
        if point["threshold"] == OPERATING:
            chosen = point
    return {
        "columns": len(fitted["columns"]),
        "fired": chosen["fired"],
        "precision": chosen["precision"],
        "closure": chosen["closure"],
        "best": max(point["closure"] for point in fitted["points"]),
    }


def fit_and_score(data: dict, on_progress=None) -> dict:
    """Fit the full feature set, then every ablation of it, over the same columns.

    Args:
        data: what :func:`dataset` returned.
        on_progress: called with (index, total, variant label).

    Returns:
        ``{"points", "ablation", "gap", "baseline", "trained_on", "scored_on",
        "features", "intercept", "weights"}``. ``baseline`` is the precision of
        guessing delete for every word, which is the number any operating point
        has to beat to mean anything; ``ablation`` says which features earned it.
    """
    encoded = _encoded(data)
    labels = data["test"]["labels"]
    variants = _variants(encoded["names"])
    rows, full = [], None
    for i, variant in enumerate(variants, 1):
        if on_progress:
            on_progress(i, len(variants), variant["label"])
        fitted = _fit_one(encoded, data, variant["keep"])
        if variant["label"] == _EVERYTHING:
            full = fitted
        row = _headline(fitted)
        row["label"] = variant["label"]
        rows.append(row)
    return {
        "points": full["points"],
        "ablation": rows,
        "gap": data["gap"],
        "baseline": sum(labels) / len(labels) if labels else 0.0,
        "trained_on": len(data["train"]["labels"]),
        "scored_on": len(labels),
        "features": len(encoded["names"]),
        "intercept": full["intercept"],
        "weights": dict(zip(full["columns"], full["weights"])),
    }
