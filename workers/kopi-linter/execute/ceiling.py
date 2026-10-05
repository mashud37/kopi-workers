"""Induce a closed edit vocabulary from the training documents and rebuild
each gold target using only the tags it licenses, which is the ceiling an edit
tagger could reach.
"""
import difflib
from collections import Counter
from functools import lru_cache

from eval.closure import distance

_MINIMUM_SIGHTINGS = 2


def _opcodes(source: list, target: list) -> list:
    """The edit script between two word lists, compared without case."""
    matcher = difflib.SequenceMatcher(
        a=[word.lower() for word in source],
        b=[word.lower() for word in target],
        autojunk=False,
    )
    return matcher.get_opcodes()


def _written_pieces(source: list, target: list) -> list:
    """Every stretch of target words this edit had to write rather than keep."""
    pieces = []
    for op, _, _, j1, j2 in _opcodes(source, target):
        if op in ("insert", "replace"):
            pieces.append(" ".join(target[j1:j2]).lower())
    return pieces


def prepare(context: dict) -> dict:
    """Count what the training documents wrote, and keep the repeated pieces.

    Args:
        context: ``{"tasks": [...]}``, every task in the corpus. Only the tasks
            from training documents are counted, so the vocabulary is never read
            off the held-out side.

    Returns:
        ``{"phrases": set, "counts": Counter}``, the set being the closed
        vocabulary a tagger would be allowed to write from.
    """
    counts = Counter()
    for task in context["tasks"]:
        if task["held_out"]:
            continue
        for piece in _written_pieces(task["source"].split(), task["target"].split()):
            counts[piece] += 1
    phrases = {piece for piece, seen in counts.items() if seen >= _MINIMUM_SIGHTINGS}
    return {"phrases": phrases, "counts": counts}


@lru_cache(maxsize=100_000)
def _lemmas(word: str) -> frozenset:
    """Every lemma the word could be an inflected form of, under any part of speech."""
    from lemminflect import getAllLemmas

    found = {word}
    for forms in getAllLemmas(word).values():
        found.update(form.lower() for form in forms)
    return frozenset(found)


def _is_form_change(source: list, target: list) -> bool:
    """Whether one word simply changed form, sharing a lemma with the other.

    Stands in for the inflection tags an edit tagger carries alongside its
    vocabulary (verb form, noun number, capitalisation), which are generated
    rather than looked up and so cost the vocabulary nothing. Testing for a
    shared lemma rather than a shared stem matters: a stem test also admits
    "analysis" against "analytical", which is a different word an edit tagger
    would have to hold in its vocabulary like any other.
    """
    if len(source) != 1 or len(target) != 1:
        return False
    first, second = source[0].lower(), target[0].lower()
    if first == second:
        return True
    return bool(_lemmas(first) & _lemmas(second))


def _writable(source: list, target: list, state: dict) -> bool:
    """Whether a form change or the induced vocabulary can produce this stretch."""
    if _is_form_change(source, target):
        return True
    return " ".join(target).lower() in state["phrases"]


def _fallback(source: list, target: list) -> list:
    """What a tagger writes where its vocabulary cannot spell the target.

    Keeping and deleting are both always available to a tagger, so a ceiling
    gets whichever of the two lands nearer what Opus wrote. Falling back to
    keeping alone understates it badly, because most of these stretches are
    compressions and dropping them is closer than leaving them.
    """
    if distance(source, target) <= len(target):
        return list(source)
    return []


def execute(task: dict, state: dict) -> str:
    """Rebuild Opus's target, falling back wherever the vocabulary cannot spell it.

    This backend reads the gold, which no other one does. It answers a ceiling
    question and not a system question: if a tagger chose every tag correctly,
    how much of what Opus wrote could its closed vocabulary spell at all?
    """
    source = task["source"].split()
    target = task["target"].split()
    out = []
    for op, i1, i2, j1, j2 in _opcodes(source, target):
        if op == "equal":
            out.extend(source[i1:i2])
        elif op == "delete":
            continue
        elif _writable(source[i1:i2], target[j1:j2], state):
            out.extend(target[j1:j2])
        else:
            out.extend(_fallback(source[i1:i2], target[j1:j2]))
    return " ".join(out)
