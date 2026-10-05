"""Predict whether the gold editor cut a paragraph at all, since a uniform
per-paragraph word budget otherwise forces edits onto paragraphs never
touched. Reports the best threshold from a sweep.
"""
from dataclasses import dataclass

_SWEEP_STEPS = 40


@dataclass
class Outcome:
    """How a decision rule did at picking paragraphs to cut."""
    name: str
    precision: float
    recall: float
    f1: float
    fired: int
    positives: int
    total: int
    note: str = ""


def features(group: list) -> dict:
    """Paragraph-level summary of its drop candidates."""
    scores = [c.features["shipped"] for c in group]
    return {
        "candidates": float(len(group)),
        "best": max(scores),
        "mean": sum(scores) / len(scores),
        "spread": max(scores) - min(scores),
    }


def label(group: list) -> bool:
    """Whether the gold editor dropped any phrase in this paragraph."""
    return any(c.dropped for c in group)


def _score(name: str, decisions: list, labels: list, note: str = "") -> Outcome:
    hits = sum(1 for d, y in zip(decisions, labels) if d and y)
    fired = sum(decisions)
    positives = sum(labels)
    precision = hits / fired if fired else 0.0
    recall = hits / positives if positives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return Outcome(name, precision, recall, f1, fired, positives, len(labels), note)


RULES = {
    "always": lambda f: True,
    "any candidate scores 0.5+": lambda f: f["best"] >= 0.5,
    "two candidates or more": lambda f: f["candidates"] >= 2.0,
    "mean 0.35+": lambda f: f["mean"] >= 0.35,
}


def sweep(rows: list, labels: list, feature: str) -> Outcome:
    """Best achievable F1 over a threshold on one feature, and where it sits.

    Reported even when it is poor. A feature whose best possible threshold barely
    beats cutting everything is a feature that does not carry the decision, and
    that is worth knowing before it is wired into the engine.
    """
    values = [r[feature] for r in rows]
    low, high = min(values), max(values)
    if high <= low:
        return _score(f"{feature} (flat)", [True] * len(rows), labels)
    best = None
    for step in range(_SWEEP_STEPS + 1):
        cut = low + (high - low) * step / _SWEEP_STEPS
        outcome = _score(f"{feature} >= {cut:.3f}",
                         [v >= cut for v in values], labels,
                         note=f"swept over {_SWEEP_STEPS} thresholds")
        if best is None or outcome.f1 > best.f1:
            best = outcome
    return best


def evaluate(groups: list) -> list:
    """Every fixed rule plus a swept threshold per feature, scored on the same data."""
    rows = [features(g) for g in groups]
    labels = [label(g) for g in groups]
    out = [_score(name, [rule(r) for r in rows], labels) for name, rule in RULES.items()]
    out += [sweep(rows, labels, name) for name in ("best", "mean", "candidates")]
    return sorted(out, key=lambda o: -o.f1)
