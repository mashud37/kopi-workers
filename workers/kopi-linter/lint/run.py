"""Run the six-stage pipeline (parse, propose, select, apply, realise,
guard) over a paragraph or document. Nothing applies until every proposal is
seen, so the output never depends on rule order.
"""
from dataclasses import dataclass, field

from lint import edit as edit_mod
from lint import guard, registry, select
from lint.edit import apply_edits


@dataclass
class LintResult:
    original: str
    edited: str
    applied: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    reason: str | None = None
    failures: list = field(default_factory=list)

    @property
    def words_saved(self) -> int:
        return len(self.original.split()) - len(self.edited.split())

    @property
    def changed(self) -> bool:
        return self.edited.strip() != self.original.strip()


def lint_paragraph(text: str, nlp, band, rules=None) -> LintResult:
    """Lint one paragraph at the given intensity band.

    Args:
        text: the paragraph, as one line.
        nlp: a loaded spaCy pipeline.
        band: a :class:`lint.bands.Band`.
        rules: ``(name, propose)`` pairs to use instead of the registered set.
            The experiment layer uses this to score one candidate method in
            isolation.

    Returns:
        A :class:`LintResult`. When the guard rejects the outcome the original
        is returned unchanged with ``reason`` set, so a failed lint is always a
        no-op rather than a partial edit.
    """
    from grammar.realise import repair

    doc = nlp(text)
    offered = registry.propose_all(doc, rules)
    proposals, failures = offered["edits"], offered["failures"]
    protected = guard.quoted_spans(text)
    rejected = [(e, "inside a quotation") for e in proposals
                if guard.touches_quote(e, protected)]
    eligible = [e for e in proposals if not guard.touches_quote(e, protected)]
    rejected += [(e, f"below the {band.name} threshold for {e.family}")
                 for e in eligible if not band.admits(e)]
    chosen = select.select(eligible, text, band)
    rejected += [(e, "lost to an overlapping edit or the word budget")
                 for e in eligible if band.admits(e) and e not in chosen]

    # Repair is scoped to the joins the edits created, so a paragraph nothing
    # fired on comes back byte-identical. Quoted spans are re-found on the
    # spliced text rather than reused: applying edits shifts every later offset.
    spliced = apply_edits(text, chosen)
    edited = repair(spliced, edit_mod.spliced_spans(chosen), guard.quoted_spans(spliced))
    failure = guard.check(text, edited, band)
    if failure:
        return LintResult(original=text, edited=text, applied=[],
                          rejected=rejected + [(e, failure) for e in chosen],
                          reason=failure, failures=failures)
    return LintResult(original=text, edited=edited, applied=chosen,
                      rejected=rejected, failures=failures)


def lint_document(paragraphs: list[str], nlp, band, on_progress=None) -> list[LintResult]:
    """Lint each paragraph independently, reporting progress per paragraph."""
    results = []
    total = len(paragraphs)
    for i, paragraph in enumerate(paragraphs, 1):
        if on_progress:
            on_progress(i, total, paragraph)
        results.append(lint_paragraph(paragraph, nlp, band))
    return results
