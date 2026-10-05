"""Turn each gold paragraph into one tag per source word, keep or delete plus
what to write before it, and induce the closed phrase vocabulary those tags
draw on.
"""
import difflib
from collections import Counter

# Every source word carries one of these, so deletion, sentence dropping,
# connective repair, lexical swap and merge are all the same mechanism. `END`
# is a slot after the last word, which only ever carries a phrase.
BASES = ("KEEP", "DELETE", "END")

COVERAGE_STEPS = (1, 2, 3, 5, 10, 25, 50)


def _tokens_of(sentences) -> list:
    """Every non-space token across a run of sentences, in order."""
    tokens = []
    for sentence in sentences:
        for token in sentence:
            if not token.is_space:
                tokens.append(token)
    return tokens


def _opcodes(source: list, target: list) -> list:
    """The edit script between two word lists, compared without case."""
    matcher = difflib.SequenceMatcher(
        a=[word.lower() for word in source],
        b=[word.lower() for word in target],
        autojunk=False,
    )
    return matcher.get_opcodes()


def _tag(token, base: str, phrase: str) -> dict:
    """One word's tag, carrying the parse token so a model can read features off it."""
    return {
        "token": token,
        "word": token.text if token is not None else "",
        "base": base,
        "phrase": phrase,
    }


def _bead_tags(bead) -> list:
    """One tag per source word in a bead, from what the gold did to that bead.

    A replacement writes its phrase before the first word it covers and deletes
    every word it covers, which is LaserTagger's shape and the reason the same
    vocabulary expresses a swap and a cut without needing two tag families.
    """
    source = _tokens_of(bead.source)
    if not source:
        return []
    if bead.op == "delete" or not bead.target:
        return [_tag(token, "DELETE", "") for token in source]
    words = [token.text for token in source]
    target = [token.text for token in _tokens_of(bead.target)]
    tags = [_tag(token, "KEEP", "") for token in source]
    tags.append(_tag(None, "END", ""))
    for op, i1, i2, j1, j2 in _opcodes(words, target):
        if op == "equal":
            continue
        tags[i1]["phrase"] = " ".join(target[j1:j2])
        for index in range(i1, i2):
            tags[index]["base"] = "DELETE"
    if not tags[-1]["phrase"]:
        tags.pop()
    return tags


def tags_for(sample, nlp) -> list:
    """Every source word in one paragraph, with the tag the gold edit implies."""
    from evidence.align import align

    out = []
    for bead in align(sample.original, sample.edit, nlp):
        out.extend(_bead_tags(bead))
    return out


def _blank() -> dict:
    return {"tokens": 0, "bases": Counter(), "phrases": Counter(), "written": 0}


def survey(samples, nlp, held_out: set, on_progress=None) -> dict:
    """Tag every gold paragraph and pool the counts, keeping the split apart.

    Args:
        samples: gold :class:`evidence.load.Sample` records.
        nlp: a loaded spaCy pipeline.
        held_out: document names in the test split.
        on_progress: called with (index, total, sample).

    Returns:
        ``{"train": row, "test": row, "failed": int}`` where a row holds the token
        count, the base-tag counts, the phrase counts and how many tags carried a
        phrase at all.
    """
    result = {"train": _blank(), "test": _blank(), "failed": 0}
    total = len(samples)
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, total, sample)
        try:
            tagged = tags_for(sample, nlp)
        except Exception:
            result["failed"] += 1
            continue
        row = result["test" if sample.doc in held_out else "train"]
        for tag in tagged:
            row["tokens"] += 1
            row["bases"][tag["base"]] += 1
            if tag["phrase"]:
                row["written"] += 1
                row["phrases"][tag["phrase"].lower()] += 1
    return result


def vocabulary(row: dict, minimum: int) -> set:
    """Phrases written at least ``minimum`` times, which is the closed tag set."""
    return {phrase for phrase, seen in row["phrases"].items() if seen >= minimum}


def coverage(train: dict, test: dict, minimum: int) -> dict:
    """How much of the held-out writing a vocabulary fitted on train can spell.

    Returns:
        ``{"minimum", "size", "covered", "share"}``, where ``share`` is over the
        held-out tags that carry a phrase, not over all tokens.
    """
    words = vocabulary(train, minimum)
    covered = 0
    for phrase, seen in test["phrases"].items():
        if phrase in words:
            covered += seen
    return {
        "minimum": minimum,
        "size": len(words),
        "covered": covered,
        "share": covered / test["written"] if test["written"] else 0.0,
    }
