"""Lean shared setup for the three routes.

There is no longer a fixed 12-step pipeline. Each route (analyze / proof / edit)
loads spaCy once, runs the shared :mod:`kopi.diagnose` core, and then performs
its own small action set. ``prepare`` builds the common state every route needs.
"""
from kopi.quote_guard import guard, unguard
from kopi import diagnose

_nlp = None


def load_nlp():
    """Load (and cache) the spaCy pipeline, or None if unavailable."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except Exception:
            _nlp = False
    return _nlp or None


def prepare(text: str, target: int, lang: str = "british") -> dict:
    """Diagnose the document and build the base state shared by every route.

    Loads spaCy once, runs the deterministic diagnosis (per-paragraph
    instructions + document estimates), records the before-readability for the
    final check, and guards quotations. Announced before any work so the user is
    never left staring at a silent terminal.
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

    guarded, qmap = guard(text)
    return {
        "text": guarded,
        "qmap": qmap,
        "diagnosis": diag,
        "target": target,
        "lang": lang,
        "log": [],
        "counts": {"step1": len(text.split())},
        "fillers": [],
        "redundant_pairs": [],
        "merge_candidates": [],
        "flags": [],
        "llm_stats": {},
        "review_items": [],
        "readability_before": readability_before,
        "original_text": text,
        "eval_metrics": {},
    }


def finalize(state: dict) -> dict:
    """Run the final check and materialise the unguarded output text."""
    from kopi import step_check
    step_check.run(state)
    state["final_text"] = unguard(state["text"], state["qmap"])
    return state
