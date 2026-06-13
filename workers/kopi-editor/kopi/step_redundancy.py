"""Step 5 — Redundancy scan.

Flags sentences that restate a point already made (so the author can cut the
restatement) and short follow-on sentences that can be merged.

Two IR ideas shape the redundancy test (see 00_policies/cs_ir_stats_reference.md):

* **IDF-weighted overlap.** Two sentences only count as redundant when they
  share *distinctive* content terms, not just common ones. Each shared lemma is
  weighted by its inverse document frequency over the document's own sentences
  (§4.2 / §6.2), so an overlap of "central methodological claim" weighs far more
  than an overlap of generic nouns.
* **Marginal novelty (MMR).** Sentences are walked in document order; one is
  flagged when it adds no novelty over the set already kept — i.e. its maximum
  similarity to an earlier retained sentence clears the threshold (§6 diversity
  / §7.6). The earlier sentence introduces the point and is kept; the later
  restatement is flagged for the author.

This step only flags — no sentence is removed here. Removal stays with the LLM
(Step 10), which sees full paragraph context.
"""
import math

from kopi.quote_guard import unguard

_MIN_WORDS = 8
_SIMILARITY_THRESHOLD = 0.85
_CONTENT_OVERLAP_THRESHOLD = 0.40
_MERGE_MAX_WORDS = 25
_MERGE_STARTERS = frozenset([
    "this", "it", "and", "also", "moreover", "furthermore",
    "in addition", "additionally", "similarly", "likewise",
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


def _select_redundant(sentences, content_lemmas, sim_matrix, idf,
                      sim_threshold=_SIMILARITY_THRESHOLD,
                      overlap_threshold=_CONTENT_OVERLAP_THRESHOLD) -> list[dict]:
    """Greedy marginal-novelty pass over sentences in document order.

    A sentence is flagged when its strongest similarity to an already-kept
    sentence clears ``sim_threshold`` *and* the two share enough distinctive
    (IDF-weighted) content. The earlier sentence is kept as the anchor; the later
    one is returned as the removable restatement. Pure function — no spaCy or
    model — so the routing logic is unit-testable.
    """
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


def run(state: dict) -> dict:
    try:
        import spacy
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError as e:
        state["log"].append({
            "step": "Step 5 — Redundancy scan",
            "detail": f"skipped — missing dependency: {e}",
            "para": None,
        })
        state["redundant_pairs"] = []
        state["merge_candidates"] = []
        return state

    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        state["log"].append({
            "step": "Step 5 — Redundancy scan",
            "detail": "skipped — run: python -m spacy download en_core_web_sm",
            "para": None,
        })
        state["redundant_pairs"] = []
        state["merge_candidates"] = []
        return state

    restored = unguard(state["text"], state["qmap"])
    doc = nlp(restored)

    # Parse once: keep the spans so content lemmas come straight off this parse
    # rather than re-running spaCy per candidate pair.
    sent_spans = [s for s in doc.sents if len(s.text.split()) >= _MIN_WORDS]
    sentences = [s.text.strip() for s in sent_spans]

    if len(sentences) < 2:
        state["redundant_pairs"] = []
        state["merge_candidates"] = []
        state["log"].append({
            "step": "Step 5 — Redundancy scan",
            "detail": "too few sentences to compare",
            "para": None,
        })
        return state

    content_lemmas = [
        {t.lemma_.lower() for t in span if t.pos_ in _CONTENT_POS and not t.is_stop}
        for span in sent_spans
    ]
    idf = _build_idf(content_lemmas)

    # Semantic similarity (preferred) needs the MiniLM embedding model. If it
    # isn't cached and can't be fetched (offline / never downloaded), fall back
    # to a purely lexical similarity built from the IDF-weighted content overlap
    # we already have — degraded, but the run never crashes on a missing model.
    mode = "semantic"
    try:
        model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        embeddings = model.encode(sentences, show_progress_bar=False)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / np.maximum(norms, 1e-10)
        sim_matrix = embeddings @ embeddings.T
    except Exception:
        mode = "lexical"
        n = len(sentences)
        sim_matrix = [
            [_weighted_overlap(content_lemmas[i], content_lemmas[j], idf) for j in range(n)]
            for i in range(n)
        ]

    pairs = _select_redundant(sentences, content_lemmas, sim_matrix, idf)

    merge_candidates = []
    all_sents = [s.text.strip() for s in doc.sents if s.text.strip()]
    for i in range(len(all_sents) - 1):
        s1, s2 = all_sents[i], all_sents[i + 1]
        if _is_merge_candidate(s1, s2):
            merge_candidates.append({"s1": s1, "s2": s2})

    total_savings = sum(p["savings"] for p in pairs)
    state["redundant_pairs"] = pairs
    state["merge_candidates"] = merge_candidates
    state["counts"]["step5_estimate"] = total_savings
    state["log"].append({
        "step": "Step 5 — Redundancy scan",
        "detail": (
            f"{len(pairs)} redundant sentence(s) (~{total_savings} words), "
            f"{len(merge_candidates)} merge candidate(s)"
            + ("" if mode == "semantic" else " [lexical fallback — embedding model unavailable]")
        ),
        "para": None,
        "items": [
            f"similarity {p['similarity']:.2f}: remove '{p['remove'][:70]}' (~{p['savings']} words)"
            for p in pairs
        ],
    })
    return state
