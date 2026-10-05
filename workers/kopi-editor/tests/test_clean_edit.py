"""_clean_edit: collapse stray paragraph splits + strip editorial meta-notes."""
from kopi.step_concision import _clean_edit


def test_collapses_internal_newlines_to_one_paragraph():
    out = _clean_edit("First sentence here.\n\nSecond sentence after a split.")
    assert "\n" not in out
    assert out == "First sentence here. Second sentence after a split."


def test_strips_trailing_editorial_note():
    out = _clean_edit(
        "The data were analysed to test the hypothesis. "
        "(Note: the original sentence was split into two for clarity.)"
    )
    assert "Note" not in out and "clarity" not in out
    assert out == "The data were analysed to test the hypothesis."


def test_strips_reasoning_think_block():
    out = _clean_edit(
        "<think>The user wants this tightened. I'll cut the filler.</think>"
        "The data were analysed to test the hypothesis."
    )
    assert "<think>" not in out and "filler" not in out
    assert out == "The data were analysed to test the hypothesis."


def test_strips_inline_meta_paren_but_keeps_real_parentheticals():
    # An editorial note is removed...
    assert "rephrased" not in _clean_edit("Text here (rephrased for concision) continues.")
    # ...but a genuine content parenthetical (a citation) is preserved.
    kept = _clean_edit("Personalisation (Miller, 2011) reshapes everyday life.")
    assert "(Miller, 2011)" in kept
