"""Propose dropping a prepositional phrase under one of four licence models
(`syntactic`, `frame`, `backoff`, `ranked`), chosen by measurement since the
parse alone cannot tell adjunct from argument.
"""
from dataclasses import dataclass
from functools import lru_cache

from evidence.adjuncts import LEVELS, keys_for, phrases
from lint.edit import Edit

try:
    from rules import induced_adjuncts
except ImportError:
    induced_adjuncts = None

_MIN_CONTENT_TOKENS = 2
_MIN_OBSERVATIONS = 5

# Zipf frequency runs 0 to about 7; the drop rate runs 0 to 1. Dividing brings
# them onto one scale so they can be added. The halving keeps the result inside
# [0, 1] and, deliberately, below the confidence a licensed rule asserts, so that
# when the budget has to give something up it gives up a ranked guess before a
# licensed edit.
_ZIPF_MAX = 7.0
_BLEND_MAX = 2.0


@dataclass(frozen=True)
class Licence:
    """Which model decides whether a phrase may be dropped.

    Attributes:
        model: ``syntactic``, ``frame``, ``backoff`` or ``ranked``.
        minimum: fewest observations before an induced rate is trusted.
        flat: confidence the syntactic baseline asserts, having no evidence of
            its own to offer.
        argument_ceiling: refuse when the governor takes this preposition at
            least this often. 1.0 disables the test. See :func:`is_argument`.
    """
    model: str = "ranked"
    minimum: int = _MIN_OBSERVATIONS
    flat: float = 0.75
    argument_ceiling: float = 1.0


DEFAULT = Licence()


def _table(level: str) -> dict:
    if induced_adjuncts is None:
        return {}
    return getattr(induced_adjuncts, f"{level.upper()}_RATE", {})


@lru_cache(maxsize=1)
def _zipf():
    from wordfreq import zipf_frequency
    return zipf_frequency


def rate(prep, governor, minimum: int = _MIN_OBSERVATIONS) -> float:
    """Induced drop rate for this phrase, backing off to coarser keys."""
    keys = keys_for(prep, governor)
    for level in LEVELS:
        entry = _table(level).get(keys[level])
        if entry and entry[1] >= minimum:
            return entry[0]
    return 0.0


def commonness(content) -> float:
    """Mean Zipf frequency of the phrase's content words, high meaning ordinary."""
    zipf = _zipf()
    scores = [zipf(lemma, "en") for lemma in sorted(content)]
    return sum(scores) / len(scores) if scores else 0.0


def is_argument(prep, governor, ceiling: float) -> bool:
    """Whether this preposition looks obligatory for this governor.

    The argument-versus-adjunct test, asked distributionally rather than from a
    verb lexicon. "Depends" takes "on" in most of its occurrences, so "on" is its
    argument and may not be dropped; "written" spreads across "in", "with",
    "for" and many others, so no single one of them is obligatory. Measured on
    the originals alone, so this licence is a fact about the language rather than
    about one teacher's edits, and should transfer to unseen prose.
    """
    if ceiling >= 1.0:
        return False
    table = _table("attachment")
    entry = table.get(f"{governor.pos_}:{governor.lemma_.lower()}:{prep.lemma_.lower()}")
    return bool(entry) and entry[0] >= ceiling


def droppability(prep, governor, content, minimum: int = _MIN_OBSERVATIONS) -> float:
    """How readily this phrase goes, in [0, 1]. Ordering, not licence.

    The blend that won the ranking comparison: the corpus statistic for how often
    editors drop this kind of phrase, plus how ordinary its words are. Neither
    reaches 1.88x a shuffle baseline alone. The weights are scaling, not fitted,
    which is the first thing to revisit if this rule underperforms.
    """
    return (rate(prep, governor, minimum) + commonness(content) / _ZIPF_MAX) / _BLEND_MAX


def _structural(prep, governor, content) -> float:
    """The baseline licence: attachment and size, and nothing else.

    Deliberately ignorant. It knows a phrase hangs off a verb or a noun and that
    the governor has other dependents to fall back on, which is the weakest
    argument-versus-adjunct test that is still a test.
    """
    if governor.pos_ not in ("VERB", "NOUN", "AUX", "PROPN"):
        return 0.0
    if len(content) < _MIN_CONTENT_TOKENS:
        return 0.0
    siblings = [c for c in governor.children if c is not prep and c.dep_ != "punct"]
    return 1.0 if siblings else 0.0


def _induced(prep, governor, licence: Licence) -> dict:  # lint-style: ignore FN004
    """Drop rate from the induced tables, with backoff, and the level it came from."""
    keys = keys_for(prep, governor)
    levels = LEVELS if licence.model == "backoff" else ("frame",)
    for level in levels:
        entry = _table(level).get(keys[level])
        if entry and entry[1] >= licence.minimum:
            return {"confidence": entry[0], "level": level}
    return {"confidence": 0.0, "level": "none"}


def _ranked(prep, governor, content, licence: Licence) -> dict:  # lint-style: ignore FN004
    """Ordering score, offered to the band's budget rather than to a threshold."""
    score = droppability(prep, governor, content, licence.minimum)
    return {"confidence": score, "level": "ranked"}


def _confidence(prep, governor, content, licence: Licence) -> dict:  # lint-style: ignore FN004
    if is_argument(prep, governor, licence.argument_ceiling):
        return {"confidence": 0.0, "level": "argument"}
    if licence.model == "syntactic":
        return {"confidence": licence.flat * _structural(prep, governor, content),
                "level": "structural"}
    if not _structural(prep, governor, content):
        return {"confidence": 0.0, "level": "none"}
    if licence.model == "ranked":
        return _ranked(prep, governor, content, licence)
    return _induced(prep, governor, licence)


def propose(doc, licence: Licence = DEFAULT):
    """A drop for every prepositional phrase the licence admits."""
    text = doc.text
    edits = []
    for prep, governor, start, end, content in phrases(doc):
        licensed = _confidence(prep, governor, content, licence)
        if licensed["confidence"] <= 0.0:
            continue
        while start > 0 and text[start - 1].isspace():
            start -= 1
        while end < len(text) and text[end] in ",;":
            end += 1
        if start == 0:
            while end < len(text) and text[end].isspace():
                end += 1
        edits.append(Edit(
            start=start, end=end, replacement="",
            rule=f"adjunct.{licence.model}", family="adjunct",
            confidence=round(licensed["confidence"], 3),
            note=f"prepositional phrase dropped: '{doc.text[start:end].strip()}' "
                 f"({licensed['level']} licence)",
            ranked=licence.model == "ranked",
        ))
    return edits
