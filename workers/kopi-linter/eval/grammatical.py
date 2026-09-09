"""Check whether an edit introduced a grammatical defect the original text
did not have, rather than whether the output is absolutely well formed.
Detectors are shallow and syntactic.
"""
from collections import Counter

_VERBAL = frozenset(["VERB", "AUX"])
_NOMINAL = frozenset(["NOUN", "PROPN", "PRON"])
_PREP_COMPLEMENTS = frozenset(["pobj", "pcomp", "prep", "advmod"])
_SUBJECTS = frozenset(["nsubj", "nsubjpass", "csubj", "csubjpass", "expl"])


def _no_root_predicate(sent) -> bool:
    """A clause-length sentence whose root is not a verb has lost its predicate."""
    return len(sent) > 4 and sent.root.pos_ not in _VERBAL


def _subjectless_verb(sent) -> bool:
    """A verb-rooted sentence with nothing standing as its subject.

    The shape left behind when a deletion takes an expletive or a subject noun
    and the verb it belonged to stays. Imperatives and fragments match it too,
    which is why it is only meaningful through :func:`introduced`.
    """
    if sent.root.pos_ not in _VERBAL:
        return False
    for child in sent.root.children:
        if child.dep_ in _SUBJECTS:
            return False
    return True


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


def _orphaned_determiner(token) -> bool:
    """A determiner the parser had to reread as a pronoun, which is what it does
    when the noun that determiner belonged to has been deleted.

    Keyed on the fine tag rather than on the dependency on purpose. Faced with
    "told me the in relation to", the parser does not leave a determiner without
    a noun; it relabels the word a pronoun and makes it the direct object, so
    every dependency-side test for this damage reads clean. The tag stays ``DT``.

    Demonstratives ("that", "these") are genuine pronouns and match this too, so
    the detector is only meaningful through :func:`introduced`, which subtracts
    what the original already had.
    """
    return token.tag_ == "DT" and token.pos_ == "PRON" and token.head.pos_ in _VERBAL


_TOKEN_DEFECTS = (
    ("dangling_prep", _dangling_prep),
    ("orphan_predicate", _orphan_predicate),
    ("stranded_aux", _stranded_aux),
    ("orphaned_determiner", _orphaned_determiner),
)


def defects(doc) -> Counter:
    """Count syntactic defects in a parsed document, by kind."""
    found = Counter()
    for sent in doc.sents:
        if _no_root_predicate(sent):
            found["no_root_predicate"] += 1
        if _subjectless_verb(sent):
            found["subjectless_verb"] += 1
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
