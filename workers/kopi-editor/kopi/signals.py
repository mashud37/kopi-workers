"""Turn one spaCy sentence span into feature counts (length, subordination,
passive voice, parse depth, removable words) that `kopi.diagnose` uses to
pick paragraph instructions. Only reads the parse.
"""

_SUBORD_DEPS = frozenset(["relcl", "acl", "advcl", "ccomp", "xcomp", "csubj", "csubjpass"])
_PASSIVE_DEPS = frozenset(["nsubjpass", "auxpass", "csubjpass"])
_NOMINAL_SUFFIXES = ("tion", "sion", "ment", "ity", "ness", "ance", "ence", "ism")

# Below this length a sentence is left alone: short sentences carry no fat.
_MIN_SENT_WORDS = 8
# Hard ceiling on the fraction of a sentence we believe is removable.
_MAX_RATIO = 0.35
_BASE_RATIO = 0.05


def _tree_depth(token) -> int:
    # Bounded: a dependency tree is acyclic, but a malformed parse (rare, on
    # table dumps / symbol runs) could cycle and hang this walk forever.
    d, cur = 0, token
    while cur.head is not cur and d < 1000:
        cur = cur.head
        d += 1
    return d


def sentence_features(sent) -> dict:
    """Feature dict + estimated removable words for one spaCy sentence span."""
    content = [t for t in sent if not t.is_punct and not t.is_space]
    length = len(content)

    subord = sum(1 for t in sent if t.dep_ in _SUBORD_DEPS)
    passive = sum(1 for t in sent if t.dep_ in _PASSIVE_DEPS)
    commas = sum(1 for t in sent if t.text == ",")
    coord = sum(1 for t in sent if t.dep_ in ("cc", "conj"))
    preps = sum(1 for t in sent if t.dep_ == "prep")
    nominal = sum(
        1 for t in sent
        if t.pos_ == "NOUN" and t.lemma_.lower().endswith(_NOMINAL_SUFFIXES)
    )
    max_depth = max((_tree_depth(t) for t in sent), default=0)

    if length < _MIN_SENT_WORDS:
        est = 0.0
        ratio = 0.0
    else:
        # Raw complexity, normalised by length -> a per-word "density of fat".
        complexity = (
            1.0 * subord
            + 0.8 * passive
            + 0.7 * coord
            + 0.4 * commas
            + 0.3 * preps
            + 0.3 * nominal
            + 0.15 * max(0, max_depth - 4)
        )
        density = complexity / length
        ratio = min(_MAX_RATIO, _BASE_RATIO + 0.6 * density)
        est = length * ratio

    return {
        "text": sent.text.strip(),
        "words": length,
        "subord": subord,
        "passive": passive,
        "commas": commas,
        "coord": coord,
        "preps": preps,
        "nominal": nominal,
        "max_depth": max_depth,
        "ratio": round(ratio, 3),
        "est_savings": round(est, 1),
    }


def _is_quote_para(para: str) -> bool:
    """A paragraph that is wholly a (block) quotation, never edited."""
    s = para.strip()
    if not s:
        return True
    if s.startswith(">"):  # markdown block quote (unguarded block quotation)
        return True
    if len(s) >= 2 and s[0] in "\"'“‘«" and s[-1] in "\"'”’»":
        # Whole paragraph wrapped in quotation marks with no other quote breaks.
        return '"' not in s[1:-1] and "”" not in s[1:-1]
    return False
