"""British and American spelling bridge, in both directions.

Every lexical resource the linter uses (WordNet, lemminflect) is American. The
prose is British. Without a bridge in both directions two things go wrong
silently: a British nominalisation returns no derivation at all
("anonymisation" has no WordNet entry), and a rule that does fire writes an
American form into a British text ("analyse" becomes "analyze").

kopi-editor's ``AMERICAN_TO_BRITISH`` table handles output for a curated word
list. It cannot handle lookup, and a fixed list cannot cover the coinages
academic prose invents ("problematisation", "operationalisation"). So the table
is used for the irregular cases and generative suffix rules cover the rest,
which is what makes an unseen word work.
"""
import re
import sys
from functools import lru_cache
from pathlib import Path

_EDITOR = Path(__file__).resolve().parents[2] / "kopi-editor"

# Suffix pairs that are fully regular in both directions. Order matters: the
# longer, more specific ending has to be tried before the shorter one that is a
# substring of it, or "isation" is mangled by the "ise" rule.
_SUFFIXES = [
    ("isations", "izations"), ("isation", "ization"),
    ("ising", "izing"), ("ised", "ized"), ("ises", "izes"), ("ise", "ize"),
    ("ysing", "yzing"), ("ysed", "yzed"), ("yses", "yzes"), ("yse", "yze"),
    ("ours", "ors"), ("our", "or"),
    ("tres", "ters"), ("tre", "ter"),
]

# Words ending in the same letters for unrelated reasons. Rewriting these would
# produce nonsense ("rise" -> "rize", "hour" -> "hor"), so they are held back.
_NEVER = frozenset([
    "rise", "rises", "rising", "wise", "wises", "advise", "advises", "advising",
    "revise", "revises", "revising", "devise", "devises", "devising",
    "supervise", "supervises", "supervising", "surprise", "surprises",
    "comprise", "comprises", "comprising", "promise", "promises", "promising",
    "exercise", "exercises", "exercising", "franchise", "franchises",
    "compromise", "compromises", "precise", "concise", "paradise", "expertise",
    "merchandise", "improvise", "improvises", "improvising", "demise",
    "hour", "hours", "flour", "sour", "tour", "tours", "pour", "four", "your",
    "detour", "velour", "contour", "contours", "glamour", "armour", "parlour",
    "acre", "acres", "genre", "genres", "cadre", "macabre", "mediocre", "ogre",
    "size", "sizes", "sized", "seize", "seizes", "prize", "prizes", "prized",
])


@lru_cache(maxsize=1)
def _table() -> dict:
    if not _EDITOR.exists():
        return {}
    if str(_EDITOR) not in sys.path:
        sys.path.insert(0, str(_EDITOR))
    try:
        from kopi.data_spelling import AMERICAN_TO_BRITISH
    except ImportError:
        return {}
    return dict(AMERICAN_TO_BRITISH)


@lru_cache(maxsize=1)
def _reverse_table() -> dict:
    return {british: american for american, british in _table().items()}


def _convert(word: str, index: int, other: int, table: dict) -> str:
    lower = word.lower()
    if lower in _NEVER:
        return word
    mapped = table.get(lower)
    if mapped:
        return _match_case(word, mapped)
    for pair in _SUFFIXES:
        source, target = pair[index], pair[other]
        if lower.endswith(source) and len(lower) > len(source) + 1:
            return _match_case(word, lower[: -len(source)] + target)
    return word


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement.capitalize()
    return replacement


def to_american(word: str) -> str:
    """British spelling to American, for looking a word up in WordNet."""
    return _convert(word, 0, 1, _reverse_table())


def to_british(word: str) -> str:
    """American spelling to British, for anything written back into the text."""
    return _convert(word, 1, 0, _table())


_WORD = re.compile(r"[A-Za-z]+")


def britishise(text: str) -> str:
    """Rewrite every American spelling in a stretch of text to its British form."""
    return _WORD.sub(lambda m: to_british(m.group(0)), text)
