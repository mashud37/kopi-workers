"""Citation detection and casing repair, shared by the editor guard and the serving
layer. Pure stdlib so the featherweight `/tighten` proxy can import it without pulling
numpy/torch.

Small models lowercase an author surname mid-sentence — '(Hallinan & Striphas 2016)'
comes back as '(Hallinan & striphas 2016)'. The citation is otherwise intact, so the
acceptance guard's exact-match rejection is a false negative on a trivial, mechanical
error. `restore_casing` repairs it deterministically: any citation whose case-folded
form matches one in the original is rewritten to the original's exact casing.
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
    return CITATION_RE.sub(lambda m: canon.get(m.group(0).lower(), m.group(0)), edited)
