"""Probe-only: reduce a lexical-verb relative clause to a participle.

"which revolve around time" to "revolving around time". This is textbook
whiz-deletion, it is the largest single block of relative clauses in the corpus
at 647 candidates, and it is **not registered anywhere**, because C13 measured
what Opus does with it and the answer was 1.1%.

It lives here so that finding stays reproducible with ``manage.py probe`` rather
than resting on a script somebody deleted. Nothing imports it except the probe
registry, and nothing should: a generator this loose has no licence at all, and
building on it would add reach at an accuracy that subtracts closure.
"""
from lemminflect import getInflection

from lint.edit import Edit
from rules.rule_relative import _RELATIVISER_TAGS, _SUBJECT_DEPS, _in_cleft

_FINITE = frozenset(["VBZ", "VBP", "VBD"])


def propose(doc):
    """Yield a participle rewrite for every finite lexical relative clause."""
    for clause in doc:
        if clause.dep_ != "relcl" or clause.tag_ not in _FINITE:
            continue
        if clause.lemma_.lower() == "be" or _in_cleft(clause):
            continue
        relativiser = next((c for c in clause.children
                            if c.tag_ in _RELATIVISER_TAGS and c.dep_ in _SUBJECT_DEPS), None)
        if relativiser is None or clause.idx <= relativiser.idx:
            continue
        participle = getInflection(clause.lemma_, tag="VBG")
        if not participle:
            continue
        yield Edit(
            start=relativiser.idx, end=clause.idx + len(clause.text),
            replacement=participle[0], rule="relative.lexical",
            family="relative-clause-lexical", confidence=0.5,
            note=f"lexical relative reduced: '{relativiser.text} {clause.text}' "
                 f"to '{participle[0]}'",
        )
