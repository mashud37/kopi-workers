"""Repair surface damage (articles, agreement, punctuation) left at edit
joins after selection, since rule-by-rule repair gets the joins wrong. Runs
once over the paragraph, skipping quoted spans.
"""
import re

_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,;:!?)\]]|\.(?!\.))")
_SPACE_AFTER_OPEN = re.compile(r"([(\[])\s+")
_REPEATED_PUNCT = re.compile(r",\s*,+")
_ORPHANED_COMMA = re.compile(r"([(\[])\s*,\s*")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_APOSTROPHE = re.compile(r"\s+('s\b|n't\b|'re\b|'ve\b|'ll\b|'d\b|'m\b)")
_SENTENCE_START = re.compile(r"(^|(?<=[.!?])\s+|\n)([a-z])")
_MID_SENTENCE_START = re.compile(r"((?<=[.!?])\s+|\n)([a-z])")

# A full stop after one of these ends an abbreviation, not a sentence. Without
# this the repair pass capitalises the next word, which silently corrupts a
# citation: "cf. boyd, 2010" becomes "cf. Boyd, 2010" and the guard rightly
# rejects the whole paragraph. Genuinely a closed class, so listing it is safe.
_ABBREVIATIONS = frozenset([
    "cf",
    "eg",
    "e.g",
    "ie",
    "i.e",
    "etc",
    "al",
    "vs",
    "viz",
    "ibid",
    "op",
    "fig",
    "figs",
    "tab",
    "no",
    "vol",
    "vols",
    "ch",
    "chap",
    "pp",
    "p",
    "ed",
    "eds",
    "trans",
    "repr",
    "esp",
    "approx",
    "cca",
    "ca",
    "circa",
    "dr",
    "prof",
    "mr",
    "mrs",
    "ms",
    "st",
    "jr",
    "sr",
])
_ARTICLE = re.compile(r"\b([Aa]n?)\s+([A-Za-z][\w-]*)")

# Words whose spelling and pronunciation disagree about the article they take.
_VOWEL_SOUND_CONSONANT_SPELLING = ("hour", "honest", "honour", "heir")
_CONSONANT_SOUND_VOWEL_SPELLING = ("one", "once", "uni", "use", "user", "usu", "euro", "eu")

# How much context around a join the repair pass needs. An article sits one word
# before its noun and a sentence start one clause after, so a margin of a short
# clause each way covers what an edit can disturb without letting the pass roam.
_MARGIN = 80


def _takes_an(word: str) -> bool:
    """Whether ``word`` should be preceded by "an", judged by sound not spelling."""
    lower = word.lower()
    if lower.startswith(_VOWEL_SOUND_CONSONANT_SPELLING):
        return True
    if lower.startswith(_CONSONANT_SOUND_VOWEL_SPELLING):
        return False
    return lower[:1] in "aeiou"


def _fix_article(match: re.Match) -> str:
    article, word = match.group(1), match.group(2)
    correct = "an" if _takes_an(word) else "a"
    if article[:1].isupper():
        correct = correct.capitalize()
    return f"{correct} {word}"


_PRECEDING_WORD = re.compile(r"([A-Za-z.]+)\.\s*$")
_ELLIPSIS = re.compile(r"\.\s*\.[.\s]*$")

# "U.S.", "e.g.", "W.E.B." and friends: a dot inside the token means the final
# dot closes an initialism rather than a sentence. Cheaper and more general than
# extending the list, which cannot anticipate the initialisms in a given field.
_INITIALISM = re.compile(r"^(?:[A-Za-z]\.)+[A-Za-z]?$")


def _ends_sentence(text: str, position: int) -> bool:
    """Whether the full stop before ``position`` really closes a sentence.

    False for the three things that end in a dot without ending a sentence: a
    listed abbreviation, an initialism, and an ellipsis. Capitalising after any
    of them corrupts the text, and in a citation ("cf. boyd, 2010") or a
    quotation it corrupts a source.
    """
    before = text[:position]
    if _ELLIPSIS.search(before):
        return False
    preceding = _PRECEDING_WORD.search(before)
    if not preceding:
        return True
    word = preceding.group(1)
    return not (_INITIALISM.match(word) or word.lower().strip(".") in _ABBREVIATIONS)


def _capitalise_sentence_start(match: re.Match) -> str:
    if not _ends_sentence(match.string, match.start(2)):
        return match.group(0)
    return match.group(1) + match.group(2).upper()


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _subtract(spans, blocked) -> list[tuple[int, int]]:
    """The parts of ``spans`` not covered by ``blocked``."""
    out = []
    for start, end in spans:
        cursor = start
        for block_start, block_end in _merge(list(blocked)):
            if block_end <= cursor or block_start >= end:
                continue
            if block_start > cursor:
                out.append((cursor, block_start))
            cursor = max(cursor, block_end)
        if cursor < end:
            out.append((cursor, end))
    return out


def repair(text: str, windows=None, protected=()) -> str:
    """Normalise the surface of a paragraph around the edits spliced into it.

    Fixes the damage splicing leaves: doubled spaces and commas, a space stranded
    before punctuation or an enclitic, a lower-case letter left opening a
    sentence, and an article whose following word changed.

    Scope is the point. Repairing the whole paragraph makes the pass responsible
    for every sentence in the corpus rather than for the joins it created, and
    that is where its two observed corruptions came from: a capital inserted
    after "U.S." and after an ellipsis, both in paragraphs where no rule had
    fired at all. A paragraph with no edits is returned untouched.

    Args:
        text: the spliced paragraph.
        windows: character spans that edits landed on, from
            :func:`lint.edit.spliced_spans`. ``None`` repairs the whole
            paragraph, which is what standalone and case-checking callers want.
            An empty sequence repairs nothing.
        protected: spans to copy through verbatim, normally the quoted spans from
            :func:`lint.guard.quoted_spans`. Quotations are evidence, and
            normalising one silently edits a source.

    Returns:
        The repaired paragraph. Stripped only when the whole paragraph was in
        scope, since trimming a partial repair would move text the caller did
        not offer for editing.
    """
    if windows is None:
        scope = _subtract([(0, len(text))], protected)
        return _splice(text, scope).strip()
    if not windows:
        return text
    widened = _merge([(max(0, s - _MARGIN), min(len(text), e + _MARGIN)) for s, e in windows])
    return _splice(text, _subtract(widened, protected))


def _splice(text: str, scope: list[tuple[int, int]]) -> str:
    pieces, cursor = [], 0
    for start, end in scope:
        pieces.append(text[cursor:start])
        span = text[start:end]
        at_start = start == 0
        repaired = _REPEATED_PUNCT.sub(",", span)
        repaired = _ORPHANED_COMMA.sub(r"\1", repaired)
        repaired = _SPACE_BEFORE_APOSTROPHE.sub(r"\1", repaired)
        repaired = _SPACE_BEFORE_PUNCT.sub(r"\1", repaired)
        repaired = _SPACE_AFTER_OPEN.sub(r"\1", repaired)
        repaired = _MULTI_SPACE.sub(" ", repaired)
        repaired = _ARTICLE.sub(_fix_article, repaired)
        pattern = _SENTENCE_START if at_start else _MID_SENTENCE_START
        repaired = pattern.sub(_capitalise_sentence_start, repaired)
        pieces.append(repaired)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)
