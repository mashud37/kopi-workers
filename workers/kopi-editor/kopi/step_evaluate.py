import pathlib
import re

_SAMPLE_PATH = pathlib.Path(__file__).parent.parent / "data" / "revision_for_concision" / "sample.tsv"


def _load_pairs():
    if not _SAMPLE_PATH.exists():
        return []
    pairs = []
    with open(_SAMPLE_PATH, encoding="utf-8") as f:
        next(f)  # skip header
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 2:
                pairs.append((parts[0].strip(), parts[1].strip()))
    return pairs


def _ter(hypothesis, reference):
    h = hypothesis.lower().split()
    r = reference.lower().split()
    if not r:
        return 0.0
    m, n = len(h), len(r)
    d = list(range(n + 1))
    for i in range(1, m + 1):
        prev = d[:]
        d[0] = i
        for j in range(1, n + 1):
            if h[i - 1] == r[j - 1]:
                d[j] = prev[j - 1]
            else:
                d[j] = 1 + min(prev[j], d[j - 1], prev[j - 1])
    return d[n] / n


def _apply_fillers(text):
    try:
        from kopi.data_fillers import PHRASE_REPLACEMENTS
    except ImportError:
        return text
    for phrase, repl in sorted(PHRASE_REPLACEMENTS.items(), key=lambda x: -len(x[0])):
        pat = re.compile(r"\b" + re.escape(phrase) + r"\b\s*", re.IGNORECASE)
        rstr = (repl + " ") if repl else ""
        text = pat.sub(rstr, text)
    return re.sub(r" {2,}", " ", text).strip()


def _apply_relcl(text):
    try:
        from kopi.data_syntax_patterns import RELCL_PATTERN
        from kopi.step_syntax import _safe_adj, _fix_article
    except ImportError:
        return text

    def _replacer(m):
        art, noun, adj = m.group(1), m.group(2).lower(), m.group(3).lower()
        if not _safe_adj(adj):
            return m.group(0)
        new_art = _fix_article(art, adj) if art.lower() in ("a", "an") else art
        return f"{new_art} {adj} {noun}"

    return RELCL_PATTERN.sub(_replacer, text)


def _pipeline_sentence(text):
    text = _apply_fillers(text)
    text = _apply_relcl(text)
    return text


def _cosine_sim(s1, s2):
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        embs = model.encode([s1, s2], show_progress_bar=False)
        n = embs / (np.linalg.norm(embs, axis=1, keepdims=True) + 1e-10)
        return float(n[0] @ n[1])
    except Exception:
        return None


def run(state: dict) -> dict:
    if not state.get("evaluate"):
        return state

    pairs = _load_pairs()
    if not pairs:
        state["log"].append({
            "step": "Step 11 — Evaluate",
            "detail": f"sample not found at {_SAMPLE_PATH}",
            "para": None,
        })
        return state

    ter_scores = []
    sim_scores = []
    improvements = 0

    for wordy, reference in pairs:
        hypothesis = _pipeline_sentence(wordy)
        ter_scores.append(_ter(hypothesis, reference))
        if len(hypothesis.split()) < len(wordy.split()):
            improvements += 1

    sim_sample = pairs[:10]
    for wordy, reference in sim_sample:
        hypothesis = _pipeline_sentence(wordy)
        sim = _cosine_sim(hypothesis, reference)
        if sim is not None:
            sim_scores.append(sim)

    mean_ter = sum(ter_scores) / len(ter_scores) if ter_scores else 0.0
    mean_sim = sum(sim_scores) / len(sim_scores) if sim_scores else None
    n = len(pairs)

    detail = (
        f"{n} pairs | mean TER: {mean_ter:.3f} | "
        f"reductions: {improvements}/{n}"
    )
    if mean_sim is not None:
        detail += f" | mean cosine sim: {mean_sim:.3f}"

    state["eval_metrics"] = {
        "n": n, "mean_ter": mean_ter, "improvements": improvements,
        "mean_cosine_sim": mean_sim,
    }
    state["log"].append({
        "step": "Step 11 — Evaluate",
        "detail": detail,
        "para": None,
        "source": "Mu & Lim 2022",
    })
    return state
