"""Fit the same keep-or-delete decision on competing feature sets and score
them on the same held-out words, which is the contest step 12 asks for.
"""
from tagging import encoder, features, fit, vocabulary

SEED = 0
MAX_ITERATIONS = 5000

# The three feature sets under comparison: the shipped one-hot bag, the frozen
# encoder's contextual vectors, and both columns together.
SETS = (
    "one-hot",
    "encoder",
    "one-hot and encoder",
)


def dataset(samples: list, nlp, held_out: set, on_progress=None) -> dict:
    """Feature dictionaries, encoder vectors and delete labels for every word.

    Args:
        samples: gold :class:`evidence.load.Sample` records.
        nlp: a loaded spaCy pipeline.
        held_out: document names in the test split.
        on_progress: called with (index, total, sample).

    Returns:
        ``{"train": {"rows", "vectors", "labels"}, "test": ..., "gap"}``, where
        ``vectors`` holds one float32 array per paragraph and ``rows`` holds one
        dictionary per word, in the same order as ``labels``.
    """
    import numpy

    from eval.closure import distance

    out = {
        "train": {"rows": [], "vectors": [], "labels": []},
        "test": {"rows": [], "vectors": [], "labels": []},
        "gap": 0,
    }
    for index, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(index, len(samples), sample)
        try:
            tagged = vocabulary.tags_for(sample, nlp)
        except Exception:
            continue
        words, rows, labels = [], [], []
        for tag in tagged:
            if tag["token"] is None:
                continue
            words.append(tag["token"].text)
            rows.append(features.of(tag["token"]))
            labels.append(int(tag["base"] == "DELETE"))
        if not words:
            continue
        side = out["test" if sample.doc in held_out else "train"]
        side["rows"].extend(rows)
        side["labels"].extend(labels)
        side["vectors"].append(numpy.asarray(encoder.vectors_for(words), dtype="float32"))
        if sample.doc in held_out:
            out["gap"] += distance(sample.original.split(), sample.edit.split())
    return out


def _columns(data: dict) -> dict:
    """Every feature set as a matrix per split, ready to fit.

    The one-hot columns are sparse and the encoder columns are dense, so the
    joined set is stacked through ``scipy`` rather than densified, which would
    cost a gigabyte for nothing.
    """
    import numpy
    from scipy.sparse import csr_matrix, hstack
    from sklearn.feature_extraction import DictVectorizer

    vectorizer = DictVectorizer(sparse=True)
    sparse_train = vectorizer.fit_transform(data["train"]["rows"])
    sparse_test = vectorizer.transform(data["test"]["rows"])
    dense_train = numpy.vstack(data["train"]["vectors"])
    dense_test = numpy.vstack(data["test"]["vectors"])
    return {
        "one-hot": {"train": sparse_train, "test": sparse_test},
        "encoder": {"train": dense_train, "test": dense_test},
        "one-hot and encoder": {
            "train": hstack([sparse_train, csr_matrix(dense_train)]).tocsr(),
            "test": hstack([sparse_test, csr_matrix(dense_test)]).tocsr(),
        },
    }


def contest(data: dict, on_progress=None) -> dict:
    """Fit each feature set on the train documents and score the held-out ones.

    Args:
        data: what :func:`dataset` returned.
        on_progress: called with (index, total, feature-set name).

    Returns:
        ``{"rows", "points", "gap", "baseline", "trained_on", "scored_on"}``.
        Each row carries the operating point at :data:`tagging.fit.OPERATING`
        and the best projected closure any threshold reaches, so the sets are
        read at one dial setting and at their own best.
    """
    from sklearn.linear_model import LogisticRegression

    matrices = _columns(data)
    labels = data["test"]["labels"]
    rows, points = [], {}
    for index, name in enumerate(SETS, 1):
        if on_progress:
            on_progress(index, len(SETS), name)
        model = LogisticRegression(max_iter=MAX_ITERATIONS, random_state=SEED)
        model.fit(matrices[name]["train"], data["train"]["labels"])
        scores = model.predict_proba(matrices[name]["test"])[:, 1]
        measured = fit.operating_points(labels, scores, data["gap"])
        chosen = measured[0]
        for point in measured:
            if point["threshold"] == fit.OPERATING:
                chosen = point
        points[name] = measured
        rows.append({
            "label": name,
            "columns": matrices[name]["train"].shape[1],
            "fired": chosen["fired"],
            "precision": chosen["precision"],
            "recall": chosen["recall"],
            "closure": chosen["closure"],
            "best": max(point["closure"] for point in measured),
        })
    return {
        "rows": rows,
        "points": points,
        "gap": data["gap"],
        "baseline": sum(labels) / len(labels) if labels else 0.0,
        "trained_on": len(data["train"]["labels"]),
        "scored_on": len(labels),
    }
