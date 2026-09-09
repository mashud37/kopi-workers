"""Propose deleting a word when the fitted keep-or-delete model is confident
enough, so the licence is decided for this token rather than for its category.
"""
from dataclasses import dataclass
from functools import lru_cache

from lint.edit import Edit

FAMILY = "tagged"

# Only keeps proposals no band would ever admit out of the changelog. The band's
# own threshold is what decides which of these fire, which is the whole point:
# the model returns a probability, so the dial already exists.
_FLOOR = 0.5

# What makes a preposition complete. The surviving governor is found by part of
# speech and not by dependency, because a coordinated preposition ("and in
# relation to") is labelled `conj` and a dependency test walks straight past it.
_PREP_COMPLEMENTS = frozenset([
    "pobj",
    "pcomp",
    "prep",
    "advmod",
])

# Words that modify a noun from in front of it and cannot stand where it stood.
_ATTACHED = frozenset([
    "det",
    "poss",
    "amod",
    "compound",
    "nummod",
])

# What a verb needs in order to keep standing once the words beside it go.
_SUPPORTING = frozenset([
    "aux",
    "auxpass",
    "expl",
    "nsubj",
    "nsubjpass",
    "csubj",
    "csubjpass",
])

# What a verb governs and cannot be left without.
_GOVERNED = frozenset([
    "dobj",
    "dative",
    "attr",
    "oprd",
])

_VERBAL = frozenset([
    "VERB",
    "AUX",
])

# Holding one word back changes what the rest of the run leaves behind, so the
# priors are asked again. Three passes settles every run in the corpus; the
# bound is here so that a prior which keeps finding offenders stops rather than
# runs on.
_TRIM_PASSES = 3


@dataclass(frozen=True)
class Gates:
    """Which shape priors to enforce. Defaults are the shipped rule.

    A confident word is not a deletable word: the model scores each token on its
    own, so nothing in it knows that the token it likes is the only verb in its
    sentence. Every prior below was written from a measured defect rather than
    from intuition, and each names one word the run may not take.

    Attributes:
        keep_the_root: hold back a word that is its own sentence's root, which is
            what leaves a sentence with no predicate.
        keep_prepositions_complete: hold back a complement whose preposition
            survives and would be left governing nothing.
        keep_modifiers_attached: hold back a noun whose determiner or adjective
            survives and would be left standing on its own.
        keep_verbs_supported: hold back an auxiliary or a subject whose verb
            survives, which is what leaves "might enabling" or no subject at all.
        keep_verbs_complete: hold back an object whose verb survives, which is
            what leaves "provided to articulate relationships".
        trim_refused_runs: delete what is left of a run once the held-back words
            are taken out. With this off the whole run is dropped instead, which
            costs every deletion that merely stood next to an offender.
    """
    keep_the_root: bool = True
    keep_prepositions_complete: bool = True
    keep_modifiers_attached: bool = True
    keep_verbs_supported: bool = True
    keep_verbs_complete: bool = True
    trim_refused_runs: bool = True


DEFAULT = Gates()


@lru_cache(maxsize=1)
def _fitted() -> dict:  # lint-style: ignore FN004
    from tagging import weights

    return {"intercept": weights.INTERCEPT, "weights": weights.WEIGHT}


def _wanted(doc, fitted: dict) -> list:
    """Every word the model scores at or above the floor, in document order.

    Punctuation is left alone. Spacing and stops belong to the repair layer, and
    a rule that proposes deleting a full stop is asking the guard to catch it.
    """
    from tagging import features, model

    out = []
    for token in doc:
        if token.is_space or token.is_punct:
            continue
        score = model.score(features.of(token), fitted)
        if score >= _FLOOR:
            out.append({"token": token, "score": score})
    return out


def _runs(wanted: list) -> list:
    """Neighbouring wanted words grouped into one span each.

    Adjacent deletions are one edit rather than several, so the changelog reads
    as a phrase removed and selection weighs the whole cut instead of its words.
    """
    runs = []
    for item in wanted:
        if runs and item["token"].i == runs[-1][-1]["token"].i + 1:
            runs[-1].append(item)
        else:
            runs.append([item])
    return runs


def _next_index(doc, start: int) -> int | None:
    """Where the next token that is not whitespace sits."""
    for index in range(start + 1, len(doc)):
        if not doc[index].is_space:
            return index
    return None


def _opens_sentence(run: list) -> bool:
    """Whether nothing but punctuation stands between the run and its sentence start."""
    first = run[0]["token"]
    for token in first.sent:
        if token.i >= first.i:
            return True
        if not token.is_punct and not token.is_space:
            return False
    return True


