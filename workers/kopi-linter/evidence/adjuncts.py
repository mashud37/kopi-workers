"""Induce prepositional-phrase drop rates from what the gold editor actually did.

`adjunct` is the largest deletion-reachable family in the corpus: 1,958
instances, 6,374 words, and 92% of it is a prepositional phrase being dropped.
Proposing the drop is trivial. Licensing it is the whole problem, because
adjuncts are removable and arguments are not, and the parse marks both `prep`.

The usual answer is a hand-written list of verbs and the prepositions they
subcategorise for. That is a hardcoded lexicon, it does not transfer to a new
discipline, and it is the instrument that reached 0.2% coverage last time. This
module takes the other route: find every prepositional phrase in the originals,
check whether it survived into the gold edit, and report the drop rate at three
levels of specificity so a rule can back off when it has never seen a frame.

**Survival is measured inside the sentence bead**, not across the paragraph, and
the difference decides whether the method works at all. Measured at paragraph
level first, the drop rate came out at 4.0% and only 5 of 921 frames cleared any
band threshold, all of them at fewer than 10 observations. That is not evidence
that phrases are rarely dropped; it is the test being wrong. A phrase counted as
kept whenever any of its content words appeared anywhere in the rewritten
paragraph, and since the editor rewrites rather than deletes, almost everything
reappears somewhere. Scoping the question to the sentences the phrase's own
sentence became is what makes the signal visible.
"""
from collections import Counter

from evidence.align import align

_CONTENT = frozenset(["NOUN", "PROPN", "ADJ", "VERB", "NUM", "ADV"])

# Most specific first. A rule consults them in this order and stops at the first
# level with enough observations behind it.
LEVELS = ("frame", "governor", "preposition")


def keys_for(prep, governor) -> dict:
    """The lookup key at each level of specificity for one phrase."""
    preposition = prep.lemma_.lower()
    return {
        "frame": f"{governor.pos_}:{governor.lemma_.lower()}:{preposition}",
        "governor": f"{governor.pos_}:{preposition}",
        "preposition": preposition,
    }


def phrases(doc):
    """Every prepositional phrase in a parse.

    Yields:
        ``(prep, governor, start, end, content)`` where ``content`` is the set of
        content lemmas inside the phrase and ``start``/``end`` are character
        offsets covering the preposition and its whole subtree.
    """
    for prep in doc:
        if prep.dep_ != "prep" or prep.pos_ != "ADP":
            continue
        subtree = list(prep.subtree)
        content = {t.lemma_.lower() for t in subtree if t.pos_ in _CONTENT}
        if not content:
            continue
        yield (prep, prep.head, subtree[0].idx,
               subtree[-1].idx + len(subtree[-1].text), content)


def _tally(sentence, target_lemmas: set, seen: dict, dropped: dict) -> None:
    for prep, governor, _, _, content in phrases(sentence.as_doc()):
        gone = not (content & target_lemmas)
        for level, key in keys_for(prep, governor).items():
            seen[level][key] += 1
            if gone:
                dropped[level][key] += 1


def survey(samples, nlp, on_progress=None) -> dict:
    """How often the gold editor dropped each kind of prepositional phrase.

    Each source sentence is checked against the target sentences its own bead
    became, so a phrase counts as dropped when it did not survive the rewrite of
    the sentence it lived in. Checking against the whole paragraph instead
    reports a 4% drop rate and no usable signal.

    Args:
        samples: gold :class:`evidence.load.Sample` records.
        nlp: a loaded spaCy pipeline.
        on_progress: called with (index, total, sample).

    Returns:
        ``{"seen": {level: Counter}, "dropped": {level: Counter}}`` keyed by
        :data:`LEVELS`.
    """
    seen = {level: Counter() for level in LEVELS}
    dropped = {level: Counter() for level in LEVELS}
    total = len(samples)
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, total, sample)
        for bead in align(sample.original, sample.edit, nlp):
            target = {t.lemma_.lower() for s in bead.target for t in s}
            for sentence in bead.source:
                _tally(sentence, target, seen, dropped)
    return {"seen": seen, "dropped": dropped}


def rates(result: dict, level: str, minimum: int) -> dict:
    """``{key: (drop rate, times seen)}`` for keys seen at least ``minimum`` times."""
    seen, dropped = result["seen"][level], result["dropped"][level]
    return {key: (dropped[key] / count, count)
            for key, count in seen.items() if count >= minimum}


def base_rate(result: dict) -> tuple[int, int]:
    """Total phrases seen and dropped, at the preposition level."""
    seen = sum(result["seen"]["preposition"].values())
    dropped = sum(result["dropped"]["preposition"].values())
    return seen, dropped


_HEADER = '''"""Prepositional-phrase drop rates, induced from the gold corpus.

Generated by ``evidence/adjuncts.py``; do not edit by hand. Regenerate with::

    python manage.py induce --family adjunct

Three tables at decreasing specificity, so a rule can back off from a frame it
has never seen to the governor class and then to the bare preposition. Each entry
is ``key: (drop rate, times seen)``. The rate is the share of occurrences whose
content lemmas were all absent from the gold edit, and it is used directly as the
rule's confidence.

The rate is a lower bound: a phrase counts as kept whenever any of its content
words survives anywhere in the paragraph, including when the editor moved it.
"""

'''


def write_table(result: dict, path, minimum: int = 5) -> dict:
    """Write the induced drop-rate tables as an importable module."""
    lines, written = [_HEADER], {}
    for level in LEVELS:
        table = rates(result, level, minimum)
        written[level] = len(table)
        lines.append(f"{level.upper()}_RATE = {{\n")
        for key, (rate, count) in sorted(table.items()):
            lines.append(f'    "{key}": ({rate:.3f}, {count}),\n')
        lines.append("}\n\n")
    path.write_text("".join(lines), encoding="utf-8")
    return written
