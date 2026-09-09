"""List every active rule explicitly, so a rule that raises is surfaced as
a bug rather than silently swallowed and mistaken for one with nothing to
propose.
"""
from rules import rule_relative, rule_tagged

# Active rules. A rule joins this tuple only once `manage.py evaluate` shows it
# agreeing with the gold editor; it leaves again when it stops.
RULES = (
    ("relative", rule_relative.propose),
    ("tagged", rule_tagged.propose),
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


def propose_all(doc, rules=None) -> dict:
    """Every proposal from every registered rule, plus any rule that failed.

    Args:
        doc: a parsed spaCy document.
        rules: ``(name, propose)`` pairs to run instead of :data:`RULES`. The
            experiment layer passes a single candidate method here so a method
            can be scored on its own rather than through whatever else is
            currently registered.

    Returns:
        Mapping with ``edits`` and ``failures``, the latter a list of
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
    return {"edits": edits, "failures": failures}
