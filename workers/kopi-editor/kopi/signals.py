"""Per-sentence and per-paragraph compressibility scoring + routing.

Produces an estimated number of removable words ("est_savings") for each
sentence and paragraph, derived from cheap features of the spaCy dependency
parse. Used to (a) prioritise which paragraphs to send to the LLM and
(b) give the LLM a per-paragraph word budget and a focus hint.

On top of that it builds a composite **fat-index** per paragraph — a weighted
blend of est_savings and several register-wordiness signals (length, sentence
length, parse depth, inverse readability, and optional proselint/intensifier
densities). Paragraphs are then flagged target-driven: enough of the fattest
paragraphs to cover the requested word reduction, with a safety margin.

Normalisation is **rank-based** (each signal mapped to [0, 1] by the fraction
of paragraphs scoring strictly lower). This is robust to outliers, makes no
distributional assumptions, and is fully deterministic — the same document and
target always produce the same flagged set.

This module only reads the parse — it never mutates text.
"""

# --- Composite fat-index configuration -------------------------------------

# Minimum paragraph length to be eligible for LLM tightening / routing.
_MIN_PARA_WORDS = 40

# Component weights for the composite fat-index. Uniform to start; exposed so
# the user can re-weight after inspecting `python calibrate.py`. Optional
# components (the two densities) are simply skipped — and the active weights
# renormalised — when their per-paragraph data is absent or misaligned.
FAT_WEIGHTS = {
    "est_savings": 1.0,
    "words": 1.0,
    "mean_sent_len": 1.0,
    "mean_dep_depth": 1.0,
    "inv_flesch": 1.0,
    "proselint_density": 1.0,
    "intensifier_density": 1.0,
}

# Fraction of a paragraph the LLM is assumed to cut, used to project how many
# paragraphs are needed to hit the target. Calibrate against real runs.
EXPECTED_COMPRESSION = 0.25
# Over-select by this factor so rejected/under-cut edits still hit target.
SAFETY = 1.3
# Never flag more than this fraction of editable paragraphs (avoid rewriting
# the whole document).
MAX_SELECT_FRACTION = 0.60

_SUBORD_DEPS = frozenset(["relcl", "acl", "advcl", "ccomp", "xcomp", "csubj", "csubjpass"])
_PASSIVE_DEPS = frozenset(["nsubjpass", "auxpass", "csubjpass"])
_NOMINAL_SUFFIXES = ("tion", "sion", "ment", "ity", "ness", "ance", "ence", "ism")

# Below this length a sentence is left alone — short sentences carry no fat.
_MIN_SENT_WORDS = 8
# Hard ceiling on the fraction of a sentence we believe is removable.
# Mirrors step_concision._MAX_COMPRESSION so estimates stay realistic.
_MAX_RATIO = 0.35
_BASE_RATIO = 0.05


def _tree_depth(token) -> int:
    d, cur = 0, token
    while cur.head is not cur:
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


def _inv_flesch(text: str):
    """100 - Flesch reading ease, clipped at 0 (higher = harder = fatter).

    Returns None if textstat is unavailable, so the component drops out cleanly.
    """
    try:
        import textstat
        return max(0.0, 100.0 - textstat.flesch_reading_ease(text))
    except Exception:
        return None


def _is_quote_para(para: str) -> bool:
    """A paragraph that is wholly a (block) quotation — never edited."""
    s = para.strip()
    if not s:
        return True
    if s.startswith(">"):  # markdown block quote (unguarded block quotation)
        return True
    if len(s) >= 2 and s[0] in "\"'“‘«" and s[-1] in "\"'”’»":
        # Whole paragraph wrapped in quotation marks with no other quote breaks.
        return '"' not in s[1:-1] and "”" not in s[1:-1]
    return False


