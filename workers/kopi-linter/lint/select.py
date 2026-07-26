"""Choose the best conflict-free subset of proposed edits.

Rules propose freely and their proposals overlap: a relative-clause reduction
and a light-verb rewrite will both claim the same verb. Applying them in
whatever order the rules ran makes the output depend on rule registration order,
which is the difference between a deterministic linter and one that merely looks
deterministic.

Picking the highest-scoring set of non-overlapping spans is weighted interval
scheduling, which has an exact dynamic program: sort by end offset, and for each
edit either take it plus the best solution ending before it starts, or skip it.
``bisect`` finds that predecessor in log time, so the whole thing is O(n log n)
and optimal, not greedy.

A word budget makes it a knapsack instead, which has no exact polynomial
solution. The budget is therefore applied as a second pass over the optimal
unconstrained set, dropping the weakest edits until the floor is respected.

That second pass used to be a safety valve that rarely fired. For ranked
families it is now the mechanism: they enter selection without a confidence
threshold and the budget decides how many survive, best-first
(``docs/constraints.md`` C9). Because a ranked family's confidence is bounded
below the confidence a licensed rule asserts, the budget gives up a ranked guess
before it gives up a licensed edit, which is the intended ordering.
"""
from bisect import bisect_right

from lint.edit import Edit


def _predecessors(edits: list[Edit]) -> list[int]:
    starts_sorted_by_end = [e.end for e in edits]
    return [bisect_right(starts_sorted_by_end, e.start) for e in edits]


def _best_set(edits: list[Edit], text: str) -> list[Edit]:
    if not edits:
        return []
    edits = sorted(edits, key=lambda e: (e.end, e.start))
    prev = _predecessors(edits)
    best = [0.0] * (len(edits) + 1)
    take = [False] * (len(edits) + 1)
    for i, edit in enumerate(edits, 1):
        with_edit = edit.weight(text) + best[prev[i - 1]]
        without = best[i - 1]
        best[i] = max(with_edit, without)
        take[i] = with_edit > without
    chosen = []
    i = len(edits)
    while i > 0:
        if take[i]:
            chosen.append(edits[i - 1])
            i = prev[i - 1]
        else:
            i -= 1
    chosen.reverse()
    return chosen


def _within_budget(chosen: list[Edit], text: str, floor: int) -> list[Edit]:
    """Drop the weakest edits until the result keeps at least ``floor`` words."""
    kept = list(chosen)
    original = len(text.split())
    while kept and original - sum(e.words_saved(text) for e in kept) < floor:
        weakest = min(kept, key=lambda e: (e.confidence, e.words_saved(text)))
        kept.remove(weakest)
    return kept


def select(edits: list[Edit], text: str, band) -> list[Edit]:
    """The conflict-free, band-admissible, budget-respecting set of edits.

    Args:
        edits: every proposal from every rule, in any order.
        text: the paragraph the offsets refer to.
        band: a :class:`lint.bands.Band`, supplying the per-family confidence
            thresholds and the compression ceiling.

    Returns:
        Edits in document order, guaranteed non-overlapping, so
        :func:`lint.edit.apply_edits` can splice them directly.
    """
    admissible = [e for e in edits if band.admits(e) and e.start <= e.end]
    chosen = _best_set(admissible, text)
    return _within_budget(chosen, text, band.floor(len(text.split())))
