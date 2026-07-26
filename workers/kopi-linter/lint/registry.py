"""The rule registry.

A rule is any callable ``propose(doc) -> Iterable[Edit]``. It reads the parse and
returns proposals with character offsets into ``doc.text``; it never mutates
anything and never decides whether its proposal survives. That decision belongs
to :mod:`lint.select`, which is what keeps the output independent of the order
rules were registered in.

Rules are listed explicitly rather than discovered by import scanning, so the
active set is readable in one place and a half-written rule cannot join the
pipeline by existing.

**A rule that raises is a bug, not an event to absorb.** An earlier version of
this module caught every exception and continued, and a broken rule then looked
exactly like a rule with nothing to propose: the whole rule silently stopped
firing and the linter went on reporting success. Failures are now recorded and
surfaced by the caller, and a run with no working rules is an error.
"""
from rules import rule_relative

# Active rules. A rule joins this tuple only once `manage.py evaluate` shows it
# agreeing with the gold editor; it leaves again when it stops.
RULES = (
    ("relative", rule_relative.propose),
)

# Withdrawn, kept for the record and for a later attempt.
#
# ``rule_support_verb`` collapses "conduct an analysis of X" into "analyse X".
# The transformation is real, but the corpus does not support firing it: the
# base rate at which the gold editor resolves a light-verb construction away is
# about 20%, and after calibrating each construction's confidence to its own
# observed rate (`manage.py induce`) the rule fired twice across 1,523
# paragraphs and disagreed with the gold editor both times. Two things would
# have to change before it returns: a discriminator that separates the
# compositional cases from the idioms, and more evidence per construction than
# the handful of observations available now.
_WITHDRAWN = ("rules.rule_support_verb",)


def propose_all(doc, rules=None) -> tuple[list, list]:
    """Every proposal from every registered rule, plus any rule that failed.

    Args:
        doc: a parsed spaCy document.
        rules: ``(name, propose)`` pairs to run instead of :data:`RULES`. The
            experiment layer passes a single candidate method here so a method
            can be scored on its own rather than through whatever else is
            currently registered.

    Returns:
        ``(edits, failures)`` where ``failures`` is a list of
        ``(rule name, exception)``. One malformed parse should cost that rule its
        proposals for this paragraph, not fail the document, but the caller has
        to be told rather than left to infer silence.
    """
    edits, failures = [], []
    for name, rule in (RULES if rules is None else rules):
        try:
            edits.extend(rule(doc))
        except Exception as error:
            failures.append((name, error))
    return edits, failures
