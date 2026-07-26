"""SARI, the standard text-simplification metric (Xu et al., 2016).

BLEU and similarity scores are the wrong instrument for this task: both reward
leaving the text alone, which is exactly the failure mode a linter falls into.
SARI scores the three operations separately against a reference edit, so keeping
what should be kept, deleting what should be deleted, and adding what should be
added each earn credit on their own.

  SARI = mean over n-gram orders of (F1_add, F1_keep, precision_delete)

Deletion is scored by precision only, as in the original: there are usually
several defensible ways to shorten a sentence, so a system is not penalised for
failing to delete what the reference deleted, only for deleting what it kept.

**Report the corpus figure, not the mean of per-paragraph figures.** When a
system leaves a paragraph untouched it attempts no deletions, and the
per-paragraph score then needs a value for an empty denominator. There is no
neutral choice: scoring it 0 hands any system that edits a large free margin
over doing nothing, and scoring it 1 makes doing nothing nearly unbeatable. On
this corpus the two conventions disagree by enough to flip the verdict on both
the linter and the served Qwen, so neither can be used to decide anything.
Pooling the counts across the test set removes the question, because the pooled
denominators are never empty. :func:`sari` is kept for inspecting one paragraph;
:func:`corpus_sari` is the number that decides.
"""
from collections import Counter

_MAX_ORDER = 4


def _ngrams(tokens: list[str], n: int) -> Counter:
    return Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


class _Pool:
    """Running hit and denominator totals for one n-gram order."""

    def __init__(self):
        self.add_hit = self.add_tried = self.add_wanted = 0
        self.keep_hit = self.keep_tried = self.keep_wanted = 0
        self.del_hit = self.del_tried = 0

    def observe(self, source: Counter, output: Counter, reference: Counter) -> None:
        added, should_add = output - source, reference - source
        self.add_hit += sum((added & should_add).values())
        self.add_tried += sum(added.values())
        self.add_wanted += sum(should_add.values())

        kept, should_keep = source & output, source & reference
        self.keep_hit += sum((kept & should_keep).values())
        self.keep_tried += sum(kept.values())
        self.keep_wanted += sum(should_keep.values())

        deleted, should_delete = source - output, source - reference
        self.del_hit += sum((deleted & should_delete).values())
        self.del_tried += sum(deleted.values())

    def score(self) -> tuple[float, float, float]:
        add = _f1(_safe(self.add_hit, self.add_tried), _safe(self.add_hit, self.add_wanted))
        keep = _f1(_safe(self.keep_hit, self.keep_tried), _safe(self.keep_hit, self.keep_wanted))
        return add, keep, _safe(self.del_hit, self.del_tried)


def _safe(hit: int, total: int) -> float:
    return hit / total if total else 0.0


def corpus_sari(triples) -> dict:
    """Corpus-level SARI over ``(source, output, reference)`` triples.

    Returns:
        ``{"sari", "add", "keep", "delete"}``, each in [0, 1]. The three
        components are reported alongside the total because they answer
        different questions: a linter that is too timid loses on ``delete``,
        and one that is too eager loses on ``keep``.
    """
    pools = [_Pool() for _ in range(_MAX_ORDER)]
    for source, output, reference in triples:
        s_tokens, o_tokens, r_tokens = (t.lower().split() for t in (source, output, reference))
        for n in range(1, _MAX_ORDER + 1):
            pools[n - 1].observe(_ngrams(s_tokens, n), _ngrams(o_tokens, n), _ngrams(r_tokens, n))
    scored = [pool.score() for pool in pools]
    add = sum(s[0] for s in scored) / len(scored)
    keep = sum(s[1] for s in scored) / len(scored)
    delete = sum(s[2] for s in scored) / len(scored)
    return {"sari": (add + keep + delete) / 3.0, "add": add, "keep": keep, "delete": delete}


def sari(source: str, output: str, reference: str) -> float:
    """Per-paragraph SARI, for inspecting a single edit.

    Convention-sensitive when the output is unchanged (see the module docstring);
    use :func:`corpus_sari` for any comparison between systems.
    """
    return corpus_sari([(source, output, reference)])["sari"]
