"""Run any candidate generator against the gold originals, classifying each
proposal as attested, declined, or rewritten/dropped by what Opus did there.
Anchors on the untouched left context.
"""
from collections import Counter
from dataclasses import dataclass, field

_LEFT = 3
_RIGHT = 6
_MINIMUM = 4


@dataclass
class Probe:
    """What the gold editor did with the candidates a generator proposed."""
    verdicts: Counter = field(default_factory=Counter)
    examples: dict = field(default_factory=dict)

    @property
    def decidable(self) -> int:
        return self.verdicts["attested"] + self.verdicts["declined"]

    @property
    def rate(self) -> float:
        """Share of decidable candidates the gold editor also transformed."""
        return self.verdicts["attested"] / self.decidable if self.decidable else 0.0


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


def _reading(original: str, start: int, tail: str) -> str:
    """One candidate reading of the text, anchored in untouched left context."""
    left = _norm(original[:start]).split()[-_LEFT:]
    right = _norm(tail).split()[:_RIGHT]
    return " ".join(left + right) if len(left) + len(right) >= _MINIMUM else ""


def verdict(edit, original: str, gold: str) -> str:
    """What the gold did with the span this edit targets.

    Args:
        edit: a proposed :class:`lint.edit.Edit`, which need not be shippable.
        original: the paragraph the edit was proposed against.
        gold: the reference editor's version of the same paragraph.

    Returns:
        ``"attested"``, ``"declined"``, ``"rewritten or dropped"``, or
        ``"too short to judge"`` when there is not enough context either side.
    """
    reference = _norm(gold)
    edited = _reading(original, edit.start, edit.replacement + original[edit.end:])
    kept = _reading(original, edit.start, original[edit.start:])
    if not edited or not kept:
        return "too short to judge"
    if edited in reference:
        return "attested"
    if kept in reference:
        return "declined"
    return "rewritten or dropped"


def run(samples, propose, nlp, on_progress=None) -> Probe:
    """Probe one candidate generator against every gold paragraph.

    Args:
        samples: :class:`evidence.load.Sample` records for the reference editor.
        propose: any ``doc -> iterable[Edit]`` callable, including a deliberately
            loose one that would never ship. Looseness is the point: the probe
            is asked before the licence exists.
        nlp: a loaded spaCy pipeline.
        on_progress: called with (index, total, sample).

    Returns:
        A :class:`Probe` of verdict counts with up to three examples each.
    """
    probe = Probe()
    total = len(samples)
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, total, sample)
        for edit in propose(nlp(sample.original)):
            call = verdict(edit, sample.original, sample.edit)
            probe.verdicts[call] += 1
            probe.examples.setdefault(call, [])
            if len(probe.examples[call]) < 3:
                probe.examples[call].append(edit.source(sample.original).strip()[:70])
    return probe
