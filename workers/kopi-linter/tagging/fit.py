"""Fit a keep-or-delete decision over every source word and score it on the
held-out documents, which is the licence question asked one token at a time.
"""
from tagging import features, vocabulary

# What the engine needs is precision, not accuracy: an edit made wrongly costs
# closure twice over. These are the operating points the band dial would sit on.
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)

_SEED = 0
_MAX_ITERATIONS = 400


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


def fit_and_score(data: dict) -> dict:
    """Fit on the training words, score on the held-out ones, report both.

    Returns:
        ``{"points", "baseline", "trained_on", "scored_on", "features"}``, where
        ``baseline`` is the precision of guessing delete for every word, which is
        the number any operating point has to beat to mean anything.
    """
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression

    encoder = DictVectorizer(sparse=True)
    train_x = encoder.fit_transform(data["train"]["rows"])
    test_x = encoder.transform(data["test"]["rows"])
    model = LogisticRegression(max_iter=_MAX_ITERATIONS, random_state=_SEED)
    model.fit(train_x, data["train"]["labels"])
    scores = model.predict_proba(test_x)[:, 1]
    labels = data["test"]["labels"]
    return {
        "points": _operating_points(labels, scores, data["gap"]),
        "gap": data["gap"],
        "baseline": sum(labels) / len(labels) if labels else 0.0,
        "trained_on": len(data["train"]["labels"]),
        "scored_on": len(labels),
        "features": len(encoder.feature_names_),
    }
