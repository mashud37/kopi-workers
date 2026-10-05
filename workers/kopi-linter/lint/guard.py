"""Check invariants a deterministic edit may never break: quotations
(blocked before selection), citations, numbers, and the band's cut ceiling.
A rule that fails one loses its edit, not the run.
"""
import re

_QUOTE = re.compile(r"[\"“‘«][^\"”’»]{0,600}[\"”’»]")
_CITATION = re.compile(r"\(([^()]{0,80}?\b(?:19|20)[0-9X]{2}[a-z]?)\)")
_NUMBER = re.compile(r"\b\d[\d.,]*\b")


def quoted_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _QUOTE.finditer(text)]


def touches_quote(edit, spans: list[tuple[int, int]]) -> bool:
    return any(start < edit.end and edit.start < end for start, end in spans)


def citations(text: str) -> set:
    return set(_CITATION.findall(text))


def numbers(text: str) -> list:
    return _NUMBER.findall(text)


def check(original: str, edited: str, band) -> str | None:
    """Reason the edited paragraph is unacceptable, or None if it passes."""
    if not edited.strip():
        return "empty result"
    if citations(original) != citations(edited):
        lost = citations(original) ^ citations(edited)
        return f"citation set changed: {sorted(lost)}"
    for number in numbers(original):
        if number not in edited:
            return f"number lost: {number}"
    kept = len(edited.split())
    floor = band.floor(len(original.split()))
    if kept < floor:
        return f"cut past the {band.name} ceiling ({kept} words, floor {floor})"
    return None
