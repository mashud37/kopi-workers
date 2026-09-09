"""Probe-only rule that drops the auxiliary of a passive, so `manage.py probe`
can ask whether the gold editor takes the passive apart that way.
"""
from lint.edit import Edit

_PASSIVE_DEPS = frozenset(["auxpass", "aux:pass"])


def _agent_of(participle):
    """The `by` phrase attached to this participle, if it has one."""
    for child in participle.children:
        if child.dep_ == "agent":
            return child
    return None


def propose(doc):
    """A deletion for every passive auxiliary, and for the agent phrase after it."""
    edits = []
    for token in doc:
        if token.dep_ not in _PASSIVE_DEPS:
            continue
        participle = token.head
        edits.append(Edit(
            start=token.idx, end=token.idx + len(token.text) + 1, replacement="",
            rule="voice.auxiliary", family="voice-probe", confidence=0.5,
            note=f"passive auxiliary dropped: '{token.text} {participle.text}'",
        ))
        agent = _agent_of(participle)
        if agent is None:
            continue
        words = [word for word in agent.subtree if not word.is_space]
        start = min(word.idx for word in words)
        end = max(word.idx + len(word.text) for word in words)
        edits.append(Edit(
            start=start, end=end, replacement="",
            rule="voice.agent", family="voice-probe", confidence=0.5,
            note=f"agent phrase dropped: '{doc.text[start:end]}'",
        ))
    return edits
