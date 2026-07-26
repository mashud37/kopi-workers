"""Which phrase goes first? Ranking, evaluated separately from the pipeline.

C9 established that a per-category drop rate cannot *license* a deletion, because
roughly nine phrases in ten survive and no category's rate approaches a usable
threshold. The conclusion is not that the rates are worthless. It is that they
answer the wrong question. A threshold asks "may this phrase go?"; the band
already knows how many words have to go, so the question it actually needs
answered is **"of the phrases here, which go first?"**

That is a ranking problem, and ranking can be evaluated without running the
engine at all. In each paragraph the gold editor dropped some number of the
phrases present. Take that number as given, rank the candidates by a scoring
function, and ask how many of its top choices were the editor's choices. A
scorer that cannot beat picking at random has no business in the selection stage,
and one that does beats it earns the budget mechanism.

Scorers are drawn from different fields on purpose, since the point of the
comparison is to find out which *kind* of information decides a drop:

* ``rate``          the induced corpus statistic, the thing C9 said cannot threshold
* ``redundancy``    discourse: how much of the phrase is recoverable from its paragraph
* ``commonness``    information theory: low-information phrases go first
* ``depdist``       processing cost, after dependency locality theory
* ``earliness``     reading position, included after it turned up by accident
* ``words``         the naive baseline, drop whatever is longest
* ``rate+*``        blends, scaled but not fitted

**The bar is ``random``, not the corpus drop rate.** Shuffling scores well above
the corpus rate, because paragraphs where many phrases were dropped contribute
more picks and a blind order therefore gets more chances exactly where hits are
easy. Scoring against the corpus rate credits every scorer with roughly 0.6x of
lift it has not earned.
"""
import random as _random
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from evidence.adjuncts import keys_for, phrases
from evidence.align import align

_CONTENT = frozenset(["NOUN", "PROPN", "ADJ", "VERB", "NUM", "ADV"])


@lru_cache(maxsize=1)
def _zipf():
    from wordfreq import zipf_frequency
    return zipf_frequency


@dataclass
class Candidate:
    """One prepositional phrase, its features, and what the gold editor did."""
    dropped: bool
    features: dict = field(default_factory=dict)


def _rate(prep, governor) -> float:
    from evidence.adjuncts import LEVELS
    from rules.rule_adjunct import _table

    keys = keys_for(prep, governor)
    for level in LEVELS:
        entry = _table(level).get(keys[level])
        if entry and entry[1] >= 5:
            return entry[0]
    return 0.0


def _commonness(content: set) -> float:
    """Mean Zipf frequency of the phrase's content words, high meaning ordinary."""
    zipf = _zipf()
    scores = [zipf(lemma, "en") for lemma in sorted(content)]
    return sum(scores) / len(scores) if scores else 0.0


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
        target = {t.lemma_.lower() for s in bead.target for t in s}
        for sentence in bead.source:
            doc = sentence.as_doc()
            elsewhere = Counter(t.lemma_.lower() for t in doc if t.pos_ in _CONTENT)
            for prep, governor, _, _, content in phrases(doc):
                out.append(Candidate(
                    dropped=not (content & target),
                    features=_features(prep, governor, content, elsewhere, noise),
                ))
    return out


def observations(samples, nlp, on_progress=None) -> list[list]:
    """Candidates grouped by paragraph, keeping only paragraphs with a choice to make."""
    groups = []
    total = len(samples)
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, total, sample)
        group = _paragraph(sample, nlp)
        kept = sum(1 for c in group if not c.dropped)
        if group and kept and any(c.dropped for c in group):
            groups.append(group)
    return groups


SCORERS = {
    "rate": lambda f: f["rate"],
    "redundancy": lambda f: f["redundancy"],
    "commonness": lambda f: f["commonness"],
    "depdist": lambda f: f["depdist"],
    "words": lambda f: f["words"],
    "earliness": lambda f: f["earliness"],
    # Zipf runs 0 to about 7, the other two are 0 to 1, so commonness is scaled
    # before being added. A fitted weighting is the obvious next step if the
    # blend ever beats its own components, which so far it does not.
    "rate+common": lambda f: f["rate"] + f["commonness"] / 7.0,
    "rate+early": lambda f: f["rate"] + f["earliness"] / 10000.0,
    "random": lambda f: f["noise"],
}


def _average_precision(ordered: list) -> float:
    hits, total = 0, 0.0
    relevant = sum(1 for c in ordered if c.dropped)
    if not relevant:
        return 0.0
    for rank, candidate in enumerate(ordered, 1):
        if candidate.dropped:
            hits += 1
            total += hits / rank
    return total / relevant


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
        total_ap += _average_precision(ordered)
    return {
        "p_at_k": hits / picks if picks else 0.0,
        "map": total_ap / len(groups) if groups else 0.0,
        "groups": len(groups),
        "candidates": candidates,
        "base": picks / candidates if candidates else 0.0,
    }