def _end_of(doc, run: list) -> int:
    """Character offset the deletion runs to.

    Ends at the next word rather than at the last deleted character, so the space
    the run would leave behind goes with it. A run that opens its sentence takes
    a following comma too, which would otherwise be stranded against the full
    stop in front of it.
    """
    last = run[-1]["token"].i
    following = _next_index(doc, last)
    if following is not None and doc[following].text == "," and _opens_sentence(run):
        last = following
        following = _next_index(doc, last)
    if following is not None:
        return doc[following].idx
    return doc[last].idx + len(doc[last].text)


def _edit_for(doc, run: list) -> Edit:
    """One deletion covering a run, confident only as its least confident word."""
    start = run[0]["token"].idx
    end = _end_of(doc, run)
    confidence = min(item["score"] for item in run)
    return Edit(
        start=start, end=end, replacement="",
        rule="tagged.delete", family=FAMILY, confidence=confidence,
        note=f"tagged for deletion: '{doc.text[start:end].strip()}' removed",
    )


def _inside(run: list) -> set:
    """Indices of every word the run would delete."""
    return {item["token"].i for item in run}


def _the_root(run: list) -> set:
    """The run's own sentence root, where the run holds it.

    Compared by index rather than by identity, because spaCy builds a fresh
    ``Token`` object on every access and two of them are never the same object.
    """
    held = set()
    for item in run:
        token = item["token"]
        if token.i == token.sent.root.i:
            held.add(token.i)
    return held


def _still_complete(preposition, inside: set) -> bool:
    """Whether a preposition keeps a complement once the run is gone."""
    for child in preposition.children:
        if child.dep_ in _PREP_COMPLEMENTS and child.i not in inside:
            return True
    return False


def _last_complements(run: list) -> set:
    """Complements whose surviving preposition would be left governing nothing."""
    inside = _inside(run)
    held = set()
    for item in run:
        token = item["token"]
        head = token.head
        if token.dep_ not in _PREP_COMPLEMENTS or head.pos_ != "ADP":
            continue
        if head.i not in inside and not _still_complete(head, inside):
            held.add(token.i)
    return held


def _modified_words(run: list) -> set:
    """Words a surviving determiner or adjective would be left attached to."""
    inside = _inside(run)
    held = set()
    for item in run:
        token = item["token"]
        for child in token.children:
            if child.dep_ in _ATTACHED and child.i not in inside:
                held.add(token.i)
    return held


def _verb_support(run: list) -> set:
    """Auxiliaries and subjects whose own verb survives the run."""
    inside = _inside(run)
    held = set()
    for item in run:
        token = item["token"]
        if token.dep_ not in _SUPPORTING:
            continue
        if token.head.i not in inside and token.head.pos_ in _VERBAL:
            held.add(token.i)
    return held


def _verb_objects(run: list) -> set:
    """Objects and complements whose own verb survives the run."""
    inside = _inside(run)
    held = set()
    for item in run:
        token = item["token"]
        if token.dep_ not in _GOVERNED:
            continue
        if token.head.i not in inside and token.head.pos_ in _VERBAL:
            held.add(token.i)
    return held


def _held_back(run: list, gates: Gates) -> set:
    """Every word in the run that an enabled shape prior refuses to delete."""
    held = set()
    if gates.keep_the_root:
        held |= _the_root(run)
    if gates.keep_prepositions_complete:
        held |= _last_complements(run)
    if gates.keep_modifiers_attached:
        held |= _modified_words(run)
    if gates.keep_verbs_supported:
        held |= _verb_support(run)
    if gates.keep_verbs_complete:
        held |= _verb_objects(run)
    return held


def _without(run: list, held: set) -> list:
    """The run's surviving words, regrouped into neighbouring spans."""
    pieces = []
    current = []
    for item in run:
        if item["token"].i in held:
            if current:
                pieces.append(current)
                current = []
        else:
            current.append(item)
    if current:
        pieces.append(current)
    return pieces


def _trimmed(run: list, gates: Gates) -> list:
    """What is left of a run once the words the priors hold back are taken out.

    Holding a word back changes what the words beside it leave behind, so each
    piece is put to the priors again until none of them objects.
    """
    pieces = [run]
    for _ in range(_TRIM_PASSES):
        kept = []
        for piece in pieces:
            held = _held_back(piece, gates)
            kept.extend(_without(piece, held))
        if kept == pieces:
            return pieces
        pieces = kept
    return pieces


def _admitted(run: list, gates: Gates) -> list:
    """The spans of this run that may be deleted."""
    if gates.trim_refused_runs:
        return _trimmed(run, gates)
    if _held_back(run, gates):
        return []
    return [run]


def propose(doc, gates: Gates = DEFAULT):
    """One deletion for every run of words the fitted model wants gone."""
    fitted = _fitted()
    if not fitted["weights"]:
        return []
    wanted = _wanted(doc, fitted)
    edits = []
    for run in _runs(wanted):
        for piece in _admitted(run, gates):
            edits.append(_edit_for(doc, piece))
    return edits
