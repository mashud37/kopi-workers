"""Describe one source word by its parse, its neighbours and its frequency, as
the plain feature dictionary a linear model reads.
"""
from functools import lru_cache

_RARE_ZIPF = 3.0
_MAX_DEPTH = 20


@lru_cache(maxsize=100_000)
def _zipf(word: str) -> float:
    from wordfreq import zipf_frequency

    return zipf_frequency(word.lower(), "en")


def _depth(token) -> int:
    """How many steps up the dependency tree the sentence root is."""
    steps = 0
    walker = token
    while walker.head is not walker and steps < _MAX_DEPTH:
        walker = walker.head
        steps += 1
    return steps


def of(token) -> dict:
    """Every feature for one word, as a name-to-value dictionary.

    Strings become one-hot columns and numbers stay numeric, which is what
    ``DictVectorizer`` does with a mixed dictionary, so the whole feature set is
    readable here rather than encoded somewhere else.
    """
    sentence = token.sent
    length = len(sentence)
    head = token.head
    return {
        "pos": token.pos_,
        "dep": token.dep_,
        "tag": token.tag_,
        "head_pos": head.pos_,
        "head_dep": head.dep_,
        "lemma": token.lemma_.lower(),
        "previous_pos": token.nbor(-1).pos_ if token.i > sentence.start else "START",
        "next_pos": token.nbor(1).pos_ if token.i + 1 < sentence.end else "END",
        "is_stop": float(token.is_stop),
        "is_punct": float(token.is_punct),
        "is_alpha": float(token.is_alpha),
        "depth": float(_depth(token)),
        "subtree": float(len(list(token.subtree))),
        "position": (token.i - sentence.start) / length if length else 0.0,
        "sentence_length": float(length),
        "rare": float(_zipf(token.text) < _RARE_ZIPF),
        "zipf": _zipf(token.text),
    }
