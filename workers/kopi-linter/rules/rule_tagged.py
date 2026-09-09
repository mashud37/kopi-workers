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

# What makes a preposition complete, taken from `eval.grammatical` so the gate
# below refuses exactly the shape the defect detector counts.
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


@dataclass(frozen=True)
class Gates:
    """Which shape priors to enforce. Defaults are the shipped rule.

    A confident word is not a deletable word: the model scores each token on its
    own, so nothing in it knows that the token it likes is the only verb in its
    sentence. Both gates below were written from measured defects rather than
    from intuition, and each refuses the whole run rather than trimming it,
    which is the conservative reading and costs some good deletions.

    Attributes:
        keep_the_root: refuse a run that takes its own sentence's root with it,
            which is what leaves a sentence with no predicate.
        keep_prepositions_complete: refuse a run that removes a preposition's
            last complement while the preposition itself survives.
        keep_modifiers_attached: refuse a run that deletes a noun and leaves the
            determiner or adjective that belonged to it standing on its own.
    """
    keep_the_root: bool = True
    keep_prepositions_complete: bool = True
    keep_modifiers_attached: bool = True


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


def _takes_the_root(run: list) -> bool:
    """Whether the run would delete the root of its own sentence.

    Compared by index rather than by identity, because spaCy builds a fresh
    ``Token`` object on every access and two of them are never the same object.
    """
    for item in run:
        token = item["token"]
        if token.i == token.sent.root.i:
            return True
    return False


def _still_complete(preposition, inside: set) -> bool:
    """Whether a preposition keeps a complement once the run is gone."""
    for child in preposition.children:
        if child.dep_ in _PREP_COMPLEMENTS and child.i not in inside:
            return True
    return False


def _strands_a_preposition(run: list) -> bool:
    """Whether the run leaves a surviving preposition with nothing to govern."""
    inside = set()
    for item in run:
        inside.add(item["token"].i)
    for item in run:
        token = item["token"]
        head = token.head
        if token.dep_ not in _PREP_COMPLEMENTS or head.dep_ != "prep":
            continue
        if head.i not in inside and not _still_complete(head, inside):
            return True
    return False


def _orphans_a_modifier(run: list) -> bool:
    """Whether the run deletes a word and leaves something that only modified it."""
    inside = set()
    for item in run:
        inside.add(item["token"].i)
    for item in run:
        for child in item["token"].children:
            if child.dep_ in _ATTACHED and child.i not in inside:
                return True
    return False


def _refused_by(run: list, gates: Gates) -> bool:
    """Whether any shape prior the gates enable refuses this run."""
    if gates.keep_the_root and _takes_the_root(run):
        return True
    if gates.keep_prepositions_complete and _strands_a_preposition(run):
        return True
    return gates.keep_modifiers_attached and _orphans_a_modifier(run)


def propose(doc, gates: Gates = DEFAULT):
    """One deletion for every run of words the fitted model wants gone."""
    fitted = _fitted()
    if not fitted["weights"]:
        return []
    wanted = _wanted(doc, fitted)
    edits = []
    for run in _runs(wanted):
        if _refused_by(run, gates):
            continue
        edits.append(_edit_for(doc, run))
    return edits
