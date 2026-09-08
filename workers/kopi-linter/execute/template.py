"""Perform the span edits plain code already reaches: dropping a span, and
correcting a spelling. Everything else is refused, which is the floor a
learned backend has to beat.
"""
from grammar import orthography


def prepare(context: dict) -> dict:
    """No state to fit; the signature is shared with every other backend."""
    return {}


def execute(task: dict, state: dict) -> str | None:
    """The replacement plain code can justify, or ``None`` when it cannot.

    Refusing is the honest answer almost everywhere. A template knows how to
    remove text and how to respell it, and it cannot know what an editor would
    have written instead, because that is the whole problem.
    """
    if task["op"] == "delete":
        return ""
    source = task["source"]
    if not source:
        return None
    spelled = orthography.britishise(source)
    return spelled if spelled != source else None
