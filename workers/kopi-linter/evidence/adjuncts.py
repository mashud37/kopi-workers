"""Measure how often a prepositional phrase the parse marks `prep` was
dropped by the gold editor, producing drop-rate tables for `rule_adjunct` at
three specificity levels.
"""
from collections import Counter

from evidence.align import align

_CONTENT = frozenset(["NOUN", "PROPN", "ADJ", "VERB", "NUM", "ADV"])

# Most specific first. A rule consults them in this order and stops at the first
# level with enough observations behind it.
LEVELS = ("frame", "governor", "preposition")

_MIN_SIGHTINGS_TO_SHIP = 5

_HEADER = '''"""Prepositional-phrase drop rates induced from the train split of the gold corpus.
Regenerate with ``python manage.py induce --family adjunct``; never edit by hand.
"""

# Three tables at decreasing specificity, so a rule can back off from a frame it
# has never seen to the governor class and then to the bare preposition. Each
# entry is `key: (drop rate, times seen)`, the rate being the share of
# occurrences whose content lemmas were all absent from the gold edit, used
# directly as the rule's confidence.
#
# The rate is a lower bound: a phrase counts as kept whenever any of its content
# words survives anywhere in the paragraph, including when the editor moved it.

'''


def keys_for(prep, governor) -> dict:
    """The lookup key at each level of specificity for one phrase."""
    preposition = prep.lemma_.lower()
    return {
        "frame": f"{governor.pos_}:{governor.lemma_.lower()}:{preposition}",
        "governor": f"{governor.pos_}:{preposition}",
        "preposition": preposition,
    }


def _lemmas_in(sentences) -> set:
    """Every lemma across a run of sentences, lower-cased."""
    lemmas = set()
    for sentence in sentences:
        for token in sentence:
            lemmas.add(token.lemma_.lower())
    return lemmas


def phrases(doc):
    """Every prepositional phrase in a parse.

    Returns:
        ``(prep, governor, start, end, content)`` per phrase, where ``content`` is
        the set of content lemmas inside the phrase and ``start``/``end`` are
        character offsets covering the preposition and its whole subtree.
    """
    found = []
    for prep in doc:
        if prep.dep_ != "prep" or prep.pos_ != "ADP":
            continue
        subtree = list(prep.subtree)
        content = {token.lemma_.lower() for token in subtree if token.pos_ in _CONTENT}
        if not content:
            continue
        found.append((
            prep,
            prep.head,
            subtree[0].idx,
            subtree[-1].idx + len(subtree[-1].text),
            content,
        ))
    return found


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
    pending = []
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, total, sample)
        for bead in align(sample.original, sample.edit, nlp):
            target = _lemmas_in(bead.target)
            for sentence in bead.source:
                pending.append((sentence, target))
    for sentence, target_lemmas in pending:
        for prep, governor, _, _, content in phrases(sentence.as_doc()):
            gone = not (content & target_lemmas)
            for level, key in keys_for(prep, governor).items():
                seen[level][key] += 1
                dropped[level][key] += int(gone)
    return {"seen": seen, "dropped": dropped}


def attachment(samples, nlp, on_progress=None) -> dict:
    """How tied each governor is to each preposition, from the originals alone.

    The argument-versus-adjunct question, asked distributionally. "Depends"
    almost always takes "on", so "on" is its argument; "written" takes "in",
    "with", "for", "after" and a dozen others, so any one of them is an adjunct.
    That is a property of the language, visible in unedited text, and it needs no
    reference to what the gold editor did. So unlike :func:`survey` this licence
    is not fitted to one teacher and should transfer to prose the corpus has
    never seen.

    Returns:
        ``{"pairs": Counter, "governors": Counter}`` keyed by
        ``"<POS>:<lemma>:<prep>"`` and ``"<POS>:<lemma>"``.
    """
    pairs, governors = Counter(), Counter()
    total = len(samples)
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, total, sample)
        doc = nlp(sample.original)
        for token in doc:
            if token.pos_ in ("VERB", "NOUN", "PROPN", "AUX", "ADJ"):
                governors[f"{token.pos_}:{token.lemma_.lower()}"] += 1
        for prep, governor, _, _, _ in phrases(doc):
            key = f"{governor.pos_}:{governor.lemma_.lower()}"
            pairs[f"{key}:{prep.lemma_.lower()}"] += 1
    return {"pairs": pairs, "governors": governors}


def attachment_rates(result: dict, minimum: int) -> dict:
    """``{key: (P(prep | governor), governor count)}`` for well-observed governors."""
    pairs, governors = result["pairs"], result["governors"]
    out = {}
    for key, count in pairs.items():
        governor = key.rsplit(":", 1)[0]
        seen = governors.get(governor, 0)
        if seen >= minimum:
            out[key] = (count / seen, seen)
    return out


def rates(result: dict, level: str, minimum: int) -> dict:
    """``{key: (drop rate, times seen)}`` for keys seen at least ``minimum`` times."""
    seen, dropped = result["seen"][level], result["dropped"][level]
    return {key: (dropped[key] / count, count)
            for key, count in seen.items() if count >= minimum}


def base_rate(result: dict) -> dict:
    """Total phrases seen and dropped, at the preposition level."""
    return {
        "seen": sum(result["seen"]["preposition"].values()),
        "dropped": sum(result["dropped"]["preposition"].values()),
    }


def _emit(lines: list, name: str, table: dict) -> None:
    lines.append(f"{name} = {{\n")
    for key, (value, count) in sorted(table.items()):
        lines.append(f'    "{key}": ({value:.3f}, {count}),\n')
    lines.append("}\n\n")


def write_table(result: dict, path, minimum: int = _MIN_SIGHTINGS_TO_SHIP,
                attach: dict | None = None) -> dict:
    """Write the induced drop-rate and attachment tables as an importable module."""
    lines, written = [_HEADER], {}
    for level in LEVELS:
        table = rates(result, level, minimum)
        written[level] = len(table)
        _emit(lines, f"{level.upper()}_RATE", table)
    if attach is not None:
        table = attachment_rates(attach, minimum)
        written["attachment"] = len(table)
        _emit(lines, "ATTACHMENT_RATE", table)
    path.write_text("".join(lines), encoding="utf-8")
    return written
