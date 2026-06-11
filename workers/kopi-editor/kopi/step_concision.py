import os
import re
import json
import time
from pathlib import Path
import numpy as np
from kopi.quote_guard import guard, unguard, word_count

_CITATION_RE = re.compile(
    r"\("
    r"(?:[A-Z][\w-]+(?:\s+(?:and|&|et\s+al\.?))?\s*[A-Z]?[\w-]*,?\s*)?"
    r"(?:\d{4}[a-z]?|199X|202X|REF)"
    r"(?:,\s*pp?\.?\s*\d+(?:[-–]\d+)?)?"
    r"\)",
    re.IGNORECASE,
)
_MIN_PARA_WORDS = 40
_MAX_COMPRESSION = 0.40
_MIN_COSINE_SIM = 0.85

_embedding_model = None


def _get_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    return _embedding_model


def _cosine_sim(a: str, b: str) -> float:
    model = _get_model()
    embs = model.encode([a, b], show_progress_bar=False)
    na, nb = embs[0], embs[1]
    denom = np.linalg.norm(na) * np.linalg.norm(nb)
    return float(np.dot(na, nb) / denom) if denom > 1e-10 else 0.0


def _get_numerics(text: str) -> list:
    return re.findall(r"\b\d[\d.,]*\b", text)


def _get_citations(text: str) -> list:
    return _CITATION_RE.findall(text)


def _para_num(text: str, para: str) -> str:
    search = para.split("\n")[0].strip()[:60].lower()
    for i, p in enumerate(text.split("\n\n"), 1):
        if search in p.lower():
            return f"P{i}"
    return "P?"


def _accept_edit(original: str, edited: str) -> tuple[bool, str]:
    orig_words = len(original.split())
    edit_words = len(edited.split())

    if edit_words >= orig_words:
        return False, "not shorter"

    if edit_words < orig_words * (1 - _MAX_COMPRESSION):
        return False, f"over-compressed ({orig_words} -> {edit_words} words)"

    orig_cites = set(_get_citations(original))
    edit_cites = set(_get_citations(edited))
    if orig_cites != edit_cites:
        changed = orig_cites ^ edit_cites
        return False, f"citation set changed: {changed}"

    for num in _get_numerics(original):
        if num not in edited:
            return False, f"numeric lost: {num}"

    sim = _cosine_sim(original, edited)
    if sim < _MIN_COSINE_SIM:
        return False, f"meaning drift (cosine similarity {sim:.2f} < {_MIN_COSINE_SIM})"

    return True, "ok"


# Hard ceiling on paragraphs sent to the LLM in one pass (bounds cloud payload
# and latency), independent of the target-driven fraction cap in signals.
_MAX_CANDIDATES = 25

_nlp = None


def _load_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except Exception:
            _nlp = False
    return _nlp or None


def get_candidates(state: dict) -> list[dict]:
    """Flag paragraphs for LLM tightening by composite fat-index, target-driven.

    Each candidate carries ``budget`` (target words to cut), ``focus`` (the
    wordiest sentences), ``fat_index`` (normalised composite, for the prompt
    nudge + calibration) and ``routing_reason`` (why it was flagged). Only
    enough of the fattest paragraphs to cover the gap (with a safety margin)
    are returned. Paragraphs already edited in a prior pass are excluded so a
    second pass flags *new* paragraphs.
    """
    restored = unguard(state["text"], state["qmap"])
    paragraphs = restored.split("\n\n")
    already = set(state.get("llm_edited_indices", set()))
    nlp = _load_nlp()

    if nlp is None:
        # Fallback: rank by raw length when the parser is unavailable.
        candidates = [
            {"index": i, "text": para, "budget": None, "focus": [],
             "fat_index": None, "routing_reason": "length-ranked (no parser)"}
            for i, para in enumerate(paragraphs)
            if len(para.split()) >= _MIN_PARA_WORDS and i not in already
        ]
        candidates.sort(key=lambda c: len(c["text"].split()), reverse=True)
        return candidates[:_MAX_CANDIDATES]

    from kopi import signals
    analysis = signals.analyze_paragraphs(paragraphs, nlp)
    fat_map = signals.paragraph_fat_index(analysis, state)
    fat_map = {i: s for i, s in fat_map.items() if i not in already}
    if not fat_map:
        return []

    gap = max(0, len(restored.split()) - state.get("target", 0))
    selected_idx = signals.select_by_target(fat_map, analysis, gap)

    # Apply the hard ceiling by fat-index rank, then restore document order.
    if len(selected_idx) > _MAX_CANDIDATES:
        selected_idx = sorted(
            sorted(selected_idx, key=lambda i: (-fat_map[i], i))[:_MAX_CANDIDATES]
        )

    ranked = sorted(fat_map, key=lambda i: (-fat_map[i], i))
    rank_of = {idx: r + 1 for r, idx in enumerate(ranked)}
    total = len(fat_map)
    by_index = {a["index"]: a for a in analysis}

    candidates = []
    for idx in selected_idx:
        a = by_index[idx]
        candidates.append({
            "index": idx,
            "text": paragraphs[idx],
            "budget": int(round(a["est_savings"])),
            "focus": a["focus"],
            "fat_index": fat_map[idx],
            "routing_reason": f"fat-index {fat_map[idx]:.2f}, rank {rank_of[idx]}/{total}",
        })
    return candidates


