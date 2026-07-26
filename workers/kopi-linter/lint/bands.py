"""Editing intensity, as a re-ranking of one rule set.

The evidence (``docs/typology.md`` section 1.3) shows the four bands draw on the
same transformation families in different proportions: nothing appears only in
the aggressive band and nothing vanishes in clarity. So intensity is modelled
here the way the data describes it, as per-family confidence thresholds over a
single rule set, rather than as four separate rule sets.

A band raises the bar rather than closing a door. In the clarity band a
structural family needs near-certainty to fire; in the aggressive band the same
family fires on ordinary evidence. Sentence dropping is the one exception, gated
off entirely below firm, because a wrongly dropped sentence is the only
unrecoverable error the linter can make.

The thresholds are provisional. They are set from the measured band gradient,
not from measured per-rule precision, which does not exist yet: once
``eval/`` reports precision per rule the numbers here should be refitted rather
than argued about.
"""
from dataclasses import dataclass

_UNREACHABLE = 2.0

# Compression ceilings carried over from kopi-editor's intensity plan, so a
# paragraph cannot be cut past what the requested reduction licenses.
_CEILING = {"clarity": 0.06, "light": 0.18, "firm": 0.35, "aggressive": 0.55}

_THRESHOLDS = {
    "clarity": {
        "relative-clause": 0.80, "support-verb": 0.90, "adjunct": 0.95,
        "stance": 0.90, "lexical": 0.85, "connective": 0.85, "voice": 0.85,
        "intensifier": 0.85, "nominalisation": 0.90, "modifier": 0.95,
        "clause": _UNREACHABLE, "sentence": _UNREACHABLE,
    },
    "light": {
        "relative-clause": 0.75, "support-verb": 0.85, "adjunct": 0.90,
        "stance": 0.85, "lexical": 0.75, "connective": 0.80, "voice": 0.80,
        "intensifier": 0.75, "nominalisation": 0.85, "modifier": 0.90,
        "clause": _UNREACHABLE, "sentence": _UNREACHABLE,
    },
    "firm": {
        "relative-clause": 0.65, "support-verb": 0.70, "adjunct": 0.75,
        "stance": 0.75, "lexical": 0.70, "connective": 0.75, "voice": 0.70,
        "intensifier": 0.65, "nominalisation": 0.75, "modifier": 0.80,
        "clause": 0.85, "sentence": 0.90,
    },
    "aggressive": {
        "relative-clause": 0.55, "support-verb": 0.60, "adjunct": 0.60,
        "stance": 0.65, "lexical": 0.60, "connective": 0.70, "voice": 0.65,
        "intensifier": 0.55, "nominalisation": 0.65, "modifier": 0.65,
        "clause": 0.70, "sentence": 0.80,
    },
}

_DEFAULT_THRESHOLD = {"clarity": 0.95, "light": 0.90, "firm": 0.80, "aggressive": 0.70}

# What the gold editor actually removes, as a share of the paragraph's words.
# Median over the corpus, measured per band: 454, 101, 528 and 440 paragraphs.
#
# These are targets and `_CEILING` is the hard stop, and the two were being
# conflated. A ranked family spends a budget rather than clearing a threshold, so
# handing it the ceiling asks for a cut two to five times deeper than the editor
# makes: at firm the ceiling is 35% against a measured median of 14.2%. Only
# clarity was ever close, at 6% against 5.7%.
_TARGET = {"clarity": 0.057, "light": 0.034, "firm": 0.142, "aggressive": 0.191}

BANDS = tuple(_THRESHOLDS)


@dataclass(frozen=True)
class Band:
    name: str
    ceiling: float

    def threshold(self, family: str) -> float:
        """Lowest confidence at which ``family`` may fire in this band."""
        return _THRESHOLDS[self.name].get(family, _DEFAULT_THRESHOLD[self.name])

    def admits(self, edit) -> bool:
        """Whether the band lets this edit into selection at all.

        A ranked proposal is always admitted here and constrained later by the
        word budget: its confidence is an ordering rather than a probability, so
        comparing it to a threshold is meaningless. See
        :class:`lint.edit.Edit` and ``docs/constraints.md`` C9 to C11.
        """
        if edit.ranked:
            return True
        return edit.confidence >= self.threshold(edit.family)

    def floor(self, words: int) -> int:
        """Fewest words a paragraph of ``words`` may keep in this band.

        The hard stop. Crossing it fails the guard and the paragraph is returned
        unedited.
        """
        return words - max(int(words * self.ceiling), 1)

    def target_floor(self, words: int) -> int:
        """Words a paragraph of ``words`` should keep if it cuts like the gold editor.

        The soft budget a ranked family spends, set from the measured median
        reduction for this band rather than from the compression ceiling.
        """
        return words - max(int(words * _TARGET[self.name]), 1)


def band(name: str) -> Band:
    if name not in _THRESHOLDS:
        raise SystemExit(f"unknown band '{name}', expected one of {', '.join(BANDS)}")
    return Band(name=name, ceiling=_CEILING[name])


def for_reduction(words_to_remove: int, total_words: int) -> Band:
    """The band implied by a requested reduction, matching kopi-editor's ratios."""
    if not words_to_remove or not total_words:
        return band("clarity")
    share = words_to_remove / total_words
    if share <= 0.05:
        return band("light")
    if share <= 0.12:
        return band("firm")
    return band("aggressive")
