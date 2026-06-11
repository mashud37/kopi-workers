"""Unit tests for the composite fat-index in kopi/signals.py.

These exercise the scoring math directly with hand-built `analysis` dicts
(paragraphs with known properties), so they need neither spaCy nor a model.
"""
from kopi import signals


def _para(index, words, est, sent_len, depth, inv_flesch, is_quote=False):
    return {
        "index": index,
        "words": words,
        "est_savings": est,
        "mean_sent_len": sent_len,
        "mean_dep_depth": depth,
        "inv_flesch": inv_flesch,
        "is_quote": is_quote,
        "focus": [],
        "sentences": [],
    }


def test_rank_normalize_monotonic_and_ties():
    vals = [10.0, 20.0, 30.0]
    assert signals._rank_normalize(vals) == [0.0, 0.5, 1.0]
    # Ties share a score (fraction strictly less).
    assert signals._rank_normalize([5.0, 5.0, 9.0]) == [0.0, 0.0, 1.0]
    # Degenerate inputs.
    assert signals._rank_normalize([]) == []
    assert signals._rank_normalize([7.0]) == [0.0]


def test_fat_index_ranks_wordiest_highest():
    # P2 dominates every signal -> must score highest; P0 lowest.
    analysis = [
        _para(0, 50, 1.0, 12, 3, 10),
        _para(1, 80, 5.0, 20, 5, 30),
        _para(2, 120, 12.0, 30, 7, 60),
    ]
    fat = signals.paragraph_fat_index(analysis)
    assert set(fat) == {0, 1, 2}
    assert fat[2] > fat[1] > fat[0]
    assert fat[0] == 0.0  # lowest on every rank-normalised component


def test_fat_index_excludes_short_and_quotes():
    analysis = [
        _para(0, 120, 10.0, 30, 7, 60),
        _para(1, 10, 8.0, 30, 7, 60),                 # too short
        _para(2, 200, 9.0, 30, 7, 60, is_quote=True),  # quotation
    ]
    fat = signals.paragraph_fat_index(analysis)
    assert set(fat) == {0}


def test_fat_index_uses_density_when_aligned():
    analysis = [
        _para(0, 100, 5.0, 20, 5, 40),
        _para(1, 100, 5.0, 20, 5, 40),
    ]
    # Identical paragraphs except P1 has many proselint hits -> P1 fatter.
    state = {"proselint_para_hits": [0, 8]}
    fat = signals.paragraph_fat_index(analysis, state)
    assert fat[1] > fat[0]


def test_fat_index_ignores_misaligned_density():
    analysis = [_para(0, 100, 5.0, 20, 5, 40), _para(1, 100, 6.0, 20, 5, 40)]
    # Wrong length -> dropped, no crash; ranking falls back to other signals.
    state = {"proselint_para_hits": [3]}  # len 1, paras 2
    fat = signals.paragraph_fat_index(analysis, state)
    assert fat[1] > fat[0]


def test_fat_index_handles_missing_inv_flesch():
    analysis = [
        _para(0, 100, 5.0, 20, 5, None),
        _para(1, 120, 9.0, 25, 6, None),
    ]
    fat = signals.paragraph_fat_index(analysis)  # inv_flesch column dropped
    assert fat[1] > fat[0]


def test_is_quote_para():
    assert signals._is_quote_para("> a block quotation here")
    assert signals._is_quote_para('"a wholly quoted paragraph"')
    assert not signals._is_quote_para("Ordinary prose, with a comma.")
    assert signals._is_quote_para("   ")
