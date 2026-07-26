"""Dropping a prepositional phrase, the largest deletion-reachable family.

1,958 instances and 6,374 words in the gold corpus, 92% of it a prepositional
phrase being removed. Proposing the drop is trivial; the whole difficulty is the
licence, because an adjunct may go and an argument may not, and the parse labels
both `prep`.

Four models are registered so the question can be settled by measurement rather
than by preference (see ``experiments/registry.py``):

* ``syntactic``  a naive structural baseline with no lexical knowledge at all
* ``frame``      the induced drop rate for this exact (governor, preposition)
* ``backoff``    the induced rate, falling back to coarser keys when unseen
* ``ranked``     the same rate blended with word commonness, as an *ordering*

``ranked`` is the one the evidence points at. Measured as licences, the first
three fail in opposite directions: structural fires 647 times at a 2% agreement
ceiling, induced fires three times because no category's drop rate can reach a
band threshold (``docs/constraints.md`` C9). Measured as an *ordering* the same
induced rate reaches 1.88x a shuffle baseline (C10), so the band stops asking
"may this phrase go?" and starts asking "how many words must go, and which are
first?". A rule in ``ranked`` mode therefore proposes freely and lets the band's
word budget decide the depth of the cut.
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
    """
    model: str = "ranked"
    minimum: int = 5
    flat: float = 0.75


DEFAULT = Licence()


def _table(level: str) -> dict:
    if induced_adjuncts is None:
        return {}
    return getattr(induced_adjuncts, f"{level.upper()}_RATE", {})


@lru_cache(maxsize=1)
def _zipf():
    from wordfreq import zipf_frequency
    return zipf_frequency


def rate(prep, governor, minimum: int = 5) -> float:
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


def droppability(prep, governor, content, minimum: int = 5) -> float:
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


def _induced(prep, governor, licence: Licence) -> tuple[float, str]:
    """Drop rate from the induced tables, with backoff. Returns (rate, level)."""
    keys = keys_for(prep, governor)
    levels = LEVELS if licence.model == "backoff" else ("frame",)
    for level in levels:
        entry = _table(level).get(keys[level])
        if entry and entry[1] >= licence.minimum:
            return entry[0], level
    return 0.0, "none"


def _ranked(prep, governor, content, licence: Licence) -> tuple[float, str]:
    """Ordering score, offered to the band's budget rather than to a threshold."""
    return droppability(prep, governor, content, licence.minimum), "ranked"


def _span(doc, start: int, end: int) -> tuple[int, int]:
    """Widen a phrase span to the whitespace and comma the drop would strand."""
    text = doc.text
    while start > 0 and text[start - 1].isspace():
        start -= 1
    while end < len(text) and text[end] in ",;":
        end += 1
    if start == 0:
        while end < len(text) and text[end].isspace():
            end += 1
    return start, end


def _confidence(prep, governor, content, licence: Licence) -> tuple[float, str]:
    if licence.model == "syntactic":
        return licence.flat * _structural(prep, governor, content), "structural"
    if not _structural(prep, governor, content):
        return 0.0, "none"
    if licence.model == "ranked":
        return _ranked(prep, governor, content, licence)
    return _induced(prep, governor, licence)


def propose(doc, licence: Licence = DEFAULT):
    """Yield a drop for every prepositional phrase the licence admits."""
    for prep, governor, start, end, content in phrases(doc):
        confidence, level = _confidence(prep, governor, content, licence)
        if confidence <= 0.0:
            continue
        start, end = _span(doc, start, end)
        yield Edit(
            start=start, end=end, replacement="",
            rule=f"adjunct.{licence.model}", family="adjunct",
            confidence=round(confidence, 3),
            note=f"prepositional phrase dropped: '{doc.text[start:end].strip()}' "
                 f"({level} licence)",
            ranked=licence.model == "ranked",
        )
