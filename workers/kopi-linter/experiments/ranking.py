"""Score candidate phrase-ranking functions (drop rate, redundancy,
commonness, dependency distance, position, length) by how many of a
paragraph's actual drops they rank first, evaluated separately from the
linting engine.
"""
import random as _random
from collections import Counter
from dataclasses import dataclass, field

from evidence.adjuncts import phrases
from evidence.align import align
from rules.rule_adjunct import commonness as _commonness
from rules.rule_adjunct import droppability as _droppability
from rules.rule_adjunct import rate as _rate

_CONTENT = frozenset(["NOUN", "PROPN", "ADJ", "VERB", "NUM", "ADV"])


@dataclass
class Candidate:
    """One prepositional phrase, its features, and what the gold editor did."""
    dropped: bool
    features: dict = field(default_factory=dict)


def _features(prep, governor, content, elsewhere: Counter, noise) -> dict:
    subtree = list(prep.subtree)
    recoverable = sum(1 for lemma in content if elsewhere.get(lemma, 0) > 1)
    return {
        "rate": _rate(prep, governor),
        "redundancy": recoverable / len(content) if content else 0.0,
        "commonness": _commonness(content),
        "depdist": abs(prep.i - governor.i) + len(subtree),
        "words": len(subtree),
        # Position in the paragraph, descending, so a higher score means earlier.
        # Not a throwaway: reading order turned out to carry signal on its own.
        "earliness": -float(prep.idx),
        "noise": noise.random(),
        # The exact function the engine uses, imported rather than reimplemented,
        # so this comparison cannot drift away from what actually ships.
        "shipped": _droppability(prep, governor, content),
    }


def _paragraph(sample, nlp) -> list:
    """Every prepositional phrase in one paragraph, marked dropped or kept."""
    out = []
    # Seeded from the paragraph so the noise baseline is reproducible across runs
    # without being constant, which is the mistake the first version made: a
    # fresh Random(0) per call returns the same float every time, which silently
    # turns the random baseline into a document-order baseline.
    noise = _random.Random(sample.key)
    for bead in align(sample.original, sample.edit, nlp):
        target = set()
        for target_sentence in bead.target:
            for token in target_sentence:
                target.add(token.lemma_.lower())
        for sentence in bead.source:
            doc = sentence.as_doc()
            elsewhere = Counter(t.lemma_.lower() for t in doc if t.pos_ in _CONTENT)
            for prep, governor, _, _, content in phrases(doc):
                out.append(Candidate(
                    dropped=not (content & target),
                    features=_features(prep, governor, content, elsewhere, noise),
                ))
    return out


def observations(samples, nlp, on_progress=None, require_choice: bool = True) -> list[list]:
    """Candidates grouped by paragraph.

    Args:
        samples: gold :class:`evidence.load.Sample` records.
        nlp: a loaded spaCy pipeline.
        on_progress: called with (index, total, sample).
        require_choice: keep only paragraphs that both dropped and kept a phrase,
            which is what a *ranking* question needs. Allocation needs every
            paragraph, including the many that dropped nothing, because whether
            to cut at all is precisely the question being asked.

    Returns:
        A list of per-paragraph candidate lists.
    """
    groups = []
    total = len(samples)
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, total, sample)
        group = _paragraph(sample, nlp)
        if not group:
            continue
        if not require_choice:
            groups.append(group)
            continue
        if any(c.dropped for c in group) and any(not c.dropped for c in group):
            groups.append(group)
    return groups


SCORERS = {
    "rate": lambda f: f["rate"],
    "redundancy": lambda f: f["redundancy"],
    "commonness": lambda f: f["commonness"],
    "depdist": lambda f: f["depdist"],
    "words": lambda f: f["words"],
    "earliness": lambda f: f["earliness"],
    "rate+early": lambda f: f["rate"] + f["earliness"] / 10000.0,
    "shipped": lambda f: f["shipped"],
    "random": lambda f: f["noise"],
}


def score(groups: list, name: str) -> dict:
    """Precision at oracle k, and mean average precision, for one scorer.

    ``k`` is the number of phrases the gold editor actually dropped in that
    paragraph, so the scorer is never penalised for not knowing how deep to cut.
    It is judged purely on ordering.

    Returns:
        ``{"p_at_k", "map", "groups", "candidates", "base"}`` where ``base`` is
        the rate a scorer would reach by picking blindly.
    """
    scorer = SCORERS[name]
    hits = picks = candidates = 0
    total_ap = 0.0
    for group in groups:
        ordered = sorted(group, key=lambda c: -scorer(c.features))
        k = sum(1 for c in group if c.dropped)
        hits += sum(1 for c in ordered[:k] if c.dropped)
        picks += k
        candidates += len(group)

        relevant = sum(1 for c in ordered if c.dropped)
        rank_hits, rank_total = 0, 0.0
        for rank, candidate in enumerate(ordered, 1):
            if candidate.dropped:
                rank_hits += 1
                rank_total += rank_hits / rank
        if relevant:
            total_ap += rank_total / relevant
    return {
        "p_at_k": hits / picks if picks else 0.0,
        "map": total_ap / len(groups) if groups else 0.0,
        "groups": len(groups),
        "candidates": candidates,
        "base": picks / candidates if candidates else 0.0,
    }