# --- Calibration logging ---------------------------------------------------

def _calibration_path() -> Path:
    override = os.environ.get("KOPI_CALIBRATION_LOG")
    return Path(override) if override else Path.home() / ".kopi" / "calibration.jsonl"


def _log_calibration(records: list[dict]) -> None:
    """Append per-paragraph compression records as JSONL. Best-effort only."""
    if not records:
        return
    try:
        path = _calibration_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
    except Exception:
        pass  # never let calibration logging break the pipeline


def apply_results(state: dict, results: list[dict]) -> dict:
    """Apply LLM editing results (from local or cloud) to state."""
    restored = unguard(state["text"], state["qmap"])
    paragraphs = restored.split("\n\n")
    accepted = 0
    rejected = 0
    changelog = []
    calibration = []
    edited_indices = set(state.get("llm_edited_indices", set()))

    for result in results:
        idx = result["index"]
        if idx >= len(paragraphs):
            continue
        original = paragraphs[idx]
        edited = result.get("edited", original)
        orig_wc = len(original.split())
        edit_wc = len(edited.split())
        is_ok = bool(result.get("accepted"))
        calibration.append({
            "ts": time.time(),
            "index": idx,
            "input_wc": orig_wc,
            "output_wc": edit_wc,
            "compression_ratio": round((orig_wc - edit_wc) / orig_wc, 4) if orig_wc else 0.0,
            "accepted": is_ok,
            "reason": result.get("reason", "ok" if is_ok else "rejected"),
            "fat_index": result.get("fat_index"),
            "routing_reason": result.get("routing_reason"),
        })
        if is_ok:
            saved = orig_wc - edit_wc
            paragraphs[idx] = edited
            accepted += 1
            edited_indices.add(idx)
            changelog.append({
                "step": "Step 10 — Concision",
                "detail": f"accepted (~{saved} words saved) [{result.get('routing_reason', 'routed')}]",
                "para": f"P{idx + 1}",
                "items": [
                    f"original -> \"{original[:100]}{'...' if len(original) > 100 else ''}\"",
                    f"edited   -> \"{edited[:100]}{'...' if len(edited) > 100 else ''}\"",
                ],
            })
        else:
            rejected += 1

    restored = "\n\n".join(paragraphs)
    state["text"], state["qmap"] = guard(restored)
    state["llm_edited_indices"] = edited_indices
    final_count = word_count(state["text"], state["qmap"])
    state["counts"]["step10"] = final_count
    state["llm_stats"] = {"para": len(results), "accepted": accepted, "rejected": rejected}
    state["log"].append({
        "step": "Step 10 — Concision",
        "detail": f"{len(results)} paragraph(s) processed: {accepted} accepted, {rejected} rejected -> {final_count} words",
        "para": None,
    })
    state["log"].extend(changelog)
    _log_calibration(calibration)
    return state


