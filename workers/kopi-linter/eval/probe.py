"""Ask whether Opus performs a transformation, before anyone builds it.

C13: linguistic validity does not predict attestation. Reducing "which revolve
around time" to "revolving around time" is textbook whiz-deletion, is described
in every grammar of English, and Opus rejects it 33 to 1. Building it would have
added 647 instances of reach at roughly 1% accuracy, which by the closure
identity is very nearly pure damage, and in any coverage-based measure it would
have looked like the biggest advance the project had made.

So the probe runs first. Point any candidate generator at the gold originals,
apply what it proposes, and ask what the gold actually did there:

* **attested**  the edited wording appears in the gold
* **declined**  the original wording appears in the gold, untouched
* **rewritten or dropped**  neither, so this candidate cannot settle anything

The ratio to read is attested against declined. "Rewritten or dropped" is the
majority class everywhere, because Opus is usually doing something larger to the
sentence, and counting it either way would answer a different question.

**Anchor on the left.** The first version of this test did not, and it is wrong
without it: the reduced form is usually a *suffix* of the original, so a gold
that kept "that is socially organised" contains "socially organised" and scores
as attested for a reduction it never made. Prefixing a few words of untouched
context makes the two readings mutually exclusive, which is the whole point.
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
    examples: dict = field(default_factory=lambda: {})

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
