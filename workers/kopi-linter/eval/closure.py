"""Closure: one number for how far the linter has come toward Opus.

Every other number in this repo answers a local question, and the project has
been losing the plot between them. This one answers the whole question, in per
cent, and it is the number to quote:

    **How much of the distance from the original text to Opus's edit have we
    closed?**

Take the word-level edit distance ``d`` (Levenshtein over whitespace tokens,
unit cost for insert, delete and substitute, which is the word error rate of
speech recognition put to a different use). ``d(original, gold)`` is all the
work Opus did. ``d(output, gold)`` is the work still outstanding after the
linter has run. So

    closure = 1 - d(output, gold) / d(original, gold)

Pooled across the corpus, never averaged per paragraph, for the same reason
corpus SARI is pooled: paragraphs Opus left alone have a zero denominator and
any convention chosen for them decides the verdict.

Why this and not SARI as the headline:

* **Doing nothing scores exactly 0.** Not 0.2439. SARI pays for correct
  *keeping*, so a linter that touches 7% of paragraphs reads as though it were
  halfway to Opus while it has moved 1% of the words. Closure cannot be earned
  by restraint, because restraint changes no distance.
* **Damage scores below 0.** An edit Opus did not make moves the text away from
  the gold, so the distance grows and closure goes negative. The band-as-budget
  wrecking ball of C11 still scored 0.41 on SARI, which looks respectable; on
  closure a system that cuts wrongly is visibly worse than one that sleeps.
* **100% means reproducing the gold**, so the number has a real ceiling rather
  than an asymptote nobody can place.

The decomposition falls out of the algebra rather than being invented. Writing
``work = d(original, output)`` for the work attempted and ``gain = d(original,
gold) - d(output, gold)`` for the distance actually closed:

    reach    = work / d(original, gold)      how much of Opus's work we attempted
    accuracy = (1 + gain / work) / 2         how much of what we attempted landed
    closure  = reach * (2 * accuracy - 1)

Both are bounded by the triangle inequality, so accuracy sits in [0, 1] with no
clamping. The identity is worth reading twice, because it sets the strategy:
**at 50% accuracy closure is zero no matter how much is attempted**, and above
that every point of reach is worth ``2a - 1`` of it. Partial credit works out
correctly on its own: deleting three words where the gold deleted two of them
gives work 3, gain 1, and so two correct and one wrong.
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
