from kopi.quote_guard import guard, unguard
from kopi.progress import StepSpinner, _first_summary
from kopi import (
    step_count, step_fillers, step_proselint,
    step_syntax, step_redundancy, step_merge, step_reduce,
    step_plain, step_proofing, step_evaluate, step_check,
)

_STEPS = [
    (step_count,      "Count"),
    (step_fillers,    "Fillers & wordiness"),
    (step_proselint,  "Proselint"),
    (step_syntax,     "Syntax transforms"),
    (step_redundancy, "Redundancy scan"),
    (step_merge,      "Sentence merge"),
    (step_reduce,     "Apply reductions"),
    (step_plain,      "Plain language"),
    (step_proofing,   "Proofing"),
    (step_evaluate,   "Benchmark"),
    (step_check,      "Final check"),
]


def _mean_dep_depth(text):
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(text[:50000])
        depths = []
        for tok in doc:
            d, cur = 0, tok
            while cur.head != cur:
                cur = cur.head
                d += 1
            depths.append(d)
        return sum(depths) / len(depths) if depths else None
    except Exception:
        return None


def run_pipeline(
    text: str,
    target: int,
    lang: str = "british",
    rules_only: bool = False,
    evaluate: bool = False,
) -> dict:
    try:
        import textstat
        readability_before = textstat.flesch_reading_ease(text)
    except Exception:
        readability_before = None

    dep_depth_before = _mean_dep_depth(text)
    guarded, qmap = guard(text)

    state = {
        "text": guarded,
        "qmap": qmap,
        "target": target,
        "lang": lang,
        "rules_only": rules_only,
        "evaluate": evaluate,
        "log": [],
        "counts": {},
        "fillers": [],
        "redundant_pairs": [],
        "merge_candidates": [],
        "flags": [],
        "llm_stats": {},
        "review_items": [],
        "readability_before": readability_before,
        "dep_depth_before": dep_depth_before,
        "original_text": text,
        "eval_metrics": {},
    }

    for step, label in _STEPS:
        log_before = len(state["log"])
        sp = StepSpinner(label)
        sp.start()
        try:
            state = step.run(state)
        finally:
            summary = _first_summary(state["log"][log_before:])
            sp.done(summary)

    state["final_text"] = unguard(state["text"], state["qmap"])
    return state
