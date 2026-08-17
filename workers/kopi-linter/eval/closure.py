"""Compute closure: the percent of the word-level edit distance from
original to Opus's gold that the output has closed, pooled across the
corpus. Decomposes into reach times accuracy.
"""
from dataclasses import dataclass


@dataclass
class Closure:
    """Pooled closure and the two factors it decomposes into."""
    closure: float
    reach: float
    accuracy: float
    gap: int
    work: int
    gain: int
    remaining: int


def distance(source: list[str], target: list[str]) -> int:
    """Word-level Levenshtein distance, unit cost for every operation.

    The shared prefix and suffix are stripped before the table is built. That is
    not a micro-optimisation here: a copy-editor changes a few words in a
    hundred, so trimming turns a 100x100 table into something nearer 8x6 and
    makes a full corpus pass cheap enough to run on every evaluation.
    """
    head = 0
    while head < len(source) and head < len(target) and source[head] == target[head]:
        head += 1
    tail = 0
    while (tail < len(source) - head and tail < len(target) - head
           and source[len(source) - 1 - tail] == target[len(target) - 1 - tail]):
        tail += 1
    source, target = source[head:len(source) - tail], target[head:len(target) - tail]
    if not source or not target:
        return len(source) or len(target)
    previous = list(range(len(target) + 1))
    for i, left in enumerate(source, 1):
        current = [i]
        for j, right in enumerate(target, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def measure(triples) -> Closure:
    """Closure over ``(original, output, gold)`` triples, pooled.

    Args:
        triples: one per paragraph, in the order source, system output, reference.

    Returns:
        A :class:`Closure`. ``accuracy`` is 0.0 when nothing was attempted,
        which is the honest reading: a system that never edits has no accuracy
        to report, and its closure is 0 either way.
    """
    gap = work = remaining = 0
    for original, output, gold in triples:
        source, produced, reference = original.split(), output.split(), gold.split()
        gap += distance(source, reference)
        work += distance(source, produced)
        remaining += distance(produced, reference)
    gain = gap - remaining
    return Closure(
        closure=gain / gap if gap else 0.0,
        reach=work / gap if gap else 0.0,
        accuracy=(1 + gain / work) / 2 if work else 0.0,
        gap=gap, work=work, gain=gain, remaining=remaining,
    )


_ANCHOR = [
    ("the gold itself", lambda o, g: g, 1.0),
    ("do nothing", lambda o, g: o, 0.0),
    ("delete everything", lambda o, g: "", None),
]


def anchors(triples) -> list[tuple[str, float, float | None]]:
    """Re-derive the fixed points of the scale on the corpus being reported.

    A metric nobody can fail is the defect this project has already shipped
    once, so the scale states where it is pinned every time it is quoted rather
    than in a comment. Copying the gold must score 1.0, doing nothing exactly
    0.0, and destroying the text must come out **negative**: that last one is
    the property SARI lacks and the reason this metric exists.

    Returns:
        ``(name, measured, expected)`` per anchor; ``expected`` is ``None`` for
        the destructive anchor, which is asserted to be negative, not exact.
    """
    out = []
    for name, produce, expected in _ANCHOR:
        score = measure([(o, produce(o, g), g) for o, _, g in triples]).closure
        out.append((name, score, expected))
    return out
