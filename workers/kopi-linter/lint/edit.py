"""The unit of work: one proposed change to one span of text.

A rule never edits. It *proposes*, and proposals compete: two rules will often
want the same words, and a rule that is right in isolation can be wrong once the
band, the word budget, or a neighbouring edit is taken into account. Keeping
proposal separate from application is what lets the engine reason about the set
of changes rather than apply them in whatever order the rules happened to run,
and it is what makes the result independent of rule order.

Every edit carries the taxonomy family it belongs to (see ``docs/typology.md``),
so band gating and per-family reporting work without the rules knowing about
either.
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
    """
    start: int
    end: int
    replacement: str
    rule: str
    family: str
    confidence: float
    note: str

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
