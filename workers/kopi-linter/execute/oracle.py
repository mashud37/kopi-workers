"""Build one execution task per gold span edit and score a backend against
Opus's own target, so performing a transformation is measured apart from
deciding where.
"""
import time
from statistics import median

from eval.closure import distance

# A span that only moves punctuation has no transformation in it to perform.
_SKIP_FAMILIES = frozenset(["punctuation"])

_WARMUP_CALLS = 1

REWRITING_OPS = frozenset(["replace", "insert"])


def _tasks_in(sample, nlp, held_out: set) -> list:
    """Every gold span edit in one paragraph, as an execution task."""
    from evidence.align import align
    from evidence.taxonomy import bead_context, classify_span

    out = []
    for bead in align(sample.original, sample.edit, nlp):
        if not bead.spans:
            continue
        context = bead_context(bead)
        for span in bead.spans:
            kind = classify_span(span, bead, context)
            if kind["family"] in _SKIP_FAMILIES:
                continue
            out.append({
                "source": span.source,
                "target": span.target,
                "left": span.left_context,
                "right": span.right_context,
                "family": kind["family"],
                "subtype": kind["subtype"],
                "op": span.op,
                "held_out": sample.doc in held_out,
            })
    return out


def tasks(samples, nlp, held_out: set, on_progress=None) -> list:
    """One task per gold span edit across the corpus.

    Args:
        samples: gold :class:`evidence.load.Sample` records.
        nlp: a loaded spaCy pipeline.
        held_out: document names in the test split, marked on every task so a
            backend fitted on the training side can be scored on both.
        on_progress: called with (index, total, sample).

    Returns:
        Task dicts in corpus order, each holding the source span, Opus's target
        for it, four words of context each side, and its family.
    """
    out = []
    total = len(samples)
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, total, sample)
        try:
            out.extend(_tasks_in(sample, nlp, held_out))
        except Exception:
            continue
    return out


def blank() -> dict:
    """An empty pooled row, also the stand-in for a group nothing landed in."""
    return {
        "tasks": 0,
        "answered": 0,
        "exact": 0,
        "beats_keep": 0,
        "beats_delete": 0,
        "gap": 0,
        "remaining": 0,
    }


def _measure(task: dict, produced: str | None) -> dict:
    """One task's contribution to a pooled row, refusal counting as leaving the span.

    Both anchors are recorded per task rather than only in the pooled closure,
    because a backend can close distance overall while being beaten span for
    span by simply dropping the text, and that difference decides whether the
    backend is worth having.
    """
    answer = task["source"] if produced is None else produced
    target = task["target"].split()
    left = distance(answer.split(), target)
    kept = distance(task["source"].split(), target)
    return {
        "tasks": 1,
        "answered": int(produced is not None),
        "exact": int(left == 0),
        "beats_keep": int(left < kept),
        "beats_delete": int(left < len(target)),
        "gap": kept,
        "remaining": left,
    }


def _pooled(row: dict, one: dict) -> dict:
    """Two rows added field by field, as a new row."""
    return {field: row[field] + one[field] for field in row}


def _keys_for(task: dict) -> dict:
    """Which row of each pooled table one task counts towards."""
    return {
        "family": task["family"],
        "op": task["op"],
        "split": "test" if task["held_out"] else "train",
        "kind": "rewriting" if task["op"] in REWRITING_OPS else "deletion",
    }


def score(tasks_to_run: list, execute, state: dict, on_progress=None) -> dict:
    """Run one backend over every task and pool its distance to Opus.

    Args:
        tasks_to_run: task dicts from :func:`tasks`.
        execute: the backend's ``(task, state) -> str | None`` callable, where
            ``None`` means it refused and the span is left as the author wrote it.
        state: whatever the backend's ``prepare`` returned.
        on_progress: called with (index, total, task).

    Returns:
        ``{"total", "family", "op", "split", "kind", "seconds"}``. The first five
        hold pooled rows; ``seconds`` holds one call time per task.
    """
    result = {
        "total": blank(),
        "family": {},
        "op": {},
        "split": {},
        "kind": {},
        "seconds": [],
    }
    total = len(tasks_to_run)
    for i, task in enumerate(tasks_to_run, 1):
        if on_progress:
            on_progress(i, total, task)
        started = time.perf_counter()
        produced = execute(task, state)
        result["seconds"].append(time.perf_counter() - started)
        one = _measure(task, produced)
        result["total"] = _pooled(result["total"], one)
        for group, key in _keys_for(task).items():
            table = result[group]
            table[key] = _pooled(table.get(key, blank()), one)
    return result


def summarise(row: dict) -> dict:
    """Span closure, exact and near rates for one pooled row.

    Closure is the project's master metric read at span level: leaving the span
    alone scores 0, writing Opus's own words scores 1, and writing something
    further from Opus than the author's original scores below 0.
    """
    seen = row["tasks"] or 1
    gap = row["gap"] or 1
    return {
        "tasks": row["tasks"],
        "closure": 1.0 - row["remaining"] / gap,
        "exact": row["exact"] / seen,
        "beats_keep": row["beats_keep"] / seen,
        "beats_delete": row["beats_delete"] / seen,
        "answered": row["answered"] / seen,
    }


def latency(seconds: list) -> float:
    """Median seconds per call, with the warm-up call discarded."""
    warm = seconds[_WARMUP_CALLS:]
    return median(warm) if warm else 0.0
