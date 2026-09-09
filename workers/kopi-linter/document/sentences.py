"""Describe every source sentence and ask whether the gold editor dropped it,
which is the licence sentence dropping needs and has never had.
"""
_RARE_ZIPF = 3.0
_SEED = 0
_MAX_ITERATIONS = 5000

THRESHOLDS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
OPERATING = 0.7

# How far down the ranking to read, since a threshold grid says nothing about a
# class this rare if the model never reaches the grid at all.
TOP = (10, 25, 50, 100)

# What kind of evidence each feature is. `discourse` is the group step 14 rests
# on: everything a sentence can only know by looking at the paragraph around it.
GROUPS = {
    "size": (
        "words",
        "sentences",
        "share_of_paragraph",
    ),
    "discourse": (
        "position",
        "first",
        "last",
        "repeated",
        "unique",
        "opens_with_connective",
    ),
    "inside": (
        "root_pos",
        "root_dep",
        "subordinate",
        "passive",
        "proper_share",
        "digit_share",
        "rare_share",
        "mean_zipf",
    ),
}


def _content(sentence) -> set:
    lemmas = set()
    for token in sentence:
        if token.is_alpha and not token.is_stop:
            lemmas.add(token.lemma_.lower())
    return lemmas


def _shares(sentence) -> dict:
    """The plain counting features, as shares of the sentence's words."""
    from wordfreq import zipf_frequency

    words = [token for token in sentence if not token.is_space]
    total = len(words) or 1
    proper = sum(1 for token in words if token.pos_ == "PROPN")
    digits = sum(1 for token in words if token.like_num)
    zipfs = [zipf_frequency(token.text.lower(), "en") for token in words if token.is_alpha]
    rare = sum(1 for value in zipfs if value < _RARE_ZIPF)
    return {
        "proper_share": proper / total,
        "digit_share": digits / total,
        "rare_share": rare / total,
        "mean_zipf": sum(zipfs) / len(zipfs) if zipfs else 0.0,
    }


def of(index: int, sentences: list) -> dict:
    """Every feature for one sentence of a paragraph, as a plain dictionary.

    Args:
        index: which sentence this is, counting from zero.
        sentences: the paragraph's sentences, in order.

    Returns:
        Numbers and strings in the shape ``DictVectorizer`` reads. ``repeated``
        is the share of the sentence's content lemmas that appear somewhere else
        in the paragraph, and ``unique`` is its complement, which is what makes
        this a discourse decision rather than a sentence-local one.
    """
    sentence = sentences[index]
    mine = _content(sentence)
    others = set()
    for place, other in enumerate(sentences):
        if place != index:
            others |= _content(other)
    shared = len(mine & others) / len(mine) if mine else 0.0
    words = len([token for token in sentence if not token.is_space])
    paragraph = sum(len([t for t in other if not t.is_space]) for other in sentences) or 1
    first = sentence[0]
    return {
        "position": index / len(sentences),
        "first": float(index == 0),
        "last": float(index == len(sentences) - 1),
        "sentences": float(len(sentences)),
        "words": float(words),
        "share_of_paragraph": words / paragraph,
        "repeated": shared,
        "unique": 1.0 - shared,
        "opens_with_connective": float(first.dep_ in {"advmod", "cc", "mark"}),
        "root_pos": sentence.root.pos_,
        "root_dep": sentence.root.dep_,
        "subordinate": float(any(token.dep_ == "mark" for token in sentence)),
        "passive": float(any(token.dep_.endswith("pass") for token in sentence)),
        **_shares(sentence),
    }


def _dropped_sentences(sample, nlp) -> set:
    """Which source sentences the gold editor cut whole, by their start offset."""
    from evidence.align import align

    out = set()
    for bead in align(sample.original, sample.edit, nlp):
        if bead.op == "delete":
            for sentence in bead.source:
                out.add(sentence.start_char)
    return out


def dataset(samples: list, nlp, held_out: set, on_progress=None) -> dict:
    """Features and drop labels for every source sentence, split by document.

    Args:
        samples: gold :class:`evidence.load.Sample` records.
        nlp: a loaded spaCy pipeline.
        held_out: document names in the test split.
        on_progress: called with (index, total, sample).

    Returns:
        ``{"train": {"rows", "labels", "lengths"}, "test": ..., "gap"}``, where
        ``lengths`` is each sentence's word count, so a projected closure can
        price a drop at what it actually moves.
    """
    from eval.closure import distance

    out = {
        "train": {"rows": [], "labels": [], "lengths": []},
        "test": {"rows": [], "labels": [], "lengths": []},
        "gap": 0,
    }
    for index, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(index, len(samples), sample)
        try:
            parsed = nlp(sample.original)
            dropped = _dropped_sentences(sample, nlp)
        except Exception:
            continue
        sentences = list(parsed.sents)
        side = out["test" if sample.doc in held_out else "train"]
        if sample.doc in held_out:
            out["gap"] += distance(sample.original.split(), sample.edit.split())
        for place, sentence in enumerate(sentences):
            side["rows"].append(of(place, sentences))
            side["labels"].append(int(sentence.start_char in dropped))
            side["lengths"].append(len(sentence.text.split()))
    return out


