"""Define `Edit`, one proposed change to a text span. Keeping proposal
separate from application lets the engine choose among conflicting edits so
the result never depends on rule order.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Edit:
    """One proposed replacement of ``text[start:end]``.

    Attributes:
        start: character offset into the paragraph, inclusive.
        end: character offset, exclusive. ``start == end`` is an insertion.
        replacement: what to put there. Empty string is a deletion.
        rule: the rule id that proposed it, for the changelog and for measuring
            per-rule precision later.
        family: taxonomy family, used for band gating.
        confidence: the rule's own estimate, in [0, 1]. Provisional until
            measured against the corpus.
        note: one human-readable line for the changelog.
        ranked: what ``confidence`` means. False, the default, is a probability
            that the edit is right, and the band compares it to a threshold.
            True is an *ordering* only, comparable between edits from the same
            rule and meaningless against a threshold, so the band admits the edit
            and lets the word budget decide how many survive.

    ``ranked`` belongs on the proposal rather than on the family, because the
    same family can be attacked both ways and the whole point of the experiment
    layer is to compare them. Keying it on the family instead silently converted
    every threshold model for that family into a budget model, and the comparison
    that was supposed to decide between the two architectures ran both of them as
    the same architecture.
    """
    start: int
    end: int
    replacement: str
    rule: str
    family: str
    confidence: float
    note: str
    ranked: bool = False

    def source(self, text: str) -> str:
        return text[self.start:self.end]

    def words_saved(self, text: str) -> int:
        return len(self.source(text).split()) - len(self.replacement.split())

    def weight(self, text: str) -> float:
        """Selection score: confident edits that save words win.

        The ``1 +`` keeps a zero-length saving from zeroing an edit out, since
        plain-language rewrites that save nothing still carry value.
        """
        return self.confidence * (1.0 + max(0, self.words_saved(text)))


def apply_edits(text: str, edits: list[Edit]) -> str:
    """Splice a set of non-overlapping edits into the text.

    Applied back to front so earlier offsets stay valid. Callers must pass a
    conflict-free set (see :mod:`lint.select`); overlapping edits here would
    corrupt the output silently.
    """
    out = text
    for edit in sorted(edits, key=lambda e: -e.start):
        out = out[:edit.start] + edit.replacement + out[edit.end:]
    return out


def spliced_spans(edits: list[Edit]) -> list[tuple[int, int]]:
    """Where each edit ends up in the text ``apply_edits`` returns.

    The repair layer needs this so it can work on the joins an edit actually
    created instead of on the whole paragraph. Offsets shift as earlier edits
    change length, so each span is displaced by the net length change of every
    edit before it.

    Returns:
        ``(start, end)`` per edit in source order, into the spliced text. A
        deletion yields an empty span at the join, which is the right thing to
        widen around.
    """
    spans, shift = [], 0
    for edit in sorted(edits, key=lambda e: e.start):
        start = edit.start + shift
        spans.append((start, start + len(edit.replacement)))
        shift += len(edit.replacement) - (edit.end - edit.start)
    return spans
