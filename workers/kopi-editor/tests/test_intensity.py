"""Test the intensity bands and the top-up shortfall trigger, the loop tying a requested
reduction to how hard the editor cuts.
"""
from kopi import intensity


def test_no_reduction_is_clarity():
    p = intensity.plan(0, 5000)
    assert p["mode"] == "clarity"
    assert p["frac"] == 0.0
    assert p["allow_drop"] is False
    assert p["max_compression"] <= 0.10  # a clarity pass barely changes length


def test_bands_scale_with_ratio():
    # 5000-word document; the band follows reduction / original_words.
    assert intensity.plan(150, 5000)["mode"] == "light"        # r = 0.03
    assert intensity.plan(400, 5000)["mode"] == "firm"         # r = 0.08
    assert intensity.plan(900, 5000)["mode"] == "aggressive"   # r = 0.18
    # Only the aggressive band may drop whole sentences.
    assert intensity.plan(150, 5000)["allow_drop"] is False
    assert intensity.plan(900, 5000)["allow_drop"] is True


def test_same_word_count_is_more_aggressive_on_a_shorter_document():
    # 500 words is a major cut on a short paper, a light one on a long thesis.
    assert intensity.plan(500, 2500)["mode"] == "aggressive"   # r = 0.20
    assert intensity.plan(500, 9000)["mode"] == "firm"         # r = 0.056


def test_paragraph_floor_tracks_fraction():
    assert intensity.paragraph_floor(100, 0.0) == 100
    assert intensity.paragraph_floor(100, 0.30) == 70


def test_topup_triggers_on_shortfall_only():
    from kopi import step_concision
    from kopi.quote_guard import guard

    paras = [f"Paragraph {i} " + "word " * 80 for i in range(6)]
    text = "\n\n".join(paras)
    quoted = guard(text)
    guarded, qmap = quoted["text"], quoted["qmap"]
    original = len(text.split())

    # Asked to remove 200 but nothing was cut yet -> a top-up is planned.
    state = {
        "text": guarded,
        "qmap": qmap,
        "reduction": 200,
        "original_words": original,
        "counts": {"step1": original},
    }
    extra = step_concision.topup_candidates(state)
    assert extra and all(c["routing_reason"].startswith("top-up") for c in extra)

    # No reduction requested -> never a top-up.
    state_clarity = dict(state, reduction=0)
    assert step_concision.topup_candidates(state_clarity) == []
