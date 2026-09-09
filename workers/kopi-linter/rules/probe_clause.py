"""Probe-only rule that drops a whole adverbial clause, so `manage.py probe` can
ask whether the gold editor removes one before anything is built to remove it.
"""
from lint.edit import Edit

# A clause worth asking about carries at least this many words. Below it the
# span is a stray connective and the probe measures punctuation, not clauses.
MINIMUM_WORDS = 4

ADVERBIAL = frozenset(["advcl"])
COMPLEMENT = frozenset(["ccomp"])
_PUNCTUATION = ",;:"


def propose(doc, deps=ADVERBIAL):
    """A deletion for every clause of these dependency types hanging off a verb."""
    edits = []
    for clause in doc:
        if clause.dep_ not in deps or clause.head.pos_ not in {"VERB", "AUX"}:
            continue
        words = [token for token in clause.subtree if not token.is_space]
        start = min(token.idx for token in words)
        end = max(token.idx + len(token.text) for token in words)
        text = doc.text[start:end]
        if len(text.split()) < MINIMUM_WORDS:
            continue
        if start == clause.sent.start_char:
            continue
        while end < len(doc.text) and doc.text[end] in _PUNCTUATION:
            end += 1
        edits.append(Edit(
            start=start, end=end, replacement="",
            rule="clause.drop", family="clause-probe", confidence=0.5,
            note=f"clause dropped: '{text}'",
        ))
    return edits
