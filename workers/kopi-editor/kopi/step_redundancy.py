from kopi.quote_guard import unguard

_MIN_WORDS = 8
_SIMILARITY_THRESHOLD = 0.85
_CONTENT_OVERLAP_THRESHOLD = 0.40
_MERGE_MAX_WORDS = 25
_MERGE_STARTERS = frozenset([
    "this", "it", "and", "also", "moreover", "furthermore",
    "in addition", "additionally", "similarly", "likewise",
])


def _content_overlap(s1: str, s2: str, nlp) -> float:
    """Fraction of content lemmas (nouns/verbs/adjectives) shared between two sentences."""
    lemmas1 = {t.lemma_ for t in nlp(s1) if t.pos_ in ("NOUN", "VERB", "ADJ") and not t.is_stop}
    lemmas2 = {t.lemma_ for t in nlp(s2) if t.pos_ in ("NOUN", "VERB", "ADJ") and not t.is_stop}
    if not lemmas1 or not lemmas2:
        return 0.0
    return len(lemmas1 & lemmas2) / min(len(lemmas1), len(lemmas2))


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
    sentences = [s.text.strip() for s in doc.sents if len(s.text.split()) >= _MIN_WORDS]

    if len(sentences) < 2:
        state["redundant_pairs"] = []
        state["merge_candidates"] = []
        state["log"].append({
            "step": "Step 5 — Redundancy scan",
            "detail": "too few sentences to compare",
            "para": None,
        })
        return state

    model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    embeddings = model.encode(sentences, show_progress_bar=False)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.maximum(norms, 1e-10)
    sim_matrix = embeddings @ embeddings.T

    pairs = []
    flagged = set()

    for i in range(len(sentences)):
        for j in range(i + 1, len(sentences)):
            if i in flagged or j in flagged:
                continue
            sim = float(sim_matrix[i, j])
            if sim >= _SIMILARITY_THRESHOLD:
                overlap = _content_overlap(sentences[i], sentences[j], nlp)
                if overlap < _CONTENT_OVERLAP_THRESHOLD:
                    continue
                remove_idx = j if len(sentences[i]) >= len(sentences[j]) else i
                keep_idx = i if remove_idx == j else j
                savings = len(sentences[remove_idx].split())
                pairs.append({
                    "keep": sentences[keep_idx],
                    "remove": sentences[remove_idx],
                    "similarity": sim,
                    "savings": savings,
                })
                flagged.add(remove_idx)

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
        ),
        "para": None,
        "items": [
            f"similarity {p['similarity']:.2f}: remove '{p['remove'][:70]}' (~{p['savings']} words)"
            for p in pairs
        ],
    })
    return state
