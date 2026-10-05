"""Unit tests for the parse-feature helpers in kopi/signals.py."""
from kopi import signals


def test_is_quote_para():
    assert signals._is_quote_para("“a wholly quoted paragraph.”")
    assert signals._is_quote_para("> a markdown block quote")
    assert signals._is_quote_para("")  # empty -> treated as non-editable
    assert not signals._is_quote_para("An ordinary sentence about the topic at hand.")
    # A paragraph that merely contains an inline quote is not a whole quotation.
    assert not signals._is_quote_para('He said "yes" and then continued at length here.')


class _CyclicTok:
    def __init__(self):
        self.head = self


def test_tree_depth_is_bounded():
    """A cyclic parse must not hang the depth walk (bounded at 1000)."""
    a = _CyclicTok()
    b = _CyclicTok()
    a.head = b
    b.head = a  # cycle
    assert signals._tree_depth(a) == 1000


class _FakeTok:
    def __init__(self, dep="dep", pos="NOUN", lemma="thing", text="thing"):
        self.dep_ = dep
        self.pos_ = pos
        self.lemma_ = lemma
        self.text = text
        self.is_punct = False
        self.is_space = False
        self.head = self


class _FakeSent:
    def __init__(self, tokens, text):
        self._tokens = tokens
        self.text = text

    def __iter__(self):
        return iter(self._tokens)


def test_sentence_features_short_sentence_has_no_savings():
    toks = [_FakeTok() for _ in range(3)]
    feats = signals.sentence_features(_FakeSent(toks, "short sentence here"))
    assert feats["words"] == 3
    assert feats["est_savings"] == 0.0  # below _MIN_SENT_WORDS


def test_sentence_features_counts_passive_and_subordination():
    toks = (
        [_FakeTok(dep="nsubjpass")]
        + [_FakeTok(dep="relcl")]
        + [_FakeTok() for _ in range(8)]
    )
    feats = signals.sentence_features(_FakeSent(toks, "x " * 10))
    assert feats["passive"] == 1
    assert feats["subord"] == 1
    assert feats["est_savings"] > 0  # long enough + has complexity
