"""Probe-only rule that reduces a lexical-verb relative clause to a participle
(`which revolve around time` to `revolving around time`), kept reproducible via
`manage.py probe` but registered nowhere else.
"""
from lemminflect import getInflection

from lint.edit import Edit
from rules.rule_relative import _RELATIVISER_TAGS, _SUBJECT_DEPS, _in_cleft

_FINITE = frozenset(["VBZ", "VBP", "VBD"])


def _subject_relativiser(clause):
    """The relative pronoun standing as the clause's subject, if it has one."""
    for child in clause.children:
        if child.tag_ in _RELATIVISER_TAGS and child.dep_ in _SUBJECT_DEPS:
            return child
    return None


def propose(doc):
    """A participle rewrite for every finite lexical relative clause."""
    edits = []
    for clause in doc:
        if clause.dep_ != "relcl" or clause.tag_ not in _FINITE:
            continue
        if clause.lemma_.lower() == "be" or _in_cleft(clause):
            continue
        relativiser = _subject_relativiser(clause)
        if relativiser is None or clause.idx <= relativiser.idx:
            continue
        participle = getInflection(clause.lemma_, tag="VBG")
        if not participle:
            continue
        edits.append(Edit(
            start=relativiser.idx, end=clause.idx + len(clause.text),
            replacement=participle[0], rule="relative.lexical",
            family="relative-clause-lexical", confidence=0.5,
            note=f"lexical relative reduced: '{relativiser.text} {clause.text}' "
                 f"to '{participle[0]}'",
        ))
    return edits
