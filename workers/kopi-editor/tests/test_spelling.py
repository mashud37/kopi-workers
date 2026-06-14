"""British-spelling normaliser: maps American spellings, preserves quotes."""
from kopi.step_plain import _apply_lookup
from kopi.data_spelling import AMERICAN_TO_BRITISH


def _normalise(text):
    return _apply_lookup(text, AMERICAN_TO_BRITISH, [], "x")


def test_common_american_spellings_are_mapped():
    for am, br in [
        ("behaviors", "behaviours"), ("personalization", "personalisation"),
        ("recognize", "recognise"), ("analyze", "analyse"), ("center", "centre"),
        ("socializing", "socialising"), ("prioritizes", "prioritises"),
    ]:
        assert AMERICAN_TO_BRITISH.get(am) == br


def test_normalise_preserves_case_and_quote_tokens():
    out = _normalise("Recognize the behaviors §Q0§ here.")
    assert "Recognise" in out          # leading capital preserved
    assert "behaviours" in out
    assert "§Q0§" in out               # guarded quote token untouched


def test_does_not_touch_non_ise_lookalikes():
    # 'size', 'prize', 'seize' are NOT -ise verbs and must be left alone.
    out = _normalise("The prize size made them seize it.")
    assert "prize" in out and "size" in out and "seize" in out
