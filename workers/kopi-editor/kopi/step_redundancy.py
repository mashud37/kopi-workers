"""Flag sentences that restate an earlier point, and short sentences that
could merge, using IDF-weighted lemma overlap and marginal-novelty ranking
over the document's sentences. It flags only, never removes text.
"""
import math

from kopi.quote_guard import unguard

_MIN_WORDS = 8
_SIMILARITY_THRESHOLD = 0.85
_CONTENT_OVERLAP_THRESHOLD = 0.40
_MERGE_MAX_WORDS = 25
_MERGE_STARTERS = frozenset([
    "this",
    "it",
    "and",
    "also",
    "moreover",
    "furthermore",
    "in addition",
    "additionally",
    "similarly",
    "likewise",
])
_CONTENT_POS = frozenset(["NOUN", "VERB", "ADJ"])


def _build_idf(lemma_sets: list[set]) -> dict:
    """Smoothed inverse document frequency per lemma over the given sentences.

    Uses the sklearn-style smoothed form ``ln((n+1)/(df+1)) + 1`` so every weight
    is strictly positive and a term appearing in every sentence still contributes
    a little. Deterministic given the input.
    """
    n = len(lemma_sets)
    df: dict = {}
    for lemmas in lemma_sets:
        for lemma in lemmas:
            df[lemma] = df.get(lemma, 0) + 1
    return {lemma: math.log((n + 1) / (count + 1)) + 1.0 for lemma, count in df.items()}


def _weighted_overlap(a: set, b: set, idf: dict) -> float:
    """IDF-weighted overlap of two content-lemma sets, in [0, 1].

    Numerator is the IDF mass shared by both sentences; denominator is the
    smaller sentence's total IDF mass (the containment form, so a short sentence
    fully echoed inside a long one still scores ~1). Distinctive shared terms
    dominate; generic shared terms barely register.
    """
    shared = a & b
    if not shared:
        return 0.0
    num = sum(idf.get(lemma, 1.0) for lemma in shared)
    mass_a = sum(idf.get(lemma, 1.0) for lemma in a)
    mass_b = sum(idf.get(lemma, 1.0) for lemma in b)
    denom = min(mass_a, mass_b)
    return num / denom if denom > 0 else 0.0


def _select_redundant(sentences, content_lemmas, sim_matrix, idf, thresholds: dict = None) -> list[dict]:
    """Greedy marginal-novelty pass over sentences in document order.

    A sentence is flagged when its strongest similarity to an already-kept
    sentence clears the similarity threshold *and* the two share enough distinctive
    (IDF-weighted) content. The earlier sentence is kept as the anchor; the later
    one is returned as the removable restatement. Pure function: no spaCy or
    model, so the routing logic is unit-testable.
    """
    if thresholds is None:
        thresholds = {"similarity": _SIMILARITY_THRESHOLD, "overlap": _CONTENT_OVERLAP_THRESHOLD}
    sim_threshold = thresholds["similarity"]
    overlap_threshold = thresholds["overlap"]
    pairs = []
    kept: list[int] = []
    for i in range(len(sentences)):
        best_j, best_sim = None, 0.0
        for j in kept:
            sim = float(sim_matrix[i][j])
            if sim > best_sim:
                best_sim, best_j = sim, j
        if best_j is not None and best_sim >= sim_threshold:
            overlap = _weighted_overlap(content_lemmas[i], content_lemmas[best_j], idf)
            if overlap >= overlap_threshold:
                pairs.append({
                    "keep": sentences[best_j],
                    "remove": sentences[i],
                    "similarity": best_sim,
                    "savings": len(sentences[i].split()),
                    "marginal_novelty": round(1.0 - best_sim, 3),
                    "overlap": round(overlap, 3),
                })
                continue
        kept.append(i)
    return pairs


def _is_merge_candidate(s1: str, s2: str) -> bool:
    w2 = s2.split()
    if len(s1.split()) > _MERGE_MAX_WORDS or len(w2) > _MERGE_MAX_WORDS:
        return False
    return w2[0].lower() in _MERGE_STARTERS or (len(w2) > 1 and f"{w2[0].lower()} {w2[1].lower()}" in _MERGE_STARTERS)


def _load_redundancy_model() -> dict:
    """Import spaCy plus sentence-transformers and load the parser.

    Raises ImportError if a package is missing, OSError if the spaCy model
    could not be downloaded; the caller tells the two apart.
    """
    import numpy as np
    from sentence_transformers import SentenceTransformer

    from kopi.language_model import load_english
    nlp = load_english()
    return {"nlp": nlp, "SentenceTransformer": SentenceTransformer, "np": np}


