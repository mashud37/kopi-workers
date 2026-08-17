"""Find citations like `(Author, Year)` and restore original casing an LLM
lowercased mid-sentence, matching case-folded forms against the source text.
Pure stdlib so the lightweight `/tighten` proxy can import it.
"""
import re

CITATION_RE = re.compile(
    r"\("
    r"(?:[A-Z][\w-]+(?:\s+(?:and|&|et\s+al\.?))?\s*[A-Z]?[\w-]*,?\s*)?"
    r"(?:\d{4}[a-z]?|199X|202X|REF)"
    r"(?:,\s*pp?\.?\s*\d+(?:[-–]\d+)?)?"
    r"\)",
    re.IGNORECASE,
)


def find(text: str) -> list[str]:
    return CITATION_RE.findall(text)


def restore_casing(original: str, edited: str) -> str:
    """Rewrite every citation in `edited` whose case-folded form matches one in
    `original` back to the original's exact casing; leave genuinely new or altered
    citations untouched so the guard still catches a real change."""
    canon = {c.lower(): c for c in find(original)}
    if not canon:
        return edited
    pieces = []
    last_end = 0
    for match in CITATION_RE.finditer(edited):
        pieces.append(edited[last_end:match.start()])
        pieces.append(canon.get(match.group(0).lower(), match.group(0)))
        last_end = match.end()
    pieces.append(edited[last_end:])
    return "".join(pieces)
