"""Propose collapsing a light-verb construction (`make use of the data` to
`use the data`) when the nominalisation governs a promotable object. The
verb comes from WordNet via `grammar.orthography`.
"""
from grammar.orthography import to_american, to_british
from lint.edit import Edit

# Verbs that contribute almost no meaning of their own in this construction.
# Genuinely a closed class, unlike the open-ended noun side.
_LIGHT_VERBS = frozenset([
    "make",
    "take",
    "give",
    "have",
    "do",
    "conduct",
    "perform",
    "provide",
    "offer",
    "undertake",
    "carry",
    "engage",
    "reach",
    "hold",
    "place",
    "put",
])

_PROMOTING_PREPS = frozenset(["of", "to", "on", "for", "with", "into"])

# Modifiers that carry meaning of their own. A collapse rewrites the whole span
# from the light verb to the noun, so any of these would be destroyed with it.
# That is not a tidy-up, it is content loss, and in the worst case a reversal:
# "offers only limited understanding of" became "understands" before this gate
# existed, which asserts the opposite of the original.
_CONTENT_MODIFIERS = frozenset(["amod", "compound", "nummod", "advmod", "neg"])


def _derived_verb(noun_lemma: str) -> str | None:
    """The verb a nominalisation was built from, in British spelling."""
    from nltk.corpus import wordnet

    american = to_american(noun_lemma).lower()
    candidates = set()
    for synset in wordnet.synsets(american, pos="n"):
        for lemma in synset.lemmas():
            if lemma.name().lower() != american:
                continue
            candidates.update(
                related.name().lower() for related in lemma.derivationally_related_forms()
                if related.synset().pos() == "v"
            )
    if not candidates:
        return None
    return to_british(sorted(candidates, key=lambda w: (abs(len(w) - len(american)), w))[0])


def _inflect(lemma: str, tag: str) -> str:  # lint-style: ignore FN004
    """Put the derived verb into the light verb's tense and person."""
    from lemminflect import getInflection

    forms = getInflection(to_american(lemma), tag=tag)
    return to_british(forms[0]) if forms else lemma


def _promotes_object(token, noun) -> bool:
    if token.lemma_.lower() not in _PROMOTING_PREPS or token.i != noun.i + 1:
        return False
    return any(child.dep_ == "pobj" for child in token.children)


def _object_preposition(verb, noun):
    """The preposition handing the real object on, wherever the parser hung it.

    "make use **of** X" attaches the preposition under the noun, but "give
    consideration **to** X" attaches it under the verb as a dative. Both are the
    same construction, so the test is adjacency to the nominalisation rather than
    which head the parser chose.
    """
    for candidate in list(noun.children) + list(verb.children):
        if _promotes_object(candidate, noun):
            return candidate
    return None


def _nominalisation_object(verb):  # lint-style: ignore FN004
    for child in verb.children:
        if child.dep_ == "dobj" and child.pos_ == "NOUN":
            return child
    return None


def _carries_modifiers(noun) -> bool:
    return any(child.dep_ in _CONTENT_MODIFIERS for child in noun.children)


def _confidence(verb, noun) -> float:
    """How often the gold editor actually resolved this construction away.

    Taken straight from the induced table rather than asserted. The base rate
    across all light-verb constructions in the corpus is about 20%, so a rule
    that fired on every match at a high confidence would be wrong four times in
    five; only the constructions the evidence supports can clear a band.
    """
    from rules.induced_support_verbs import COLLAPSE_RATE

    rate, _ = COLLAPSE_RATE.get(f"{verb.lemma_.lower()} {noun.lemma_.lower()}", (0.0, 0))
    return rate


def _proposal(verb, noun, preposition, text: str) -> Edit | None:
    derived = _derived_verb(noun.lemma_)
    if derived is None or derived == verb.lemma_.lower():
        return None
    end = (preposition.idx + len(preposition.text)) if preposition is not None else \
        (noun.idx + len(noun.text))
    if end <= verb.idx:
        return None
    replacement = _inflect(derived, verb.tag_)
    if verb.text[:1].isupper():
        replacement = replacement.capitalize()
    return Edit(
        start=verb.idx, end=end, replacement=replacement,
        rule="support-verb.collapse", family="support-verb",
        confidence=_confidence(verb, noun),
        note=f"light verb collapsed: '{text[verb.idx:end]}' -> '{replacement}'",
    )


def propose(doc):
    """A collapse for every licensed light-verb construction in ``doc``."""
    text = doc.text
    edits = []
    for verb in doc:
        if verb.pos_ not in ("VERB", "AUX") or verb.lemma_.lower() not in _LIGHT_VERBS:
            continue
        noun = _nominalisation_object(verb)
        if noun is None or _carries_modifiers(noun):
            continue
        edit = _proposal(verb, noun, _object_preposition(verb, noun), text)
        if edit is not None:
            edits.append(edit)
    return edits