def needs_second_pass(state: dict) -> bool:
    """True if the run is still short of target by more than 10% of the request.

    Compares the post-Step-10 count against target, relative to the originally
    requested reduction (counts['step1'] - target).
    """
    target = state.get("target", 0)
    current = state["counts"].get("step10")
    original = state["counts"].get("step1")
    if current is None or original is None:
        return False
    reduction = original - target
    if reduction <= 0:
        return False
    shortfall = current - target
    return shortfall > 0.10 * reduction


def run(state: dict) -> dict:

    current = word_count(state["text"], state["qmap"])
    target = state["target"]

    if current <= target:
        state["log"].append({
            "step": "Step 10 — Concision",
            "detail": f"target already met ({current} words)",
            "para": None,
        })
        return state

    try:
        from kopi.llm import edit_paragraph
        import ollama
        ollama.list()
    except ImportError:
        state["log"].append({
            "step": "Step 10 — Concision",
            "detail": "skipped — ollama package not installed",
            "para": None,
        })
        return state
    except Exception as e:
        state["log"].append({
            "step": "Step 10 — Concision",
            "detail": f"skipped — Ollama not running: {e}",
            "para": None,
        })
        return state

    restored = unguard(state["text"], state["qmap"])
    changelog = []
    calibration = []
    para_count = 0
    accepted = 0
    rejected = 0

    paragraphs = restored.split("\n\n")
    # Flag the fattest paragraphs needed to cover the gap (target-driven) and
    # process them in document order. The selection is already bounded, so we
    # do not stop early — the LLM undercuts projections, and stopping short of
    # the flagged set is the main cause of undershooting target.
    candidates = get_candidates(state)
    edited_indices = set(state.get("llm_edited_indices", set()))

    for cand in candidates:
        idx = cand["index"]
        para = paragraphs[idx]
        para_count += 1
        para_ref = f"P{idx + 1}"

        try:
            edited = edit_paragraph(
                para,
                budget=cand.get("budget"),
                focus=cand.get("focus"),
                fat_index=cand.get("fat_index"),
            )
        except Exception as e:
            changelog.append({
                "step": "Step 10 — Concision",
                "detail": f"LLM error: {e}",
                "para": para_ref,
            })
            continue

        ok, reason = _accept_edit(para, edited)
        orig_wc = len(para.split())
        edit_wc = len(edited.split())
        calibration.append({
            "ts": time.time(),
            "index": idx,
            "input_wc": orig_wc,
            "output_wc": edit_wc,
            "compression_ratio": round((orig_wc - edit_wc) / orig_wc, 4) if orig_wc else 0.0,
            "accepted": ok,
            "reason": reason,
            "fat_index": cand.get("fat_index"),
            "routing_reason": cand.get("routing_reason"),
        })
        if ok:
            saved = orig_wc - edit_wc
            current -= saved
            accepted += 1
            paragraphs[idx] = edited
            edited_indices.add(idx)
            changelog.append({
                "step": "Step 10 — Concision",
                "detail": f"accepted (~{saved} words saved) [{cand.get('routing_reason', 'routed')}]",
                "para": para_ref,
                "items": [
                    f"original -> \"{para[:100]}{'...' if len(para) > 100 else ''}\"",
                    f"edited   -> \"{edited[:100]}{'...' if len(edited) > 100 else ''}\"",
                ],
            })
        else:
            rejected += 1
            changelog.append({
                "step": "Step 10 — Concision",
                "detail": f"rejected — {reason} [{cand.get('routing_reason', 'routed')}]",
                "para": para_ref,
            })

    restored = "\n\n".join(paragraphs)
    state["text"], state["qmap"] = guard(restored)
    state["llm_edited_indices"] = edited_indices
    final_count = word_count(state["text"], state["qmap"])
    state["counts"]["step10"] = final_count
    state["llm_stats"] = {"para": para_count, "accepted": accepted, "rejected": rejected}
    state["log"].append({
        "step": "Step 10 — Concision",
        "detail": f"{para_count} paragraphs processed: {accepted} accepted, {rejected} rejected -> {final_count} words",
        "para": None,
    })
    state["log"].extend(changelog)
    _log_calibration(calibration)
    return state
