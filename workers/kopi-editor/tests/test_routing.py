"""Unit tests for the target-driven selector in kopi/signals.py."""
from kopi import signals
from kopi import step_concision
from kopi.quote_guard import guard, word_count


def _analysis(words_by_index):
    return [
        {"index": i, "words": w, "est_savings": 0.0, "mean_sent_len": 0,
         "mean_dep_depth": 0, "inv_flesch": 0, "is_quote": False,
         "focus": [], "sentences": []}
        for i, w in words_by_index.items()
    ]


def test_returns_document_order():
    fat = {0: 0.2, 1: 0.9, 2: 0.5, 3: 0.7}
    analysis = _analysis({0: 100, 1: 100, 2: 100, 3: 100})
    selected = signals.select_by_target(fat, analysis, reduction=10)
    assert selected == sorted(selected)  # ascending document order


def test_covers_target_with_safety_margin():
    # 100-word paras, expected_compression 0.25 -> 25 projected each.
    fat = {i: 1.0 - i * 0.01 for i in range(20)}
    analysis = _analysis({i: 100 for i in range(20)})
    reduction = 50  # needs >= 50 * 1.3 = 65 projected -> at least 3 paras (75)
    selected = signals.select_by_target(fat, analysis, reduction)
    projected = len(selected) * 100 * signals.EXPECTED_COMPRESSION
    assert projected >= reduction * signals.SAFETY
    assert len(selected) == 3


def test_respects_fraction_cap():
    # Huge target can't force more than 60% of eligible paragraphs.
    fat = {i: 1.0 for i in range(10)}
    analysis = _analysis({i: 100 for i in range(10)})
    selected = signals.select_by_target(fat, analysis, reduction=100000)
    assert len(selected) <= int(signals.MAX_SELECT_FRACTION * 10)
    assert len(selected) == 6


def test_empty_fat_map():
    assert signals.select_by_target({}, _analysis({}), reduction=100) == []


def test_deterministic_and_index_tiebreak():
    fat = {0: 0.5, 1: 0.5, 2: 0.5, 3: 0.5}
    analysis = _analysis({0: 100, 1: 100, 2: 100, 3: 100})
    first = signals.select_by_target(fat, analysis, reduction=10)
    second = signals.select_by_target(fat, analysis, reduction=10)
    assert first == second
    # With all-equal scores, the lowest index wins the single needed slot.
    assert first == [0]


def test_get_candidates_glue(monkeypatch):
    """get_candidates spaCy path: glue runs without error and returns well-formed
    candidates with fat_index/routing_reason. spaCy is mocked out (it only feeds
    analyze_paragraphs, which we replace), so this runs anywhere."""
    paras = [f"Paragraph {i} " + "word " * 60 for i in range(8)]
    text = "\n\n".join(paras)
    guarded, qmap = guard(text)
    state = {
        "text": guarded, "qmap": qmap, "target": word_count(guarded, qmap) - 200,
        # realistic optional density arrays (aligned to paragraph count)
        "proselint_para_hits": [i for i in range(8)],
        "intensifier_para_hits": [0] * 8,
    }

    def fake_analyze(paragraphs, nlp):
        out = []
        for i, p in enumerate(paragraphs):
            w = len(p.split())
            out.append({
                "index": i, "words": w, "est_savings": float(w) * 0.1,
                "mean_sent_len": w, "mean_dep_depth": 4 + i, "inv_flesch": 30 + i,
                "is_quote": False, "focus": [f"snippet {i}"], "sentences": [],
            })
        return out

    monkeypatch.setattr(step_concision, "_load_nlp", lambda: object())
    monkeypatch.setattr("kopi.signals.analyze_paragraphs", fake_analyze)

    cands = step_concision.get_candidates(state)
    assert cands, "expected candidates"
    for c in cands:
        assert set(c) >= {"index", "text", "budget", "focus", "fat_index", "routing_reason"}
        assert "fat-index" in c["routing_reason"]
    # Document order preserved.
    assert [c["index"] for c in cands] == sorted(c["index"] for c in cands)

    # Second pass excludes already-edited paragraphs.
    state["llm_edited_indices"] = {c["index"] for c in cands}
    assert step_concision.get_candidates(state) == []


def test_full_pipeline_fat_then_select_is_stable():
    analysis = [
        {"index": 0, "words": 120, "est_savings": 12.0, "mean_sent_len": 30,
         "mean_dep_depth": 7, "inv_flesch": 60, "is_quote": False, "focus": [], "sentences": []},
        {"index": 1, "words": 90, "est_savings": 4.0, "mean_sent_len": 18,
         "mean_dep_depth": 4, "inv_flesch": 25, "is_quote": False, "focus": [], "sentences": []},
        {"index": 2, "words": 60, "est_savings": 1.0, "mean_sent_len": 12,
         "mean_dep_depth": 3, "inv_flesch": 10, "is_quote": False, "focus": [], "sentences": []},
    ]
    fat = signals.paragraph_fat_index(analysis)
    a = signals.select_by_target(fat, analysis, reduction=20)
    b = signals.select_by_target(fat, analysis, reduction=20)
    assert a == b
    assert 0 in a  # the fattest paragraph is always flagged