def _build_sentence_data(doc) -> dict:
    # Parse once: keep the spans so content lemmas come straight off this parse
    # rather than re-running spaCy per candidate pair.
    sent_spans = [s for s in doc.sents if len(s.text.split()) >= _MIN_WORDS]
    sentences = [s.text.strip() for s in sent_spans]
    content_lemmas = []
    for span in sent_spans:
        lemmas = set()
        for token in span:
            if token.pos_ in _CONTENT_POS and not token.is_stop:
                lemmas.add(token.lemma_.lower())
        content_lemmas.append(lemmas)
    idf = _build_idf(content_lemmas)
    return {"sentences": sentences, "content_lemmas": content_lemmas, "idf": idf}


def _compute_similarity(sentence_data: dict, sentence_transformer_class, np_module) -> dict:
    # Semantic similarity (preferred) needs the MiniLM embedding model. If it
    # isn't cached and can't be fetched (offline / never downloaded), fall back
    # to a purely lexical similarity built from the IDF-weighted content overlap
    # we already have: degraded, but the run never crashes on a missing model.
    sentences = sentence_data["sentences"]
    content_lemmas = sentence_data["content_lemmas"]
    idf = sentence_data["idf"]
    try:
        model = sentence_transformer_class("all-MiniLM-L6-v2", local_files_only=True)
        embeddings = model.encode(sentences, show_progress_bar=False)
        norms = np_module.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / np_module.maximum(norms, 1e-10)
        sim_matrix = embeddings @ embeddings.T
        return {"sim_matrix": sim_matrix, "mode": "semantic"}
    except Exception:
        n = len(sentences)
        sim_matrix = []
        for i in range(n):
            row = []
            for j in range(n):
                row.append(_weighted_overlap(content_lemmas[i], content_lemmas[j], idf))
            sim_matrix.append(row)
        return {"sim_matrix": sim_matrix, "mode": "lexical"}


def _find_merge_candidates(doc) -> list:
    merge_candidates = []
    all_sents = [s.text.strip() for s in doc.sents if s.text.strip()]
    for i in range(len(all_sents) - 1):
        s1, s2 = all_sents[i], all_sents[i + 1]
        if _is_merge_candidate(s1, s2):
            merge_candidates.append({"s1": s1, "s2": s2})
    return merge_candidates


def run(state: dict) -> dict:
    try:
        deps = _load_redundancy_model()
    except ImportError as e:
        state["log"].append({
            "step": "Step 5: Redundancy scan",
            "detail": f"skipped, missing dependency: {e}",
            "para": None,
        })
        return {**state, "redundant_pairs": [], "merge_candidates": []}
    except OSError:
        state["log"].append({
            "step": "Step 5: Redundancy scan",
            "detail": "skipped, spaCy's English model could not be downloaded",
            "para": None,
        })
        return {**state, "redundant_pairs": [], "merge_candidates": []}

    restored = unguard(state["text"], state["qmap"])
    doc = deps["nlp"](restored)
    sentence_data = _build_sentence_data(doc)
    sentences = sentence_data["sentences"]

    if len(sentences) < 2:
        state["log"].append({
            "step": "Step 5: Redundancy scan",
            "detail": "too few sentences to compare",
            "para": None,
        })
        return {**state, "redundant_pairs": [], "merge_candidates": []}

    similarity = _compute_similarity(sentence_data, deps["SentenceTransformer"], deps["np"])
    pairs = _select_redundant(
        sentences, sentence_data["content_lemmas"], similarity["sim_matrix"], sentence_data["idf"]
    )
    merge_candidates = _find_merge_candidates(doc)

    total_savings = sum(p["savings"] for p in pairs)
    state = {**state, "redundant_pairs": pairs, "merge_candidates": merge_candidates}
    state["counts"]["step5_estimate"] = total_savings
    state["log"].append({
        "step": "Step 5: Redundancy scan",
        "detail": (
            f"{len(pairs)} redundant sentence(s) (~{total_savings} words), "
            f"{len(merge_candidates)} merge candidate(s)"
            + ("" if similarity["mode"] == "semantic" else " [lexical fallback: embedding model unavailable]")
        ),
        "para": None,
        "items": [
            f"similarity {p['similarity']:.2f}: remove '{p['remove'][:70]}' (~{p['savings']} words)"
            for p in pairs
        ],
    })
    return state
