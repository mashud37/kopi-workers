"""Pick the highest-scoring conflict-free subset of proposed edits via
weighted interval scheduling, then trim to the word budget by dropping the
weakest edits, ranked families first.
"""
from bisect import bisect_right

from lint.edit import Edit


def _best_set(edits: list[Edit], text: str) -> list[Edit]:
    if not edits:
        return []
    edits = sorted(edits, key=lambda e: (e.end, e.start))
    starts_sorted_by_end = [e.end for e in edits]
    prev = [bisect_right(starts_sorted_by_end, e.start) for e in edits]
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


def _trim(kept: list[Edit], text: str, floor: int, ranked_only: bool) -> list[Edit]:
    """Drop the weakest edits until the result keeps at least ``floor`` words."""
    original = len(text.split())
    while kept and original - sum(e.words_saved(text) for e in kept) < floor:
        pool = [e for e in kept if e.ranked] if ranked_only else kept
        if not pool:
            break
        kept.remove(min(pool, key=lambda e: (e.confidence, e.words_saved(text))))
    return kept


def _within_budget(chosen: list[Edit], text: str, band) -> list[Edit]:
    """Spend the band's word budget, then enforce its hard ceiling.

    Two passes, because the band carries two different numbers. The soft target
    is what the gold editor typically removes at this intensity, and only ranked
    edits are trimmed against it: a licensed edit asserts it is correct, so it is
    not given up merely because the paragraph is already short enough. The hard
    floor is the compression ceiling, and everything is trimmed against that.
    """
    words = len(text.split())
    kept = _trim(list(chosen), text, band.target_floor(words), ranked_only=True)
    return _trim(kept, text, band.floor(words), ranked_only=False)


def select(edits: list[Edit], text: str, band) -> list[Edit]:
    """The conflict-free, band-admissible, budget-respecting set of edits.

    Args:
        edits: every proposal from every rule, in any order.
        text: the paragraph the offsets refer to.
        band: a :class:`lint.bands.Band`, supplying the per-family confidence
            thresholds, the word target and the compression ceiling.

    Returns:
        Edits in document order, guaranteed non-overlapping, so
        :func:`lint.edit.apply_edits` can splice them directly.
    """
    admissible = [e for e in edits if band.admits(e) and e.start <= e.end]
    chosen = _best_set(admissible, text)
    return _within_budget(chosen, text, band)