def analyze_paragraphs(paragraphs: list[str], nlp) -> list[dict]:
    """Score every paragraph. Returns one dict per paragraph, in document order.

    Each entry: index, words, est_savings, focus (wordiest sentence snippets),
    the composite-index component signals (mean_sent_len, mean_dep_depth,
    inv_flesch), an is_quote flag, and the underlying per-sentence feature dicts.
    """
    results = []
    for index, (doc, para) in enumerate(zip(nlp.pipe(paragraphs), paragraphs)):
        sents = [sentence_features(s) for s in doc.sents if s.text.strip()]
        para_words = len(para.split())
        est = sum(s["est_savings"] for s in sents)
        focus = [
            s["text"][:90]
            for s in sorted(sents, key=lambda s: -s["est_savings"])[:2]
            if s["est_savings"] > 0
        ]
        n_sents = len(sents)
        mean_sent_len = sum(s["words"] for s in sents) / n_sents if n_sents else 0.0
        mean_dep_depth = sum(s["max_depth"] for s in sents) / n_sents if n_sents else 0.0
        results.append({
            "index": index,
            "words": para_words,
            "est_savings": round(est, 1),
            "mean_sent_len": round(mean_sent_len, 2),
            "mean_dep_depth": round(mean_dep_depth, 2),
            "inv_flesch": _inv_flesch(para),
            "is_quote": _is_quote_para(para),
            "focus": focus,
            "sentences": sents,
        })
    return results


def _rank_normalize(values: list[float]) -> list[float]:
    """Map values to [0, 1] by the fraction of values strictly lower than each.

    Ties share a score; the minimum maps to 0. Deterministic given the input.
    """
    n = len(values)
    if n <= 1:
        return [0.0] * n
    denom = n - 1
    return [sum(1 for v in values if v < x) / denom for x in values]


def paragraph_fat_index(analysis: list[dict], state: dict | None = None) -> dict:
    """Composite wordiness score per eligible paragraph -> {index: fat_score}.

    Eligible = at least ``_MIN_PARA_WORDS`` words and not a quotation. Each
    component signal is rank-normalised across the eligible paragraphs, then
    combined as a weight-normalised sum. Optional density components are only
    included when ``state`` carries per-paragraph hit arrays aligned to the
    paragraph split.
    """
    eligible = [
        a for a in analysis
        if a["words"] >= _MIN_PARA_WORDS and not a.get("is_quote")
    ]
    if not eligible:
        return {}

    n_paras = len(analysis)
    state = state or {}

    def _density(key: str):
        hits = state.get(key)
        if not isinstance(hits, list) or len(hits) != n_paras:
            return None
        return [hits[a["index"]] / max(1, a["words"]) for a in eligible]

    # Build the raw column for each component (None => component absent).
    columns = {
        "est_savings": [a["est_savings"] for a in eligible],
        "words": [a["words"] for a in eligible],
        "mean_sent_len": [a["mean_sent_len"] for a in eligible],
        "mean_dep_depth": [a["mean_dep_depth"] for a in eligible],
        "inv_flesch": None
        if any(a["inv_flesch"] is None for a in eligible)
        else [a["inv_flesch"] for a in eligible],
        "proselint_density": _density("proselint_para_hits"),
        "intensifier_density": _density("intensifier_para_hits"),
    }

    active = {k: v for k, v in columns.items() if v is not None and FAT_WEIGHTS.get(k, 0)}
    total_weight = sum(FAT_WEIGHTS[k] for k in active)
    if total_weight <= 0:
        return {a["index"]: 0.0 for a in eligible}

    normed = {k: _rank_normalize(v) for k, v in active.items()}
    scores = {}
    for row, a in enumerate(eligible):
        score = sum(FAT_WEIGHTS[k] * normed[k][row] for k in active) / total_weight
        scores[a["index"]] = round(score, 4)
    return scores


def select_by_target(fat_map: dict, analysis: list[dict], reduction: int) -> list[int]:
    """Flag the fattest paragraphs needed to cover ``reduction`` words.

    Walks paragraphs by descending fat-index (index as a deterministic
    tiebreak), projecting ``words * EXPECTED_COMPRESSION`` removable each, until
    the projected total reaches ``reduction * SAFETY`` — capped at
    ``MAX_SELECT_FRACTION`` of eligible paragraphs. Returns indices in **document
    order** so cross-reference logic is preserved.
    """
    if not fat_map:
        return []
    words_by_index = {a["index"]: a["words"] for a in analysis}
    ranked = sorted(fat_map, key=lambda i: (-fat_map[i], i))
    max_select = max(1, int(MAX_SELECT_FRACTION * len(fat_map)))
    needed = max(0, reduction) * SAFETY

    selected = []
    projected = 0.0
    for idx in ranked:
        if len(selected) >= max_select:
            break
        selected.append(idx)
        projected += words_by_index.get(idx, 0) * EXPECTED_COMPRESSION
        if needed and projected >= needed:
            break
    return sorted(selected)
