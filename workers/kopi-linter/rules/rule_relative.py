"""Relative clause reduction, the classic "whiz-deletion".

"the data which were collected over several months" becomes "the data collected
over several months". The evidence puts this family at 5.3 words saved per
instance, the highest of any span family, on a transformation that changes no
content at all: the relativiser and the copula carry no meaning the rest of the
clause does not already carry.

It is only safe when the relativiser is the *subject* of the relative clause.
"the data which we collected" must stay, because deleting "which" there strands
the object. The parse gives that distinction directly, so the rule is gated on
it rather than on a surface pattern.

The four licensed shapes, and what makes each safe:

* past participle, "which were collected" -> "collected"
* present participle, "who are studying" -> "studying"
* prepositional phrase, "which is on the table" -> "on the table"
* adjective *with a complement*, "who are eager to learn" -> "eager to learn"

Every gate here is a claim about what would break without it, and every such
claim is testable by turning the gate off. :class:`Gates` exists so that the
experiment layer can do exactly that, rather than leaving the gates asserted in
a docstring. See ``docs/good.md`` section 3.1 for the cases each one covers.
"""
from dataclasses import dataclass

from lint.edit import Edit

_RELATIVISER_TAGS = frozenset(["WDT", "WP"])
_SUBJECT_DEPS = frozenset(["nsubj", "nsubjpass"])
_CLEFT_DEPS = frozenset(["attr", "acomp"])

# Relations the cleft search may climb: all of them keep the walk inside one
# nominal. Anything else is a clause boundary and ends the search.
_NOMINAL_INTERNAL = frozenset(["pobj", "prep", "compound", "conj", "appos",
                               "poss", "amod", "nmod", "npadvmod", "acl", "pcomp"])
_CLEFT_SEARCH_DEPTH = 10

_PARTICIPLE = {"VBN": 0.92, "VBG": 0.88}


@dataclass(frozen=True)
class Gates:
    """Which licence conditions to enforce. Defaults are the shipped rule.

    Attributes:
        copula_only: refuse when the deleted span holds anything but forms of
            "be", which is what stops the rule eating modals and adverbs.
        subject_relativiser: refuse when the relativiser is not the clause
            subject, which is what stops it stranding an object.
        adjective_complement: refuse a bare predicate adjective, which cannot
            follow its noun.
        block_cleft: refuse when the head sits in an it-cleft, where the
            relativiser is the cleft pivot rather than a modifier.
    """
    copula_only: bool = True
    subject_relativiser: bool = True
    adjective_complement: bool = True
    block_cleft: bool = True


DEFAULT = Gates()


def _deletes_only_copula(doc, relativiser, target) -> bool:
    """Whether the span about to be deleted holds nothing but forms of "be".

    A reduction removes everything from the relativiser up to the surviving
    phrase, so anything else caught in between is destroyed with it. Two kinds of
    word live there and neither may go: a modal ("a resource that people **can**
    use creatively") and an adverb ("practices that are **increasingly**
    personalised"). Requiring the span to be copular auxiliaries only is what
    makes this a reduction rather than a deletion.
    """
    for token in doc[relativiser.i + 1:target.i]:
        if token.is_space or token.is_punct:
            continue
        if token.tag_ == "MD" or token.pos_ != "AUX" or token.lemma_.lower() != "be":
            return False
    return True


def _is_cleft_pivot(token) -> bool:
    return (token.dep_ in _CLEFT_DEPS and token.head.lemma_.lower() == "be"
            and any(child.dep_ == "nsubj" and child.lower_ == "it"
                    for child in token.head.children))


def _in_cleft(clause) -> bool:
    """Whether the relative clause is the second half of an it-cleft.

    "It is X that is key to my thesis" looks like a relative clause to the parser
    and is not one: "that is" is the cleft pivot, and deleting it leaves the
    sentence asserting nothing.

    The walk up the tree is the part that matters, and checking only the
    immediate head is what let the first version of this gate pass its own test
    case. A relative clause attaches to the nearest eligible noun, not to the
    cleft focus, so in the sentence above the clause hangs off "power" while the
    focus is "kinds" five hops higher. The walk climbs nominal-internal relations
    only and stops at the first clause boundary, so a relative clause genuinely
    inside a cleft focus is not mistaken for the pivot.
    """
    token = clause.head
    for _ in range(_CLEFT_SEARCH_DEPTH):
        if _is_cleft_pivot(token):
            return True
        if token.dep_ not in _NOMINAL_INTERNAL or token.head is token:
            return False
        token = token.head
    return False


def _relativiser(clause, gates: Gates):
    for child in clause.children:
        if child.tag_ not in _RELATIVISER_TAGS:
            continue
        if gates.subject_relativiser and child.dep_ not in _SUBJECT_DEPS:
            continue
        return child
    return None


def _copula(clause):
    for child in clause.children:
        if child.dep_ in ("aux", "auxpass") and child.lemma_.lower() == "be":
            return child
    return None


def _predicate_after_copula(clause, gates: Gates):
    """For a copular relative clause, the phrase that survives the reduction."""
    for child in clause.children:
        if child.dep_ == "prep":
            return child, 0.85
        if child.dep_ == "acomp" and child.pos_ == "ADJ":
            if not gates.adjective_complement or any(True for _ in child.rights):
                return child, 0.75
    return None, 0.0


def _make(text: str, relativiser, target, rule: str, confidence: float) -> Edit:
    return Edit(
        start=relativiser.idx, end=target.idx, replacement="",
        rule=rule, family="relative-clause", confidence=confidence,
        note=f"relative clause reduced: '{text[relativiser.idx:target.idx].strip()}' removed "
             f"before '{target.text}'",
    )


def _participle_edit(doc, clause, relativiser, text: str, gates: Gates) -> Edit | None:
    confidence = _PARTICIPLE.get(clause.tag_)
    if _copula(clause) is None or confidence is None or clause.idx <= relativiser.idx:
        return None
    if gates.copula_only and not _deletes_only_copula(doc, relativiser, clause):
        return None
    return _make(text, relativiser, clause, "relative.participle", confidence)


def _copular_edit(doc, clause, relativiser, text: str, gates: Gates) -> Edit | None:
    if clause.lemma_.lower() != "be":
        return None
    predicate, confidence = _predicate_after_copula(clause, gates)
    if predicate is None or predicate.idx <= relativiser.idx:
        return None
    if gates.copula_only and not _deletes_only_copula(doc, relativiser, predicate):
        return None
    return _make(text, relativiser, predicate, "relative.copular", confidence)


def propose(doc, gates: Gates = DEFAULT):
    """Yield a reduction for every safely reducible relative clause in ``doc``."""
    text = doc.text
    for clause in doc:
        if clause.dep_ != "relcl":
            continue
        if gates.block_cleft and _in_cleft(clause):
            continue
        relativiser = _relativiser(clause, gates)
        if relativiser is None:
            continue
        edit = _participle_edit(doc, clause, relativiser, text, gates) or \
            _copular_edit(doc, clause, relativiser, text, gates)
        if edit is not None:
            yield edit