def operating_points(labels: list, lengths: list, scores: list, gap: int) -> list:
    """Precision, recall and projected closure at each threshold, priced in words.

    A dropped sentence moves its own length in word operations, so a right drop
    gains that many and a wrong one loses that many. Recall is over words too,
    since dropping the short sentences and refusing the long ones is not the same
    achievement as the reverse.
    """
    points = []
    total = sum(length for length, label in zip(lengths, labels) if label)
    for threshold in THRESHOLDS:
        fired = [place for place, score in enumerate(scores) if score >= threshold]
        hit = [place for place in fired if labels[place]]
        gained = sum(lengths[place] for place in hit)
        lost = sum(lengths[place] for place in fired if not labels[place])
        points.append({
            "threshold": threshold,
            "fired": len(fired),
            "precision": len(hit) / len(fired) if fired else 0.0,
            "recall": gained / total if total else 0.0,
            "words": gained - lost,
            "closure": (gained - lost) / gap if gap else 0.0,
        })
    return points


def ranked(labels: list, lengths: list, scores: list) -> list:
    """Precision and net words among the highest-scoring sentences.

    A rare class can be ranked well and still never cross a probability
    threshold, so this asks the other question: if the engine simply dropped the
    ``k`` sentences the model likes most, how many would Opus have dropped too?
    """
    order = sorted(range(len(scores)), key=lambda place: scores[place], reverse=True)
    out = []
    for size in TOP:
        picked = order[:size]
        hit = [place for place in picked if labels[place]]
        gained = sum(lengths[place] for place in hit)
        lost = sum(lengths[place] for place in picked if not labels[place])
        out.append({
            "size": size,
            "hit": len(hit),
            "precision": len(hit) / len(picked) if picked else 0.0,
            "words": gained - lost,
        })
    return out


def _variants(names: list) -> list:
    """The full feature set, then each group removed, then each on its own."""
    everything = set()
    for column in names:
        everything.add(column.split("=")[0])
    out = [{"label": "everything", "keep": everything}]
    for group in GROUPS:
        out.append({"label": f"without {group}", "keep": everything - set(GROUPS[group])})
    for group in GROUPS:
        out.append({"label": f"{group} only", "keep": everything & set(GROUPS[group])})
    return out


def fit_and_score(data: dict, on_progress=None) -> dict:
    """Fit the drop decision on the train documents and score the held-out ones.

    Args:
        data: what :func:`dataset` returned.
        on_progress: called with (index, total, variant label).

    Returns:
        ``{"points", "ablation", "gap", "baseline", "trained_on", "scored_on",
        "dropped"}``. ``baseline`` is the share of held-out sentences Opus
        dropped, which is what guessing drop everywhere would score.
    """
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression

    vectorizer = DictVectorizer(sparse=True)
    train = vectorizer.fit_transform(data["train"]["rows"])
    test = vectorizer.transform(data["test"]["rows"])
    names = list(vectorizer.feature_names_)
    labels, lengths = data["test"]["labels"], data["test"]["lengths"]
    rows, full = [], None
    variants = _variants(names)
    for index, variant in enumerate(variants, 1):
        if on_progress:
            on_progress(index, len(variants), variant["label"])
        columns = [place for place, name in enumerate(names)
                   if name.split("=")[0] in variant["keep"]]
        model = LogisticRegression(max_iter=_MAX_ITERATIONS, random_state=_SEED)
        model.fit(train[:, columns], data["train"]["labels"])
        scores = model.predict_proba(test[:, columns])[:, 1]
        measured = operating_points(labels, lengths, scores, data["gap"])
        chosen = [point for point in measured if point["threshold"] == OPERATING][0]
        if variant["label"] == "everything":
            full = measured
            top = ranked(labels, lengths, scores)
            highest = max(scores)
        rows.append({
            "label": variant["label"],
            "columns": len(columns),
            "fired": chosen["fired"],
            "precision": chosen["precision"],
            "closure": chosen["closure"],
            "best": max(point["closure"] for point in measured),
        })
    return {
        "points": full,
        "top": top,
        "highest": float(highest),
        "ablation": rows,
        "gap": data["gap"],
        "baseline": sum(labels) / len(labels) if labels else 0.0,
        "trained_on": len(data["train"]["labels"]),
        "scored_on": len(labels),
        "dropped": sum(labels),
    }
