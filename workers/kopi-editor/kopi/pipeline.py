"""Shared setup for the three routes (analyze, proof, edit): loads spaCy once,
runs the diagnosis core, then lets each route perform its own actions.
`prepare` builds the common state.
"""
from kopi import diagnose
from kopi.language_model import load_english
from kopi.quote_guard import guard, unguard


def load_nlp():
    """The spaCy pipeline, downloaded on first use, or None if it cannot be had."""
    try:
        return load_english()
    except Exception:
        return None


def prepare(text: str, target: int, lang: str = "british", reduction: int = 0) -> dict:
    """Diagnose the document and build the base state shared by every route.

    Loads spaCy once, runs the deterministic diagnosis (per-paragraph
    instructions + document estimates), records the before-readability for the
    final check, and guards quotations. Announced before any work so the user is
    never left staring at a silent terminal. ``reduction`` (words the user asked to
    remove, 0 = clarity pass) drives the editing intensity in :mod:`kopi.intensity`.
    """
    from kopi.progress import StepSpinner

    sp = StepSpinner("loading spaCy model")
    sp.start()
    try:
        nlp = load_nlp()
    finally:
        sp.done()

    try:
        import textstat
        readability_before = textstat.flesch_reading_ease(text)
    except Exception:
        readability_before = None

    sp = StepSpinner("analysing document")
    sp.start()
    try:
        diag = diagnose.diagnose(text, nlp) if nlp is not None else None
    finally:
        sp.done()

    quoted = guard(text)
    guarded, qmap = quoted["text"], quoted["qmap"]
    return {
        "text": guarded,
        "qmap": qmap,
        "diagnosis": diag,
        "target": target,
        "reduction": reduction,
        "original_words": len(text.split()),
        "lang": lang,
        "log": [],
        "counts": {"step1": len(text.split())},
        "fillers": [],
        "redundant_pairs": [],
        "merge_candidates": [],
        "flags": [],
        "llm_stats": {},
        "readability_before": readability_before,
        "original_text": text,
        "eval_metrics": {},
    }


def finalize(state: dict) -> dict:
    """Run the final check and materialise the unguarded output text."""
    from kopi import step_check
    state = step_check.run(state)
    return {**state, "final_text": unguard(state["text"], state["qmap"])}
