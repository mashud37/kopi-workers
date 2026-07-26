"""Does the output still parse as English?

The invariant guard checks citations, numbers and length, and all four of its
checks passed on an output that had lost its main predicate. Truth preservation
does not imply grammaticality, so it needs its own check.

The check is differential, never absolute. Source prose legitimately contains
fragments: block quotations, reference-list entries, headings, elliptical
interview speech. Asking "is this well formed?" flags all of them. Asking "did
this edit *introduce* a defect the original did not have?" is the question that
distinguishes a broken rule from ordinary academic prose, and it is the only one
answered here.

Detectors are deliberately shallow and syntactic. A parse-based check inherits
the parser's mistakes, so a defect count is evidence rather than proof, and the
delta matters more than the absolute value.
"""
from collections import Counter

_VERBAL = frozenset(["VERB", "AUX"])
_NOMINAL = frozenset(["NOUN", "PROPN", "PRON"])
_PREP_COMPLEMENTS = frozenset(["pobj", "pcomp", "prep", "advmod"])


def _no_root_predicate(sent) -> bool:
    """A clause-length sentence whose root is not a verb has lost its predicate."""
    return len(sent) > 4 and sent.root.pos_ not in _VERBAL


def _dangling_prep(token) -> bool:
    return token.dep_ == "prep" and not any(
        child.dep_ in _PREP_COMPLEMENTS for child in token.children
    )


def _orphan_predicate(token) -> bool:
    """A predicate adjective or nominal hanging off a noun, with no copula left.

    This is the shape a reduction leaves when it deletes a copula that was
    carrying the sentence rather than introducing a modifier.
    """
    return token.dep_ in ("acomp", "attr") and token.head.pos_ in _NOMINAL


def _stranded_aux(token) -> bool:
    return token.dep_ in ("aux", "auxpass") and token.head.pos_ not in _VERBAL


_TOKEN_DEFECTS = (
    ("dangling_prep", _dangling_prep),
    ("orphan_predicate", _orphan_predicate),
    ("stranded_aux", _stranded_aux),
)


def defects(doc) -> Counter:
    """Count syntactic defects in a parsed document, by kind."""
    found = Counter()
    for sent in doc.sents:
        if _no_root_predicate(sent):
            found["no_root_predicate"] += 1
    for token in doc:
        for name, detector in _TOKEN_DEFECTS:
            if detector(token):
                found[name] += 1
    return found


def introduced(original: str, edited: str, nlp) -> Counter:
    """Defects present after the edit that were not present before.

    Returns:
        A Counter of defect kind to net increase. Empty when the edit introduced
        nothing, which is the passing case. Negative counts are dropped: an edit
        that repairs a pre-existing defect is not credited here.
    """
    if edited.strip() == original.strip():
        return Counter()
    before, after = defects(nlp(original)), defects(nlp(edited))
    net = Counter()
    for kind, count in after.items():
        gain = count - before.get(kind, 0)
        if gain > 0:
            net[kind] = gain
    return net
