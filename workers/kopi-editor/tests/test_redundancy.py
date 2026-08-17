"""Unit tests for the redundancy scoring in kopi/step_redundancy.py. These
exercise the pure scoring and selection functions with hand-built lemma sets
and similarity matrices, needing neither spaCy nor a model.
"""
from kopi import step_redundancy as red


def test_build_idf_rarer_terms_weigh_more():
    # 'common' appears in every sentence; 'rare' in one.
    lemma_sets = [{"common", "rare"}, {"common"}, {"common"}]
    idf = red._build_idf(lemma_sets)
    assert idf["rare"] > idf["common"]
    # Smoothed form is strictly positive even for an all-sentences term.
    assert idf["common"] > 0


def test_weighted_overlap_bounds_and_emptiness():
    idf = {"a": 2.0, "b": 1.0}
    assert red._weighted_overlap(set(), {"a"}, idf) == 0.0
    assert red._weighted_overlap({"a"}, {"a"}, idf) == 1.0   # identical -> full
    # Disjoint sets share nothing.
    assert red._weighted_overlap({"a"}, {"b"}, idf) == 0.0


def test_weighted_overlap_distinctive_terms_dominate():
    # Sharing the distinctive 'thesis' should outweigh sharing the generic 'thing'.
    idf = {"thesis": 5.0, "thing": 1.0, "other": 1.0, "else": 1.0}
    share_rare = red._weighted_overlap({"thesis", "other"}, {"thesis", "else"}, idf)
    share_common = red._weighted_overlap({"thing", "other"}, {"thing", "else"}, idf)
    assert share_rare > share_common


def test_select_redundant_flags_later_restatement():
    sentences = [
        "The reform reshaped agricultural labour markets across the region.",
        "Across the region, the reform reshaped agricultural labour markets.",
        "A wholly unrelated point about maritime trade and shipping routes.",
    ]
    lemmas = [
        {"reform", "reshape", "agricultural", "labour", "market", "region"},
        {"reform", "reshape", "agricultural", "labour", "market", "region"},
        {"unrelated", "point", "maritime", "trade", "shipping", "route"},
    ]
    idf = red._build_idf(lemmas)
    # S0 and S1 near-identical; S2 distinct.
    sim = [
        [1.00, 0.93, 0.10],
        [0.93, 1.00, 0.12],
        [0.10, 0.12, 1.00],
    ]
    pairs = red._select_redundant(sentences, lemmas, sim, idf)
    assert len(pairs) == 1
    # The earlier sentence is kept as the anchor; the later one is removed.
    assert pairs[0]["keep"] == sentences[0]
    assert pairs[0]["remove"] == sentences[1]
    assert pairs[0]["similarity"] == 0.93
    assert pairs[0]["savings"] == len(sentences[1].split())


def test_select_redundant_requires_content_overlap():
    # High embedding similarity but no shared distinctive content -> not flagged.
    sentences = ["alpha beta gamma delta", "epsilon zeta eta theta"]
    lemmas = [{"alpha", "beta", "gamma"}, {"epsilon", "zeta", "eta"}]
    idf = red._build_idf(lemmas)
    sim = [[1.00, 0.99], [0.99, 1.00]]
    pairs = red._select_redundant(sentences, lemmas, sim, idf)
    assert pairs == []


def test_select_redundant_below_similarity_threshold():
    sentences = ["one two three four", "one two three five"]
    lemmas = [{"one", "two", "three"}, {"one", "two", "three"}]
    idf = red._build_idf(lemmas)
    sim = [[1.00, 0.50], [0.50, 1.00]]   # below 0.85
    pairs = red._select_redundant(sentences, lemmas, sim, idf)
    assert pairs == []


def test_select_redundant_three_near_duplicates():
    # All three restate the same point; the first anchors, the next two flagged.
    sentences = ["point a stated once", "point a stated twice", "point a stated thrice"]
    lemmas = [{"point", "state"}, {"point", "state"}, {"point", "state"}]
    idf = red._build_idf(lemmas)
    sim = [
        [1.00, 0.90, 0.88],
        [0.90, 1.00, 0.91],
        [0.88, 0.91, 1.00],
    ]
    pairs = red._select_redundant(sentences, lemmas, sim, idf)
    assert len(pairs) == 2
    assert all(p["keep"] == sentences[0] for p in pairs)
    assert {p["remove"] for p in pairs} == {sentences[1], sentences[2]}
